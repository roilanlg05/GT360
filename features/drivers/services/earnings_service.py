"""
Earnings service - Complex business logic for calculating driver earnings.
Handles pay types (hourly/daily/per_trip) and pay frequencies (daily/weekly/biweekly).
"""

from datetime import datetime, timezone, date, timedelta, time
from typing import Optional, List, Dict, Tuple
from uuid import UUID
from decimal import Decimal
from psqlmodel import Select, AsyncSession
from fastapi import HTTPException
import pytz

from shared.db.schemas.drivers import DriverShift, ShiftStatus, ReviewStatus, DriverExpense, ExpenseStatus
from shared.db.schemas.entities.drivers import Driver
from shared.db.schemas.entities.users import User
from shared.db.schemas.entities.locations import Location
from shared.db.schemas.trips.trips_history import TripHistory
from .shift_service import calculate_hours_per_day


def get_work_day_key(
    started_at: datetime,
    shift_start_time: Optional[time] = None,
    shift_end_time: Optional[time] = None,
    timezone_str: str = 'UTC'
) -> str:
    """
    Determine which "logical work day" a shift belongs to.

    This groups multiple shifts opened on the same calendar day (or overnight window)
    into a single work day, so daily-rate drivers are charged once per day.

    Args:
        started_at: When the shift started (UTC)
        shift_start_time: Driver's scheduled start time (snapshot, may be None)
        shift_end_time: Driver's scheduled end time (snapshot, may be None)
        timezone_str: Driver's timezone

    Returns:
        ISO date string representing the logical work day
    """
    tz = pytz.timezone(timezone_str)
    local_dt = started_at.astimezone(tz)
    local_time = local_dt.time()

    # No schedule defined: group by the local date of started_at
    if shift_start_time is None or shift_end_time is None:
        return local_dt.date().isoformat()

    # Overnight schedule: start > end (e.g. 21:00 - 03:00)
    if shift_start_time > shift_end_time:
        # If shift started at or after the schedule start → today's work day
        if local_time >= shift_start_time:
            return local_dt.date().isoformat()
        # If shift started before the schedule end → belongs to yesterday's work day
        elif local_time < shift_end_time:
            return (local_dt.date() - timedelta(days=1)).isoformat()
        # Outside schedule window entirely, just use today
        return local_dt.date().isoformat()

    # Normal day schedule: start < end (e.g. 08:00 - 20:00)
    return local_dt.date().isoformat()


async def get_driver_timezone(session: AsyncSession, driver_id: UUID) -> str:
    """
    Get driver's timezone from their assigned location.

    Args:
        session: Database session
        driver_id: Driver UUID

    Returns:
        Timezone string (e.g., 'America/New_York')
    """
    driver = await session.exec(
        Select(Driver).Where(Driver.id == driver_id)
    ).first()

    if not driver or not driver.location_id:
        return 'UTC'

    location = await session.exec(
        Select(Location).Where(Location.id == driver.location_id)
    ).first()

    # Assuming Location has a timezone field
    # If not, default to UTC
    return getattr(location, 'timezone', 'UTC') if location else 'UTC'


def get_period_range(
    reference_date: date,
    pay_frequency: str,
    timezone_str: str
) -> Tuple[datetime, datetime]:
    """
    Calculate period start and end dates based on pay frequency.

    Args:
        reference_date: Reference date within the period
        pay_frequency: 'daily', 'weekly', or 'biweekly'
        timezone_str: Timezone string

    Returns:
        Tuple of (period_start, period_end) in UTC
    """
    tz = pytz.timezone(timezone_str)

    if pay_frequency == 'daily':
        # Period is the same day
        day_start = tz.localize(datetime.combine(reference_date, time.min))
        day_end = tz.localize(datetime.combine(reference_date, time.max))
        return (
            day_start.astimezone(timezone.utc),
            day_end.astimezone(timezone.utc)
        )

    elif pay_frequency == 'weekly':
        # Period is Monday to Sunday
        days_since_monday = reference_date.weekday()
        monday = reference_date - timedelta(days=days_since_monday)
        sunday = monday + timedelta(days=6)

        week_start = tz.localize(datetime.combine(monday, time.min))
        week_end = tz.localize(datetime.combine(sunday, time.max))

        return (
            week_start.astimezone(timezone.utc),
            week_end.astimezone(timezone.utc)
        )

    elif pay_frequency == 'biweekly':
        # Biweekly period - 26 periods per year
        # First period starts on first Monday of the year
        year_start = date(reference_date.year, 1, 1)
        days_until_monday = (7 - year_start.weekday()) % 7
        first_monday = year_start + timedelta(days=days_until_monday)

        # Calculate which biweekly period we're in
        days_since_first = (reference_date - first_monday).days
        biweekly_number = days_since_first // 14

        # Calculate period boundaries
        period_start_date = first_monday + timedelta(weeks=biweekly_number * 2)
        period_end_date = period_start_date + timedelta(days=13)

        period_start = tz.localize(datetime.combine(period_start_date, time.min))
        period_end = tz.localize(datetime.combine(period_end_date, time.max))

        return (
            period_start.astimezone(timezone.utc),
            period_end.astimezone(timezone.utc)
        )

    else:
        raise ValueError(f"Invalid pay_frequency: {pay_frequency}")


async def get_completed_shifts_for_period(
    session: AsyncSession,
    driver_id: UUID,
    period_start: datetime,
    period_end: datetime
) -> List[DriverShift]:
    """
    Get shifts for a period (completed, reviewed, and active).

    Args:
        session: Database session
        driver_id: Driver UUID
        period_start: Period start (UTC)
        period_end: Period end (UTC)

    Returns:
        List of shifts
    """
    # Completed/reviewed shifts with ended_at in the period
    completed_shifts = await session.exec(
        Select(DriverShift)
        .Where(
            (DriverShift.driver_id == driver_id)
            & (DriverShift.status.In([ShiftStatus.COMPLETED, ShiftStatus.REVIEWED]))
            & (
                (DriverShift.review_status == None)
                | (DriverShift.review_status == ReviewStatus.APPROVED)
            )
            & (DriverShift.started_at <= period_end)
            & (DriverShift.ended_at >= period_start)
            & (DriverShift.ended_at != None)
        )
    ).all()

    # Active shifts that started within the period
    active_shifts = await session.exec(
        Select(DriverShift)
        .Where(
            (DriverShift.driver_id == driver_id)
            & (DriverShift.status == ShiftStatus.ACTIVE)
            & (DriverShift.started_at >= period_start)
            & (DriverShift.started_at <= period_end)
        )
    ).all()

    return list(completed_shifts) + list(active_shifts)


async def get_trips_in_shifts(
    session: AsyncSession,
    driver_id: UUID,
    shifts: List[DriverShift]
) -> list:
    """
    Get completed trips from trips_history that occurred within the given shifts.

    Args:
        session: Database session
        driver_id: Driver UUID
        shifts: List of shifts

    Returns:
        List of trip history objects
    """
    if not shifts:
        return []

    trips = []
    seen_ids = set()

    for shift in shifts:
        # For active shifts use now() as the upper bound
        end_boundary = shift.ended_at or datetime.now(timezone.utc)

        history_trips = await session.exec(
            Select(TripHistory)
            .Where(
                (TripHistory.assigned_driver == driver_id)
                & (TripHistory.status == 'completed')
                & (TripHistory.dropped_off_at >= shift.started_at)
                & (TripHistory.dropped_off_at <= end_boundary)
            )
        ).all()

        for t in history_trips:
            if t.id not in seen_ids:
                seen_ids.add(t.id)
                trips.append(t)

    return trips


def calculate_total_hours(shifts: List[DriverShift]) -> float:
    """Calculate total hours from shifts (active shifts use now as end)."""
    total_seconds = 0
    for shift in shifts:
        end = shift.ended_at or datetime.now(timezone.utc)
        total_seconds += (end - shift.started_at).total_seconds()
    return round(total_seconds / 3600, 2)


def calculate_days_worked(shifts: List[DriverShift], timezone_str: str = 'UTC') -> int:
    """Calculate unique work days from shifts using work day grouping."""
    unique_days = set()
    for shift in shifts:
        day_key = get_work_day_key(
            shift.started_at,
            getattr(shift, 'shift_start_time', None),
            getattr(shift, 'shift_end_time', None),
            timezone_str
        )
        unique_days.add(day_key)
    return len(unique_days)


async def calculate_earnings_for_period(
    session: AsyncSession,
    driver: Driver,
    period_start: datetime,
    period_end: datetime
) -> Dict:
    """
    Calculate earnings for a specific period.

    Args:
        session: Database session
        driver: Driver object
        period_start: Period start (UTC)
        period_end: Period end (UTC)

    Returns:
        Dictionary with earnings data
    """
    # Get shifts
    shifts = await get_completed_shifts_for_period(
        session,
        driver.id,
        period_start,
        period_end
    )

    # Get ALL completed trips for the period (from trips_history)
    # This includes trips done outside of shifts
    trips = await session.exec(
        Select(TripHistory)
        .Where(
            (TripHistory.assigned_driver == driver.id)
            & (TripHistory.status == 'completed')
            & (TripHistory.dropped_off_at >= period_start)
            & (TripHistory.dropped_off_at <= period_end)
        )
    ).all()
    trips = list(trips)

    # Calculate earnings per shift using each shift's frozen rate/pay_type
    gross_earnings = Decimal("0.00")
    # Fallback pay_type/rate from driver profile (for old shifts without snapshot)
    default_pay_type = driver.pay_type or 'hour'
    default_rate = driver.rate or Decimal("10.00")

    # Get driver timezone for work day grouping
    driver_timezone = await get_driver_timezone(session, driver.id)

    # Group daily-rate shifts by work day to avoid charging per-shift
    # Key: (work_day_key, rate) → ensures each unique day × rate = 1 charge
    daily_work_days: Dict[tuple, Decimal] = {}

    for shift in shifts:
        shift_pay_type = shift.pay_type or default_pay_type
        shift_rate = shift.rate if shift.rate is not None else default_rate

        if shift_pay_type == 'hour':
            hours = calculate_total_hours([shift])
            gross_earnings += Decimal(str(hours)) * shift_rate
        elif shift_pay_type == 'day':
            # Group by work day key — multiple shifts in same day = 1 day charge
            day_key = get_work_day_key(
                shift.started_at,
                getattr(shift, 'shift_start_time', None),
                getattr(shift, 'shift_end_time', None),
                driver_timezone
            )
            group_key = (day_key, shift_rate)
            daily_work_days[group_key] = shift_rate
        elif shift_pay_type == 'trip':
            shift_trips = await get_trips_in_shifts(session, driver.id, [shift])
            gross_earnings += Decimal(str(len(shift_trips))) * shift_rate

    # Add daily earnings: each unique work day = 1 × rate
    for group_key, rate in daily_work_days.items():
        gross_earnings += rate

    # Get expenses
    from .expense_service import get_verified_expenses_for_period

    expenses = await get_verified_expenses_for_period(
        session,
        driver.id,
        period_start.date(),
        period_end.date()
    )

    verified_expenses = sum(e.amount for e in expenses)

    # Calculate net pay
    net_pay = gross_earnings + verified_expenses

    # Count trips per shift for the response (searches both tables)
    shift_trip_counts = {}
    for shift in shifts:
        shift_trips = await get_trips_in_shifts(session, driver.id, [shift])
        shift_trip_counts[shift.id] = len(shift_trips)

    # Serialize ORM objects to plain dicts (PSQLModel objects are not JSON-serializable)
    shifts_data = [
        {
            'id': str(s.id),
            'started_at': s.started_at.isoformat() if s.started_at else None,
            'ended_at': s.ended_at.isoformat() if s.ended_at else None,
            'status': s.status,
            'pay_type': s.pay_type,
            'rate': float(s.rate) if s.rate is not None else None,
            'hours': round((s.ended_at - s.started_at).total_seconds() / 3600, 2) if s.ended_at else 0,
            'trips_in_shift': shift_trip_counts.get(s.id, 0),
        }
        for s in shifts
    ]

    trips_data = [
        {
            'id': str(t.id),
            'pick_up_date': t.pick_up_date.isoformat() if t.pick_up_date else None,
            'pick_up_time': t.pick_up_time.isoformat() if t.pick_up_time else None,
            'pick_up_location': t.pick_up_location,
            'drop_off_location': t.drop_off_location,
            'dropped_off_at': t.dropped_off_at.isoformat() if t.dropped_off_at else None,
            'airline': t.airline,
            'flight_number': t.flight_number,
        }
        for t in trips
    ]

    expenses_data = [
        {
            'id': str(e.id),
            'amount': float(e.amount),
            'expense_type': e.expense_type,
            'description': e.description,
            'expense_date': e.expense_date.isoformat() if e.expense_date else None,
            'status': e.status,
            'receipt_photo_url': e.receipt_photo_url,
        }
        for e in expenses
    ]

    return {
        'gross_earnings': float(gross_earnings),
        'verified_expenses': float(verified_expenses),
        'net_pay': float(net_pay),
        'total_hours': calculate_total_hours(shifts),
        'total_days': calculate_days_worked(shifts, driver_timezone),
        'total_trips': len(trips),
        'total_shifts': len(shifts),
        'expenses_count': len(expenses),
        'shifts': shifts_data,
        'trips': trips_data,
        'expenses': expenses_data
    }


async def get_earnings_for_driver(
    session: AsyncSession,
    driver_id: UUID,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    page: int = 1,
    page_size: int = 10
) -> Dict:
    """
    Get earnings data for a driver with pagination.

    Args:
        session: Database session
        driver_id: Driver UUID
        start_date: Optional start date filter
        end_date: Optional end date filter
        page: Page number
        page_size: Periods per page

    Returns:
        Complete earnings response dict
    """
    # Get driver
    driver = await session.exec(
        Select(Driver).Where(Driver.id == driver_id)
    ).first()

    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    # Get timezone
    driver_timezone = await get_driver_timezone(session, driver_id)

    # Get pay frequency
    pay_frequency = driver.pay_frequency or 'weekly'  # default

    # Get driver's created_at as the earliest possible date
    user = await session.exec(
        Select(User).Where(User.id == driver_id)
    ).first()
    driver_created = user.created_at.date() if user and user.created_at else date.today()

    # Determine date range
    if not end_date:
        end_date = date.today()

    if not start_date:
        start_date = driver_created

    # Generate periods by starting from the CURRENT period and going backwards.
    # This guarantees the current period is always included.
    # Each period is a full week (Mon-Sun), even if the driver started mid-week.
    # Example: driver starts Wed Feb 6 → first period is Mon Feb 3 - Sun Feb 9.
    tz_obj = pytz.timezone(driver_timezone)
    periods = []
    seen_starts = set()

    # Walk backwards from today
    ref = end_date
    while True:
        p_start, p_end = get_period_range(ref, pay_frequency, driver_timezone)

        # Use local dates for comparisons (UTC can shift +1 day)
        local_start = p_start.astimezone(tz_obj).date()
        local_end = p_end.astimezone(tz_obj).date()

        # Stop if the period ends before the driver existed
        if local_end < start_date:
            break

        # Avoid duplicates
        if local_start not in seen_starts:
            seen_starts.add(local_start)
            # Don't include fully future periods
            if local_start <= date.today():
                periods.append((p_start, p_end))

        # Move backwards by one period
        if pay_frequency == 'daily':
            ref -= timedelta(days=1)
        elif pay_frequency == 'weekly':
            ref -= timedelta(weeks=1)
        elif pay_frequency == 'biweekly':
            ref -= timedelta(weeks=2)

    # periods is already most-recent-first (we walked backwards)

    # Paginate periods
    total_periods = len(periods)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_periods = periods[start_idx:end_idx]

    # Calculate earnings for each period
    periods_data = []
    for period_start, period_end in page_periods:
        earnings_data = await calculate_earnings_for_period(
            session,
            driver,
            period_start,
            period_end
        )

        # Convert to local date for display (UTC end can shift +1 day)
        local_start = period_start.astimezone(tz_obj).date()
        local_end = period_end.astimezone(tz_obj).date()

        periods_data.append({
            'period_start': local_start.isoformat(),
            'period_end': local_end.isoformat(),
            **earnings_data
        })

    # Calculate year-to-date
    year_start = date(date.today().year, 1, 1)
    year_start_dt, year_end_dt = get_period_range(
        date.today(),
        'daily',
        driver_timezone
    )
    year_start_dt = year_start_dt.replace(month=1, day=1, hour=0, minute=0, second=0)

    ytd_data = await calculate_earnings_for_period(
        session,
        driver,
        year_start_dt,
        datetime.now(timezone.utc)
    )

    return {
        'driver_id': str(driver_id),
        'pay_type': driver.pay_type,
        'pay_frequency': pay_frequency,
        'rate': float(driver.rate) if driver.rate is not None else None,
        'timezone': driver_timezone,
        'periods': periods_data,
        'pagination': {
            'page': page,
            'page_size': page_size,
            'total_periods': total_periods,
            'total_pages': (total_periods + page_size - 1) // page_size
        },
        'year_to_date': {
            'year': date.today().year,
            'total_gross_earnings': ytd_data['gross_earnings'],
            'total_expenses_reimbursed': ytd_data['verified_expenses'],
            'total_net_pay': ytd_data['net_pay'],
            'total_hours_worked': ytd_data['total_hours'],
            'total_days_worked': ytd_data['total_days'],
            'total_trips': ytd_data['total_trips']
        }
    }
