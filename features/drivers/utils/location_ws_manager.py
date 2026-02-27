from fastapi import WebSocket
from typing import Dict, Set, Optional, Any
import asyncio
import json
import logging
from datetime import datetime, timezone

from shared.redis.redis_client import redis_client as redis

logger = logging.getLogger(__name__)


class DriverLocationWSManager:
    """
    WebSocket manager for driver location sharing.

    - Manager connections are stored in rooms[org_id].
    - Each manager can optionally filter by location_id.
    - Driver connections are stored in driver_rooms["{org_id}:{location_id}"].
    - Driver locations are stored in Redis hash driver_locations:{org_id}
      and published to Redis channel driver_locations:{org_id}.
    - Control channel driver_visibility_control:{org_id} handles sharing toggle.
    """

    def __init__(self) -> None:
        # Manager rooms
        self.rooms: Dict[str, Set[WebSocket]] = {}  # org_id -> set of manager websockets
        self.ws_meta: Dict[WebSocket, dict] = {}

        # Driver rooms (for location sharing between drivers)
        self.driver_rooms: Dict[str, Set[WebSocket]] = {}  # "{org_id}:{location_id}" -> driver sockets
        self.driver_ws_meta: Dict[WebSocket, dict] = {}    # driver socket -> metadata

        # Shared
        self.org_listener_tasks: Dict[str, asyncio.Task] = {}
        self._sharing_enabled: Dict[str, bool] = {}  # org_id -> cached setting
        self._lock = asyncio.Lock()

    # ─── Manager connection management ──────────────────────────────────────

    async def connect(
        self,
        ws: WebSocket,
        org_id: str,
        claims: dict,
        location_id: Optional[str] = None,
    ) -> None:
        await ws.accept()
        async with self._lock:
            metadata = claims.get("metadata") or {}
            self.rooms.setdefault(org_id, set()).add(ws)
            self.ws_meta[ws] = {
                "org_id": org_id,
                "user_id": claims.get("sub"),
                "role": metadata.get("role"),
                "location_id": location_id,
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

                # Only cancel listener if NO drivers are connected either
                if not self._has_drivers_for_org(org_id):
                    task_to_cancel = self.org_listener_tasks.pop(org_id, None)

        if task_to_cancel:
            task_to_cancel.cancel()

    # ─── Driver connection management ───────────────────────────────────────

    async def connect_driver(
        self,
        ws: WebSocket,
        org_id: str,
        driver_id: str,
        location_id: str,
        driver_info: dict,
    ) -> None:
        """Register a driver WebSocket in the location-scoped room.

        If the same driver_id already has an active connection, the old
        one is evicted (session takeover) to prevent duplicate broadcasts
        and race conditions on disconnect cleanup.
        """
        room_key = f"{org_id}:{location_id}"
        old_ws: Optional[WebSocket] = None

        async with self._lock:
            # Evict previous connection for the same driver_id
            for existing_ws, meta in list(self.driver_ws_meta.items()):
                if meta.get("driver_id") == driver_id:
                    old_ws = existing_ws
                    old_room_key = f"{meta['org_id']}:{meta['location_id']}"
                    self.driver_rooms.get(old_room_key, set()).discard(existing_ws)
                    if old_room_key in self.driver_rooms and not self.driver_rooms[old_room_key]:
                        self.driver_rooms.pop(old_room_key, None)
                    self.driver_ws_meta.pop(existing_ws, None)
                    break

            # Register new connection
            self.driver_rooms.setdefault(room_key, set()).add(ws)
            self.driver_ws_meta[ws] = {
                "org_id": org_id,
                "driver_id": driver_id,
                "location_id": location_id,
                "driver_info": driver_info,
            }

        # Close old connection outside the lock to avoid deadlocks
        if old_ws:
            try:
                await old_ws.close(code=4001, reason="New connection established")
            except Exception:
                pass

    async def disconnect_driver(self, ws: WebSocket) -> None:
        """Remove a driver WebSocket from its room."""
        task_to_cancel: Optional[asyncio.Task] = None

        async with self._lock:
            meta = self.driver_ws_meta.pop(ws, None)
            if not meta:
                return

            room_key = f"{meta['org_id']}:{meta['location_id']}"
            self.driver_rooms.get(room_key, set()).discard(ws)
            if room_key in self.driver_rooms and not self.driver_rooms[room_key]:
                self.driver_rooms.pop(room_key, None)

            org_id = meta["org_id"]
            has_managers = bool(self.rooms.get(org_id))
            if not has_managers and not self._has_drivers_for_org(org_id):
                task_to_cancel = self.org_listener_tasks.pop(org_id, None)

        if task_to_cancel:
            task_to_cancel.cancel()

    def _has_drivers_for_org(self, org_id: str) -> bool:
        """Check if any driver rooms exist for this org (must be called under lock)."""
        prefix = f"{org_id}:"
        return any(key.startswith(prefix) for key in self.driver_rooms)

    # ─── Broadcasting ───────────────────────────────────────────────────────

    async def _safe_send(self, ws: WebSocket, payload: dict) -> bool:
        try:
            await ws.send_json(payload)
            return True
        except Exception:
            return False

    async def broadcast_to_org(self, org_id: str, payload: dict) -> None:
        """Send payload to all managers in org, applying location_id filter per connection."""
        org_id = str(org_id)

        async with self._lock:
            targets = list(self.rooms.get(org_id, set()))
            meta_snapshot = {ws: self.ws_meta.get(ws, {}) for ws in targets}

        dead = []
        for ws in targets:
            meta = meta_snapshot.get(ws, {})
            filter_loc = meta.get("location_id")
            # Apply location_id filter if set on the manager connection
            if filter_loc and payload.get("location_id") and str(filter_loc) != str(payload["location_id"]):
                continue
            if not await self._safe_send(ws, payload):
                dead.append(ws)

        for ws in dead:
            await self.disconnect(ws)

    async def broadcast_to_drivers_at_location(
        self,
        org_id: str,
        location_id: str,
        payload: dict,
        exclude_driver_id: Optional[str] = None,
    ) -> None:
        """Send payload to all drivers at a specific location, excluding sender."""
        room_key = f"{org_id}:{location_id}"

        async with self._lock:
            targets = list(self.driver_rooms.get(room_key, set()))
            meta_snapshot = {ws: self.driver_ws_meta.get(ws, {}) for ws in targets}

        dead = []
        for ws in targets:
            meta = meta_snapshot.get(ws, {})
            if exclude_driver_id and meta.get("driver_id") == exclude_driver_id:
                continue
            if not await self._safe_send(ws, payload):
                dead.append(ws)

        for ws in dead:
            await self.disconnect_driver(ws)

    async def broadcast_to_all_drivers_in_org(self, org_id: str, payload: dict) -> None:
        """Send payload to ALL drivers in an organization (all locations)."""
        prefix = f"{org_id}:"

        async with self._lock:
            target_sockets = []
            for key, sockets in self.driver_rooms.items():
                if key.startswith(prefix):
                    target_sockets.extend(list(sockets))

        dead = []
        for ws in target_sockets:
            if not await self._safe_send(ws, payload):
                dead.append(ws)

        for ws in dead:
            await self.disconnect_driver(ws)

    # ─── Driver location storage ────────────────────────────────────────────

    async def store_driver_location(
        self,
        org_id: str,
        driver_id: str,
        data: dict,
    ) -> None:
        """Write driver location to Redis hash and publish to channel."""
        hash_key = f"driver_locations:{org_id}"
        channel = f"driver_locations:{org_id}"

        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        serialized = json.dumps(data)

        await redis.hset(hash_key, driver_id, serialized)
        await redis.publish(channel, serialized)

    async def remove_driver_location(self, org_id: str, driver_id: str) -> None:
        """Remove a driver's location from the Redis hash and notify managers."""
        hash_key = f"driver_locations:{org_id}"
        removed = await redis.hdel(hash_key, driver_id)
        if removed:
            channel = f"driver_locations:{org_id}"
            offline_payload = json.dumps({
                "type": "driver_offline",
                "driver_id": driver_id,
            })
            await redis.publish(channel, offline_payload)

    async def get_all_driver_locations(
        self,
        org_id: str,
        location_id: Optional[str] = None,
    ) -> list[dict]:
        """Read all driver locations from Redis hash, filtering by location_id if given."""
        hash_key = f"driver_locations:{org_id}"
        raw = await redis.hgetall(hash_key)

        results = []
        for _driver_id, value in raw.items():
            try:
                if isinstance(value, (bytes, bytearray)):
                    value = value.decode("utf-8")
                entry = json.loads(value)
                if location_id and str(entry.get("location_id")) != str(location_id):
                    continue
                results.append(entry)
            except Exception:
                continue

        return results

    # ─── Sharing toggle ─────────────────────────────────────────────────────

    async def is_sharing_enabled(self, org_id: str) -> bool:
        """Check if driver location sharing is enabled for an org."""
        org_id = str(org_id)

        # 1. In-memory cache
        if org_id in self._sharing_enabled:
            return self._sharing_enabled[org_id]

        # 2. Redis cache
        cached = await redis.get(f"driver_sharing:{org_id}")
        if cached is not None:
            enabled = cached == "1"
            self._sharing_enabled[org_id] = enabled
            return enabled

        # 3. DB fallback
        enabled = await self._fetch_sharing_from_db(org_id)
        self._sharing_enabled[org_id] = enabled
        await redis.set(f"driver_sharing:{org_id}", "1" if enabled else "0")
        return enabled

    async def _fetch_sharing_from_db(self, org_id: str) -> bool:
        """Query the DB for the driver_location_sharing setting."""
        from shared.db.db_config import engine
        from shared.db.schemas import Organization
        from psqlmodel import Select, AsyncSession
        from uuid import UUID

        try:
            org_uuid = UUID(org_id)
        except ValueError:
            return False

        async with AsyncSession(engine) as session:
            org = await session.exec(
                Select(Organization.driver_location_sharing)
                .Where(Organization.id == org_uuid)
            ).first()

        if org is None:
            return False
        # psqlmodel may return a Row or the value directly
        if hasattr(org, "driver_location_sharing"):
            return bool(org.driver_location_sharing)
        return bool(org)

    async def publish_sharing_toggle(self, org_id: str, enabled: bool) -> None:
        """Publish a sharing toggle event to the Redis control channel."""
        org_id = str(org_id)
        # Update caches
        self._sharing_enabled[org_id] = enabled
        await redis.set(f"driver_sharing:{org_id}", "1" if enabled else "0")
        # Publish control event
        channel = f"driver_visibility_control:{org_id}"
        payload = json.dumps({"action": "toggle", "enabled": enabled})
        await redis.publish(channel, payload)

    async def _handle_sharing_toggle(self, org_id: str, ev: dict) -> None:
        """Handle a sharing toggle control message from Redis."""
        if ev.get("action") != "toggle":
            return

        enabled = ev.get("enabled", False)
        self._sharing_enabled[org_id] = enabled

        if enabled:
            # Send snapshot to each driver at their location
            prefix = f"{org_id}:"
            async with self._lock:
                rooms_snapshot = {
                    key: list(sockets)
                    for key, sockets in self.driver_rooms.items()
                    if key.startswith(prefix)
                }
                meta_snapshot = dict(self.driver_ws_meta)

            for room_key, sockets in rooms_snapshot.items():
                location_id = room_key.split(":", 1)[1]
                drivers_at_location = await self.get_all_driver_locations(org_id, location_id)

                for ws in sockets:
                    meta = meta_snapshot.get(ws, {})
                    # Exclude self from snapshot
                    filtered = [
                        d for d in drivers_at_location
                        if d.get("driver_id") != meta.get("driver_id")
                    ]
                    await self._safe_send(ws, {
                        "type": "sharing_enabled",
                        "drivers": filtered,
                    })
        else:
            # Notify all drivers in org that sharing is off
            await self.broadcast_to_all_drivers_in_org(org_id, {
                "type": "sharing_disabled",
            })

    # ─── Redis listener ─────────────────────────────────────────────────────

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
        """Listen to Redis channels and forward to managers AND drivers."""
        location_channel = f"driver_locations:{org_id}"
        control_channel = f"driver_visibility_control:{org_id}"
        pubsub = redis.pubsub()
        await pubsub.subscribe(location_channel, control_channel)

        try:
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue

                channel = msg.get("channel")
                if isinstance(channel, (bytes, bytearray)):
                    channel = channel.decode("utf-8")

                ev = self._decode_pubsub_data(msg.get("data"))
                if not ev:
                    continue

                # --- Control channel: sharing toggle ---
                if channel == control_channel:
                    await self._handle_sharing_toggle(org_id, ev)
                    continue

                # --- Location channel: driver location update ---
                payload = {"type": "location_update", **ev}

                # Always broadcast to managers (existing behavior)
                await self.broadcast_to_org(org_id, payload)

                # Broadcast to drivers at same location IF sharing is enabled
                if self._sharing_enabled.get(org_id, False):
                    location_id = ev.get("location_id")
                    driver_id = ev.get("driver_id")
                    if location_id:
                        await self.broadcast_to_drivers_at_location(
                            org_id, str(location_id), payload,
                            exclude_driver_id=driver_id,
                        )

        except asyncio.CancelledError:
            pass
        finally:
            try:
                await pubsub.unsubscribe(location_channel, control_channel)
                await pubsub.close()
            except Exception:
                pass

    # ─── Stale driver cleanup ────────────────────────────────────────────

    _STALE_THRESHOLD_SECONDS = 180  # 3 minutes

    def start_cleanup_task(self) -> None:
        """Start the periodic task that removes stale driver locations."""
        if hasattr(self, "_cleanup_task") and self._cleanup_task and not self._cleanup_task.done():
            return
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    def stop_cleanup_task(self) -> None:
        """Cancel the cleanup task."""
        task = getattr(self, "_cleanup_task", None)
        if task and not task.done():
            task.cancel()

    async def _cleanup_loop(self) -> None:
        """Run cleanup every 60 seconds."""
        try:
            while True:
                await asyncio.sleep(60)
                await self._remove_stale_locations()
        except asyncio.CancelledError:
            pass

    async def _remove_stale_locations(self) -> None:
        """Scan all driver_locations:* hashes, remove entries older than threshold."""
        now = datetime.now(timezone.utc)
        cursor = None
        while cursor != 0:
            cursor, keys = await redis.scan(
                cursor=cursor or 0,
                match="driver_locations:*",
                count=100,
            )
            for key in keys:
                if isinstance(key, (bytes, bytearray)):
                    key = key.decode("utf-8")

                # Extract org_id from key pattern "driver_locations:{org_id}"
                org_id = key.split(":", 1)[1] if ":" in key else None
                if not org_id:
                    continue

                raw = await redis.hgetall(key)
                for driver_id, value in raw.items():
                    if isinstance(driver_id, (bytes, bytearray)):
                        driver_id = driver_id.decode("utf-8")
                    if isinstance(value, (bytes, bytearray)):
                        value = value.decode("utf-8")

                    try:
                        entry = json.loads(value)
                    except Exception:
                        await redis.hdel(key, driver_id)
                        continue

                    updated_at_str = entry.get("updated_at")
                    if not updated_at_str:
                        await redis.hdel(key, driver_id)
                        continue

                    try:
                        updated_at = datetime.fromisoformat(updated_at_str)
                    except (ValueError, TypeError):
                        await redis.hdel(key, driver_id)
                        continue

                    age = (now - updated_at).total_seconds()
                    if age > self._STALE_THRESHOLD_SECONDS:
                        await redis.hdel(key, driver_id)
                        # Notify managers so the driver disappears from Mapbox
                        channel = f"driver_locations:{org_id}"
                        offline_payload = json.dumps({
                            "type": "driver_offline",
                            "driver_id": driver_id,
                        })
                        await redis.publish(channel, offline_payload)
                        logger.info(
                            "Removed stale location for driver %s in org %s (age: %.0fs)",
                            driver_id, org_id, age,
                        )


driver_location_manager = DriverLocationWSManager()
