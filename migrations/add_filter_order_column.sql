-- Migration: Add filter_order column to trips and trips_history
-- Date: 2026-02-11
-- Purpose: Store chronological order of filters applied to each trip for frontend display

-- Add column to trips.trips
ALTER TABLE trips.trips
ADD COLUMN IF NOT EXISTS filter_order TEXT DEFAULT NULL;

-- Add column to trips.trips_history
ALTER TABLE trips.trips_history
ADD COLUMN IF NOT EXISTS filter_order TEXT DEFAULT NULL;

-- Add comment for documentation
COMMENT ON COLUMN trips.trips.filter_order IS 'Chronological order of filters applied, comma-separated (e.g., "expand,reduce" or "reduce,combine,expand")';
COMMENT ON COLUMN trips.trips_history.filter_order IS 'Chronological order of filters applied, comma-separated (e.g., "expand,reduce")';

-- Populate existing trips with filter_order based on current flags and steps
-- This is a best-effort migration - uses alphabetical order as fallback
UPDATE trips.trips
SET filter_order = (
    SELECT string_agg(filter_type, ',' ORDER BY step_order)
    FROM (
        SELECT DISTINCT
            CASE
                WHEN reduce_applied THEN 'reduce'
                WHEN combine_applied THEN 'combine'
                WHEN expand_applied THEN 'expand'
            END as filter_type,
            COALESCE(
                (SELECT fs.step_order
                 FROM trips.filter_steps fs
                 WHERE fs.filter_type = CASE
                    WHEN reduce_applied THEN 'reduce'
                    WHEN combine_applied THEN 'combine'
                    WHEN expand_applied THEN 'expand'
                 END
                 AND fs.pick_up_date = trips.pick_up_date
                 AND fs.airline = trips.airline
                 AND fs.location_id = trips.location_id
                 AND fs.is_active = true
                 LIMIT 1),
                999
            ) as step_order
        FROM trips.trips t
        WHERE t.id = trips.trips.id
        AND (t.reduce_applied OR t.combine_applied OR t.expand_applied)
    ) subq
    WHERE filter_type IS NOT NULL
)
WHERE (reduce_applied OR combine_applied OR expand_applied)
  AND filter_order IS NULL;

-- Do the same for trips_history
UPDATE trips.trips_history
SET filter_order = (
    SELECT string_agg(filter_type, ',' ORDER BY step_order)
    FROM (
        SELECT DISTINCT
            CASE
                WHEN reduce_applied THEN 'reduce'
                WHEN combine_applied THEN 'combine'
                WHEN expand_applied THEN 'expand'
            END as filter_type,
            COALESCE(
                (SELECT fs.step_order
                 FROM trips.filter_steps fs
                 WHERE fs.filter_type = CASE
                    WHEN reduce_applied THEN 'reduce'
                    WHEN combine_applied THEN 'combine'
                    WHEN expand_applied THEN 'expand'
                 END
                 AND fs.pick_up_date = trips.trips_history.pick_up_date
                 AND fs.airline = trips.trips_history.airline
                 AND fs.location_id = trips.trips_history.location_id
                 AND fs.is_active = true
                 LIMIT 1),
                999
            ) as step_order
        FROM trips.trips_history t
        WHERE t.id = trips.trips_history.id
        AND (t.reduce_applied OR t.combine_applied OR t.expand_applied)
    ) subq
    WHERE filter_type IS NOT NULL
)
WHERE (reduce_applied OR combine_applied OR expand_applied)
  AND filter_order IS NULL;

-- Verify migration
SELECT
    COUNT(*) as trips_with_filters,
    COUNT(filter_order) as trips_with_order
FROM trips.trips
WHERE reduce_applied OR combine_applied OR expand_applied;
