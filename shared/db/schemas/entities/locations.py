from psqlmodel import PSQLModel, table, Column, CheckConstraint
from psqlmodel.orm.types import jsonb, timestamptz, uuid
from psqlmodel.utils import gen_default_uuid, now


# Visibility zone constants
MAX_RADIUS = 1.0  # 1 millas maximo

class ValidationStatus:
    NEEDS_VALIDATION = "NEEDS_VALIDATION"
    VALIDATED = "VALIDATED"
    DISABLED = "DISABLED"



@table("locations", 
        schema="entities",
        constraints=[
            CheckConstraint("radio_zone IS NULL OR radio_zone <= 1.0", name="ck_location_max_radius")
        ]
)
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

    address: str = Column(default=None, max_len=255)

    radio_zone: float = Column(default=None)

    validation_status: str = Column(default=ValidationStatus.NEEDS_VALIDATION, max_len=50)

    provider: str = Column(default=None, max_len=15)

    created_at: timestamptz = Column(default=now)   

    timezone: str = Column(default="America/New_York", max_len=255)