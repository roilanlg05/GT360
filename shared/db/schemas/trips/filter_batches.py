from psqlmodel import table, Column, PSQLModel
from psqlmodel.orm.types import uuid, jsonb, timestamptz
from psqlmodel.utils import gen_default_uuid, now


@table("filter_batches", schema="trips")
class FilterBatch(PSQLModel):
    """
    Stores metadata about filter application batches.

    This table tracks which filters were applied in each batch,
    allowing for partial revert (reverting only specific filters).

    When a filter batch is applied:
    1. Create a FilterBatch record with the configuration
    2. Apply filters to trips with that batch_id
    3. For partial revert: fetch config, modify it, revert trips, re-apply
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

    # Store the full FilterRequest configuration as JSON
    # {
    #   "pick_up_date_from": "2026-01-15",
    #   "pick_up_date_to": "2026-01-31",
    #   "rounding_mode": "multiple_of_5",
    #   "reduce": {"enabled": true, "minutes_to_reduce": 20, ...},
    #   "combine": {"enabled": true, "min_gap": 10, ...},
    #   "expand": {"enabled": true, "min_gap": 21, ...}
    # }
    config: jsonb = Column(nullable=False)

    # Track which filters were actually applied (for quick lookup)
    # ["reduce", "combine", "expand"] or subset
    filters_applied: jsonb = Column(nullable=False)

    # Number of trips affected in this batch
    trips_affected: int = Column(nullable=False, default=0)

    # When this batch was created/applied
    created_at: timestamptz = Column(
        default=now,
        nullable=False,
        index=True
    )

    # Track partial reverts
    # {"reduce": {"reverted_at": "2026-01-17T10:30:00Z", "trips_reverted": 5}, ...}
    revert_history: jsonb = Column(
        nullable=True,
        default=None
    )
