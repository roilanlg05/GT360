from fastapi import WebSocket
from typing import Dict, Set, Optional, Any
import asyncio
import json

from shared.redis.redis_client import redis_client as redis


class WSManager:
    """
    Batch-only pubsub consumer:
    Redis channel loc:{location_id} debe publicar:
      {"type":"trips_batch","location_id":"<loc>","events":[ ... ]}

    Por defecto reenvía a clientes como eventos individuales ("trip_event") por item.
    Si quieres reenviar como 1 solo mensaje batch al frontend, setea:
      self.SEND_WS_BATCH = True
    """
    SEND_WS_BATCH = False  # <- ponlo True si quieres mandar 1 msg WS por batch

    def __init__(self) -> None:
        self.rooms: Dict[str, Set[WebSocket]] = {}
        self.ws_meta: Dict[WebSocket, dict] = {}

        self.location_listener_tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, location_id: str, claims: dict) -> None:
        await ws.accept()
        async with self._lock:
            metadata = claims.get("metadata") or {}
            self.rooms.setdefault(location_id, set()).add(ws)
            self.ws_meta[ws] = {
                "location_id": location_id,
                "user_id": claims.get("sub"),
                "role": metadata.get("role"),
                "org_id": metadata.get("organization_id"),
            }

    async def disconnect(self, ws: WebSocket) -> None:
        task_to_cancel: Optional[asyncio.Task] = None

        async with self._lock:
            meta = self.ws_meta.pop(ws, None)
            if not meta:
                return

            loc = meta["location_id"]
            self.rooms.get(loc, set()).discard(ws)

            if loc in self.rooms and not self.rooms[loc]:
                self.rooms.pop(loc, None)
                task_to_cancel = self.location_listener_tasks.pop(loc, None)

        if task_to_cancel:
            task_to_cancel.cancel()

    async def _safe_send(self, ws: WebSocket, payload: dict) -> bool:
        try:
            await ws.send_json(payload)
            return True
        except Exception:
            return False

    async def route_location_event(self, location_id: str, payload: dict) -> None:
        location_id = str(location_id)

        async with self._lock:
            targets = set(self.rooms.get(location_id, set()))

        dead = []
        for ws in targets:
            if not await self._safe_send(ws, payload):
                dead.append(ws)

        for ws in dead:
            await self.disconnect(ws)

    async def ensure_location_listener(self, location_id: str) -> None:
        async with self._lock:
            if location_id in self.location_listener_tasks:
                return
            self.location_listener_tasks[location_id] = asyncio.create_task(
                self._location_listener(location_id)
            )

    # ----------------- Pub/Sub helpers -----------------

    def _decode_pubsub_data(self, data: Any) -> Optional[dict]:
        try:
            if isinstance(data, (bytes, bytearray)):
                data = data.decode("utf-8", errors="ignore")
            if isinstance(data, str):
                return json.loads(data)
            if isinstance(data, dict):
                return data
        except Exception:
            return None
        return None

    async def _dispatch_single(self, location_id: str, ev: dict) -> None:
        trip_id = ev.get("trip_id")
        event_type = ev.get("event_type") or ev.get("event") or "db_update"
        trip = ev.get("trip")

        payload = {
            "type": "trip_event",
            "event_type": event_type,
            "location_id": location_id,
            "trip_id": trip_id,
        }
        if isinstance(trip, dict):
            payload["trip"] = trip

        await self.route_location_event(location_id, payload)

    async def _location_listener(self, location_id: str) -> None:
        """
        Batch-only listener:
          {"type":"trips_batch","location_id":"<loc>","events":[...]}
        """
        channel = f"loc:{location_id}"
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)

        try:
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue

                ev = self._decode_pubsub_data(msg.get("data"))
                if not ev:
                    continue

                if ev.get("type") != "trips_batch":
                    continue

                msg_loc = ev.get("location_id")
                if msg_loc and str(msg_loc) != str(location_id):
                    continue

                events = ev.get("events") or []
                if not isinstance(events, list) or not events:
                    continue

                # Opción 1: reenviar 1 solo mensaje batch por websocket
                if self.SEND_WS_BATCH:
                    ws_payload = {
                        "type": "trips_batch",
                        "location_id": location_id,
                        "events": events,
                    }
                    await self.route_location_event(location_id, ws_payload)
                    continue

                # Opción 2: reenviar item por item (default)
                for item in events:
                    if isinstance(item, dict):
                        await self._dispatch_single(location_id, item)

        except asyncio.CancelledError:
            pass
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
            except Exception:
                pass


manager = WSManager()
