from psqlmodel import table, Column, PSQLModel
from psqlmodel.orm.types import uuid, jsonb, timestamptz, date
from psqlmodel.utils import gen_default_uuid, now


class FilterType:
    """Filter type constants for step filters."""
    REDUCE = "reduce"
    COMBINE = "combine"
    EXPAND = "expand"


@table("filter_steps", schema="trips")
class FilterStep(PSQLModel):
    """
    Stores individual filter steps in a stack-based system.

    This allows:
    - Order-free filter application (any order of reduce/combine/expand)
    - Per-day configuration (each step targets a specific pick_up_date)
    - Time windows per filter
    - Scalable revert by marking steps as inactive

    When a step is reverted:
    1. Mark is_active = False
    2. Recalculate all trips from original_pick_up_time
    3. Re-apply remaining active steps in step_order
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

    # Day this step applies to
    pick_up_date: date = Column(
        nullable=False,
        index=True
    )

    # Order in the stack (1, 2, 3...)
    # Used to re-apply steps in correct order after revert
    step_order: int = Column(
        nullable=False,
        index=True
    )

    # Filter type: "reduce", "combine", "expand"
    filter_type: str = Column(
        max_len=20,
        nullable=False,
        index=True
    )

    # Filter configuration (parameters specific to filter type)
    # {
    #   "minutes_to_reduce": 15,  # For reduce
    #   "min_gap": 10, "max_gap": 20,  # For combine/expand
    #   "max_shift": 10,  # For expand
    #   "hotel_names": ["Hotel A", "Hotel B"]  # Optional
    # }
    config: jsonb = Column(nullable=False)

    # Time windows for this step
    # [
    #   {"start": "00:00", "end": "12:00", "enabled": true},
    #   {"start": "12:00", "end": "24:00", "enabled": false}
    # ]
    windows: jsonb = Column(nullable=False)

    # Number of trips modified by this step
    trips_affected: int = Column(
        nullable=False,
        default=0
    )

    # When this step was created/applied
    created_at: timestamptz = Column(
        default=now,
        nullable=False,
        index=True
    )

    # False if step was reverted
    is_active: bool = Column(
        nullable=False,
        default=True,
        index=True
    )

    # Unique constraint: one step per location+airline+date+order
    class Config:
        unique_together = [("location_id", "airline", "pick_up_date", "step_order")]
