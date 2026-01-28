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

class AssignUnassignDriverToTrip(BaseModel):
    driver_id: UUID
