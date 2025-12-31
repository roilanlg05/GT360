from psqlmodel import PSQLModel, table, Column
from psqlmodel.orm.types import timestamptz, uuid
from psqlmodel.utils import gen_default_uuid, now

@table("tokens", schema="auth")
class Token(PSQLModel):

    id: uuid = Column(
        default=gen_default_uuid,
        primary_key=True
    )

    user_id: uuid = Column(
        foreign_key="entities.users.id", 
        on_delete="CASCADE",
        nullable=False,
        index=True
    )

    token_hash: str = Column(nullable=False)

    token_type: str = Column(nullable=False)

    expires_at: timestamptz = Column(
        nullable=False, 
        index=True
    )

    revoked: bool = Column(default=False, nullable=False, index=True)

    created_at: timestamptz = Column(
        default=now,
        nullable=False, 
        index=True
    )