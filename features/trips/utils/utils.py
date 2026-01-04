from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, date, time
from functools import lru_cache
from zoneinfo import ZoneInfo
from timezonefinder import TimezoneFinder
import json
from shared.redis.redis_client import redis_client
from psqlmodel import Select
from shared.db.schemas import Location


async def save_trip_event_to_redis(trip_id: str, event_data: dict):
    """
    Save or update trip event data in Redis by trip_id.
    Args:
        trip_id (str): The location identifier.
        event_data (dict): The event data to store.
    """
    key = f"trip:{trip_id}"
    await redis_client.set(key, json.dumps(event_data))

async def get_trip_event_from_redis(trip_id: str):
    """
    Retrieve trip event data from Redis by location_id.
    Args:
        location_id (str): The location identifier.
    Returns:
        dict or None: The event data if exists, else None.
    """
    key = f"trip:{trip_id}"
    data = await redis_client.get(key)
    return json.loads(data) if data else None

async def get_locations_by_org_id(session, org_id):
    locations = await session.exec(
        Select(Location)
        .Where(Location.organization_id == org_id)
    ).to_dicts()
    return locations

# ---- Core: timezone lookup (Lat/Lon -> IANA) ----

_tf = TimezoneFinder()

@lru_cache(maxsize=50_000)
def tz_from_latlon(lat: float, lon: float) -> str:
    """
    Returns IANA timezone name for a given lat/lon, e.g. "America/New_York".
    Cached for speed.
    """
    tz = _tf.timezone_at(lat=lat, lng=lon) or _tf.closest_timezone_at(lat=lat, lng=lon)
    if not tz:
        raise ValueError(f"Could not determine timezone for lat={lat}, lon={lon}")
    return tz


# ---- Core: UTC timestamps ----

def utc_now() -> datetime:
    """Current time in UTC (timezone-aware)."""
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime) -> datetime:
    """
    Ensures a datetime is timezone-aware and in UTC.
    If naive -> raises (avoid guessing).
    """
    if dt.tzinfo is None:
        raise ValueError("Datetime must be timezone-aware (expected UTC or convertible to UTC).")
    return dt.astimezone(timezone.utc)


# ---- Core: conversions ----

def utc_to_local(dt_utc: datetime, tz_name: str) -> datetime:
    """Convert UTC datetime to local tz (DST-safe)."""
    dt_utc = ensure_utc(dt_utc)
    return dt_utc.astimezone(ZoneInfo(tz_name))


def local_to_utc(dt_local: datetime, tz_name: str | None = None) -> datetime:
    """
    Convert local datetime -> UTC.
    - If dt_local is naive, you MUST provide tz_name.
    - If dt_local is aware, tz_name is ignored.
    """
    if dt_local.tzinfo is None:
        if not tz_name:
            raise ValueError("If dt_local is naive, tz_name is required.")
        dt_local = dt_local.replace(tzinfo=ZoneInfo(tz_name))
    return dt_local.astimezone(timezone.utc)


def local_date_time_to_utc(d: date, t: time, tz_name: str) -> datetime:
    """
    Convert (date + local time + tz) -> UTC datetime.
    Useful for schedule times like 8:00 AM that must become an instant.
    """
    # NOTE: This assumes t is a wall-clock time in tz_name.
    dt_local = datetime(d.year, d.month, d.day, t.hour, t.minute, t.second, tzinfo=ZoneInfo(tz_name))
    return dt_local.astimezone(timezone.utc)


def utc_to_local_date_time(dt_utc: datetime, tz_name: str) -> tuple[date, time]:
    """Convert UTC -> (local date, local time)."""
    local_dt = utc_to_local(dt_utc, tz_name)
    return local_dt.date(), local_dt.timetz().replace(tzinfo=None)


# ---- Formatting helpers for API payloads ----

@dataclass(frozen=True)
class ZonedTimestamp:
    utc_iso: str
    local_iso: str
    tz_name: str
    tz_abbrev: str
    utc_offset: str  # e.g. "-05:00"


def build_zoned_timestamp(dt_utc: datetime, tz_name: str) -> ZonedTimestamp:
    """
    Build a stable payload for frontend:
    - utc_iso: ISO in UTC
    - local_iso: ISO in local tz
    - tz_abbrev: EST/EDT etc (depends on date)
    - utc_offset: "-05:00" etc
    """
    dt_utc = ensure_utc(dt_utc)
    local_dt = utc_to_local(dt_utc, tz_name)

    offset = local_dt.utcoffset()
    offset_str = offset and _format_timedelta_offset(offset) or "+00:00"

    return ZonedTimestamp(
        utc_iso=dt_utc.isoformat(),
        local_iso=local_dt.isoformat(),
        tz_name=tz_name,
        tz_abbrev=local_dt.tzname() or "",
        utc_offset=offset_str,
    )


def build_event_timestamp_from_latlon(lat: float, lon: float, dt_utc: datetime | None = None) -> ZonedTimestamp:
    """
    Typical usage for "driver pressed complete":
    - backend sets dt_utc = utc_now()
    - tz comes from driver's lat/lon at completion
    """
    if dt_utc is None:
        dt_utc = utc_now()
    tz_name = tz_from_latlon(lat, lon)
    return build_zoned_timestamp(dt_utc, tz_name)


def build_time_label_for_list(d: date, t: time, tz_name: str) -> dict:
    """
    For trip list UI, where you have a local wall-clock time (e.g. 08:00)
    and you want to send timezone + a friendly label + computed UTC instant.
    """
    local_dt = datetime(d.year, d.month, d.day, t.hour, t.minute, t.second, tzinfo=ZoneInfo(tz_name))
    return {
        "time_local": _format_ampm(local_dt),
        "tz_name": tz_name,
        "tz_abbrev": local_dt.tzname() or "",
        "utc_offset": _format_timedelta_offset(local_dt.utcoffset()) if local_dt.utcoffset() else "+00:00",
        "at_utc_iso": local_dt.astimezone(timezone.utc).isoformat(),
        "at_local_iso": local_dt.isoformat(),
    }


# ---- Internal formatting ----

def _format_ampm(dt: datetime) -> str:
    """
    '8:00 AM' formatter.
    Uses a cross-platform approach (avoids %-I issues on Windows).
    """
    hour = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{hour}:{dt.minute:02d} {ampm}"


def _format_timedelta_offset(td) -> str:
    # td is datetime.timedelta
    total_seconds = int(td.total_seconds())
    sign = "+" if total_seconds >= 0 else "-"
    total_seconds = abs(total_seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    return f"{sign}{hours:02d}:{minutes:02d}"