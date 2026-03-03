"""
Filter Preset Router

Endpoints for managing global filter presets (auto-apply on import).
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from psqlmodel import AsyncSession, Select
from uuid import UUID

from shared.db.db_config import get_db
from shared.db.schemas import FilterStep
from features.auth.utils import verify_role
from features.trips.services.filter_preset_service import FilterPresetService
from features.trips.models.filter_models import (
    CreateFilterPreset,
    UpdateFilterPreset,
    FilterPresetResponse,
    AutoApplyResult,
)


router = APIRouter(tags=["Filter Presets"])


@router.post("/v2/locations/{location_id}/airlines/{airline}/filters/preset")
async def create_preset(
    location_id: str,
    airline: str,
    preset: CreateFilterPreset,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> FilterPresetResponse:
    """
    Create or update global filter preset.

    The preset is a "stack template" that will be auto-applied
    to new days when trips are imported.

    - **location_id**: Location UUID
    - **airline**: Airline code (e.g., "WN", "AA")
    - **preset**: Stack template with steps and windows

    Returns the created/updated preset.
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    service = FilterPresetService(session)

    try:
        stack_template_dict = [t.model_dump() for t in preset.stack_template]
        result = await service.create_or_update_preset(
            location_uuid, airline, stack_template_dict, user_id=None
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating preset: {str(e)}")


@router.get("/v2/locations/{location_id}/airlines/{airline}/filters/preset")
async def get_preset(
    location_id: str,
    airline: str,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> FilterPresetResponse:
    """
    Get global filter preset for location+airline.

    Returns 404 if no preset exists.

    - **location_id**: Location UUID
    - **airline**: Airline code
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location_id format")

    service = FilterPresetService(session)
    preset = await service.get_preset(location_uuid, airline)

    if not preset:
        raise HTTPException(
            status_code=404,
            detail=f"No preset found for location={location_id}, airline={airline}"
        )

    return preset


@router.put("/v2/locations/{location_id}/airlines/{airline}/filters/preset")
async def update_preset(
    location_id: str,
    airline: str,
    preset: UpdateFilterPreset,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> FilterPresetResponse:
    """
    Update existing preset.

    Alias for POST (create_or_update).

    - **location_id**: Location UUID
    - **airline**: Airline code
    - **preset**: Updated stack template
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    service = FilterPresetService(session)

    try:
        stack_template_dict = [t.model_dump() for t in preset.stack_template]
        result = await service.create_or_update_preset(
            location_uuid, airline, stack_template_dict, user_id=None
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating preset: {str(e)}")


@router.delete("/v2/locations/{location_id}/airlines/{airline}/filters/preset")
async def delete_preset(
    location_id: str,
    airline: str,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Delete global filter preset.

    - **location_id**: Location UUID
    - **airline**: Airline code

    Returns 204 No Content on success.
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location_id format")

    service = FilterPresetService(session)

    # Check if exists
    existing = await service.get_preset(location_uuid, airline)
    if not existing:
        raise HTTPException(
            status_code=404,
            detail=f"No preset found for location={location_id}, airline={airline}"
        )

    await service.delete_preset(location_uuid, airline)
    return {"status": "deleted"}


@router.post("/v2/locations/{location_id}/airlines/{airline}/filters/preset/test")
async def test_preset(
    location_id: str,
    airline: str,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> AutoApplyResult:
    """
    Test how preset would be applied for this location+airline.

    This is a dry-run that shows what would happen without actually applying.

    - **location_id**: Location UUID
    - **airline**: Airline code

    Returns summary of what would be applied.
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location_id format")

    service = FilterPresetService(session)

    result = await service.auto_apply_preset(location_uuid, airline)

    return result


@router.post("/v2/locations/{location_id}/airlines/{airline}/filters/preset/from-stack")
async def create_preset_from_stack(
    location_id: str,
    airline: str,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> FilterPresetResponse:
    """
    Create preset from the current active filter stack.

    This copies the current active stack and saves it as the preset
    for this location+airline.

    - **location_id**: Location UUID
    - **airline**: Airline code (e.g., "WN", "AA")

    Returns the created preset.
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location_id format")

    # Get current active steps
    steps_query = (
        Select(FilterStep)
        .Where(FilterStep.location_id == location_uuid)
        .Where(FilterStep.airline == airline)
        .Where(FilterStep.is_active == True)
        .OrderBy(FilterStep.step_order.Asc())
    )
    active_steps = await session.exec(steps_query).all()

    if not active_steps:
        raise HTTPException(
            status_code=404,
            detail="No active filter stack found. Apply filters first, then save as preset."
        )

    # Convert steps to stack_template format
    stack_template = []
    for step in active_steps:
        template = {
            "filter_type": step.filter_type,
            "windows": step.windows if step.windows else []
        }
        stack_template.append(template)

    # Create preset
    service = FilterPresetService(session)
    try:
        result = await service.create_or_update_preset(
            location_uuid, airline, stack_template, user_id=None
        )

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating preset: {str(e)}")
