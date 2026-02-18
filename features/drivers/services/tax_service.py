"""
Tax service - Business logic for tax information and 1099 generation.
Handles W-9 submission and 1099-NEC form generation.
"""

from datetime import datetime, timezone, date
from typing import Optional, Dict, List
from uuid import UUID
from decimal import Decimal
from psqlmodel import Select, AsyncSession
from fastapi import HTTPException
import re

from shared.db.schemas.drivers import (
    DriverTaxInformation,
    TINType,
    Form1099Archive,
    DriverShift,
    DriverExpense,
    ExpenseStatus,
    ShiftStatus,
    ReviewStatus
)
from shared.db.schemas.entities.drivers import Driver
from shared.db.schemas.entities.users import User
from .earnings_service import (
    get_completed_shifts_for_period,
    get_trips_in_shifts,
    calculate_total_hours,
    calculate_days_worked
)


def validate_tin(tin: str, tin_type: str) -> bool:
    """
    Validate TIN format.

    Args:
        tin: TIN string
        tin_type: 'SSN' or 'EIN'

    Returns:
        True if valid format
    """
    if tin_type == TINType.SSN:
        # SSN format: XXX-XX-XXXX
        pattern = r'^\d{3}-\d{2}-\d{4}$'
        return bool(re.match(pattern, tin))

    elif tin_type == TINType.EIN:
        # EIN format: XX-XXXXXXX
        pattern = r'^\d{2}-\d{7}$'
        return bool(re.match(pattern, tin))

    return False


def mask_tin(tin: str) -> str:
    """
    Mask TIN for display.

    Args:
        tin: Full TIN

    Returns:
        Masked TIN (e.g., ***-**-4321)
    """
    if '-' in tin:
        parts = tin.split('-')
        if len(parts) == 3:  # SSN
            return f"***-**-{parts[-1]}"
        elif len(parts) == 2:  # EIN
            return f"**-****{parts[-1][-3:]}"

    return "***-***"


async def submit_tax_information(
    session: AsyncSession,
    driver_id: UUID,
    tin_type: str,
    tin: str,
    legal_first_name: str,
    legal_middle_name: Optional[str],
    legal_last_name: str,
    address_street: str,
    address_city: str,
    address_state: str,
    address_zip: str,
    address_country: str,
    w9_document_url: str
) -> DriverTaxInformation:
    """
    Submit tax information (W-9) for a driver.

    Args:
        session: Database session
        driver_id: Driver UUID
        tin_type: 'SSN' or 'EIN'
        tin: TIN value
        ... other fields

    Returns:
        Created tax information

    Raises:
        HTTPException: If validation fails
    """
    # Validate driver exists
    driver = await session.exec(
        Select(Driver).Where(Driver.id == driver_id)
    ).first()

    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    # Check if tax info already exists
    existing = await session.exec(
        Select(DriverTaxInformation)
        .Where(DriverTaxInformation.driver_id == driver_id)
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Tax information already exists for this driver"
        )

    # Validate TIN type
    if tin_type not in [TINType.SSN, TINType.EIN]:
        raise HTTPException(
            status_code=400,
            detail="Invalid TIN type. Must be 'SSN' or 'EIN'"
        )

    # Validate TIN format
    if not validate_tin(tin, tin_type):
        expected_format = "XXX-XX-XXXX" if tin_type == TINType.SSN else "XX-XXXXXXX"
        raise HTTPException(
            status_code=400,
            detail=f"Invalid TIN format. Expected: {expected_format}"
        )

    # Validate state code
    if len(address_state) != 2:
        raise HTTPException(
            status_code=400,
            detail="Invalid state code. Must be 2 letters"
        )

    # TODO: Encrypt TIN before storing
    # For now, storing as-is. In production, use encryption:
    # encrypted_tin = encrypt_tin(tin)

    # Create tax information
    tax_info = DriverTaxInformation(
        driver_id=driver_id,
        tin_type=tin_type,
        tin=tin,  # Should be encrypted
        legal_first_name=legal_first_name,
        legal_middle_name=legal_middle_name,
        legal_last_name=legal_last_name,
        address_street=address_street,
        address_city=address_city,
        address_state=address_state.upper(),
        address_zip=address_zip,
        address_country=address_country.upper(),
        w9_submitted=True,
        w9_submitted_at=datetime.now(timezone.utc),
        w9_document_url=w9_document_url
    )

    session.add(tax_info)
    await session.commit()
    await session.refresh(tax_info)

    return tax_info


async def calculate_1099_data(
    session: AsyncSession,
    driver_id: UUID,
    tax_year: int
) -> Dict:
    """
    Calculate 1099-NEC data for a driver for a specific tax year.

    Args:
        session: Database session
        driver_id: Driver UUID
        tax_year: Tax year (e.g., 2026)

    Returns:
        Dictionary with 1099 form data

    Raises:
        HTTPException: If data is invalid or missing
    """
    # Get driver
    driver = await session.exec(
        Select(Driver).Where(Driver.id == driver_id)
    ).first()

    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    # Get tax information
    tax_info = await session.exec(
        Select(DriverTaxInformation)
        .Where(DriverTaxInformation.driver_id == driver_id)
    ).first()

    if not tax_info:
        raise HTTPException(
            status_code=400,
            detail="Tax information not found. Driver must complete W-9 first."
        )

    # Validate year
    current_year = date.today().year
    if tax_year > current_year:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot generate 1099 for future year {tax_year}"
        )

    # Date range for tax year
    year_start = datetime(tax_year, 1, 1, tzinfo=timezone.utc)
    year_end = datetime(tax_year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    # Get all completed and approved shifts for the year
    shifts = await get_completed_shifts_for_period(
        session,
        driver_id,
        year_start,
        year_end
    )

    # Get trips in those shifts
    trips = await get_trips_in_shifts(session, driver_id, shifts)

    # Calculate gross earnings based on pay_type
    pay_type = driver.pay_type or 'hour'
    rate = driver.rate or Decimal("10.00")  # default rate
    total_gross_earnings = Decimal("0.00")

    if pay_type == 'hour':
        total_hours = calculate_total_hours(shifts)
        total_gross_earnings = Decimal(str(total_hours)) * rate

    elif pay_type == 'day':
        total_days = calculate_days_worked(shifts)
        total_gross_earnings = Decimal(str(total_days)) * rate

    elif pay_type == 'trip':
        trips_count = len(trips)
        total_gross_earnings = Decimal(str(trips_count)) * rate

    # Get verified expenses for the year
    expenses = await session.exec(
        Select(DriverExpense)
        .Where(
            (DriverExpense.driver_id == driver_id)
            & (DriverExpense.status == ExpenseStatus.VERIFIED)
            & (DriverExpense.expense_date >= year_start.date())
            & (DriverExpense.expense_date <= year_end.date())
        )
    ).all()

    total_expenses = sum(e.amount for e in expenses)

    # Check IRS reporting threshold
    requires_1099 = total_gross_earnings >= Decimal("600.00")

    if not requires_1099:
        raise HTTPException(
            status_code=400,
            detail=f"Earnings below $600 threshold. 1099 not required. Total: ${total_gross_earnings}"
        )

    # Get driver name from User table
    user = await session.exec(
        Select(User).Where(User.id == driver_id)
    ).first()

    driver_name = f"{user.first_name} {user.last_name}" if user else "Unknown Driver"

    # Build 1099 data
    form_data = {
        'form_type': '1099-NEC',
        'tax_year': tax_year,
        'generated_at': datetime.now(timezone.utc),

        'payer': {
            'name': 'GT360 Transportation LLC',
            'ein': '12-3456789',  # TODO: Get from settings
            'address': {
                'street': '123 Business Ave',
                'city': 'Miami',
                'state': 'FL',
                'zip': '33101'
            },
            'phone': '+1-555-0100'
        },

        'recipient': {
            'name': f"{tax_info.legal_first_name} {tax_info.legal_middle_name or ''} {tax_info.legal_last_name}".strip(),
            'tin': tax_info.tin,
            'tin_type': tax_info.tin_type,
            'tin_masked': mask_tin(tax_info.tin),
            'address': {
                'street': tax_info.address_street,
                'city': tax_info.address_city,
                'state': tax_info.address_state,
                'zip': tax_info.address_zip
            }
        },

        'form_data': {
            'box_1_nonemployee_compensation': float(total_gross_earnings),
            'box_2_payer_made_direct_sales': None,
            'box_4_federal_income_tax_withheld': 0.00,
            'box_5_state_tax_withheld': 0.00,
            'box_6_state_payers_state_no': None,
            'box_7_state_income': float(total_gross_earnings)
        },

        'earnings_breakdown': {
            'total_gross_earnings': float(total_gross_earnings),
            'total_hours_worked': calculate_total_hours(shifts),
            'total_days_worked': calculate_days_worked(shifts),
            'total_trips': len(trips),
            'pay_type': pay_type,
            'rate': float(driver.rate or 0)
        },

        'expenses_summary': {
            'total_expenses_reimbursed': float(total_expenses),
            'note': 'Expenses are business reimbursements and not included in Box 1'
        },

        'payment_summary': {
            'total_gross_earnings': float(total_gross_earnings),
            'total_expenses_reimbursed': float(total_expenses),
            'total_paid_to_driver': float(total_gross_earnings + total_expenses),
            'total_reported_on_1099': float(total_gross_earnings)
        },

        'compliance': {
            'minimum_reporting_threshold': 600.00,
            'requires_1099': requires_1099,
            'form_due_date': date(tax_year + 1, 1, 31),
            'recipient_copy_due_date': date(tax_year + 1, 1, 31)
        }
    }

    return form_data


async def archive_1099(
    session: AsyncSession,
    driver_id: UUID,
    tax_year: int,
    box_1_amount: Decimal,
    pdf_url: Optional[str],
    generated_by: UUID
) -> Form1099Archive:
    """
    Archive a generated 1099 form.

    Args:
        session: Database session
        driver_id: Driver UUID
        tax_year: Tax year
        box_1_amount: Box 1 amount
        pdf_url: URL to PDF
        generated_by: Manager UUID who generated it

    Returns:
        Archived form record
    """
    # Check if already archived
    existing = await session.exec(
        Select(Form1099Archive)
        .Where(
            (Form1099Archive.driver_id == driver_id)
            & (Form1099Archive.tax_year == tax_year)
        )
    ).first()

    if existing:
        # Update existing
        existing.box_1_amount = box_1_amount
        existing.pdf_url = pdf_url
        existing.pdf_generated_at = datetime.now(timezone.utc)
        session.add(existing)
        await session.commit()
        await session.refresh(existing)
        return existing

    # Create new archive
    archive = Form1099Archive(
        driver_id=driver_id,
        tax_year=tax_year,
        box_1_amount=box_1_amount,
        pdf_url=pdf_url,
        pdf_generated_at=datetime.now(timezone.utc) if pdf_url else None,
        generated_by=generated_by
    )

    session.add(archive)
    await session.commit()
    await session.refresh(archive)

    return archive


async def get_drivers_for_1099(
    session: AsyncSession,
    tax_year: int,
    min_earnings: Decimal = Decimal("600.00")
) -> List[Dict]:
    """
    Get all drivers eligible for 1099 generation.

    Args:
        session: Database session
        tax_year: Tax year
        min_earnings: Minimum earnings threshold

    Returns:
        List of driver summaries
    """
    # Get all active drivers with tax info
    drivers = await session.exec(
        Select(Driver).Where(Driver.is_active == True)
    ).all()

    eligible_drivers = []

    for driver in drivers:
        try:
            form_data = await calculate_1099_data(session, driver.id, tax_year)

            if form_data['form_data']['box_1_nonemployee_compensation'] >= float(min_earnings):
                eligible_drivers.append({
                    'driver_id': driver.id,
                    'box_1_amount': form_data['form_data']['box_1_nonemployee_compensation'],
                    'expenses_reimbursed': form_data['expenses_summary']['total_expenses_reimbursed'],
                    'total_paid': form_data['payment_summary']['total_paid_to_driver'],
                    'has_tax_info': True
                })
        except HTTPException:
            # Driver doesn't have tax info or doesn't meet threshold
            continue

    return eligible_drivers
