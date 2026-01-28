"""
Step Filter Router (V2)

Endpoints for the new step/stack-based filter system.

All endpoints use the /v2/ prefix to maintain compatibility with v1.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from psqlmodel import AsyncSession
from uuid import UUID
from typing import Optional

from shared.db.db_config import get_db
from features.auth.utils import verify_role
from features.trips.services.step_filter_service import StepFilterService
from features.trips.models.filter_models import (
    FilterStepConfig,
    StepResult,
    StepRevertResult,
    StackState,
    EligibilityResult,
    BulkFilterConfig,
    BulkStepResult,
    BulkEligibilityResult,
    BulkRevertConfig,
    BulkRevertResult,
)


router = APIRouter(tags=["Filters V2"])


# =============================================================================
# STEP FILTER ENDPOINTS (V2)
# =============================================================================


@router.post("/v2/locations/{location_id}/airlines/{airline}/filters/step/preview")
async def preview_step(
    location_id: str,
    airline: str,
    config: FilterStepConfig,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> StepResult:
    """
    Preview a filter step without applying changes.

    This allows the user to see what changes would be made before committing.

    - **location_id**: Location UUID
    - **airline**: Airline code (e.g., "WN", "AA")
    - **config**: Filter step configuration

    Returns proposed changes and exclusions.
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location_id format")

    service = StepFilterService(session)

    try:
        result = await service.preview_step(location_uuid, airline, config)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error previewing step: {str(e)}")


@router.post("/v2/locations/{location_id}/airlines/{airline}/filters/step/apply")
async def apply_step(
    location_id: str,
    airline: str,
    config: FilterStepConfig,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> StepResult:
    """
    Apply a filter step to the stack.

    The step is added to the stack and changes are persisted.
    Steps can be applied in any order (reduce, combine, expand).

    - **location_id**: Location UUID
    - **airline**: Airline code (e.g., "WN", "AA")
    - **config**: Filter step configuration

    Returns applied changes and step information.
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location_id format")

    service = StepFilterService(session)

    try:
        result = await service.apply_step(location_uuid, airline, config)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error applying step: {str(e)}")


@router.get("/v2/locations/{location_id}/airlines/{airline}/filters/stack")
async def get_stack(
    location_id: str,
    airline: str,
    pick_up_date: str = Query(..., description="Date in YYYY-MM-DD format"),
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> StackState:
    """
    Get the current filter stack for a specific day.

    Returns all active steps in order, showing:
    - Step order
    - Filter type
    - Number of trips affected
    - Creation timestamp

    - **location_id**: Location UUID
    - **airline**: Airline code (e.g., "WN", "AA")
    - **pick_up_date**: Target date (YYYY-MM-DD)
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location_id format")

    service = StepFilterService(session)

    try:
        result = await service.get_stack(location_uuid, airline, pick_up_date)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting stack: {str(e)}")


@router.post("/v2/locations/{location_id}/airlines/{airline}/filters/revert-last")
async def revert_last_step(
    location_id: str,
    airline: str,
    pick_up_date: str = Query(..., description="Date in YYYY-MM-DD format"),
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> StepRevertResult:
    """
    Revert the last active step (pop from stack).

    This removes the most recently applied step and recalculates
    all trip times from original_pick_up_time.

    - **location_id**: Location UUID
    - **airline**: Airline code (e.g., "WN", "AA")
    - **pick_up_date**: Target date (YYYY-MM-DD)

    Returns revert results and updated stack state.
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location_id format")

    service = StepFilterService(session)

    try:
        result = await service.revert_last_step(location_uuid, airline, pick_up_date)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reverting step: {str(e)}")


@router.post("/v2/locations/{location_id}/airlines/{airline}/filters/step/{step_id}/revert")
async def revert_step(
    location_id: str,
    airline: str,
    step_id: str,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> StepRevertResult:
    """
    Revert a specific step by ID.

    This marks the step as inactive and recalculates all trip times
    by re-applying remaining active steps in order.

    - **location_id**: Location UUID (for authorization)
    - **airline**: Airline code (for authorization)
    - **step_id**: Step UUID to revert

    Returns revert results and updated stack state.
    """
    try:
        step_uuid = UUID(step_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid step_id format")

    service = StepFilterService(session)

    try:
        result = await service.revert_step(step_uuid)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reverting step: {str(e)}")


@router.get("/v2/locations/{location_id}/airlines/{airline}/filters/eligibility")
async def get_eligibility(
    location_id: str,
    airline: str,
    pick_up_date: str = Query(..., description="Date in YYYY-MM-DD format"),
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> EligibilityResult:
    """
    Check filter eligibility for a specific day.

    Returns information about:
    - Total trips for the day
    - Eligible trips (outbound, scheduled)
    - Trips already filtered
    - Breakdown by hotel

    - **location_id**: Location UUID
    - **airline**: Airline code (e.g., "WN", "AA")
    - **pick_up_date**: Target date (YYYY-MM-DD)
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location_id format")

    service = StepFilterService(session)

    try:
        result = await service.get_eligibility(location_uuid, airline, pick_up_date)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking eligibility: {str(e)}")


# =============================================================================
# BULK FILTER ENDPOINTS (Multi-Day)
# =============================================================================


@router.post("/v2/locations/{location_id}/airlines/{airline}/filters/bulk/preview")
async def preview_bulk(
    location_id: str,
    airline: str,
    config: BulkFilterConfig,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> BulkStepResult:
    """
    Preview a filter across multiple days (bulk operation).

    This allows previewing changes for a date range or all future trips
    in a single request.

    - **location_id**: Location UUID
    - **airline**: Airline code (e.g., "WN", "AA")
    - **config**: Bulk filter configuration with date_from, date_to (optional), windows

    If date_to is not provided, previews all future trips from date_from.

    Returns aggregated results with per-day breakdown.
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location_id format")

    service = StepFilterService(session)

    try:
        result = await service.preview_bulk(location_uuid, airline, config)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error previewing bulk: {str(e)}")


@router.post("/v2/locations/{location_id}/airlines/{airline}/filters/bulk/apply")
async def apply_bulk(
    location_id: str,
    airline: str,
    config: BulkFilterConfig,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> BulkStepResult:
    """
    Apply a filter across multiple days (bulk operation).

    This applies the same filter configuration to all dates in the range,
    creating one filter step per day.

    - **location_id**: Location UUID
    - **airline**: Airline code (e.g., "WN", "AA")
    - **config**: Bulk filter configuration with date_from, date_to (optional), windows

    If date_to is not provided, applies to all future trips from date_from.

    By default, days that already have filter steps are skipped.
    Set skip_days_with_stack=false to apply even to days with existing filters.

    Returns aggregated results with per-day breakdown including step_ids.
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location_id format")

    service = StepFilterService(session)

    try:
        result = await service.apply_bulk(location_uuid, airline, config)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error applying bulk: {str(e)}")


@router.get("/v2/locations/{location_id}/airlines/{airline}/filters/bulk/eligibility")
async def get_bulk_eligibility(
    location_id: str,
    airline: str,
    date_from: str = Query(..., description="Start date in YYYY-MM-DD format"),
    date_to: Optional[str] = Query(None, description="End date in YYYY-MM-DD format (optional)"),
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> BulkEligibilityResult:
    """
    Check filter eligibility across multiple days.

    Returns summary and per-day breakdown of eligible trips for the date range.

    - **location_id**: Location UUID
    - **airline**: Airline code (e.g., "WN", "AA")
    - **date_from**: Start date (YYYY-MM-DD)
    - **date_to**: End date (optional, YYYY-MM-DD). If not provided, checks all future.

    Useful for showing users how many trips will be affected before applying filters.
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location_id format")

    service = StepFilterService(session)

    try:
        result = await service.get_bulk_eligibility(location_uuid, airline, date_from, date_to)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking bulk eligibility: {str(e)}")


@router.post("/v2/locations/{location_id}/airlines/{airline}/filters/bulk/revert")
async def revert_bulk(
    location_id: str,
    airline: str,
    config: BulkRevertConfig,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> BulkRevertResult:
    """
    Revert filter steps across multiple days (bulk operation).

    This allows reverting all steps of a specific filter_type (or all types)
    across a date range or all future dates.

    - **location_id**: Location UUID
    - **airline**: Airline code (e.g., "WN", "AA")
    - **config**: Bulk revert configuration with date_from, date_to (optional), filter_type (optional)

    If date_to is not provided, reverts all future dates from date_from.
    If filter_type is not provided, reverts ALL filter types.

    Returns summary with per-day breakdown of reverted steps.
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location_id format")

    service = StepFilterService(session)

    try:
        result = await service.revert_bulk(location_uuid, airline, config)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reverting bulk: {str(e)}")
