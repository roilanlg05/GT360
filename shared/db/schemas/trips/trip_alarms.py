from psqlmodel import table, Column, PSQLModel, UniqueConstraint
from psqlmodel.orm.types import uuid, timestamptz, timestamp
from psqlmodel.utils import gen_default_uuid, now


@table("trip_alarms", schema="trips", constraints=[
    UniqueConstraint("trip_id", "user_id"),
])
class TripAlarm(PSQLModel):

    id: uuid = Column(
        default=gen_default_uuid,
        primary_key=True
    )

    trip_id: uuid = Column(
        foreign_key="trips.trips.id",
        on_delete="CASCADE",
        nullable=False,
        index=True,
    )

    user_id: uuid = Column(
        foreign_key="entities.users.id",
        on_delete="CASCADE",
        nullable=False,
        index=True,
    )

    alarm_at: timestamp = Column(
        nullable=False,
    )

    is_active: bool = Column(
        default=True,
        nullable=False,
        index=True,
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
