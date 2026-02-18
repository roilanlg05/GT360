"""
Expenses router - Driver endpoints for expense management.
Handles submitting and viewing expense reimbursements.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from psqlmodel import AsyncSession
from typing import Optional
from datetime import date
from uuid import UUID
from decimal import Decimal

from shared.db.db_config import get_db
from features.auth.utils import verify_role
from features.drivers.models.expense_models import (
    ExpenseResponse,
    ExpenseListResponse,
    SubmitExpenseResponse
)
from features.drivers.services.expense_service import (
    submit_expense,
    get_expenses_for_driver,
    calculate_days_pending
)
from features.drivers.services.receipt_upload_service import upload_receipt_photo


router = APIRouter(prefix="/v1/drivers", tags=["Driver Expenses"])


def build_expense_response(expense) -> dict:
    """Build expense response."""
    return {
        "expense_id": expense.id,
        "driver_id": expense.driver_id,
        "amount": float(expense.amount),
        "expense_type": expense.expense_type,
        "description": expense.description,
        "expense_date": expense.expense_date,
        "receipt_photo_url": expense.receipt_photo_url,
        "receipt_uploaded": expense.receipt_uploaded,
        "status": expense.status,
        "reviewed_at": expense.reviewed_at,
        "reviewed_by": expense.reviewed_by,
        "manager_notes": expense.manager_notes,
        "rejection_reason": expense.rejection_reason,
        "pay_period_start": expense.pay_period_start,
        "pay_period_end": expense.pay_period_end,
        "included_in_payment": expense.included_in_payment,
        "created_at": expense.created_at
    }


@router.post("/{driver_id}/expenses")
async def submit_driver_expense(
    driver_id: str,
    amount: Decimal = Form(...),
    expense_type: str = Form(...),
    expense_date: str = Form(...),
    description: Optional[str] = Form(None),
    receipt_photo: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["driver"]))
):
    """
    Submit an expense reimbursement request.

    Form data:
    - amount: Expense amount (must be > 0)
    - expense_type: Type ('gas', 'maintenance', 'parking', 'tolls', 'other')
    - expense_date: Date of expense (YYYY-MM-DD)
    - description: Optional description
    - receipt_photo: Receipt image/PDF (max 10MB)

    Validations:
    - Amount must be positive
    - Expense date cannot be in future
    - Expense date cannot be more than 30 days old
    - Receipt photo is required
    """
    try:
        driver_uuid = UUID(driver_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid driver ID")

    # Parse expense date
    try:
        exp_date = date.fromisoformat(expense_date)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD"
        )

    # Upload receipt photo
    receipt_url = await upload_receipt_photo(receipt_photo, driver_uuid)

    # Submit expense
    expense = await submit_expense(
        session,
        driver_uuid,
        amount,
        expense_type,
        exp_date,
        receipt_url,
        description
    )

    expense_data = build_expense_response(expense)

    return {
        "status": "ok",
        "message": "Expense submitted for review",
        "expense": expense_data
    }


@router.get("/{driver_id}/expenses")
async def get_driver_expenses(
    driver_id: str,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    expense_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["driver"]))
):
    """
    Get expenses for a driver with pagination.

    Query parameters:
    - status: Filter by status ('pending', 'verified', 'rejected', 'all')
    - start_date: Filter expenses from this date (YYYY-MM-DD)
    - end_date: Filter expenses until this date (YYYY-MM-DD)
    - expense_type: Filter by type ('gas', 'maintenance', etc.)
    - page: Page number (default 1)
    - page_size: Items per page (default 20)

    Returns summary of totals by status.
    """
    try:
        driver_uuid = UUID(driver_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid driver ID")

    # Parse dates
    start_dt = date.fromisoformat(start_date) if start_date else None
    end_dt = date.fromisoformat(end_date) if end_date else None

    expenses, total_count, summary = await get_expenses_for_driver(
        session,
        driver_uuid,
        status,
        start_dt,
        end_dt,
        expense_type,
        page,
        page_size
    )

    # Build response
    expenses_data = []
    for expense in expenses:
        expense_data = build_expense_response(expense)
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
