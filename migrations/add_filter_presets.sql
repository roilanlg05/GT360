-- Migration: Filter Presets (Auto-Apply on Import)
-- Date: 2026-01-23
-- Description: Creates filter_presets table for storing global filter templates

-- =============================================================================
-- 1. Create filter_presets table
-- =============================================================================

CREATE TABLE IF NOT EXISTS trips.filter_presets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    location_id UUID NOT NULL REFERENCES entities.locations(id) ON DELETE CASCADE,
    airline VARCHAR(10) NOT NULL,
    stack_template JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID REFERENCES entities.users(id) ON DELETE SET NULL,

    -- One preset per location+airline
    CONSTRAINT uq_filter_presets_location_airline UNIQUE (location_id, airline)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_filter_presets_location_airline
    ON trips.filter_presets(location_id, airline);

CREATE INDEX IF NOT EXISTS idx_filter_presets_created_at
    ON trips.filter_presets(created_at DESC);

-- =============================================================================
-- 2. Trigger for updated_at
-- =============================================================================

CREATE OR REPLACE FUNCTION update_filter_presets_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_filter_presets_updated_at ON trips.filter_presets;

CREATE TRIGGER trigger_filter_presets_updated_at
BEFORE UPDATE ON trips.filter_presets
FOR EACH ROW
EXECUTE FUNCTION update_filter_presets_updated_at();

-- =============================================================================
-- Verification queries
-- =============================================================================

-- Check table was created:
-- SELECT * FROM information_schema.tables WHERE table_name = 'filter_presets';

-- Check columns:
-- SELECT column_name, data_type FROM information_schema.columns
-- WHERE table_schema = 'trips' AND table_name = 'filter_presets';
