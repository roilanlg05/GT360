-- Migration: Create driver_shifts table
-- Date: 2026-02-16
-- Description: Creates table to track driver work sessions

-- Create schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS drivers;

-- Create driver_shifts table
CREATE TABLE IF NOT EXISTS drivers.driver_shifts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL REFERENCES entities.drivers(id) ON DELETE CASCADE,

    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,

    -- Status columns
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    -- Values: 'active', 'completed', 'auto_closed', 'under_review', 'reviewed'

    -- Review system
    review_status VARCHAR(20),
    -- Values: NULL, 'pending', 'approved', 'rejected'

    review_reason TEXT,
    reviewed_at TIMESTAMPTZ,
    reviewed_by UUID REFERENCES entities.users(id) ON DELETE SET NULL,
    manager_notes TEXT,

    auto_closed BOOLEAN DEFAULT FALSE NOT NULL,

    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,

    -- Constraints
    CONSTRAINT valid_ended_at CHECK (ended_at IS NULL OR ended_at > started_at)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_shifts_driver_started
ON drivers.driver_shifts(driver_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_shifts_status
ON drivers.driver_shifts(status)
WHERE status IN ('active', 'under_review');

CREATE INDEX IF NOT EXISTS idx_shifts_review_status
ON drivers.driver_shifts(review_status)
WHERE review_status = 'pending';

CREATE INDEX IF NOT EXISTS idx_shifts_driver_status
ON drivers.driver_shifts(driver_id, status);

-- Add comments
COMMENT ON TABLE drivers.driver_shifts IS 'Driver work sessions for earnings tracking';
COMMENT ON COLUMN drivers.driver_shifts.status IS 'Current shift status';
COMMENT ON COLUMN drivers.driver_shifts.review_status IS 'Review status if shift needs manager approval';
COMMENT ON COLUMN drivers.driver_shifts.auto_closed IS 'Whether shift was automatically closed after 6 hours';

-- Create updated_at trigger
CREATE OR REPLACE FUNCTION drivers.update_shift_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_shift_timestamp
    BEFORE UPDATE ON drivers.driver_shifts
    FOR EACH ROW
    EXECUTE FUNCTION drivers.update_shift_updated_at();
