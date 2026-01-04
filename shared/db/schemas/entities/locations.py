from psqlmodel import PSQLModel, table, Column
from psqlmodel.orm.types import jsonb, timestamptz, uuid
from psqlmodel.utils import gen_default_uuid, now



@table("locations", schema="entities")
class Location(PSQLModel):

    id: uuid = Column(
        default=gen_default_uuid,
        primary_key=True
    )

    organization_id: uuid = Column(
        foreign_key="entities.organizations.id", 
        on_delete="CASCADE",
        nullable=False,
        index=True
    )

    name: str = Column(nullable=False, index=True)

    point: jsonb = Column(default=None)

    radio_zone: float = Column(default=None)

    created_at: timestamptz = Column(default=now)

    timezone: str = Column(default="America/New_York")