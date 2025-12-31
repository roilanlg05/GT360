from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from shared.redis.redis_client import redis_client as redis
from features.trips.utils.ws_manager import manager
import json
from shared.db.db_config import engine, AsyncSession
from psqlmodel import Select
from typing import Set, List
from shared.db.schemas import Trip
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
            trip_ids = set(msg.get("trip_ids", []))

            if action == "subscribe":
                requested: Set[str] = set()

                # normalizar ids a str y limpiar vacíos
                for tid in trip_ids:
                    if isinstance(tid, (bytes, bytearray)):
                        tid = tid.decode("utf-8", errors="ignore")
                    tid = str(tid).strip()
                    if tid:
                        requested.add(tid)

                if not requested:
                    await ws.send_json({"type": "subscribed", "trip_ids": [], "trips": []})
                    continue

                # 1) Redis: un solo MGET
                keys = [f"trip:{tid}" for tid in requested]
                vals = await redis.mget(keys)

                valid: Set[str] = set()
                now: List[dict] = []
                missing: List[str] = []

                for tid, raw in zip(requested, vals):
                    if not raw:
                        missing.append(tid)
                        continue

                    if isinstance(raw, (bytes, bytearray)):
                        raw = raw.decode("utf-8", errors="ignore")

                    try:
                        trip = json.loads(raw)
                        if str(trip.get("location_id")) == str(location_id):
                            valid.add(tid)
                            now.append(trip)
                        else:
                            # existe pero es de otra location -> inválido
                            pass
                    except Exception:
                        # si está corrupto, lo validamos por DB
                        missing.append(tid)

                # 2) DB: una sola query con .In(...)
                if missing:
                    async with AsyncSession(engine) as session:
                        try:
                            rows = await session.exec(
                                Select(Trip).Where(
                                    (Trip.location_id == location_id) & (Trip.id.In(missing))
                                )
                            ).all() or []

                            for r in rows:
                                valid.add(str(r.id))

                        except Exception as e:
                            print("DB validate error:", e)

                await manager.subscribe_trips(ws, valid)

                # responder con trips cacheados (solo Redis). Los validados por DB pueden no estar en Redis todavía.
                await ws.send_json({"type": "subscribed", "trip_ids": list(valid), "trips": now})

            elif action == "unsubscribe":
                await manager.unsubscribe_trips(ws, trip_ids)
                await ws.send_json({"type": "unsubscribed", "trip_ids": list(trip_ids)})

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
