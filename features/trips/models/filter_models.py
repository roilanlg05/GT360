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


class DateRange(BaseModel):
    """Date range for filtering trips by pickup date."""
    date_from: Optional[str] = None  # "YYYY-MM-DD" - filters trips >= this date
    date_to: Optional[str] = None    # "YYYY-MM-DD" - filters trips <= this date


class ReduceFilterConfig(BaseModel):
    """Configuration for Lead Time Reduction filter."""
    enabled: bool = False
    minutes_to_reduce: int = Field(default=0, ge=0, le=120)
    hotel_names: Optional[list[str]] = None  # None = ALL
    time_range: Optional[TimeRange] = None   # None = ALL
    date_range: Optional[DateRange] = None   # None = ALL (filter-level date range)


class CombineFilterConfig(BaseModel):
    """Configuration for Combine (contract) filter."""
    enabled: bool = False
    min_gap: int = Field(ge=1, le=60)   # e.g., 15
    max_gap: int = Field(ge=1, le=120)  # e.g., 20
    hotel_names: Optional[list[str]] = None
    time_range: Optional[TimeRange] = None
    date_range: Optional[DateRange] = None   # None = ALL (filter-level date range)

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
    date_range: Optional[DateRange] = None   # None = ALL (filter-level date range)
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
    original_time: time | str  # time object or formatted string
    new_time: time | str  # time object or formatted string
    filter_applied: str  # "reduce", "combine", "expand"
    hotel_name: str
    pick_up_date: Optional[str] = None
    airline: Optional[str] = None
    flight_number: Optional[str] = None  # Necesario para mostrar en preview UI

    model_config = {"from_attributes": True}


class TripExclusionInfo(BaseModel):
    """Information about a trip involved in an exclusion."""
    trip_id: UUID
    airline: str
    flight_number: Optional[str] = None
    hotel_name: str
    pick_up_date: Optional[str] = None
    pick_up_time: Optional[str] = None  # Current pick up time (HH:MM or HH:MM:SS)
    original_pick_up_time: Optional[str] = None  # Original time before filters (if modified)


class FilterExclusion(BaseModel):
    """Represents an operation that was excluded due to collision."""
    operation: str       # e.g., "expand(A,B)"
    trip_ids: list[UUID]
    reason: str
    gap_before: int
    gap_after: int
    trips_info: list[TripExclusionInfo] = []  # Details of trips involved


class FilterPreviewResult(BaseModel):
    """Result of filter preview (simulation without applying)."""
    location_id: UUID
    airline: str
    changes: list[TripChange]
    exclusions: list[FilterExclusion]
    summary: dict  # {"reduce": 5, "combine": 10, "expand": 3, "excluded": 2}
    total_trips_evaluated: int
    eligible_trips: int


class FilterPreviewSaved(BaseModel):
    """Saved preview result retrieved from database.

    This model is used when retrieving a previously saved preview,
    allowing Device B to see the preview created on Device A.
    """
    preview_id: UUID
    location_id: UUID
    airline: str
    config: dict  # FilterRequest configuration that was previewed
    result: FilterPreviewResult  # The preview result
    created_at: datetime


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


class FilterCurrentResponse(BaseModel):
    """Response for GET /filters/current - shows active filter configuration."""
    has_active_filters: bool
    batch_id: Optional[UUID] = None
    applied_at: Optional[datetime] = None
    filters_active: list[str] = []  # ["reduce", "combine", "expand"]
    config: Optional[dict] = None  # Full FilterRequest configuration
    trips_affected: int = 0
    summary: Optional[dict] = None  # Breakdown: {"reduced": 100, "combined": 50, "expanded": 20}


class FilterHistoryItem(BaseModel):
    """Single item in filter history."""
    batch_id: UUID
    applied_at: datetime
    filters_applied: list[str]  # ["reduce", "combine", "expand"]
    trips_affected: int
    is_active: bool  # True if trips still reference this batch
    reverted_filters: list[str] = []  # Filters that were partially reverted


class FilterHistoryResponse(BaseModel):
    """Response for GET /filters/history - paginated list of filter batches."""
    data: list[FilterHistoryItem]
    total: int
    skip: int
    limit: int
