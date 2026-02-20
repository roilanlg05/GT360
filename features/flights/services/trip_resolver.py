"""
Trip Airport Resolver

Resolves the origin/destination airports for a flight tracking session
directly from the trip record in the database.

This is the authoritative source — no external API calls needed.
"""

from __future__ import annotations

import logging
from typing import Optional

from shared.db.db_config import engine
from psqlmodel import AsyncSession, Select
from shared.db.schemas.trips.trips import Trip as TripDB, TripType
from shared.db.schemas.entities.airports import Airport as AirportDB
from features.flights.models.tracking_models import Airport

logger = logging.getLogger(__name__)


async def get_trip_airports(trip_id: str) -> tuple[Optional[Airport], Optional[Airport]]:
    """
    Resolve origin and destination airports for a trip.

    Only inbound trips are tracked (outbound and ground don't need flight tracking).

    For inbound trips: pick_up_location holds the arriving airport IATA code
    (e.g. "SDF"), which is the flight's destination. Coordinates come from the
    local airports table — no external API needed.

    Returns:
        (None, destination_airport) for inbound, (None, None) for everything else.
    """
    try:
        async with AsyncSession(engine) as session:
            # 1. Fetch trip
            trip_rows = await session.exec(
                Select(TripDB).Where(TripDB.id == trip_id)
            )
            trip = trip_rows.first()

            if not trip:
                logger.warning(f"[TRIP_RESOLVER] Trip not found: {trip_id}")
                return None, None

            # Only inbound trips are tracked — outbound and ground have no tracking
            if trip.trip_type != TripType.INBOUND:
                logger.debug(f"[TRIP_RESOLVER] Trip {trip_id} is type={trip.trip_type}, skipping airport resolution")
                return None, None

            # Inbound: flight arrives at local airport → pick_up_location = destination
            destination_code = _extract_airport_code(trip.pick_up_location)
            destination = await _lookup_airport(session, destination_code)

            logger.info(
                f"[TRIP_RESOLVER] trip={trip_id} inbound → destination={destination_code} "
                f"({'found' if destination else 'not in airports table'})"
            )
            return None, destination

    except Exception as e:
        logger.error(f"[TRIP_RESOLVER] Error resolving airports for trip {trip_id}: {type(e).__name__}: {e}")
        return None, None


def _extract_airport_code(value: Optional[str]) -> Optional[str]:
    """
    Extract a valid IATA airport code from a pick_up/drop_off string.

    Codes are stored as 3-letter uppercase strings (e.g. "SDF", "JFK").
    Hotel names are longer strings and are ignored.
    """
    if not value:
        return None
    v = value.strip().upper()
    if len(v) == 3 and v.isalpha():
        return v
    return None


async def _lookup_airport(session: AsyncSession, code: Optional[str]) -> Optional[Airport]:
    """Look up an airport by IATA code and return it with coordinates."""
    if not code:
        return None

    try:
        rows = await session.exec(
            Select(AirportDB).Where(AirportDB.code == code)
        )
        airport_db = rows.first()

        if not airport_db:
            logger.warning(f"[TRIP_RESOLVER] Airport code '{code}' not found in airports table")
            return None

        return Airport(
            icao=code,   # Our DB uses IATA as the code; use it as identifier
            iata=code,
            name=airport_db.name,
            lat=airport_db.latitude,
            lon=airport_db.longitude,
        )

    except Exception as e:
        logger.error(f"[TRIP_RESOLVER] Error looking up airport '{code}': {type(e).__name__}: {e}")
        return None
