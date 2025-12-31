from psqlmodel import PSQLModel, table, Column
from psqlmodel.orm.types import uuid
from psqlmodel.utils import gen_default_uuid

@table(name="crew", schema="entities")
class Crew(PSQLModel):

    id: uuid = Column(
        foreign_key="entities.users.id", on_delete="CASCADE",
        nullable=False,
        primary_key=True
    )

    airline: str = Column(default=None, description="Código AA, WN, DL...", index=True)
