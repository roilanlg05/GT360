from psqlmodel import table, Column, PSQLModel, UniqueConstraint, CheckConstraint
from psqlmodel.orm.types import uuid, timestamptz
from psqlmodel.utils import gen_default_uuid


# Radio por defecto: 1 milla
DEFAULT_AIRPORT_RADIUS = 1.0

# Radio máximo: 2 millas (mismo que hoteles)
MAX_RADIUS = 2.0


@table('airports', schema="entities", constraints=[
        UniqueConstraint("code", name="uq_airport_code"),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_airport_lat"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_airport_lon"),
        CheckConstraint("radio_zone IS NULL OR radio_zone <= 2.0", name="ck_airport_max_radius"),
    ]
)
class Airport(PSQLModel):

    id: uuid = Column(
        default=gen_default_uuid,
        primary_key=True
    )

    code: str = Column(max_len=10, nullable=False, index=True, unique=True)

    name: str = Column(max_len=150, nullable=False)

    latitude: float = Column(nullable=False)

    longitude: float = Column(nullable=False)

    country_code: str = Column(max_len=5, nullable=False, index=True)

    zone_code: str = Column(max_len=4, nullable=False, index=True)

    # Geofencing: radio de la zona (en millas)
    radio_zone: float = Column(default=DEFAULT_AIRPORT_RADIUS, nullable=True)

    # Auditoría de modificaciones
    last_modified_at: timestamptz = Column(nullable=True)
    last_modified_by: uuid = Column(foreign_key='entities.users.id', nullable=True, on_delete='SET NULL')