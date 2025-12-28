from fastapi import WebSocket
from typing import Dict, Set, Optional
import asyncio
import json

from shared.redis.redis_client import redis_client as redis

class WSManager:
    def __init__(self) -> None:
        self.rooms: Dict[str, Set[WebSocket]] = {}
        self.trip_subscribers: Dict[str, Set[WebSocket]] = {}
        self.ws_meta: Dict[WebSocket, dict] = {}

        # Para no abrir 100 listeners por location:
        self.location_listener_tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, location_id: str, claims: dict) -> None:
        await ws.accept()
        async with self._lock:
            metadata = claims.get("metadata")
            org_id = metadata.get("organization_id")
            role = metadata.get("role")
            self.rooms.setdefault(location_id, set()).add(ws)
            self.ws_meta[ws] = {
                "location_id": location_id,
                "user_id": claims.get("sub"),
                "role": role,
                "org_id": org_id,
                "trip_ids": set(),  # suscripciones por trip de este cliente
            }

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            meta = self.ws_meta.pop(ws, None)
            if not meta:
                return

            loc = meta["location_id"]
            self.rooms.get(loc, set()).discard(ws)
            if loc in self.rooms and not self.rooms[loc]:
                self.rooms.pop(loc, None)

            for tid in list(meta["trip_ids"]):
                subs = self.trip_subscribers.get(tid)
                if subs:
                    subs.discard(ws)
                    if not subs:
                        self.trip_subscribers.pop(tid, None)

    async def subscribe_trips(self, ws: WebSocket, trip_ids: Set[str]) -> None:
        async with self._lock:
            meta = self.ws_meta.get(ws)
            if not meta:
                return
            for tid in trip_ids:
                self.trip_subscribers.setdefault(tid, set()).add(ws)
                meta["trip_ids"].add(tid)

    async def unsubscribe_trips(self, ws: WebSocket, trip_ids: Set[str]) -> None:
        async with self._lock:
            meta = self.ws_meta.get(ws)
            if not meta:
                return
            for tid in trip_ids:
                subs = self.trip_subscribers.get(tid)
                if subs:
                    subs.discard(ws)
                    if not subs:
                        self.trip_subscribers.pop(tid, None)
                meta["trip_ids"].discard(tid)

    async def _safe_send(self, ws: WebSocket, payload: dict) -> bool:
        try:
            await ws.send_json(payload)
            return True
        except Exception:
            return False

    async def route_location_event(self, location_id: str, trip_id: Optional[str], payload: dict) -> None:
        """
        Recibe evento (desde Redis Pub/Sub) y lo distribuye:
        - Siempre a los conectados en la location (si quieres refrescar listas)
        - Y/o solo a los suscritos al trip_id (si quieres granularidad)
        """
        async with self._lock:
            loc_targets = set(self.rooms.get(location_id, set()))
            trip_targets = set(self.trip_subscribers.get(trip_id, set())) if trip_id else set()

            # Dedupe: si un WS está en ambos, se envía una sola vez
            targets = list(loc_targets.union(trip_targets))

        dead = []
        for ws in targets:
            ok = await self._safe_send(ws, payload)
            if not ok:
                dead.append(ws)

        for ws in dead:
            await self.disconnect(ws)

    async def ensure_location_listener(self, location_id: str) -> None:
        """
        Un listener Redis por location por proceso.
        Arranca al primer cliente que entra a esa location.
        """
        async with self._lock:
            if location_id in self.location_listener_tasks:
                return

            task = asyncio.create_task(self._location_listener(location_id))
            self.location_listener_tasks[location_id] = task

    async def _location_listener(self, location_id: str) -> None:
        """
        Escucha Redis Pub/Sub channel loc:{location_id} y routea eventos a sockets.
        """
        channel = f"loc:{location_id}"
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)

        try:
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue

                data = msg.get("data")
                try:
                    event = json.loads(data) if isinstance(data, str) else data
                except Exception:
                    continue

                trip_id = event.get("trip_id")
                payload = {
                    "type": "trip_event",
                    "event_type": event.get("event_type"),  # o "update"/"insert"/"delete"
                    "location_id": location_id,
                    "trip": event.get("trip"),
                }
                await self.route_location_event(location_id, trip_id, payload)
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
            except Exception:
                pass


manager = WSManager()
