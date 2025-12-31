from fastapi import APIRouter, Request, Header
from shared.settings import settings
from features.auth.utils import verify_webhook_signature
from shared.redis.redis_client import redis_client as redis
import json
from collections import defaultdict

WEBHOOK_SECRET = settings.WEBHOOK_SECRET
TRIP_TTL_SECONDS = 300

webhook = APIRouter()

def _safe_str(x) -> str:
    return str(x or "").strip()

def _process_event_into_pipe(event: dict, pipe):
    """
    Mete comandos Redis al pipeline según el event_type.
    Retorna (location_id, pub_event) o None si inválido.
    """
    location_id = _safe_str(event.get("location_id"))
    trip_id = _safe_str(event.get("trip_id"))
    event_type = _safe_str(event.get("event_type") or event.get("event") or "db_update")

    # El trip puede venir como dict (update/insert) o (delete) también dict con estado anterior
    trip = event.get("trip")

    if not location_id or not trip_id:
        return None

    trip_key = f"trip:{trip_id}"
    idx_key = f"loc:{location_id}:trips"

    # Si delete: borra cache + srem del índice (en vez de set)
    if event_type == "delete":
        pipe.delete(trip_key)
        pipe.srem(idx_key, trip_id)
        # mantenemos TTL del índice para que se limpie solo si queda vacío/abandonado
        pipe.expire(idx_key, TRIP_TTL_SECONDS)

        pub_event = {
            "location_id": location_id,
            "trip_id": trip_id,
            "event_type": "delete",
        }
        return location_id, pub_event

    # insert/update: requiere trip dict (mínimo)
    if not isinstance(trip, dict):
        return None

    pipe.set(trip_key, json.dumps(trip), ex=TRIP_TTL_SECONDS)
    pipe.sadd(idx_key, trip_id)
    pipe.expire(idx_key, TRIP_TTL_SECONDS)

    pub_event = {
        "location_id": location_id,
        "trip_id": trip_id,
        "event_type": event_type or "db_update",
        "trip": trip,  # si esto pesa mucho, puedes quitarlo del pubsub
    }
    return location_id, pub_event


@webhook.post("/v1/webhooks/trips/batch")
async def trips_webhook_batch(
    request: Request,
    x_signature: str = Header(default="", alias="x-webhook-secret"),
):
    raw = await request.body()

    # Seguridad: firma HMAC sobre TODO el body del batch
    if not x_signature or not verify_webhook_signature(raw, x_signature, WEBHOOK_SECRET):
        return {"ok": False, "error": "invalid signature"}

    payload = await request.json()

    events = payload.get("events")
    if not isinstance(events, list) or not events:
        return {"ok": False, "error": "missing events list"}

    # 1) Redis pipeline: 1 ejecución para todo el batch
    pipe = redis.pipeline()

    # 2) Agrupar pubsub por location para publicar menos mensajes
    by_location = defaultdict(list)

    accepted = 0
    skipped = 0

    for ev in events:
        if not isinstance(ev, dict):
            skipped += 1
            continue

        out = _process_event_into_pipe(ev, pipe)
        if not out:
            skipped += 1
            continue

        location_id, pub_event = out
        by_location[location_id].append(pub_event)
        accepted += 1

    # Ejecuta pipeline (rápido)
    if accepted:
        await pipe.execute()

    # 3) Pub/Sub: 1 publish por location (no 1 por evento)
    #    Si aún quieres menos, puedes publicar 1 solo canal global.
    for location_id, items in by_location.items():
        msg = {"type": "trips_batch", "location_id": location_id, "events": items}
        await redis.publish(f"loc:{location_id}", json.dumps(msg))

    return {"ok": True, "received": len(events), "accepted": accepted, "skipped": skipped}
