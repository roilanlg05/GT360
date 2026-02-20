"""
WebSocket for Real-Time Flight Position Tracking.

Streams aircraft positions from ADSB.lol with adaptive intervals
based on ETA to destination.

Authentication: JWT token as query parameter (same as trips WS).
"""

import asyncio
import logging
from typing import Optional, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from features.auth.utils import decode_token
from features.flights.utils.ws_manager import manager
from features.flights.services.tracking_cache import get_tracking_cache
from features.flights.models.tracking_models import FlightTrackingState, TrackingInterval

logger = logging.getLogger(__name__)


router = APIRouter(tags=["Flight WebSockets"])


# Active tracking tasks per WebSocket
_tracking_tasks: Dict[WebSocket, Dict[str, asyncio.Task]] = {}


async def _poll_position(
    ws: WebSocket,
    flight_number: str,
    trip_id: str,
    origin_icao: Optional[str],
    destination_icao: Optional[str],
    initial_interval: int = 0,
):
    """
    Poll flight position at adaptive intervals.

    Intervals adjust based on ETA:
    - >60 min: every 20 minutes
    - 30-60 min: every 5 minutes
    - 20-30 min: every 2.5 minutes
    - 10-20 min: every 1 minute
    - <10 min: every 1 second (real-time)

    If initial_interval > 0, the first poll is delayed by that amount
    (because a snapshot was already sent before this task was created).
    """
    cache = await get_tracking_cache()

    try:
        # If a snapshot was already sent, respect its interval before the next fetch
        if initial_interval > 0:
            await asyncio.sleep(initial_interval)

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
           (origin_icao and destination_icao are optional — auto-detected via routeset)
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

                await ws.send_json({
                    "type": "tracking_started",
                    "flight_number": flight_number,
                    "trip_id": trip_id,
                })

                # Fetch and send snapshot immediately so the client gets
                # current data right away, regardless of the polling interval.
                initial_interval = 0
                try:
                    cache = await get_tracking_cache()
                    logger.info(f"[TRACKING] Fetching snapshot for {flight_number} (trip={trip_id}, origin={origin_icao}, dest={destination_icao})")
                    snapshot = await cache.get_or_fetch_position(
                        flight_number=flight_number,
                        trip_id=trip_id,
                        origin_icao=origin_icao,
                        destination_icao=destination_icao,
                    )
                    logger.info(f"[TRACKING] Snapshot result for {flight_number}: {'found' if snapshot else 'None (flight not found in ADSB.lol)'}")

                    if snapshot:
                        await ws.send_json({
                            "type": "position_update",
                            "position": snapshot.model_dump(),
                        })
                        # Polling task starts sleeping from this interval so it
                        # doesn't double-fetch right after the snapshot.
                        initial_interval = snapshot.interval_seconds
                except Exception as e:
                    logger.error(f"[TRACKING] Error fetching snapshot for {flight_number}: {type(e).__name__}: {e}", exc_info=True)

                # Also join the room for pub/sub updates
                await manager.subscribe_tracking(ws, flight_number, trip_id)

                # Start polling task
                task = asyncio.create_task(
                    _poll_position(
                        ws, flight_number, trip_id,
                        origin_icao, destination_icao,
                        initial_interval=initial_interval,
                    )
                )
                _tracking_tasks[ws][task_key] = task
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
        pass  # Normal disconnection
    except (ConnectionClosedError, ConnectionClosedOK):
        pass  # Connection closed by client
    except Exception as e:
        logger.error(f"[WS] Unhandled exception — closing connection: {type(e).__name__}: {e}", exc_info=True)
    finally:
        # Cleanup: cancel all tracking tasks
        if ws in _tracking_tasks:
            for task in _tracking_tasks[ws].values():
                task.cancel()
            del _tracking_tasks[ws]

        try:
            await manager.disconnect(ws)
        except Exception:
            pass

        # Only close if connection is still open
        if ws.client_state == WebSocketState.CONNECTED:
            try:
                await ws.close(code=1000)
            except Exception:
                pass
