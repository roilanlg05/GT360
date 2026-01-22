from psqlmodel import table, Column, PSQLModel
from psqlmodel.orm.types import uuid, jsonb, timestamptz
from psqlmodel.utils import gen_default_uuid, now


@table("filter_previews", schema="trips")
class FilterPreview(PSQLModel):
    """
    Stores the last filter preview result for a location+airline.

    This allows preview data to be shared across devices for the same account.
    The preview is replaced when a new preview is requested, and deleted when
    filters are actually applied.

    Only one preview can exist per location+airline combination (UNIQUE constraint).
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

    # Store the FilterRequest configuration that was previewed
    # {
    #   "pick_up_date_from": "2026-01-15",
    #   "pick_up_date_to": "2026-01-31",
    #   "rounding_mode": "multiple_of_5",
    #   "reduce": {"enabled": true, "minutes_to_reduce": 20, ...},
    #   "combine": {"enabled": true, "min_gap": 10, ...},
    #   "expand": {"enabled": true, "min_gap": 21, ...}
    # }
    config: jsonb = Column(nullable=False)

    # Store the preview result (changes, exclusions, summary)
    # {
    #   "changes": [...],
    #   "exclusions": [...],
    #   "summary": {"reduce": 5, "combine": 10, "expand": 3, "excluded": 2},
    #   "total_trips_evaluated": 500,
    #   "eligible_trips": 450
    # }
    result: jsonb = Column(nullable=False)

    # When this preview was created
    created_at: timestamptz = Column(
        default=now,
        nullable=False,
        index=True
    )

    # Ensure only one preview per location+airline
    class Config:
        unique_together = [("location_id", "airline")]
