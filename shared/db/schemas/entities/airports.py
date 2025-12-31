from psqlmodel import table, Column, PSQLModel, UniqueConstraint, CheckConstraint
from psqlmodel.orm.types import uuid
from psqlmodel.utils import gen_default_uuid


@table('airports', schema="entities", constraints=[
        UniqueConstraint("code", name="uq_airport_code"),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_airport_lat"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_airport_lon"),
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