"""
ADSB.lol Client - Fetches real-time aircraft positions.

API: https://api.adsb.lol
- Public API, no authentication required
- Returns ADS-B data from aircraft transponders
"""

from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from features.flights.models.tracking_models import (
    AircraftPosition,
    FlightPosition,
    TrackingInterval,
    Airport,
)


ADSB_BASE_URL = "https://api.adsb.lol"


def get_tracking_interval(minutes_to_arrival: Optional[int]) -> Tuple[TrackingInterval, float]:
    """
    Determine tracking interval based on ETA.

    Returns (interval_enum, seconds)
    """
    if minutes_to_arrival is None:
        return TrackingInterval.FAR, 1200  # 20 minutes

    if minutes_to_arrival <= 10:
        return TrackingInterval.REAL_TIME, 1  # 1 second
    elif minutes_to_arrival <= 20:
        return TrackingInterval.VERY_CLOSE, 60  # 1 minute
    elif minutes_to_arrival <= 30:
        return TrackingInterval.CLOSE, 150  # 2.5 minutes
    elif minutes_to_arrival <= 60:
        return TrackingInterval.MEDIUM, 300  # 5 minutes
    else:
        return TrackingInterval.FAR, 1200  # 20 minutes


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two points in nautical miles.
    """
    R = 3440.065  # Earth radius in nautical miles

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (math.sin(delta_lat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def calculate_eta_minutes(distance_nm: float, ground_speed_knots: float) -> Optional[int]:
    """Calculate ETA in minutes based on distance and speed."""
    if ground_speed_knots <= 0:
        return None
    hours = distance_nm / ground_speed_knots
    return int(hours * 60)


class ADSBClient:
    """
    Client for ADSB.lol API.

    Fetches real-time aircraft positions based on callsign or geographic search.
    """

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None):
        self._http = http_client
        self._owns_http = http_client is None

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=5, read=10, write=5, pool=5)
            )
        return self._http

    async def close(self) -> None:
        if self._owns_http and self._http:
            await self._http.aclose()
            self._http = None

    async def get_aircraft_by_callsign(self, callsign: str) -> Optional[AircraftPosition]:
        """
        Get aircraft position by callsign (flight number).

        Args:
            callsign: Flight callsign (e.g., "WN1234", "AAL567")

        Returns:
            AircraftPosition if found, None otherwise
        """
        http = await self._get_http()

        # Normalize callsign (remove spaces, uppercase)
        callsign = callsign.strip().upper().replace(" ", "")

        url = f"{ADSB_BASE_URL}/v2/callsign/{callsign}"

        try:
            response = await http.get(url)
            if response.status_code == 404:
                return None
            response.raise_for_status()

            data = response.json()
            aircraft_list = data.get("ac", [])

            if not aircraft_list:
                return None

            # Get the first matching aircraft
            ac = aircraft_list[0]

            return AircraftPosition(
                hex=ac.get("hex"),
                flight=ac.get("flight", "").strip(),
                lat=ac.get("lat"),
                lon=ac.get("lon"),
                alt_baro=ac.get("alt_baro"),
                alt_geom=ac.get("alt_geom"),
                gs=ac.get("gs"),
                track=ac.get("track"),
                baro_rate=ac.get("baro_rate"),
                squawk=ac.get("squawk"),
                category=ac.get("category"),
                nav_heading=ac.get("nav_heading"),
                seen=ac.get("seen"),
                seen_pos=ac.get("seen_pos"),
            )

        except httpx.HTTPStatusError:
            return None
        except Exception:
            return None

    async def get_aircraft_near_airport(
        self,
        icao: str,
        radius_nm: float = 50
    ) -> List[AircraftPosition]:
        """
        Get all aircraft near an airport.

        Args:
            icao: Airport ICAO code
            radius_nm: Search radius in nautical miles (default 50)

        Returns:
            List of aircraft positions
        """
        http = await self._get_http()

        # First get airport coordinates
        airport = await self.get_airport_info(icao)
        if not airport:
            return []

        # Search by coordinates
        url = f"{ADSB_BASE_URL}/v2/lat/{airport.lat}/lon/{airport.lon}/dist/{int(radius_nm)}"

        try:
            response = await http.get(url)
            response.raise_for_status()

            data = response.json()
            aircraft_list = data.get("ac", [])

            positions = []
            for ac in aircraft_list:
                if ac.get("lat") is not None and ac.get("lon") is not None:
                    positions.append(AircraftPosition(
                        hex=ac.get("hex"),
                        flight=ac.get("flight", "").strip() if ac.get("flight") else None,
                        lat=ac.get("lat"),
                        lon=ac.get("lon"),
                        alt_baro=ac.get("alt_baro"),
                        alt_geom=ac.get("alt_geom"),
                        gs=ac.get("gs"),
                        track=ac.get("track"),
                        baro_rate=ac.get("baro_rate"),
                        squawk=ac.get("squawk"),
                        category=ac.get("category"),
                        nav_heading=ac.get("nav_heading"),
                        seen=ac.get("seen"),
                        seen_pos=ac.get("seen_pos"),
                    ))

            return positions

        except Exception:
            return []

    async def get_airport_info(self, icao: str) -> Optional[Airport]:
        """
        Get airport information including coordinates.

        Args:
            icao: Airport ICAO code

        Returns:
            Airport with coordinates if found
        """
        http = await self._get_http()

        url = f"{ADSB_BASE_URL}/api/0/airport/{icao.upper()}"

        try:
            response = await http.get(url)
            if response.status_code == 404:
                return None
            response.raise_for_status()

            data = response.json()

            # Parse airport data
            return Airport(
                icao=data.get("icao", icao.upper()),
                iata=data.get("iata"),
                name=data.get("name"),
                lat=data.get("lat", 0),
                lon=data.get("lon", 0),
            )

        except Exception:
            return None

    async def get_flight_position(
        self,
        flight_number: str,
        trip_id: str,
        origin_icao: Optional[str] = None,
        destination_icao: Optional[str] = None,
    ) -> Optional[FlightPosition]:
        """
        Get processed flight position with ETA calculation.

        Args:
            flight_number: Flight number/callsign
            trip_id: Trip ID from your system
            origin_icao: Origin airport ICAO (optional, for context)
            destination_icao: Destination airport ICAO (for ETA calculation)

        Returns:
            FlightPosition with all calculated fields
        """
        # Get aircraft position
        aircraft = await self.get_aircraft_by_callsign(flight_number)
        if not aircraft or aircraft.lat is None or aircraft.lon is None:
            return None

        # Get destination airport for ETA calculation
        destination = None
        distance_nm = None
        eta_minutes = None

        if destination_icao:
            destination = await self.get_airport_info(destination_icao)
            if destination:
                distance_nm = haversine_distance(
                    aircraft.lat, aircraft.lon,
                    destination.lat, destination.lon
                )
                if aircraft.gs and aircraft.gs > 0:
                    eta_minutes = calculate_eta_minutes(distance_nm, aircraft.gs)

        # Get origin airport info
        origin = None
        if origin_icao:
            origin = await self.get_airport_info(origin_icao)

        # Determine tracking interval
        interval_enum, interval_seconds = get_tracking_interval(eta_minutes)

        now = datetime.now(timezone.utc)

        return FlightPosition(
            flight_number=flight_number,
            trip_id=trip_id,
            lat=aircraft.lat,
            lon=aircraft.lon,
            altitude=aircraft.alt_baro or aircraft.alt_geom,
            ground_speed=aircraft.gs,
            heading=aircraft.track or aircraft.nav_heading,
            vertical_rate=aircraft.baro_rate,
            origin_icao=origin.icao if origin else origin_icao,
            origin_iata=origin.iata if origin else None,
            destination_icao=destination.icao if destination else destination_icao,
            destination_iata=destination.iata if destination else None,
            distance_to_destination_nm=round(distance_nm, 1) if distance_nm else None,
            eta_utc=(now.replace(second=0, microsecond=0) +
                     __import__('datetime').timedelta(minutes=eta_minutes)).isoformat() if eta_minutes else None,
            minutes_to_arrival=eta_minutes,
            tracking_interval=interval_enum,
            interval_seconds=interval_seconds,
            position_time=now.isoformat(),
            cached_at=now.isoformat(),
            cache_ttl_seconds=2,
        )


# =============================================================================
# Singleton
# =============================================================================

_adsb_client: Optional[ADSBClient] = None


async def get_adsb_client() -> ADSBClient:
    """Get or create singleton ADSB client."""
    global _adsb_client
    if _adsb_client is None:
        _adsb_client = ADSBClient()
    return _adsb_client
