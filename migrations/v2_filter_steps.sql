-- Migration: V2 Step-Based Filter System
-- Date: 2026-01-23
-- Description: Creates filter_steps table and adds current_step_id to trips

-- =============================================================================
-- 1. Create filter_steps table
-- =============================================================================

CREATE TABLE IF NOT EXISTS trips.filter_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    location_id UUID NOT NULL REFERENCES entities.locations(id) ON DELETE CASCADE,
    airline VARCHAR(10) NOT NULL,
    pick_up_date DATE NOT NULL,
    step_order INTEGER NOT NULL,
    filter_type VARCHAR(20) NOT NULL,  -- 'reduce', 'combine', 'expand'
    config JSONB NOT NULL,
    windows JSONB NOT NULL,  -- List of time windows
    trips_affected INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    -- Ensure unique step order per location+airline+date
    CONSTRAINT uq_filter_steps_order UNIQUE (location_id, airline, pick_up_date, step_order)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_filter_steps_location_date
    ON trips.filter_steps(location_id, airline, pick_up_date);

CREATE INDEX IF NOT EXISTS idx_filter_steps_active
    ON trips.filter_steps(is_active)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_filter_steps_created
    ON trips.filter_steps(created_at DESC);

-- =============================================================================
-- 2. Add current_step_id to trips table
-- =============================================================================

ALTER TABLE trips.trips
    ADD COLUMN IF NOT EXISTS current_step_id UUID
    REFERENCES trips.filter_steps(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_trips_current_step
    ON trips.trips(current_step_id)
    WHERE current_step_id IS NOT NULL;

-- =============================================================================
-- 3. Grant permissions (if needed)
-- =============================================================================

-- GRANT SELECT, INSERT, UPDATE, DELETE ON trips.filter_steps TO your_app_user;

-- =============================================================================
-- Verification queries
-- =============================================================================

-- Check table was created:
-- SELECT * FROM information_schema.tables WHERE table_name = 'filter_steps';

-- Check columns:
-- SELECT column_name, data_type FROM information_schema.columns
-- WHERE table_schema = 'trips' AND table_name = 'filter_steps';

-- Check current_step_id was added:
-- SELECT column_name, data_type FROM information_schema.columns
-- WHERE table_schema = 'trips' AND table_name = 'trips' AND column_name = 'current_step_id';
