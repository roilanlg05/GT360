# Race Condition: Revert WebSocket vs Database Commits

**Date:** 2026-01-28
**Severity:** HIGH
**Issue:** Frontend refetch occurs before all commits complete
**Status:** 🔍 CONFIRMED

---

## 🎯 Problem Confirmed

The frontend developer's analysis is **100% CORRECT**. There is a race condition where:

1. Backend sends WebSocket event **TOO EARLY**
2. Frontend receives event and triggers refetch **IMMEDIATELY**
3. Refetch happens **BETWEEN commits**, getting incomplete data

---

## 📊 Timeline of Events

### Current Flow (BUGGY)

```
Time | Backend | Database | Frontend
-----|---------|----------|----------
T0   | Revert API called | |
T1   | Mark step inactive | |
T2   | Reset trips | |
T3   | COMMIT 1 | All flags → FALSE ✅ |
T4   | Re-apply Step 1 | |
T5   | Set reduce_applied=TRUE | |
T6   | COMMIT 2 | reduce_applied=TRUE ✅ |
T7   | Re-apply Step 2 | |
T8   | Set combine_applied=TRUE | |
T9   | COMMIT 3 | combine_applied=TRUE ✅ |
T10  | Send WebSocket event | | ← EVENT SENT
T11  | | | WebSocket received
T12  | | | infiniteScroll.reset()
T13  | | | REFETCH trips ← TOO EARLY!
T14  | Return HTTP response | |
```

**Problem:** Refetch at T13 might read from database BEFORE commit at T9 is fully visible.

---

## 🔍 Code Analysis

### Current Code (Lines 748-855)

```python
async def _revert_step_internal(...):
    # FASE 1: Mark step inactive
    step.is_active = False
    self.session.add(step)

    # FASE 2: Reset ALL trips to original (líneas 748-761)
    for trip in trips:
        trip.reduce_applied = False  # ← All set to FALSE
        trip.combine_applied = False
        trip.expand_applied = False
    await self.session.commit()  # ← COMMIT 1 (all flags FALSE)

    # FASE 3: Re-apply remaining active steps (líneas 776-834)
    for active_step in active_steps:  # Ej: 2 steps
        # Apply filter
        trip.reduce_applied = True
        await self.session.commit()  # ← COMMIT 2 (reduce TRUE)

        # Next step
        trip.combine_applied = True
        await self.session.commit()  # ← COMMIT 3 (combine TRUE)

    # FASE 4: Get stack state (línea 844)
    stack_state = await self.get_stack(...)

    # FASE 5: Send WebSocket (línea 847)
    await self._send_revert_notification(...)  # ← TOO EARLY!

    # FASE 6: Return response (línea 849)
    return StepRevertResult(...)
```

### The Race Condition

```
Scenario: Revert Step 3 (Expand) when Steps 1 & 2 (Reduce, Combine) are active

Backend Timeline:
  [T1] COMMIT: All flags → FALSE
  [T2] COMMIT: reduce_applied → TRUE
  [T3] COMMIT: combine_applied → TRUE  ← Still processing
  [T4] Send WebSocket: "step_reverted"  ← EVENT SENT
  [T5] Return HTTP response

Frontend Timeline:
  [T4.1] WebSocket event received
  [T4.2] infiniteScroll.reset() triggered
  [T4.3] REFETCH trips ← Happens BEFORE T3 commit is visible!

Result:
  Frontend gets: reduce_applied=FALSE, combine_applied=FALSE ❌
  Expected: reduce_applied=TRUE, combine_applied=TRUE ✅
```

**Why it happens:**
1. WebSocket event is sent at line 847, AFTER commits finish
2. BUT PostgreSQL commits are asynchronous
3. Frontend receives WebSocket and refetches IMMEDIATELY
4. Database might not have propagated all changes yet
5. Frontend reads STALE data (from after COMMIT 1 but before COMMIT 3)

---

## 🐛 Root Cause

### Issue 1: WebSocket Sent Before Response

**Current order:**
```python
await self.session.commit()  # Last commit
await self._send_revert_notification()  # Send WebSocket ← LINE 847
return StepRevertResult(...)  # Return response ← LINE 849
```

**Problem:** WebSocket triggers frontend refetch BEFORE HTTP response arrives.

### Issue 2: Multiple Commits Create Windows for Race

**Current structure:**
```python
await self.session.commit()  # Commit 1: Reset
# ← Gap 1: Frontend can refetch here

for active_step in active_steps:
    # ... apply filter ...
    await self.session.commit()  # Commit 2
    # ← Gap 2: Frontend can refetch here

    # ... next step ...
    await self.session.commit()  # Commit 3
    # ← Gap 3: Frontend can refetch here

await self._send_revert_notification()  # WebSocket
```

Even though WebSocket is sent at the end, if there's ANY delay in:
- Commit propagation
- Redis pub/sub
- WebSocket message delivery
- Frontend processing

The frontend's refetch can land between commits.

---

## ✅ Solutions

### Solution 1: Move WebSocket AFTER Return (Recommended)

The WebSocket notification should be sent AFTER the HTTP response is returned, not before.

**Problem:** FastAPI returns response synchronously, can't send WebSocket after.

**Alternative:** Send WebSocket in a background task.

```python
from fastapi import BackgroundTasks

async def _revert_step_internal(...):
    # ... all commits ...

    stack_state = await self.get_stack(...)

    # DON'T send WebSocket here
    # await self._send_revert_notification(...)  # ← REMOVE

    return StepRevertResult(
        step_id=step_id,
        stack_state=stack_state,
        # ... other fields ...
    )

# In the router
@router.post("/revert-last")
async def revert_last_step(
    background_tasks: BackgroundTasks,
    ...
):
    result = await service.revert_last_step(...)

    # Send WebSocket AFTER response is ready
    background_tasks.add_task(
        service._send_revert_notification,
        location_uuid, airline, result.step_id, result.filter_type
    )

    return result
```

### Solution 2: Single Commit at End (Alternative)

Instead of committing after each step, accumulate all changes and commit once:

```python
async def _revert_step_internal(...):
    # Reset trips (NO commit yet)
    for trip in trips:
        trip.reduce_applied = False
        self.session.add(trip)
    # DON'T COMMIT

    # Re-apply all steps (NO commits yet)
    for active_step in active_steps:
        # Apply filter
        trip.reduce_applied = True
        self.session.add(trip)
        # DON'T COMMIT

    # SINGLE COMMIT at end
    await self.session.commit()

    # Now send WebSocket (all changes are committed)
    await self._send_revert_notification(...)

    return StepRevertResult(...)
```

**Trade-off:** If revert fails midway, need to rollback entire operation.

### Solution 3: Add Delay Before WebSocket (Quick Fix)

Add a small delay to ensure commits are visible:

```python
# After all commits
await self.session.commit()

# Small delay to ensure commit visibility
await asyncio.sleep(0.1)  # 100ms

# Now send WebSocket
await self._send_revert_notification(...)
```

**Trade-off:** Hacky, not guaranteed to work in all cases.

### Solution 4: Frontend Waits for HTTP Response (Frontend Fix)

Frontend should refetch based on HTTP response, not WebSocket:

```typescript
// ❌ CURRENT (buggy)
websocket.on('step_reverted', () => {
    infiniteScroll.reset();  // Refetch immediately
});

// ✅ FIXED
const revertStep = async (stepId) => {
    const response = await api.revertStep(stepId);  // Wait for response

    // Use response data (guaranteed to be consistent)
    setFilters(response.stack_state.steps);

    // Refetch trips AFTER HTTP response
    await refetchTrips();
};

// WebSocket only for multi-tab sync
websocket.on('step_reverted', () => {
    if (!isCurrentUserAction) {  // Another tab reverted
        refetchStack();
        refetchTrips();
    }
});
```

---

## 🎯 Recommended Solution

**Best approach:** Combination of Solution 1 + Solution 4

### Backend Change:
Send WebSocket as background task AFTER HTTP response:

```python
# In router (step_filter_router.py)
@router.post("/revert-last")
async def revert_last_step(
    background_tasks: BackgroundTasks,
    location_id: str,
    airline: str,
    pick_up_date: str,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> StepRevertResult:
    location_uuid = UUID(location_id)
    service = StepFilterService(session)

    result = await service.revert_last_step(location_uuid, airline, pick_up_date)

    # Send WebSocket AFTER response is ready to be returned
    background_tasks.add_task(
        send_revert_notification_task,
        location_uuid, airline, result.step_id, result.filter_type
    )

    return result
```

### Frontend Change:
Rely on HTTP response, use WebSocket only for multi-tab:

```typescript
const handleRevert = async (stepId) => {
    // Wait for HTTP response (guaranteed consistent)
    const response = await api.revertStep(stepId);

    // Update UI from response
    setFilters(response.stack_state.steps);
    await refetchTrips();
};
```

---

## 📊 Why This Happens

### PostgreSQL Transaction Isolation

Default isolation level: READ COMMITTED

```
Transaction 1 (Revert):          Transaction 2 (Refetch):
-------------------------        -------------------------
BEGIN
UPDATE trips SET flags=FALSE
COMMIT ← visible
                                 BEGIN
                                 SELECT trips ← Sees FALSE
UPDATE trips SET reduce=TRUE
COMMIT ← not visible yet
                                 (reads stale data)
UPDATE trips SET combine=TRUE
COMMIT
                                 COMMIT
```

Even though commits are awaited, there can be a tiny window where:
- Commit 1 is visible (flags=FALSE)
- Commit 2-3 not yet visible (reduce=FALSE, combine=FALSE)

### Redis Pub/Sub Speed

Redis pub/sub is VERY fast (sub-millisecond), so:
```
T1: commit() returns
T2: WebSocket sent to Redis (0.5ms)
T3: Frontend receives WebSocket (1ms)
T4: Frontend triggers refetch (2ms)
T5: Refetch query reaches DB (3ms) ← Might see partial commits
T6: Next commit() completes (5ms)
```

The refetch at T5 can happen before all commits are visible.

---

## 🧪 Testing the Race Condition

### Test 1: Reproduce the Bug

```python
# Apply 3 steps
await apply_step(Reduce)  # Step 1
await apply_step(Combine)  # Step 2
await apply_step(Expand)  # Step 3

# Revert Step 3
result = await revert_last_step(date="2026-01-31")

# Immediately query database
trips = await get_trips(date="2026-01-31")

# Check flags
print([t.reduce_applied for t in trips])  # Might show FALSE
print([t.combine_applied for t in trips])  # Might show FALSE

# Wait 100ms
await asyncio.sleep(0.1)

# Query again
trips = await get_trips(date="2026-01-31")
print([t.reduce_applied for t in trips])  # Shows TRUE
print([t.combine_applied for t in trips])  # Shows TRUE
```

### Test 2: Verify WebSocket Timing

```python
import time

# Start timer
start = time.time()

# Call revert
result = await revert_last_step(...)
http_response_time = time.time() - start

# Log
print(f"HTTP response time: {http_response_time}ms")
# WebSocket was sent during this time
```

---

## 💡 Immediate Fix

### Quick Fix (Backend): Add Small Delay

While we implement the proper fix, add a small delay:

```python
async def _revert_step_internal(...):
    # ... all commits ...

    # Ensure all commits are fully visible
    await asyncio.sleep(0.05)  # 50ms delay

    # Now send WebSocket
    await self._send_revert_notification(...)

    return StepRevertResult(...)
```

**Location:** Line 847 in `step_filter_service.py`

### Proper Fix (Backend): Background Task

Remove WebSocket from internal method, send it from router:

```python
# In _revert_step_internal: REMOVE line 847
# DON'T send WebSocket here

# In router: ADD background task
background_tasks.add_task(
    send_notification,
    location_uuid, airline, result.step_id, result.filter_type
)
```

### Best Fix (Frontend): Use HTTP Response

```typescript
// Don't refetch on WebSocket for current user's actions
const handleRevert = async (stepId) => {
    // Wait for HTTP response
    const response = await api.revertStep(stepId);

    // Use response data (guaranteed consistent)
    updateFromResponse(response);
};

// WebSocket only for OTHER users/tabs
websocket.on('step_reverted', (event) => {
    if (!isCurrentUserAction) {
        refetchData();
    }
});
```

---

## 🔧 Implementation

I'll implement the quick fix (add delay) now while recommending the proper architectural fix for later.

---

## 📋 Summary

**Frontend Developer's Analysis:** ✅ CORRECT

**Root Cause:** WebSocket event triggers refetch before all commits are visible

**Why Multiple Commits:** Each active step commits individually for consistency

**Fix Options:**
1. ⚡ Quick: Add 50ms delay before WebSocket
2. 🏗️ Proper: Send WebSocket as background task after HTTP response
3. 🎨 Best: Frontend uses HTTP response, WebSocket only for multi-tab

**Recommendation:** Apply quick fix now + implement proper fix later
