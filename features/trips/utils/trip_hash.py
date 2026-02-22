import hashlib
from datetime import date, time
from typing import Optional


def compute_trip_hash(
    pick_up_date: date,
    pick_up_time: time,
    pick_up_location: str,
    drop_off_location: str,
    airline: str,
    flight_number: str,
    riders: dict[str, int],
    trip_type: Optional[str] = None,
) -> str:
    """
    Deterministic SHA-256 hash for trip deduplication.

    Replaces Python's non-deterministic ``hash()`` which produces different
    values across processes / server restarts (PYTHONHASHSEED randomisation).
    """
    canonical_parts = [
        str(pick_up_date),
        pick_up_time.strftime("%H:%M:%S"),  # strip timezone for consistency
        pick_up_location.strip(),
        drop_off_location.strip(),
        airline.strip(),
        flight_number.strip(),
        str(sorted(riders.items())),
        str(trip_type) if trip_type else "",
    ]
    canonical_string = "|".join(canonical_parts)
    return hashlib.sha256(canonical_string.encode("utf-8")).hexdigest()
