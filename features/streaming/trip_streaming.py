from features.trips.schemas import Trip
from psqlmodel import create_async_engine, Subscribe
import httpx
import asyncio
from shared.settings import settings
import uuid
import json
import time
import hmac
import hashlib

client = httpx.AsyncClient(timeout=5)
SECRET = settings.WEBHOOK_SECRET

WEBHOOK_URL = "http://192.168.0.133:8080/v1/webhooks/trips"

def sign_body(secret: str, body: bytes, ts: int) -> str:
    msg = f"{ts}.".encode("utf-8") + body
    sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"

async def main():
    async_engine = create_async_engine(
        username=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        port=settings.POSTGRES_PORT,
        host=settings.POSTGRES_SERVER,
        database=settings.POSTGRES_DB,
        debug=True,
        models_path="__main__",
    )

    async def on_trip_change(payload):
        # payload esperado: {"event": "...", "old": {...}, "new": {...}}
        event_type = payload.get("event")
        old = payload.get("old") or {}
        new = payload.get("new") or {}

        # Asegurar ids
        trip_id = str((new.get("id") or old.get("id") or "")).strip()
        location_id = str((new.get("location_id") or old.get("location_id") or "")).strip()

        if not trip_id or not location_id:
            print("Skipping: missing trip_id/location_id", {"event": event_type, "trip_id": trip_id, "location_id": location_id})
            return

        data = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,              # "insert" | "update" | "delete"
            "trip_id": trip_id,
            "location_id": location_id,
            "trip": old if event_type == "delete" else new,
        }

        print("Trip changed:", data)

        if not SECRET:
            print("Invalid WEBHOOK_SECRET.")
            return

        # Body estable y firmado (importante)
        body = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ts = int(time.time())
        signature = sign_body(SECRET, body, ts)

        headers = {
            "Content-Type": "application/json",
            "x-webhook-secret": signature,
        }

        try:
            resp = await client.post(WEBHOOK_URL, content=body, headers=headers)
            print(resp.status_code, resp.text)
        except Exception as e:
            print("Webhook POST failed:", e)

    try:
        sub = Subscribe.engine(async_engine, use_engine_pool=False)
        await sub(Trip).OnEvent("change").Exec(on_trip_change).StartAsync()
    except Exception as e:
        print("Subscriber error:", e)
        try:
            await sub.StopAsync()
        except Exception:
            pass

if __name__ == "__main__":
    asyncio.run(main())
