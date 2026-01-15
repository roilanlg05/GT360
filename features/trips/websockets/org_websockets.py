from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from features.trips.utils.org_ws_manager import org_manager
from features.auth.utils import decode_token

router = APIRouter()


@router.websocket("/ws/org")
async def ws_org_events(ws: WebSocket, organization_id: str, token: str):
    """
    WebSocket endpoint for organization-level events.

    Query params:
      - organization_id: UUID of the organization
      - token: JWT token for authentication

    Events received:
      - location_deleted: When a location is deleted with its hotels
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

    # Validate org_id matches token
    token_org_id = metadata.get("organization_id")
    if not token_org_id or str(token_org_id) != str(organization_id):
        await ws.close(code=1008)
        return

    # Connect to org room
    await org_manager.connect(ws, organization_id, claims)
    await org_manager.ensure_org_listener(organization_id)

    # Send connected confirmation
    await ws.send_json({
        "type": "connected",
        "organization_id": organization_id,
        "message": "Connected to organization events"
    })

    try:
        while True:
            msg = await ws.receive_json()
            action = msg.get("action")

            # Ping/Pong with token validation
            if action == "ping":
                ping_token = msg.get("token")
                if not ping_token:
                    await ws.send_json({"type": "error", "code": 401, "detail": "Token required"})
                    await ws.close(code=1008)
                    return

                try:
                    decode_token(ping_token)
                    await ws.send_json({"type": "pong"})
                except Exception:
                    await ws.send_json({"type": "error", "code": 401, "detail": "Invalid or expired token"})
                    await ws.close(code=1008)
                    return
                continue

            else:
                await ws.send_json({"type": "error", "detail": "Unknown action"})

    except WebSocketDisconnect:
        await org_manager.disconnect(ws)
    except Exception:
        await org_manager.disconnect(ws)
        try:
            await ws.close(code=1011)
        except Exception:
            pass
