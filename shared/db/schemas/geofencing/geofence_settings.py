from psqlmodel import PSQLModel, Column, table, CheckConstraint
from psqlmodel.orm.types import uuid, timestamptz
from psqlmodel.utils import gen_default_uuid, now


# Valores por defecto
DEFAULT_DWELL_INTERVAL_MINUTES = 5
DEFAULT_MIN_CONSECUTIVE_READINGS = 3
DEFAULT_COOLDOWN_SECONDS = 30


@table(
    "geofence_settings",
    schema="geofencing",
    constraints=[
        CheckConstraint("dwell_interval_minutes >= 1 AND dwell_interval_minutes <= 60", name="ck_dwell_interval_range"),
        CheckConstraint("min_consecutive_readings >= 1 AND min_consecutive_readings <= 10", name="ck_consecutive_range"),
        CheckConstraint("cooldown_seconds >= 10 AND cooldown_seconds <= 300", name="ck_cooldown_range"),
    ]
)
class GeofenceSettings(PSQLModel):
    """
    Configuración de geofencing por organización.

    Permite personalizar:
    - Intervalo de eventos DWELL (cada cuántos minutos emitir)
    - Lecturas consecutivas mínimas para anti-jitter
    - Cooldown entre eventos ENTER/EXIT

    Defaults razonables:
    - DWELL cada 5 minutos
    - 3 lecturas consecutivas para confirmar entrada/salida
    - 30 segundos de cooldown entre eventos
    """

    id: uuid = Column(primary_key=True, default=gen_default_uuid)

    # Una configuración por organización
    organization_id: uuid = Column(
        foreign_key='entities.organizations.id',
        nullable=False,
        unique=True,
        on_delete='CASCADE'
    )

    # Configuración DWELL
    dwell_interval_minutes: int = Column(
        default=DEFAULT_DWELL_INTERVAL_MINUTES,
        nullable=False
    )

    # Configuración anti-jitter
    min_consecutive_readings: int = Column(
        default=DEFAULT_MIN_CONSECUTIVE_READINGS,
        nullable=False
    )

    # Cooldown entre eventos (evita ping-pong)
    cooldown_seconds: int = Column(
        default=DEFAULT_COOLDOWN_SECONDS,
        nullable=False
    )

    # Auditoría
    created_at: timestamptz = Column(default=now, nullable=False)
    updated_at: timestamptz = Column(default=now, nullable=False)
    updated_by: uuid = Column(foreign_key='entities.users.id', nullable=True, on_delete='SET NULL')
