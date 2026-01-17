"""
Flight Tracking Router - REST and WebSocket endpoints for flight tracking.

Features:
- Single flight tracking (REST + WebSocket)
- Batch flight tracking
- Metrics and rate limit status
- Adaptive WebSocket polling intervals
"""

import asyncio
from typing import List

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Query
import httpx

from features.flights.models import (
    FlightSnapshot,
    EtaOnly,
    Leg,
    BatchFlightRequest,
    BatchFlightResponse,
    MetricsResponse,
    RateLimitResponse,
)
from features.flights.services.flight_cache import get_flight_cache
from features.auth.utils import decode_token


router = APIRouter(tags=["Flights"])


# =========================================================
# Single Flight Endpoints
# =========================================================

@router.get("/v1/flights/{flight_number}/{date_local}", response_model=FlightSnapshot)
async def get_flight_snapshot(flight_number: str, date_local: str) -> FlightSnapshot:
    """
    Get full flight status snapshot.

    Uses Redis micro-cache with intelligent TTL based on flight status:
    - Landed/Arrived: 60s cache
    - En route (close): 2-3s cache
    - En route (far): 5-10s cache
    - Scheduled: 15s cache

    Args:
        flight_number: Flight number (e.g., WN1234, AA567)
        date_local: Local departure date (YYYY-MM-DD)

    Returns:
        FlightSnapshot with status, ETA, position, and recommended ws_interval
    """
    cache = await get_flight_cache()
    try:
        return await cache.get_or_fetch(flight_number, date_local)
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"AeroDataBox error: {e.response.text}")
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    except Exception as e:
        raise HTTPException(500, f"Internal error: {type(e).__name__}")


@router.get("/v1/flights/{flight_number}/{date_local}/eta", response_model=EtaOnly)
async def get_eta_only(flight_number: str, date_local: str) -> EtaOnly:
    """
    Get minimal ETA-only response for a flight.

    Lighter response than full snapshot - useful for dashboards.

    Args:
        flight_number: Flight number (e.g., WN1234, AA567)
        date_local: Local departure date (YYYY-MM-DD)

    Returns:
        EtaOnly with status, ETA, and minutes to arrival
    """
    cache = await get_flight_cache()
    try:
        snap = await cache.get_or_fetch(flight_number, date_local)
        return EtaOnly(
            flight_number=snap.flight_number,
            date_local=snap.date_local,
            status=snap.status,
            eta_utc=snap.eta_utc,
            minutes_to_arrival=snap.minutes_to_arrival,
            provider_last_updated_utc=snap.provider_last_updated_utc,
            cached_at_utc=snap.cached_at_utc,
            cache_ttl_seconds=snap.cache_ttl_seconds,
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"AeroDataBox error: {e.response.text}")
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    except Exception as e:
        raise HTTPException(500, f"Internal error: {type(e).__name__}")


@router.get("/v1/flights/{flight_number}/{date_local}/legs", response_model=List[Leg])
async def get_legs(flight_number: str, date_local: str) -> List[Leg]:
    """
    Get flight legs/segments.

    Args:
        flight_number: Flight number (e.g., WN1234, AA567)
        date_local: Local departure date (YYYY-MM-DD)

    Returns:
        List of Leg objects with departure/arrival times
    """
    cache = await get_flight_cache()
    try:
        snap = await cache.get_or_fetch(flight_number, date_local)
        return snap.legs
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"AeroDataBox error: {e.response.text}")
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    except Exception as e:
        raise HTTPException(500, f"Internal error: {type(e).__name__}")


# =========================================================
# Batch Flight Endpoint
# =========================================================

@router.post("/v1/flights/batch", response_model=BatchFlightResponse)
async def get_flights_batch(
    request: BatchFlightRequest,
    max_concurrent: int = Query(10, ge=1, le=20, description="Max concurrent API requests")
):
    """
    Fetch multiple flights in parallel.

    Efficient for dashboards that need to track multiple flights.
    Uses the same cache as single flight endpoints.

    Request body:
    ```json
    {
        "flights": [
            {"flight_number": "WN1234", "date_local": "2026-01-16"},
            {"flight_number": "AA567", "date_local": "2026-01-16"}
        ]
    }
    ```

    Args:
        request: BatchFlightRequest with list of flights
        max_concurrent: Max concurrent API requests (default 10, max 20)

    Returns:
        BatchFlightResponse with all flight snapshots
    """
    if not request.flights:
        raise HTTPException(400, "flights list cannot be empty")

    if len(request.flights) > 50:
        raise HTTPException(400, "Maximum 50 flights per batch request")

    # Validate and extract flight info
    flights_to_fetch = []
    for i, f in enumerate(request.flights):
        fn = f.get("flight_number")
        date = f.get("date_local")
        if not fn or not date:
            raise HTTPException(400, f"Flight at index {i} missing flight_number or date_local")
        flights_to_fetch.append((fn, date))

    cache = await get_flight_cache()
    try:
        snapshots = await cache.get_or_fetch_batch(flights_to_fetch, max_concurrent=max_concurrent)

        # Count cached vs API
        cached_count = 0
        api_count = 0
        for snap in snapshots:
            # If cache_ttl is high and status isn't an error, likely from cache
            if snap.status not in ["ERROR", "RATE_LIMITED"]:
                # This is a rough estimate - actual tracking is in metrics
                cached_count += 1

        return BatchFlightResponse(
            flights=snapshots,
            total=len(snapshots),
            cached=cached_count,
            from_api=len(snapshots) - cached_count
        )
    except Exception as e:
        raise HTTPException(500, f"Batch fetch error: {type(e).__name__}")


# =========================================================
# Metrics and Rate Limit Endpoints
# =========================================================

@router.get("/v1/flights/metrics", response_model=MetricsResponse)
async def get_flight_metrics(
    date: str = Query(None, description="Date in YYYY-MM-DD format (default: today)")
):
    """
    Get flight tracking metrics for a specific date.

    Tracks:
    - cache_hits: Requests served from cache
    - cache_misses: Requests that needed API call
    - api_calls: Actual API calls made
    - api_errors: Failed API calls
    - rate_limited: Requests blocked by rate limiter
    - flights_not_found: Flights not found in API

    Args:
        date: Date to get metrics for (default: today)

    Returns:
        MetricsResponse with all counters
    """
    cache = await get_flight_cache()
    metrics = await cache.get_metrics(date)

    from datetime import datetime, timezone
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    return MetricsResponse(
        date=date,
        cache_hits=metrics.get("cache_hits", 0),
        cache_misses=metrics.get("cache_misses", 0),
        api_calls=metrics.get("api_calls", 0),
        api_errors=metrics.get("api_errors", 0),
        rate_limited=metrics.get("rate_limited", 0),
        flights_not_found=metrics.get("flights_not_found", 0),
    )


@router.get("/v1/flights/rate-limit", response_model=RateLimitResponse)
async def get_rate_limit_status():
    """
    Get current rate limit status.

    Returns:
        RateLimitResponse with current usage and remaining quota
    """
    cache = await get_flight_cache()
    status = await cache.get_rate_limit_status()
    return RateLimitResponse(**status)


# =========================================================
# WebSocket - Adaptive Polling with Authentication
# =========================================================

@router.websocket("/v1/ws/flights/{flight_number}/{date_local}")
async def ws_flight(
    websocket: WebSocket,
    flight_number: str,
    date_local: str,
    token: str
) -> None:
    """
    Real-time flight tracking WebSocket with adaptive polling.

    Requires JWT token as query parameter for authentication.

    The polling interval adapts based on flight status:
    - Landed/Arrived: 10s (terminal state)
    - En route, close (<=15 min): 1s (real-time)
    - En route, medium (15-30 min): 2s
    - En route, far (30-60 min): 3s
    - En route, very far (>60 min): 5s
    - Scheduled/Boarding: 5s
    - Not found: 5s

    The interval is included in each snapshot as `ws_interval_seconds`.

    Args:
        flight_number: Flight number (e.g., WN1234, AA567)
        date_local: Local departure date (YYYY-MM-DD)
        token: JWT token for authentication
    """
    # Validate token
    try:
        claims = decode_token(token)
    except Exception:
        await websocket.close(code=1008)
        return

    if not claims.get("metadata"):
        await websocket.close(code=1008)
        return

    await websocket.accept()

    try:
        cache = await get_flight_cache()
    except Exception:
        await websocket.close(code=1011)
        return

    try:
        while True:
            # Check for incoming messages (ping/pong with token validation)
            try:
                # Non-blocking check for messages
                msg = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=0.1
                )
                action = msg.get("action")

                if action == "ping":
                    ping_token = msg.get("token")
                    if not ping_token:
                        await websocket.send_json({"type": "error", "code": 401, "detail": "Token required"})
                        await websocket.close(code=1008)
                        return

                    try:
                        decode_token(ping_token)
                        await websocket.send_json({"type": "pong"})
                    except Exception:
                        await websocket.send_json({"type": "error", "code": 401, "detail": "Invalid or expired token"})
                        await websocket.close(code=1008)
                        return

            except asyncio.TimeoutError:
                # No message received, continue with normal flow
                pass

            snap = await cache.get_or_fetch(flight_number, date_local)
            await websocket.send_text(snap.model_dump_json())

            # Use adaptive interval from snapshot
            interval = snap.ws_interval_seconds
            await asyncio.sleep(interval)

    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
