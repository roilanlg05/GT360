# Bug: Cross-Filter Duplication in Preview

**Date:** 2026-01-28
**Status:** 🔍 INVESTIGATING
**Severity:** HIGH
**Reporter:** User

---

## 📊 Problem Description

User reports seeing the SAME trip DUPLICATED when applying BOTH Reduce and Combine filters:

### Expected Behavior
```
{icon-reduce} {icon-combine} {original-time} → {new-time}
```
One line showing BOTH icons with the final result.

### Actual Behavior
```
Line 1: {icon-reduce} 04:45 → 04:35
Line 2: {icon-combine} 04:35 → 04:40
```
Same trip appearing TWICE in separate lines.

### User Confirmation
- ✅ Applying BOTH Reduce AND Combine
- ✅ Trip is NOT duplicated in database (verified from table screenshot)
- ✅ Same trip shown twice with different icons and times

---

## 🔍 Investigation

### Step 1: Verify Current Fix ✅

The fix deployed only prevents duplicates WITHIN the same filter type:
```python
# In _apply_reduce()
processed_trips = set()  # ← Prevents duplicate within Reduce

# But does NOT prevent across filter types
```

**Problem:** Fix only works for:
- Reduce + Reduce (overlapping windows) ✅
- Combine + Combine (multiple windows) ✅
- Expand + Expand (multiple windows) ✅

**Does NOT work for:**
- Reduce + Combine ❌ (different filter types)
- Reduce + Expand ❌
- Combine + Expand ❌

---

### Step 2: Backend Endpoint Analysis

**Preview Step Endpoint:**
```python
@router.post("/v2/.../filters/step/preview")
async def preview_step(config: FilterStepConfig):
    # Previews ONE SINGLE filter type at a time
    # filter_type = "reduce" OR "combine" OR "expand"
```

This endpoint ONLY previews ONE filter at a time.

**Bulk Preview Endpoint:**
```python
@router.post("/v2/.../filters/bulk/preview")
async def preview_bulk(config: BulkFilterConfig):
    # Applies ONE filter type to MULTIPLE dates
    # filter_type = one type
    # dates = multiple
```

This endpoint applies ONE filter type to multiple dates.

**Conclusion:** Backend doesn't have an endpoint that applies MULTIPLE filter types in a single call.

---

### Step 3: Possible Scenarios

#### Scenario A: Frontend Aggregation 🎯 LIKELY

Frontend is calling multiple preview/apply endpoints and combining results:

```typescript
// Frontend code (hypothetical)
const reduceChanges = await api.previewStep({filter_type: "reduce"});
const combineChanges = await api.previewStep({filter_type: "combine"});

// Combining both arrays
const allChanges = [...reduceChanges.changes, ...combineChanges.changes];
// ❌ Same trip appears in BOTH arrays
```

**If this is the case:** This is a FRONTEND BUG, not backend.

#### Scenario B: Stack Preview (Not Implemented)

Frontend wants to preview the ENTIRE stack (all active steps) but backend doesn't provide this:

```
Current Stack:
  Step 1: Reduce (already applied)
  Step 2: Combine (being previewed)

Frontend shows:
  - Changes from Step 1 (Reduce) ← From previous apply
  - Changes from Step 2 (Combine) ← From current preview

Result: Same trip twice if affected by both
```

**If this is the case:** Frontend should only show NEW changes, not existing.

#### Scenario C: Bulk Apply with Multiple Steps

User is using bulk apply which creates multiple steps at once:

```
Bulk Apply:
  - Creates Step 1 (Reduce) for Jan 31
  - Creates Step 2 (Combine) for Jan 31

Response contains:
  - all_changes array with ALL changes
  - If same trip affected by both, appears twice
```

**If this is the case:** Backend should deduplicate across steps.

---

## 🧪 Verification Needed

### Question 1: Where Are You Seeing This?

**Preview or Apply?**
- [ ] In PREVIEW (before clicking "Apply Changes")
- [ ] In APPLY result (after clicking "Apply Changes")
- [ ] In the trip list/table

### Question 2: How Are You Applying Filters?

**Method:**
- [ ] Step by step (Applied Reduce first, then previewing Combine)
- [ ] Bulk apply (Applying multiple filters at once)
- [ ] Using presets (Auto-apply multiple filters)

### Question 3: How Many Steps in Stack?

Check the current stack:
```bash
# Query to check
curl GET "/v2/locations/{loc}/airlines/WN/filters/stack?pick_up_date=2026-01-31"
```

Expected response:
```json
{
  "steps": [
    {"step_order": 1, "filter_type": "reduce", "is_active": true},
    {"step_order": 2, "filter_type": "combine", "is_active": true}
  ]
}
```

---

## 💡 Diagnosis Summary

Based on the evidence:

### Most Likely: Frontend Issue

**Reason:**
1. Backend endpoints only handle ONE filter type at a time
2. No backend code aggregates changes across filter types
3. Frontend must be combining results from multiple calls

**Fix Location:** Frontend
- Only show changes from current preview, not previous steps
- OR deduplicate trips when showing multiple steps
- OR group changes by trip_id and show all filter icons together

### Less Likely: Backend Issue with Bulk Operations

If using bulk apply/preview with a feature that applies multiple filter types:
- Need to verify bulk endpoints
- Need to add cross-filter deduplication

---

## 🔧 Potential Backend Fix (If Needed)

If backend needs to support previewing multiple filter types together:

### Option 1: Add Deduplication at Response Level

```python
async def preview_step(...):
    # Apply all filters...

    # Deduplicate changes by trip_id
    unique_changes = {}
    for change in self.changes:
        if change.trip_id not in unique_changes:
            unique_changes[change.trip_id] = change
        else:
            # Keep the latest change for this trip
            unique_changes[change.trip_id] = change

    return StepResult(changes=list(unique_changes.values()))
```

### Option 2: Add Multi-Step Preview Endpoint

```python
@router.post("/v2/.../filters/preview-stack")
async def preview_stack(configs: list[FilterStepConfig]):
    """Preview multiple filter steps together."""
    # Apply each filter
    # Deduplicate by trip_id
    # Return final state
```

---

## 📋 Next Steps

1. ⏳ Get clarification from user:
   - Preview or Apply?
   - Step-by-step or Bulk?
   - Check stack state

2. ⏳ If Frontend issue:
   - Report to frontend team
   - Provide expected behavior spec

3. ⏳ If Backend issue:
   - Implement cross-filter deduplication
   - Add multi-step preview endpoint
   - Test and deploy

---

## 🎯 Recommendation

**Most likely this is a FRONTEND issue** where the UI is showing:
- Existing applied filters (from stack)
- PLUS new preview changes
- Causing the same trip to appear twice

**Frontend should:**
- Only show changes from current preview
- OR clearly separate existing changes vs new changes
- OR deduplicate and show one line with multiple icons

**Backend is working correctly** - each endpoint returns unique changes for its filter type.

---

**Status:** Waiting for user clarification on:
1. Preview vs Apply?
2. Step-by-step vs Bulk?
3. Current stack state?
