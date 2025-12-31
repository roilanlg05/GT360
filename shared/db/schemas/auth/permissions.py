from psqlmodel import PSQLModel, table, Column
from psqlmodel.orm.types import uuid
from psqlmodel.utils import gen_default_uuid

@table("permissions", schema="auth")
class Permission(PSQLModel):
    id: uuid = Column(default=gen_default_uuid, primary_key=True)
    name: str = Column(nullable=False, index=True)
    description: str = Column(default=None)