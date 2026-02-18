from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional, List
from uuid import UUID
from decimal import Decimal


class SubmitExpenseRequest(BaseModel):
    """Request to submit an expense (used with form-data)."""
    amount: Decimal = Field(
        ...,
        gt=0,
        description="Expense amount in dollars"
    )
    expense_type: str = Field(
        ...,
        description="Type of expense: 'gas', 'maintenance', 'parking', 'tolls', 'other'"
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of the expense"
    )
    expense_date: date = Field(
        ...,
        description="Date of the expense (from receipt)"
    )


class ExpenseResponse(BaseModel):
    """Response model for a single expense."""
    expense_id: UUID
    driver_id: UUID
    amount: Decimal
    expense_type: str
    description: Optional[str]
    expense_date: date
    receipt_photo_url: Optional[str]
    receipt_uploaded: bool
    status: str
    reviewed_at: Optional[datetime]
    reviewed_by: Optional[UUID]
    manager_notes: Optional[str]
    rejection_reason: Optional[str]
    pay_period_start: Optional[date]
    pay_period_end: Optional[date]
    included_in_payment: bool
    created_at: datetime


class ExpenseListResponse(BaseModel):
    """Response model for list of expenses."""
    expenses: List[ExpenseResponse]
    pagination: dict
    summary: dict


class SubmitExpenseResponse(BaseModel):
    """Response when expense is submitted."""
    status: str
    message: str
    expense: ExpenseResponse


# Manager models

class ResolveExpenseRequest(BaseModel):
    """Manager request to resolve an expense."""
    action: str = Field(
        ...,
        description="Action to take: 'verify', 'reject', or 'adjust'"
    )
    manager_notes: Optional[str] = Field(
        default=None,
        description="Manager's notes about the resolution"
    )
    adjusted_amount: Optional[Decimal] = Field(
        default=None,
        gt=0,
        description="Adjusted amount (required if action='adjust')"
    )
    adjustment_reason: Optional[str] = Field(
        default=None,
        description="Reason for adjustment (required if action='adjust')"
    )
    rejection_reason: Optional[str] = Field(
        default=None,
        description="Reason for rejection (required if action='reject')"
    )


class ResolveExpenseResponse(BaseModel):
    """Response when expense review is resolved."""
    status: str
    message: str
    expense: ExpenseResponse
