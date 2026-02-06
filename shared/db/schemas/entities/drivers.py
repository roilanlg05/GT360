from psqlmodel import PSQLModel, table, Column
from psqlmodel.orm.types import jsonb, uuid


class PayType:
    """Pay type constants for drivers."""
    DAY = "day"
    HOUR = "hour"
    TRIP = "trip"


@table("drivers", schema="entities")
class Driver(PSQLModel):

    id: uuid = Column(
        foreign_key="entities.users.id",
        on_delete="CASCADE",
        nullable=False,
        primary_key=True
    )

    is_active: bool = Column(
        default=False,
        nullable=False,
        index=True
    )

    point: jsonb = Column(
        default=None
    )

    location_id: uuid = Column(
        default=None,
        foreign_key="entities.locations.id",
        on_delete="SET NULL",
        nullable=True,
        index=True,
    )


    organization_id: uuid = Column(
        default=None,
        foreign_key = "entities.organizations.id",
        on_delete="CASCADE",
        index=True,
    )

    pay_type: str = Column(
        max_len=10,
        default=None,
        nullable=True,
        index=True,
    )

    profile_pic_url: str = Column(unique=True)
