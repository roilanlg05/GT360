from pydantic import BaseModel, Field, field_validator
from datetime import time, datetime
from typing import Optional
from uuid import UUID


class TimeRange(BaseModel):
    """Time range for filtering trips by pickup time window.

    Accepts time in HH:MM or HH:MM:SS format.
    Special case: "24:00" is allowed for end time to represent end of day.
    """
    start: str  # e.g., "05:00"
    end: str    # e.g., "10:00" or "24:00" for end of day

    @field_validator('start')
    @classmethod
    def validate_start_time(cls, v):
        """Validate HH:MM or HH:MM:SS format for start time (24:00 not allowed)."""
        try:
            parts = v.split(":")
            if len(parts) == 2:
                hour, minute = int(parts[0]), int(parts[1])
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError
            elif len(parts) == 3:
                hour, minute, second = int(parts[0]), int(parts[1]), int(parts[2])
                if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
                    raise ValueError
            else:
                raise ValueError
        except (ValueError, IndexError):
            raise ValueError(f"Invalid time format for start: {v}. Use HH:MM or HH:MM:SS (e.g., '09:30')")
        return v

    @field_validator('end')
    @classmethod
    def validate_end_time(cls, v):
        """Validate HH:MM or HH:MM:SS format for end time (24:00 allowed for end of day)."""
        if v in ("24:00", "24:00:00"):
            return v  # Special case for end of day
        try:
            # Try parsing as HH:MM:SS first, then HH:MM
            parts = v.split(":")
            if len(parts) == 2:
                hour, minute = int(parts[0]), int(parts[1])
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError
            elif len(parts) == 3:
                hour, minute, second = int(parts[0]), int(parts[1]), int(parts[2])
                if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
                    raise ValueError
            else:
                raise ValueError
        except (ValueError, IndexError):
            raise ValueError(f"Invalid time format: {v}. Use HH:MM or HH:MM:SS (e.g., '09:30', '09:30:00')")
        return v

    def get_start_time(self) -> time:
        """Convert start string to time object."""
        parts = self.start.split(":")
        if len(parts) == 2:
            return time(int(parts[0]), int(parts[1]))
        return time(int(parts[0]), int(parts[1]), int(parts[2]))

    def get_end_time(self) -> time:
        """Convert end string to time object.

        For "24:00" or "24:00:00", returns time(23, 59, 59) as the practical end of day.
        """
        if self.end in ("24:00", "24:00:00"):
            return time(23, 59, 59)
        parts = self.end.split(":")
        if len(parts) == 2:
            return time(int(parts[0]), int(parts[1]))
        return time(int(parts[0]), int(parts[1]), int(parts[2]))


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


# =============================================================================
# V2 Step-Based Filter Models
# =============================================================================

class TimeWindow(BaseModel):
    """
    Time window with its own configuration (v2).

    Each window can have different config params, enabling:
    - Reduce with different minutes per time range
    - Combine/Expand with different gaps per time range
    - Ventanas sin config (enabled=False or all params=None)

    Rules:
    - start < end always (no midnight crossing)
    - Windows in same step cannot overlap
    - Default window is 00:00-24:00 (entire day)
    """
    start: str = Field(default="00:00", description="Start time in HH:MM format")
    end: str = Field(default="24:00", description="End time in HH:MM format")
    enabled: bool = Field(default=True, description="Whether this window is active")

    # Config específica de esta ventana (solo para tipos aplicables)
    minutes_to_reduce: Optional[int] = Field(
        default=None,
        ge=1,
        le=120,
        description="Minutes to reduce (for Reduce filter)"
    )
    min_gap: Optional[int] = Field(
        default=None,
        ge=1,
        le=60,
        description="Minimum gap (for Combine/Expand)"
    )
    max_gap: Optional[int] = Field(
        default=None,
        ge=1,
        le=120,
        description="Maximum gap (for Combine/Expand)"
    )
    max_shift: Optional[int] = Field(
        default=None,
        ge=1,
        le=20,
        description="Maximum shift per trip (for Expand)"
    )
    hotel_names: Optional[list[str]] = Field(
        default=None,
        description="Filter to specific hotels (None = all)"
    )

    @field_validator('start', 'end')
    @classmethod
    def validate_time_format(cls, v):
        """Validate HH:MM format."""
        if v == "24:00":
            return v  # Special case for end of day
        try:
            parts = v.split(":")
            if len(parts) != 2:
                raise ValueError
            hour, minute = int(parts[0]), int(parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
        except (ValueError, IndexError):
            raise ValueError(f"Invalid time format: {v}. Use HH:MM (e.g., '09:30')")
        return v

    @field_validator('end')
    @classmethod
    def validate_no_midnight_cross(cls, v, info):
        """Ensure start < end (no midnight crossing)."""
        start = info.data.get('start')
        if start and v != "24:00":
            if start >= v:
                raise ValueError(
                    f"Window crosses midnight ({start}-{v}). "
                    "Midnight crossing is not allowed in v2."
                )
        return v


class FilterStepConfig(BaseModel):
    """
    Configuration for a single filter step (v2).

    Supports:
    - Order-free application (any sequence of reduce/combine/expand)
    - Per-day configuration (pick_up_date)
    - Time windows with config per window (1..N per step)
    - Minute precision (no rounding to multiples of 5)

    Each TimeWindow contains its own config (minutes_to_reduce, min_gap, etc.).
    This allows different configs per time range within a single step.
    """
    filter_type: str = Field(
        description="Filter type: 'reduce', 'combine', or 'expand'"
    )
    pick_up_date: str = Field(
        description="Target date in YYYY-MM-DD format"
    )
    windows: list[TimeWindow] = Field(
        default_factory=lambda: [TimeWindow()],
        description="Time windows with config per window (default: entire day)"
    )

    @field_validator('filter_type')
    @classmethod
    def validate_filter_type(cls, v):
        valid_types = {'reduce', 'combine', 'expand'}
        if v not in valid_types:
            raise ValueError(f"filter_type must be one of {valid_types}")
        return v

    @field_validator('pick_up_date')
    @classmethod
    def validate_date_format(cls, v):
        from datetime import date as dt_date
        try:
            dt_date.fromisoformat(v)
        except ValueError:
            raise ValueError(f"Invalid date format: {v}. Use YYYY-MM-DD")
        return v


class StepResult(BaseModel):
    """Result of applying or previewing a step (v2)."""
    step_id: Optional[UUID] = None  # None for preview
    filter_type: str
    pick_up_date: str
    trips_modified: int
    changes: list[TripChange]
    exclusions: list[FilterExclusion]
    summary: dict = Field(default_factory=dict)


class FilterStepInfo(BaseModel):
    """Info about a step in the stack (v2)."""
    step_id: UUID
    step_order: int
    filter_type: str
    windows_count: int
    windows: list[dict] = Field(default_factory=list)  # Full windows config for UI rehydration
    trips_affected: int
    created_at: datetime
    is_active: bool
    config: dict = Field(default_factory=dict)


class StackState(BaseModel):
    """Current state of the filter stack for a day (v2)."""
    location_id: UUID
    airline: str
    pick_up_date: str
    steps: list[FilterStepInfo]
    total_trips_affected: int


class StepRevertResult(BaseModel):
    """Result of reverting a step (v2)."""
    step_id: UUID
    filter_type: str
    trips_recalculated: int
    remaining_steps: int
    stack_state: Optional[StackState] = None


class EligibilityResult(BaseModel):
    """Result of checking filter eligibility for a day (v2)."""
    location_id: UUID
    airline: str
    pick_up_date: str
    filter_type: Optional[str] = None  # "reduce" | "combine" | "expand" (if checking specific type)
    total_trips: int
    eligible_trips: int
    already_filtered: int  # Trips with ANY filter
    trips_with_filter: Optional[int] = None  # Trips with THIS specific filter (if filter_type provided)
    trips_new: Optional[int] = None  # Trips WITHOUT this filter (if filter_type provided)
    by_hotel: dict = Field(default_factory=dict)  # {"Hotel A": 10, "Hotel B": 5}
    by_time_range: dict = Field(default_factory=dict)  # {"00:00-06:00": 5, ...}


# =============================================================================
# Filter Presets (Global Auto-Apply)
# =============================================================================

class FilterPresetTemplate(BaseModel):
    """Template for a single step in the preset."""
    filter_type: str = Field(description="Filter type: reduce, combine, or expand")
    windows: list[dict] = Field(description="Windows with full config")

    @field_validator('filter_type')
    @classmethod
    def validate_filter_type(cls, v):
        valid_types = {'reduce', 'combine', 'expand'}
        if v not in valid_types:
            raise ValueError(f"filter_type must be one of {valid_types}")
        return v


class FilterPresetResponse(BaseModel):
    """Response for filter preset."""
    id: UUID
    location_id: UUID
    airline: str
    stack_template: list[FilterPresetTemplate]
    created_at: datetime
    updated_at: datetime
    created_by: Optional[UUID] = None


class CreateFilterPreset(BaseModel):
    """Request to create filter preset."""
    stack_template: list[FilterPresetTemplate]


class UpdateFilterPreset(BaseModel):
    """Request to update filter preset."""
    stack_template: list[FilterPresetTemplate]


class AutoApplyResult(BaseModel):
    """Result of auto-applying preset."""
    applied: bool
    reason: Optional[str] = None
    days_processed: int = 0
    days_skipped: int = 0
    trips_affected: int = 0
    stack_cloned_from_preset: bool = False
    days_with_existing_stack: int = 0  # Days where we applied existing stack to new trips


# =============================================================================
# Bulk Operations (Multi-Day)
# =============================================================================

class BulkFilterConfig(BaseModel):
    """
    Configuration for bulk filter operations (multiple days).

    Allows applying the same filter config to all future trips
    or a specific date range.
    """
    filter_type: str = Field(
        description="Filter type: 'reduce', 'combine', or 'expand'"
    )
    date_from: str = Field(
        description="Start date in YYYY-MM-DD format"
    )
    date_to: Optional[str] = Field(
        default=None,
        description="End date in YYYY-MM-DD format (None = all future)"
    )
    windows: list[TimeWindow] = Field(
        default_factory=lambda: [TimeWindow()],
        description="Time windows with config (applied to all days)"
    )
    skip_days_with_stack: bool = Field(
        default=True,
        description="Skip days that already have filter steps applied"
    )

    @field_validator('filter_type')
    @classmethod
    def validate_filter_type(cls, v):
        valid_types = {'reduce', 'combine', 'expand'}
        if v not in valid_types:
            raise ValueError(f"filter_type must be one of {valid_types}")
        return v

    @field_validator('date_from', 'date_to')
    @classmethod
    def validate_date_format(cls, v):
        if v is None:
            return v
        from datetime import date as dt_date
        try:
            dt_date.fromisoformat(v)
        except ValueError:
            raise ValueError(f"Invalid date format: {v}. Use YYYY-MM-DD")
        return v


class DayResult(BaseModel):
    """Result for a single day in bulk operation."""
    pick_up_date: str
    trips_modified: int
    exclusions_count: int
    step_id: Optional[UUID] = None  # None for preview, UUID for apply
    skipped: bool = False
    skip_reason: Optional[str] = None


class BulkStepResult(BaseModel):
    """Result of bulk preview or apply operation."""
    filter_type: str
    date_from: str
    date_to: Optional[str]

    # Summary
    total_days: int
    days_processed: int
    days_skipped: int
    total_trips_modified: int
    total_exclusions: int

    # Per-day details
    by_date: list[DayResult] = Field(default_factory=list)

    # All changes (optional, can be large)
    all_changes: list[TripChange] = Field(default_factory=list)
    all_exclusions: list[FilterExclusion] = Field(default_factory=list)


class BulkEligibilityResult(BaseModel):
    """Result of bulk eligibility check."""
    location_id: UUID
    airline: str
    date_from: str
    date_to: Optional[str]
    filter_type: Optional[str] = None  # If provided, shows filter-specific counts

    # Summary
    total_days: int
    total_trips: int
    total_eligible: int
    trips_with_filter: Optional[int] = None  # Total trips with this filter applied (across all days)
    trips_new: Optional[int] = None  # Total trips WITHOUT this filter (available for filtering)

    # Per-day breakdown
    by_date: list[dict] = Field(default_factory=list)  # [{pick_up_date, eligible, trips_with_filter, trips_new, by_hotel}]


class BulkRevertConfig(BaseModel):
    """
    Configuration for bulk revert operations.

    Allows reverting filter steps across multiple days or all future.
    Can optionally filter by filter_type to only revert specific filter types.
    """
    date_from: str = Field(
        description="Start date in YYYY-MM-DD format"
    )
    date_to: Optional[str] = Field(
        default=None,
        description="End date in YYYY-MM-DD format (None = all future)"
    )
    filter_type: Optional[str] = Field(
        default=None,
        description="Filter type to revert: 'reduce', 'combine', 'expand', or null for all types"
    )

    @field_validator('filter_type')
    @classmethod
    def validate_filter_type(cls, v):
        if v is None:
            return v
        valid_types = {'reduce', 'combine', 'expand'}
        if v not in valid_types:
            raise ValueError(f"filter_type must be one of {valid_types} or null")
        return v

    @field_validator('date_from', 'date_to')
    @classmethod
    def validate_date_format(cls, v):
        if v is None:
            return v
        from datetime import date as dt_date
        try:
            dt_date.fromisoformat(v)
        except ValueError:
            raise ValueError(f"Invalid date format: {v}. Use YYYY-MM-DD")
        return v


class DayRevertResult(BaseModel):
    """Result for a single day in bulk revert operation."""
    pick_up_date: str
    steps_reverted: int
    step_ids: list[UUID] = Field(default_factory=list)
    trips_recalculated: int
    skipped: bool = False
    skip_reason: Optional[str] = None


class BulkRevertResult(BaseModel):
    """Result of bulk revert operation."""
    date_from: str
    date_to: Optional[str]
    filter_type: Optional[str]

    # Summary
    total_days: int
    days_with_reverts: int
    days_skipped: int
    total_steps_reverted: int
    total_trips_recalculated: int

    # Per-day details
    by_date: list[DayRevertResult] = Field(default_factory=list)
