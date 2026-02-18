from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from uuid import UUID


class CreateAlarmRequest(BaseModel):
    alarm_at: datetime


class UpdateAlarmRequest(BaseModel):
    alarm_at: Optional[datetime] = None
    is_active: Optional[bool] = None


class AlarmResponse(BaseModel):
    id: UUID
    trip_id: UUID
    user_id: UUID
    alarm_at: datetime
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
