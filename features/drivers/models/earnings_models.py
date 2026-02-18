from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional, List, Dict
from uuid import UUID
from decimal import Decimal


class ShiftSummary(BaseModel):
    """Summary of a shift within a day."""
    shift_id: UUID
    started_at: datetime
    ended_at: datetime
    duration_hours: float


class DailySummary(BaseModel):
    """Summary of work for a single day."""
    date: date
    day_of_week: str
    hours_worked: float
    trips_count: int
    daily_earnings: Decimal
    shifts: Optional[List[ShiftSummary]] = None


class WeeklySummary(BaseModel):
    """Summary of work for a week."""
    week_start: date
    week_end: date
    hours_worked: float
    days_worked: int
    trips_count: int
    earnings: Decimal
    daily_summary: List[DailySummary]


class BiweeklyBreakdown(BaseModel):
    """Breakdown for biweekly period."""
    week_1: WeeklySummary
    week_2: WeeklySummary


class ExpenseDetail(BaseModel):
    """Expense detail within a period."""
    expense_id: UUID
    expense_date: date
    expense_type: str
    amount: Decimal
    status: str
    description: Optional[str]


class ExpensesSummary(BaseModel):
    """Summary of expenses in a period."""
    verified: Decimal
    pending: Decimal
    rejected: Decimal
    total_verified: Decimal


class Breakdown1099(BaseModel):
    """Breakdown for 1099 purposes."""
    taxable_income: Decimal
    non_taxable_reimbursements: Decimal
    total_payment: Decimal


class PeriodSummary(BaseModel):
    """Summary metrics for a period."""
    total_trips: int
    total_hours_worked: float
    total_days_worked: int
    total_shifts: int
    expenses_count: int


class EarningsPeriod(BaseModel):
    """Earnings data for a pay period."""
    period_type: str = Field(description="'daily', 'weekly', or 'biweekly'")
    period_number: Optional[int] = Field(
        default=None,
        description="Period number in the year"
    )
    year: int
    period_start: date
    period_end: date

    gross_earnings: Decimal = Field(description="Earnings from work (taxable)")
    expenses: ExpensesSummary
    net_pay: Decimal = Field(description="Total payment to driver")

    breakdown_for_1099: Breakdown1099
    summary: PeriodSummary

    # Breakdown varies by period type
    breakdown: Optional[Dict] = Field(
        default=None,
        description="Detailed breakdown (structure varies by period_type)"
    )

    expense_details: List[ExpenseDetail]


class YearToDate(BaseModel):
    """Year-to-date totals."""
    year: int
    total_gross_earnings: Decimal
    total_expenses_reimbursed: Decimal
    total_net_pay: Decimal
    total_hours_worked: float
    total_days_worked: int
    total_trips: int


class EarningsResponse(BaseModel):
    """Complete earnings response."""
    driver_id: UUID
    driver_name: str
    pay_type: str
    pay_frequency: str
    rate: Decimal
    timezone: str

    periods: List[EarningsPeriod]
    pagination: dict
    year_to_date: YearToDate
