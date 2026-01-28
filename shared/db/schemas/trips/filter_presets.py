from psqlmodel import table, Column, PSQLModel
from psqlmodel.orm.types import uuid, jsonb, timestamptz
from psqlmodel.utils import gen_default_uuid, now


@table("filter_presets", schema="trips")
class FilterPreset(PSQLModel):
    """
    Global filter preset per Location + Airline.

    Stores a "stack template" that can be auto-applied to new days
    when trips are imported.

    Benefits:
    - Auto-apply filters on import without manual intervention
    - Consistent filter config across days
    - Manager sets it once, applies forever

    Lifecycle:
    - Persists even if trips are deleted
    - Deleted when location is deleted (FK CASCADE)
    """

    id: uuid = Column(
        default=gen_default_uuid,
        primary_key=True
    )

    location_id: uuid = Column(
        foreign_key="entities.locations.id",
        on_delete="CASCADE",
        nullable=False,
        index=True,
    )

    airline: str = Column(
        max_len=10,
        nullable=False,
        index=True
    )

    # Stack template: array of step templates
    # [
    #   {
    #     "filter_type": "reduce",
    #     "windows": [
    #       {"start": "05:00", "end": "10:00", "enabled": true, "minutes_to_reduce": 10}
    #     ]
    #   },
    #   {
    #     "filter_type": "combine",
    #     "windows": [
    #       {"start": "00:00", "end": "24:00", "enabled": true, "min_gap": 10, "max_gap": 20}
    #     ]
    #   }
    # ]
    stack_template: jsonb = Column(nullable=False)

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

    created_by: uuid = Column(
        default=None,
        foreign_key="entities.users.id",
        on_delete="SET NULL",
        nullable=True,
    )

    # Unique constraint: one preset per location+airline
    class Config:
        unique_together = [("location_id", "airline")]
