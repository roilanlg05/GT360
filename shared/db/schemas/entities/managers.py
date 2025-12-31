from psqlmodel import PSQLModel, table, Column
from psqlmodel.orm.types import uuid

@table(name="managers", schema="entities")
class Manager(PSQLModel):

    id: uuid = Column(
        foreign_key="entities.users.id", 
        on_delete="CASCADE", 
        nullable=False, 
        primary_key=True
    )

    organization_id: uuid = Column(
        default=None, 
        foreign_key="entities.organizations.id", 
        on_delete="CASCADE",
        index=True,
        nullable=True,
        unique=True
    )