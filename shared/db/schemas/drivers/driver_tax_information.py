from psqlmodel import PSQLModel, table, Column
from psqlmodel.orm.types import uuid, timestamptz, varchar, text, boolean, decimal
from psqlmodel.utils import gen_default_uuid, now


class TINType:
    """TIN (Taxpayer Identification Number) type constants."""
    SSN = "SSN"  # Social Security Number
    EIN = "EIN"  # Employer Identification Number


@table("driver_tax_information", schema="drivers")
class DriverTaxInformation(PSQLModel):
    """
    Driver tax information for 1099 generation.
    Stores W-9 data required by IRS for tax reporting.
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
        unique=True,
        index=True
    )

    # TIN (Taxpayer Identification Number)
    # NOTE: This should be encrypted at the application level
    tin_type: varchar = Column(
        max_len=10,
        nullable=False
    )

    tin: varchar = Column(
        max_len=20,
        nullable=False
    )

    # Legal name for 1099
    legal_first_name: varchar = Column(
        max_len=100,
        nullable=False
    )

    legal_middle_name: varchar = Column(
        max_len=100,
        nullable=True
    )

    legal_last_name: varchar = Column(
        max_len=100,
        nullable=False
    )

    # Address for 1099
    address_street: varchar = Column(
        max_len=255,
        nullable=False
    )

    address_city: varchar = Column(
        max_len=100,
        nullable=False
    )

    address_state: varchar = Column(
        max_len=2,
        nullable=False
    )

    address_zip: varchar = Column(
        max_len=10,
        nullable=False
    )

    address_country: varchar = Column(
        max_len=2,
        default="US",
        nullable=False
    )

    # W-9 document
    w9_submitted: boolean = Column(
        default=False,
        nullable=False
    )

    w9_submitted_at: timestamptz = Column(
        nullable=True
    )

    w9_document_url: text = Column(
        nullable=True
    )

    # Backup withholding
    backup_withholding_rate: decimal = Column(
        default=0.00,
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
