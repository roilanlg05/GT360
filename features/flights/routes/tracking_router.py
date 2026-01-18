"""
Flight Tracking API - Subscription management endpoints.

Endpoints for:
- Subscribing flights for push notifications (AeroDataBox)
- Managing subscriptions
- Getting tracking status
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from features.flights.models.tracking_models import (
    SubscribeRequest,
    SubscribeResponse,
    FlightSubscription,
    FlightTrackingState,
    FlightPosition,
)
from features.flights.services.push_api_client import get_push_client
from features.flights.services.tracking_cache import get_tracking_cache


router = APIRouter(prefix="/v1/flights/tracking", tags=["Flight Tracking"])


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe_flights(request: SubscribeRequest):
    """
    Subscribe to push notifications for multiple flights.

    This creates webhook subscriptions with AeroDataBox.
    When flight status changes, we receive notifications via webhook
    and broadcast them through the WebSocket.

    Request body:
        flights: List of {flight_number, trip_id, date_local}

    Returns:
        SubscribeResponse with subscription results
    """
    if not request.flights:
        raise HTTPException(400, "No flights to subscribe")

    if len(request.flights) > 50:
        raise HTTPException(400, "Maximum 50 flights per request")

    push_client = await get_push_client()
    cache = await get_tracking_cache()

    subscribed = []
    failed = []

    for flight in request.flights:
        try:
            # Create subscription with AeroDataBox
            subscription = await push_client.create_subscription(
                flight_number=flight.flight_number,
                date_local=flight.date_local,
                trip_id=flight.trip_id,
            )

            if subscription.subscription_id:
                # Save to cache
                await cache.save_subscription(subscription)
                subscribed.append(subscription)
            else:
                failed.append({
                    "flight_number": flight.flight_number,
                    "trip_id": flight.trip_id,
                    "error": subscription.status,
                })

        except Exception as e:
            failed.append({
                "flight_number": flight.flight_number,
                "trip_id": flight.trip_id,
                "error": str(e),
            })

    return SubscribeResponse(
        subscribed=subscribed,
        failed=failed,
        total=len(request.flights),
        success_count=len(subscribed),
        failure_count=len(failed),
    )


@router.delete("/subscribe/{flight_number}")
async def unsubscribe_flight(
    flight_number: str,
    trip_id: str = Query(..., description="Trip ID"),
):
    """
    Unsubscribe from push notifications for a flight.

    Args:
        flight_number: Flight number (path param)
        trip_id: Trip ID (query param)

    Returns:
        {"status": "ok"} if successful
    """
    push_client = await get_push_client()
    cache = await get_tracking_cache()

    # Delete from AeroDataBox
    await push_client.delete_subscription(flight_number)

    # Delete from cache
    await cache.delete_subscription(flight_number, trip_id)

    return {"status": "ok", "flight_number": flight_number, "trip_id": trip_id}


@router.get("/subscription/{flight_number}", response_model=Optional[FlightSubscription])
async def get_subscription(
    flight_number: str,
    trip_id: str = Query(..., description="Trip ID"),
):
    """
    Get subscription details for a flight.

    Args:
        flight_number: Flight number (path param)
        trip_id: Trip ID (query param)

    Returns:
        FlightSubscription if exists, null otherwise
    """
    cache = await get_tracking_cache()
    subscription = await cache.get_subscription(flight_number, trip_id)
    return subscription


@router.get("/state/{flight_number}", response_model=Optional[FlightTrackingState])
async def get_tracking_state(
    flight_number: str,
    trip_id: str = Query(..., description="Trip ID"),
):
    """
    Get current tracking state for a flight.

    Includes:
    - Current status (scheduled, departed, landed, etc.)
    - Whether real-time tracking is active
    - Last known position
    - Current tracking interval

    Args:
        flight_number: Flight number (path param)
        trip_id: Trip ID (query param)

    Returns:
        FlightTrackingState if exists, null otherwise
    """
    cache = await get_tracking_cache()
    state = await cache.get_tracking_state(flight_number, trip_id)
    return state


@router.get("/position/{flight_number}", response_model=Optional[FlightPosition])
async def get_flight_position(
    flight_number: str,
    trip_id: str = Query(..., description="Trip ID"),
    origin_icao: Optional[str] = Query(None, description="Origin airport ICAO"),
    destination_icao: Optional[str] = Query(None, description="Destination airport ICAO"),
):
    """
    Get current position for a flight.

    Uses 2-second cache with singleflight pattern to prevent
    duplicate API calls.

    Args:
        flight_number: Flight number (path param)
        trip_id: Trip ID (query param)
        origin_icao: Origin airport ICAO (optional)
        destination_icao: Destination airport ICAO (for ETA calculation)

    Returns:
        FlightPosition with lat/lon, altitude, ETA, etc.
    """
    cache = await get_tracking_cache()

    position = await cache.get_or_fetch_position(
        flight_number=flight_number,
        trip_id=trip_id,
        origin_icao=origin_icao,
        destination_icao=destination_icao,
    )

    return position


@router.get("/active")
async def get_active_flights():
    """
    Get list of all actively tracked flights.

    Returns:
        List of "flight_number:trip_id" strings
    """
    cache = await get_tracking_cache()
    active = await cache.get_active_flights()
    return {"active_flights": active, "count": len(active)}


@router.post("/activate/{flight_number}")
async def activate_tracking(
    flight_number: str,
    trip_id: str = Query(..., description="Trip ID"),
):
    """
    Manually activate real-time tracking for a flight.

    Normally tracking activates automatically when we receive
    a "departed" push notification. Use this to manually start.

    Args:
        flight_number: Flight number (path param)
        trip_id: Trip ID (query param)
    """
    cache = await get_tracking_cache()

    await cache.update_tracking_active(
        flight_number=flight_number,
        trip_id=trip_id,
        is_active=True,
    )

    return {
        "status": "ok",
        "flight_number": flight_number,
        "trip_id": trip_id,
        "tracking_active": True,
    }


@router.post("/deactivate/{flight_number}")
async def deactivate_tracking(
    flight_number: str,
    trip_id: str = Query(..., description="Trip ID"),
):
    """
    Manually deactivate real-time tracking for a flight.

    Normally tracking deactivates automatically when we receive
    a "landed" push notification. Use this to manually stop.

    Args:
        flight_number: Flight number (path param)
        trip_id: Trip ID (query param)
    """
    cache = await get_tracking_cache()

    await cache.update_tracking_active(
        flight_number=flight_number,
        trip_id=trip_id,
        is_active=False,
    )

    return {
        "status": "ok",
        "flight_number": flight_number,
        "trip_id": trip_id,
        "tracking_active": False,
    }
