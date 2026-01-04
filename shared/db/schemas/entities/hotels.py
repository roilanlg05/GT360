from psqlmodel import PSQLModel, Column, table
from psqlmodel.orm.types import uuid, timestamptz, jsonb
from psqlmodel.utils import gen_default_uuid, now


@table("hotels", schema="entities", unique_together=['name', 'location_id'])
class Hotel(PSQLModel):
    id: uuid = Column(primary_key=True, default=gen_default_uuid)
    name: str = Column(max_len=250, nullable=False)
    location_id: uuid = Column(foreign_key='entities.locations.id', nullable=False, on_delete='CASCADE')
    address: str = Column(max_len=250, nullable=True)
    point: jsonb = Column(nullable=True)
    radio_zone: float = Column(default=None, nullable=True)
    crated_at: timestamptz = Column(default=now)
    updated_at: timestamptz = Column(default=now)

