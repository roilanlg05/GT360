from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from shared.redis.redis_client import redis_client as redis
from features.trips.utils.ws_manager import manager
import json
from shared.db import engine, AsyncSession
from psqlmodel import Select
from typing import Set
from features.trips.schemas import Trip
from features.auth.utils import user_can_access_location, decode_token, get_ws_token

router = APIRouter()

async def send_snapshot(ws: WebSocket, location_id: str) -> None:
    """
    “Muy importante”: al conectar, enviar lo que esté en Redis primero (TTL 5 min),
    para que el UI pinte rápido antes de depender de updates.
    """
    idx_key = f"loc:{location_id}:trips"
    trip_ids = await redis.smembers(idx_key)

    if not trip_ids:
        await ws.send_json({"type": "snapshot", "location_id": location_id, "trips": []})
        return

    keys = [f"trip:{tid}" for tid in trip_ids]
    values = await redis.mget(keys)

    trips = []
    for v in values:
        if not v:
            continue
        try:
            trips.append(json.loads(v))
        except Exception:
            continue

    await ws.send_json({"type": "snapshot", "location_id": location_id, "trips": trips})


# ----------------- WEBSOCKET ENDPOINT -----------------

@router.websocket("/ws/trips")
async def ws_location_trips(ws: WebSocket, location_id: str):

    try:
        token = get_ws_token(ws)
    except Exception:
        await ws.close(code=1008)
        return

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

    # Arranca listener Redis para esta location (una sola vez por proceso)
    await manager.ensure_location_listener(location_id)

    # Snapshot primero (redis)
    await send_snapshot(ws, location_id)

    try:
        while True:
            msg = await ws.receive_json()
            action = msg.get("action")
            trip_ids = set(msg.get("trip_ids", []))

            if action == "subscribe":
                # Validación simple/rápida:
                # - si el trip está cacheado, verifica location_id dentro del JSON
                # - si no está cacheado, lo normal es consultar DB (o rechazar hasta snapshot)
                valid: Set[str] = set()
                for tid in trip_ids:
                    raw = await redis.get(f"trip:{tid}")
                    if raw:
                        try:
                            trip = json.loads(raw)
                            if str(trip.get("location_id")) == str(location_id):
                                valid.add(tid)
                        except Exception:
                            pass
                    else:
                        async with AsyncSession(engine) as session:
                            try:
                                result = await session.exec(
                                    Select(Trip).Where((Trip.id == tid) & (Trip.location_id == location_id))
                                ).first()

                                print("RESULTS: ", result)

                                trip = result.model_dump(mode="json")
                                if trip:
                                    valid.add(tid)
                            except Exception as e:
                                print(e)

                await manager.subscribe_trips(ws, valid)

                # Opcional: responder con el estado actual cacheado de esos trips
                # para pintar inmediatamente (si existía)
                if valid:
                    keys = [f"trip:{tid}" for tid in valid]
                    vals = await redis.mget(keys)
                    now = []
                    for v in vals:
                        if v:
                            try: now.append(json.loads(v))
                            except: pass
                    await ws.send_json({"type": "subscribed", "trip_ids": list(valid), "trips": now})
                else:
                    await ws.send_json({"type": "subscribed", "trip_ids": []})

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
