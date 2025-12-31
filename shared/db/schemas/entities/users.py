from psqlmodel import Column, PSQLModel, table
from psqlmodel.utils import gen_default_uuid, now
from psqlmodel.orm.types import timestamptz, uuid

@table(name="users", schema="entities")
class User(PSQLModel):

    id: uuid = Column(default=gen_default_uuid, primary_key=True)
    full_name: str = Column(nullable=True, index=True)
    email: str = Column(nullable=False, unique=True, index=True)
    password_hash: str = Column(nullable=False)
    phone: str = Column(default=None, unique=True)
    profile_pic: str = Column(default=None, unique=True)
    role: str = Column(nullable=False, index=True)

    email_verified_at: timestamptz = Column(
        default=None, 
        nullable=True, 
        index=True
        )
    
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

    password_reset_nonce: str | None = Column(
        default=None, 
        index=True
    )