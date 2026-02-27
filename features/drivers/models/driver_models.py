from pydantic import BaseModel
from datetime import datetime, time
from typing import Optional, List
from decimal import Decimal
from enum import Enum


class PayTypeEnum(str, Enum):
    DAY = "day"
    HOUR = "hour"
    TRIP = "trip"


class PayFrequencyEnum(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"


class DriverResponse(BaseModel):
    """Response model for a single driver."""
    id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: str
    phone: Optional[str] = None
    profile_pic: Optional[str] = None
    is_active: bool
    pay_type: Optional[str] = None
    pay_frequency: Optional[str] = None
    rate: Optional[float] = None
    location_id: Optional[str] = None
    organization_id: Optional[str] = None
    shift_start_time: Optional[str] = None
    shift_end_time: Optional[str] = None
    work_days: Optional[List[str]] = None
    created_at: datetime


class DriverListResponse(BaseModel):
    """Response model for list of drivers."""
    drivers: list[DriverResponse]
    total: int

class DriverActiveUpdate(BaseModel):
    is_active: bool


class DriverStatusResponse(BaseModel):
    id: str
    is_active: bool


class DriverDetailsUpdate(BaseModel):
    location_id: Optional[str] = None
    pay_type: Optional[PayTypeEnum] = None
    pay_frequency: Optional[PayFrequencyEnum] = None
    rate: Optional[Decimal] = None
    is_active: Optional[bool] = None
    profile_pic_url: Optional[str] = None
    shift_start_time: Optional[time] = None
    shift_end_time: Optional[time] = None
    work_days: Optional[List[str]] = None


class DriverLocationSharingUpdate(BaseModel):
    driver_location_sharing: bool


class DriverLocationUpdate(BaseModel):
    lat: float
    lng: float