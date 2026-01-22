"""
Webhook utility functions for flight tracking.

Contains:
- DateTime utilities
- AeroDataBox notification parser
- Tracking activation/deactivation logic
- Request validation
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import Request

from features.flights.models.tracking_models import PushNotification


# Expected User-Agent from AeroDataBox
AERODATABOX_USER_AGENT_PREFIX = "AeroDataBoxNotificationBot/"


def utcnow() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)


def is_valid_aerodatabox_request(request: Request) -> bool:
    """Validate that the request comes from AeroDataBox by checking User-Agent."""
    user_agent = request.headers.get("user-agent", "")
    return user_agent.startswith(AERODATABOX_USER_AGENT_PREFIX)


def parse_aerodatabox_notification(payload: Dict[str, Any]) -> PushNotification:
    """
    Parse AeroDataBox webhook payload into PushNotification.

    AeroDataBox sends flight status updates in various formats.
    This function normalizes the data.

    Args:
        payload: Raw JSON payload from AeroDataBox webhook

    Returns:
        Normalized PushNotification object
    """
    # Extract flight number from various possible fields
    flight_number = (
        payload.get("number") or
        payload.get("flightNumber") or
        payload.get("flight", {}).get("number") or
        payload.get("flightIata") or
        payload.get("flightIcao")
    )

    # Extract status
    status_raw = payload.get("status")
    if isinstance(status_raw, dict):
        status = status_raw.get("value") or status_raw.get("status")
    else:
        status = status_raw

    # Extract departure info
    departure = payload.get("departure", {})
    dep_airport = (
        departure.get("airport", {}).get("iata") or
        departure.get("airport", {}).get("icao") or
        departure.get("iata") or
        payload.get("departureAirport")
    )

    dep_scheduled = departure.get("scheduledTime", {}).get("utc")
    dep_estimated = departure.get("revisedTime", {}).get("utc")
    dep_actual = departure.get("runwayTime", {}).get("utc")

    # Extract arrival info
    arrival = payload.get("arrival", {})
    arr_airport = (
        arrival.get("airport", {}).get("iata") or
        arrival.get("airport", {}).get("icao") or
        arrival.get("iata") or
        payload.get("arrivalAirport")
    )

    arr_scheduled = arrival.get("scheduledTime", {}).get("utc")
    arr_estimated = arrival.get("revisedTime", {}).get("utc")
    arr_actual = arrival.get("runwayTime", {}).get("utc")

    return PushNotification(
        flight_number=flight_number,
        flight_iata=payload.get("flightIata"),
        flight_icao=payload.get("flightIcao"),
        status=status,
        departure_airport=dep_airport,
        departure_scheduled=dep_scheduled,
        departure_estimated=dep_estimated,
        departure_actual=dep_actual,
        arrival_airport=arr_airport,
        arrival_scheduled=arr_scheduled,
        arrival_estimated=arr_estimated,
        arrival_actual=arr_actual,
        raw=payload,
        received_at=utcnow().isoformat(),
    )


def should_activate_tracking(status: Optional[str]) -> bool:
    """
    Determine if we should start real-time tracking based on flight status.

    Args:
        status: Flight status string from AeroDataBox

    Returns:
        True if tracking should be activated
    """
    if not status:
        return False

    status_upper = status.upper()

    # Activate tracking when flight departs
    return status_upper in [
        "DEPARTED",
        "ENROUTE",
        "INFLIGHT",
        "AIRBORNE",
        "TAKINGOFF",
        "TAKING_OFF",
    ]


def should_stop_tracking(status: Optional[str]) -> bool:
    """
    Determine if we should stop tracking based on flight status.

    Args:
        status: Flight status string from AeroDataBox

    Returns:
        True if tracking should be stopped
    """
    if not status:
        return False

    status_upper = status.upper()

    # Stop tracking when flight lands or is cancelled
    return status_upper in [
        "LANDED",
        "ARRIVED",
        "CANCELED",
        "CANCELLED",
        "DIVERTED",
    ]
