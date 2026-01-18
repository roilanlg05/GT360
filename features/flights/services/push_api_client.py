"""
AeroDataBox Push API Client - Manages flight subscriptions.

Uses the Push API to subscribe to flight status notifications via webhooks.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import httpx

from features.flights.models.tracking_models import FlightSubscription


# =============================================================================
# Config
# =============================================================================

AERODATABOX_BASE_URL = os.getenv("AERODATABOX_BASE_URL", "https://aerodatabox.p.rapidapi.com")
AERODATABOX_RAPIDAPI_KEY = os.getenv("AERODATABOX_RAPIDAPI_KEY", "")
AERODATABOX_RAPIDAPI_HOST = os.getenv("AERODATABOX_RAPIDAPI_HOST", "aerodatabox.p.rapidapi.com")

# Your webhook URL that AeroDataBox will call
WEBHOOK_URL = os.getenv("FLIGHT_WEBHOOK_URL", "")

# Subscription duration in hours (max 60 days = 1440 hours)
SUBSCRIPTION_DURATION_HOURS = int(os.getenv("FLIGHT_SUBSCRIPTION_HOURS", "24"))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PushAPIClient:
    """
    Client for AeroDataBox Push API.

    Manages webhook subscriptions for flight status notifications.
    """

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None):
        self._http = http_client
        self._owns_http = http_client is None

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=10, read=30, write=10, pool=10)
            )
        return self._http

    async def close(self) -> None:
        if self._owns_http and self._http:
            await self._http.aclose()
            self._http = None

    def _get_headers(self) -> Dict[str, str]:
        return {
            "X-RapidAPI-Key": AERODATABOX_RAPIDAPI_KEY,
            "X-RapidAPI-Host": AERODATABOX_RAPIDAPI_HOST,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def create_subscription(
        self,
        flight_number: str,
        date_local: str,
        trip_id: str,
    ) -> FlightSubscription:
        """
        Create a webhook subscription for a flight.

        Args:
            flight_number: Flight number (e.g., "WN1234")
            date_local: Local departure date (YYYY-MM-DD)
            trip_id: Your internal trip ID

        Returns:
            FlightSubscription with subscription details
        """
        if not AERODATABOX_RAPIDAPI_KEY:
            raise RuntimeError("Missing AERODATABOX_RAPIDAPI_KEY")

        if not WEBHOOK_URL:
            raise RuntimeError("Missing FLIGHT_WEBHOOK_URL - configure your webhook endpoint")

        http = await self._get_http()
        now = utcnow()

        # Normalize flight number
        flight_number = flight_number.strip().upper()

        # AeroDataBox uses flight number as subject
        # The format for subscription is: /subscriptions/webhook/flight/{flightNumber}
        url = f"{AERODATABOX_BASE_URL}/subscriptions/webhook/flight/{flight_number}"

        # Subscription payload
        # We include trip_id in metadata via the webhook URL query params
        webhook_url_with_params = f"{WEBHOOK_URL}?trip_id={trip_id}&date={date_local}"

        payload = {
            "url": webhook_url_with_params,
            "dateLocal": date_local,
            "expiresAfterHours": SUBSCRIPTION_DURATION_HOURS,
        }

        try:
            response = await http.post(
                url,
                headers=self._get_headers(),
                json=payload
            )
            response.raise_for_status()

            data = response.json()

            expires_at = now + timedelta(hours=SUBSCRIPTION_DURATION_HOURS)

            return FlightSubscription(
                flight_number=flight_number,
                trip_id=trip_id,
                date_local=date_local,
                subscription_id=data.get("subscriptionId") or data.get("id"),
                status="active",
                created_at=now.isoformat(),
                expires_at=expires_at.isoformat(),
            )

        except httpx.HTTPStatusError as e:
            error_detail = ""
            try:
                error_detail = e.response.text
            except Exception:
                pass

            return FlightSubscription(
                flight_number=flight_number,
                trip_id=trip_id,
                date_local=date_local,
                subscription_id=None,
                status=f"error: {e.response.status_code} - {error_detail[:100]}",
                created_at=now.isoformat(),
                expires_at=None,
            )

        except Exception as e:
            return FlightSubscription(
                flight_number=flight_number,
                trip_id=trip_id,
                date_local=date_local,
                subscription_id=None,
                status=f"error: {type(e).__name__}",
                created_at=now.isoformat(),
                expires_at=None,
            )

    async def refresh_subscription(
        self,
        flight_number: str,
    ) -> bool:
        """
        Refresh/extend an existing subscription.

        Args:
            flight_number: Flight number

        Returns:
            True if refresh successful, False otherwise
        """
        if not AERODATABOX_RAPIDAPI_KEY:
            return False

        http = await self._get_http()

        flight_number = flight_number.strip().upper()
        url = f"{AERODATABOX_BASE_URL}/subscriptions/webhook/flight/{flight_number}"

        try:
            response = await http.put(
                url,
                headers=self._get_headers()
            )
            return response.status_code in [200, 204]

        except Exception:
            return False

    async def delete_subscription(
        self,
        flight_number: str,
    ) -> bool:
        """
        Delete/cancel a subscription.

        Args:
            flight_number: Flight number

        Returns:
            True if deleted, False otherwise
        """
        if not AERODATABOX_RAPIDAPI_KEY:
            return False

        http = await self._get_http()

        flight_number = flight_number.strip().upper()
        url = f"{AERODATABOX_BASE_URL}/subscriptions/webhook/flight/{flight_number}"

        try:
            response = await http.delete(
                url,
                headers=self._get_headers()
            )
            return response.status_code in [200, 204]

        except Exception:
            return False

    async def get_subscription(
        self,
        flight_number: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get subscription details.

        Args:
            flight_number: Flight number

        Returns:
            Subscription data if exists, None otherwise
        """
        if not AERODATABOX_RAPIDAPI_KEY:
            return None

        http = await self._get_http()

        flight_number = flight_number.strip().upper()
        url = f"{AERODATABOX_BASE_URL}/subscriptions/webhook/flight/{flight_number}"

        try:
            response = await http.get(
                url,
                headers=self._get_headers()
            )

            if response.status_code == 404:
                return None

            response.raise_for_status()
            return response.json()

        except Exception:
            return None

    async def list_subscriptions(self) -> List[Dict[str, Any]]:
        """
        List all active subscriptions.

        Returns:
            List of subscription data
        """
        if not AERODATABOX_RAPIDAPI_KEY:
            return []

        http = await self._get_http()

        url = f"{AERODATABOX_BASE_URL}/subscriptions/webhook"

        try:
            response = await http.get(
                url,
                headers=self._get_headers()
            )
            response.raise_for_status()

            data = response.json()
            return data if isinstance(data, list) else []

        except Exception:
            return []

    async def create_subscriptions_batch(
        self,
        flights: List[Dict[str, str]],
    ) -> List[FlightSubscription]:
        """
        Create subscriptions for multiple flights.

        Args:
            flights: List of {"flight_number": str, "trip_id": str, "date_local": str}

        Returns:
            List of FlightSubscription results
        """
        results = []

        for flight in flights:
            subscription = await self.create_subscription(
                flight_number=flight["flight_number"],
                date_local=flight["date_local"],
                trip_id=flight["trip_id"],
            )
            results.append(subscription)

        return results


# =============================================================================
# Singleton
# =============================================================================

_push_client: Optional[PushAPIClient] = None


async def get_push_client() -> PushAPIClient:
    """Get or create singleton Push API client."""
    global _push_client
    if _push_client is None:
        _push_client = PushAPIClient()
    return _push_client
