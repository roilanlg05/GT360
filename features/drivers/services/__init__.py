"""Driver earnings system services."""

from .shift_service import (
    start_shift,
    end_shift,
    get_shifts_for_driver,
    auto_close_stale_shifts,
    resolve_shift_review,
    get_shifts_pending_review,
    calculate_shift_duration,
    shift_crosses_midnight,
    calculate_hours_per_day,
    get_trips_in_shift
)

from .expense_service import (
    submit_expense,
    get_expenses_for_driver,
    resolve_expense_review,
    get_expenses_pending_review,
    get_verified_expenses_for_period,
    calculate_days_pending
)

from .earnings_service import (
    get_earnings_for_driver,
    calculate_earnings_for_period,
    get_driver_timezone,
    get_period_range
)

from .tax_service import (
    submit_tax_information,
    calculate_1099_data,
    archive_1099,
    get_drivers_for_1099,
    validate_tin,
    mask_tin
)

from .receipt_upload_service import (
    upload_receipt_photo,
    upload_w9_document,
    delete_file,
    ensure_upload_dirs
)

__all__ = [
    # Shift service
    "start_shift",
    "end_shift",
    "get_shifts_for_driver",
    "auto_close_stale_shifts",
    "resolve_shift_review",
    "get_shifts_pending_review",
    "calculate_shift_duration",
    "shift_crosses_midnight",
    "calculate_hours_per_day",
    "get_trips_in_shift",
    # Expense service
    "submit_expense",
    "get_expenses_for_driver",
    "resolve_expense_review",
    "get_expenses_pending_review",
    "get_verified_expenses_for_period",
    "calculate_days_pending",
    # Earnings service
    "get_earnings_for_driver",
    "calculate_earnings_for_period",
    "get_driver_timezone",
    "get_period_range",
    # Tax service
    "submit_tax_information",
    "calculate_1099_data",
    "archive_1099",
    "get_drivers_for_1099",
    "validate_tin",
    "mask_tin",
    # Upload service
    "upload_receipt_photo",
    "upload_w9_document",
    "delete_file",
    "ensure_upload_dirs",
]
