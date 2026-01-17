from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Leg(BaseModel):
    """Represents a single leg/segment of a flight."""
    seq: int
    origin: Optional[str] = None
    destination: Optional[str] = None

    dep_scheduled_utc: Optional[str] = None
    dep_estimated_utc: Optional[str] = None
    dep_actual_utc: Optional[str] = None

    arr_scheduled_utc: Optional[str] = None
    arr_estimated_utc: Optional[str] = None
    arr_actual_utc: Optional[str] = None

    eta_utc: Optional[str] = None
    duration_seconds: Optional[int] = None
    status: Optional[str] = None
    provider_last_updated_utc: Optional[str] = None


class FlightSnapshot(BaseModel):
    """Complete flight status snapshot with all available data."""
    flight_number: str
    date_local: str

    status: Optional[str] = None
    eta_utc: Optional[str] = None
    minutes_to_arrival: Optional[int] = None
    duration_seconds: Optional[int] = None

    # Position is optional (depends on provider availability / subscription / coverage)
    position: Optional[Dict[str, Any]] = None

    # Legs derived from multiple returned items for same flight_number/date
    legs: List[Leg] = Field(default_factory=list)

    provider_last_updated_utc: Optional[str] = None
    cached_at_utc: str
    cache_ttl_seconds: int

    # Recommended WebSocket polling interval (adaptive based on status/proximity)
    ws_interval_seconds: float = 1.0


class EtaOnly(BaseModel):
    """Minimal response with only ETA information."""
    flight_number: str
    date_local: str
    status: Optional[str] = None
    eta_utc: Optional[str] = None
    minutes_to_arrival: Optional[int] = None
    provider_last_updated_utc: Optional[str] = None
    cached_at_utc: str
    cache_ttl_seconds: int


class BatchFlightRequest(BaseModel):
    """Request for batch flight tracking."""
    flights: List[dict]  # [{"flight_number": "WN1234", "date_local": "2026-01-16"}, ...]


class BatchFlightResponse(BaseModel):
    """Response for batch flight tracking."""
    flights: List[FlightSnapshot]
    total: int
    cached: int
    from_api: int


class MetricsResponse(BaseModel):
    """Response for metrics endpoint."""
    date: str
    cache_hits: int
    cache_misses: int
    api_calls: int
    api_errors: int
    rate_limited: int
    flights_not_found: int


class RateLimitResponse(BaseModel):
    """Response for rate limit status."""
    current: int
    limit: int
    remaining: int
