"""
WebSocket for Flight Push Notifications.

Receives status updates from AeroDataBox via webhooks and broadcasts
to connected clients in real-time.

Authentication: JWT token as query parameter (same as trips WS).
Subscription: By location_id + flight_numbers list.
"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from starlette.websockets import WebSocketState
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from features.auth.utils import decode_token
from features.flights.utils.ws_manager import manager
from features.flights.services.tracking_cache import get_tracking_cache
from shared.db.schemas.entities.locations import Location

from psqlmodel import Select, AsyncSession
from shared.db.db_config import engine

from uuid import UUID
from fastapi import HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Flight WebSockets"])


async def get_location_iata(location_id: str) -> str | None:
    """Get location name (IATA code) from database."""
    try:
        async with AsyncSession(engine) as session:
            location = await session.exec(
                Select(Location).Where(Location.id == location_id)
            ).first()
        if location:
            print(f"Location IATA for ID {location_id}: {location}")
            return location.name
    except Exception:
        pass
    return None


@router.websocket("/ws/flights/push")
async def ws_flight_push(
    ws: WebSocket,
    location_id: str = Query(..., description="Location ID to monitor"),
    flight_numbers: str = Query(..., description="Comma-separated flight numbers"),
    token: str = Query(..., description="JWT token for authentication"),
):
    """
    WebSocket for push notifications.

    Query params:
        location_id: Location ID to monitor (we get IATA from DB)
        flight_numbers: Comma-separated list of flight numbers (e.g., "WN1036,AA123")
        token: JWT token for authentication

    Messages from server:
        - {"type": "connected", "location_iata": "...", "flight_numbers": [...]}
        - {"type": "flight_update", "flight_number": "...", "status": "...", "message": "...", ...}
        - {"type": "pong"}
        - {"type": "error", "code": int, "detail": "..."}

    Messages from client:
        - {"action": "ping", "token": "..."} - keep-alive with token validation
        - {"action": "subscribe", "flight_number": "..."} - subscribe to additional flight
        - {"action": "unsubscribe", "flight_number": "..."} - unsubscribe from flight
    """

    try:
        uuid_location_id = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de location inválido")


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

    # Get location IATA from database
    location_iata = await get_location_iata(uuid_location_id)
    
    if not location_iata:
        await ws.accept()
        await ws.send_json({
            "type": "error",
            "code": 404,
            "detail": "Location not found"
        })
        await ws.close(code=1008)
        return

    # Parse flight numbers
    flight_list = [fn.strip().upper() for fn in flight_numbers.split(",") if fn.strip()]
    if not flight_list:
        await ws.accept()
        await ws.send_json({
            "type": "error",
            "code": 400,
            "detail": "No flight numbers provided"
        })
        await ws.close(code=1008)
        return

    # Connect and store location_iata in connection metadata
    await manager.connect(ws, claims, location_iata)

    # Subscribe to each flight number
    for flight_number in flight_list:
        await manager.subscribe_push(ws, location_iata, flight_number)

    # Send connection confirmation
    try:
        await ws.send_json({
            "type": "connected",
            "location_id": location_id,
            "location_iata": location_iata,
            "flight_numbers": flight_list,
        })
    except Exception:
        await manager.disconnect(ws)
        return

    # Send snapshot of recent notifications (avoids missing updates)
    try:
        cache = await get_tracking_cache()
        notifications = await cache.get_notifications_for_flights(
            arrival_iata=location_iata,
            flight_numbers=flight_list,
            limit_per_flight=10
        )

        if notifications:
            await ws.send_json({
                "type": "snapshot",
                "notifications": notifications,
                "count": len(notifications),
            })
    except Exception as e:
        logger.warning(f"Error sending notification snapshot: {e}")

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

            # Subscribe to additional flight
            if action == "subscribe":
                new_flight = msg.get("flight_number", "").strip().upper()
                if new_flight:
                    await manager.subscribe_push(ws, location_iata, new_flight)
                    await ws.send_json({
                        "type": "subscribed",
                        "flight_number": new_flight,
                    })

                    # Send snapshot for the new flight
                    try:
                        cache = await get_tracking_cache()
                        notifications = await cache.get_notifications(
                            arrival_iata=location_iata,
                            flight_number=new_flight,
                            limit=10
                        )
                        if notifications:
                            await ws.send_json({
                                "type": "snapshot",
                                "flight_number": new_flight,
                                "notifications": notifications,
                                "count": len(notifications),
                            })
                    except Exception:
                        pass
                continue

            # Unsubscribe from flight
            if action == "unsubscribe":
                old_flight = msg.get("flight_number", "").strip().upper()
                if old_flight:
                    await manager.unsubscribe_push(ws, location_iata, old_flight)
                    await ws.send_json({
                        "type": "unsubscribed",
                        "flight_number": old_flight,
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
    except Exception:
        pass  # Suppress all WS errors (client disconnected)
    finally:
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
