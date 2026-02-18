from psqlmodel import PSQLModel, table, Column
from psqlmodel.orm.types import uuid, timestamptz, varchar, text, boolean, decimal, integer
from psqlmodel.utils import gen_default_uuid, now


class DeliveryMethod:
    """1099 delivery method constants."""
    EMAIL = "email"
    MAIL = "mail"
    PORTAL = "portal"


@table("form_1099_archive", schema="drivers")
class Form1099Archive(PSQLModel):
    """
    Archive of generated 1099 forms.
    Stores historical 1099-NEC forms for tax compliance and record keeping.
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

    tax_year: integer = Column(
        nullable=False,
        index=True
    )

    # Form data
    form_type: varchar = Column(
        max_len=20,
        default="1099-NEC",
        nullable=False
    )

    box_1_amount: decimal = Column(
        nullable=False
    )

    box_4_federal_withholding: decimal = Column(
        default=0.00,
        nullable=False
    )

    # PDF document
    pdf_url: text = Column(
        nullable=True
    )

    pdf_generated_at: timestamptz = Column(
        nullable=True
    )

    # IRS submission
    submitted_to_irs: boolean = Column(
        default=False,
        nullable=False
    )

    submitted_at: timestamptz = Column(
        nullable=True
    )

    confirmation_number: varchar = Column(
        max_len=100,
        nullable=True
    )

    # Driver delivery
    sent_to_driver: boolean = Column(
        default=False,
        nullable=False
    )

    sent_to_driver_at: timestamptz = Column(
        nullable=True
    )

    delivery_method: varchar = Column(
        max_len=20,
        nullable=True
    )

    # Metadata
    generated_by: uuid = Column(
        foreign_key="entities.users.id",
        on_delete="SET NULL",
        nullable=True
    )

    created_at: timestamptz = Column(
        default=now,
        nullable=False
    )
