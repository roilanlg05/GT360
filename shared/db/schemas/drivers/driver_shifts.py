from psqlmodel import PSQLModel, table, Column
from psqlmodel.orm.types import uuid, timestamptz, varchar, text, boolean, decimal, time
from psqlmodel.utils import gen_default_uuid, now


class ShiftStatus:
    """Shift status constants."""
    ACTIVE = "active"
    COMPLETED = "completed"
    AUTO_CLOSED = "auto_closed"
    UNDER_REVIEW = "under_review"
    REVIEWED = "reviewed"


class ReviewStatus:
    """Review status constants."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@table("driver_shifts", schema="drivers")
class DriverShift(PSQLModel):
    """
    Driver work shifts tracking.
    Records when drivers start and end their work sessions.
    """

    id: uuid = Column(
        primary_key=True,
        default=gen_default_uuid,
        nullable=False
    )

    driver_id: uuid = Column(
        foreign_key="entities.drivers.id",
        on_delete="CASCADE",
        nullable=False,
        index=True
    )

    # Pay snapshot at shift start
    pay_type: varchar = Column(
        max_len=10,
        nullable=True
    )

    rate: decimal = Column(
        nullable=True
    )

    # Schedule snapshot (captured at shift start)
    shift_start_time: time = Column(
        nullable=True
    )

    shift_end_time: time = Column(
        nullable=True
    )

    started_at: timestamptz = Column(
        nullable=False,
        index=True
    )

    ended_at: timestamptz = Column(
        nullable=True
    )

    # Status
    status: varchar = Column(
        max_len=20,
        default=ShiftStatus.ACTIVE,
        nullable=False,
        index=True
    )

    # Review system
    review_status: varchar = Column(
        max_len=20,
        nullable=True,
        index=True
    )

    review_reason: text = Column(
        nullable=True
    )

    reviewed_at: timestamptz = Column(
        nullable=True
    )

    reviewed_by: uuid = Column(
        foreign_key="entities.users.id",
        on_delete="SET NULL",
        nullable=True
    )

    manager_notes: text = Column(
        nullable=True
    )

    auto_closed: boolean = Column(
        default=False,
        nullable=False
    )

    created_at: timestamptz = Column(
        default=now,
        nullable=False
    )

    updated_at: timestamptz = Column(
        default=now,
        nullable=False
    )
