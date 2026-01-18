"""
Tracking Cache Service - Redis caching for flight positions.

Implements 2-second TTL cache with singleflight pattern to prevent
duplicate API requests when multiple clients request the same flight.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

import redis.asyncio as redis

from features.flights.models.tracking_models import (
    FlightPosition,
    FlightTrackingState,
    FlightSubscription,
    PushNotification,
)
from features.flights.services.adsb_client import get_adsb_client


# =============================================================================
# Config
# =============================================================================

POSITION_CACHE_TTL = 2  # seconds
LOCK_TTL_MS = 1500  # milliseconds
SUBSCRIPTION_TTL = 86400 * 2  # 2 days

# Redis key prefixes
PREFIX_POSITION = "flight:pos:"
PREFIX_TRACKING = "flight:track:"
PREFIX_SUBSCRIPTION = "flight:sub:"
PREFIX_ACTIVE_FLIGHTS = "flight:active"

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
        raw = await self.r.get(key)

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
        await self.r.set(key, position.model_dump_json(), ex=ttl)

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

        got_lock = await self.r.set(lk, token, nx=True, px=LOCK_TTL_MS)

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
                await self.r.eval(UNLOCK_LUA, 1, lk, token)
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
        raw = await self.r.get(key)

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
        await self.r.set(key, state.model_dump_json(), ex=ttl)

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
            await self.r.sadd(PREFIX_ACTIVE_FLIGHTS, member)
        else:
            await self.r.srem(PREFIX_ACTIVE_FLIGHTS, member)

    async def get_active_flights(self) -> List[str]:
        """Get all active flight tracking sessions."""
        members = await self.r.smembers(PREFIX_ACTIVE_FLIGHTS)
        return [m.decode() if isinstance(m, bytes) else m for m in members]

    # =========================================================================
    # Subscriptions
    # =========================================================================

    async def save_subscription(self, subscription: FlightSubscription) -> None:
        """Save subscription to Redis."""
        key = subscription_key(subscription.flight_number, subscription.trip_id)
        await self.r.set(key, subscription.model_dump_json(), ex=SUBSCRIPTION_TTL)

    async def get_subscription(
        self,
        flight_number: str,
        trip_id: str
    ) -> Optional[FlightSubscription]:
        """Get subscription from Redis."""
        key = subscription_key(flight_number, trip_id)
        raw = await self.r.get(key)

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
        await self.r.delete(key)

    # =========================================================================
    # Pub/Sub for Push Notifications
    # =========================================================================

    async def publish_push_notification(
        self,
        notification: PushNotification,
        trip_id: str
    ) -> None:
        """Publish push notification to Redis channel."""
        channel = f"flight:push:{trip_id}"
        await self.r.publish(channel, notification.model_dump_json())

    async def publish_position_update(
        self,
        position: FlightPosition
    ) -> None:
        """Publish position update to Redis channel."""
        channel = f"flight:track:{position.trip_id}"
        await self.r.publish(channel, position.model_dump_json())


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
