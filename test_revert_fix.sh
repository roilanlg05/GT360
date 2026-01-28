#!/bin/bash
# Test script to verify the revert fix
# This script checks if the reduce_applied flag is correctly set after revert

LOCATION_ID="775af5fd-caf6-40c7-8236-d4728903d2d1"
TEST_DATE="2026-02-28"

echo "=================================================="
echo "Testing Revert Fix - Filter Flags"
echo "=================================================="
echo ""
echo "Location: ONT ($LOCATION_ID)"
echo "Test Date: $TEST_DATE"
echo ""

# Check current state
echo "Step 1: Checking current filter steps state..."
docker exec postgres psql -U gt360 -d gt360 -c "
SELECT
    step_order,
    filter_type,
    is_active,
    trips_affected
FROM trips.filter_steps
WHERE location_id = '$LOCATION_ID'
  AND pick_up_date = '$TEST_DATE'
ORDER BY step_order;
"

echo ""
echo "Step 2: Checking current trip flags (BEFORE fix test)..."
docker exec postgres psql -U gt360 -d gt360 -c "
SELECT
    COUNT(*) as total_trips,
    COUNT(CASE WHEN reduce_applied THEN 1 END) as with_reduce_flag,
    COUNT(CASE WHEN combine_applied THEN 1 END) as with_combine_flag,
    COUNT(CASE WHEN original_pick_up_time IS NOT NULL AND pick_up_time != original_pick_up_time THEN 1 END) as with_time_changes
FROM trips.trips
WHERE location_id = '$LOCATION_ID'
  AND pick_up_date = '$TEST_DATE'
  AND trip_type = 'outbound'
  AND status = 'scheduled';
"

echo ""
echo "Step 3: Sample trips to verify flags..."
docker exec postgres psql -U gt360 -d gt360 -c "
SELECT
    flight_number,
    original_pick_up_time::text as orig,
    pick_up_time::text as curr,
    reduce_applied as reduce,
    combine_applied as combine,
    current_step_id IS NOT NULL as has_step
FROM trips.trips
WHERE location_id = '$LOCATION_ID'
  AND pick_up_date = '$TEST_DATE'
  AND trip_type = 'outbound'
  AND status = 'scheduled'
  AND original_pick_up_time IS NOT NULL
ORDER BY pick_up_time
LIMIT 10;
"

echo ""
echo "=================================================="
echo "EXPECTED RESULTS AFTER FIX:"
echo "=================================================="
echo "✅ Steps 1 & 2 (Reduce): is_active = TRUE"
echo "✅ Step 3 (Combine): is_active = FALSE"
echo "✅ Trips with reduce_flag: Should be > 0 (122 expected)"
echo "✅ Trips with combine_flag: Should be 0 (was reverted)"
echo "✅ reduce column should show 't' (true) for modified trips"
echo ""
echo "If reduce_applied is still FALSE, the fix needs to be deployed."
echo "=================================================="
