"""
Shift service - Business logic for driver shifts.
Handles starting, ending, and reviewing driver work sessions.
"""

from datetime import datetime, timezone, timedelta, time
from typing import Optional, Dict, List, Tuple
from uuid import UUID
from psqlmodel import Select, Count, AsyncSession
from fastapi import HTTPException

from shared.db.schemas.drivers import DriverShift, ShiftStatus, ReviewStatus
from shared.db.schemas.entities.drivers import Driver
from shared.db.schemas.trips.trips_history import TripHistory


async def start_shift(
    session: AsyncSession,
    driver_id: UUID,
    started_at: Optional[datetime] = None
) -> DriverShift:
    """
    Start a new shift for a driver.

    Args:
        session: Database session
        driver_id: Driver UUID
        started_at: Optional start time (defaults to now)

    Returns:
        Created shift

    Raises:
        HTTPException: If driver already has an active shift or is not active
    """
    # Check if driver exists and is active
    driver = await session.exec(
        Select(Driver).Where(Driver.id == driver_id)
    ).first()

    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    if not driver.is_active:
        raise HTTPException(status_code=403, detail="Driver is not active")

    # Check for existing active shift
    existing_shift = await session.exec(
        Select(DriverShift)
        .Where(
            (DriverShift.driver_id == driver_id)
            & (DriverShift.status == ShiftStatus.ACTIVE)
        )
    ).first()

    if existing_shift:
        raise HTTPException(
            status_code=409,
            detail="Driver already has an active shift"
        )

    # Create new shift with pay + schedule snapshot
    new_shift = DriverShift(
        driver_id=driver_id,
        pay_type=driver.pay_type,
        rate=driver.rate,
        shift_start_time=driver.shift_start_time,
        shift_end_time=driver.shift_end_time,
        started_at=started_at or datetime.now(timezone.utc),
        status=ShiftStatus.ACTIVE
    )

    session.add(new_shift)
    await session.commit()
    await session.refresh(new_shift)

    return new_shift


async def end_shift(
    session: AsyncSession,
    driver_id: UUID,
    ended_at: Optional[datetime] = None
) -> DriverShift:
    """
    End the active shift for a driver.

    Args:
        session: Database session
        driver_id: Driver UUID
        ended_at: Optional end time (defaults to now)

    Returns:
        Updated shift

    Raises:
        HTTPException: If no active shift found or invalid end time
    """
    # Find active shift
    shift = await session.exec(
        Select(DriverShift)
        .Where(
            (DriverShift.driver_id == driver_id)
            & (DriverShift.status == ShiftStatus.ACTIVE)
        )
    ).first()

    if not shift:
        raise HTTPException(status_code=404, detail="No active shift found")

    # Set end time
    end_time = ended_at or datetime.now(timezone.utc)

    # Validate end time
    if end_time <= shift.started_at:
        raise HTTPException(
            status_code=400,
            detail="End time must be after start time"
        )

    # Update shift
    shift.ended_at = end_time
    shift.status = ShiftStatus.COMPLETED
    shift.updated_at = datetime.now(timezone.utc)

    session.add(shift)
    await session.commit()
    await session.refresh(shift)

    return shift


def calculate_shift_duration(shift: DriverShift) -> Optional[float]:
    """
    Calculate shift duration in hours.

    Args:
        shift: Shift object

    Returns:
        Duration in hours or None if shift not ended
    """
    if not shift.ended_at:
        return None

    duration_seconds = (shift.ended_at - shift.started_at).total_seconds()
    return round(duration_seconds / 3600, 2)


def shift_crosses_midnight(shift: DriverShift) -> bool:
    """
    Check if shift crosses midnight (different days).

    Args:
        shift: Shift object

    Returns:
        True if shift crosses midnight
    """
    if not shift.ended_at:
        return False

    return shift.started_at.date() != shift.ended_at.date()


def calculate_hours_per_day(shift: DriverShift) -> Dict[str, float]:
    """
    Calculate hours worked per day for shifts that cross midnight.

    Args:
        shift: Shift object

    Returns:
        Dictionary mapping date (ISO string) to hours worked
    """
    if not shift.ended_at:
        return {}

    hours_by_day = {}
    current_time = shift.started_at
    end_time = shift.ended_at

    while current_time < end_time:
        current_date = current_time.date()

        # End of current day
        day_end = datetime.combine(
            current_date,
            time.max
        ).replace(tzinfo=timezone.utc)

        # Segment ends at day end or shift end, whichever is earlier
        segment_end = min(day_end, end_time)

        # Calculate hours in this segment
        hours = (segment_end - current_time).total_seconds() / 3600

        # Store in dict
        date_key = current_date.isoformat()
        hours_by_day[date_key] = round(hours, 2)

        # Move to next day
        current_time = datetime.combine(
            current_date + timedelta(days=1),
            time.min
        ).replace(tzinfo=timezone.utc)

    return hours_by_day


async def get_shifts_for_driver(
    session: AsyncSession,
    driver_id: UUID,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20
) -> Tuple[List[DriverShift], int]:
    """
    Get shifts for a driver with pagination.

    Args:
        session: Database session
        driver_id: Driver UUID
        start_date: Optional start date filter
        end_date: Optional end date filter
        status: Optional status filter
        page: Page number (1-indexed)
        page_size: Items per page

    Returns:
        Tuple of (shifts list, total count)
    """
    # Build filter
    base_filter = (DriverShift.driver_id == driver_id)

    if start_date:
        base_filter = base_filter & (DriverShift.started_at >= start_date)

    if end_date:
        base_filter = base_filter & (DriverShift.started_at <= end_date)

    if status:
        base_filter = base_filter & (DriverShift.status == status)

    # Get total count
    total_count_result = await session.exec(
        Select(Count(DriverShift.id)).From(DriverShift).Where(base_filter)
    ).first()
    total_count = total_count_result[0] if total_count_result else 0

    # Get paginated results
    shifts = await session.exec(
        Select(DriverShift)
        .Where(base_filter)
        .OrderBy(DriverShift.started_at.Desc())
        .Limit(page_size)
        .Offset((page - 1) * page_size)
    ).all()

    return list(shifts), total_count


async def get_trips_in_shift(
    session: AsyncSession,
    shift: DriverShift
) -> int:
    """
    Get count of trips completed during a shift.

    Args:
        session: Database session
        shift: Shift object

    Returns:
        Number of trips
    """
    # For active shifts use now() as the upper bound
    end_boundary = shift.ended_at or datetime.now(timezone.utc)

    # Query completed trips from history within shift timeframe
    trips = await session.exec(
        Select(TripHistory)
        .Where(
            (TripHistory.assigned_driver == shift.driver_id)
            & (TripHistory.status == 'completed')
            & (TripHistory.dropped_off_at >= shift.started_at)
            & (TripHistory.dropped_off_at <= end_boundary)
        )
    ).all()

    return len(trips)


async def auto_close_stale_shifts(
    session: AsyncSession,
    hours_threshold: int = 6
) -> List[DriverShift]:
    """
    Auto-close shifts that have been active for more than threshold hours.

    Args:
        session: Database session
        hours_threshold: Hours after which to auto-close (default 6)

    Returns:
        List of auto-closed shifts
    """
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_threshold)

    # Find active shifts older than threshold
    stale_shifts = await session.exec(
        Select(DriverShift)
        .Where(
            (DriverShift.status == ShiftStatus.ACTIVE)
            & (DriverShift.started_at < cutoff_time)
        )
    ).all()

    auto_closed_shifts = []

    for shift in stale_shifts:
        # Close shift at threshold time
        shift.ended_at = shift.started_at + timedelta(hours=hours_threshold)
        shift.status = ShiftStatus.UNDER_REVIEW
        shift.review_status = ReviewStatus.PENDING
        shift.auto_closed = True
        shift.review_reason = (
            f"Auto-closed after {hours_threshold} hours of inactivity. "
            f"Started at {shift.started_at.isoformat()}"
        )
        shift.updated_at = datetime.now(timezone.utc)

        session.add(shift)
        auto_closed_shifts.append(shift)

    if auto_closed_shifts:
        await session.commit()

    return auto_closed_shifts


async def resolve_shift_review(
    session: AsyncSession,
    shift_id: UUID,
    manager_id: UUID,
    action: str,
    manager_notes: Optional[str] = None,
    adjusted_ended_at: Optional[datetime] = None
) -> DriverShift:
    """
    Resolve a shift that's under review.

    Args:
        session: Database session
        shift_id: Shift UUID
        manager_id: Manager UUID performing the action
        action: 'approve', 'reject', or 'adjust'
        manager_notes: Optional manager notes
        adjusted_ended_at: Required if action='adjust'

    Returns:
        Updated shift

    Raises:
        HTTPException: If shift not found or invalid action
    """
    # Find shift
    shift = await session.exec(
        Select(DriverShift).Where(DriverShift.id == shift_id)
    ).first()

    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    if shift.status != ShiftStatus.UNDER_REVIEW:
        raise HTTPException(
            status_code=400,
            detail="Shift is not under review"
        )

    # Validate action
    if action not in ['approve', 'reject', 'adjust']:
        raise HTTPException(
            status_code=400,
            detail="Invalid action. Must be 'approve', 'reject', or 'adjust'"
        )

    # Handle actions
    if action == 'approve':
        shift.status = ShiftStatus.REVIEWED
        shift.review_status = ReviewStatus.APPROVED

    elif action == 'reject':
        shift.status = ShiftStatus.REVIEWED
        shift.review_status = ReviewStatus.REJECTED

    elif action == 'adjust':
        if not adjusted_ended_at:
            raise HTTPException(
                status_code=400,
                detail="adjusted_ended_at is required for adjust action"
            )

        if adjusted_ended_at <= shift.started_at:
            raise HTTPException(
                status_code=400,
                detail="Adjusted end time must be after start time"
            )

        shift.ended_at = adjusted_ended_at
        shift.status = ShiftStatus.REVIEWED
        shift.review_status = ReviewStatus.APPROVED

    # Update review metadata
    shift.reviewed_at = datetime.now(timezone.utc)
    shift.reviewed_by = manager_id
    shift.manager_notes = manager_notes
    shift.updated_at = datetime.now(timezone.utc)

    session.add(shift)
    await session.commit()
    await session.refresh(shift)

    return shift


async def get_shifts_pending_review(
    session: AsyncSession,
    driver_id: Optional[UUID] = None,
    page: int = 1,
    page_size: int = 20
) -> Tuple[List[DriverShift], int]:
    """
    Get shifts pending manager review.

    Args:
        session: Database session
        driver_id: Optional filter by driver
        page: Page number
        page_size: Items per page

    Returns:
        Tuple of (shifts list, total count)
    """
    base_filter = (
        (DriverShift.status == ShiftStatus.UNDER_REVIEW)
        & (DriverShift.review_status == ReviewStatus.PENDING)
    )

    if driver_id:
        base_filter = base_filter & (DriverShift.driver_id == driver_id)

    # Get total count
    total_count_result = await session.exec(
        Select(Count(DriverShift.id)).From(DriverShift).Where(base_filter)
    ).first()
    total_count = total_count_result[0] if total_count_result else 0

    # Get paginated results
    shifts = await session.exec(
        Select(DriverShift)
        .Where(base_filter)
        .OrderBy(DriverShift.created_at.Desc())
        .Limit(page_size)
        .Offset((page - 1) * page_size)
    ).all()

    return list(shifts), total_count
