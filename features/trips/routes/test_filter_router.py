"""
Test endpoint para verificar rehidratación de filtros
Solo habilitado en desarrollo
"""

from fastapi import APIRouter, Depends, Query
from psqlmodel import AsyncSession, Select
from uuid import UUID
from datetime import date

from shared.db.db_config import get_db
from shared.db.schemas import FilterStep, Trip, TripType, TripStatus
from features.auth.utils import verify_role

router = APIRouter(tags=["Filter Tests"])


@router.get("/test/filters/check-inconsistency")
async def check_filter_inconsistency(
    location_id: str = Query(...),
    airline: str = Query(...),
    pick_up_date: str = Query(...),
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Test endpoint para verificar inconsistencias entre trips y filter_steps.

    Retorna:
    - trips_with_filters: Trips que tienen reduce/combine/expand_applied=true
    - active_filter_steps: FilterSteps activos para esa fecha
    - inconsistency_detected: True si hay trips con filtros pero sin steps
    """
    try:
        location_uuid = UUID(location_id)
        target_date = date.fromisoformat(pick_up_date)
    except ValueError as e:
        return {"error": f"Invalid ID or date format: {e}"}

    # 1. Contar trips con filtros aplicados
    trips_with_filters_query = (
        Select(Trip)
        .Where(Trip.location_id == location_uuid)
        .Where(Trip.airline == airline)
        .Where(Trip.pick_up_date == target_date)
        .Where(Trip.original_pick_up_time != None)
    )
    trips_with_filters = await session.exec(trips_with_filters_query).all()

    # 2. Buscar FilterSteps activos
    active_steps_query = (
        Select(FilterStep)
        .Where(FilterStep.location_id == location_uuid)
        .Where(FilterStep.airline == airline)
        .Where(FilterStep.pick_up_date == target_date)
        .Where(FilterStep.is_active == True)
    )
    active_steps = await session.exec(active_steps_query).all()

    # 3. Buscar TODOS los FilterSteps (activos e inactivos)
    all_steps_query = (
        Select(FilterStep)
        .Where(FilterStep.location_id == location_uuid)
        .Where(FilterStep.airline == airline)
        .Where(FilterStep.pick_up_date == target_date)
    )
    all_steps = await session.exec(all_steps_query).all()

    # 4. Analizar trips
    trips_analysis = []
    for trip in trips_with_filters[:10]:  # Primeros 10
        trips_analysis.append({
            "trip_id": str(trip.id),
            "flight_number": trip.flight_number,
            "original_time": str(trip.original_pick_up_time) if trip.original_pick_up_time else None,
            "current_time": str(trip.pick_up_time) if trip.pick_up_time else None,
            "reduce_applied": trip.reduce_applied,
            "combine_applied": trip.combine_applied,
            "expand_applied": trip.expand_applied,
            "current_step_id": str(trip.current_step_id) if trip.current_step_id else None,
        })

    # 5. Analizar steps
    steps_analysis = []
    for step in all_steps:
        steps_analysis.append({
            "step_id": str(step.id),
            "filter_type": step.filter_type,
            "step_order": step.step_order,
            "is_active": step.is_active,
            "trips_affected": step.trips_affected,
            "windows": step.windows,
            "created_at": step.created_at.isoformat() if step.created_at else None,
        })

    # 6. Detectar inconsistencia
    has_trips_with_filters = len(trips_with_filters) > 0
    has_active_steps = len(active_steps) > 0
    inconsistency = has_trips_with_filters and not has_active_steps

    return {
        "test_parameters": {
            "location_id": location_id,
            "airline": airline,
            "pick_up_date": pick_up_date
        },
        "results": {
            "trips_with_filters_count": len(trips_with_filters),
            "active_steps_count": len(active_steps),
            "total_steps_count": len(all_steps),
            "inconsistency_detected": inconsistency
        },
        "trips_sample": trips_analysis,
        "all_steps": steps_analysis,
        "diagnosis": {
            "status": "ERROR" if inconsistency else "OK",
            "message": (
                f"INCONSISTENCIA DETECTADA: {len(trips_with_filters)} trips tienen filtros aplicados "
                f"pero NO hay FilterSteps activos. "
                f"(Total steps en DB: {len(all_steps)}, activos: {len(active_steps)})"
            ) if inconsistency else (
                f"OK: {len(trips_with_filters)} trips con filtros, {len(active_steps)} steps activos"
            )
        }
    }


@router.get("/test/filters/stack-rehidration")
async def test_stack_rehidration(
    location_id: str = Query(...),
    airline: str = Query(...),
    pick_up_date: str = Query(...),
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Test del flujo completo de rehidratación.

    Simula lo que pasa cuando el frontend hace F5 y llama GET /stack.
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        return {"error": "Invalid location_id format"}

    from features.trips.services.step_filter_service import StepFilterService

    service = StepFilterService(session)

    try:
        # Llamar get_stack (lo mismo que hace GET /stack endpoint)
        stack_state = await service.get_stack(location_uuid, airline, pick_up_date)

        return {
            "test": "Stack Rehidration Test",
            "parameters": {
                "location_id": location_id,
                "airline": airline,
                "pick_up_date": pick_up_date
            },
            "stack_state": {
                "location_id": str(stack_state.location_id),
                "airline": stack_state.airline,
                "pick_up_date": stack_state.pick_up_date,
                "steps_count": len(stack_state.steps),
                "total_trips_affected": stack_state.total_trips_affected,
                "steps": [
                    {
                        "step_id": str(step.step_id),
                        "filter_type": step.filter_type,
                        "step_order": step.step_order,
                        "windows_count": step.windows_count,
                        "windows": step.windows,
                        "trips_affected": step.trips_affected,
                        "is_active": step.is_active
                    }
                    for step in stack_state.steps
                ]
            },
            "diagnosis": {
                "has_steps": len(stack_state.steps) > 0,
                "message": (
                    f"OK: Rehidratación funcionando. {len(stack_state.steps)} steps activos."
                ) if stack_state.steps else (
                    "PROBLEMA: No hay steps activos. Si hay trips con filtros, hay inconsistencia."
                )
            }
        }

    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc()
        }
