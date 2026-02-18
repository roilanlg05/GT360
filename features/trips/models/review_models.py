from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from uuid import UUID


class ReviewActionRequest(BaseModel):
    """Request del driver para marcar pickup/dropoff sin validacion de geofence."""
    type: str  # "pick-up" or "drop-off"
    driver_id: UUID


class ReviewResolveRequest(BaseModel):
    """Request del manager para marcar un review como revisado."""
    type: str  # "pick-up" or "drop-off"


class ReviewResponse(BaseModel):
    """Respuesta completa de un trip review."""
    id: UUID
    trip_id: UUID
    trip_hash: str
    driver_id: Optional[UUID] = None
    location_id: UUID
    review_pickup: bool = False
    review_dropoff: bool = False
    pickup_flagged_at: Optional[datetime] = None
    dropoff_flagged_at: Optional[datetime] = None
    pickup_reviewed_at: Optional[datetime] = None
    dropoff_reviewed_at: Optional[datetime] = None
    pickup_reviewed_by: Optional[UUID] = None
    dropoff_reviewed_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
