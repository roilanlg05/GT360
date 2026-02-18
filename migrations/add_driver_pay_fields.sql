-- Migration: Add pay frequency and rate to drivers table
-- Date: 2026-02-16
-- Description: Adds pay_frequency and rate fields to support the earnings system

-- Add pay_frequency column
ALTER TABLE entities.drivers
ADD COLUMN IF NOT EXISTS pay_frequency VARCHAR(20);

-- Add single rate column (applies based on pay_type)
ALTER TABLE entities.drivers
ADD COLUMN IF NOT EXISTS rate DECIMAL(10, 2);

-- Add index on pay_frequency for filtering
CREATE INDEX IF NOT EXISTS idx_drivers_pay_frequency
ON entities.drivers(pay_frequency);

-- Add comments for documentation
COMMENT ON COLUMN entities.drivers.pay_frequency IS 'Payment frequency: daily, weekly, or biweekly';
COMMENT ON COLUMN entities.drivers.rate IS 'Payment rate (hourly/daily/per-trip based on pay_type)';
