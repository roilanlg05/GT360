from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Depends, Request
from fastapi.responses import JSONResponse
from shared.db.db_config import get_db
from psqlmodel import Select, AsyncSession
from shared.db.schemas import Trip as TripDB, Driver, Location, TripStatus
from shared.db.schemas.reviews.trip_reviews import TripReview
from features.trips.models.review_models import (
    ReviewActionRequest,
    ReviewResolveRequest,
    ReviewResponse,
)
from features.auth.utils import verify_role
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

REVIEW_WAIT_MINUTES = 5

router = APIRouter(tags=["Reviews"])


@router.post("/v1/trips/{trip_id}/review-action")
async def review_action(
    trip_id: str,
    request_data: ReviewActionRequest,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["driver"]))
):
    """
    Marca pickup o dropoff de un trip SIN validacion de geofence.
    Crea/actualiza un registro en trip_reviews indicando que necesita revision por un manager.
    """
    # Validar tipo
    action_type = request_data.type.lower().strip()
    if action_type not in ("pick-up", "drop-off"):
        raise HTTPException(
            status_code=400,
            detail="type must be 'pick-up' or 'drop-off'"
        )

    try:
        uuid_trip_id = UUID(trip_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid trip ID")

    # Buscar el trip
    trip = await session.exec(
        Select(TripDB).Where(TripDB.id == uuid_trip_id)
    ).first()

    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Validar que el driver este activo
    driver = await session.exec(
        Select(Driver).Where(Driver.id == request_data.driver_id)
    ).first()
    if not driver or not driver.is_active:
        raise HTTPException(status_code=403, detail="The driver is not active")

    # Validar que el driver este asignado al trip
    if trip.assigned_driver != request_data.driver_id:
        raise HTTPException(
            status_code=403,
            detail="Driver is not assigned to this trip"
        )

    now_utc = datetime.now(timezone.utc)

    # Buscar review existente para este trip
    existing_review = await session.exec(
        Select(TripReview).Where(TripReview.trip_id == uuid_trip_id)
    ).first()

    if action_type == "pick-up":
        # Validar que el driver haya llegado al pickup location
        if not trip.arrived_pickup_at:
            raise HTTPException(
                status_code=400,
                detail="Driver must have arrived at the pickup location first"
            )
        # Validar que hayan pasado al menos 5 minutos desde la llegada
        elapsed = now_utc - trip.arrived_pickup_at
        if elapsed < timedelta(minutes=REVIEW_WAIT_MINUTES):
            remaining = REVIEW_WAIT_MINUTES * 60 - int(elapsed.total_seconds())
            raise HTTPException(
                status_code=400,
                detail=f"Must wait {REVIEW_WAIT_MINUTES} minutes after arrival at pickup location. {remaining} seconds remaining"
            )
        # Validar que no tenga pickup ya
        if trip.picked_up_at:
            raise HTTPException(status_code=409, detail="Trip already picked up")

        if existing_review:
            existing_review.review_pickup = True
            existing_review.pickup_flagged_at = now_utc
            existing_review.updated_at = now_utc
            session.add(existing_review)
        else:
            existing_review = TripReview(
                trip_id=uuid_trip_id,
                trip_hash=trip.trip_hash,
                driver_id=request_data.driver_id,
                location_id=trip.location_id,
                review_pickup=True,
                pickup_flagged_at=now_utc,
            )
            session.add(existing_review)

        # Flush review antes de actualizar trip
        await session.flush()

        # Actualizar trip
        trip.picked_up_at = now_utc
        trip.status = TripStatus.EN_ROUTE
        session.add(trip)
        await session.commit()

        return JSONResponse(content={
            "status": "ok",
            "message": "Pickup registered - needs review",
            "trip_id": str(trip.id),
            "picked_up_at": trip.picked_up_at.isoformat(),
            "needs_review": True,
        })

    else:
        # drop-off
        # Validar que el driver haya llegado al dropoff location
        if not trip.arrived_dropoff_at:
            raise HTTPException(
                status_code=400,
                detail="Driver must have arrived at the drop-off location first"
            )
        # Validar que hayan pasado al menos 5 minutos desde la llegada
        elapsed = now_utc - trip.arrived_dropoff_at
        if elapsed < timedelta(minutes=REVIEW_WAIT_MINUTES):
            remaining = REVIEW_WAIT_MINUTES * 60 - int(elapsed.total_seconds())
            raise HTTPException(
                status_code=400,
                detail=f"Must wait {REVIEW_WAIT_MINUTES} minutes after arrival at drop-off location. {remaining} seconds remaining"
            )
        if trip.dropped_off_at:
            raise HTTPException(status_code=409, detail="Trip already dropped off")

        if existing_review:
            existing_review.review_dropoff = True
            existing_review.dropoff_flagged_at = now_utc
            existing_review.updated_at = now_utc
            session.add(existing_review)
        else:
            existing_review = TripReview(
                trip_id=uuid_trip_id,
                trip_hash=trip.trip_hash,
                driver_id=request_data.driver_id,
                location_id=trip.location_id,
                review_dropoff=True,
                dropoff_flagged_at=now_utc,
            )
            session.add(existing_review)

        # CRITICO: flush del review ANTES de actualizar trip
        # El trigger archiva y borra el trip al hacer drop-off
        await session.flush()

        # Actualizar trip (esto dispara el trigger de archivado)
        trip.dropped_off_at = now_utc
        trip.status = TripStatus.COMPLETED
        session.add(trip)
        await session.commit()

        return JSONResponse(content={
            "status": "ok",
            "message": "Drop off registered - needs review",
            "trip_id": str(uuid_trip_id),
            "dropped_off_at": now_utc.isoformat(),
            "needs_review": True,
        })


@router.get("/v1/reviews")
async def list_reviews(
    request: Request,
    location_id: Optional[str] = Query(None),
    pending_only: bool = Query(True),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Lista reviews pendientes, filtrable por location_id.
    Por defecto solo muestra reviews con pickup o dropoff pendiente de revision.
    """
    stmt = Select(TripReview)

    if location_id:
        try:
            uuid_location_id = UUID(location_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid location_id format")
        stmt = stmt.Where(TripReview.location_id == uuid_location_id)

    if pending_only:
        # Reviews donde pickup o dropoff estan flagueados pero no revisados
        stmt = stmt.Where(
            ((TripReview.review_pickup == True) & (TripReview.pickup_reviewed_at == None))
            | ((TripReview.review_dropoff == True) & (TripReview.dropoff_reviewed_at == None))
        )

    stmt = stmt.OrderBy(TripReview.created_at.Desc()).Limit(limit).Offset(skip)

    reviews = await session.exec(stmt).all()

    results = [
        ReviewResponse.model_validate(r).model_dump(mode="json")
        for r in reviews
    ]

    return JSONResponse(content={
        "reviews": results,
        "total": len(results),
        "limit": limit,
        "skip": skip,
    })


@router.patch("/v1/reviews/{review_id}")
async def resolve_review(
    review_id: str,
    request: Request,
    request_data: ReviewResolveRequest,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Marca pickup o dropoff de un review como revisado por el manager.
    """
    resolve_type = request_data.type.lower().strip()
    if resolve_type not in ("pick-up", "drop-off"):
        raise HTTPException(
            status_code=400,
            detail="type must be 'pick-up' or 'drop-off'"
        )

    try:
        uuid_review_id = UUID(review_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid review ID")

    review = await session.exec(
        Select(TripReview).Where(TripReview.id == uuid_review_id)
    ).first()

    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    # Obtener user_id del manager desde el token
    user_data = getattr(request.state, "user_data", None)
    manager_user_id = user_data.get("user_id") if user_data else None
    if not manager_user_id:
        raise HTTPException(status_code=401, detail="Missing authentication")

    try:
        manager_uuid = UUID(str(manager_user_id))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication")

    now_utc = datetime.now(timezone.utc)

    if resolve_type == "pick-up":
        if not review.review_pickup:
            raise HTTPException(status_code=400, detail="Pickup was not flagged for review")
        if review.pickup_reviewed_at:
            raise HTTPException(status_code=409, detail="Pickup already reviewed")
        review.pickup_reviewed_at = now_utc
        review.pickup_reviewed_by = manager_uuid
    else:
        if not review.review_dropoff:
            raise HTTPException(status_code=400, detail="Dropoff was not flagged for review")
        if review.dropoff_reviewed_at:
            raise HTTPException(status_code=409, detail="Dropoff already reviewed")
        review.dropoff_reviewed_at = now_utc
        review.dropoff_reviewed_by = manager_uuid

    review.updated_at = now_utc
    session.add(review)
    await session.commit()
    await session.refresh(review)

    result = ReviewResponse.model_validate(review).model_dump(mode="json")

    return JSONResponse(content={
        "status": "ok",
        "message": f"{resolve_type} reviewed successfully",
        "review": result,
    })
