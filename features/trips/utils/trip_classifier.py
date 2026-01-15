"""
Trip type classification utilities.

Provides robust trip type classification based on pickup/dropoff locations
compared against the location's airport code.
"""

from typing import Literal
from shared.db.schemas import TripType

TripTypeValue = Literal["inbound", "outbound", "ground"]


def classify_trip_type_sync(
    pick_up_location: str,
    drop_off_location: str,
    location_airport_code: str,
) -> TripTypeValue:
    """
    Classify trip based on pickup/dropoff locations.

    Logic:
    - inbound: pickup is airport → dropoff is NOT airport
    - outbound: pickup is NOT airport → dropoff is airport
    - ground: neither matches airport code

    Args:
        pick_up_location: Trip pickup location string
        drop_off_location: Trip dropoff location string
        location_airport_code: Airport code (e.g., "SDF")

    Returns:
        "inbound", "outbound", or "ground"

    Examples:
        >>> classify_trip_type_sync("SDF", "Marriott Hotel", "SDF")
        "inbound"

        >>> classify_trip_type_sync("Holiday Inn", "SDF", "SDF")
        "outbound"

        >>> classify_trip_type_sync("Marriott", "Holiday Inn", "SDF")
        "ground"
    """
    # Normalize inputs for comparison
    pick_up = pick_up_location.strip().upper()
    drop_off = drop_off_location.strip().upper()
    airport = location_airport_code.strip().upper()

    # Check if locations match airport code
    pickup_is_airport = pick_up == airport
    dropoff_is_airport = drop_off == airport

    # Classification logic
    if pickup_is_airport and not dropoff_is_airport:
        return TripType.INBOUND
    elif not pickup_is_airport and dropoff_is_airport:
        return TripType.OUTBOUND
    else:
        # Both are airport OR neither is airport → ground
        return TripType.GROUND


async def classify_trip_type(
    pick_up_location: str,
    drop_off_location: str,
    location_airport_code: str,
) -> TripTypeValue:
    """
    Async version for use in API routes.

    Same logic as classify_trip_type_sync but async-compatible.
    """
    return classify_trip_type_sync(
        pick_up_location, drop_off_location, location_airport_code
    )
