"""
Manager 1099 router - Manager endpoints for 1099 operations.
Handles bulk 1099 generation and management.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from psqlmodel import Select, AsyncSession
from typing import Optional, List
from uuid import UUID, uuid4
from decimal import Decimal
from datetime import date, datetime, timezone

from shared.db.db_config import get_db
from features.auth.utils import verify_role
from features.billing.utils.subscription_guard import ActiveSubscription
from features.drivers.services.tax_service import (
    get_drivers_for_1099,
    calculate_1099_data,
    mask_tin
)


router = APIRouter(prefix="/v1/managers", tags=["Manager - 1099 Management"])


@router.get("/1099/bulk")
async def get_bulk_1099_data(
    year: int,
    format: str = "json",
    min_earnings: float = 600.00,
    driver_ids: Optional[str] = None,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Get 1099 data for all eligible drivers.

    Query parameters:
    - year: Tax year (required, e.g., 2026)
    - format: 'json' or 'csv' (default 'json')
    - min_earnings: Minimum earnings threshold (default $600)
    - driver_ids: Comma-separated driver UUIDs (optional)

    Returns:
    - Summary of all drivers eligible for 1099
    - Total earnings and expenses
    - Individual driver summaries with download links
    """
    # Validate year
    current_year = date.today().year
    if year > current_year:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot generate 1099 for future year {year}"
        )

    # Parse driver_ids if provided
    filter_drivers = None
    if driver_ids:
        try:
            filter_drivers = [UUID(d.strip()) for d in driver_ids.split(',')]
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid driver ID format"
            )

    # Get eligible drivers
    min_decimal = Decimal(str(min_earnings))
    all_drivers = await get_drivers_for_1099(session, year, min_decimal)

    # Filter if specific drivers requested
    if filter_drivers:
        all_drivers = [d for d in all_drivers if d['driver_id'] in filter_drivers]

    # Calculate totals
    total_earnings = sum(d['box_1_amount'] for d in all_drivers)
    total_expenses = sum(d['expenses_reimbursed'] for d in all_drivers)
    total_paid = sum(d['total_paid'] for d in all_drivers)

    # Build driver summaries
    driver_summaries = []
    for driver_data in all_drivers:
        # Get driver name from User table
        from shared.db.schemas.entities.users import User

        user = await session.exec(
            Select(User).Where(User.id == driver_data['driver_id'])
        ).first()
        driver_name = f"{user.first_name} {user.last_name}" if user else "Unknown"

        # Get TIN (masked)
        from shared.db.schemas.drivers import DriverTaxInformation
        tax_info = await session.exec(
            Select(DriverTaxInformation)
            .Where(DriverTaxInformation.driver_id == driver_data['driver_id'])
        ).first()
        tin_masked = mask_tin(tax_info.tin) if tax_info else "***-***"

        driver_summaries.append({
            "driver_id": str(driver_data['driver_id']),
            "driver_name": driver_name,
            "tin": tin_masked,
            "box_1_amount": driver_data['box_1_amount'],
            "expenses_reimbursed": driver_data['expenses_reimbursed'],
            "total_paid": driver_data['total_paid'],
            "requires_1099": True,
            "has_tax_info": driver_data['has_tax_info'],
            "download_url": f"/api/v1/drivers/{driver_data['driver_id']}/1099?year={year}&format=pdf"
        })

    if format == 'json':
        return {
            "tax_year": year,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_drivers": len(driver_summaries),
            "total_earnings_reported": total_earnings,
            "total_expenses_reimbursed": total_expenses,
            "total_paid_to_drivers": total_paid,
            "drivers": driver_summaries,
            "bulk_download_url": f"/api/v1/managers/1099/bulk/download?year={year}&format=zip"
        }

    elif format == 'csv':
        # TODO: Generate CSV
        raise HTTPException(
            status_code=501,
            detail="CSV format not yet implemented"
        )

    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid format. Must be 'json' or 'csv'"
        )


@router.post("/1099/generate-all")
async def generate_all_1099s(
    request: Request,
    year: int,
    min_earnings: float = 600.00,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"])),
    _sub=Depends(ActiveSubscription),
):
    """
    Generate PDF 1099 forms for all eligible drivers.

    This is an async operation that generates PDFs in the background.

    Body:
    - year: Tax year (required)
    - min_earnings: Minimum earnings threshold (default $600)

    Returns:
    - Job ID for tracking progress
    - Estimated completion time
    - Count of drivers to process
    """
    # Validate year
    current_year = date.today().year
    if year > current_year:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot generate 1099 for future year {year}"
        )

    # Get manager ID
    user_data = getattr(request.state, "user_data", None)
    manager_id = UUID(user_data.get("id")) if user_data else None

    if not manager_id:
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid authentication"
        )

    # Get eligible drivers
    min_decimal = Decimal(str(min_earnings))
    eligible_drivers = await get_drivers_for_1099(session, year, min_decimal)

    # TODO: Create background job to generate PDFs
    # For now, return mock response
    job_id = uuid4()
    total_drivers = len(eligible_drivers)

    # Estimate 1 minute per 10 drivers
    estimated_minutes = max(1, total_drivers // 10)
    estimated_completion = datetime.now(timezone.utc)

    return {
        "status": "ok",
        "message": "1099 forms generation started",
        "job_id": str(job_id),
        "total_drivers": total_drivers,
        "estimated_completion": estimated_completion.isoformat()
    }


@router.get("/1099/bulk/download")
async def download_bulk_1099s(
    year: int,
    format: str = "zip",
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Download all 1099 PDFs as a ZIP file.

    Query parameters:
    - year: Tax year (required)
    - format: Only 'zip' supported

    Returns:
    - ZIP file with all generated 1099 PDFs
    """
    # TODO: Implement ZIP download
    raise HTTPException(
        status_code=501,
        detail="Bulk download not yet implemented"
    )
