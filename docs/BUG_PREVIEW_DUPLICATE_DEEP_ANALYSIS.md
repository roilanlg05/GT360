# Bug Preview Duplicate - Deep Analysis

**Date:** 2026-01-28
**Status:** 🔍 INVESTIGATING
**Reporter:** User
**Evidence:** Screenshot showing WN 4667 Mission Inn Hotel appearing twice

---

## 📊 Problem Description

After deploying the fix for duplicate trips in preview, the user reports that **WN 4667 Mission Inn Hotel** still appears TWICE in the preview changes for **Sat, Jan 31**.

---

## 🔍 Investigation Log

### Step 1: Verify Fix Deployment ✅

**Command:**
```bash
docker exec gt360 cat /app/features/trips/services/step_filter_service.py | grep -A 30 "def _apply_reduce"
```

**Result:** ✅ Fix IS deployed
```python
processed_trips = set()  # ← Present in deployed code

for window in config.windows:
    for trip in filtered_trips:
        if trip.id in processed_trips:  # ← Deduplication logic present
            continue
        processed_trips.add(trip.id)  # ← Tracking trips
```

**Conclusion:** The fix was successfully deployed.

---

### Step 2: Analyze Screenshot Evidence

From the screenshot:
- Date: **Sat, Jan 31**
- Total changes: **17 changes**
- Duplicate: **WN 4667 Mission Inn Hotel** appears twice:
  1. Line with purple icon: `04:35 → 04:40` (increases 5 min)
  2. Line with blue icon: `04:45 → 04:35` (decreases 10 min)

**Key Observations:**
1. Different original times: 04:35 vs 04:45
2. Different icons (purple vs blue) - suggests different filter types
3. Same flight number (4667) and hotel (Mission Inn Hotel)

---

### Step 3: Possible Explanations

#### Hypothesis 1: Different Trip IDs ❓
- These could be TWO DIFFERENT trips (different UUIDs)
- Same flight number, same hotel, but different pickup times
- Not actually a duplicate bug - just two separate trips

#### Hypothesis 2: Frontend Cache 🔍
- Frontend might be showing cached data from before the fix
- Need to verify if user refreshed after deployment

#### Hypothesis 3: Different Filter Types 🎯 LIKELY
- Purple icon = Combine filter (04:35 → 04:40, increases by 5)
- Blue icon = Reduce filter (04:45 → 04:35, decreases by 10)
- If BOTH filters are being previewed/applied, same trip could appear twice
- This would be CORRECT behavior if applying two different filters

#### Hypothesis 4: Bulk Preview Accumulation ❓
- The recent log shows: `/bulk/apply` endpoint was called
- Bulk operations aggregate changes from multiple operations
- Could be accumulating the same trip from different contexts

---

### Step 4: Code Flow Analysis

#### Per-Day Preview
```python
async def preview_step():
    self._reset_state()  # ← Resets self.changes and processed_trips
    
    if filter_type == "reduce":
        self._apply_reduce(trips, config)  # ← Has fix
    
    return StepResult(changes=self.changes)  # ← Unique per step
```

✅ This should work correctly with our fix.

#### Bulk Preview
```python
async def preview_bulk():
    all_changes = []
    
    for pick_up_date in dates:
        result = await self.preview_step(...)  # ← Calls preview_step
        all_changes.extend(result.changes)  # ← Accumulates
    
    return BulkStepResult(all_changes=all_changes)
```

⚠️ Potential issue: If `preview_step` is called MULTIPLE TIMES for the same date (shouldn't happen), or if there are trips with the same flight number but different trip_ids.

---

## 🧪 Testing Required

### Test 1: Verify Trip IDs

Need to check if the two appearances have:
- Same `trip_id` (duplicate bug) ❌
- Different `trip_id` (two separate trips) ✅

**Query:**
```sql
SELECT 
    id,
    flight_number,
    pick_up_location,
    pick_up_date,
    pick_up_time
FROM trips.trips
WHERE pick_up_date = '2026-01-31'
  AND flight_number = '4667'
  AND pick_up_location ILIKE '%Mission Inn%'
ORDER BY pick_up_time;
```

### Test 2: Check Frontend Cache

User should:
1. Hard refresh the page (Ctrl+Shift+R)
2. Clear browser cache
3. Try preview again

### Test 3: Direct API Test

Test the preview endpoint directly:
```bash
curl -X POST "http://localhost:8000/v2/locations/{loc}/airlines/WN/filters/step/preview" \
  -H "Content-Type: application/json" \
  -d '{
    "filter_type": "reduce",
    "pick_up_date": "2026-01-31",
    "windows": [
      {"start": "00:00", "end": "12:00", "minutes_to_reduce": 10},
      {"start": "04:00", "end": "06:00", "minutes_to_reduce": 5}
    ]
  }'
```

Check if response contains duplicates.

---

## 📋 Next Steps

1. ⏳ Ask user to verify trip details (are they same trip_id?)
2. ⏳ Check database for trips on Jan 31 with flight 4667
3. ⏳ Test preview endpoint directly with overlapping windows
4. ⏳ Verify if multiple filter types are being applied
5. ⏳ Check frontend network tab for actual API response

---

## 🎯 Likely Diagnosis

Based on the different icons and times, **most likely explanation**:
- These are TWO DIFFERENT operations or filter types
- Purple icon = Combine/Expand filter
- Blue icon = Reduce filter
- User is seeing the cumulative effect of multiple filters
- This is NOT a duplicate bug, but correct behavior

**To Confirm:**
Need user to check if they're applying MULTIPLE filters (Reduce + Combine) or if this is a single filter preview.

---

## 🔧 Potential Fix (If Real Bug)

If this IS a real duplicate bug, possible causes and fixes:

### Cause 1: Bulk operations not using fix
- Fix was only applied to `_apply_reduce`
- Need to verify bulk operations use the same code path

### Cause 2: Multiple step previews
- If frontend is calling preview multiple times and merging results
- Need to add deduplication at the API response level

### Cause 3: Different filter types
- If applying Reduce + Combine in sequence
- Need to deduplicate across filter types, not just within one

---

## 📊 Status

- ✅ Fix deployed successfully
- ✅ Code verified in container
- ❓ Real bug or expected behavior? - Need more info
- ⏳ Waiting for user clarification
