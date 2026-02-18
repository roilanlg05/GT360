from psqlmodel import table, Column, PSQLModel
from psqlmodel.orm.types import uuid, timestamptz
from psqlmodel.utils import gen_default_uuid, now


@table("trip_reviews", schema="reviews")
class TripReview(PSQLModel):

    id: uuid = Column(
        default=gen_default_uuid,
        primary_key=True
    )

    # SIN FK CASCADE porque trips se borran al archivarse
    trip_id: uuid = Column(
        nullable=False,
        index=True,
    )

    # Para correlacionar con trips_history despues del archivado
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

    location_id: uuid = Column(
        foreign_key="entities.locations.id",
        on_delete="CASCADE",
        nullable=False,
        index=True,
    )

    # Flags de revision
    review_pickup: bool = Column(
        default=False,
        nullable=False,
        index=True,
    )

    review_dropoff: bool = Column(
        default=False,
        nullable=False,
        index=True,
    )

    # Timestamps de cuando se flageo
    pickup_flagged_at: timestamptz = Column(
        default=None,
        nullable=True,
    )

    dropoff_flagged_at: timestamptz = Column(
        default=None,
        nullable=True,
    )

    # Timestamps de revision por manager
    pickup_reviewed_at: timestamptz = Column(
        default=None,
        nullable=True,
    )

    dropoff_reviewed_at: timestamptz = Column(
        default=None,
        nullable=True,
    )

    # Quien reviso
    pickup_reviewed_by: uuid = Column(
        default=None,
        foreign_key="entities.users.id",
        on_delete="SET NULL",
        nullable=True,
    )

    dropoff_reviewed_by: uuid = Column(
        default=None,
        foreign_key="entities.users.id",
        on_delete="SET NULL",
        nullable=True,
    )

    created_at: timestamptz = Column(
        default=now,
        nullable=False,
        index=True,
    )

    updated_at: timestamptz = Column(
        default=now,
        nullable=False,
        index=True,
    )
