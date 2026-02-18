from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Depends, Request
from fastapi.responses import JSONResponse
from shared.db.db_config import get_db
from psqlmodel import Select, AsyncSession
from shared.db.schemas import Trip as TripDB
from shared.db.schemas.trips.trip_alarms import TripAlarm
from features.trips.models.alarm_models import (
    CreateAlarmRequest,
    UpdateAlarmRequest,
    AlarmResponse,
)
from features.auth.utils import verify_role
from datetime import datetime
from typing import Optional
from uuid import UUID

router = APIRouter(tags=["Alarms"])


def _get_user_id(request: Request) -> UUID:
    """Extract user_id from the authenticated token."""
    user_data = getattr(request.state, "user_data", None)
    if not user_data:
        raise HTTPException(status_code=401, detail="Missing authentication")
    user_id = user_data.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing authentication")
    try:
        return UUID(str(user_id))
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authentication")


@router.post("/v1/trips/{trip_id}/alarm")
async def create_alarm(
    trip_id: str,
    request: Request,
    request_data: CreateAlarmRequest,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["driver", "manager"])),
):
    """Create an alarm for the authenticated user on a specific trip."""
    try:
        uuid_trip_id = UUID(trip_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid trip ID")

    user_id = _get_user_id(request)

    # Verify the trip exists
    trip = await session.exec(
        Select(TripDB).Where(TripDB.id == uuid_trip_id)
    ).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Check if alarm already exists for this user+trip
    existing = await session.exec(
        Select(TripAlarm).Where(
            (TripAlarm.trip_id == uuid_trip_id) & (TripAlarm.user_id == user_id)
        )
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Alarm already exists for this trip")

    alarm = TripAlarm(
        trip_id=uuid_trip_id,
        user_id=user_id,
        alarm_at=request_data.alarm_at,
    )
    session.add(alarm)
    await session.commit()
    await session.refresh(alarm)

    result = AlarmResponse.model_validate(alarm).model_dump(mode="json")

    return JSONResponse(status_code=201, content={
        "status": "ok",
        "message": "Alarm created",
        "alarm": result,
    })


@router.get("/v1/trips/alarms")
async def list_alarms(
    request: Request,
    local_time: Optional[str] = Query(None, description="Client local time in ISO 8601 format"),
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["driver", "manager"])),
):
    """List all active alarms for the authenticated user.
    If local_time is provided, automatically removes alarms whose trip pickup time has already passed.
    """
    user_id = _get_user_id(request)

    stmt = (
        Select(TripAlarm)
        .Where((TripAlarm.user_id == user_id) & (TripAlarm.is_active == True))
        .OrderBy(TripAlarm.alarm_at.Asc())
    )

    alarms = await session.exec(stmt).all()

    # If client sends local_time, clean up alarms for trips whose pickup has passed
    if local_time and alarms:
        try:
            now_local = datetime.fromisoformat(local_time)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid local_time format. Use ISO 8601.")

        trip_ids = [a.trip_id for a in alarms]
        rows = await session.exec(
            Select(TripDB.id, TripDB.pick_up_date, TripDB.pick_up_time)
            .Where(TripDB.id.In(trip_ids))
        ).all()
        pickup_by_trip = {row[0]: (row[1], row[2]) for row in rows}

        expired_ids = []
        active_alarms = []

        for alarm in alarms:
            pickup = pickup_by_trip.get(alarm.trip_id)
            if pickup:
                pick_up_date, pick_up_time = pickup
                if pick_up_date and pick_up_time:
                    pickup_dt = datetime.combine(pick_up_date, pick_up_time)
                    now_naive = now_local.replace(tzinfo=None)
                    if pickup_dt <= now_naive:
                        expired_ids.append(alarm.id)
                        continue
            active_alarms.append(alarm)

        if expired_ids:
            await session.BulkDelete(TripAlarm, expired_ids)
            await session.commit()

        alarms = active_alarms

    results = [
        AlarmResponse.model_validate(a).model_dump(mode="json")
        for a in alarms
    ]

    return JSONResponse(content={
        "alarms": results,
        "total": len(results),
    })


@router.patch("/v1/trips/{trip_id}/alarm")
async def update_alarm(
    trip_id: str,
    request: Request,
    request_data: UpdateAlarmRequest,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["driver", "manager"])),
):
    """Update the alarm for the authenticated user on a specific trip."""
    try:
        uuid_trip_id = UUID(trip_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid trip ID")

    user_id = _get_user_id(request)

    alarm = await session.exec(
        Select(TripAlarm).Where(
            (TripAlarm.trip_id == uuid_trip_id) & (TripAlarm.user_id == user_id)
        )
    ).first()
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")

    if request_data.alarm_at is not None:
        alarm.alarm_at = request_data.alarm_at
    if request_data.is_active is not None:
        alarm.is_active = request_data.is_active

    alarm.updated_at = datetime.now()
    session.add(alarm)
    await session.commit()
    await session.refresh(alarm)

    result = AlarmResponse.model_validate(alarm).model_dump(mode="json")

    return JSONResponse(content={
        "status": "ok",
        "message": "Alarm updated",
        "alarm": result,
    })


@router.delete("/v1/trips/{trip_id}/alarm")
async def delete_alarm(
    trip_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["driver", "manager"])),
):
    """Delete the alarm for the authenticated user on a specific trip."""
    try:
        uuid_trip_id = UUID(trip_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid trip ID")

    user_id = _get_user_id(request)

    alarm = await session.exec(
        Select(TripAlarm).Where(
            (TripAlarm.trip_id == uuid_trip_id) & (TripAlarm.user_id == user_id)
        )
    ).first()
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")

    await session.delete(alarm)
    await session.commit()

    return JSONResponse(content={
        "status": "ok",
        "message": "Alarm deleted",
        "trip_id": str(uuid_trip_id),
    })
