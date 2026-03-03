"""
Step Filter Router (V2)

Endpoints for the new step/stack-based filter system.

All endpoints use the /v2/ prefix to maintain compatibility with v1.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from psqlmodel import AsyncSession
from uuid import UUID

from shared.db.db_config import get_db
from features.auth.utils import verify_role
from features.trips.services.step_filter_service import StepFilterService
from features.trips.models.filter_models import (
    FilterStepConfig,
    StepResult,
    StepRevertResult,
    StackState,
    EligibilityResult,
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
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> StackState:
    """
    Get the current filter stack for a location+airline.

    Returns all active steps in order, showing:
    - Step order
    - Filter type
    - Number of trips affected
    - Creation timestamp

    - **location_id**: Location UUID
    - **airline**: Airline code (e.g., "WN", "AA")
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location_id format")

    service = StepFilterService(session)

    try:
        result = await service.get_stack(location_uuid, airline)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting stack: {str(e)}")


@router.post("/v2/locations/{location_id}/airlines/{airline}/filters/revert-last")
async def revert_last_step(
    location_id: str,
    airline: str,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> StepRevertResult:
    """
    Revert the last active step (pop from stack).

    This removes the most recently applied step and recalculates
    all trip times from original_pick_up_time.

    - **location_id**: Location UUID
    - **airline**: Airline code (e.g., "WN", "AA")

    Returns revert results and updated stack state.
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location_id format")

    service = StepFilterService(session)

    try:
        result = await service.revert_last_step(location_uuid, airline)
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
    filter_type: str = Query(None, description="Filter type to check: reduce, combine, or expand"),
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> EligibilityResult:
    """
    Check filter eligibility for a location+airline.

    Returns information about:
    - Total eligible trips (outbound, scheduled)
    - Trips already filtered
    - Breakdown by hotel
    - If filter_type provided: trips with/without this specific filter

    - **location_id**: Location UUID
    - **airline**: Airline code (e.g., "WN", "AA")
    - **filter_type**: Optional filter type ("reduce", "combine", "expand")
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location_id format")

    service = StepFilterService(session)

    try:
        result = await service.get_eligibility(location_uuid, airline, filter_type)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking eligibility: {str(e)}")


