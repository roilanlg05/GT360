from psqlmodel import PSQLModel, Column, table, CheckConstraint
from psqlmodel.orm.types import uuid, timestamptz, jsonb
from psqlmodel.utils import gen_default_uuid, now


# Constantes de validación
MAX_RADIUS = 0.1 # En millas

# Estados de validación
class ValidationStatus:
    NEEDS_VALIDATION = "NEEDS_VALIDATION"
    VALIDATED = "VALIDATED"
    DISABLED = "DISABLED"


@table(
    "hotels",
    schema="entities",
    unique_together=['name', 'location_id'],
    constraints=[
        CheckConstraint("radio_zone IS NULL OR radio_zone <= 0.1", name="ck_hotel_max_radius")
    ]
)
class Hotel(PSQLModel):
    
    id: uuid = Column(primary_key=True, default=gen_default_uuid)

    name: str = Column(max_len=250, nullable=False)

    location_id: uuid = Column(foreign_key='entities.locations.id', nullable=False, on_delete='CASCADE')

    address: str = Column(max_len=250, nullable=True)

    point: jsonb = Column(nullable=True)

    radio_zone: float = Column(default=None, nullable=True)

    # Estado de validación para geofencing
    validation_status: str = Column(
        max_len=20,
        default=ValidationStatus.NEEDS_VALIDATION,
        nullable=False,
        index=True
    )

    # Auditoría de validación
    validated_at: timestamptz = Column(nullable=True)
    validated_by: uuid = Column(foreign_key='entities.users.id', nullable=True, on_delete='SET NULL')

    last_modified_at: timestamptz = Column(nullable=True)
    last_modified_by: uuid = Column(foreign_key='entities.users.id', nullable=True, on_delete='SET NULL')

    # Timestamps originales
    created_at: timestamptz = Column(default=now)
    updated_at: timestamptz = Column(default=now)

