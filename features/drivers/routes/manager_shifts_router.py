"""
Manager shifts router - Manager endpoints for reviewing shifts.
Handles shift review and approval workflow.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from psqlmodel import Select, AsyncSession
from typing import Optional
from datetime import datetime
from uuid import UUID

from shared.db.db_config import get_db
from features.auth.utils import verify_role
from features.drivers.models.shift_models import (
    ResolveShiftRequest,
    ResolveShiftResponse
)
from features.drivers.services.shift_service import (
    get_shifts_pending_review,
    resolve_shift_review,
    calculate_shift_duration,
    shift_crosses_midnight,
    calculate_hours_per_day,
    get_trips_in_shift
)
from shared.db.schemas.entities.users import User


router = APIRouter(prefix="/v1/managers", tags=["Manager - Shift Review"])


async def build_shift_response_with_driver(shift, session: AsyncSession) -> dict:
    """Build shift response with driver info."""
    # Get driver name
    user = await session.exec(
        Select(User).Where(User.id == shift.driver_id)
    ).first()
    driver_name = f"{user.first_name} {user.last_name}" if user else "Unknown"

    duration = calculate_shift_duration(shift)
    crosses = shift_crosses_midnight(shift)
    hours_dist = calculate_hours_per_day(shift) if crosses else None
    trips_count = await get_trips_in_shift(session, shift)

    return {
        "shift_id": shift.id,
        "driver_id": shift.driver_id,
        "driver_name": driver_name,
        "started_at": shift.started_at,
        "ended_at": shift.ended_at,
        "duration_hours": duration,
        "auto_closed": shift.auto_closed,
        "review_status": shift.review_status,
        "review_reason": shift.review_reason,
        "reviewed_at": shift.reviewed_at,
        "reviewed_by": shift.reviewed_by,
        "manager_notes": shift.manager_notes,
        "created_at": shift.created_at,
        "trips_in_shift": trips_count,
        "hours_distribution": hours_dist
    }


@router.get("/shifts/review")
async def get_shifts_for_review(
    driver_id: Optional[str] = None,
    status: Optional[str] = None,
    sort_by: str = "created_at",
    order: str = "desc",
    page: int = 1,
    page_size: int = 20,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Get shifts pending manager review.

    Query parameters:
    - driver_id: Filter by specific driver (optional)
    - status: Filter by review status ('pending', 'approved', 'rejected')
    - sort_by: Sort field ('created_at', 'started_at', 'driver_name')
    - order: Sort order ('asc', 'desc')
    - page: Page number (default 1)
    - page_size: Items per page (default 20)

    Returns:
    - List of shifts needing review
    - Summary counts by status
    """
    # Parse driver_id if provided
    driver_uuid = None
    if driver_id:
        try:
            driver_uuid = UUID(driver_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid driver ID")

    # Get shifts
    shifts, total_count = await get_shifts_pending_review(
        session,
        driver_uuid,
        page,
        page_size
    )

    # Build response
    shifts_data = []
    for shift in shifts:
        shift_data = await build_shift_response_with_driver(shift, session)
        shifts_data.append(shift_data)

    # Calculate summary
    from shared.db.schemas.drivers import ReviewStatus
    summary = {
        "pending_count": sum(1 for s in shifts if s.review_status == ReviewStatus.PENDING),
        "approved_count": sum(1 for s in shifts if s.review_status == ReviewStatus.APPROVED),
        "rejected_count": sum(1 for s in shifts if s.review_status == ReviewStatus.REJECTED)
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


@router.post("/shifts/{shift_id}/resolve")
async def resolve_shift(
    shift_id: str,
    request_data: ResolveShiftRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Resolve a shift under review.

    Actions:
    - 'approve': Accept shift as-is
    - 'reject': Reject the shift (won't count for earnings)
    - 'adjust': Modify end time and approve

    Body:
    - action: Action to take (required)
    - manager_notes: Manager's notes (optional)
    - adjusted_ended_at: New end time (required if action='adjust')

    Validations:
    - Shift must be under review
    - Adjusted end time must be after start time
    """
    try:
        shift_uuid = UUID(shift_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid shift ID")

    # Get manager ID from token
    user_data = getattr(request.state, "user_data", None)
    manager_id = UUID(user_data.get("id")) if user_data else None

    if not manager_id:
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid authentication"
        )

    # Resolve shift
    shift = await resolve_shift_review(
        session,
        shift_uuid,
        manager_id,
        request_data.action,
        request_data.manager_notes,
        request_data.adjusted_ended_at
    )

    # Build response
    shift_data = await build_shift_response_with_driver(shift, session)

    action_messages = {
        'approve': 'Shift approved successfully',
        'reject': 'Shift rejected',
        'adjust': 'Shift adjusted and approved'
    }

    return {
        "status": "ok",
        "message": action_messages.get(request_data.action, "Shift resolved"),
        "shift": shift_data
    }
