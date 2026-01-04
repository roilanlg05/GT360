from pydantic import BaseModel
from typing import Optional


class HotelPointUpdate(BaseModel):
    point: Optional[dict] = None  # GeoJSON: {"type": "Point", "coordinates": [lon, lat]}
    radio_zone: Optional[float] = None
    address: str