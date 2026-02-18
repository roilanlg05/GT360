-- Add driver work schedule fields
-- shift_start_time/shift_end_time: driver's scheduled shift hours
-- work_days: JSON array of day abbreviations e.g. ["mon","tue","wed","thu","fri"]

ALTER TABLE entities.drivers ADD COLUMN IF NOT EXISTS shift_start_time TIME;
ALTER TABLE entities.drivers ADD COLUMN IF NOT EXISTS shift_end_time TIME;
ALTER TABLE entities.drivers ADD COLUMN IF NOT EXISTS work_days JSONB;

-- Snapshot columns on driver_shifts (captured at shift start for historical accuracy)
ALTER TABLE drivers.driver_shifts ADD COLUMN IF NOT EXISTS shift_start_time TIME;
ALTER TABLE drivers.driver_shifts ADD COLUMN IF NOT EXISTS shift_end_time TIME;
