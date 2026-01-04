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
    flight_number: str
    riders: dict[str, int]
    location_id: Optional[UUID] = None

class TripUpdate(BaseModel):
    pick_up_date: Optional[date] = None
    pick_up_time: Optional[time] = None
    pick_up_location: Optional[str] = None
    drop_off_location: Optional[str] = None
    airline: Optional[str] = None
    flight_number: Optional[str] = None
    riders: Optional[dict[str, int]] = None

class CreateTrip(BaseModel):
    pick_up_date: date
    pick_up_time: time
    pick_up_location: str
    drop_off_location: str
    assigned_driver: Optional[UUID] = None
    airline: str
    flight_number: str
    riders: dict[str, int]


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
    started_at: Optional[datetime] = None
    picked_up_at: Optional[datetime] = None
    dropped_off_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # Pydantic v2:
    model_config = {"from_attributes": True}

class AssignUnassignDriverToTrip(BaseModel):
    driver_id: UUID
