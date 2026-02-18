-- Migration: Create driver_expenses table
-- Date: 2026-02-16
-- Description: Creates table to track driver expense reimbursements

-- Create driver_expenses table
CREATE TABLE IF NOT EXISTS drivers.driver_expenses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL REFERENCES entities.drivers(id) ON DELETE CASCADE,

    -- Expense details
    amount DECIMAL(10, 2) NOT NULL,
    expense_type VARCHAR(50) NOT NULL,
    -- Values: 'gas', 'maintenance', 'parking', 'tolls', 'other'

    description TEXT,
    expense_date DATE NOT NULL,

    -- Receipt
    receipt_photo_url TEXT,
    receipt_uploaded BOOLEAN DEFAULT FALSE NOT NULL,

    -- Review system
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- Values: 'pending', 'verified', 'rejected'

    reviewed_at TIMESTAMPTZ,
    reviewed_by UUID REFERENCES entities.users(id) ON DELETE SET NULL,
    manager_notes TEXT,
    rejection_reason TEXT,

    -- Payment period
    pay_period_start DATE,
    pay_period_end DATE,
    included_in_payment BOOLEAN DEFAULT FALSE NOT NULL,

    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,

    -- Constraints
    CONSTRAINT valid_amount CHECK (amount > 0)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_expenses_driver_date
ON drivers.driver_expenses(driver_id, expense_date DESC);

CREATE INDEX IF NOT EXISTS idx_expenses_status
ON drivers.driver_expenses(status);

CREATE INDEX IF NOT EXISTS idx_expenses_pending_review
ON drivers.driver_expenses(driver_id, status)
WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_expenses_pay_period
ON drivers.driver_expenses(driver_id, pay_period_start, pay_period_end)
WHERE status = 'verified';

CREATE INDEX IF NOT EXISTS idx_expenses_type
ON drivers.driver_expenses(expense_type);

-- Add comments
COMMENT ON TABLE drivers.driver_expenses IS 'Driver expense reimbursements';
COMMENT ON COLUMN drivers.driver_expenses.amount IS 'Expense amount in dollars';
COMMENT ON COLUMN drivers.driver_expenses.status IS 'Review status: pending, verified, or rejected';
COMMENT ON COLUMN drivers.driver_expenses.receipt_photo_url IS 'URL to receipt photo in S3 or local storage';

-- Create updated_at trigger
CREATE OR REPLACE FUNCTION drivers.update_expense_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_expense_timestamp
    BEFORE UPDATE ON drivers.driver_expenses
    FOR EACH ROW
    EXECUTE FUNCTION drivers.update_expense_updated_at();
