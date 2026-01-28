"""
Tracking Cache Service - Redis caching for flight positions.

Implements 2-second TTL cache with singleflight pattern to prevent
duplicate API requests when multiple clients request the same flight.
"""

from __future__ import annotations

import asyncio
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

import redis.asyncio as redis

from features.flights.models.tracking_models import (
    FlightPosition,
    FlightTrackingState,
    FlightSubscription,
    PushNotification,
)
from features.flights.services.adsb_client import get_adsb_client
from shared.redis.redis_safe import safe_redis_call


# =============================================================================
# Config
# =============================================================================

POSITION_CACHE_TTL = 2  # seconds
LOCK_TTL_MS = 1500  # milliseconds
SUBSCRIPTION_TTL = 86400 * 2  # 2 days
NOTIFICATION_TTL = 86400  # 24 hours
MAX_NOTIFICATIONS_PER_FLIGHT = 50  # Max notifications to store per flight

# Redis key prefixes
PREFIX_POSITION = "flight:pos:"
PREFIX_TRACKING = "flight:track:"
PREFIX_SUBSCRIPTION = "flight:sub:"
PREFIX_ACTIVE_FLIGHTS = "flight:active"
PREFIX_NOTIFICATIONS = "flight:notifications:"

# Lua script for safe lock release
UNLOCK_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
else
  return 0
end
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def position_key(flight_number: str, trip_id: str) -> str:
    return f"{PREFIX_POSITION}{flight_number.upper()}:{trip_id}"


def tracking_key(flight_number: str, trip_id: str) -> str:
    return f"{PREFIX_TRACKING}{flight_number.upper()}:{trip_id}"


def subscription_key(flight_number: str, trip_id: str) -> str:
    return f"{PREFIX_SUBSCRIPTION}{flight_number.upper()}:{trip_id}"


def lock_key(key: str) -> str:
    return f"{key}:lock"


def notifications_key(arrival_iata: str, flight_number: str) -> str:
    """Key for notifications sorted set."""
    return f"{PREFIX_NOTIFICATIONS}{arrival_iata.upper()}:{flight_number.upper()}"


def generate_notification_id(notification: dict) -> str:
    """
    Generate unique ID for notification to prevent duplicates.

    Uses: flight_number + status + last_updated timestamp.
    If two notifications have the same ID, they're duplicates.
    """
    flight_number = notification.get("flight_number", "")
    status = notification.get("status", "")
    last_updated = notification.get("last_updated", "")
    return f"{flight_number}:{status}:{last_updated}"


class TrackingCache:
    """
    Flight tracking cache with Redis.

    Features:
    - 2-second position cache
    - Singleflight pattern (prevents duplicate API calls)
    - Active flight tracking state
    - Subscription management
    """

    def __init__(self, redis_client: redis.Redis):
        self.r = redis_client
        self._logger = logging.getLogger(__name__)

    async def _safe(
        self,
        op: Callable[..., Awaitable[Any]],
        *args,
        context: str = "",
        default: Any = None,
        **kwargs,
    ) -> Any:
        return await safe_redis_call(
            op,
            *args,
            context=context,
            default=default,
            logger_override=self._logger,
            **kwargs,
        )

    # =========================================================================
    # Position Cache (2s TTL)
    # =========================================================================

    async def get_position(
        self,
        flight_number: str,
        trip_id: str
    ) -> Optional[FlightPosition]:
        """Get cached position if exists and not expired."""
        key = position_key(flight_number, trip_id)
        raw = await self._safe(self.r.get, key, context=f"get {key}")

        if not raw:
            return None

        try:
            data = json.loads(raw)
            return FlightPosition(**data)
        except Exception:
            return None

    async def set_position(
        self,
        position: FlightPosition,
        ttl: int = POSITION_CACHE_TTL
    ) -> None:
        """Cache position with TTL."""
        key = position_key(position.flight_number, position.trip_id)
        await self._safe(
            self.r.set,
            key,
            position.model_dump_json(),
            ex=ttl,
            context=f"set {key}",
        )

    async def get_or_fetch_position(
        self,
        flight_number: str,
        trip_id: str,
        origin_icao: Optional[str] = None,
        destination_icao: Optional[str] = None,
    ) -> Optional[FlightPosition]:
        """
        Get position from cache or fetch from ADSB.lol.

        Uses singleflight pattern - if multiple requests come for the
        same flight, only one will hit the API.
        """
        # 1) Check cache
        cached = await self.get_position(flight_number, trip_id)
        if cached:
            return cached

        # 2) Try to acquire lock
        key = position_key(flight_number, trip_id)
        lk = lock_key(key)
        token = str(uuid.uuid4())

        got_lock = await self._safe(
            self.r.set,
            lk,
            token,
            nx=True,
            px=LOCK_TTL_MS,
            context=f"set lock {lk}",
            default=False,
        )

        if not got_lock:
            # Another request is fetching, wait and check cache
            await asyncio.sleep(0.15)
            cached = await self.get_position(flight_number, trip_id)
            if cached:
                return cached

            # Wait a bit more
            await asyncio.sleep(0.15)
            return await self.get_position(flight_number, trip_id)

        try:
            # Double-check cache after acquiring lock
            cached = await self.get_position(flight_number, trip_id)
            if cached:
                return cached

            # Fetch from ADSB.lol
            client = await get_adsb_client()
            position = await client.get_flight_position(
                flight_number=flight_number,
                trip_id=trip_id,
                origin_icao=origin_icao,
                destination_icao=destination_icao,
            )

            if position:
                await self.set_position(position)

            return position

        finally:
            # Release lock
            try:
                await self._safe(
                    self.r.eval,
                    UNLOCK_LUA,
                    1,
                    lk,
                    token,
                    context=f"unlock {lk}",
                )
            except Exception:
                pass

    # =========================================================================
    # Tracking State
    # =========================================================================

    async def get_tracking_state(
        self,
        flight_number: str,
        trip_id: str
    ) -> Optional[FlightTrackingState]:
        """Get tracking state for a flight."""
        key = tracking_key(flight_number, trip_id)
        raw = await self._safe(self.r.get, key, context=f"get {key}")

        if not raw:
            return None

        try:
            data = json.loads(raw)
            return FlightTrackingState(**data)
        except Exception:
            return None

    async def set_tracking_state(
        self,
        state: FlightTrackingState,
        ttl: int = SUBSCRIPTION_TTL
    ) -> None:
        """Save tracking state."""
        key = tracking_key(state.flight_number, state.trip_id)
        await self._safe(
            self.r.set,
            key,
            state.model_dump_json(),
            ex=ttl,
            context=f"set {key}",
        )

    async def update_tracking_active(
        self,
        flight_number: str,
        trip_id: str,
        is_active: bool
    ) -> None:
        """Update whether tracking is active for a flight."""
        state = await self.get_tracking_state(flight_number, trip_id)
        if state:
            state.is_tracking_active = is_active
            await self.set_tracking_state(state)

        # Update active flights set
        member = f"{flight_number.upper()}:{trip_id}"
        if is_active:
            await self._safe(
                self.r.sadd,
                PREFIX_ACTIVE_FLIGHTS,
                member,
                context=f"sadd {PREFIX_ACTIVE_FLIGHTS}",
            )
        else:
            await self._safe(
                self.r.srem,
                PREFIX_ACTIVE_FLIGHTS,
                member,
                context=f"srem {PREFIX_ACTIVE_FLIGHTS}",
            )

    async def get_active_flights(self) -> List[str]:
        """Get all active flight tracking sessions."""
        members = await self._safe(
            self.r.smembers,
            PREFIX_ACTIVE_FLIGHTS,
            context=f"smembers {PREFIX_ACTIVE_FLIGHTS}",
            default=set(),
        )
        return [m.decode() if isinstance(m, bytes) else m for m in members]

    # =========================================================================
    # Subscriptions
    # =========================================================================

    async def save_subscription(self, subscription: FlightSubscription) -> None:
        """Save subscription to Redis."""
        key = subscription_key(subscription.flight_number, subscription.trip_id)
        await self._safe(
            self.r.set,
            key,
            subscription.model_dump_json(),
            ex=SUBSCRIPTION_TTL,
            context=f"set {key}",
        )

    async def get_subscription(
        self,
        flight_number: str,
        trip_id: str
    ) -> Optional[FlightSubscription]:
        """Get subscription from Redis."""
        key = subscription_key(flight_number, trip_id)
        raw = await self._safe(self.r.get, key, context=f"get {key}")

        if not raw:
            return None

        try:
            data = json.loads(raw)
            return FlightSubscription(**data)
        except Exception:
            return None

    async def delete_subscription(
        self,
        flight_number: str,
        trip_id: str
    ) -> None:
        """Delete subscription from Redis."""
        key = subscription_key(flight_number, trip_id)
        await self._safe(self.r.delete, key, context=f"delete {key}")

    # =========================================================================
    # Pub/Sub for Push Notifications
    # =========================================================================

    async def publish_push_notification(
        self,
        notification: PushNotification,
        trip_id: str
    ) -> None:
        """Publish push notification to Redis channel (legacy)."""
        channel = f"flight:push:{trip_id}"
        await self._safe(
            self.r.publish,
            channel,
            notification.model_dump_json(),
            context=f"publish {channel}",
        )

    async def publish_flight_update(
        self,
        arrival_iata: str,
        flight_number: str,
        message: dict
    ) -> None:
        """
        Publish flight update to Redis channel.

        Channel format: flight:push:{arrival_iata}:{flight_number}
        Only subscribers watching this arrival airport will receive it.
        """
        channel = f"flight:push:{arrival_iata.upper()}:{flight_number.upper()}"
        await self._safe(
            self.r.publish,
            channel,
            json.dumps(message, default=str),
            context=f"publish {channel}",
        )

    async def publish_position_update(
        self,
        position: FlightPosition
    ) -> None:
        """Publish position update to Redis channel."""
        channel = f"flight:track:{position.trip_id}"
        await self._safe(
            self.r.publish,
            channel,
            position.model_dump_json(),
            context=f"publish {channel}",
        )

    # =========================================================================
    # Notification Storage (for snapshot on connect)
    # =========================================================================

    async def store_notification(
        self,
        arrival_iata: str,
        flight_number: str,
        notification: dict
    ) -> bool:
        """
        Store notification in Redis sorted set.

        Uses notification ID for deduplication.
        Returns True if notification was new, False if duplicate.
        """
        key = notifications_key(arrival_iata, flight_number)
        notification_id = generate_notification_id(notification)

        # Check if notification already exists (by ID in value)
        existing = await self._safe(
            self.r.zrangebyscore,
            key,
            "-inf",
            "+inf",
            context=f"zrangebyscore {key}",
            default=[],
        )
        for item in existing:
            try:
                data = json.loads(item)
                if data.get("_notification_id") == notification_id:
                    return False  # Duplicate
            except Exception:
                continue

        # Add notification ID to the notification data
        notification_with_id = {**notification, "_notification_id": notification_id}

        # Score = current timestamp for ordering
        score = utcnow().timestamp()

        # Add to sorted set
        await self._safe(
            self.r.zadd,
            key,
            {json.dumps(notification_with_id, default=str): score},
            context=f"zadd {key}",
        )

        # Trim to max notifications (keep most recent)
        count = await self._safe(
            self.r.zcard,
            key,
            context=f"zcard {key}",
            default=0,
        )
        if count > MAX_NOTIFICATIONS_PER_FLIGHT:
            # Remove oldest (lowest scores)
            await self._safe(
                self.r.zremrangebyrank,
                key,
                0,
                count - MAX_NOTIFICATIONS_PER_FLIGHT - 1,
                context=f"zremrangebyrank {key}",
            )

        # Set TTL on the key
        await self._safe(
            self.r.expire,
            key,
            NOTIFICATION_TTL,
            context=f"expire {key}",
        )

        return True

    async def get_notifications(
        self,
        arrival_iata: str,
        flight_number: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get recent notifications for a flight.

        Returns notifications ordered by time (most recent first).
        """
        key = notifications_key(arrival_iata, flight_number)

        # Get most recent notifications (highest scores = most recent)
        raw_items = await self._safe(
            self.r.zrevrange,
            key,
            0,
            limit - 1,
            context=f"zrevrange {key}",
            default=[],
        )

        notifications = []
        for item in raw_items:
            try:
                data = item.decode() if isinstance(item, bytes) else item
                notification = json.loads(data)
                # Remove internal ID before returning
                notification.pop("_notification_id", None)
                notifications.append(notification)
            except Exception:
                continue

        return notifications

    async def get_notifications_for_flights(
        self,
        arrival_iata: str,
        flight_numbers: List[str],
        limit_per_flight: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get recent notifications for multiple flights.

        Returns all notifications sorted by received_at (most recent first).
        Useful for sending snapshot when client connects.
        """
        all_notifications = []

        for flight_number in flight_numbers:
            notifications = await self.get_notifications(
                arrival_iata,
                flight_number,
                limit=limit_per_flight
            )
            all_notifications.extend(notifications)

        # Sort all by received_at (most recent first)
        all_notifications.sort(
            key=lambda x: x.get("received_at", ""),
            reverse=True
        )

        return all_notifications


# =============================================================================
# Singleton
# =============================================================================

_tracking_cache: Optional[TrackingCache] = None


async def get_tracking_cache() -> TrackingCache:
    """Get or create singleton tracking cache."""
    global _tracking_cache
    if _tracking_cache is None:
        from shared.redis.redis_client import redis_client
        _tracking_cache = TrackingCache(redis_client)
    return _tracking_cache
