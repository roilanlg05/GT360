from fastapi import APIRouter, Request, Header
from shared.settings import settings
from features.auth.utils import verify_webhook_signature
from shared.redis.redis_client import redis_client as redis
import json

WEBHOOK_SECRET=settings.WEBHOOK_SECRET
TRIP_TTL_SECONDS = 300

webhook = APIRouter()

@webhook.post("/v1/webhooks/trips")
async def trips_webhook(request: Request, x_signature: str = Header(alias="x-webhook-secret")):
    raw = await request.body()

    # 1) Seguridad webhook: firma HMAC (y opcional allowlist IP)
    if not x_signature or not verify_webhook_signature(raw, x_signature, WEBHOOK_SECRET):
        return {"ok": False, "error": "invalid signature"}

    event = await request.json()

    location_id = str(event.get("location_id") or "")
    trip_id = str(event.get("trip_id") or "")
    trip = event.get("trip")  # ideal: trip completo o estado mínimo

    if not location_id or not trip_id or not isinstance(trip, dict):
        return {"ok": False, "error": "missing location_id/trip_id/trip"}

    # 2) Cache TTL 5min + index por location (TTL 5min)
    trip_key = f"trip:{trip_id}"
    idx_key = f"loc:{location_id}:trips"

    # pipeline para hacerlo atómico y eficiente
    pipe = redis.pipeline()
    pipe.set(trip_key, json.dumps(trip), ex=TRIP_TTL_SECONDS)
    pipe.sadd(idx_key, trip_id)
    pipe.expire(idx_key, TRIP_TTL_SECONDS)
    await pipe.execute()

    # 3) Pub/Sub: publicar evento en canal de la location
    payload = {
        "location_id": location_id,
        "trip_id": trip_id,
        "event_type": event.get("event_type", "db_update"),
        "trip": trip,
    }
    await redis.publish(f"loc:{location_id}", json.dumps(payload))

    return {"ok": True}
