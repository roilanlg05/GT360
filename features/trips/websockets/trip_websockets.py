from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from shared.redis.redis_client import redis_client as redis
from features.trips.utils.ws_manager import manager
from shared.db.db_config import engine, AsyncSession
from shared.db.schemas import Trip as TripDB, Location
from features.auth.utils import user_can_access_location, decode_token
from psqlmodel import Select
from uuid import UUID
import json

router = APIRouter()

# Consistent with trip_webhooks.py
TRIP_TTL_SECONDS = 300


async def _get_location_info(location_id: str) -> dict | None:
    """
    Get location metadata for Timeline ordering.

    Returns:
        dict with: id, name (airport code), timezone
        Used by frontend to:
        - Determine inbound/outbound (compare with pick_up_location/drop_off_location)
        - Group trips by day using the correct timezone
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        return None

    async with AsyncSession(engine) as session:
        location = await session.exec(
            Select(Location).Where(Location.id == location_uuid)
        ).first()

        if not location:
            return None

        return {
            "id": str(location.id),
            "name": location.name,  # Airport code (e.g., "SDF")
            "timezone": location.timezone,  # e.g., "America/New_York"
        }

async def _get_trips_from_redis(trip_ids: set) -> list:
    """Get trips from Redis cache."""
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
    return trips


async def _get_trips_from_db(location_id: str) -> list:
    """Fallback: get trips from PostgreSQL when Redis cache is empty."""
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        return []

    async with AsyncSession(engine) as session:
        stmt = (
            Select(TripDB)
            .Where(TripDB.location_id == location_uuid)
            .OrderBy(TripDB.pick_up_date.Asc(), TripDB.pick_up_time.Asc())
        )
        trips = await session.exec(stmt).all()
        return [t.model_dump(mode="json") for t in trips]


async def _populate_redis_cache(location_id: str, trips: list) -> None:
    """Repopulate Redis cache with trips from DB (self-healing cache)."""
    if not trips:
        return

    idx_key = f"loc:{location_id}:trips"
    pipe = redis.pipeline()

    for trip in trips:
        trip_id = trip.get("id")
        if trip_id:
            trip_key = f"trip:{trip_id}"
            pipe.set(trip_key, json.dumps(trip), ex=TRIP_TTL_SECONDS)
            pipe.sadd(idx_key, trip_id)

    pipe.expire(idx_key, TRIP_TTL_SECONDS)
    try:
        await pipe.execute()
    except Exception:
        # Cache population is best-effort; if Redis is unavailable or read-only,
        # the app continues working with DB fallback
        pass


async def send_snapshot(ws: WebSocket, location_id: str) -> None:
    """
    Send snapshot of all trips for a location.

    Strategy:
    1. Get location info (timezone, name) for Timeline support
    2. Try Redis cache first (fast path)
    3. If empty, fallback to PostgreSQL (reliable path)
    4. Repopulate cache if DB has data (self-healing)
    """
    # 0. Get location metadata for Timeline (timezone, airport code)
    location_info = await _get_location_info(location_id)

    idx_key = f"loc:{location_id}:trips"
    trip_ids = await redis.smembers(idx_key)

    # 1. If Redis has data, use it (fast path)
    if trip_ids:
        trips = await _get_trips_from_redis(trip_ids)
        if trips:
            await ws.send_json({
                "type": "snapshot",
                "location_id": location_id,
                "location_info": location_info,
                "trips": trips
            })
            return

    # 2. Fallback to PostgreSQL if Redis is empty
    trips = await _get_trips_from_db(location_id)

    # 3. Repopulate cache if DB has data (self-healing)
    if trips:
        await _populate_redis_cache(location_id, trips)

    # 4. Send snapshot (may be empty if no trips in DB - that's legitimate)
    await ws.send_json({
        "type": "snapshot",
        "location_id": location_id,
        "location_info": location_info,
        "trips": trips
    })


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
