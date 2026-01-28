-- Verification Script for Bug #2: Revert Behavior
-- Purpose: Check if reverting one filter correctly preserves other filters
-- Usage: Run after applying 2 filters and reverting 1

-- ==============================================================================
-- SETUP: Replace these values with actual test data
-- ==============================================================================
-- \set location_id 'your-location-uuid'
-- \set airline 'WN'
-- \set test_date '2026-01-25'

-- ==============================================================================
-- Step 1: Check Current Stack State
-- ==============================================================================
SELECT
    'Current Filter Stack' as info,
    step_order,
    filter_type,
    is_active,
    trips_affected,
    created_at,
    id as step_id
FROM trips.filter_steps
WHERE location_id = :location_id
  AND airline = :airline
  AND pick_up_date = :test_date
ORDER BY step_order ASC;

-- Expected Result Examples:
-- After applying Reduce + Combine:
--   step_order=1, filter_type='reduce', is_active=true
--   step_order=2, filter_type='combine', is_active=true
--
-- After reverting Combine:
--   step_order=1, filter_type='reduce', is_active=true
--   step_order=2, filter_type='combine', is_active=false

-- ==============================================================================
-- Step 2: Check Trip Filter States
-- ==============================================================================
SELECT
    'Trip Filter States' as info,
    id,
    flight_number,
    pick_up_location as hotel,
    pick_up_time::text as current_time,
    original_pick_up_time::text as original_time,
    reduce_applied,
    combine_applied,
    expand_applied,
    current_step_id,
    filtered_at
FROM trips.trips
WHERE location_id = :location_id
  AND airline = :airline
  AND pick_up_date = :test_date
  AND trip_type = 'OUTBOUND'
  AND status = 'SCHEDULED'
ORDER BY pick_up_time ASC
LIMIT 50;

-- Expected Results for Bug #2 Verification:
--
-- SCENARIO 1: After applying Reduce + Combine
-- Trip affected by both:
--   reduce_applied=true, combine_applied=true
--
-- SCENARIO 2: After reverting Combine (Step 2)
-- Trip that was affected by both:
--   reduce_applied=true, combine_applied=false ← CORRECT BACKEND BEHAVIOR
--   (If both are false, backend has a bug)
--   (If both are true, revert didn't work)
--
-- SCENARIO 3: After reverting Reduce (Step 1)
-- Trip that was affected by both:
--   reduce_applied=false, combine_applied=false ← CORRECT (all filters gone)
--   original_pick_up_time=NULL ← CORRECT (no filters remain)

-- ==============================================================================
-- Step 3: Aggregate Statistics
-- ==============================================================================
SELECT
    'Filter Application Stats' as info,
    COUNT(*) as total_trips,
    COUNT(CASE WHEN original_pick_up_time IS NOT NULL THEN 1 END) as trips_with_filters,
    COUNT(CASE WHEN reduce_applied THEN 1 END) as reduce_count,
    COUNT(CASE WHEN combine_applied THEN 1 END) as combine_count,
    COUNT(CASE WHEN expand_applied THEN 1 END) as expand_count,
    COUNT(CASE WHEN reduce_applied AND combine_applied THEN 1 END) as both_reduce_combine,
    COUNT(CASE WHEN reduce_applied AND expand_applied THEN 1 END) as both_reduce_expand
FROM trips.trips
WHERE location_id = :location_id
  AND airline = :airline
  AND pick_up_date = :test_date
  AND trip_type = 'OUTBOUND'
  AND status = 'SCHEDULED';

-- ==============================================================================
-- Step 4: Detailed Analysis - Find Trips Affected by Multiple Filters
-- ==============================================================================
SELECT
    'Trips with Multiple Filters' as info,
    id,
    flight_number,
    pick_up_location as hotel,
    pick_up_time::text,
    original_pick_up_time::text,
    CASE
        WHEN reduce_applied AND combine_applied THEN 'Reduce + Combine'
        WHEN reduce_applied AND expand_applied THEN 'Reduce + Expand'
        WHEN combine_applied AND expand_applied THEN 'Combine + Expand'
        WHEN reduce_applied THEN 'Reduce only'
        WHEN combine_applied THEN 'Combine only'
        WHEN expand_applied THEN 'Expand only'
        ELSE 'No filters'
    END as filters_applied
FROM trips.trips
WHERE location_id = :location_id
  AND airline = :airline
  AND pick_up_date = :test_date
  AND trip_type = 'OUTBOUND'
  AND status = 'SCHEDULED'
  AND original_pick_up_time IS NOT NULL
ORDER BY
    (reduce_applied::int + combine_applied::int + expand_applied::int) DESC,
    pick_up_time ASC;

-- ==============================================================================
-- Bug #2 Verification Checklist
-- ==============================================================================
-- After reverting Step 2 (Combine) when Step 1 (Reduce) is still active:
--
-- ✓ CORRECT Backend Behavior:
--   1. Step 1: is_active=true
--   2. Step 2: is_active=false
--   3. Trips affected by both: reduce_applied=true, combine_applied=false
--   4. Trips affected by reduce only: reduce_applied=true, combine_applied=false
--   5. Trips affected by combine only: reduce_applied=false, combine_applied=false
--   6. current_step_id points to Step 1 for all filtered trips
--
-- ✗ INCORRECT Backend Behavior:
--   1. All trips have reduce_applied=false AND combine_applied=false
--   2. original_pick_up_time is NULL for trips that should still be filtered
--   3. Step 1 shows is_active=false when it should be true
--
-- If backend behavior is CORRECT but frontend shows all filters gone:
--   → Bug is in FRONTEND (not refetching trips or mishandling WebSocket events)
--
-- If backend behavior is INCORRECT:
--   → Bug is in BACKEND revert logic (needs further investigation)
