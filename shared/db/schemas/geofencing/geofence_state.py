from psqlmodel import PSQLModel, Column, table, UniqueConstraint, Index
from psqlmodel.orm.types import uuid, timestamptz
from psqlmodel.utils import gen_default_uuid, now


@table(
    "geofence_states",
    schema="geofencing",
    constraints=[
        UniqueConstraint("actor_type", "actor_id", "target_type", "target_id", name="uq_geofence_state_actor_target")
    ],
    indexes=[
        Index("idx_geofence_state_actor", "actor_type", "actor_id"),
        Index("idx_geofence_state_inside", "is_inside"),
    ]
)
class GeofenceState(PSQLModel):
    """
    Estado actual de un actor en relación a un geofence específico.

    Esta tabla implementa el mecanismo anti-jitter para evitar eventos
    duplicados causados por ruido de GPS. Mantiene contadores de lecturas
    consecutivas dentro/fuera del geofence antes de emitir eventos.

    Anti-jitter Logic:
    - Solo emite ENTER después de N lecturas consecutivas dentro
    - Solo emite EXIT después de N lecturas consecutivas fuera
    - Respeta cooldown entre eventos para evitar ping-pong
    """

    id: uuid = Column(primary_key=True, default=gen_default_uuid)

    # Actor
    actor_type: str = Column(max_len=20, nullable=False)  # 'driver' | 'crew'
    actor_id: uuid = Column(foreign_key='entities.users.id', nullable=False, on_delete='CASCADE')

    # Target
    target_type: str = Column(max_len=20, nullable=False)  # 'hotel' | 'airport'
    target_id: uuid = Column(nullable=False)  # ID del hotel o airport

    # Estado actual confirmado
    is_inside: bool = Column(default=False, nullable=False)

    # Contadores anti-jitter (lecturas consecutivas)
    consecutive_inside_count: int = Column(default=0, nullable=False)
    consecutive_outside_count: int = Column(default=0, nullable=False)

    # Timestamps de eventos
    last_enter_at: timestamptz = Column(nullable=True)  # Última vez que entró
    last_exit_at: timestamptz = Column(nullable=True)   # Última vez que salió
    last_dwell_at: timestamptz = Column(nullable=True)  # Último evento DWELL

    # Última posición procesada
    last_position_at: timestamptz = Column(default=now, nullable=False)
    last_lat: float = Column(nullable=True)
    last_lon: float = Column(nullable=True)
    last_distance: float = Column(nullable=True)  # Distancia al centro en millas
