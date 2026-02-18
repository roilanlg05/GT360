from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from shared.db.schemas.ratings.driver_ratings import RatingStamp


class SubmitRatingRequest(BaseModel):
    """Request from crew to rate a driver after a completed trip."""
    score: int = Field(..., ge=1, le=5, description="Rating score from 1 to 5")
    comment: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional comment about the driver"
    )
    stamps: Optional[List[str]] = Field(
        default=None,
        description="Optional list of predefined stamps/tags"
    )


class RatingResponse(BaseModel):
    """Response model for a single rating."""
    id: UUID
    trip_id: UUID
    trip_hash: str
    driver_id: Optional[UUID] = None
    crew_id: Optional[UUID] = None
    crew_name: Optional[str] = None
    score: int
    comment: Optional[str] = None
    stamps: Optional[List[str]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class StampCount(BaseModel):
    """A stamp and how many times it has been given."""
    stamp: str
    count: int


class RatingSummaryResponse(BaseModel):
    """Aggregated rating summary for a driver."""
    driver_id: UUID
    average_score: float
    total_ratings: int
    score_distribution: dict  # {1: N, 2: N, 3: N, 4: N, 5: N}
    stamp_counts: List[StampCount]
