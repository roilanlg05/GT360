from pydantic import BaseModel
from typing import Optional


class LocationZoneUpdate(BaseModel):
    point: Optional[dict] = None
    radio_zone: Optional[float] = None