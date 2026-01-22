"""
WebSocket for Flight Push Notifications.

Receives status updates from AeroDataBox via webhooks and broadcasts
to connected clients in real-time.

Authentication: JWT token as query parameter (same as trips WS).
"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from features.auth.utils import decode_token
from features.flights.utils.ws_manager import manager
from features.flights.services.tracking_cache import get_tracking_cache

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Flight WebSockets"])


@router.websocket("/ws/flights/push")
async def ws_flight_push(ws: WebSocket, trip_id: str, token: str):
    """
    WebSocket for push notifications.

    Query params:
        trip_id: Trip ID to subscribe to
        token: JWT token for authentication

    Messages from server:
        - {"type": "connected", "trip_id": "..."}
        - {"type": "push_notification", "trip_id": "...", "notification": {...}}
        - {"type": "pong"}
        - {"type": "error", "code": int, "detail": "..."}

    Messages from client:
        - {"action": "ping", "token": "..."} - keep-alive with token validation
        - {"action": "subscribe", "trip_id": "..."} - subscribe to additional trip
        - {"action": "unsubscribe", "trip_id": "..."} - unsubscribe from trip
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

    # Connect and subscribe to initial trip
    await manager.connect(ws, claims)
    await manager.subscribe_push(ws, trip_id)

    # Send connection confirmation
    try:
        await ws.send_json({
            "type": "connected",
            "trip_id": trip_id,
        })
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

            # Subscribe to additional trip
            if action == "subscribe":
                sub_trip_id = msg.get("trip_id")
                if sub_trip_id:
                    await manager.subscribe_push(ws, sub_trip_id)
                    await ws.send_json({
                        "type": "subscribed",
                        "trip_id": sub_trip_id,
                    })
                continue

            # Unsubscribe from trip
            if action == "unsubscribe":
                unsub_trip_id = msg.get("trip_id")
                if unsub_trip_id:
                    await manager.unsubscribe_push(ws, unsub_trip_id)
                    await ws.send_json({
                        "type": "unsubscribed",
                        "trip_id": unsub_trip_id,
                    })
                continue

            # Unknown action
            await ws.send_json({
                "type": "error",
                "detail": "Unknown action"
            })

    except WebSocketDisconnect:
        logger.debug("Push WebSocket disconnected normally")
    except (ConnectionClosedError, ConnectionClosedOK):
        logger.debug("Push WebSocket connection closed")
    except Exception as e:
        logger.warning(f"Push WebSocket error: {e}")
    finally:
        await manager.disconnect(ws)

        # Only close if connection is still open
        if ws.client_state == WebSocketState.CONNECTED:
            try:
                await ws.close(code=1000)
            except Exception:
                pass
