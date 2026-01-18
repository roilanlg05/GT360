"""
Models for real-time flight tracking and push notifications.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class FlightStatus(str, Enum):
    """Flight status values."""
    SCHEDULED = "Scheduled"
    BOARDING = "Boarding"
    DEPARTED = "Departed"
    EN_ROUTE = "EnRoute"
    LANDED = "Landed"
    ARRIVED = "Arrived"
    CANCELED = "Canceled"
    DIVERTED = "Diverted"
    UNKNOWN = "Unknown"


class TrackingInterval(str, Enum):
    """Tracking interval based on ETA."""
    REAL_TIME = "real_time"      # <10 min: every 1 second
    VERY_CLOSE = "very_close"    # 10-20 min: every 1 minute
    CLOSE = "close"              # 20-30 min: every 2.5 minutes
    MEDIUM = "medium"            # 30-60 min: every 5 minutes
    FAR = "far"                  # >60 min: every 20 minutes


# =============================================================================
# Subscription Models
# =============================================================================

class FlightToSubscribe(BaseModel):
    """Single flight to subscribe for tracking."""
    flight_number: str
    trip_id: str
    date_local: str  # YYYY-MM-DD


class SubscribeRequest(BaseModel):
    """Request to subscribe multiple flights for tracking."""
    flights: List[FlightToSubscribe]


class FlightSubscription(BaseModel):
    """Active flight subscription."""
    flight_number: str
    trip_id: str
    date_local: str
    subscription_id: Optional[str] = None  # AeroDataBox subscription ID
    status: str = "pending"  # pending, active, expired, error
    created_at: str
    expires_at: Optional[str] = None


class SubscribeResponse(BaseModel):
    """Response after subscribing flights."""
    subscribed: List[FlightSubscription]
    failed: List[dict] = Field(default_factory=list)
    total: int
    success_count: int
    failure_count: int


# =============================================================================
# Position Models (ADSB.lol)
# =============================================================================

class AircraftPosition(BaseModel):
    """Aircraft position from ADSB.lol."""
    hex: Optional[str] = None  # ICAO hex code
    flight: Optional[str] = None  # Callsign/flight number
    lat: Optional[float] = None
    lon: Optional[float] = None
    alt_baro: Optional[int] = None  # Barometric altitude (feet)
    alt_geom: Optional[int] = None  # Geometric altitude (feet)
    gs: Optional[float] = None  # Ground speed (knots)
    track: Optional[float] = None  # Track angle (degrees)
    baro_rate: Optional[int] = None  # Vertical rate (feet/min)
    squawk: Optional[str] = None
    category: Optional[str] = None  # Aircraft category
    nav_heading: Optional[float] = None
    seen: Optional[float] = None  # Seconds since last message
    seen_pos: Optional[float] = None  # Seconds since last position


class FlightPosition(BaseModel):
    """Processed flight position for frontend."""
    flight_number: str
    trip_id: str

    # Position
    lat: float
    lon: float
    altitude: Optional[int] = None  # feet
    ground_speed: Optional[float] = None  # knots
    heading: Optional[float] = None  # degrees
    vertical_rate: Optional[int] = None  # feet/min

    # Airports
    origin_icao: Optional[str] = None
    origin_iata: Optional[str] = None
    destination_icao: Optional[str] = None
    destination_iata: Optional[str] = None

    # ETA calculation
    distance_to_destination_nm: Optional[float] = None  # nautical miles
    eta_utc: Optional[str] = None
    minutes_to_arrival: Optional[int] = None

    # Tracking info
    tracking_interval: TrackingInterval
    interval_seconds: float

    # Timestamps
    position_time: str  # When position was reported
    cached_at: str
    cache_ttl_seconds: int = 2


class FlightTrackingState(BaseModel):
    """Current tracking state for a flight."""
    flight_number: str
    trip_id: str
    date_local: str

    # Status
    status: FlightStatus = FlightStatus.UNKNOWN
    is_tracking_active: bool = False

    # Last known position
    last_position: Optional[FlightPosition] = None

    # Tracking config
    current_interval: TrackingInterval = TrackingInterval.FAR
    interval_seconds: float = 1200  # 20 minutes default

    # Subscription
    subscription_id: Optional[str] = None
    subscription_status: str = "pending"


# =============================================================================
# Push Notification Models (AeroDataBox Webhook)
# =============================================================================

class PushNotification(BaseModel):
    """Push notification received from AeroDataBox webhook."""
    # Flight identification
    flight_number: Optional[str] = None
    flight_iata: Optional[str] = None
    flight_icao: Optional[str] = None

    # Status
    status: Optional[str] = None

    # Departure
    departure_airport: Optional[str] = None
    departure_scheduled: Optional[str] = None
    departure_estimated: Optional[str] = None
    departure_actual: Optional[str] = None

    # Arrival
    arrival_airport: Optional[str] = None
    arrival_scheduled: Optional[str] = None
    arrival_estimated: Optional[str] = None
    arrival_actual: Optional[str] = None

    # Raw payload
    raw: Optional[Dict[str, Any]] = None

    # Metadata
    received_at: str


# =============================================================================
# Airport Models
# =============================================================================

class Airport(BaseModel):
    """Airport information."""
    icao: str
    iata: Optional[str] = None
    name: Optional[str] = None
    lat: float
    lon: float


class AirportPair(BaseModel):
    """Origin and destination airports."""
    origin: Airport
    destination: Airport
