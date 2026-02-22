from fastapi import WebSocket
from typing import Dict, Set, Optional, Any
import asyncio
import json

from shared.redis.redis_client import redis_client as redis


class OrgWSManager:
    """
    WebSocket manager for organization-level events.
    Listens to Redis channel org:{organization_id} for events like:
      - location_deleted
      - (future org-level events)
    """

    def __init__(self) -> None:
        self.rooms: Dict[str, Set[WebSocket]] = {}  # org_id -> set of websockets
        self.ws_meta: Dict[WebSocket, dict] = {}
        self.org_listener_tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, org_id: str, claims: dict) -> None:
        await ws.accept()
        async with self._lock:
            metadata = claims.get("metadata") or {}
            self.rooms.setdefault(org_id, set()).add(ws)
            self.ws_meta[ws] = {
                "org_id": org_id,
                "user_id": claims.get("sub"),
                "role": metadata.get("role"),
            }

    async def disconnect(self, ws: WebSocket) -> None:
        task_to_cancel: Optional[asyncio.Task] = None

        async with self._lock:
            meta = self.ws_meta.pop(ws, None)
            if not meta:
                return

            org_id = meta["org_id"]
            self.rooms.get(org_id, set()).discard(ws)

            if org_id in self.rooms and not self.rooms[org_id]:
                self.rooms.pop(org_id, None)
                task_to_cancel = self.org_listener_tasks.pop(org_id, None)

        if task_to_cancel:
            task_to_cancel.cancel()

    async def _safe_send(self, ws: WebSocket, payload: dict) -> bool:
        try:
            await ws.send_json(payload)
            return True
        except Exception:
            return False

    async def broadcast_to_org(self, org_id: str, payload: dict) -> None:
        org_id = str(org_id)

        async with self._lock:
            targets = set(self.rooms.get(org_id, set()))

        dead = []
        for ws in targets:
            if not await self._safe_send(ws, payload):
                dead.append(ws)

        for ws in dead:
            await self.disconnect(ws)

    async def broadcast_to_managers(self, org_id: str, payload: dict) -> None:
        """Send payload only to manager connections in the org room."""
        org_id = str(org_id)

        async with self._lock:
            all_ws = set(self.rooms.get(org_id, set()))
            targets = {
                ws for ws in all_ws
                if self.ws_meta.get(ws, {}).get("role") == "manager"
            }

        dead = []
        for ws in targets:
            if not await self._safe_send(ws, payload):
                dead.append(ws)

        for ws in dead:
            await self.disconnect(ws)

    async def ensure_org_listener(self, org_id: str) -> None:
        async with self._lock:
            if org_id in self.org_listener_tasks:
                return
            self.org_listener_tasks[org_id] = asyncio.create_task(
                self._org_listener(org_id)
            )

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

    async def _org_listener(self, org_id: str) -> None:
        """
        Listen to Redis channel org:{org_id} for organization-level events.
        Expected message format:
          {
            "type": "location_deleted",
            "location_id": "uuid",
            "location_name": "...",
            "message": "...",
            "hotels": [...],
            "hotels_count": N
          }
        """
        channel = f"org:{org_id}"
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)

        try:
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue

                ev = self._decode_pubsub_data(msg.get("data"))
                if not ev:
                    continue

                # Billing events go only to managers
                if ev.get("type") == "billing_event":
                    await self.broadcast_to_managers(org_id, ev)
                else:
                    await self.broadcast_to_org(org_id, ev)

        except asyncio.CancelledError:
            pass
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
            except Exception:
                pass


org_manager = OrgWSManager()
