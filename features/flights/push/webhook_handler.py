"""
Webhook Handler - Receives push notifications from AeroDataBox.

When a flight status changes, AeroDataBox calls this webhook.
We process the notification and:
1. Publish to Redis for WebSocket clients
2. If flight departed, activate real-time tracking
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import JSONResponse

from features.flights.models.tracking_models import (
    PushNotification,
    FlightTrackingState,
    FlightStatus,
    TrackingInterval,
)
from features.flights.services.tracking_cache import get_tracking_cache


router = APIRouter(tags=["Flight Webhooks"])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_aerodatabox_notification(payload: Dict[str, Any]) -> PushNotification:
    """
    Parse AeroDataBox webhook payload into PushNotification.

    AeroDataBox sends flight status updates in various formats.
    This function normalizes the data.
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
    """Determine if we should start real-time tracking based on status."""
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
    """Determine if we should stop tracking based on status."""
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


@router.post("/v1/webhooks/flights/push")
async def receive_push_notification(
    request: Request,
    trip_id: str = Query(..., description="Trip ID from subscription"),
    date: str = Query(None, description="Date from subscription"),
):
    """
    Receive push notification from AeroDataBox.

    This endpoint is called by AeroDataBox when a subscribed flight
    changes status.

    Query params are passed from the subscription webhook URL.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON payload")

    # Parse notification
    notification = parse_aerodatabox_notification(payload)

    if not notification.flight_number:
        # Can't process without flight number
        return JSONResponse({"status": "ignored", "reason": "no flight number"})

    cache = await get_tracking_cache()

    # Publish notification to Redis for WebSocket clients
    await cache.publish_push_notification(notification, trip_id)

    # Get or create tracking state
    state = await cache.get_tracking_state(notification.flight_number, trip_id)

    if not state:
        state = FlightTrackingState(
            flight_number=notification.flight_number,
            trip_id=trip_id,
            date_local=date or "",
            status=FlightStatus.UNKNOWN,
            is_tracking_active=False,
        )

    # Update status
    if notification.status:
        try:
            state.status = FlightStatus(notification.status)
        except ValueError:
            state.status = FlightStatus.UNKNOWN

    # Check if we should activate/deactivate tracking
    if should_activate_tracking(notification.status):
        state.is_tracking_active = True
        state.current_interval = TrackingInterval.FAR
        state.interval_seconds = 1200  # Start with 20 min, will adjust based on ETA

    elif should_stop_tracking(notification.status):
        state.is_tracking_active = False

    # Save state
    await cache.set_tracking_state(state)

    # Update active flights set
    await cache.update_tracking_active(
        notification.flight_number,
        trip_id,
        state.is_tracking_active
    )

    return JSONResponse({
        "status": "ok",
        "flight_number": notification.flight_number,
        "trip_id": trip_id,
        "flight_status": notification.status,
        "tracking_active": state.is_tracking_active,
    })


@router.get("/v1/webhooks/flights/push/health")
async def webhook_health():
    """Health check for webhook endpoint."""
    return {"status": "ok", "timestamp": utcnow().isoformat()}
