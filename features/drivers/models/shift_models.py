from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict
from uuid import UUID


class StartShiftRequest(BaseModel):
    """Request to start a shift."""
    started_at: Optional[datetime] = Field(
        default=None,
        description="Shift start time (defaults to current time if not provided)"
    )


class EndShiftRequest(BaseModel):
    """Request to end a shift."""
    ended_at: Optional[datetime] = Field(
        default=None,
        description="Shift end time (defaults to current time if not provided)"
    )


class ShiftResponse(BaseModel):
    """Response model for a single shift."""
    shift_id: UUID
    driver_id: UUID
    started_at: datetime
    ended_at: Optional[datetime]
    duration_hours: Optional[float]
    status: str
    review_status: Optional[str]
    review_reason: Optional[str]
    reviewed_at: Optional[datetime]
    reviewed_by: Optional[UUID]
    manager_notes: Optional[str]
    auto_closed: bool
    crosses_midnight: bool
    trips_in_shift: int
    hours_distribution: Optional[Dict[str, float]] = Field(
        default=None,
        description="Hours worked per day if shift crosses midnight"
    )
    created_at: datetime


class ShiftListResponse(BaseModel):
    """Response model for list of shifts."""
    shifts: List[ShiftResponse]
    pagination: dict
    summary: dict


class ShiftStartResponse(BaseModel):
    """Response when shift is started."""
    status: str
    message: str
    shift: ShiftResponse


class ShiftEndResponse(BaseModel):
    """Response when shift is ended."""
    status: str
    message: str
    shift: ShiftResponse


# Manager models

class ResolveShiftRequest(BaseModel):
    """Manager request to resolve a shift under review."""
    action: str = Field(
        ...,
        description="Action to take: 'approve', 'reject', or 'adjust'"
    )
    manager_notes: Optional[str] = Field(
        default=None,
        description="Manager's notes about the resolution"
    )
    adjusted_ended_at: Optional[datetime] = Field(
        default=None,
        description="Adjusted end time (required if action='adjust')"
    )


class ResolveShiftResponse(BaseModel):
    """Response when shift review is resolved."""
    status: str
    message: str
    shift: ShiftResponse
