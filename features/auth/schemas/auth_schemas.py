from psqlmodel import PSQLModel, table, Column, Relation, Relationship
from psqlmodel.orm.types import jsonb, timestamptz, uuid
from psqlmodel.utils import gen_default_uuid, now

@table(name="users", schema="auth")
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
    
    manager: Relation["Manager"] = Relationship(cascade=True)
    crew: Relation["Crew"] = Relationship(cascade=True)

    

@table(name="managers", schema="auth")
class Manager(PSQLModel):

    id: uuid = Column(foreign_key=User.id, on_delete="CASCADE", nullable=False, primary_key=True)
    organization_id: uuid = Column(
        default=None, 
        foreign_key="organizations.id", 
        on_delete="CASCADE",
        index=True,
        nullable=True,
        unique=True
    )

    profile_pic_url: str = Column(unique=True)

    user: Relation[User] = Relationship(cascade=True)

@table(name="crew", schema="auth")
class Crew(PSQLModel):

    id: uuid = Column(
        foreign_key=User.id, on_delete="CASCADE",
        nullable=False,
        primary_key=True
    )

    airline: str = Column(default=None, description="Código AA, WN, DL...", index=True)

    user: Relation[User] = Relationship(cascade=True)

@table("drivers", schema="auth")
class Driver(PSQLModel):

    id: uuid = Column(
        foreign_key=User.id, 
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
        foreign_key = "locations.id", 
        on_delete="CASCADE",
        index=True,
    )

    profile_pic_url: str = Column(unique=True)

    user: Relation[User] = Relationship(cascade=True)

@table("supervisors", schema="auth")
class Supervisor(PSQLModel):

    id: uuid = Column(foreign_key=User.id, primary_key=True, unique=True)
    
    organization_id: uuid = Column(
        foreign_key="organizations.id", 
        nullable=False, 
        on_delete="SET NULL",
        unique=True
    )
    location_id: uuid = Column(
        foreign_key="locations.id", 
        nullable=False, 
        on_delete="SET NULL"
    )

    profile_pic_url: str = Column(unique=True)

    user: Relation[User] = Relationship(cascade=True)
    permissions: Relation[list["Permission"]] = Relationship(secondary="supervisors_permissions", cascade=True)

@table("permissions", schema="auth")
class Permission(PSQLModel):
    id: uuid = Column(default=gen_default_uuid, primary_key=True)
    name: str = Column(nullable=False, index=True)
    description: str = Column(default=None)

    supervisors: Relation[list[Supervisor]] = Relationship(secondary="supervisors_permissions", cascade=True)

@table("supervisors_permissions", schema="auth")
class SupervisorsPermission(PSQLModel):
    user_id: uuid = Column(foreign_key="auth.supervisors.id")
    permission_id: uuid = Column(foreign_key="auth.permissions.id")

@table("tokens", schema="auth")
class Token(PSQLModel):

    id: uuid = Column(
        default=gen_default_uuid,
        primary_key=True
    )

    user_id: uuid = Column(
        foreign_key=User.id, 
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

@table("organizations")
class Organization(PSQLModel):

    id: uuid = Column(
        default=gen_default_uuid,
        primary_key=True
    )

    manager_id: uuid = Column(
        default=None,
        foreign_key = Manager.id, 
        on_delete="SET NULL",  # <-- SET NULL para no borrar la organización
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

    drivers: Relation[list[Driver]] = Relationship(cascade=True)

    manager: Relation[Manager] = Relationship(cascade=True)

    supervisors: Relation[list[Supervisor]] = Relationship(cascade=True)



@table("locations")
class Location(PSQLModel):

    id: uuid = Column(
        default=gen_default_uuid,
        primary_key=True
    )

    organization_id: uuid = Column(
        foreign_key="organizations.id", 
        on_delete="CASCADE",
        nullable=False,
        index=True,
        unique=True
    )

    name: str = Column(nullable=False, index=True)

    point: jsonb = Column(
        default=None
    )
