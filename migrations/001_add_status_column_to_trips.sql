-- Migration: Add status column to trips table
-- Date: 2026-01-14
-- Description: Add status column to track trip states (scheduled, canceled, en_route)
-- Fixes: Error 500 "column trips.status does not exist"

-- Add status column with default value 'scheduled'
ALTER TABLE trips.trips
ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'scheduled';

-- Create index for status column to improve query performance
CREATE INDEX IF NOT EXISTS idx_trips_status ON trips.trips(status);

-- Comment for documentation
COMMENT ON COLUMN trips.trips.status IS 'Trip status: scheduled, canceled, en_route';
