from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from shared.redis.redis_client import redis_client as redis
from features.trips.utils.ws_manager import manager
import json
from shared.db.db_config import engine, AsyncSession
from features.auth.utils import user_can_access_location, decode_token

router = APIRouter()

async def send_snapshot(ws: WebSocket, location_id: str) -> None:
    idx_key = f"loc:{location_id}:trips"
    trip_ids = await redis.smembers(idx_key)

    if not trip_ids:
        await ws.send_json({"type": "snapshot", "location_id": location_id, "trips": []})
        return

    # smembers puede devolver bytes; normalizamos a str
    norm_ids = []
    for tid in trip_ids:
        if isinstance(tid, (bytes, bytearray)):
            tid = tid.decode("utf-8", errors="ignore")
        norm_ids.append(str(tid))

    keys = [f"trip:{tid}" for tid in norm_ids]
    values = await redis.mget(keys)

    trips = []
    for v in values:
        if not v:
            continue
        if isinstance(v, (bytes, bytearray)):
            v = v.decode("utf-8", errors="ignore")
        try:
            trips.append(json.loads(v))
        except Exception:
            continue

    await ws.send_json({"type": "snapshot", "location_id": location_id, "trips": trips})


@router.websocket("/ws/trips")
async def ws_location_trips(ws: WebSocket, location_id: str, token: str):
    try:
        claims = decode_token(token)
    except Exception:
        await ws.close(code=1008)
        return

    metadata = claims.get("metadata")
    if not metadata:
        await ws.close(code=1008)
        return

    org_id = metadata.get("organization_id")

    async with AsyncSession(engine) as session:
        if not await user_can_access_location(session, org_id, location_id):
            await ws.close(code=1008)
            return

    await manager.connect(ws, location_id, claims)
    await manager.ensure_location_listener(location_id)
    await send_snapshot(ws, location_id)

    try:
        while True:
            msg = await ws.receive_json()
            action = msg.get("action")

            # --- Ping/Pong con validación de token ---
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

            if action == "subscribe":
                # Suscripción por location - ya está conectado a la room
                await ws.send_json({"type": "subscribed", "location_id": location_id})

            elif action == "unsubscribe":
                # Desuscripción de la location
                await ws.send_json({"type": "unsubscribed", "location_id": location_id})

            else:
                await ws.send_json({"type": "error", "detail": "Unknown action"})

    except WebSocketDisconnect:
        await manager.disconnect(ws)
    except Exception:
        await manager.disconnect(ws)
        try:
            await ws.close(code=1011)
        except Exception:
            pass
