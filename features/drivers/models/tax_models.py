from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional, List
from uuid import UUID
from decimal import Decimal


class SubmitTaxInformationRequest(BaseModel):
    """Request to submit W-9 tax information (used with form-data)."""
    legal_first_name: str
    legal_middle_name: Optional[str] = None
    legal_last_name: str
    tin_type: str = Field(description="'SSN' or 'EIN'")
    tin: str = Field(description="SSN (XXX-XX-XXXX) or EIN (XX-XXXXXXX)")
    address_street: str
    address_city: str
    address_state: str = Field(min_length=2, max_length=2)
    address_zip: str
    address_country: str = Field(default="US")


class TaxInformationResponse(BaseModel):
    """Response model for tax information."""
    tax_info_id: UUID
    driver_id: UUID
    tin_type: str
    tin_masked: str = Field(description="Masked TIN for display (e.g., ***-**-4321)")
    legal_name: str
    address: str
    w9_submitted: bool
    w9_document_url: Optional[str]
    created_at: datetime


class SubmitTaxInformationResponse(BaseModel):
    """Response when tax information is submitted."""
    status: str
    message: str
    tax_info: TaxInformationResponse


class Address(BaseModel):
    """Address model for 1099."""
    street: str
    city: str
    state: str
    zip: str


class PayerInfo(BaseModel):
    """Payer (company) information for 1099."""
    name: str
    ein: str
    address: Address
    phone: str


class RecipientInfo(BaseModel):
    """Recipient (driver) information for 1099."""
    name: str
    tin: str
    tin_type: str
    tin_masked: str
    address: Address


class Form1099Data(BaseModel):
    """1099-NEC form box data."""
    box_1_nonemployee_compensation: Decimal
    box_2_payer_made_direct_sales: Optional[Decimal]
    box_4_federal_income_tax_withheld: Decimal
    box_5_state_tax_withheld: Decimal
    box_6_state_payers_state_no: Optional[str]
    box_7_state_income: Decimal


class EarningsBreakdown(BaseModel):
    """Breakdown of earnings for 1099."""
    total_gross_earnings: Decimal
    total_hours_worked: float
    total_days_worked: int
    total_trips: int
    pay_type: str
    rate: Decimal


class ExpensesSummary1099(BaseModel):
    """Summary of expenses (not included in 1099)."""
    total_expenses_reimbursed: Decimal
    note: str = "Expenses are business reimbursements and not included in Box 1"


class PaymentSummary(BaseModel):
    """Payment summary for 1099."""
    total_gross_earnings: Decimal
    total_expenses_reimbursed: Decimal
    total_paid_to_driver: Decimal
    total_reported_on_1099: Decimal


class PeriodBreakdown(BaseModel):
    """Breakdown of earnings by period."""
    period: str
    gross_earnings: Decimal
    expenses_reimbursed: Decimal
    net_pay: Decimal
    hours_worked: float


class Compliance(BaseModel):
    """Compliance information for 1099."""
    minimum_reporting_threshold: Decimal
    requires_1099: bool
    form_due_date: date
    recipient_copy_due_date: date


class Form1099Response(BaseModel):
    """Complete 1099-NEC response."""
    form_type: str
    tax_year: int
    generated_at: datetime

    payer: PayerInfo
    recipient: RecipientInfo

    form_data: Form1099Data
    earnings_breakdown: EarningsBreakdown
    expenses_summary: ExpensesSummary1099
    payment_summary: PaymentSummary

    periods_breakdown: List[PeriodBreakdown]
    compliance: Compliance


# Manager bulk 1099 models

class Driver1099Summary(BaseModel):
    """Summary of a driver's 1099 for bulk view."""
    driver_id: UUID
    driver_name: str
    tin: str = Field(description="Partially masked TIN")
    box_1_amount: Decimal
    expenses_reimbursed: Decimal
    total_paid: Decimal
    requires_1099: bool
    has_tax_info: bool
    download_url: str


class Bulk1099Response(BaseModel):
    """Response for bulk 1099 data."""
    tax_year: int
    generated_at: datetime
    total_drivers: int
    total_earnings_reported: Decimal
    total_expenses_reimbursed: Decimal
    total_paid_to_drivers: Decimal

    drivers: List[Driver1099Summary]
    bulk_download_url: str


class GenerateAll1099Request(BaseModel):
    """Request to generate all 1099 PDFs."""
    year: int
    min_earnings: Decimal = Field(default=Decimal("600.00"))


class GenerateAll1099Response(BaseModel):
    """Response when bulk 1099 generation starts."""
    status: str
    message: str
    job_id: UUID
    total_drivers: int
    estimated_completion: datetime
