from psqlmodel import table, Column, PSQLModel, UniqueConstraint, CheckConstraint
from psqlmodel.orm.types import uuid, jsonb, timestamptz, smallint
from psqlmodel.utils import gen_default_uuid, now


class RatingStamp:
    """Valid stamp constants for driver ratings."""
    SMOOTH_DRIVING = "smooth_driving"
    LATE = "late"
    NICE = "nice"
    PROFESSIONAL = "professional"
    CLEAN_VEHICLE = "clean_vehicle"
    RUDE = "rude"
    UNSAFE_DRIVING = "unsafe_driving"
    HELPFUL = "helpful"

    ALL = [
        SMOOTH_DRIVING, LATE, NICE, PROFESSIONAL,
        CLEAN_VEHICLE, RUDE, UNSAFE_DRIVING, HELPFUL,
    ]


@table("driver_ratings", schema="ratings")
class DriverRating(PSQLModel):

    id: uuid = Column(
        default=gen_default_uuid,
        primary_key=True
    )

    # NO FK — trips get deleted when archived to trips_history
    trip_id: uuid = Column(
        nullable=False,
        index=True,
    )

    trip_hash: str = Column(
        nullable=False,
        index=True,
    )

    driver_id: uuid = Column(
        default=None,
        foreign_key="entities.drivers.id",
        on_delete="SET NULL",
        nullable=True,
        index=True,
    )

    crew_id: uuid = Column(
        default=None,
        foreign_key="entities.users.id",
        on_delete="SET NULL",
        nullable=True,
        index=True,
    )

    score: smallint = Column(
        nullable=False,
    )

    comment: str = Column(
        default=None,
        nullable=True,
    )

    stamps: jsonb = Column(
        default=None,
        nullable=True,
    )

    created_at: timestamptz = Column(
        default=now,
        nullable=False,
        index=True,
    )
