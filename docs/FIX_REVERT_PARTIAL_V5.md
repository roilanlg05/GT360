# Fix: Revert Partial - Preserve Filter Values

## Issue Summary

**Problem:** When using `revert-partial` to remove one filter (e.g., EXPAND) while keeping others (e.g., REDUCE), the remaining filter's values were being reset to their defaults:
- `reduce_applied` was reset to `false`
- `original_pick_up_time` was reset to `NULL`

**Impact:** After partial revert, trips appeared as if no filters were applied, even though REDUCE should have remained active.

## Root Cause

The issue was caused by SQLAlchemy's session identity map. When `revert_partial` was called:

1. **Step 1** reverted all trips and committed, but the Trip objects remained in the session's identity map
2. **Step 3** called `apply()` to re-apply remaining filters
3. `apply()` loaded "fresh" trips from DB, but SQLAlchemy returned the **same Python objects** from the identity map
4. These objects had conflicting state, causing the ORM to reset fields to defaults on commit

## Solution

Added `session.expunge_all()` before calling `apply()` in Step 3 to completely clear the session's identity map. This ensures `apply()` loads truly fresh Trip objects from the database.

### Code Change

```python
# In revert_partial(), before calling apply():

# Save filter_batch values before expunging (they'll be detached after expunge)
location_id_for_apply = filter_batch.location_id
airline_for_apply = filter_batch.airline

# CRITICAL: Clear the session before apply() to avoid identity map conflicts
self.session.expunge_all()

# Re-apply remaining filters with existing batch_id
result = await self.apply(
    location_id=location_id_for_apply,
    airline=airline_for_apply,
    config=modified_config,
    existing_batch_id=batch_id,
    skip_batch_record=True,
)
```

## Additional Changes

1. **`apply()` now accepts optional parameters:**
   - `existing_batch_id`: Reuse an existing batch ID instead of creating a new one
   - `skip_batch_record`: Skip creating a FilterBatch record when reusing existing batch

2. **Simplified `revert_partial` flow:**
   - Removed complex "Step 3b" that tried to move trips between batches
   - Now directly reuses the original batch ID

## Verification

### Before Fix
```sql
-- After revert-partial of EXPAND (keeping REDUCE):
SELECT reduce_applied, expand_applied, original_pick_up_time IS NOT NULL
FROM trips.trips WHERE filter_batch_id = '...'

reduce_applied | expand_applied | has_original
---------------+----------------+-------------
 f             | f              | f           -- WRONG!
```

### After Fix
```sql
-- After revert-partial of EXPAND (keeping REDUCE):
SELECT reduce_applied, expand_applied, original_pick_up_time IS NOT NULL
FROM trips.trips WHERE filter_batch_id = '...'

reduce_applied | expand_applied | has_original
---------------+----------------+-------------
 t             | f              | t           -- CORRECT!
```

## Frontend Integration

No frontend changes are required. The API contract remains the same:

### Endpoint
```
POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/revert-partial
    ?batch_id={uuid}
    &filter_type={reduce|combine|expand}
```

### Response
```json
{
  "batch_id": "uuid",
  "filter_reverted": "expand",
  "trips_affected": 338,
  "filters_reapplied": ["reduce"],
  "changes_applied": 338,
  "summary": {
    "reduce": 338,
    "combine": 0,
    "expand": 0,
    "excluded": 0
  }
}
```

### What the Frontend Should Expect

After calling `revert-partial`:

1. **Trips in the batch will have:**
   - `reduce_applied = true` (if REDUCE was kept)
   - `expand_applied = false` (if EXPAND was reverted)
   - `original_pick_up_time` preserved (not NULL)
   - `pick_up_time` recalculated based on remaining filters

2. **The batch's `filters_applied` will be updated** to only show remaining filters

3. **Refresh trip data** after calling revert-partial to see updated times

## Files Modified

- `features/trips/services/trip_filter_service.py`
  - Added `existing_batch_id` and `skip_batch_record` parameters to `apply()`
  - Added `session.expunge_all()` in `revert_partial()` before calling `apply()`
  - Simplified Step 3 to use existing batch ID directly

## Testing

```bash
# 1. Apply REDUCE + EXPAND
POST /filters/apply
Body: { reduce: {enabled: true}, expand: {enabled: true} }

# 2. Partial revert EXPAND (keep REDUCE)
POST /filters/revert-partial?batch_id={batch}&filter_type=expand

# 3. Verify trips have reduce_applied=true, expand_applied=false, original_pick_up_time set
GET /trips?filter_batch_id={batch}
```

## Date
2026-01-20
