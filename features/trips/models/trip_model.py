from pydantic import BaseModel
from datetime import date, time
from typing import Dict, Optional


class Trip(BaseModel):
    pick_up_date: date
    pick_up_time: time
    pick_up_location: str
    drop_off_location: str
    airline: str
    flight_number: str
    riders: Dict[str, int]
    location_id: Optional[str] = None

class TripUpdate(BaseModel):
    pick_up_date: Optional[date] = None
    pick_up_time: Optional[time] = None
    pick_up_location: Optional[str] = None
    drop_off_location: Optional[str] = None
    airline: Optional[str] = None
    flight_number: Optional[str] = None
    riders: Optional[Dict[str, int]] = None

class CreateTrip(BaseModel):
    pick_up_date: date
    pick_up_time: time
    pick_up_location: str
    drop_off_location: str
    asigned_to: str
    airline: str
    flight_number: str
    riders: dict[str, int]
