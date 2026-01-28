-- Migration: Remove Ground Filters V1
-- Date: 2026-01-24
-- Description: Removes V1 batch-based filter system, keeping only V2 step-based
--
-- IMPORTANT: Make a backup before running this migration!
-- This migration is IRREVERSIBLE.

BEGIN;

-- 1. Drop filter_batches table (V1 only)
DROP TABLE IF EXISTS trips.filter_batches CASCADE;

-- 2. Drop filter_previews table (V1 only)
DROP TABLE IF EXISTS trips.filter_previews CASCADE;

-- 3. Remove V1-only columns from trips table
ALTER TABLE trips.trips DROP COLUMN IF EXISTS filter_batch_id;
ALTER TABLE trips.trips DROP COLUMN IF EXISTS filter_applied;

-- 4. Clear V1 references in trips that were filtered with V1 but not V2
-- Only reset trips where current_step_id is NULL (meaning V2 wasn't used)
-- This restores trips that were only modified by V1 to their original state
UPDATE trips.trips
SET original_pick_up_time = NULL,
    reduce_applied = FALSE,
    combine_applied = FALSE,
    expand_applied = FALSE,
    filtered_at = NULL
WHERE current_step_id IS NULL
  AND (original_pick_up_time IS NOT NULL OR reduce_applied = TRUE OR combine_applied = TRUE OR expand_applied = TRUE);

-- Note: Trips with current_step_id set (V2) keep their filter state intact

COMMIT;

-- Verification queries (run after migration):
--
-- Check tables were dropped:
-- SELECT table_name FROM information_schema.tables WHERE table_schema = 'trips' AND table_name IN ('filter_batches', 'filter_previews');
-- Should return 0 rows
--
-- Check columns were dropped:
-- SELECT column_name FROM information_schema.columns WHERE table_schema = 'trips' AND table_name = 'trips' AND column_name IN ('filter_batch_id', 'filter_applied');
-- Should return 0 rows
--
-- Check V2 tables still exist:
-- SELECT table_name FROM information_schema.tables WHERE table_schema = 'trips' AND table_name IN ('filter_steps', 'filter_presets');
-- Should return 2 rows
--
-- Check V2 trips are intact:
-- SELECT COUNT(*) FROM trips.trips WHERE current_step_id IS NOT NULL;
-- Should return count of V2-filtered trips
