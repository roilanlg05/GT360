"""
WebSocket Manager for Flight Tracking.

Manages WebSocket connections for:
1. Push notifications - status updates from AeroDataBox webhooks
2. Real-time tracking - position updates from ADSB.lol
"""

from __future__ import annotations

import asyncio
import json
from typing import Dict, List, Optional, Set, Any
from fastapi import WebSocket
import redis.asyncio as redis


class FlightWSManager:
    """
    Manages WebSocket connections for flight tracking.

    Room structure:
    - push:{trip_id} - clients subscribed to push notifications for a trip
    - track:{flight_number}:{trip_id} - clients subscribed to position updates
    """

    def __init__(self):
        # Room -> set of WebSockets
        self._rooms: Dict[str, Set[WebSocket]] = {}
        # WebSocket -> set of rooms it's in
        self._ws_rooms: Dict[WebSocket, Set[str]] = {}
        # Active Redis listeners
        self._listeners: Dict[str, asyncio.Task] = {}
        self._redis: Optional[redis.Redis] = None
        self._lock = asyncio.Lock()

    async def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            from shared.redis.redis_client import redis_client
            self._redis = redis_client
        return self._redis

    async def connect(self, ws: WebSocket, claims: dict) -> None:
        """Accept WebSocket connection."""
        await ws.accept()
        self._ws_rooms[ws] = set()

    async def disconnect(self, ws: WebSocket) -> None:
        """Disconnect WebSocket from all rooms."""
        rooms = self._ws_rooms.pop(ws, set())
        for room in rooms:
            if room in self._rooms:
                self._rooms[room].discard(ws)
                if not self._rooms[room]:
                    del self._rooms[room]

    async def join_room(self, ws: WebSocket, room: str) -> None:
        """Add WebSocket to a room."""
        if room not in self._rooms:
            self._rooms[room] = set()
        self._rooms[room].add(ws)

        if ws not in self._ws_rooms:
            self._ws_rooms[ws] = set()
        self._ws_rooms[ws].add(room)

    async def leave_room(self, ws: WebSocket, room: str) -> None:
        """Remove WebSocket from a room."""
        if room in self._rooms:
            self._rooms[room].discard(ws)
            if not self._rooms[room]:
                del self._rooms[room]

        if ws in self._ws_rooms:
            self._ws_rooms[ws].discard(room)

    async def broadcast_to_room(self, room: str, message: dict) -> None:
        """Broadcast message to all clients in a room."""
        if room not in self._rooms:
            return

        dead_sockets = []
        for ws in self._rooms[room]:
            try:
                await ws.send_json(message)
            except Exception:
                dead_sockets.append(ws)

        # Cleanup dead sockets
        for ws in dead_sockets:
            await self.disconnect(ws)

    # =========================================================================
    # Push Notifications Room (by trip_id)
    # =========================================================================

    def push_room(self, trip_id: str) -> str:
        return f"push:{trip_id}"

    async def subscribe_push(self, ws: WebSocket, trip_id: str) -> None:
        """Subscribe WebSocket to push notifications for a trip."""
        room = self.push_room(trip_id)
        await self.join_room(ws, room)
        await self.ensure_push_listener(trip_id)

    async def unsubscribe_push(self, ws: WebSocket, trip_id: str) -> None:
        """Unsubscribe WebSocket from push notifications."""
        room = self.push_room(trip_id)
        await self.leave_room(ws, room)

    async def ensure_push_listener(self, trip_id: str) -> None:
        """Ensure Redis listener is running for push notifications."""
        channel = f"flight:push:{trip_id}"

        async with self._lock:
            if channel in self._listeners:
                return

            task = asyncio.create_task(self._listen_push(trip_id, channel))
            self._listeners[channel] = task

    async def _listen_push(self, trip_id: str, channel: str) -> None:
        """Listen for push notifications from Redis pub/sub."""
        r = await self._get_redis()
        pubsub = r.pubsub()

        try:
            await pubsub.subscribe(channel)

            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue

                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")

                try:
                    notification = json.loads(data)
                    await self.broadcast_to_room(
                        self.push_room(trip_id),
                        {
                            "type": "push_notification",
                            "trip_id": trip_id,
                            "notification": notification,
                        }
                    )
                except Exception:
                    pass

        except asyncio.CancelledError:
            pass
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
            except Exception:
                pass

            async with self._lock:
                self._listeners.pop(channel, None)

    # =========================================================================
    # Real-Time Tracking Room (by flight_number + trip_id)
    # =========================================================================

    def track_room(self, flight_number: str, trip_id: str) -> str:
        return f"track:{flight_number.upper()}:{trip_id}"

    async def subscribe_tracking(
        self,
        ws: WebSocket,
        flight_number: str,
        trip_id: str
    ) -> None:
        """Subscribe WebSocket to position updates for a flight."""
        room = self.track_room(flight_number, trip_id)
        await self.join_room(ws, room)
        await self.ensure_tracking_listener(flight_number, trip_id)

    async def unsubscribe_tracking(
        self,
        ws: WebSocket,
        flight_number: str,
        trip_id: str
    ) -> None:
        """Unsubscribe WebSocket from position updates."""
        room = self.track_room(flight_number, trip_id)
        await self.leave_room(ws, room)

    async def ensure_tracking_listener(
        self,
        flight_number: str,
        trip_id: str
    ) -> None:
        """Ensure Redis listener is running for position updates."""
        channel = f"flight:track:{trip_id}"

        async with self._lock:
            if channel in self._listeners:
                return

            task = asyncio.create_task(
                self._listen_tracking(flight_number, trip_id, channel)
            )
            self._listeners[channel] = task

    async def _listen_tracking(
        self,
        flight_number: str,
        trip_id: str,
        channel: str
    ) -> None:
        """Listen for position updates from Redis pub/sub."""
        r = await self._get_redis()
        pubsub = r.pubsub()

        try:
            await pubsub.subscribe(channel)

            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue

                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")

                try:
                    position = json.loads(data)
                    # Broadcast to room for this specific flight
                    flight_num = position.get("flight_number", "").upper()
                    tid = position.get("trip_id", "")

                    await self.broadcast_to_room(
                        self.track_room(flight_num, tid),
                        {
                            "type": "position_update",
                            "position": position,
                        }
                    )
                except Exception:
                    pass

        except asyncio.CancelledError:
            pass
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
            except Exception:
                pass

            async with self._lock:
                self._listeners.pop(channel, None)


# Singleton manager
manager = FlightWSManager()
