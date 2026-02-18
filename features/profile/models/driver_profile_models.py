"""
Driver Profile Models - Pydantic models for driver profile endpoint.
"""

from typing import Optional, List
from pydantic import BaseModel, Field


class DriverLocationInfo(BaseModel):
    """Location assigned to the driver."""
    id: str
    name: str
    address: Optional[str] = None
    timezone: str = "America/New_York"


class DriverProfileResponse(BaseModel):
    """
    Complete driver profile response.
    Combines data from: users, drivers, organizations, locations.
    """
    # User data
    id: str = Field(..., description="UUID del driver")
    first_name: Optional[str] = Field(None)
    last_name: Optional[str] = Field(None)
    email: str = Field(...)
    phone: Optional[str] = Field(None)
    profile_pic: Optional[str] = Field(None)
    created_at: str = Field(...)

    # Driver data
    is_active: bool = Field(...)
    pay_type: Optional[str] = Field(None, description="day, hour, trip")
    pay_frequency: Optional[str] = Field(None, description="daily, weekly, biweekly")
    rate: Optional[float] = Field(None)

    # Schedule data
    shift_start_time: Optional[str] = Field(None, description="Scheduled shift start time (HH:MM)")
    shift_end_time: Optional[str] = Field(None, description="Scheduled shift end time (HH:MM)")
    work_days: Optional[List[str]] = Field(None, description="Days of week driver works, e.g. ['mon','tue']")

    # Location data
    location: Optional[DriverLocationInfo] = Field(None)

    # Organization data
    organization_id: Optional[str] = Field(None)
    organization_name: Optional[str] = Field(None)
