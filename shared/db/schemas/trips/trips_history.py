from psqlmodel import table, Column, PSQLModel, UniqueConstraint, CheckConstraint
from psqlmodel.orm.types import uuid, jsonb, timestamptz, date, time
from psqlmodel.utils import gen_default_uuid, now


""", unique_together=[
    "location_id", "pick_up_date", 
    "pick_up_time", "airline", 
    "flight_number", "pick_up_location",
    "drop_off_location"
]"""

@table('trips_history', schema="trips")
class TripHistory(PSQLModel):

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
        index=True
    )

    trip_hash: str = Column(
        nullable=False,
        index=True,
    )

    pick_up_date: date = Column(nullable=False, index=True)

    pick_up_time: time = Column(nullable=False, index=True)
    
    pick_up_location: str = Column(nullable=False)

    drop_off_location: str = Column(nullable=False)

    airline: str = Column(nullable=False, index=True)

    flight_number: str = Column(nullable=False, index=True)

    trip_type: str = Column(
        max_len=10,
        nullable=True,
        index=True,
    )

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

    arrived_pickup_at: timestamptz = Column(
        default=None,
        nullable=True,
        index=True
    )

    arrived_dropoff_at: timestamptz = Column(
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

    # === Filter tracking fields (V2 Step-based) ===
    original_pick_up_time: time = Column(
        default=None,
        nullable=True,
        index=True
    )

    reduce_applied: bool = Column(
        default=False,
        nullable=False,
        index=True
    )

    combine_applied: bool = Column(
        default=False,
        nullable=False,
        index=True
    )

    expand_applied: bool = Column(
        default=False,
        nullable=False,
        index=True
    )

    filtered_at: timestamptz = Column(
        default=None,
        nullable=True,
        index=True
    )

    current_step_id: uuid = Column(
        default=None,
        foreign_key="trips.filter_steps.id",
        on_delete="SET NULL",
        nullable=True,
        index=True
    )

    # Chronological order of filters applied (e.g., "expand,reduce")
    filter_order: str = Column(
        default=None,
        nullable=True
    )

    status: str = Column(
        default="scheduled",
        nullable=False,
        index=True
    )
