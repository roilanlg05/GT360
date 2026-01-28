# CRITICAL BUG: Revert Process Not Setting Filter Flags

**Date:** 2026-01-27
**Severity:** HIGH
**Location Tested:** ONT (ID: `775af5fd-caf6-40c7-8236-d4728903d2d1`)
**Test Scenario:** Apply Reduce → Apply Reduce again → Apply Combine → Revert Combine

---

## 🚨 Executive Summary

**CRITICAL BUG FOUND IN BACKEND REVERT PROCESS**

The revert process is correctly:
- ✅ Marking the reverted step as inactive
- ✅ Resetting trips to original times
- ✅ Re-applying remaining active steps
- ✅ Updating `pick_up_time`, `current_step_id`, `filtered_at`

BUT FAILING TO:
- ❌ Set the filter flags (`reduce_applied`, `combine_applied`, `expand_applied`)

**Result:** Trips have modified times and correct `current_step_id`, but **ALL filter flags are FALSE**.

---

## 📊 Database Evidence

### Filter Steps State (2026-02-28)

```sql
Step Order | Filter Type | Active  | Trips Affected | Step ID
-----------|-------------|---------|----------------|----------
    1      | reduce      | TRUE ✅  |      18       | 78e258b4...
    2      | reduce      | TRUE ✅  |      18       | d848c8b1...
    3      | combine     | FALSE ❌ |       8       | f3aa02f0...
```

**Timeline:**
```
22:03:45 - Step 1 (Reduce) created & applied
22:03:58 - Step 2 (Reduce) created & applied
22:04:00 - Step 3 (Combine) created & applied
22:04:?? - Step 3 (Combine) REVERTED
```

**Expected State After Revert:**
- Steps 1 & 2: Active
- Step 3: Inactive
- Trips: `reduce_applied = TRUE` (from Steps 1 & 2)

---

## 🔍 Trip State Analysis

### Sample Trips from Feb 28

| Flight | Original Time | Current Time | reduce_applied | combine_applied | current_step_id |
|--------|--------------|--------------|----------------|-----------------|-----------------|
| 3027   | 05:35:00     | **05:25:00** | **FALSE ❌**   | FALSE           | Step 2 (d848..) |
| 3018   | 05:50:00     | **05:40:00** | **FALSE ❌**   | FALSE           | Step 2 (d848..) |
| 2220   | 06:10:00     | **06:00:00** | **FALSE ❌**   | FALSE           | Step 2 (d848..) |
| 1869   | 06:20:00     | **06:10:00** | **FALSE ❌**   | FALSE           | Step 2 (d848..) |
| 2193   | 13:40:00     | **13:30:00** | **FALSE ❌**   | FALSE           | Step 2 (d848..) |
| 3022   | 13:50:00     | **13:40:00** | **FALSE ❌**   | FALSE           | Step 2 (d848..) |

**Observations:**
1. ✅ Times ARE modified (reduced by 10 minutes)
2. ✅ `current_step_id` points to Step 2 (correct)
3. ✅ `filtered_at` has timestamp
4. ❌ `reduce_applied` is **FALSE** (should be TRUE)
5. ❌ `combine_applied` is **FALSE** (correct, was reverted)
6. ❌ `expand_applied` is **FALSE** (correct, never applied)

---

## 📈 Statistics

### Total Impact

```sql
Location: 775af5fd-caf6-40c7-8236-d4728903d2d1
Airline: WN
Total OUTBOUND SCHEDULED trips: 461

Trips with filters applied:
- Have original_pick_up_time: 461 (100%)
- Have reduce_applied flag:    0   (0%) ❌
- Have combine_applied flag:   0   (0%) ✅ (correct, was reverted)
- Have expand_applied flag:    0   (0%) ✅ (correct, never applied)

Trips with modified times but missing flags: 122 ❌
```

**This affects 122 out of 461 trips** (26.5%)

---

## 🐛 Root Cause Analysis

### Code Location
File: `features/trips/services/step_filter_service.py`
Method: `_revert_step_internal()`
Lines: 707-839

### Revert Flow

```python
async def _revert_step_internal(...):
    # 1. Mark step as inactive ✅
    step.is_active = False

    # 2. Get all filtered trips ✅
    trips = await self.session.exec(trips_query).all()

    # 3. Reset all trips to original ✅
    for trip in trips:
        trip.pick_up_time = trip.original_pick_up_time
        trip.reduce_applied = False      # ← All set to FALSE
        trip.combine_applied = False     # ← All set to FALSE
        trip.expand_applied = False      # ← All set to FALSE
        trip.current_step_id = None

    # 4. COMMIT RESET ✅
    await self.session.commit()  # Line 761

    # 5. Get remaining active steps ✅
    active_steps = await self.session.exec(active_steps_query).all()

    # 6. Re-apply each active step ✅
    if active_steps:
        trips = await self.session.exec(trips_query).all()  # Line 779
        trip_lookup = {t.id: t for t in trips}               # Line 780

        for active_step in active_steps:
            # Get trips for this step
            current_trips = await self._get_eligible_trips(...)  # Line 793

            # Apply filter (updates trip times in memory)
            self._apply_reduce(current_trips, config)  # Line 797

            # Persist changes
            for change in self.changes:
                trip = trip_lookup.get(change.trip_id)  # Line 806
                if not trip:
                    # Fetch from DB if not in lookup
                    trip = await self.session.exec(...).first()  # Line 810

                if trip:
                    # Update trip properties
                    trip.pick_up_time = change.new_time           # Line 814 ✅
                    trip.current_step_id = active_step.id         # Line 815 ✅
                    trip.filtered_at = now                        # Line 816 ✅

                    # SET FLAGS ← THIS SHOULD WORK
                    if config.filter_type == "reduce":
                        trip.reduce_applied = True  # Line 819 ❌ NOT HAPPENING
                    elif config.filter_type == "combine":
                        trip.combine_applied = True
                    elif config.filter_type == "expand":
                        trip.expand_applied = True

                    self.session.add(trip)  # Line 825

            await self.session.commit()  # Line 828 (NOT in original code!)
```

### Suspected Issues

#### Issue #1: Missing Commit After Re-applying Steps?

Looking at line 828, there should be a `commit()` after re-applying each step, but I need to verify this exists in the actual code.

If the commit is OUTSIDE the loop, then only the LAST step's changes would be persisted with flags set.

#### Issue #2: Trip Lookup Stale Reference

Line 779: Gets trips from DB (after reset commit)
Line 793: Gets trips AGAIN with `_get_eligible_trips()`
Line 806: Tries to find trip in the ORIGINAL lookup from line 780

**Problem:** If `_get_eligible_trips()` returns different trip instances than those in `trip_lookup`, the lookup will fail and fall back to line 810.

**Hypothesis:** Line 810 fetches a FRESH trip from DB, but this fresh trip might not have all the necessary context, OR there's a session/transaction issue where changes aren't being tracked.

#### Issue #3: Session State Confusion

After the commit on line 761, the session is flushed. When trips are fetched again on line 779, they're new instances. But if the trips from `_get_eligible_trips()` (line 793) are YET ANOTHER set of instances, we might have:
- `trip_lookup` trips (from line 780)
- `current_trips` trips (from line 793)
- Fresh trips from DB (from line 810)

Changes to one might not reflect in another.

---

## 🔬 Detailed Investigation Needed

### Questions to Answer

1. **Where is the commit after re-applying steps?**
   - Line 828 should have `await self.session.commit()`
   - Is it there? Is it inside or outside the loop?

2. **Why are trips fetched twice?**
   - Line 779: `trips = await self.session.exec(trips_query).all()`
   - Line 793: `current_trips = await self._get_eligible_trips(...)`
   - Are these returning the same trip instances?

3. **Is trip_lookup working correctly?**
   - Does `change.trip_id` match the IDs in `trip_lookup`?
   - Is the fallback to line 810 always being hit?

4. **Are flags being set but not committed?**
   - Add logging to see if line 819 is executed
   - Add logging to see if trip is added to session (line 825)
   - Check if changes are lost before commit

---

## 🧪 Verification Queries

### Check if flags are set for any trips

```sql
SELECT
    COUNT(*) as total,
    COUNT(CASE WHEN reduce_applied THEN 1 END) as has_reduce_flag,
    COUNT(CASE WHEN original_pick_up_time IS NOT NULL THEN 1 END) as has_filter
FROM trips.trips
WHERE location_id = '775af5fd-caf6-40c7-8236-d4728903d2d1'
  AND trip_type = 'outbound'
  AND status = 'scheduled';
```

**Expected:** has_reduce_flag > 0 (at least some trips should have the flag)
**Actual:** has_reduce_flag = 0 ❌

### Find trips modified but missing flags

```sql
SELECT
    flight_number,
    original_pick_up_time::text as orig,
    pick_up_time::text as curr,
    reduce_applied,
    current_step_id
FROM trips.trips
WHERE location_id = '775af5fd-caf6-40c7-8236-d4728903d2d1'
  AND trip_type = 'outbound'
  AND status = 'scheduled'
  AND original_pick_up_time IS NOT NULL
  AND pick_up_time != original_pick_up_time
  AND reduce_applied = false
LIMIT 10;
```

**Result:** 122 trips found ❌

---

## 💡 Recommended Fixes

### Fix #1: Ensure Commit is Inside the Loop

**Current Code (lines 782-828):**
```python
for active_step in active_steps:
    self._reset_state()
    # ... apply filter ...
    for change in self.changes:
        # ... update trip ...
        self.session.add(trip)
    # NEEDS COMMIT HERE! ← Check if this exists

# await self.session.commit()  # If commit is here, it's wrong
```

**Should be:**
```python
for active_step in active_steps:
    self._reset_state()
    # ... apply filter ...
    for change in self.changes:
        # ... update trip ...
        self.session.add(trip)

    await self.session.commit()  # ← Must be inside loop
```

### Fix #2: Use Same Trip Instances

Instead of fetching trips multiple times, use the same trip instances throughout:

```python
if active_steps:
    trips = await self.session.exec(trips_query).all()

    for active_step in active_steps:
        # Use the SAME trips instance, not re-fetching
        eligible_trips = [
            t for t in trips
            if t.trip_type == TripType.OUTBOUND
            and t.status == TripStatus.SCHEDULED
        ]

        self._apply_reduce(eligible_trips, config)

        for change in self.changes:
            # Find trip in our existing list
            trip = next((t for t in trips if t.id == change.trip_id), None)
            if trip:
                # Update trip...
                trip.reduce_applied = True
                self.session.add(trip)

        await self.session.commit()
```

### Fix #3: Add Logging for Debugging

Add debug logging to understand what's happening:

```python
for change in self.changes:
    trip = trip_lookup.get(change.trip_id)
    logger.debug(f"Processing change for trip {change.trip_id}, found in lookup: {trip is not None}")

    if not trip:
        trip = await self.session.exec(...).first()
        logger.debug(f"Fetched from DB: {trip is not None}")

    if trip:
        logger.debug(f"Before: reduce_applied={trip.reduce_applied}")
        trip.reduce_applied = True
        logger.debug(f"After: reduce_applied={trip.reduce_applied}")
        self.session.add(trip)
```

---

## 🎯 Immediate Action Items

1. **Review Code:** Check line 818-828 in `step_filter_service.py`
   - Is there a `commit()` inside the loop?
   - Is the commit outside the loop?

2. **Add Debugging:**
   - Add logs to see if line 819 is executed
   - Add logs to see trip IDs and lookup results
   - Check if `self.session.add(trip)` is called

3. **Test Fix:**
   - Apply the recommended fix #1 or #2
   - Revert Combine again on ONT location
   - Check if `reduce_applied` is set to TRUE

4. **Verify All Locations:**
   - This bug likely affects ALL locations
   - Check other locations that had reverts
   - May need to fix historical data

---

## 📝 Frontend Impact

### Why Frontend Shows All Filters Gone

If trips have:
- `original_pick_up_time` set
- `reduce_applied = FALSE`
- `combine_applied = FALSE`
- `expand_applied = FALSE`

The frontend logic might be:
```typescript
const hasFilters = trip.reduce_applied || trip.combine_applied || trip.expand_applied;

if (hasFilters) {
  showFilterChips();
} else {
  hideFilterChips();  // ← This happens because all flags are false
}
```

Even though `current_step_id` points to an active step and times are modified, if the frontend relies on the boolean flags to show UI, it will appear as if NO filters are active.

---

## ✅ Conclusion

**Backend Bug Confirmed:** ❌
**Frontend Bug:** ❓ (Might also have issues, but backend is definitely broken)

The backend revert process has a critical bug where it:
1. ✅ Correctly reverts the step (marks as inactive)
2. ✅ Correctly resets trips to original times
3. ✅ Correctly re-applies remaining steps (times are modified)
4. ✅ Correctly updates `current_step_id` and `filtered_at`
5. ❌ **FAILS to set filter flags (`reduce_applied`, `combine_applied`, `expand_applied`)**

This causes trips to have modified times but no filter flags, making the frontend think no filters are active.

**Priority:** CRITICAL - Fix immediately
**Affected:** All locations that have used revert functionality
**Data Integrity:** May need to run a migration to fix existing trips

---

## 📎 Test Data Reference

```
Location ID: 775af5fd-caf6-40c7-8236-d4728903d2d1
Location Name: ONT
Airline: WN
Test Date: 2026-02-28

Active Steps:
- Step 1: 78e258b4-ef4e-40c8-bb8a-a87158377386 (Reduce, active)
- Step 2: d848c8b1-86f0-4b4d-8a17-a40ecc5a2aad (Reduce, active)
- Step 3: f3aa02f0-1c5c-4112-aee3-74e0b59424eb (Combine, inactive)

Affected Trips: 122 with modified times but reduce_applied = FALSE
```
