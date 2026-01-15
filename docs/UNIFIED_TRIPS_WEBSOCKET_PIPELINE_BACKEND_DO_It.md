# Unified Trips WebSocket Pipeline - Backend Implementation

**Version:** 1.0
**Date:** 2026-01-05
**Status:** Pending Implementation

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Architecture](#2-current-architecture)
3. [Analysis Results](#3-analysis-results)
4. [Problem Identified](#4-problem-identified)
5. [Implementation Plan](#5-implementation-plan)
6. [Code Changes](#6-code-changes)
7. [Testing Checklist](#7-testing-checklist)
8. [Rollback Plan](#8-rollback-plan)

---

## 1. Executive Summary

### Context
The frontend implemented a unified trips WebSocket pipeline to display trips data in real-time across multiple views (Table + Cards). This document analyzes the backend consistency and provides the implementation plan for a critical fix.

### Key Finding
The backend is **correctly implemented** for the main use case (individual CRUD operations). However, there's a **critical risk**: the snapshot depends on Redis cache (TTL 5 min), which can return empty data even when trips exist in PostgreSQL.

### Solution
Implement a **fallback to PostgreSQL** when Redis cache is empty, ensuring the frontend always receives accurate data.

### Streaming Service Status
```
✅ RUNNING
Process: python -u services/streaming/trip_streaming.py (PID 757823)
Container: gt360-streaming-1 - Up 27 hours
```

---

## 2. Current Architecture

### Data Flow
```
PostgreSQL (Trip table)
    ↓ (DB NOTIFY on change)
trip_streaming.py (EXTERNAL PROCESS)
    ↓ (HTTP POST /v1/webhooks/trips/batch)
trip_webhooks.py
    ↓ (Redis pipeline + PUBLISH)
Redis (cache + pub/sub)
    ↓ (Subscribe)
ws_manager.py
    ↓ (WebSocket)
Frontend (Table + Cards)
```

### Key Files

| File | Purpose | Path |
|------|---------|------|
| trip_websockets.py | `/ws/trips` endpoint, snapshot, ping/pong | `features/trips/websockets/trip_websockets.py` |
| ws_manager.py | Connection management, event distribution | `features/trips/utils/ws_manager.py` |
| trip_webhooks.py | Webhook batch, Redis update, pub/sub | `features/trips/webhooks/trip_webhooks.py` |
| trip_streaming.py | External service: DB changes → webhook | `services/streaming/trip_streaming.py` |
| trips_router.py | REST CRUD endpoints | `features/trips/routes/trips_router.py` |

### Message Formats

**Snapshot (on connect):**
```json
{
  "type": "snapshot",
  "location_id": "uuid",
  "trips": [/* array of trips */]
}
```

**Trip Event (real-time):**
```json
{
  "type": "trip_event",
  "event_type": "insert|update|delete",
  "location_id": "uuid",
  "trip_id": "uuid",
  "trip": {/* full trip object */}
}
```

---

## 3. Analysis Results

### What Works Correctly

| Aspect | Status | Details |
|--------|--------|---------|
| Message formats | ✅ OK | Consistent with frontend expectations |
| Event types | ✅ OK | `insert`, `update`, `delete` correctly emitted |
| Individual CRUD → WS | ✅ OK | Streaming service captures changes |
| Ping/pong with token | ✅ OK | JWT validation on each ping |
| Streaming service | ✅ OK | Running in Docker container |

### Event Type Mapping

In `trip_streaming.py:27-44`, the `build_event()` function correctly extracts event types from PostgreSQL:

```python
def build_event(payload: dict) -> dict | None:
    event_type = payload.get("event")  # "insert" | "update" | "delete"
    # ...
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "trip_id": trip_id,
        "location_id": location_id,
        "trip": old if event_type == "delete" else new,
    }
```

### CRUD Operations That Trigger Events

| Endpoint | Method | Action | File:Line |
|----------|--------|--------|-----------|
| `/v1/locations/{id}/trips` | POST | Create trip | `trips_router.py:278` |
| `/v1/locations/{id}/trips/{id}` | PATCH | Update trip | `trips_router.py:544` |
| `/v1/locations/{id}/trips/{id}` | DELETE | Delete trip | `trips_router.py:489` |

---

## 4. Problem Identified

### Issue: Redis Cache TTL (5 minutes)

**Location:** `trip_webhooks.py:9`
```python
TRIP_TTL_SECONDS = 300  # 5 minutes
```

**Current Snapshot Logic:** `trip_websockets.py:10-39`
```python
async def send_snapshot(ws: WebSocket, location_id: str) -> None:
    idx_key = f"loc:{location_id}:trips"
    trip_ids = await redis.smembers(idx_key)

    if not trip_ids:
        # PROBLEM: Returns empty even if trips exist in PostgreSQL!
        await ws.send_json({"type": "snapshot", "location_id": location_id, "trips": []})
        return
```

### Impact Scenarios

| Scenario | Current Behavior | Expected Behavior |
|----------|------------------|-------------------|
| First connection after Redis restart | `trips: []` (empty) | `trips: [...]` (from DB) |
| Cache expires (5 min inactivity) | `trips: []` (empty) | `trips: [...]` (from DB) |
| New location, no prior WS activity | `trips: []` (empty) | `trips: [...]` (from DB) |

### Root Cause
The snapshot reads **only from Redis cache**, not from PostgreSQL. If the cache is empty (expired, never populated, or Redis restarted), the frontend receives an empty snapshot even when trips exist in the database.

---

## 5. Implementation Plan

### Objective
When Redis cache is empty, fallback to PostgreSQL to ensure the frontend always receives accurate data.

### File to Modify
`features/trips/websockets/trip_websockets.py`

### Changes Overview

1. **Refactor `send_snapshot()`** - Add fallback logic
2. **Add `_get_trips_from_redis()`** - Extract current Redis logic
3. **Add `_get_trips_from_db()`** - Query PostgreSQL as fallback
4. **Add `_populate_redis_cache()`** - Repopulate cache from DB results

### New Flow
```
Client connects to /ws/trips?location_id=X&token=Y
    ↓
send_snapshot(ws, location_id)
    ↓
Does Redis cache have data?
    ├─ YES → Send snapshot from Redis
    └─ NO → Query PostgreSQL
              ↓
           Does PostgreSQL have data?
              ├─ YES → Repopulate Redis cache + Send snapshot
              └─ NO → Send empty snapshot (legitimate: no trips)
```

---

## 6. Code Changes

### File: `features/trips/websockets/trip_websockets.py`

#### Current Code (lines 1-39)
```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from shared.redis.redis_client import redis_client as redis
from features.trips.utils.ws_manager import manager
import json
from shared.db.db_config import engine, AsyncSession
from features.auth.utils import user_can_access_location, decode_token

router = APIRouter()

async def send_snapshot(ws: WebSocket, location_id: str) -> None:
    idx_key = f"loc:{location_id}:trips"
    trip_ids = await redis.smembers(idx_key)

    if not trip_ids:
        await ws.send_json({"type": "snapshot", "location_id": location_id, "trips": []})
        return

    # smembers puede devolver bytes; normalizamos a str
    norm_ids = []
    for tid in trip_ids:
        if isinstance(tid, (bytes, bytearray)):
            tid = tid.decode("utf-8", errors="ignore")
        norm_ids.append(str(tid))

    keys = [f"trip:{tid}" for tid in norm_ids]
    values = await redis.mget(keys)

    trips = []
    for v in values:
        if not v:
            continue
        if isinstance(v, (bytes, bytearray)):
            v = v.decode("utf-8", errors="ignore")
        try:
            trips.append(json.loads(v))
        except Exception:
            continue

    await ws.send_json({"type": "snapshot", "location_id": location_id, "trips": trips})
```

#### New Code (replace lines 1-39)
```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from shared.redis.redis_client import redis_client as redis
from features.trips.utils.ws_manager import manager
from shared.db.db_config import engine, AsyncSession
from shared.db.schemas import Trip as TripDB
from features.auth.utils import user_can_access_location, decode_token
from psqlmodel import Select
from uuid import UUID
import json

router = APIRouter()

# Consistent with trip_webhooks.py
TRIP_TTL_SECONDS = 300


async def _get_trips_from_redis(trip_ids: set) -> list:
    """Get trips from Redis cache."""
    norm_ids = []
    for tid in trip_ids:
        if isinstance(tid, (bytes, bytearray)):
            tid = tid.decode("utf-8", errors="ignore")
        norm_ids.append(str(tid))

    keys = [f"trip:{tid}" for tid in norm_ids]
    values = await redis.mget(keys)

    trips = []
    for v in values:
        if not v:
            continue
        if isinstance(v, (bytes, bytearray)):
            v = v.decode("utf-8", errors="ignore")
        try:
            trips.append(json.loads(v))
        except Exception:
            continue
    return trips


async def _get_trips_from_db(location_id: str) -> list:
    """Fallback: get trips from PostgreSQL."""
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        return []

    async with AsyncSession(engine) as session:
        stmt = (
            Select(TripDB)
            .Where(TripDB.location_id == location_uuid)
            .OrderBy(TripDB.pick_up_date.Asc(), TripDB.pick_up_time.Asc())
        )
        trips = await session.exec(stmt).all()
        return [t.model_dump(mode="json") for t in trips]


async def _populate_redis_cache(location_id: str, trips: list) -> None:
    """Repopulate Redis cache with trips from DB."""
    if not trips:
        return

    idx_key = f"loc:{location_id}:trips"
    pipe = redis.pipeline()

    for trip in trips:
        trip_id = trip.get("id")
        if trip_id:
            trip_key = f"trip:{trip_id}"
            pipe.set(trip_key, json.dumps(trip), ex=TRIP_TTL_SECONDS)
            pipe.sadd(idx_key, trip_id)

    pipe.expire(idx_key, TRIP_TTL_SECONDS)
    await pipe.execute()


async def send_snapshot(ws: WebSocket, location_id: str) -> None:
    """
    Send snapshot of all trips for a location.

    Strategy:
    1. Try Redis cache first (fast path)
    2. If empty, fallback to PostgreSQL (reliable path)
    3. Repopulate cache if DB has data (self-healing)
    """
    idx_key = f"loc:{location_id}:trips"
    trip_ids = await redis.smembers(idx_key)

    # 1. If Redis has data, use it (fast path)
    if trip_ids:
        trips = await _get_trips_from_redis(trip_ids)
        if trips:
            await ws.send_json({"type": "snapshot", "location_id": location_id, "trips": trips})
            return

    # 2. Fallback to PostgreSQL if Redis is empty
    trips = await _get_trips_from_db(location_id)

    # 3. Repopulate cache if DB has data (self-healing)
    if trips:
        await _populate_redis_cache(location_id, trips)

    # 4. Send snapshot (may be empty if no trips in DB - that's legitimate)
    await ws.send_json({"type": "snapshot", "location_id": location_id, "trips": trips})
```

### Summary of Changes

| Change | Description |
|--------|-------------|
| Added imports | `TripDB`, `Select`, `UUID` for PostgreSQL queries |
| Added `TRIP_TTL_SECONDS` | Constant for Redis TTL (300s = 5 min) |
| Added `_get_trips_from_redis()` | Extracted Redis logic into separate function |
| Added `_get_trips_from_db()` | New function to query PostgreSQL |
| Added `_populate_redis_cache()` | New function to repopulate cache |
| Modified `send_snapshot()` | Implements fallback logic with self-healing cache |

---

## 7. Testing Checklist

### Pre-Implementation
- [ ] Backup current `trip_websockets.py`
- [ ] Verify streaming service is running

### Unit Tests
- [ ] Test `_get_trips_from_redis()` with valid data
- [ ] Test `_get_trips_from_redis()` with empty cache
- [ ] Test `_get_trips_from_db()` with valid location_id
- [ ] Test `_get_trips_from_db()` with invalid UUID
- [ ] Test `_populate_redis_cache()` populates correctly

### Integration Tests

#### Test 1: Normal Flow (Redis has data)
1. Connect to `/ws/trips?location_id=X&token=Y`
2. Verify snapshot contains trips from Redis
3. Expected: Fast response, trips array populated

#### Test 2: Fallback Flow (Redis empty)
1. Clear Redis cache: `redis-cli DEL loc:{location_id}:trips`
2. Connect to `/ws/trips?location_id=X&token=Y`
3. Verify snapshot contains trips from PostgreSQL
4. Verify Redis cache was repopulated

#### Test 3: Legitimate Empty (No trips in DB)
1. Use a location with no trips in PostgreSQL
2. Connect to `/ws/trips?location_id=X&token=Y`
3. Verify snapshot is `{"type": "snapshot", "trips": []}`

#### Test 4: CRUD Events
1. Connect WebSocket to a location
2. Create trip via POST → Verify `trip_event:insert`
3. Update trip via PATCH → Verify `trip_event:update`
4. Delete trip via DELETE → Verify `trip_event:delete`

#### Test 5: Cache Expiration
1. Connect, receive snapshot with trips
2. Wait 5+ minutes
3. Reconnect → Verify snapshot still has trips (fallback works)

### Performance Tests
- [ ] Measure latency for Redis path vs PostgreSQL fallback
- [ ] Verify no significant performance degradation

---

## 8. Rollback Plan

### If Issues Occur

1. **Revert file:**
   ```bash
   git checkout HEAD~1 -- features/trips/websockets/trip_websockets.py
   ```

2. **Restart service:**
   ```bash
   docker-compose restart gt360-api
   ```

3. **Verify:**
   - WebSocket connections working
   - Snapshots being sent
   - Events being distributed

### Monitoring After Deploy

Watch for:
- Increased PostgreSQL query load (expected initially)
- Redis cache hit rate
- WebSocket connection errors
- Snapshot response times

---

## Appendix A: Related Documentation

| Document | Purpose |
|----------|---------|
| [WEBSOCKET_FRONTEND_GUIDE.md](WEBSOCKET_FRONTEND_GUIDE.md) | Frontend integration guide |
| [UNIFIED_TRIPS_WEBSOCKET_PIPELINE.md](UNIFIED_TRIPS_WEBSOCKET_PIPELINE.md) | Frontend architecture |
| [BACKEND_WEBSOCKET_LOCATION_CREATED.md](BACKEND_WEBSOCKET_LOCATION_CREATED.md) | Location events spec |

---

## Appendix B: Configuration Reference

| Setting | Value | Location |
|---------|-------|----------|
| Redis Trip TTL | 300 seconds (5 min) | `trip_webhooks.py:9` |
| JWT Algorithm | HS256 | `shared/settings.py` |
| Access Token Duration | 60 minutes | `shared/settings.py` |
| Ping Validation | Required | `trip_websockets.py:72-86` |
| Streaming Batch Interval | 200ms | `trip_streaming.py:98` |
| Max Batch Size | 100 events | `trip_streaming.py:97` |

---

## Appendix C: Troubleshooting

### Issue: Empty snapshot after implementation

**Check:**
1. Is PostgreSQL accessible from the API container?
2. Are there trips in the database for this location_id?
3. Check logs for errors in `_get_trips_from_db()`

**Debug:**
```python
# Add logging to send_snapshot()
print(f"[SNAPSHOT] location_id={location_id}")
print(f"[SNAPSHOT] Redis trip_ids count={len(trip_ids) if trip_ids else 0}")
print(f"[SNAPSHOT] DB trips count={len(trips)}")
```

### Issue: Slow snapshot response

**Check:**
1. Is fallback being triggered too often?
2. Check Redis connectivity
3. Monitor PostgreSQL query performance

**Optimize:**
- Add index on `trips.location_id` if missing
- Consider increasing Redis TTL

---

**Document End**
