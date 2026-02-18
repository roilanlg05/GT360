"""
Earnings router - Driver endpoints for viewing earnings.
Handles earnings calculation and breakdown by pay period.
"""

from fastapi import APIRouter, Depends, HTTPException
from psqlmodel import Select, AsyncSession
from typing import Optional
from datetime import date
from uuid import UUID

from shared.db.db_config import get_db
from features.auth.utils import verify_role
from features.drivers.services.earnings_service import get_earnings_for_driver
from shared.db.schemas.entities.users import User


router = APIRouter(prefix="/v1/drivers", tags=["Driver Earnings"])


@router.get("/{driver_id}/earnings")
async def get_driver_earnings(
    driver_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["driver"]))
):
    """
    Get earnings breakdown by pay period for a driver.

    Query parameters:
    - start_date: Filter from this date (YYYY-MM-DD)
    - end_date: Filter until this date (YYYY-MM-DD)
    - page: Page number (default 1)
    - page_size: Periods per page (default 10)

    Returns:
    - Periods with gross earnings, expenses, and net pay
    - Year-to-date totals
    - Breakdown varies by pay_frequency (daily/weekly/biweekly)
    """
    try:
        driver_uuid = UUID(driver_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid driver ID")

    # Parse dates
    start_dt = date.fromisoformat(start_date) if start_date else None
    end_dt = date.fromisoformat(end_date) if end_date else None

    # Get earnings data
    earnings_data = await get_earnings_for_driver(
        session,
        driver_uuid,
        start_dt,
        end_dt,
        page,
        page_size
    )

    # Get driver name
    user = await session.exec(
        Select(User).Where(User.id == driver_uuid)
    ).first()
    driver_name = f"{user.first_name} {user.last_name}" if user else "Unknown"

    # Build response
    return {
        "driver_id": str(driver_uuid),
        "driver_name": driver_name,
        "pay_type": earnings_data['pay_type'],
        "pay_frequency": earnings_data['pay_frequency'],
        "rate": earnings_data.get('rate'),
        "timezone": earnings_data['timezone'],
        "periods": earnings_data['periods'],
        "pagination": earnings_data['pagination'],
        "year_to_date": earnings_data['year_to_date']
    }
