"""
Expense service - Business logic for driver expenses.
Handles submitting, reviewing, and tracking expense reimbursements.
"""

from datetime import datetime, timezone, date, timedelta
from typing import Optional, List, Tuple
from uuid import UUID
from decimal import Decimal
from psqlmodel import Select, Count, AsyncSession
from fastapi import HTTPException, UploadFile

from shared.db.schemas.drivers import DriverExpense, ExpenseStatus, ExpenseType
from shared.db.schemas.entities.drivers import Driver


async def submit_expense(
    session: AsyncSession,
    driver_id: UUID,
    amount: Decimal,
    expense_type: str,
    expense_date: date,
    receipt_photo_url: str,
    description: Optional[str] = None
) -> DriverExpense:
    """
    Submit a new expense reimbursement request.

    Args:
        session: Database session
        driver_id: Driver UUID
        amount: Expense amount
        expense_type: Type of expense
        expense_date: Date of expense
        receipt_photo_url: URL to uploaded receipt
        description: Optional description

    Returns:
        Created expense

    Raises:
        HTTPException: If validation fails
    """
    # Validate driver
    driver = await session.exec(
        Select(Driver).Where(Driver.id == driver_id)
    ).first()

    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    if not driver.is_active:
        raise HTTPException(status_code=403, detail="Driver is not active")

    # Validate amount
    if amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="Amount must be greater than 0"
        )

    # Validate expense date
    today = date.today()
    if expense_date > today:
        raise HTTPException(
            status_code=400,
            detail="Expense date cannot be in the future"
        )

    # Check if expense is more than 30 days old
    days_ago = (today - expense_date).days
    if days_ago > 30:
        raise HTTPException(
            status_code=400,
            detail=f"Expense date cannot be more than 30 days in the past (submitted {days_ago} days after)"
        )

    # Validate expense type
    valid_types = [
        ExpenseType.GAS,
        ExpenseType.MAINTENANCE,
        ExpenseType.PARKING,
        ExpenseType.TOLLS,
        ExpenseType.CAR_WASH,
        ExpenseType.SUPPLIES,
        ExpenseType.OTHER
    ]
    if expense_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid expense type. Must be one of: {', '.join(valid_types)}"
        )

    # Create expense
    new_expense = DriverExpense(
        driver_id=driver_id,
        amount=amount,
        expense_type=expense_type,
        description=description,
        expense_date=expense_date,
        receipt_photo_url=receipt_photo_url,
        receipt_uploaded=True,
        status=ExpenseStatus.PENDING
    )

    session.add(new_expense)
    await session.commit()
    await session.refresh(new_expense)

    return new_expense


async def get_expenses_for_driver(
    session: AsyncSession,
    driver_id: UUID,
    status: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    expense_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 20
) -> Tuple[List[DriverExpense], int, dict]:
    """
    Get expenses for a driver with pagination and summary.

    Args:
        session: Database session
        driver_id: Driver UUID
        status: Optional status filter
        start_date: Optional start date filter
        end_date: Optional end date filter
        expense_type: Optional type filter
        page: Page number
        page_size: Items per page

    Returns:
        Tuple of (expenses list, total count, summary dict)
    """
    # Build base filter
    base_filter = (DriverExpense.driver_id == driver_id)

    if status and status != 'all':
        base_filter = base_filter & (DriverExpense.status == status)

    if start_date:
        base_filter = base_filter & (DriverExpense.expense_date >= start_date)

    if end_date:
        base_filter = base_filter & (DriverExpense.expense_date <= end_date)

    if expense_type:
        base_filter = base_filter & (DriverExpense.expense_type == expense_type)

    # Get total count
    total_count_result = await session.exec(
        Select(Count(DriverExpense.id)).From(DriverExpense).Where(base_filter)
    ).first()
    total_count = total_count_result[0] if total_count_result else 0

    # Get paginated results
    expenses = await session.exec(
        Select(DriverExpense)
        .Where(base_filter)
        .OrderBy(DriverExpense.expense_date.Desc())
        .Limit(page_size)
        .Offset((page - 1) * page_size)
    ).all()

    # Calculate summary from all driver expenses
    all_expenses = await session.exec(
        Select(DriverExpense)
        .Where(DriverExpense.driver_id == driver_id)
    ).all()

    summary = {
        'pending_count': sum(1 for e in all_expenses if e.status == ExpenseStatus.PENDING),
        'pending_total': float(sum(e.amount for e in all_expenses if e.status == ExpenseStatus.PENDING)),
        'verified_count': sum(1 for e in all_expenses if e.status == ExpenseStatus.VERIFIED),
        'verified_total': float(sum(e.amount for e in all_expenses if e.status == ExpenseStatus.VERIFIED)),
        'rejected_count': sum(1 for e in all_expenses if e.status == ExpenseStatus.REJECTED),
        'rejected_total': float(sum(e.amount for e in all_expenses if e.status == ExpenseStatus.REJECTED))
    }

    return list(expenses), total_count, summary


async def resolve_expense_review(
    session: AsyncSession,
    expense_id: UUID,
    manager_id: UUID,
    action: str,
    manager_notes: Optional[str] = None,
    adjusted_amount: Optional[Decimal] = None,
    adjustment_reason: Optional[str] = None,
    rejection_reason: Optional[str] = None
) -> DriverExpense:
    """
    Resolve an expense review.

    Args:
        session: Database session
        expense_id: Expense UUID
        manager_id: Manager UUID
        action: 'verify', 'reject', or 'adjust'
        manager_notes: Optional manager notes
        adjusted_amount: Required if action='adjust'
        adjustment_reason: Required if action='adjust'
        rejection_reason: Required if action='reject'

    Returns:
        Updated expense

    Raises:
        HTTPException: If validation fails
    """
    # Find expense
    expense = await session.exec(
        Select(DriverExpense).Where(DriverExpense.id == expense_id)
    ).first()

    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    if expense.status != ExpenseStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Expense is not pending review"
        )

    # Validate action
    if action not in ['verify', 'reject', 'adjust']:
        raise HTTPException(
            status_code=400,
            detail="Invalid action. Must be 'verify', 'reject', or 'adjust'"
        )

    # Handle actions
    if action == 'verify':
        expense.status = ExpenseStatus.VERIFIED

    elif action == 'reject':
        if not rejection_reason:
            raise HTTPException(
                status_code=400,
                detail="rejection_reason is required when rejecting"
            )
        expense.status = ExpenseStatus.REJECTED
        expense.rejection_reason = rejection_reason

    elif action == 'adjust':
        if not adjusted_amount:
            raise HTTPException(
                status_code=400,
                detail="adjusted_amount is required for adjust action"
            )

        if adjusted_amount <= 0:
            raise HTTPException(
                status_code=400,
                detail="Adjusted amount must be greater than 0"
            )

        if not adjustment_reason:
            raise HTTPException(
                status_code=400,
                detail="adjustment_reason is required for adjust action"
            )

        expense.amount = adjusted_amount
        expense.status = ExpenseStatus.VERIFIED
        expense.rejection_reason = adjustment_reason  # Store adjustment reason here

    # Update review metadata
    expense.reviewed_at = datetime.now(timezone.utc)
    expense.reviewed_by = manager_id
    expense.manager_notes = manager_notes
    expense.updated_at = datetime.now(timezone.utc)

    session.add(expense)
    await session.commit()
    await session.refresh(expense)

    return expense


async def get_expenses_pending_review(
    session: AsyncSession,
    driver_id: Optional[UUID] = None,
    expense_type: Optional[str] = None,
    min_amount: Optional[Decimal] = None,
    max_amount: Optional[Decimal] = None,
    page: int = 1,
    page_size: int = 20
) -> Tuple[List[DriverExpense], int, dict]:
    """
    Get expenses pending manager review.

    Args:
        session: Database session
        driver_id: Optional driver filter
        expense_type: Optional type filter
        min_amount: Optional min amount filter
        max_amount: Optional max amount filter
        page: Page number
        page_size: Items per page

    Returns:
        Tuple of (expenses list, total count, summary dict)
    """
    base_filter = (DriverExpense.status == ExpenseStatus.PENDING)

    if driver_id:
        base_filter = base_filter & (DriverExpense.driver_id == driver_id)

    if expense_type:
        base_filter = base_filter & (DriverExpense.expense_type == expense_type)

    if min_amount:
        base_filter = base_filter & (DriverExpense.amount >= min_amount)

    if max_amount:
        base_filter = base_filter & (DriverExpense.amount <= max_amount)

    # Get total count
    total_count_result = await session.exec(
        Select(Count(DriverExpense.id)).From(DriverExpense).Where(base_filter)
    ).first()
    total_count = total_count_result[0] if total_count_result else 0

    # Get paginated results
    expenses = await session.exec(
        Select(DriverExpense)
        .Where(base_filter)
        .OrderBy(DriverExpense.created_at.Desc())
        .Limit(page_size)
        .Offset((page - 1) * page_size)
    ).all()

    # Calculate summary
    pending_expenses = await session.exec(
        Select(DriverExpense)
        .Where(DriverExpense.status == ExpenseStatus.PENDING)
    ).all()

    # Get today's verified/rejected counts
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())

    verified_today_list = await session.exec(
        Select(DriverExpense)
        .Where(
            (DriverExpense.status == ExpenseStatus.VERIFIED)
            & (DriverExpense.reviewed_at >= today_start)
        )
    ).all()
    verified_today = len(verified_today_list)

    rejected_today_list = await session.exec(
        Select(DriverExpense)
        .Where(
            (DriverExpense.status == ExpenseStatus.REJECTED)
            & (DriverExpense.reviewed_at >= today_start)
        )
    ).all()
    rejected_today = len(rejected_today_list)

    summary = {
        'pending_count': len(pending_expenses),
        'pending_total': float(sum(e.amount for e in pending_expenses)),
        'verified_today': verified_today,
        'rejected_today': rejected_today
    }

    return list(expenses), total_count, summary


async def get_verified_expenses_for_period(
    session: AsyncSession,
    driver_id: UUID,
    period_start: date,
    period_end: date
) -> List[DriverExpense]:
    """
    Get verified expenses for a specific pay period.

    Args:
        session: Database session
        driver_id: Driver UUID
        period_start: Period start date
        period_end: Period end date

    Returns:
        List of verified expenses
    """
    expenses = await session.exec(
        Select(DriverExpense)
        .Where(
            (DriverExpense.driver_id == driver_id)
            & (DriverExpense.status == ExpenseStatus.VERIFIED)
            & (DriverExpense.expense_date >= period_start)
            & (DriverExpense.expense_date <= period_end)
        )
    ).all()

    return list(expenses)


def calculate_days_pending(expense: DriverExpense) -> int:
    """
    Calculate how many days an expense has been pending.

    Args:
        expense: Expense object

    Returns:
        Number of days pending
    """
    if expense.status != ExpenseStatus.PENDING:
        return 0

    now = datetime.now(timezone.utc)
    delta = now - expense.created_at

    return delta.days
