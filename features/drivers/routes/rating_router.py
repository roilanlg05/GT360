"""
Rating router - Crew rates drivers after completed trips.
Managers can view ratings per driver; drivers can see their own summary.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from psqlmodel import AsyncSession, Select
from uuid import UUID
from collections import Counter

from shared.db.db_config import get_db
from shared.db.schemas import User, Crew, Driver
from shared.db.schemas.trips.trips_history import TripHistory
from shared.db.schemas.ratings.driver_ratings import DriverRating, RatingStamp
from features.auth.utils import verify_role
from features.drivers.models.rating_models import (
    SubmitRatingRequest,
    RatingResponse,
    RatingSummaryResponse,
    StampCount,
)


router = APIRouter(prefix="/v1/ratings", tags=["Driver Ratings"])


# ─── POST /v1/ratings/trips/{trip_id} ────────────────────────────────
@router.post("/trips/{trip_id}", status_code=201)
async def submit_rating(
    trip_id: str,
    body: SubmitRatingRequest,
    session: AsyncSession = Depends(get_db),
    user_data=Depends(verify_role(["crew"])),
):
    """
    Crew member rates a driver after a completed trip.
    Only one rating per crew per trip is allowed.
    """
    # Parse trip_id
    try:
        trip_uuid = UUID(trip_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid trip ID")

    crew_user_id = UUID(user_data["id"])

    # Validate stamps if provided
    if body.stamps:
        invalid = [s for s in body.stamps if s not in RatingStamp.ALL]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid stamps: {invalid}. Valid stamps: {RatingStamp.ALL}"
            )

    # Find trip in trips_history (completed trips are archived there)
    trip = await session.exec(
        Select(TripHistory).Where(TripHistory.id == trip_uuid)
    ).first()

    if not trip:
        raise HTTPException(status_code=404, detail="Completed trip not found")

    # Verify trip is completed (has dropped_off_at)
    if not trip.dropped_off_at:
        raise HTTPException(status_code=400, detail="Trip is not completed yet")

    # Get crew airline
    crew = await session.exec(
        Select(Crew).Where(Crew.id == crew_user_id)
    ).first()

    if not crew:
        raise HTTPException(status_code=404, detail="Crew record not found")

    # Validate crew airline matches trip airline
    if crew.airline and trip.airline:
        if crew.airline.upper() != trip.airline.upper():
            raise HTTPException(
                status_code=403,
                detail="Your airline does not match the trip airline"
            )

    # Check for duplicate rating
    existing = await session.exec(
        Select(DriverRating).Where(
            (DriverRating.crew_id == crew_user_id)
            & (DriverRating.trip_id == trip_uuid)
        )
    ).first()

    if existing:
        raise HTTPException(status_code=409, detail="You have already rated this trip")

    # Create the rating
    rating = DriverRating(
        trip_id=trip_uuid,
        trip_hash=trip.trip_hash,
        driver_id=trip.assigned_driver,
        crew_id=crew_user_id,
        score=body.score,
        comment=body.comment,
        stamps=body.stamps,
    )
    session.add(rating)
    await session.commit()
    await session.refresh(rating)

    # Get crew name for response
    crew_user = await session.get(User, crew_user_id)
    crew_name = None
    if crew_user:
        parts = [crew_user.first_name, crew_user.last_name]
        crew_name = " ".join(p for p in parts if p) or None

    return JSONResponse(
        status_code=201,
        content={
            "status": "ok",
            "message": "Rating submitted successfully",
            "rating": RatingResponse(
                id=rating.id,
                trip_id=rating.trip_id,
                trip_hash=rating.trip_hash,
                driver_id=rating.driver_id,
                crew_id=rating.crew_id,
                crew_name=crew_name,
                score=rating.score,
                comment=rating.comment,
                stamps=rating.stamps,
                created_at=rating.created_at,
            ).model_dump(mode="json"),
        },
    )


# ─── GET /v1/ratings/drivers/{driver_id} ─────────────────────────────
@router.get("/drivers/{driver_id}")
async def list_driver_ratings(
    driver_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    user_data=Depends(verify_role(["manager"])),
):
    """List all ratings for a specific driver (manager only)."""
    try:
        driver_uuid = UUID(driver_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid driver ID")

    # Verify driver exists
    driver = await session.get(Driver, driver_uuid)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    # Count total
    count_rows = await session.exec(
        Select(DriverRating.id).Where(DriverRating.driver_id == driver_uuid)
    ).all()
    total = len(count_rows)

    # Fetch page
    offset = (page - 1) * page_size
    ratings = await session.exec(
        Select(DriverRating)
        .Where(DriverRating.driver_id == driver_uuid)
        .OrderBy(DriverRating.created_at.Desc())
        .Limit(page_size)
        .Offset(offset)
    ).all()

    # Build response with crew names
    results = []
    for r in ratings:
        crew_name = None
        if r.crew_id:
            crew_user = await session.get(User, r.crew_id)
            if crew_user:
                parts = [crew_user.first_name, crew_user.last_name]
                crew_name = " ".join(p for p in parts if p) or None

        results.append(
            RatingResponse(
                id=r.id,
                trip_id=r.trip_id,
                trip_hash=r.trip_hash,
                driver_id=r.driver_id,
                crew_id=r.crew_id,
                crew_name=crew_name,
                score=r.score,
                comment=r.comment,
                stamps=r.stamps,
                created_at=r.created_at,
            ).model_dump(mode="json")
        )

    return JSONResponse(content={
        "ratings": results,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_ratings": total,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        },
    })


# ─── GET /v1/ratings/drivers/{driver_id}/summary ─────────────────────
@router.get("/drivers/{driver_id}/summary")
async def get_driver_rating_summary(
    driver_id: str,
    session: AsyncSession = Depends(get_db),
    user_data=Depends(verify_role(["manager", "driver"])),
):
    """
    Get aggregated rating summary for a driver.
    Managers can view any driver; drivers can only view their own.
    """
    try:
        driver_uuid = UUID(driver_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid driver ID")

    # Drivers can only see their own summary
    if user_data.get("role") == "driver":
        current_user_id = UUID(user_data["id"])
        if current_user_id != driver_uuid:
            raise HTTPException(
                status_code=403,
                detail="Drivers can only view their own rating summary"
            )

    # Verify driver exists
    driver = await session.get(Driver, driver_uuid)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    # Fetch all ratings for this driver
    ratings = await session.exec(
        Select(DriverRating).Where(DriverRating.driver_id == driver_uuid)
    ).all()

    total = len(ratings)

    if total == 0:
        return JSONResponse(content=RatingSummaryResponse(
            driver_id=driver_uuid,
            average_score=0.0,
            total_ratings=0,
            score_distribution={1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
            stamp_counts=[],
        ).model_dump(mode="json"))

    # Calculate average
    scores = [r.score for r in ratings]
    average = round(sum(scores) / total, 2)

    # Score distribution
    dist = Counter(scores)
    score_distribution = {i: dist.get(i, 0) for i in range(1, 6)}

    # Stamp counts
    all_stamps = []
    for r in ratings:
        if r.stamps and isinstance(r.stamps, list):
            all_stamps.extend(r.stamps)
    stamp_counter = Counter(all_stamps)
    stamp_counts = [
        StampCount(stamp=s, count=c)
        for s, c in stamp_counter.most_common()
    ]

    return JSONResponse(content=RatingSummaryResponse(
        driver_id=driver_uuid,
        average_score=average,
        total_ratings=total,
        score_distribution=score_distribution,
        stamp_counts=stamp_counts,
    ).model_dump(mode="json"))


# ─── GET /v1/ratings/stamps ──────────────────────────────────────────
@router.get("/stamps")
async def get_available_stamps(
    _user_data=Depends(verify_role(["crew"])),
):
    """Returns the list of valid stamp strings a crew member can use."""
    return JSONResponse(content={
        "stamps": RatingStamp.ALL,
    })
