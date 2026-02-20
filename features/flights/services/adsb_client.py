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
import re
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
AIRLABS_BASE_URL = "https://airlabs.co/api/v9"

# In-memory cache for IATA → ICAO airline code (static data, never changes)
_airline_icao_cache: Dict[str, str] = {}


def _extract_iata_prefix(flight_number: str) -> Optional[str]:
    """
    Extract the IATA airline prefix from a flight number.
    e.g. "WN2105" → "WN", "AA567" → "AA"
    Returns None if it looks like it's already an ICAO prefix (3 letters).
    """
    match = re.match(r'^([A-Z]{2})\d', flight_number.upper())
    return match.group(1) if match else None


async def get_icao_callsign(flight_number: str, http: httpx.AsyncClient) -> str:
    """
    Convert a flight number with IATA airline prefix to ICAO callsign.

    e.g. "WN2105" → "SWA2105"

    Calls Airlabs API to get the ICAO code for the airline, then substitutes
    the 2-letter IATA prefix with the 3-letter ICAO prefix.
    Falls back to the original flight number if conversion fails.
    """
    from shared.settings import settings

    iata_prefix = _extract_iata_prefix(flight_number)
    if not iata_prefix:
        # Already 3-letter prefix or unrecognized format — use as-is
        return flight_number

    # Check in-memory cache first
    if iata_prefix in _airline_icao_cache:
        icao_code = _airline_icao_cache[iata_prefix]
        callsign = icao_code + flight_number[len(iata_prefix):]
        print(f"[AIRLABS] Cache hit: {flight_number} → {callsign}")
        return callsign

    api_key = settings.AIRLABS_API_KEY
    if not api_key:
        print(f"[AIRLABS] No API key configured, using flight number as-is: {flight_number}")
        return flight_number

    try:
        response = await http.get(
            f"{AIRLABS_BASE_URL}/airlines",
            params={"iata_code": iata_prefix, "api_key": api_key},
            timeout=5,
        )
        data = response.json()
        airlines = data.get("response", [])

        if not airlines:
            print(f"[AIRLABS] No airline found for IATA code '{iata_prefix}', using as-is")
            return flight_number

        icao_code = airlines[0].get("icao_code", "").strip().upper()
        if not icao_code:
            print(f"[AIRLABS] Airline found but no ICAO code for '{iata_prefix}'")
            return flight_number

        _airline_icao_cache[iata_prefix] = icao_code
        callsign = icao_code + flight_number[len(iata_prefix):]
        print(f"[AIRLABS] Converted: {flight_number} → {callsign} ({iata_prefix} → {icao_code})")
        return callsign

    except Exception as e:
        print(f"[AIRLABS] Error converting '{iata_prefix}' to ICAO: {type(e).__name__}: {e}")
        return flight_number


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


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate initial bearing from point 1 to point 2 (degrees, 0-360).
    Used to compare against aircraft heading to detect routing deviation.
    """
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlon_r = math.radians(lon2 - lon1)

    x = math.sin(dlon_r) * math.cos(lat2_r)
    y = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlon_r)

    return (math.degrees(math.atan2(x, y)) + 360) % 360


def calculate_eta_minutes(
    distance_nm: float,
    ground_speed_knots: float,
    heading: Optional[float] = None,
    bearing_to_dest: Optional[float] = None,
    altitude_ft: Optional[float] = None,
) -> Optional[int]:
    """
    Calculate ETA with three-factor correction:

    1. HEADING DEVIATION — if the aircraft isn't pointing toward the destination,
       the actual path is longer than the straight-line distance. A 45° deviation
       adds ~21%, a 90° deviation adds ~30%.

    2. AIRWAY ROUTE FACTOR — actual airways are 8-12% longer than great circle
       distance at cruise altitude, less during descent.

    3. SPEED REDUCTION — aircraft slow from cruise speed (~450 kts) to approach
       speed (~170 kts) before landing. Using cruise speed for the entire remaining
       distance causes significant underestimation. We model the last ~30nm at
       a realistic approach speed.
    """
    if ground_speed_knots <= 0:
        return None

    corrected_distance = distance_nm

    # --- Factor 1: Heading deviation ---
    if heading is not None and bearing_to_dest is not None:
        heading_diff = abs((heading - bearing_to_dest + 180) % 360 - 180)
        # sin(0°)=0 (on course), sin(90°)=1 (perpendicular), weight 0.30
        heading_factor = 1.0 + math.sin(math.radians(heading_diff)) * 0.30
        corrected_distance *= heading_factor
        print(f"[ETA] heading={heading:.0f}° bearing={bearing_to_dest:.0f}° diff={heading_diff:.0f}° → heading_factor={heading_factor:.3f}")

    # --- Factor 2: Airway route factor ---
    if altitude_ft is not None and altitude_ft > 20000:
        route_factor = 1.12   # En-route: airways add ~12%
    elif altitude_ft is not None and altitude_ft > 8000:
        route_factor = 1.06   # Descending: more direct
    else:
        route_factor = 1.02   # On approach: nearly direct
    corrected_distance *= route_factor

    print(f"[ETA] straight={distance_nm:.1f}nm corrected={corrected_distance:.1f}nm alt={altitude_ft} route_factor={route_factor}")

    # --- Factor 3: Speed reduction for descent/approach ---
    # Model: last APPROACH_DIST nm are flown at APPROACH_SPEED regardless of current GS.
    # Rest is flown at current GS (already includes factor 1 & 2 corrections).
    APPROACH_DIST_NM = 30     # nm of approach phase at reduced speed
    APPROACH_SPEED_KTS = 170  # average kts from 30nm to touchdown

    if altitude_ft is not None and altitude_ft > 25000:
        # Still in cruise — will spend significant time slowing for approach
        if corrected_distance > APPROACH_DIST_NM:
            time_hours = (
                (corrected_distance - APPROACH_DIST_NM) / ground_speed_knots
                + APPROACH_DIST_NM / APPROACH_SPEED_KTS
            )
        else:
            time_hours = corrected_distance / APPROACH_SPEED_KTS

    elif altitude_ft is not None and altitude_ft > 10000:
        # Descending — already slowing, use 90% of current GS for cruise portion
        approach_portion = min(APPROACH_DIST_NM, corrected_distance * 0.40)
        cruise_portion = corrected_distance - approach_portion
        time_hours = (
            cruise_portion / (ground_speed_knots * 0.90)
            + approach_portion / APPROACH_SPEED_KTS
        )

    else:
        # On approach or altitude unknown — use current speed directly
        time_hours = corrected_distance / ground_speed_knots

    eta = int(time_hours * 60)
    print(f"[ETA] gs={ground_speed_knots:.0f}kts → ETA={eta}min")
    return eta


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

        Accepts IATA flight numbers (e.g., "WN2105") and converts them to
        ICAO callsigns (e.g., "SWA2105") via Airlabs before querying ADSB.lol.

        Args:
            callsign: Flight number in IATA or ICAO format

        Returns:
            AircraftPosition if found, None otherwise
        """
        http = await self._get_http()

        # Normalize (remove spaces, uppercase)
        callsign = callsign.strip().upper().replace(" ", "")

        # Convert IATA prefix to ICAO callsign (e.g. WN2105 → SWA2105)
        icao_callsign = await get_icao_callsign(callsign, http)

        url = f"{ADSB_BASE_URL}/v2/callsign/{icao_callsign}"

        try:
            response = await http.get(url)
            print(f"[ADSB] GET {url} → {response.status_code}")

            if response.status_code == 404:
                print(f"[ADSB] 404 - callsign '{callsign}' not found in ADSB.lol")
                return None
            response.raise_for_status()

            data = response.json()
            aircraft_list = data.get("ac", [])

            print(f"[ADSB] callsign '{callsign}' → {len(aircraft_list)} aircraft found")

            if not aircraft_list:
                print(f"[ADSB] No aircraft in air for callsign '{callsign}' (flight may be on ground)")
                return None

            # Get the first matching aircraft
            ac = aircraft_list[0]
            print(f"[ADSB] Aircraft: hex={ac.get('hex')} flight={ac.get('flight')} lat={ac.get('lat')} lon={ac.get('lon')} alt={ac.get('alt_baro')} gs={ac.get('gs')}")

            # alt_baro can be the string "ground" — coerce to None in that case
            alt_baro_raw = ac.get("alt_baro")
            alt_baro = alt_baro_raw if isinstance(alt_baro_raw, (int, float)) else None

            return AircraftPosition(
                hex=ac.get("hex"),
                flight=ac.get("flight", "").strip(),
                lat=ac.get("lat"),
                lon=ac.get("lon"),
                alt_baro=alt_baro,
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

        except httpx.HTTPStatusError as e:
            print(f"[ADSB] HTTP error for '{callsign}': {e.response.status_code} - {e.response.text[:200]}")
            return None
        except Exception as e:
            print(f"[ADSB] Exception fetching '{callsign}': {type(e).__name__}: {e}")
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

    async def get_routeset(
        self,
        icao_callsign: str,
        lat: float,
        lon: float,
    ) -> Optional[dict]:
        """
        Get route information for an aircraft using ADSB.lol /api/0/routeset.

        Returns origin and destination airports (with coords) so we don't need
        separate /api/0/airport/ calls.

        Args:
            icao_callsign: ICAO callsign (e.g. "SWA2105")
            lat: Current aircraft latitude
            lon: Current aircraft longitude

        Returns:
            Route dict with _airports list, or None if not found
        """
        http = await self._get_http()

        try:
            response = await http.post(
                f"{ADSB_BASE_URL}/api/0/routeset",
                json={"planes": [{"callsign": icao_callsign, "lat": lat, "lng": lon}]},
                timeout=5,
            )
            response.raise_for_status()
            data = response.json()

            if not isinstance(data, list) or not data:
                print(f"[ADSB] Routeset empty for '{icao_callsign}'")
                return None

            # Prefer plausible routes
            plausible = [r for r in data if r.get("plausible", 0) == 1]
            route = (plausible or data)[0]

            airports = route.get("_airports", [])
            print(f"[ADSB] Routeset '{icao_callsign}': {route.get('airport_codes')} (plausible={route.get('plausible')}, airports={len(airports)})")
            return route

        except Exception as e:
            print(f"[ADSB] Routeset error for '{icao_callsign}': {type(e).__name__}: {e}")
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

        Flow:
          1. Convert IATA flight number to ICAO callsign via Airlabs
          2. Fetch aircraft position from ADSB.lol /v2/callsign/
          3. Fetch route from ADSB.lol /api/0/routeset → auto-detects origin/destination
             with coords (no separate /api/0/airport/ calls needed)
          4. Calculate haversine distance + ETA to destination
          5. Return FlightPosition with adaptive tracking interval

        Args:
            flight_number: IATA flight number (e.g. "WN2105")
            trip_id: Trip ID from your system
            origin_icao: Optional override for origin airport ICAO
            destination_icao: Optional override for destination airport ICAO

        Returns:
            FlightPosition with all calculated fields, or None if aircraft not found
        """
        http = await self._get_http()

        # Step 1: Convert IATA → ICAO callsign once (cached after first call per airline)
        callsign = flight_number.strip().upper().replace(" ", "")
        icao_callsign = await get_icao_callsign(callsign, http)

        # Step 2: Get live aircraft position
        aircraft = await self.get_aircraft_by_callsign(icao_callsign)
        if not aircraft or aircraft.lat is None or aircraft.lon is None:
            return None

        # Step 3: Resolve origin + destination airports with coordinates.
        #
        # Priority (most → least reliable):
        #   1. Explicit ICAO params supplied by the caller
        #   2. Trip DB lookup — authoritative, uses our own airports table
        #   3. ADSB.lol routeset — last resort (can be incorrect)
        origin: Optional[Airport] = None
        destination: Optional[Airport] = None

        if origin_icao:
            origin = await self.get_airport_info(origin_icao)
        if destination_icao:
            destination = await self.get_airport_info(destination_icao)

        # Fill any remaining gaps from the trip record in our DB
        if not origin or not destination:
            from features.flights.services.trip_resolver import get_trip_airports
            db_origin, db_destination = await get_trip_airports(trip_id)
            if not origin and db_origin:
                origin = db_origin
            if not destination and db_destination:
                destination = db_destination

        # Last resort: routeset (unreliable — only if both are still missing)
        if not destination:
            route = await self.get_routeset(icao_callsign, aircraft.lat, aircraft.lon)
            if route:
                airports = route.get("_airports", [])
                if not origin and len(airports) >= 1:
                    a = airports[0]
                    origin = Airport(
                        icao=a.get("icao", ""),
                        iata=a.get("iata"),
                        name=a.get("name"),
                        lat=a.get("lat", 0.0),
                        lon=a.get("lon", 0.0),
                    )
                if not destination and len(airports) >= 2:
                    a = airports[1]
                    destination = Airport(
                        icao=a.get("icao", ""),
                        iata=a.get("iata"),
                        name=a.get("name"),
                        lat=a.get("lat", 0.0),
                        lon=a.get("lon", 0.0),
                    )

        # Step 4: Calculate distance + ETA
        distance_nm = None
        eta_minutes = None

        if destination and destination.lat and destination.lon:
            distance_nm = haversine_distance(
                aircraft.lat, aircraft.lon,
                destination.lat, destination.lon,
            )
            if aircraft.gs and aircraft.gs > 0:
                bearing_to_dest = calculate_bearing(
                    aircraft.lat, aircraft.lon,
                    destination.lat, destination.lon,
                )
                altitude_ft = aircraft.alt_baro or aircraft.alt_geom
                eta_minutes = calculate_eta_minutes(
                    distance_nm,
                    aircraft.gs,
                    heading=aircraft.track,
                    bearing_to_dest=bearing_to_dest,
                    altitude_ft=altitude_ft,
                )

        # Step 5: Determine adaptive tracking interval
        interval_enum, interval_seconds = get_tracking_interval(eta_minutes)

        from datetime import timedelta
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
            eta_utc=(now.replace(second=0, microsecond=0) + timedelta(minutes=eta_minutes)).isoformat() if eta_minutes else None,
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
