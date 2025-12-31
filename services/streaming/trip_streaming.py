'''from shared.db.schemas import Trip
from psqlmodel import create_async_engine, Subscribe
from shared.settings import settings

import httpx, asyncio, uuid, json, time, hmac, hashlib, random

SECRET = settings.WEBHOOK_SECRET
WEBHOOK_BATCH_URL = f"{settings.BACKEND_URL}/v1/webhooks/trips/batch"

def sign_body(secret: str, body: bytes, ts: int) -> str:
    msg = f"{ts}.".encode("utf-8") + body
    sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"

def build_event(payload: dict) -> dict | None:
    event_type = payload.get("event")
    old = payload.get("old") or {}
    new = payload.get("new") or {}

    trip_id = str((new.get("id") or old.get("id") or "")).strip()
    location_id = str((new.get("location_id") or old.get("location_id") or "")).strip()
    if not trip_id or not location_id:
        return None

    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "trip_id": trip_id,
        "location_id": location_id,
        "trip": old if event_type == "delete" else new,
    }

async def post_batch_with_retry(client: httpx.AsyncClient, batch: dict, max_retries: int = 8):
    body = json.dumps(batch, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    for attempt in range(max_retries + 1):
        ts = int(time.time())
        signature = sign_body(SECRET, body, ts)
        headers = {"Content-Type": "application/json", "x-webhook-secret": signature}

        try:
            resp = await client.post(WEBHOOK_BATCH_URL, content=body, headers=headers)
            print("[HTTP]", resp.status_code, "events=", len(batch["events"]))

            if 200 <= resp.status_code < 300:
                return True

            if resp.status_code in (408, 425, 429, 500, 502, 503, 504):
                ra = resp.headers.get("retry-after")
                if ra:
                    try:
                        await asyncio.sleep(float(ra))
                        continue
                    except Exception:
                        pass
                raise httpx.HTTPStatusError(f"{resp.status_code}: {resp.text}", request=resp.request, response=resp)

            print("Batch non-retryable:", resp.status_code, resp.text)
            return False

        except Exception as e:
            print(f"[HTTP] attempt={attempt} error={repr(e)}")
            if attempt >= max_retries:
                print("Batch failed permanently:", "batch_id=", batch.get("batch_id"))
                return False
            backoff = min(2 ** attempt, 20) + random.random()
            await asyncio.sleep(backoff)

async def composer(event_q: asyncio.Queue, batch_q: asyncio.Queue):
    """
    Lee eventos individuales y arma batches de 100.
    FLUSH_INTERVAL asegura que si llegan pocos eventos, igual se manden.
    """
    MAX_BATCH = 100
    FLUSH_INTERVAL = 0.2

    buffer: list[dict] = []
    last_flush = time.monotonic()

    while True:
        timeout = max(0.0, FLUSH_INTERVAL - (time.monotonic() - last_flush))

        ev = None
        try:
            ev = await asyncio.wait_for(event_q.get(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

        if ev is not None:
            buffer.append(ev)
            event_q.task_done()

        if buffer and (len(buffer) >= MAX_BATCH or (time.monotonic() - last_flush) >= FLUSH_INTERVAL):
            batch = {
                "batch_id": str(uuid.uuid4()),
                "sent_at": int(time.time()),
                "source": "trips-subscriber",
                "events": buffer,
            }
            buffer = []
            last_flush = time.monotonic()

            # backpressure: si batch_q se llena, composer se pausa aquí
            await batch_q.put(batch)
            print("[BATCH] queued batch events=", len(batch["events"]))

async def sender(batch_q: asyncio.Queue, client: httpx.AsyncClient):
    """
    Envía batches uno por uno. Solo toma el siguiente cuando termina el anterior.
    """
    while True:
        batch = await batch_q.get()
        try:
            ok = await post_batch_with_retry(client, batch)
            if not ok:
                # si quieres, re-enqueue o log; yo lo dejo logeado
                pass
        finally:
            batch_q.task_done()

async def main():
    if not SECRET:
        raise RuntimeError("Invalid WEBHOOK_SECRET.")

    # Cola de eventos individuales (rápida)
    event_q: asyncio.Queue = asyncio.Queue(maxsize=200_000)

    # Cola de batches ya listos (controla memoria y ritmo de envío)
    batch_q: asyncio.Queue = asyncio.Queue(maxsize=2_000)  # 2000 * 100 = 200k eventos en el peor caso

    limits = httpx.Limits(max_connections=10, max_keepalive_connections=10)
    timeout = httpx.Timeout(30.0, connect=5.0)

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        composer_task = asyncio.create_task(composer(event_q, batch_q))
        sender_task = asyncio.create_task(sender(batch_q, client))

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
            ev = build_event(payload)
            if ev:
                # rápido. si se llena, aplica backpressure natural
                await event_q.put(ev)

        sub = Subscribe.engine(async_engine, use_engine_pool=False)

        try:
            await sub(Trip).OnEvent("change").Exec(on_trip_change).StartAsync()
        finally:
            try:
                await sub.StopAsync()
            except Exception:
                pass

            # drenar colas antes de salir
            await event_q.join()
            await batch_q.join()

            composer_task.cancel()
            sender_task.cancel()
            await asyncio.gather(composer_task, sender_task, return_exceptions=True)

if __name__ == "__main__":
    asyncio.run(main())
'''

from shared.db.schemas import Trip
from psqlmodel import create_async_engine, Subscribe
from shared.settings import settings

import httpx
import asyncio
import uuid
import json
import time
import hmac
import hashlib
import random
from asyncio import QueueEmpty

SECRET = settings.WEBHOOK_SECRET
WEBHOOK_BATCH_URL = f"{settings.BACKEND_URL}/v1/webhooks/trips/batch"

# ----------------- SIGNING -----------------

def sign_body(secret: str, body: bytes, ts: int) -> str:
    msg = f"{ts}.".encode("utf-8") + body
    sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"

# ----------------- EVENT BUILD -----------------

def build_event(payload: dict) -> dict | None:
    # payload esperado: {"event": "...", "old": {...}, "new": {...}}
    event_type = payload.get("event")
    old = payload.get("old") or {}
    new = payload.get("new") or {}

    trip_id = str((new.get("id") or old.get("id") or "")).strip()
    location_id = str((new.get("location_id") or old.get("location_id") or "")).strip()
    if not trip_id or not location_id:
        return None

    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,  # "insert" | "update" | "delete"
        "trip_id": trip_id,
        "location_id": location_id,
        "trip": old if event_type == "delete" else new,
    }

# ----------------- HTTP POST (RETRY) -----------------

async def post_batch_with_retry(client: httpx.AsyncClient, batch: dict, max_retries: int = 8) -> bool:
    body = json.dumps(batch, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    for attempt in range(max_retries + 1):
        ts = int(time.time())
        signature = sign_body(SECRET, body, ts)
        headers = {"Content-Type": "application/json", "x-webhook-secret": signature}

        try:
            resp = await client.post(WEBHOOK_BATCH_URL, content=body, headers=headers)
            print("[HTTP]", resp.status_code, "events=", len(batch["events"]), flush=True)

            if 200 <= resp.status_code < 300:
                return True

            if resp.status_code in (408, 425, 429, 500, 502, 503, 504):
                ra = resp.headers.get("retry-after")
                if ra:
                    try:
                        await asyncio.sleep(float(ra))
                        continue
                    except Exception:
                        pass
                raise httpx.HTTPStatusError(
                    f"{resp.status_code}: {resp.text}",
                    request=resp.request,
                    response=resp,
                )

            # No reintentar 4xx duros
            print("Batch non-retryable:", resp.status_code, resp.text[:300], flush=True)
            return False

        except Exception as e:
            print(f"[HTTP] attempt={attempt} error={repr(e)}", flush=True)
            if attempt >= max_retries:
                print("Batch failed permanently:", "batch_id=", batch.get("batch_id"), flush=True)
                return False
            backoff = min(2 ** attempt, 20) + random.random()
            await asyncio.sleep(backoff)

# ----------------- COMPOSER (EVENT_Q -> BATCH_Q) -----------------

async def composer(event_q: asyncio.Queue, batch_q: asyncio.Queue):
    """
    - Drena rápido event_q (get_nowait) hasta MAX_BATCH.
    - Flush por tamaño o por tiempo.
    - NUNCA hace busy-loop (si no hay trabajo, hace await).
    """
    MAX_BATCH = 100
    FLUSH_INTERVAL = 0.2

    buffer: list[dict] = []
    last_flush = time.monotonic()

    print("[COMPOSER] started", flush=True)

    while True:
        # 1) Drena lo que haya sin bloquear
        while len(buffer) < MAX_BATCH:
            try:
                ev = event_q.get_nowait()
            except QueueEmpty:
                break
            buffer.append(ev)
            event_q.task_done()

        # 2) Flush inmediato por tamaño
        if len(buffer) >= MAX_BATCH:
            batch = {
                "batch_id": str(uuid.uuid4()),
                "sent_at": int(time.time()),
                "source": "trips-subscriber",
                "events": buffer,
            }
            buffer = []
            last_flush = time.monotonic()
            await batch_q.put(batch)
            print("[BATCH] queued size=100 batch_q=", batch_q.qsize(), flush=True)
            continue

        # 3) Flush por tiempo
        if buffer and (time.monotonic() - last_flush) >= FLUSH_INTERVAL:
            batch = {
                "batch_id": str(uuid.uuid4()),
                "sent_at": int(time.time()),
                "source": "trips-subscriber",
                "events": buffer,
            }
            size = len(buffer)
            buffer = []
            last_flush = time.monotonic()
            await batch_q.put(batch)
            print("[BATCH] queued size=", size, "batch_q=", batch_q.qsize(), flush=True)
            continue

        # 4) Si no hay nada, espera un evento (cede el event loop)
        if not buffer:
            ev = await event_q.get()
            buffer.append(ev)
            event_q.task_done()
            continue

        # 5) Si hay buffer, espera o próximo evento o el timeout para flush
        remaining = max(0.0, FLUSH_INTERVAL - (time.monotonic() - last_flush))
        try:
            ev = await asyncio.wait_for(event_q.get(), timeout=remaining)
            buffer.append(ev)
            event_q.task_done()
        except asyncio.TimeoutError:
            # próximo loop flushea
            pass

# ----------------- SENDER (BATCH_Q -> HTTP) -----------------

async def sender(batch_q: asyncio.Queue, client: httpx.AsyncClient):
    print("[SENDER] started", flush=True)
    while True:
        batch = await batch_q.get()
        try:
            await post_batch_with_retry(client, batch)
        finally:
            batch_q.task_done()

# ----------------- HEARTBEAT (OPTIONAL) -----------------

async def heartbeat(event_q: asyncio.Queue, batch_q: asyncio.Queue):
    while True:
        print(f"[HB] event_q={event_q.qsize()} batch_q={batch_q.qsize()}", flush=True)
        await asyncio.sleep(1)

# ----------------- MAIN -----------------

async def main():
    print("[BOOT] WEBHOOK_BATCH_URL =", WEBHOOK_BATCH_URL, flush=True)
    print("[BOOT] SECRET length =", (len(SECRET) if SECRET else 0), flush=True)

    if not SECRET:
        raise RuntimeError("Invalid WEBHOOK_SECRET.")

    # Cola de eventos individuales (rápida)
    event_q: asyncio.Queue = asyncio.Queue(maxsize=200_000)

    # Cola de batches listos (control de memoria / ritmo)
    batch_q: asyncio.Queue = asyncio.Queue(maxsize=2_000)

    limits = httpx.Limits(max_connections=10, max_keepalive_connections=10)
    timeout = httpx.Timeout(30.0, connect=5.0)

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        composer_task = asyncio.create_task(composer(event_q, batch_q))
        sender_task = [asyncio.create_task(sender(batch_q, client)) for _ in range(3)]
        hb_task = asyncio.create_task(heartbeat(event_q, batch_q))  # quítalo si no lo quieres

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
            ev = build_event(payload)
            if ev:
                await event_q.put(ev)

        sub = Subscribe.engine(async_engine, use_engine_pool=False)

        try:
            await sub(Trip).OnEvent("change").Exec(on_trip_change).StartAsync()
        finally:
            try:
                await sub.StopAsync()
            except Exception:
                pass

            # drenar colas antes de salir
            await event_q.join()
            await batch_q.join()

            for t in (composer_task, sender_task, hb_task):
                t.cancel()
            await asyncio.gather(composer_task, sender_task, hb_task, return_exceptions=True)

if __name__ == "__main__":
    # Recomendado: ejecuta con `python -u script.py` para prints inmediatos
    asyncio.run(main())
