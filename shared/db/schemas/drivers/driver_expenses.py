from psqlmodel import PSQLModel, table, Column
from psqlmodel.orm.types import uuid, timestamptz, varchar, text, boolean, decimal, date
from psqlmodel.utils import gen_default_uuid, now


class ExpenseType:
    """Expense type constants."""
    GAS = "gas"
    MAINTENANCE = "maintenance"
    PARKING = "parking"
    TOLLS = "tolls"
    CAR_WASH = "car_wash"
    SUPPLIES = "supplies"
    OTHER = "other"


class ExpenseStatus:
    """Expense status constants."""
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


@table("driver_expenses", schema="drivers")
class DriverExpense(PSQLModel):
    """
    Driver expense reimbursements.
    Tracks expenses submitted by drivers for approval and reimbursement.
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

    # Expense details
    amount: decimal = Column(
        nullable=False
    )

    expense_type: varchar = Column(
        max_len=50,
        nullable=False,
        index=True
    )

    description: text = Column(
        nullable=True
    )

    expense_date: date = Column(
        nullable=False,
        index=True
    )

    # Receipt
    receipt_photo_url: text = Column(
        nullable=True
    )

    receipt_uploaded: boolean = Column(
        default=False,
        nullable=False
    )

    # Review system
    status: varchar = Column(
        max_len=20,
        default=ExpenseStatus.PENDING,
        nullable=False,
        index=True
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

    rejection_reason: text = Column(
        nullable=True
    )

    # Payment period
    pay_period_start: date = Column(
        nullable=True,
        index=True
    )

    pay_period_end: date = Column(
        nullable=True,
        index=True
    )

    included_in_payment: boolean = Column(
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
