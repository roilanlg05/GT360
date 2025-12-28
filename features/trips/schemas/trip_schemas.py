from psqlmodel import table, Column, PSQLModel, Relation, Relationship, UniqueConstraint, CheckConstraint
from psqlmodel.orm.types import uuid, jsonb, timestamptz, date, time
from psqlmodel.utils import gen_default_uuid, now
from features.auth.schemas import Driver, Location, Organization

@table("trips", unique_together=[
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
        foreign_key=Driver.id,
        on_delete="SET NULL",
        index=True,
        nullable=True,
    )

    location_id: uuid = Column(
            foreign_key=Location.id,
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

    driver: Relation[Driver] = Relationship(passive_deletes = True)

    location: Relation[Location] = Relationship(passive_deletes = True)

@table('trips_history', unique_together=[
    "location_id", "pick_up_date", 
    "pick_up_time", "airline", 
    "flight_number", "pick_up_location",
    "drop_off_location"
])
class TripHistory(PSQLModel):

    id: uuid = Column(
        default=gen_default_uuid,
        primary_key=True
    )
    
    assigned_driver: uuid = Column(
        default=None,
        foreign_key=Driver.id,
        on_delete="SET NULL", 
        index=True,
        nullable=True,
    )

    location_id: uuid = Column(
        foreign_key=Location.id, 
        on_delete="CASCADE",
        nullable=False,
        index=True
    )

    pick_up_date: date = Column(nullable=False, index=True)

    pick_up_time: time = Column(nullable=False, index=True)
    
    pick_up_location: str = Column(nullable=False)

    drop_off_location: str = Column(nullable=False)

    airline: str = Column(nullable=False, index=True)

    flight_number: str = Column(nullable=False, index=True)

    riders: jsonb = Column(nullable=False)

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

@table('airports', constraints=[
        UniqueConstraint("code", name="uq_airport_code"),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_airport_lat"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_airport_lon"),
    ]
)
class Airport(PSQLModel):

    id: uuid = Column(
        default=gen_default_uuid,
        primary_key=True
    )

    code: str = Column(max_len=10, nullable=False, index=True, unique=True)
    
    name: str = Column(max_len=150, nullable=False)
    
    latitude: float = Column(nullable=False)
    
    longitude: float = Column(nullable=False)
    
    country_code: str = Column(max_len=5, nullable=False, index=True)
    
    zone_code: str = Column(max_len=4, nullable=False, index=True)