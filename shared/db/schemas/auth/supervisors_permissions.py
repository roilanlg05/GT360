from psqlmodel import PSQLModel, table, Column
from psqlmodel.orm.types import jsonb, timestamptz, uuid
from psqlmodel.utils import gen_default_uuid, now


@table("supervisors_permissions", schema="auth")
class SupervisorsPermission(PSQLModel):
    user_id: uuid = Column(foreign_key="entities.supervisors.id", nullable=False)
    permission_id: uuid = Column(foreign_key="auth.permissions.id", nullable=False)
    granted_at: timestamptz = Column(default=now)