"""
Shifts router - Driver endpoints for shift management.
Handles starting, ending, and viewing shifts.
"""

from fastapi import APIRouter, Depends, HTTPException
from psqlmodel import AsyncSession
from typing import Optional
from datetime import datetime, date
from uuid import UUID

from shared.db.db_config import get_db
from features.auth.utils import verify_role
from features.drivers.models.shift_models import (
    StartShiftRequest,
    EndShiftRequest,
    ShiftResponse,
    ShiftListResponse,
    ShiftStartResponse,
    ShiftEndResponse
)
from features.drivers.services.shift_service import (
    start_shift,
    end_shift,
    get_shifts_for_driver,
    calculate_shift_duration,
    shift_crosses_midnight,
    calculate_hours_per_day,
    get_trips_in_shift
)


router = APIRouter(prefix="/v1/drivers", tags=["Driver Shifts"])


async def build_shift_response(shift, session: AsyncSession) -> dict:
    """Build shift response with calculated fields."""
    duration = calculate_shift_duration(shift)
    crosses = shift_crosses_midnight(shift)
    hours_dist = calculate_hours_per_day(shift) if crosses else None
    trips_count = await get_trips_in_shift(session, shift)

    return {
        "shift_id": shift.id,
        "driver_id": shift.driver_id,
        "pay_type": shift.pay_type,
        "rate": float(shift.rate) if shift.rate is not None else None,
        "started_at": shift.started_at,
        "ended_at": shift.ended_at,
        "duration_hours": duration,
        "status": shift.status,
        "review_status": shift.review_status,
        "review_reason": shift.review_reason,
        "reviewed_at": shift.reviewed_at,
        "reviewed_by": shift.reviewed_by,
        "manager_notes": shift.manager_notes,
        "auto_closed": shift.auto_closed,
        "crosses_midnight": crosses,
        "trips_in_shift": trips_count,
        "hours_distribution": hours_dist,
        "created_at": shift.created_at
    }


@router.post("/{driver_id}/shifts/start")
async def start_driver_shift(
    driver_id: str,
    request_data: StartShiftRequest,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["driver"]))
):
    """
    Start a new shift for the driver.

    - Driver must not have an existing active shift
    - Driver must be active
    - Returns the created shift
    """
    try:
        driver_uuid = UUID(driver_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid driver ID")

    shift = await start_shift(
        session,
        driver_uuid,
        request_data.started_at
    )

    shift_data = await build_shift_response(shift, session)

    return {
        "status": "ok",
        "message": "Shift started successfully",
        "shift": shift_data
    }


@router.post("/{driver_id}/shifts/end")
async def end_driver_shift(
    driver_id: str,
    request_data: EndShiftRequest,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["driver"]))
):
    """
    End the active shift for the driver.

    - Driver must have an active shift
    - End time must be after start time
    - Returns the updated shift
    """
    try:
        driver_uuid = UUID(driver_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid driver ID")

    shift = await end_shift(
        session,
        driver_uuid,
        request_data.ended_at
    )

    shift_data = await build_shift_response(shift, session)

    return {
        "status": "ok",
        "message": "Shift ended successfully",
        "shift": shift_data
    }


@router.get("/{driver_id}/shifts")
async def get_driver_shifts(
    driver_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["driver"]))
):
    """
    Get shifts for a driver with pagination.

    Query parameters:
    - start_date: Filter shifts starting after this date (ISO format)
    - end_date: Filter shifts starting before this date (ISO format)
    - status: Filter by status ('active', 'completed', 'under_review', etc.)
    - page: Page number (default 1)
    - page_size: Items per page (default 20)
    """
    try:
        driver_uuid = UUID(driver_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid driver ID")

    # Parse dates
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None

    shifts, total_count = await get_shifts_for_driver(
        session,
        driver_uuid,
        start_dt,
        end_dt,
        status,
        page,
        page_size
    )

    # Build response
    shifts_data = []
    for shift in shifts:
        shift_data = await build_shift_response(shift, session)
        shifts_data.append(shift_data)

    # Calculate summary
    from shared.db.schemas.drivers import ShiftStatus
    summary = {
        "active_shifts": sum(1 for s in shifts if s.status == ShiftStatus.ACTIVE),
        "completed_shifts": sum(1 for s in shifts if s.status == ShiftStatus.COMPLETED),
        "under_review_shifts": sum(1 for s in shifts if s.status == ShiftStatus.UNDER_REVIEW)
    }

    return {
        "shifts": shifts_data,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_shifts": total_count,
            "total_pages": (total_count + page_size - 1) // page_size
        },
        "summary": summary
    }
