"""
Webhook Handler - Receives push notifications from AeroDataBox.

When a flight status changes, AeroDataBox calls this webhook.
We process the notification and:
1. Publish to Redis for WebSocket clients
2. If flight departed, activate real-time tracking
3. Log all events to WEBHOOK_EVENTS.json for debugging
"""

import json
import asyncio
import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import JSONResponse

from features.flights.models.tracking_models import PushNotification
from features.flights.services.tracking_cache import get_tracking_cache
from features.flights.utils.webhook_utils import (
    utcnow,
    is_valid_aerodatabox_request,
    parse_aerodatabox_notification,
)


router = APIRouter(tags=["Flight Webhooks"])
logger = logging.getLogger(__name__)

# Path to webhook events log file
WEBHOOK_EVENTS_FILE = Path(__file__).parent / "WEBHOOK_EVENTS.json"

# Lock for thread-safe file writes
_file_lock = asyncio.Lock()


async def save_webhook_event(
    payload: Dict[str, Any],
    trip_id: str,
    date: str | None,
    processed_status: str | None,
    tracking_active: bool,
    note: str | None = None,
    error: str | None = None,
) -> None:
    """
    Save webhook event to JSON file for debugging and analysis.

    Args:
        payload: Raw payload from AeroDataBox
        trip_id: Trip ID from query params
        date: Date from query params
        processed_status: Status after processing
        tracking_active: Whether tracking was activated
        note: Extra context (e.g. ignored reasons)
        error: Error message if processing failed
    """
    event = {
        "received_at": utcnow().isoformat(),
        "trip_id": trip_id,
        "date": date,
        "processed_status": processed_status,
        "tracking_active": tracking_active,
        "raw_payload": payload,
    }

    if note:
        event["note"] = note
    if error:
        event["error"] = error

    try:
        WEBHOOK_EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)

        async with _file_lock:
            # Read existing events
            events = []
            if WEBHOOK_EVENTS_FILE.exists():
                try:
                    content = WEBHOOK_EVENTS_FILE.read_text()
                    if content.strip():
                        events = json.loads(content)
                except (json.JSONDecodeError, Exception):
                    # If file is corrupted, start fresh
                    events = []

            # Append new event
            events.append(event)

            # Write back to file
            WEBHOOK_EVENTS_FILE.write_text(
                json.dumps(events, indent=2, default=str)
            )
    except Exception as exc:
        logger.warning("No se pudo guardar evento del webhook: %s", exc)


@router.post("/v1/webhooks/flights/push")
async def receive_push_notification(
    request: Request,
    trip_id: str | None = Query(None, description="Trip ID from subscription (optional)"),
    date: str | None = Query(None, description="Date from subscription"),
):
    """
    Receive push notification from AeroDataBox and fan it out to WebSocket listeners.

    Trip ID is now optional; if it is missing we fall back to the flight number
    for routing the message to Redis/WS subscribers.
    """
    if not is_valid_aerodatabox_request(request):
        raise HTTPException(403, "Forbidden")

    try:
        payload = await request.json()
    except Exception:
        await save_webhook_event(
            payload={},
            trip_id=trip_id or "",
            date=date,
            processed_status=None,
            tracking_active=False,
            note="invalid json payload",
        )
        raise HTTPException(400, "Invalid JSON payload")

    # Normalize payload from AeroDataBox
    notification: PushNotification = parse_aerodatabox_notification(payload)
    target_trip_id = trip_id or notification.flight_number or "unknown"

    try:
        cache = await get_tracking_cache()
        await cache.publish_push_notification(notification, target_trip_id)
    except Exception as exc:
        await save_webhook_event(
            payload=payload,
            trip_id=target_trip_id,
            date=date,
            processed_status=notification.status,
            tracking_active=False,
            error=str(exc),
        )
        raise

    # Save event to JSON file for debugging/traceability
    await save_webhook_event(
        payload=payload,
        trip_id=target_trip_id,
        date=date,
        processed_status=notification.status,
        tracking_active=False,
        note="forwarded to ws",
    )

    return JSONResponse({
        "status": "ok",
        "flight_number": notification.flight_number,
        "trip_id": target_trip_id,
        "flight_status": notification.status,
    })


@router.get("/v1/webhooks/flights/push/health")
async def webhook_health():
    """Health check for webhook endpoint."""
    return {"status": "ok", "timestamp": utcnow().isoformat()}
