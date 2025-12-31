from psqlmodel import table, Column, PSQLModel, UniqueConstraint, CheckConstraint
from psqlmodel.orm.types import uuid, jsonb, timestamptz, date, time
from psqlmodel.utils import gen_default_uuid, now
@table("trips", schema="trips", unique_together=[
    "location_id", "pick_up_date", 
    "pick_up_time", "airline", 
    "flight_number", "pick_up_location", 
    "drop_off_location"
])
class Trip(PSQLModel):

    id: uuid = Column(
        default=gen_default_uuid,
        primary_key=True
    )

    assigned_driver: uuid = Column(
        default=None,
        foreign_key="entities.drivers.id",
        on_delete="SET NULL",
        index=True,
        nullable=True,
    )

    location_id: uuid = Column(
            foreign_key="entities.locations.id",
            on_delete="CASCADE",
            nullable=False,
            index=True,
    )

    pick_up_date: date = Column(nullable=False, index=True)

    pick_up_time: time = Column(nullable=False, index=True)
    
    pick_up_location: str = Column(nullable=False)

    drop_off_location: str = Column(nullable=False)
    
    airline: str = Column(nullable=False, index=True)

    flight_number: str = Column(nullable=False, index=True)

    riders: jsonb = Column(nullable=True)

    started_at: timestamptz = Column(
        default=None,
        nullable=True, 
        index=True
    )

    picked_up_at: timestamptz = Column(
        default=None, 
        nullable=True, 
        index=True
    )

    dropped_off_at: timestamptz = Column(
        default=None,
        nullable=True, 
        index=True
    )

    created_at: timestamptz = Column(
        default=now,
        nullable=False, 
        index=True
    )

    updated_at: timestamptz = Column(
        default=now,
        nullable=False, 
        index=True
    )