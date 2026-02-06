from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from enum import Enum


class PayTypeEnum(str, Enum):
    DAY = "day"
    HOUR = "hour"
    TRIP = "trip"


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
    location_id: Optional[str] = None
    organization_id: Optional[str] = None
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