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


# ---- Timeline utilities ----

def get_current_datetime_in_timezone(tz_name: str) -> datetime:
    """
    Get the current datetime in a specific timezone.

    Args:
        tz_name: IANA timezone name (e.g., "America/New_York")

    Returns:
        Current datetime in the specified timezone (timezone-aware)
    """
    return datetime.now(ZoneInfo(tz_name))


def get_current_date_in_timezone(tz_name: str) -> date:
    """
    Get the current date in a specific timezone.

    Args:
        tz_name: IANA timezone name (e.g., "America/New_York")

    Returns:
        Current date in the specified timezone
    """
    return get_current_datetime_in_timezone(tz_name).date()


def get_current_time_in_timezone(tz_name: str) -> time:
    """
    Get the current time in a specific timezone.

    Args:
        tz_name: IANA timezone name (e.g., "America/New_York")

    Returns:
        Current time in the specified timezone (without tzinfo)
    """
    return get_current_datetime_in_timezone(tz_name).time()


def compute_is_live(
    trip_status: str,
    pick_up_date: date,
    pick_up_time: time,
    location_timezone: str
) -> bool:
    """
    Determine if a trip is LIVE using Status + Time rules.

    Rules (in priority order):
    - COMPLETED or CANCELED → always HISTORY (False)
    - EN_ROUTE → always LIVE (True)
    - SCHEDULED → depends on whether pickup_time has passed in location timezone

    Args:
        trip_status: Trip status (scheduled, canceled, en_route, completed)
        pick_up_date: Pickup date (local date)
        pick_up_time: Pickup time (local time)
        location_timezone: IANA timezone of the location

    Returns:
        True if trip is LIVE, False if HISTORY
    """
    from shared.db.schemas import TripStatus

    # Status-based rules (highest priority)
    if trip_status in (TripStatus.COMPLETED, TripStatus.CANCELED):
        return False  # Always HISTORY

    if trip_status == TripStatus.EN_ROUTE:
        return True  # Always LIVE

    # Time-based rule for SCHEDULED trips
    now_local = get_current_datetime_in_timezone(location_timezone)

    # Combine pickup date + time into a datetime
    trip_datetime = datetime.combine(
        pick_up_date,
        pick_up_time,
        tzinfo=ZoneInfo(location_timezone)
    )

    # LIVE if pickup time is in the future
    return trip_datetime > now_local


def format_time_for_display(t: time, format_24h: bool = True) -> str:
    """
    Format a time for display.

    Args:
        t: Time to format
        format_24h: If True, use 24h format (14:30), else 12h format (2:30 PM)

    Returns:
        Formatted time string
    """
    if format_24h:
        return f"{t.hour:02d}:{t.minute:02d}"
    else:
        hour = t.hour % 12 or 12
        ampm = "AM" if t.hour < 12 else "PM"
        return f"{hour}:{t.minute:02d} {ampm}"


def build_cursor(pick_up_date: date, pick_up_time: time, trip_id: str) -> str:
    """
    Build a cursor string for timeline pagination.

    Format: {date}T{time}_{trip_id}
    Example: "2026-01-21T15:00:00_550e8400-e29b-41d4-a716-446655440000"

    Args:
        pick_up_date: Trip pickup date
        pick_up_time: Trip pickup time
        trip_id: Trip UUID as string

    Returns:
        Cursor string
    """
    time_str = f"{pick_up_time.hour:02d}:{pick_up_time.minute:02d}:{pick_up_time.second:02d}"
    return f"{pick_up_date.isoformat()}T{time_str}_{trip_id}"


def parse_cursor(cursor: str) -> tuple[date, time, str]:
    """
    Parse a cursor string into its components.

    Args:
        cursor: Cursor string in format "{date}T{time}_{trip_id}"

    Returns:
        Tuple of (pickup_date, pickup_time, trip_id)

    Raises:
        ValueError: If cursor format is invalid
    """
    try:
        datetime_part, trip_id = cursor.rsplit("_", 1)
        dt = datetime.fromisoformat(datetime_part)
        return dt.date(), dt.time(), trip_id
    except (ValueError, AttributeError) as e:
        raise ValueError(f"Invalid cursor format: {cursor}") from e