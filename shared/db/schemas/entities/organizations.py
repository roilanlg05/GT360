from psqlmodel import PSQLModel, table, Column
from psqlmodel.orm.types import timestamptz, uuid
from psqlmodel.utils import gen_default_uuid, now


@table("organizations", schema="entities")
class Organization(PSQLModel):

    id: uuid = Column(
        default=gen_default_uuid,
        primary_key=True
    )

    manager_id: uuid = Column(
        default=None,
        foreign_key = "entities.managers.id", 
        on_delete="CASCADE",  
        index=True,
        nullable=True,
        unique=True
    )

    name: str = Column(nullable=False, index=True, unique=True)

    address: str = Column(default=None, nullable=False)

    website: str | None = Column(default=None)

    plan: str = Column(default="freemium", nullable=False, index=True)

    status: str = Column(default=None, index=True)

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
