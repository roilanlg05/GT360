"""
Webhook Handler - Receives push notifications from AeroDataBox.

When a flight status changes, AeroDataBox calls this webhook.
We process the notification and:
1. Extract flight info and arrival airport
2. Format a human-readable message based on status
3. Publish to Redis for WebSocket clients watching that arrival airport
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from features.flights.services.tracking_cache import get_tracking_cache
from features.flights.utils.webhook_utils import (
    utcnow,
    is_valid_aerodatabox_request,
)


router = APIRouter(tags=["Flight Webhooks"])
logger = logging.getLogger(__name__)


# AeroDataBox status codes to human-readable status
STATUS_MAP = {
    0: "Unknown",
    1: "Expected",
    2: "EnRoute",
    3: "CheckIn",
    4: "Boarding",
    5: "GateClosed",
    6: "Departed",
    7: "Delayed",
    8: "Approaching",
    9: "Arrived",
    10: "Canceled",
    11: "Diverted",
    12: "CanceledUncertain",
}


def get_status_string(status: Any) -> str:
    """Convert AeroDataBox status code to string."""
    if isinstance(status, int):
        return STATUS_MAP.get(status, f"Unknown({status})")
    if isinstance(status, str):
        return status
    return "Unknown"


def extract_flight_info(payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[Dict]]:
    """
    Extract flight number, arrival IATA, status, and flight data from payload.

    Returns:
        (flight_number, arrival_iata, status, flight_data)
    """
    # Get flight number from subscription or first flight
    flight_number = None
    subscription = payload.get("subscription", {})
    subject = subscription.get("subject", {})
    if subject.get("id"):
        flight_number = subject["id"]

    # Get flight data
    flights = payload.get("flights", [])
    flight_data = flights[0] if flights else None

    if flight_data:
        # Fallback flight number from flight data
        if not flight_number:
            flight_number = flight_data.get("number")

        # Get arrival airport IATA
        arrival = flight_data.get("arrival", {})
        airport = arrival.get("airport", {})
        arrival_iata = airport.get("iata")

        # Get status
        status_raw = flight_data.get("status")
        status = get_status_string(status_raw)

        return flight_number, arrival_iata, status, flight_data

    return flight_number, None, None, None


def format_time(time_str: Optional[str]) -> str:
    """Format time string to HH:MM format."""
    if not time_str:
        return "unknown time"
    try:
        # Parse "2026-01-21 18:28Z" or "2026-01-21 13:28-05:00"
        if "Z" in time_str:
            dt = datetime.strptime(time_str.replace("Z", "+0000"), "%Y-%m-%d %H:%M%z")
        else:
            # Local time with offset
            dt = datetime.fromisoformat(time_str.replace(" ", "T"))
        return dt.strftime("%H:%M")
    except Exception:
        return time_str


def build_notification_message(
    flight_number: str,
    status: str,
    flight_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build a notification message based on flight status.

    Returns dict with:
        - type: "flight_update"
        - flight_number: normalized flight number
        - status: status string
        - message: human-readable message
        - departure/arrival details
        - raw: original flight data
    """
    # Normalize flight number (remove spaces)
    fn_clean = flight_number.replace(" ", "")

    # Extract times
    departure = flight_data.get("departure", {})
    arrival = flight_data.get("arrival", {})

    dep_airport = departure.get("airport", {})
    arr_airport = arrival.get("airport", {})

    # Get the most accurate time (runway > revised > scheduled)
    dep_time = (
        departure.get("runwayTime", {}).get("local") or
        departure.get("revisedTime", {}).get("local") or
        departure.get("scheduledTime", {}).get("local")
    )
    arr_time = (
        arrival.get("runwayTime", {}).get("local") or
        arrival.get("revisedTime", {}).get("local") or
        arrival.get("scheduledTime", {}).get("local")
    )

    dep_time_formatted = format_time(dep_time)
    arr_time_formatted = format_time(arr_time)

    # Build message based on status
    status_upper = status.upper()

    if status_upper == "ARRIVED":
        message = f"Flight {fn_clean} has arrived at {arr_time_formatted}"
    elif status_upper == "DEPARTED":
        message = f"Flight {fn_clean} has departed at {dep_time_formatted}"
    elif status_upper == "ENROUTE":
        message = f"Flight {fn_clean} is en route"
    elif status_upper == "BOARDING":
        message = f"Flight {fn_clean} is now boarding"
    elif status_upper == "GATECLOSED":
        message = f"Flight {fn_clean} gate is now closed"
    elif status_upper == "DELAYED":
        message = f"Flight {fn_clean} has been delayed"
    elif status_upper == "CANCELED":
        message = f"Flight {fn_clean} has been canceled"
    elif status_upper == "DIVERTED":
        message = f"Flight {fn_clean} has been diverted"
    elif status_upper == "APPROACHING":
        message = f"Flight {fn_clean} is approaching {arr_airport.get('iata', 'destination')}"
    elif status_upper == "CHECKIN":
        message = f"Flight {fn_clean} check-in is now open"
    elif status_upper == "EXPECTED":
        message = f"Flight {fn_clean} is expected at {arr_time_formatted}"
    else:
        message = f"Flight {fn_clean} status: {status}"

    # Get airline info
    airline = flight_data.get("airline", {})

    return {
        "type": "flight_update",
        "flight_number": fn_clean,
        "status": status,
        "message": message,
        "departure": {
            "airport_iata": dep_airport.get("iata"),
            "airport_name": dep_airport.get("name"),
            "scheduled_time": departure.get("scheduledTime", {}).get("local"),
            "actual_time": dep_time,
        },
        "arrival": {
            "airport_iata": arr_airport.get("iata"),
            "airport_name": arr_airport.get("name"),
            "scheduled_time": arrival.get("scheduledTime", {}).get("local"),
            "actual_time": arr_time,
        },
        "airline": {
            "name": airline.get("name"),
            "iata": airline.get("iata"),
        },
        "aircraft": flight_data.get("aircraft"),
        "last_updated": flight_data.get("lastUpdatedUtc"),
        "raw": flight_data,
    }


@router.post("/v1/webhooks/flights/push")
async def receive_push_notification(request: Request):
    """
    Receive push notification from AeroDataBox and fan it out to WebSocket listeners.

    The webhook extracts:
    - flight_number from subscription.subject.id or flights[0].number
    - arrival_iata from flights[0].arrival.airport.iata
    - status and formats a human-readable message

    Only WebSocket subscribers watching this arrival_iata + flight_number
    will receive the notification.
    """
    if not is_valid_aerodatabox_request(request):
        raise HTTPException(403, "Forbidden")

    try:
        payload = await request.json()
    except Exception:
        now = utcnow()
        print("=" * 60)
        print("[WEBHOOK] Invalid JSON payload received")
        print(f"  date: {now.strftime('%Y-%m-%d')}")
        print(f"  time: {now.strftime('%H:%M:%S')}")
        print("=" * 60)
        raise HTTPException(400, "Invalid JSON payload")

    # Current timestamp
    now = utcnow()

    # Print received payload
    print("=" * 60)
    print("[WEBHOOK] Push notification received")
    print(f"  date: {now.strftime('%Y-%m-%d')}")
    print(f"  time: {now.strftime('%H:%M:%S')}")
    print(f"  payload: {json.dumps(payload, indent=2, default=str)}")
    print("=" * 60)

    # Save payload to file for debugging
    json_file = "/app/webhook_payload.json"
    try:
        with open(json_file, "w") as f:
            json.dump(payload, f, indent=2, default=str)
        print(f"[WEBHOOK] Payload saved to: {json_file}")
    except Exception as e:
        print(f"[WEBHOOK] Error saving JSON: {e}")

    # Extract flight info
    flight_number, arrival_iata, status, flight_data = extract_flight_info(payload)

    if not flight_number:
        print("[WEBHOOK] Could not extract flight number from payload")
        return JSONResponse({
            "status": "ok",
            "message": "No flight number found",
        })

    if not arrival_iata:
        print(f"[WEBHOOK] No arrival airport for flight {flight_number}")
        return JSONResponse({
            "status": "ok",
            "flight_number": flight_number,
            "message": "No arrival airport found",
        })

    if not flight_data:
        print(f"[WEBHOOK] No flight data for {flight_number}")
        return JSONResponse({
            "status": "ok",
            "flight_number": flight_number,
            "message": "No flight data found",
        })

    # Normalize flight number (remove spaces for matching)
    fn_normalized = flight_number.replace(" ", "").upper()

    # Build notification message
    notification = build_notification_message(flight_number, status, flight_data)
    notification["received_at"] = now.isoformat()

    print(f"[WEBHOOK] Flight: {fn_normalized}, Arrival: {arrival_iata}, Status: {status}")
    print(f"[WEBHOOK] Message: {notification['message']}")

    # Publish to Redis and store notification
    try:
        cache = await get_tracking_cache()

        # Store notification for snapshot (deduplication happens inside)
        is_new = await cache.store_notification(
            arrival_iata=arrival_iata,
            flight_number=fn_normalized,
            notification=notification
        )

        if is_new:
            # Only publish if it's a new notification (not duplicate)
            await cache.publish_flight_update(
                arrival_iata=arrival_iata,
                flight_number=fn_normalized,
                message=notification
            )
            print(f"[WEBHOOK] Published to Redis: flight:push:{arrival_iata}:{fn_normalized}")
        else:
            print(f"[WEBHOOK] Duplicate notification skipped: {fn_normalized} - {status}")

    except Exception as exc:
        print(f"[WEBHOOK] ERROR publishing to Redis: {exc}")
        raise

    return JSONResponse({
        "status": "ok",
        "flight_number": fn_normalized,
        "arrival_iata": arrival_iata,
        "flight_status": status,
        "message": notification["message"],
    })


@router.get("/v1/webhooks/flights/push/health")
async def webhook_health():
    """Health check for webhook endpoint."""
    return {"status": "ok", "timestamp": utcnow().isoformat()}
