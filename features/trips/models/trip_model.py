from pydantic import BaseModel
from datetime import date, time, datetime
from typing import Optional
from uuid import UUID


class Trip(BaseModel):
    pick_up_date: date
    pick_up_time: time
    pick_up_location: str
    drop_off_location: str
    airline: str
    trip_hash: str
    flight_number: str
    riders: dict[str, int]
    trip_type: Optional[str] = None
    location_id: Optional[UUID] = None

class TripUpdate(BaseModel):
    assigned_driver: Optional[UUID] = None
    pick_up_date: Optional[date] = None
    pick_up_time: Optional[time] = None
    pick_up_location: Optional[str] = None
    drop_off_location: Optional[str] = None
    airline: Optional[str] = None
    flight_number: Optional[str] = None
    riders: Optional[dict[str, int]] = None
    trip_type: Optional[str] = None
    started_at: Optional[datetime] = None
    picked_up_at: Optional[datetime] = None
    dropped_off_at: Optional[datetime] = None

class CreateTrip(BaseModel):
    pick_up_date: date
    pick_up_time: time
    pick_up_location: str
    drop_off_location: str
    assigned_driver: Optional[UUID] = None
    airline: str
    flight_number: str
    riders: dict[str, int]
    trip_type: Optional[str] = None


class TripResponse(BaseModel):
    id: UUID
    assigned_driver: Optional[UUID] = None
    location_id: UUID
    pick_up_date: date
    pick_up_time: time
    pick_up_location: str
    drop_off_location: str
    airline: str
    flight_number: str
    riders: Optional[dict[str, int]] = None
    trip_type: Optional[str] = None
    started_at: Optional[datetime] = None
    picked_up_at: Optional[datetime] = None
    dropped_off_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # Ground Filters V2 - Step-based tracking
    original_pick_up_time: Optional[time] = None
    reduce_applied: bool = False
    combine_applied: bool = False
    expand_applied: bool = False
    filtered_at: Optional[datetime] = None
    current_step_id: Optional[UUID] = None

    # Trip status
    status: Optional[str] = None

    # Pydantic v2:
    model_config = {"from_attributes": True}


class TripSearchResult(BaseModel):
    """Trip con información de location para búsqueda organizacional."""
    id: UUID
    assigned_driver: Optional[UUID] = None
    location_id: UUID
    location_name: str
    pick_up_date: date
    pick_up_time: time
    pick_up_location: str
    drop_off_location: str
    airline: str
    flight_number: str
    trip_type: Optional[str] = None
    status: Optional[str] = None

    # Riders breakdown (pilots, flight_attendants, etc.)
    riders: Optional[dict[str, int]] = None

    # Filter information
    original_pick_up_time: Optional[time] = None
    reduce_applied: bool = False
    combine_applied: bool = False
    expand_applied: bool = False
    filtered_at: Optional[datetime] = None
    current_step_id: Optional[UUID] = None

    # Timestamps
    started_at: Optional[datetime] = None
    picked_up_at: Optional[datetime] = None
    dropped_off_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class TripSearchResponse(BaseModel):
    """Respuesta paginada para búsqueda de trips."""
    trips: list[TripSearchResult]
    total: int
    limit: int
    skip: int


class AssignUnassignDriverToTrip(BaseModel):
    driver_id: UUID


class LocationDetails(BaseModel):
    """Detalles de location para endpoint de trip details."""
    id: UUID
    name: str
    timezone: str
    address: Optional[str] = None
    coordinates: Optional[dict] = None  # GeoJSON Point
    radio_zone: Optional[float] = None
    validation_status: str
    provider: Optional[str] = None
    model_config = {"from_attributes": True}


class DriverDetails(BaseModel):
    """Detalles de driver incluyendo info de User."""
    id: UUID
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: str
    phone: Optional[str] = None
    pay_type: Optional[str] = None
    is_active: bool
    current_location: Optional[dict] = None  # GeoJSON Point del GPS
    model_config = {"from_attributes": True}


class FilterStepDetails(BaseModel):
    """Detalles del filter step aplicado."""
    id: UUID
    filter_type: str  # reduce/combine/expand
    step_order: int
    config: dict
    windows: list[dict]
    trips_affected: int
    created_at: datetime
    is_active: bool
    model_config = {"from_attributes": True}


class HotelDetails(BaseModel):
    """Detalles de hotel para pickup/dropoff."""
    id: UUID
    name: str
    address: Optional[str] = None
    coordinates: Optional[dict] = None  # GeoJSON Point
    radio_zone: Optional[float] = None
    validation_status: str
    model_config = {"from_attributes": True}


class TripDetailedResponse(BaseModel):
    """Respuesta completa con trip y todos los datos relacionados."""
    trip: dict  # Serializado con model_dump_with_time_format
    location: LocationDetails
    driver: Optional[DriverDetails] = None
    filter_step: Optional[FilterStepDetails] = None
    pickup_hotel: Optional[HotelDetails] = None
    dropoff_hotel: Optional[HotelDetails] = None


class PickUpTripRequest(BaseModel):
    """Request para marcar pickup de un trip validando ubicacion del driver."""
    driver_id: UUID
    driver_location: dict  # GeoJSON Point: {"type": "Point", "coordinates": [lon, lat]}
    pickup_location: dict  # GeoJSON Point del hotel/aeropuerto
    radio_zone: float  # Radio en millas


class StartTripRequest(BaseModel):
    """Request para iniciar un trip."""
    driver_id: Optional[UUID] = None  # Opcional para validacion futura


class DropOffTripRequest(BaseModel):
    """Request para marcar drop off de un trip validando ubicacion del driver."""
    driver_id: UUID
    driver_location: dict  # GeoJSON Point: {"type": "Point", "coordinates": [lon, lat]}
    dropoff_location: dict  # GeoJSON Point del hotel/aeropuerto destino
    radio_zone: float  # Radio en millas
