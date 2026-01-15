from psqlmodel import PSQLModel, Column, table, Index
from psqlmodel.orm.types import uuid, timestamptz
from psqlmodel.utils import gen_default_uuid, now


class EventType:
    """Tipos de evento de geofencing."""
    ENTER = "ENTER"
    DWELL = "DWELL"
    EXIT = "EXIT"


class ActorType:
    """Tipos de actor que pueden generar eventos."""
    DRIVER = "driver"
    CREW = "crew"


class TargetType:
    """Tipos de target para geofencing."""
    HOTEL = "hotel"
    AIRPORT = "airport"


@table(
    "geofence_events",
    schema="geofencing",
    indexes=[
        Index("idx_geofence_events_actor", "actor_type", "actor_id"),
        Index("idx_geofence_events_target", "target_type", "target_id"),
        Index("idx_geofence_events_location", "location_id"),
        Index("idx_geofence_events_org", "organization_id"),
        Index("idx_geofence_events_created", "created_at"),
    ]
)
class GeofenceEvent(PSQLModel):
    """
    Registro de eventos de geofencing.

    Cada vez que un actor (Driver/Crew) entra, permanece (DWELL) o sale
    de un geofence (Hotel/Airport), se crea un registro aquí.
    """

    id: uuid = Column(primary_key=True, default=gen_default_uuid)

    # Actor (quien genera el evento)
    actor_type: str = Column(max_len=20, nullable=False)  # 'driver' | 'crew'
    actor_id: uuid = Column(foreign_key='entities.users.id', nullable=False, on_delete='CASCADE')

    # Target (geofence donde ocurre el evento)
    target_type: str = Column(max_len=20, nullable=False)  # 'hotel' | 'airport'
    target_id: uuid = Column(nullable=False)  # ID del hotel o airport

    # Scope (jerarquía organizacional)
    location_id: uuid = Column(foreign_key='entities.locations.id', nullable=False, on_delete='CASCADE')
    organization_id: uuid = Column(foreign_key='entities.organizations.id', nullable=False, on_delete='CASCADE')

    # Tipo de evento
    event_type: str = Column(max_len=10, nullable=False)  # 'ENTER' | 'DWELL' | 'EXIT'

    # Ubicación reportada al momento del evento
    reported_lat: float = Column(nullable=False)
    reported_lon: float = Column(nullable=False)
    distance_to_center: float = Column(nullable=False)  # Distancia en metros al centro del geofence

    # Para eventos DWELL: minutos acumulados dentro del geofence
    dwell_minutes: int = Column(nullable=True)

    # Para eventos EXIT: tiempo total dentro del geofence (segundos)
    total_time_inside_seconds: int = Column(nullable=True)

    # Timestamp
    created_at: timestamptz = Column(default=now, nullable=False)
