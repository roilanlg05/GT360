from pydantic import BaseModel, Field, field_validator
from datetime import time, datetime
from typing import Optional
from uuid import UUID
from enum import Enum


class RoundingMode(str, Enum):
    """Rounding mode for time calculations."""
    MULTIPLE_OF_5 = "multiple_of_5"  # Round to 5-minute multiples: 10:15, 1:25 (default)
    ODD_MINUTES = "odd_minutes"      # Keep odd minutes, no rounding: 2:11, 5:27


class TimeRange(BaseModel):
    """Time range for filtering trips by pickup time window."""
    start: time  # e.g., 05:00
    end: time    # e.g., 10:00

    @field_validator('end')
    @classmethod
    def validate_range(cls, v, info):
        # Allow midnight crossing (e.g., 22:00 - 02:00)
        return v


class ReduceFilterConfig(BaseModel):
    """Configuration for Lead Time Reduction filter."""
    enabled: bool = False
    minutes_to_reduce: int = Field(default=0, ge=0, le=120)
    hotel_names: Optional[list[str]] = None  # None = ALL
    time_range: Optional[TimeRange] = None   # None = ALL


class CombineFilterConfig(BaseModel):
    """Configuration for Combine (contract) filter."""
    enabled: bool = False
    min_gap: int = Field(ge=1, le=60)   # e.g., 15
    max_gap: int = Field(ge=1, le=120)  # e.g., 20
    hotel_names: Optional[list[str]] = None
    time_range: Optional[TimeRange] = None

    @field_validator('max_gap')
    @classmethod
    def validate_gap_range(cls, v, info):
        min_gap = info.data.get('min_gap')
        if min_gap is not None and v < min_gap:
            raise ValueError('max_gap must be >= min_gap')
        return v


class ExpandFilterConfig(BaseModel):
    """Configuration for Expand filter."""
    enabled: bool = False
    min_gap: int = Field(ge=1, le=60)    # e.g., 21
    max_gap: int = Field(ge=1, le=120)   # e.g., 30
    max_shift: int = Field(ge=1, le=30)  # max minutes to shift per trip
    hotel_names: Optional[list[str]] = None
    time_range: Optional[TimeRange] = None
    # Note: Distribution is fixed at 1/3 earlier, 2/3 later

    @field_validator('max_gap')
    @classmethod
    def validate_gap_range(cls, v, info):
        min_gap = info.data.get('min_gap')
        if min_gap is not None and v < min_gap:
            raise ValueError('max_gap must be >= min_gap')
        return v


class FilterRequest(BaseModel):
    """Request model for applying filters."""
    pick_up_date_from: Optional[str] = None  # "YYYY-MM-DD" - filters trips >= this date
    pick_up_date_to: Optional[str] = None    # "YYYY-MM-DD" - filters trips <= this date
    rounding_mode: RoundingMode = RoundingMode.MULTIPLE_OF_5  # Time rounding mode
    reduce: Optional[ReduceFilterConfig] = None
    combine: Optional[CombineFilterConfig] = None
    expand: Optional[ExpandFilterConfig] = None


class TripChange(BaseModel):
    """Represents a single trip modification."""
    trip_id: UUID
    original_time: time
    new_time: time
    filter_applied: str  # "reduce", "combine", "expand"
    hotel_name: str
    pick_up_date: Optional[str] = None
    airline: Optional[str] = None

    model_config = {"from_attributes": True}


class FilterExclusion(BaseModel):
    """Represents an operation that was excluded due to collision."""
    operation: str       # e.g., "expand(A,B)"
    trip_ids: list[UUID]
    reason: str
    gap_before: int
    gap_after: int


class FilterPreviewResult(BaseModel):
    """Result of filter preview (simulation without applying)."""
    location_id: UUID
    airline: str
    changes: list[TripChange]
    exclusions: list[FilterExclusion]
    summary: dict  # {"reduce": 5, "combine": 10, "expand": 3, "excluded": 2}
    total_trips_evaluated: int
    eligible_trips: int


class FilterApplyResult(BaseModel):
    """Result of applying filters."""
    batch_id: UUID
    location_id: UUID
    airline: str
    changes_applied: int
    exclusions: list[FilterExclusion]
    log: list[dict]
    summary: dict


class FilterRevertResult(BaseModel):
    """Result of reverting filters."""
    trips_reverted: int
    batch_ids_reverted: list[UUID]


class FilterRevertPartialResult(BaseModel):
    """Result of partial filter revert (reverting specific filter types)."""
    batch_id: UUID
    filter_reverted: str  # "reduce", "combine", or "expand"
    trips_affected: int
    filters_reapplied: list[str]  # Remaining filters that were re-applied
    changes_applied: int  # Number of changes after re-application
    summary: dict  # Summary of changes after re-application
