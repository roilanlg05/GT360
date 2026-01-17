"""
Flight Cache Service - Uses existing Redis instance for micro-caching flight data.

Features:
- Singleflight pattern to avoid stampede on cache miss
- Intelligent TTL based on flight status
- Rate limiting to protect API quota
- Metrics tracking (cache hits/misses, API calls)
- Batch fetching for multiple flights
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
import redis.asyncio as redis

from features.flights.models import Leg, FlightSnapshot


# =========================================================
# Config
# =========================================================

CACHE_TTL_SECONDS = int(os.getenv("FLIGHT_CACHE_TTL_SECONDS", "3"))
LOCK_TTL_MS = int(os.getenv("FLIGHT_LOCK_TTL_MS", "1500"))

# Rate limiting: max requests per minute to AeroDataBox
RATE_LIMIT_PER_MINUTE = int(os.getenv("FLIGHT_RATE_LIMIT_PER_MINUTE", "100"))

AERODATABOX_BASE_URL = os.getenv("AERODATABOX_BASE_URL", "https://aerodatabox.p.rapidapi.com")
AERODATABOX_RAPIDAPI_KEY = os.getenv("AERODATABOX_RAPIDAPI_KEY", "")
AERODATABOX_RAPIDAPI_HOST = os.getenv("AERODATABOX_RAPIDAPI_HOST", "aerodatabox.p.rapidapi.com")

AERODATABOX_WITH_LOCATION = os.getenv("AERODATABOX_WITH_LOCATION", "true").lower() == "true"
AERODATABOX_WITH_FLIGHT_PLAN = os.getenv("AERODATABOX_WITH_FLIGHT_PLAN", "false").lower() == "true"


# =========================================================
# Flight Status Constants
# =========================================================

class FlightStatus:
    """Known flight status values from AeroDataBox."""
    # Terminal states (high TTL)
    LANDED = "Landed"
    ARRIVED = "Arrived"
    CANCELED = "Canceled"
    DIVERTED = "Diverted"

    # Active states (low TTL)
    EN_ROUTE = "EnRoute"
    IN_FLIGHT = "InFlight"
    AIRBORNE = "Airborne"
    DEPARTED = "Departed"

    # Pre-flight states (medium TTL)
    SCHEDULED = "Scheduled"
    BOARDING = "Boarding"
    GATE_CLOSED = "GateClosed"
    DELAYED = "Delayed"

    # Unknown
    NOT_FOUND = "NOT_FOUND"
    UNKNOWN = "Unknown"


# =========================================================
# Time helpers
# =========================================================

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def first(*vals):
    for v in vals:
        if v is not None:
            return v
    return None


# =========================================================
# Redis keys
# =========================================================

UNLOCK_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
else
  return 0
end
"""


def norm_flight_number(fn: str) -> str:
    return fn.strip().upper()


def norm_date_local(d: str) -> str:
    return d.strip()


def cache_key(fn: str, date_local: str) -> str:
    return f"flight:snap:{norm_flight_number(fn)}:{norm_date_local(date_local)}"


def lock_key(k: str) -> str:
    return f"{k}:lock"


def rate_limit_key() -> str:
    """Key for rate limiting counter (resets every minute)."""
    minute = utcnow().strftime("%Y%m%d%H%M")
    return f"flight:ratelimit:{minute}"


def metrics_key(date: str) -> str:
    """Key for daily metrics."""
    return f"flight:metrics:{date}"


# =========================================================
# TTL Strategy - Intelligent caching based on status
# =========================================================

def ttl_for_status(status: Optional[str], minutes_to_arrival: Optional[int]) -> int:
    """
    Determine cache TTL based on flight status and ETA.

    Strategy:
    - Landed/Arrived: 60s (terminal state, won't change)
    - Canceled/Diverted: 120s (terminal state)
    - En route, close to arrival (<=30 min): 2s (need real-time updates)
    - En route, medium (30-60 min): 3s
    - En route, far (>60 min): 5s
    - Scheduled/Boarding: 15s (pre-flight, changes less frequent)
    - Unknown/Not found: 10s (retry soon)
    """
    status_upper = (status or "").upper()

    # Terminal states - cache longer
    if status_upper in ["LANDED", "ARRIVED"]:
        return 60
    if status_upper in ["CANCELED", "DIVERTED"]:
        return 120

    # Not found - short cache to retry
    if status_upper == "NOT_FOUND":
        return 10

    # Pre-flight states
    if status_upper in ["SCHEDULED", "BOARDING", "GATECLOSED", "DELAYED"]:
        return 15

    # En route - use minutes to arrival
    if minutes_to_arrival is not None:
        if minutes_to_arrival <= 30:
            return 2  # Critical phase - real-time
        if minutes_to_arrival <= 60:
            return 3
        if minutes_to_arrival <= 180:
            return 5
        return 10  # Far out, less urgent

    # Default for unknown status
    return 5


def ws_interval_for_status(status: Optional[str], minutes_to_arrival: Optional[int]) -> float:
    """
    Determine WebSocket polling interval based on flight status.

    Returns interval in seconds.
    """
    status_upper = (status or "").upper()

    # Terminal states - slow polling
    if status_upper in ["LANDED", "ARRIVED", "CANCELED", "DIVERTED"]:
        return 10.0

    # Not found
    if status_upper == "NOT_FOUND":
        return 5.0

    # Pre-flight
    if status_upper in ["SCHEDULED", "BOARDING", "GATECLOSED", "DELAYED"]:
        return 5.0

    # En route - adaptive based on proximity
    if minutes_to_arrival is not None:
        if minutes_to_arrival <= 15:
            return 1.0  # Very close - real-time
        if minutes_to_arrival <= 30:
            return 2.0
        if minutes_to_arrival <= 60:
            return 3.0
        return 5.0

    # Default
    return 3.0


# =========================================================
# Provider fetch (AeroDataBox Flight Status)
# =========================================================

async def fetch_aerodatabox_flights(
    client: httpx.AsyncClient,
    flight_number: str,
    date_local: str,
) -> List[Dict[str, Any]]:
    """
    AeroDataBox Flight Status:
      GET /flights/number/{flight_number}/{date_local}
    """
    if not AERODATABOX_RAPIDAPI_KEY:
        raise RuntimeError("Missing env AERODATABOX_RAPIDAPI_KEY")

    fn = norm_flight_number(flight_number)
    date_local = norm_date_local(date_local)

    url = f"{AERODATABOX_BASE_URL}/flights/number/{fn}/{date_local}"
    headers = {
        "X-RapidAPI-Key": AERODATABOX_RAPIDAPI_KEY,
        "X-RapidAPI-Host": AERODATABOX_RAPIDAPI_HOST,
        "Accept": "application/json",
    }

    params: Dict[str, str] = {"dateLocalRole": "Departure"}
    if AERODATABOX_WITH_LOCATION:
        params["withLocation"] = "true"
    if AERODATABOX_WITH_FLIGHT_PLAN:
        params["withFlightPlan"] = "true"

    r = await client.get(url, headers=headers, params=params)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else [data]


def _movement_times(mov: Dict[str, Any]) -> Dict[str, Optional[datetime]]:
    scheduled = parse_dt(((mov.get("scheduledTime") or {}).get("utc")))
    estimated = parse_dt(((mov.get("revisedTime") or {}).get("utc")))
    actual = parse_dt(((mov.get("runwayTime") or {}).get("utc")))
    return {"scheduled": scheduled, "estimated": estimated, "actual": actual}


def compute_legs(flights: List[Dict[str, Any]], flight_number: str) -> List[Leg]:
    fn = norm_flight_number(flight_number)
    legs_raw: List[Dict[str, Any]] = []

    for f in flights:
        if not isinstance(f, dict):
            continue
        num = norm_flight_number(str(f.get("number") or ""))
        if num and num != fn:
            continue

        dep = f.get("departure") or {}
        arr = f.get("arrival") or {}

        dep_t = _movement_times(dep)
        arr_t = _movement_times(arr)

        origin = ((dep.get("airport") or {}).get("iata")) or ((dep.get("airport") or {}).get("icao"))
        dest = ((arr.get("airport") or {}).get("iata")) or ((arr.get("airport") or {}).get("icao"))

        eta_dt = first(arr_t["estimated"], arr_t["scheduled"])
        dep_for_dur = first(dep_t["actual"], dep_t["estimated"], dep_t["scheduled"])
        dur_s = int(max(0, (eta_dt - dep_for_dur).total_seconds())) if (eta_dt and dep_for_dur) else None

        status = (f.get("status") or {}).get("value") if isinstance(f.get("status"), dict) else f.get("status")

        legs_raw.append({
            "origin": origin,
            "destination": dest,
            "dep_scheduled_utc": iso(dep_t["scheduled"]),
            "dep_estimated_utc": iso(dep_t["estimated"]),
            "dep_actual_utc": iso(dep_t["actual"]),
            "arr_scheduled_utc": iso(arr_t["scheduled"]),
            "arr_estimated_utc": iso(arr_t["estimated"]),
            "arr_actual_utc": iso(arr_t["actual"]),
            "eta_utc": iso(eta_dt),
            "duration_seconds": dur_s,
            "status": str(status) if status is not None else None,
            "provider_last_updated_utc": f.get("lastUpdatedUtc"),
        })

    def sort_key(x: Dict[str, Any]) -> str:
        return x["dep_actual_utc"] or x["dep_estimated_utc"] or x["dep_scheduled_utc"] or "9999"

    legs_raw.sort(key=sort_key)

    legs: List[Leg] = []
    for i, lr in enumerate(legs_raw, start=1):
        lr["seq"] = i
        legs.append(Leg(**lr))
    return legs


def pick_best_flight(flights: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    def updated_key(f: Dict[str, Any]) -> datetime:
        return parse_dt(f.get("lastUpdatedUtc")) or datetime.min.replace(tzinfo=timezone.utc)

    fs = [f for f in flights if isinstance(f, dict)]
    if not fs:
        return None
    fs.sort(key=updated_key, reverse=True)
    return fs[0]


def extract_position(best: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    loc = best.get("location") or {}
    if not isinstance(loc, dict):
        return None
    if loc.get("lat") is None or loc.get("lon") is None:
        return None

    out = {
        "lat": float(loc["lat"]),
        "lon": float(loc["lon"]),
        "reported_at_utc": loc.get("reportedAtUtc"),
    }
    if "groundSpeed" in loc:
        out["ground_speed"] = loc.get("groundSpeed")
    if "altitude" in loc:
        out["altitude"] = loc.get("altitude")
    if "trueTrack" in loc:
        out["true_track"] = loc.get("trueTrack")

    return out


def build_snapshot(
    flight_number: str,
    date_local: str,
    flights: List[Dict[str, Any]],
    ttl: int,
    ws_interval: float = 1.0
) -> FlightSnapshot:
    fn = norm_flight_number(flight_number)
    date_local = norm_date_local(date_local)

    legs = compute_legs(flights, fn)
    best = pick_best_flight(flights)

    status = None
    eta = None
    provider_last_updated = None
    position = None
    duration_seconds = None

    if best:
        status = (best.get("status") or {}).get("value") if isinstance(best.get("status"), dict) else best.get("status")
        provider_last_updated = best.get("lastUpdatedUtc")

        dep = best.get("departure") or {}
        arr = best.get("arrival") or {}

        dep_t = _movement_times(dep)
        arr_t = _movement_times(arr)

        eta_dt = first(arr_t["estimated"], arr_t["scheduled"])
        eta = iso(eta_dt)

        dep_for_dur = first(dep_t["actual"], dep_t["estimated"], dep_t["scheduled"])
        if eta_dt and dep_for_dur:
            duration_seconds = int(max(0, (eta_dt - dep_for_dur).total_seconds()))

        position = extract_position(best)

    minutes_to_arrival = None
    if eta:
        eta_dt = parse_dt(eta)
        if eta_dt:
            minutes_to_arrival = int((eta_dt - utcnow()).total_seconds() / 60)

    return FlightSnapshot(
        flight_number=fn,
        date_local=date_local,
        status=str(status) if status is not None else None,
        eta_utc=eta,
        minutes_to_arrival=minutes_to_arrival,
        duration_seconds=duration_seconds,
        position=position,
        legs=legs,
        provider_last_updated_utc=provider_last_updated,
        cached_at_utc=utcnow().isoformat(),
        cache_ttl_seconds=ttl,
        ws_interval_seconds=ws_interval,
    )


# =========================================================
# FlightCache - Main service class
# =========================================================

class FlightCache:
    """
    Flight caching service with:
    - Singleflight pattern (avoid stampede)
    - Intelligent TTL based on status
    - Rate limiting
    - Metrics tracking
    - Batch fetching
    """

    def __init__(self, redis_client: redis.Redis, http_client: Optional[httpx.AsyncClient] = None):
        self.r = redis_client
        self._http = http_client
        self._owns_http = http_client is None

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=8, read=18, write=8, pool=8)
            )
        return self._http

    async def close(self) -> None:
        if self._owns_http and self._http:
            await self._http.aclose()
            self._http = None

    # =========================================================
    # Metrics
    # =========================================================

    async def _increment_metric(self, metric: str) -> None:
        """Increment a daily metric counter."""
        try:
            key = metrics_key(utcnow().strftime("%Y-%m-%d"))
            await self.r.hincrby(key, metric, 1)
            await self.r.expire(key, 86400 * 7)  # Keep 7 days
        except Exception:
            pass  # Metrics should never break the main flow

    async def get_metrics(self, date: Optional[str] = None) -> Dict[str, int]:
        """Get metrics for a specific date (default: today)."""
        if date is None:
            date = utcnow().strftime("%Y-%m-%d")
        key = metrics_key(date)
        try:
            data = await self.r.hgetall(key)
            return {k: int(v) for k, v in data.items()}
        except Exception:
            return {}

    # =========================================================
    # Rate limiting
    # =========================================================

    async def _check_rate_limit(self) -> bool:
        """
        Check if we're within rate limit.
        Returns True if request is allowed, False if rate limited.
        """
        key = rate_limit_key()
        try:
            current = await self.r.incr(key)
            if current == 1:
                await self.r.expire(key, 60)  # Expire after 1 minute
            return current <= RATE_LIMIT_PER_MINUTE
        except Exception:
            return True  # Allow on error

    async def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get current rate limit status."""
        key = rate_limit_key()
        try:
            current = await self.r.get(key)
            return {
                "current": int(current) if current else 0,
                "limit": RATE_LIMIT_PER_MINUTE,
                "remaining": max(0, RATE_LIMIT_PER_MINUTE - (int(current) if current else 0)),
            }
        except Exception:
            return {"current": 0, "limit": RATE_LIMIT_PER_MINUTE, "remaining": RATE_LIMIT_PER_MINUTE}

    # =========================================================
    # Cache operations
    # =========================================================

    async def get_snapshot(self, fn: str, date_local: str) -> Optional[FlightSnapshot]:
        k = cache_key(fn, date_local)
        raw = await self.r.get(k)
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return FlightSnapshot(**data)
        except Exception:
            return None

    async def set_snapshot(self, fn: str, date_local: str, snap: FlightSnapshot, ttl: int) -> None:
        k = cache_key(fn, date_local)
        await self.r.set(k, snap.model_dump_json(), ex=ttl)

    async def get_or_fetch(self, fn: str, date_local: str) -> FlightSnapshot:
        fn = norm_flight_number(fn)
        date_local = norm_date_local(date_local)

        # 1) Cache hit
        cached = await self.get_snapshot(fn, date_local)
        if cached:
            await self._increment_metric("cache_hits")
            return cached

        await self._increment_metric("cache_misses")

        # 2) Lock to avoid stampede
        k = cache_key(fn, date_local)
        lk = lock_key(k)
        token = str(uuid.uuid4())

        got_lock = await self.r.set(lk, token, nx=True, px=LOCK_TTL_MS)
        if not got_lock:
            # Another worker is fetching. Wait briefly and re-check cache.
            await asyncio.sleep(0.12)
            cached2 = await self.get_snapshot(fn, date_local)
            if cached2:
                return cached2
            await asyncio.sleep(0.12)
            cached3 = await self.get_snapshot(fn, date_local)
            if cached3:
                return cached3
            # Worst case: fetch anyway (rare)
            return await self._fetch_and_cache(fn, date_local)

        try:
            # double-check after lock
            cached4 = await self.get_snapshot(fn, date_local)
            if cached4:
                return cached4

            return await self._fetch_and_cache(fn, date_local)
        finally:
            # Safe unlock
            try:
                await self.r.eval(UNLOCK_LUA, 1, lk, token)
            except Exception:
                pass

    async def _fetch_and_cache(self, fn: str, date_local: str) -> FlightSnapshot:
        # Check rate limit
        if not await self._check_rate_limit():
            await self._increment_metric("rate_limited")
            # Return a rate-limited response (serve stale if possible or error)
            cached = await self.get_snapshot(fn, date_local)
            if cached:
                return cached
            # No cache, return error snapshot
            return FlightSnapshot(
                flight_number=fn,
                date_local=date_local,
                status="RATE_LIMITED",
                eta_utc=None,
                minutes_to_arrival=None,
                duration_seconds=None,
                position=None,
                legs=[],
                provider_last_updated_utc=None,
                cached_at_utc=utcnow().isoformat(),
                cache_ttl_seconds=5,
                ws_interval_seconds=5.0,
            )

        await self._increment_metric("api_calls")

        http = await self._get_http()
        try:
            flights = await fetch_aerodatabox_flights(http, fn, date_local)
        except httpx.HTTPStatusError as e:
            await self._increment_metric("api_errors")
            raise
        except Exception as e:
            await self._increment_metric("api_errors")
            raise

        # Not found: negative cache
        if not flights:
            await self._increment_metric("flights_not_found")
            ttl = ttl_for_status(FlightStatus.NOT_FOUND, None)
            ws_interval = ws_interval_for_status(FlightStatus.NOT_FOUND, None)
            snap = FlightSnapshot(
                flight_number=fn,
                date_local=date_local,
                status=FlightStatus.NOT_FOUND,
                eta_utc=None,
                minutes_to_arrival=None,
                duration_seconds=None,
                position=None,
                legs=[],
                provider_last_updated_utc=None,
                cached_at_utc=utcnow().isoformat(),
                cache_ttl_seconds=ttl,
                ws_interval_seconds=ws_interval,
            )
            await self.set_snapshot(fn, date_local, snap, ttl=ttl)
            return snap

        # Build snapshot with intelligent TTL
        # First pass to get status and minutes_to_arrival
        tmp = build_snapshot(fn, date_local, flights, ttl=CACHE_TTL_SECONDS)
        ttl = ttl_for_status(tmp.status, tmp.minutes_to_arrival)
        ws_interval = ws_interval_for_status(tmp.status, tmp.minutes_to_arrival)

        snap = build_snapshot(fn, date_local, flights, ttl=ttl, ws_interval=ws_interval)
        await self.set_snapshot(fn, date_local, snap, ttl=ttl)
        return snap

    # =========================================================
    # Batch fetching
    # =========================================================

    async def get_or_fetch_batch(
        self,
        flights: List[Tuple[str, str]],
        max_concurrent: int = 10
    ) -> List[FlightSnapshot]:
        """
        Fetch multiple flights in parallel.

        Args:
            flights: List of (flight_number, date_local) tuples
            max_concurrent: Max concurrent API requests

        Returns:
            List of FlightSnapshot in same order as input
        """
        if not flights:
            return []

        # Normalize and dedupe
        normalized = [(norm_flight_number(fn), norm_date_local(d)) for fn, d in flights]
        unique_flights = list(dict.fromkeys(normalized))  # Preserve order, remove dupes

        # Semaphore to limit concurrent fetches
        sem = asyncio.Semaphore(max_concurrent)

        async def fetch_one(fn: str, date_local: str) -> FlightSnapshot:
            async with sem:
                return await self.get_or_fetch(fn, date_local)

        # Fetch all unique flights
        tasks = [fetch_one(fn, d) for fn, d in unique_flights]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build lookup
        lookup: Dict[Tuple[str, str], FlightSnapshot] = {}
        for (fn, d), result in zip(unique_flights, results):
            if isinstance(result, Exception):
                # Return error snapshot for failed fetches
                lookup[(fn, d)] = FlightSnapshot(
                    flight_number=fn,
                    date_local=d,
                    status="ERROR",
                    eta_utc=None,
                    minutes_to_arrival=None,
                    duration_seconds=None,
                    position=None,
                    legs=[],
                    provider_last_updated_utc=None,
                    cached_at_utc=utcnow().isoformat(),
                    cache_ttl_seconds=5,
                    ws_interval_seconds=5.0,
                )
            else:
                lookup[(fn, d)] = result

        # Return in original order
        return [lookup[key] for key in normalized]


# =========================================================
# Singleton instance (lazy initialization)
# =========================================================

_flight_cache: Optional[FlightCache] = None


async def get_flight_cache() -> FlightCache:
    """Get or create the singleton FlightCache instance."""
    global _flight_cache
    if _flight_cache is None:
        from shared.redis.redis_client import redis_client
        _flight_cache = FlightCache(redis_client)
    return _flight_cache
