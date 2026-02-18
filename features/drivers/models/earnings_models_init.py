"""Earnings system models."""

from .shift_models import (
    StartShiftRequest,
    EndShiftRequest,
    ShiftResponse,
    ShiftListResponse,
    ShiftStartResponse,
    ShiftEndResponse,
    ResolveShiftRequest,
    ResolveShiftResponse,
)

from .expense_models import (
    SubmitExpenseRequest,
    ExpenseResponse,
    ExpenseListResponse,
    SubmitExpenseResponse,
    ResolveExpenseRequest,
    ResolveExpenseResponse,
)

from .earnings_models import (
    EarningsResponse,
    EarningsPeriod,
    YearToDate,
)

from .tax_models import (
    SubmitTaxInformationRequest,
    TaxInformationResponse,
    SubmitTaxInformationResponse,
    Form1099Response,
    Bulk1099Response,
    Driver1099Summary,
    GenerateAll1099Request,
    GenerateAll1099Response,
)

__all__ = [
    # Shift models
    "StartShiftRequest",
    "EndShiftRequest",
    "ShiftResponse",
    "ShiftListResponse",
    "ShiftStartResponse",
    "ShiftEndResponse",
    "ResolveShiftRequest",
    "ResolveShiftResponse",
    # Expense models
    "SubmitExpenseRequest",
    "ExpenseResponse",
    "ExpenseListResponse",
    "SubmitExpenseResponse",
    "ResolveExpenseRequest",
    "ResolveExpenseResponse",
    # Earnings models
    "EarningsResponse",
    "EarningsPeriod",
    "YearToDate",
    # Tax models
    "SubmitTaxInformationRequest",
    "TaxInformationResponse",
    "SubmitTaxInformationResponse",
    "Form1099Response",
    "Bulk1099Response",
    "Driver1099Summary",
    "GenerateAll1099Request",
    "GenerateAll1099Response",
]
