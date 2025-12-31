from psqlmodel import PSQLModel, table, Column
from psqlmodel.orm.types import uuid

@table("supervisors", schema="entities")
class Supervisor(PSQLModel):

    id: uuid = Column(foreign_key="entities.users.id", primary_key=True)
    
    organization_id: uuid = Column(
        foreign_key="entities.organizations.id", 
        nullable=False, 
        on_delete="SET NULL",
        unique=True
    )
    location_id: uuid = Column(
        foreign_key="entities.locations.id", 
        nullable=False, 
        on_delete="SET NULL"
    )

    profile_pic_url: str = Column(unique=True)
