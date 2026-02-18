"""
Manager expenses router - Manager endpoints for reviewing expenses.
Handles expense review and approval workflow.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from psqlmodel import Select, AsyncSession
from typing import Optional
from uuid import UUID
from decimal import Decimal

from shared.db.db_config import get_db
from features.auth.utils import verify_role
from features.drivers.models.expense_models import (
    ResolveExpenseRequest,
    ResolveExpenseResponse
)
from features.drivers.services.expense_service import (
    get_expenses_pending_review,
    resolve_expense_review,
    calculate_days_pending
)
from shared.db.schemas.entities.users import User


router = APIRouter(prefix="/v1/managers", tags=["Manager - Expense Review"])


async def build_expense_response_with_driver(expense, session: AsyncSession) -> dict:
    """Build expense response with driver info."""
    # Get driver name
    user = await session.exec(
        Select(User).Where(User.id == expense.driver_id)
    ).first()
    driver_name = f"{user.first_name} {user.last_name}" if user else "Unknown"

    days_pending = calculate_days_pending(expense)

    return {
        "expense_id": expense.id,
        "driver_id": expense.driver_id,
        "driver_name": driver_name,
        "amount": float(expense.amount),
        "expense_type": expense.expense_type,
        "description": expense.description,
        "expense_date": expense.expense_date,
        "receipt_photo_url": expense.receipt_photo_url,
        "status": expense.status,
        "reviewed_at": expense.reviewed_at,
        "reviewed_by": expense.reviewed_by,
        "manager_notes": expense.manager_notes,
        "rejection_reason": expense.rejection_reason,
        "created_at": expense.created_at,
        "days_pending": days_pending
    }


@router.get("/expenses/review")
async def get_expenses_for_review(
    driver_id: Optional[str] = None,
    expense_type: Optional[str] = None,
    status: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    sort_by: str = "created_at",
    order: str = "desc",
    page: int = 1,
    page_size: int = 20,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Get expenses pending manager review.

    Query parameters:
    - driver_id: Filter by specific driver (optional)
    - expense_type: Filter by type ('gas', 'maintenance', etc.)
    - status: Filter by status ('pending', 'verified', 'rejected')
    - min_amount: Filter by minimum amount
    - max_amount: Filter by maximum amount
    - sort_by: Sort field ('created_at', 'amount', 'expense_date')
    - order: Sort order ('asc', 'desc')
    - page: Page number (default 1)
    - page_size: Items per page (default 20)

    Returns:
    - List of expenses needing review
    - Summary with totals and counts
    """
    # Parse driver_id if provided
    driver_uuid = None
    if driver_id:
        try:
            driver_uuid = UUID(driver_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid driver ID")

    # Convert amounts to Decimal
    min_decimal = Decimal(str(min_amount)) if min_amount else None
    max_decimal = Decimal(str(max_amount)) if max_amount else None

    # Get expenses
    expenses, total_count, summary = await get_expenses_pending_review(
        session,
        driver_uuid,
        expense_type,
        min_decimal,
        max_decimal,
        page,
        page_size
    )

    # Build response
    expenses_data = []
    for expense in expenses:
        expense_data = await build_expense_response_with_driver(expense, session)
        expenses_data.append(expense_data)

    return {
        "expenses": expenses_data,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_expenses": total_count,
            "total_pages": (total_count + page_size - 1) // page_size
        },
        "summary": summary
    }


@router.post("/expenses/{expense_id}/resolve")
async def resolve_expense(
    expense_id: str,
    request_data: ResolveExpenseRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Resolve an expense review.

    Actions:
    - 'verify': Approve expense as-is
    - 'reject': Reject the expense
    - 'adjust': Modify amount and approve

    Body:
    - action: Action to take (required)
    - manager_notes: Manager's notes (optional)
    - adjusted_amount: New amount (required if action='adjust')
    - adjustment_reason: Reason for adjustment (required if action='adjust')
    - rejection_reason: Reason for rejection (required if action='reject')

    Validations:
    - Expense must be pending review
    - Adjusted amount must be > 0
    - Rejection reason required when rejecting
    """
    try:
        expense_uuid = UUID(expense_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid expense ID")

    # Get manager ID from token
    user_data = getattr(request.state, "user_data", None)
    manager_id = UUID(user_data.get("id")) if user_data else None

    if not manager_id:
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid authentication"
        )

    # Resolve expense
    expense = await resolve_expense_review(
        session,
        expense_uuid,
        manager_id,
        request_data.action,
        request_data.manager_notes,
        request_data.adjusted_amount,
        request_data.adjustment_reason,
        request_data.rejection_reason
    )

    # Build response
    expense_data = await build_expense_response_with_driver(expense, session)

    action_messages = {
        'verify': 'Expense verified successfully',
        'reject': 'Expense rejected',
        'adjust': 'Expense adjusted and verified'
    }

    return {
        "status": "ok",
        "message": action_messages.get(request_data.action, "Expense resolved"),
        "expense": expense_data
    }


@router.get("/drivers/{driver_id}/earnings")
async def get_manager_driver_earnings(
    driver_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Get earnings for any driver (manager view).

    Same as driver earnings endpoint but accessible to managers.
    Allows managers to view earnings for any driver.

    See driver earnings endpoint documentation for details.
    """
    # Reuse the driver earnings logic
    from .earnings_router import get_driver_earnings as driver_endpoint

    # Call driver endpoint with manager role
    return await driver_endpoint(
        driver_id,
        start_date,
        end_date,
        page,
        page_size,
        session,
        _role  # Pass through manager role
    )
