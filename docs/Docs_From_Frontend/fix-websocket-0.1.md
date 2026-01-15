# WebSocket Batch Fix v0.1

**Date:** 2026-01-05
**Status:** Implemented
**Version:** 0.1

---

## Summary

This document describes the frontend fixes implemented to resolve issues with WebSocket batch processing for trips.

---

## Problems Resolved

| Issue | Description | Status |
|-------|-------------|--------|
| Duplicate trips on XLS upload | Counter showed 2x expected trips | Fixed |
| "Maximum update depth exceeded" | React error when deleting locations with many trips | Fixed (frontend ready, requires backend `SEND_WS_BATCH=True`) |
| Slow deletion | Trip-by-trip instead of batch processing | Fixed (requires backend) |

---

## Root Cause Analysis

### Problem 1: Synthetic Event Bug

**File:** `src/hooks/use-websocket-trips.ts`
**Lines:** 212-233 (before fix)

The code created a synthetic event for batch notifications that only included the first trip:
```typescript
trip: event.events[0]?.trip,  // Only first trip!
```

This caused the provider to process incorrect data when handling batch events.

### Problem 2: Triple Data Path on XLS Upload

**File:** `src/app/(main)/dashboard/locations/[code]/[airline]/schedule-dashboard-client.tsx`

Three routes were adding trips simultaneously:
1. **REST Response:** `handleUploaded() → setRowsData(trips)`
2. **WebSocket Batch:** `isTripsBatchMessage() → setTrips()`
3. **Effect Hook:** `useEffect → syncs store trips → rowsData`

This caused the trip counter to show double the actual number.

### Problem 3: Backend Not Sending Batch Messages

The error stack trace pointed to line 238 (individual event handler) instead of line 173 (batch handler), indicating the backend was sending 688 individual `trip_event` messages instead of one `trips_batch` message.

---

## Fixes Implemented

### FIX 1: Remove Synthetic Event

**File:** `src/hooks/use-websocket-trips.ts`

**Before:**
```typescript
// Created synthetic event with only first trip
onTripEventRef.current({
  type: 'trip_event',
  event_type: eventType,
  location_id: event.location_id,
  trip_id: `batch-${count}`,
  trip: event.events[0]?.trip,  // BUG: Only first trip
  _batch: { count, eventType },
})
```

**After:**
```typescript
// Show notification directly, no synthetic event
if (event.events.length > 0) {
  const predominant = (Object.entries(counts) as [keyof typeof counts, number][])
    .filter(([, count]) => count > 0)
    .sort((a, b) => b[1] - a[1])[0]

  if (predominant) {
    const [eventType, count] = predominant
    showBatchNotification(eventType, count)
  }
}
```

### FIX 2: Remove Direct rowsData Setting on XLS Upload

**File:** `src/app/(main)/dashboard/locations/[code]/[airline]/schedule-dashboard-client.tsx`

**Before:**
```typescript
const handleUploaded = (event: Event) => {
  // ...
  setRowsData(toTripRows(trips));  // Caused duplicates
  // ...
};
```

**After:**
```typescript
const handleUploaded = (event: Event) => {
  // ...
  // Don't set rowsData directly - WebSocket batch will sync automatically
  console.log('[Upload] Received', trips.length, 'trips, waiting for WebSocket sync');
  // ...
};
```

### FIX 3: Add Provider Guard for Batch Events

**File:** `src/providers/trips-websocket-provider.tsx`

**Added guard to ignore batch-prefixed event IDs:**
```typescript
const handleTripEvent = useCallback((event: TripEventUpdate) => {
  // Ignore synthetic batch events - already processed in hook
  if (event.trip_id?.startsWith('batch-')) {
    console.log('[TripsWebSocketProvider] Ignoring batch summary event')
    return
  }
  // ... rest of handler
}, [...])
```

---

## Backend Requirement

For the "Maximum update depth exceeded" error to be fully resolved, the backend must send `trips_batch` messages instead of individual `trip_event` messages for bulk operations.

**Check:** `ws_manager.py` line 19
```python
SEND_WS_BATCH = True  # Must be True
```

---

## Files Modified

| File | Change |
|------|--------|
| `src/hooks/use-websocket-trips.ts` | Removed synthetic event, added import for `showBatchNotification` |
| `src/app/(main)/dashboard/locations/[code]/[airline]/schedule-dashboard-client.tsx` | Removed direct `setRowsData()` call in upload handler |
| `src/providers/trips-websocket-provider.tsx` | Added guard for batch-prefixed event IDs |

---

## Testing Checklist

- [ ] Upload XLS → Counter shows correct number (not 2x)
- [ ] Delete location with many trips → No "Maximum update depth" error
- [ ] Delete individual trip → Notification appears normally
- [ ] Console shows `[Upload] Received N trips, waiting for WebSocket sync`
- [ ] Console shows `[useWebSocketTrips] Batch processed: { delete: N }` for bulk operations

---

## Console Logs to Verify

### Correct Behavior (with batch)
```
[useWebSocketTrips] Received batch: 688 events
[useWebSocketTrips] Batch processed: { insert: 0, update: 0, delete: 688 }
[Notifications] Batch notification: delete 688
```

### Incorrect Behavior (without batch - backend issue)
```
[useWebSocketTrips] Received update: delete uuid1
[useWebSocketTrips] Received update: delete uuid2
... (688 times)
Error: Maximum update depth exceeded
```

---

## Related Documentation

| Document | Description |
|----------|-------------|
| [WEBSOCKET_BATCH_FIX.md](WEBSOCKET_BATCH_FIX.md) | Original backend documentation for batch feature |
| [UNIFIED_TRIPS_WEBSOCKET_PIPELINE.md](../Docs_From_Frontend/UNIFIED_TRIPS_WEBSOCKET_PIPELINE.md) | WebSocket architecture overview |

---

**Document Created:** 2026-01-05
