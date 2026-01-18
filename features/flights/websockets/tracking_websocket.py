"""
WebSocket for Real-Time Flight Position Tracking.

Streams aircraft positions from ADSB.lol with adaptive intervals
based on ETA to destination.

Authentication: JWT token as query parameter (same as trips WS).
"""

import asyncio
from typing import Optional, Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from features.auth.utils import decode_token
from features.flights.utils.ws_manager import manager
from features.flights.services.tracking_cache import get_tracking_cache
from features.flights.models.tracking_models import FlightTrackingState, TrackingInterval


router = APIRouter(tags=["Flight WebSockets"])


# Active tracking tasks per WebSocket
_tracking_tasks: Dict[WebSocket, Dict[str, asyncio.Task]] = {}


async def _poll_position(
    ws: WebSocket,
    flight_number: str,
    trip_id: str,
    origin_icao: Optional[str],
    destination_icao: Optional[str],
):
    """
    Poll flight position at adaptive intervals.

    Intervals adjust based on ETA:
    - >60 min: every 20 minutes
    - 30-60 min: every 5 minutes
    - 20-30 min: every 2.5 minutes
    - 10-20 min: every 1 minute
    - <10 min: every 1 second (real-time)
    """
    cache = await get_tracking_cache()

    try:
        while True:
            # Get position (uses cache with singleflight pattern)
            position = await cache.get_or_fetch_position(
                flight_number=flight_number,
                trip_id=trip_id,
                origin_icao=origin_icao,
                destination_icao=destination_icao,
            )

            if position:
                # Send position to this client
                try:
                    await ws.send_json({
                        "type": "position_update",
                        "position": position.model_dump(),
                    })
                except Exception:
                    # WebSocket closed
                    break

                # Also publish to Redis for other listeners
                await cache.publish_position_update(position)

                # Determine next poll interval based on ETA
                interval = position.interval_seconds
            else:
                # No position found, use default interval
                interval = 60  # 1 minute

            # Wait before next poll
            await asyncio.sleep(interval)

    except asyncio.CancelledError:
        pass
    except Exception:
        pass


@router.websocket("/ws/flights/tracking")
async def ws_flight_tracking(ws: WebSocket, token: str):
    """
    WebSocket for real-time flight tracking.

    Query params:
        token: JWT token for authentication

    Messages from server:
        - {"type": "connected"}
        - {"type": "position_update", "position": {...}}
        - {"type": "tracking_started", "flight_number": "...", "trip_id": "..."}
        - {"type": "tracking_stopped", "flight_number": "...", "trip_id": "..."}
        - {"type": "pong"}
        - {"type": "error", "code": int, "detail": "..."}

    Messages from client:
        - {"action": "ping", "token": "..."} - keep-alive with token validation
        - {"action": "track", "flight_number": "...", "trip_id": "...",
           "origin_icao": "...", "destination_icao": "..."} - start tracking
        - {"action": "stop", "flight_number": "...", "trip_id": "..."} - stop tracking
    """
    # Validate token
    try:
        claims = decode_token(token)
    except Exception:
        await ws.close(code=1008)
        return

    metadata = claims.get("metadata")
    if not metadata:
        await ws.close(code=1008)
        return

    # Connect
    await manager.connect(ws, claims)
    _tracking_tasks[ws] = {}

    # Send connection confirmation
    try:
        await ws.send_json({"type": "connected"})
    except Exception:
        await manager.disconnect(ws)
        return

    try:
        while True:
            msg = await ws.receive_json()
            action = msg.get("action")

            # Ping/pong with token validation
            if action == "ping":
                ping_token = msg.get("token")
                if not ping_token:
                    await ws.send_json({
                        "type": "error",
                        "code": 401,
                        "detail": "Token required"
                    })
                    await ws.close(code=1008)
                    return

                try:
                    decode_token(ping_token)
                    await ws.send_json({"type": "pong"})
                except Exception:
                    await ws.send_json({
                        "type": "error",
                        "code": 401,
                        "detail": "Invalid or expired token"
                    })
                    await ws.close(code=1008)
                    return
                continue

            # Start tracking a flight
            if action == "track":
                flight_number = msg.get("flight_number", "").strip().upper()
                trip_id = msg.get("trip_id", "")
                origin_icao = msg.get("origin_icao")
                destination_icao = msg.get("destination_icao")

                if not flight_number or not trip_id:
                    await ws.send_json({
                        "type": "error",
                        "detail": "flight_number and trip_id required"
                    })
                    continue

                task_key = f"{flight_number}:{trip_id}"

                # Check if already tracking
                if task_key in _tracking_tasks.get(ws, {}):
                    await ws.send_json({
                        "type": "error",
                        "detail": f"Already tracking {flight_number}"
                    })
                    continue

                # Start polling task
                task = asyncio.create_task(
                    _poll_position(
                        ws, flight_number, trip_id,
                        origin_icao, destination_icao
                    )
                )
                _tracking_tasks[ws][task_key] = task

                # Also join the room for pub/sub updates
                await manager.subscribe_tracking(ws, flight_number, trip_id)

                await ws.send_json({
                    "type": "tracking_started",
                    "flight_number": flight_number,
                    "trip_id": trip_id,
                })
                continue

            # Stop tracking a flight
            if action == "stop":
                flight_number = msg.get("flight_number", "").strip().upper()
                trip_id = msg.get("trip_id", "")

                if not flight_number or not trip_id:
                    await ws.send_json({
                        "type": "error",
                        "detail": "flight_number and trip_id required"
                    })
                    continue

                task_key = f"{flight_number}:{trip_id}"

                # Cancel polling task
                if ws in _tracking_tasks and task_key in _tracking_tasks[ws]:
                    _tracking_tasks[ws][task_key].cancel()
                    del _tracking_tasks[ws][task_key]

                # Leave the room
                await manager.unsubscribe_tracking(ws, flight_number, trip_id)

                await ws.send_json({
                    "type": "tracking_stopped",
                    "flight_number": flight_number,
                    "trip_id": trip_id,
                })
                continue

            # Unknown action
            await ws.send_json({
                "type": "error",
                "detail": "Unknown action"
            })

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        # Cleanup: cancel all tracking tasks
        if ws in _tracking_tasks:
            for task in _tracking_tasks[ws].values():
                task.cancel()
            del _tracking_tasks[ws]

        await manager.disconnect(ws)
        try:
            await ws.close(code=1011)
        except Exception:
            pass
