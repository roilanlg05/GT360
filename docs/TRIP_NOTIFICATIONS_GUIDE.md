# GT360 Trip Notifications — Complete Backend Reference

Detailed documentation of how trip data flows through the backend, what triggers WebSocket events, what doesn't, and how the Redis cache + snapshot system works. **Manager perspective only.**

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Event Sources & Notification Matrix](#2-event-sources--notification-matrix)
3. [ws/trips Connection Lifecycle](#3-wstrips-connection-lifecycle)
4. [Snapshot Mechanism (Redis Cache + DB Fallback)](#4-snapshot-mechanism-redis-cache--db-fallback)
5. [External Webhook — trips_batch Events](#5-external-webhook--trips_batch-events)
6. [XLS Upload — batch_insert Events](#6-xls-upload--batch_insert-events)
7. [Individual Trip CRUD (No WS Events)](#7-individual-trip-crud-no-ws-events)
8. [Trip Delete Operations (No WS Events)](#8-trip-delete-operations-no-ws-events)
9. [Trip Relief — trip_relieved Events](#9-trip-relief--trip_relieved-events)
10. [Filter Events — step_applied / step_reverted](#10-filter-events--step_applied--step_reverted)
11. [Location Deletion — Dual-Event Pattern](#11-location-deletion--dual-event-pattern)
12. [Redis Caching Layer](#12-redis-caching-layer)
13. [WSManager Internals — Event Routing](#13-wsmanager-internals--event-routing)
14. [Database Trigger — Trip Archival](#14-database-trigger--trip-archival)
15. [Complete Event Flow Diagrams](#15-complete-event-flow-diagrams)
16. [Critical Gaps — What Does NOT Trigger WS](#16-critical-gaps--what-does-not-trigger-ws)
17. [Frontend Implications & Recommendations](#17-frontend-implications--recommendations)

---

## 1. Architecture Overview

```
                    ┌─────────────────────────────────────────────────┐
                    │                   PRODUCERS                      │
                    │                                                   │
                    │  External Webhook ──┐                            │
                    │  XLS Upload ────────┤── Redis Pub/Sub ──────┐   │
                    │  Trip Relief ───────┤   (loc:{id})          │   │
                    │  Filter Service ────┤   (org:{id})          │   │
                    │  Location Delete ───┘                       │   │
                    │                                              │   │
                    │              ┌───────────────────────────────┘   │
                    │              │                                    │
                    │              ▼                                    │
                    │    ┌──────────────────┐   ┌──────────────────┐  │
                    │    │  WSManager        │   │  OrgWSManager     │  │
                    │    │  (loc:{id})       │   │  (org:{id})       │  │
                    │    │  _location_       │   │  _org_listener()  │  │
                    │    │   listener()      │   │                   │  │
                    │    └────────┬─────────┘   └────────┬──────────┘  │
                    │             │                       │             │
                    │             ▼                       ▼             │
                    │       ws/trips clients        ws/org clients     │
                    └─────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────┐
    │                    NO WS EVENTS                                  │
    │                                                                   │
    │  Create Trip (POST)     ── DB only, no Redis, no WS             │
    │  Update Trip (PATCH)    ── DB only, no Redis, no WS             │
    │  Delete Trips (DELETE)  ── DB only, no Redis, no WS             │
    │  Assign Driver (PATCH)  ── DB only, no Redis, no WS             │
    │  Trip Status Changes    ── DB only, no Redis, no WS             │
    │  (start, pick-up, drop-off, log-arrival)                        │
    └─────────────────────────────────────────────────────────────────┘
```

---

## 2. Event Sources & Notification Matrix

| Event Source | REST Endpoint | Redis Channel(s) | WS Event Type | Cache Updated | Notes |
|---|---|---|---|---|---|
| External Webhook | `POST /v1/webhooks/trips/batch` | `loc:{id}` | `trips_batch` | **Yes** (pipeline) | Primary real-time event source |
| XLS Upload | `POST /v1/trips/upload-trips` | `loc:{id}` + `org:{id}` | `batch_insert` | **No** | No trip data in event |
| Trip Relief | `POST /v1/trips/{id}/relief` | `loc:{id}` + `org:{id}` | `trips_batch` (event_type: `trip_relieved`) | **No** | Only WS-enabled single-trip mutation |
| Filter Apply | `POST /v2/.../step/apply` | `loc:{id}` | `step_applied` | **No** | No trip data in event |
| Filter Revert | `POST /v2/.../revert-last` | `loc:{id}` | `step_reverted` | **No** | No trip data in event |
| Location Delete | `DELETE /v1/locations/{id}` | `loc:{id}` + `org:{id}` | `location_delete_started` + `location_deleted` | **No** | Dual-event pattern |
| Create Trip | `POST /v1/locations/{id}/trips` | **None** | **None** | **No** | Silent — no WS notification |
| Update Trip | `PATCH /v1/locations/{id}/trips/{id}` | **None** | **None** | **No** | Silent — no WS notification |
| Delete Trips | `DELETE /v1/locations/{id}/trips` | **None** | **None** | **No** | Silent — no WS notification |
| Delete All Trips | `DELETE /v1/locations/{id}/trips/all` | **None** | **None** | **No** | Silent — no WS notification |
| Delete by Airline | `DELETE /v1/locations/{id}/airlines/{airline}/trips/all` | **None** | **None** | **No** | Silent — no WS notification |
| Assign Driver | `PATCH .../trips/{id}/assign` | **None** | **None** | **No** | Silent — no WS notification |
| Trip Status Changes | `POST /v1/trips/{id}/start\|pick-up\|drop-off\|log-arrival` | **None** | **None** | **No** | Silent — no WS notification |

---

## 3. ws/trips Connection Lifecycle

**File:** `features/trips/websockets/trip_websockets.py`

```
Client connects: wss://api.gt360.app/ws/trips?location_id={uuid}&token={jwt}
        │
        ├─ 1. decode_token(token) → validate JWT
        ├─ 2. user_can_access_location(org_id, location_id) → auth check
        ├─ 3. manager.connect(ws, location_id, claims) → join room
        ├─ 4. manager.ensure_location_listener(location_id) → start Redis listener
        └─ 5. send_snapshot(ws, location_id) → initial data load
              │
              ▼
        Client enters message loop:
              │
              ├─ {"action": "ping", "token": "..."} → validate token, reply {"type": "pong"}
              ├─ {"action": "subscribe"} → reply {"type": "subscribed", ...}
              ├─ {"action": "unsubscribe"} → reply {"type": "unsubscribed", ...}
              └─ other → reply {"type": "error", "detail": "Unknown action"}
```

**Key points:**
- Snapshot is sent **automatically** on connect (step 5) — no subscribe needed
- The `subscribe` action only sends a confirmation message, NOT a snapshot
- Token is re-validated on every `ping` (every 30s) — if expired, server closes with 1008
- On disconnect, the WebSocket is removed from the room. If no more connections exist for this location, the Redis listener task is cancelled

---

## 4. Snapshot Mechanism (Redis Cache + DB Fallback)

**File:** `features/trips/websockets/trip_websockets.py` — `send_snapshot()`

### Strategy (Self-Healing Cache)

```
send_snapshot(ws, location_id)
    │
    ├─ 1. Get location_info (timezone, airport code) from DB
    │
    ├─ 2. Check Redis: SMEMBERS loc:{location_id}:trips
    │     ├─ Has trip IDs? → MGET trip:{id1} trip:{id2} ... (fast path)
    │     │   └─ All found? → Send snapshot ✓
    │     │   └─ Some missing? → Send what we have ✓
    │     │
    │     └─ Empty set? → DB fallback (step 3)
    │
    ├─ 3. Query PostgreSQL: SELECT * FROM trips WHERE location_id = ? ORDER BY pick_up_date, pick_up_time
    │
    ├─ 4. Repopulate Redis cache (self-healing):
    │     ├─ SET trip:{id} → JSON (TTL: 300s) for each trip
    │     └─ SADD loc:{location_id}:trips → trip IDs (TTL: 300s)
    │
    └─ 5. Send snapshot to client
```

### Snapshot Payload

```json
{
  "type": "snapshot",
  "location_id": "uuid",
  "location_info": {
    "id": "uuid",
    "name": "SDF",
    "timezone": "America/New_York"
  },
  "trips": [
    {
      "id": "trip-uuid",
      "location_id": "loc-uuid",
      "pick_up_date": "2026-02-23",
      "pick_up_time": "2026-02-23T14:30:00-05:00",
      "original_pick_up_time": "14:45:00",
      "pick_up_location": "Hilton Garden Inn",
      "drop_off_location": "SDF",
      "airline": "WN",
      "flight_number": "WN1036",
      "riders": 2,
      "trip_type": "outbound",
      "trip_hash": "abc123...",
      "status": "scheduled",
      "assigned_driver": null,
      "started_at": null,
      "picked_up_at": null,
      "arrived_pickup_at": null,
      "arrived_dropoff_at": null,
      "dropped_off_at": null,
      "reduce_applied": true,
      "combine_applied": false,
      "expand_applied": false,
      "filter_order": ["reduce"],
      "current_step_id": "step-uuid",
      "created_at": "2026-02-20T10:00:00Z",
      "updated_at": "2026-02-23T14:30:00Z"
    }
  ]
}
```

### Important Cache Behavior

- Cache TTL is **300 seconds** (5 minutes) — after that, entries expire
- The webhook is the **only** producer that writes to cache (via Redis pipeline)
- Individual trip CRUD does **NOT** update cache — data goes stale until TTL expires
- On next WS connect after cache expiry, the system falls back to DB and self-heals
- `location_info.timezone` is critical for the frontend to display times correctly

---

## 5. External Webhook — trips_batch Events

**File:** `features/trips/webhooks/trip_webhooks.py`

**Endpoint:** `POST /v1/webhooks/trips/batch`

This is the **primary** real-time event source for trip updates. An external system sends batch events that are processed and forwarded to WebSocket clients.

### Flow

```
External System sends POST /v1/webhooks/trips/batch
    │
    ├─ 1. Verify HMAC signature (x-webhook-secret header)
    │
    ├─ 2. For each event:
    │     ├─ Deduplicate by event_id (Redis SETNX, TTL: 60s)
    │     ├─ Validate location_id + trip_id
    │     └─ Add to Redis pipeline:
    │         ├─ insert/update: SET trip:{id} + SADD loc:{loc}:trips
    │         └─ delete: DEL trip:{id} + SREM loc:{loc}:trips
    │
    ├─ 3. Execute pipeline (one round-trip to Redis)
    │
    └─ 4. Publish grouped by location:
          For each location_id:
            PUBLISH loc:{location_id} → {"type": "trips_batch", "events": [...]}
```

### Incoming Webhook Payload

```json
{
  "events": [
    {
      "event_id": "unique-dedup-id",
      "location_id": "uuid",
      "trip_id": "uuid",
      "event_type": "insert",
      "trip": { ...full trip object... }
    },
    {
      "event_id": "unique-dedup-id-2",
      "location_id": "uuid",
      "trip_id": "uuid-2",
      "event_type": "delete",
      "trip": { ...trip data before deletion... }
    }
  ]
}
```

### Redis Channel Message (what WSManager receives)

```json
{
  "type": "trips_batch",
  "location_id": "uuid",
  "events": [
    {
      "location_id": "uuid",
      "trip_id": "uuid",
      "event_type": "db_update",
      "trip": { ...full trip object... }
    }
  ]
}
```

### Event Types from Webhook

| `event_type` | Meaning | Cache Action | Frontend Action |
|---|---|---|---|
| `db_update` | Default when caller doesn't specify | SET + SADD | Upsert (could be new or update) |
| `insert` | Explicitly new trip | SET + SADD | Add to list |
| `update` | Explicitly updated | SET + SADD | Update in list |
| `delete` | Trip deleted | DEL + SREM | Remove from list |

### Deduplication

- Each event can have an `event_id` field
- Server uses `Redis SETNX` with key `processed_events:{event_id}` (TTL: 60s)
- If key already exists → event is a duplicate and is skipped
- If `event_id` is missing → no dedup, event is always processed

### Cache Updates (Pipeline)

For **insert/update** events:
```
SET trip:{trip_id} → JSON(trip) [TTL: 300s]
SADD loc:{location_id}:trips → trip_id
EXPIRE loc:{location_id}:trips → 300s
```

For **delete** events:
```
DEL trip:{trip_id}
SREM loc:{location_id}:trips → trip_id
EXPIRE loc:{location_id}:trips → 300s
```

### What the Frontend Receives (via ws/trips)

Because `SEND_WS_BATCH = True` in WSManager, the frontend receives **one message per location batch**:

```json
{
  "type": "trips_batch",
  "location_id": "uuid",
  "events": [
    {
      "trip_id": "uuid",
      "event_type": "db_update",
      "location_id": "uuid",
      "trip": { ...full trip object... }
    },
    {
      "trip_id": "uuid-2",
      "event_type": "delete",
      "location_id": "uuid",
      "trip": { ...trip data before deletion... }
    }
  ]
}
```

---

## 6. XLS Upload — batch_insert Events

**File:** `features/trips/routes/trips_router.py` — `upload_trips()`

**Endpoint:** `POST /v1/trips/upload-trips`

### Flow

```
Manager uploads Excel/PDF file
    │
    ├─ 1. Parse file → extract trips
    ├─ 2. Deduplicate by trip_hash (skip existing)
    ├─ 3. BulkInsert trips into DB
    ├─ 4. Create Hotel records for new hotels
    ├─ 5. COMMIT
    │
    ├─ 6. Auto-apply filter preset (if exists for this airline)
    │     ├─ New dates → create stack from preset
    │     └─ Existing dates → apply existing stack to new trips
    │
    └─ 7. Publish batch_insert event:
          ├─ PUBLISH loc:{location_id} → batch_event
          └─ PUBLISH org:{org_id} → batch_event
```

### WS Event Payload

```json
{
  "type": "batch_insert",
  "location_id": "uuid",
  "location_name": "SDF",
  "airline": "WN",
  "trips_count": 150,
  "months_affected": [
    {"year": 2026, "month": 0, "count": 80},
    {"year": 2026, "month": 1, "count": 70}
  ],
  "message": "150 trips uploaded successfully"
}
```

### Critical Details

- **No individual trip data** is included in the WS event
- **No Redis cache update** — trips go straight to DB, cache is not populated
- `month` is **zero-indexed** (JavaScript format: 0=January, 11=December)
- The event publishes to **both** `loc:{location_id}` and `org:{org_id}` channels
- **Auto-apply result** is only in the HTTP response, NOT in the WS event

### HTTP Response (includes auto_apply)

```json
{
  "status": "ok",
  "uploaded_rows": 150,
  "location_id": "uuid",
  "airport_code": "SDF",
  "trips": [ ...first 50 trips... ],
  "hotels": [ ...hotel objects... ],
  "auto_apply": {
    "applied": true,
    "reason": null,
    "trips_affected": 120,
    "days_processed": 5,
    "days_with_existing_stack": 2
  }
}
```

### Frontend Handling

On receiving `batch_insert` via WebSocket:
1. Show toast: `${msg.trips_count} trips uploaded to ${msg.location_name}`
2. **Refetch trips** — either reconnect WS (triggers new snapshot) or call REST API
3. The refetched data will already include filter-applied `pick_up_time` values if auto-apply ran

---

## 7. Individual Trip CRUD (No WS Events)

### Create Trip

**Endpoint:** `POST /v1/locations/{location_id}/trips`

- Creates a single trip in the database
- Automatically assigns timezone from location
- Calculates `trip_type` (inbound/outbound/ground)
- Computes deterministic `trip_hash`
- **NO Redis publish** — no WebSocket notification
- **NO Redis cache update** — other connected clients won't see it via WS

### Update Trip

**Endpoint:** `PATCH /v1/locations/{location_id}/trips/{trip_id}`

- Updates trip fields
- Recalculates `trip_type` if locations changed
- Recalculates `trip_hash` if relevant fields changed
- Respects location timezone for `pick_up_time`
- **NO Redis publish** — no WebSocket notification
- **NO Redis cache update**

---

## 8. Trip Delete Operations (No WS Events)

All delete endpoints are **silent** — no WebSocket events, no Redis cache cleanup.

### Delete Multiple Trips

**Endpoint:** `DELETE /v1/locations/{location_id}/trips?trip_ids=uuid1&trip_ids=uuid2`

- Deletes specific trips by ID list
- Returns 204 No Content

### Delete All Trips for Location

**Endpoint:** `DELETE /v1/locations/{location_id}/trips/all`

- Deletes ALL trips in the location
- Returns 204 No Content

### Delete by Airline (with filters)

**Endpoint:** `DELETE /v1/locations/{location_id}/airlines/{airline}/trips/all?confirm=DELETE_ALL`

- Requires `confirm=DELETE_ALL` safety parameter
- Optional filters: `pick_up_date`, `status`
- Returns count of deleted trips

### Cache Implications

After any delete:
- Redis cache (`trip:{id}`, `loc:{location_id}:trips`) becomes **stale**
- Stale entries expire after TTL (300s)
- Next WS snapshot will self-heal from DB
- **Connected clients are NOT notified** of the deletion

---

## 9. Trip Relief — trip_relieved Events

**File:** `features/trips/routes/trips_router.py` — `relief_trip()`

**Endpoint:** `POST /v1/trips/{trip_id}/relief`

This is the **only single-trip mutation** that triggers a WebSocket notification.

### Who Can Call

- **Driver only** — the driver assigned to the trip can release it
- Trip must be `EN_ROUTE` and not dropped off

### What It Does

1. Resets trip to `SCHEDULED` status
2. Clears: `assigned_driver`, `started_at`, `picked_up_at`, `arrived_pickup_at`, `arrived_dropoff_at`
3. Publishes to both `loc:{location_id}` and `org:{org_id}` channels

### WS Event Payload

```json
{
  "type": "trips_batch",
  "location_id": "uuid",
  "events": [
    {
      "trip_id": "uuid",
      "event_type": "trip_relieved",
      "trip": {
        "id": "uuid",
        "assigned_driver": null,
        "status": "scheduled",
        "started_at": null,
        "picked_up_at": null,
        "arrived_pickup_at": null,
        "arrived_dropoff_at": null
      }
    }
  ]
}
```

### Frontend Handling

```typescript
// Inside trips_batch handler:
if (ev.event_type === 'trip_relieved') {
  updateTrip(ev.trip_id, {
    assigned_driver: null,
    status: 'scheduled',
    started_at: null,
    picked_up_at: null,
    arrived_pickup_at: null,
    arrived_dropoff_at: null,
  });
}
```

> **Note:** The `trip` object in the relief event contains **only the reset fields**, not the full trip. Merge with existing trip data.

---

## 10. Filter Events — step_applied / step_reverted

**File:** `features/trips/services/step_filter_service.py`

These events are published to `loc:{location_id}` only (not org channel).

### step_applied

Emitted when: `POST .../step/apply` or `POST .../bulk/apply`

```json
{
  "type": "step_applied",
  "location_id": "uuid",
  "airline": "WN",
  "step_id": "step-uuid",
  "filter_type": "reduce",
  "trips_affected": 42,
  "total_changes": 42,
  "timestamp": "2026-02-23T14:30:00.000000",
  "message": "Filter applied: reduce (42 new trips)"
}
```

### step_reverted

Emitted when: `POST .../revert-last`, `POST .../step/{id}/revert`, or `POST .../bulk/revert`

```json
{
  "type": "step_reverted",
  "location_id": "uuid",
  "airline": "WN",
  "step_id": "step-uuid",
  "filter_type": "reduce",
  "timestamp": "2026-02-23T14:30:00.000000",
  "message": "Filter step reverted: reduce"
}
```

### Frontend Handling

Neither event includes trip data. The frontend **must refetch trips** (reconnect WS or call REST API) to see updated `pick_up_time` values.

For bulk operations, one event is emitted per day/step processed.

---

## 11. Location Deletion — Dual-Event Pattern

**File:** `features/trips/routes/trips_router.py` — `delete_location()`

**Endpoint:** `DELETE /v1/locations/{location_id}`

### Two-Phase Event Flow

```
DELETE /v1/locations/{id}
    │
    ├─ 1. Count trips & hotels (for event payload)
    │
    ├─ 2. PUBLISH "location_delete_started" → org:{id} + loc:{id}
    │     (frontend should stop processing events for this location)
    │
    ├─ 3. DELETE trips, hotels, location from DB
    ├─ 4. COMMIT
    │
    └─ 5. PUBLISH "location_deleted" → org:{id} + loc:{id}
          (frontend should navigate away)
```

### Event 1: location_delete_started

```json
{
  "type": "location_delete_started",
  "location_id": "uuid",
  "location_name": "SDF",
  "trips_count": 150,
  "hotels_count": 25
}
```

### Event 2: location_deleted

```json
{
  "type": "location_deleted",
  "location_id": "uuid",
  "location_name": "SDF",
  "trips_deleted": 150,
  "hotels_deleted": 25,
  "message": "Location SDF deleted",
  "detail": "150 trips and 25 hotels also deleted"
}
```

### Why Two Events?

Between the cascade delete of trips/hotels and the commit, the DB trigger may fire individual delete events. The `location_delete_started` event tells the frontend to **ignore any subsequent `trips_batch` events** for this location, preventing confusing individual deletion notifications.

---

## 12. Redis Caching Layer

### Cache Keys

| Key Pattern | Type | TTL | Producer | Consumer |
|---|---|---|---|---|
| `trip:{trip_id}` | String (JSON) | 300s | Webhook pipeline | Snapshot (MGET) |
| `loc:{location_id}:trips` | Set (trip IDs) | 300s | Webhook pipeline | Snapshot (SMEMBERS) |
| `processed_events:{event_id}` | String ("1") | 60s | Webhook dedup | Webhook dedup |

### Who Writes Cache

| Source | Writes trip:{id}? | Writes loc:{id}:trips? |
|---|---|---|
| External Webhook | **Yes** (pipeline) | **Yes** (pipeline) |
| XLS Upload | **No** | **No** |
| Create Trip | **No** | **No** |
| Update Trip | **No** | **No** |
| Delete Trips | **No** | **No** |
| Trip Relief | **No** | **No** |
| Snapshot self-heal | **Yes** (from DB) | **Yes** (from DB) |

### Cache Staleness

The Redis cache can become **stale** when:

1. **Individual trip created/updated/deleted** via REST API — cache has old data for up to 300s
2. **TTL expired** — cache is empty, next snapshot self-heals from DB
3. **XLS upload** — new trips in DB but not in cache

The self-healing mechanism in `send_snapshot()` handles this: on next WS connect, if Redis is empty, data is loaded from DB and cache is repopulated.

### Cache Read Path (Snapshot)

```python
# 1. Get trip IDs from index set
trip_ids = await redis.smembers(f"loc:{location_id}:trips")

# 2. If IDs exist, batch-get all trips
if trip_ids:
    keys = [f"trip:{tid}" for tid in trip_ids]
    values = await redis.mget(keys)  # Fast: one round-trip
    trips = [json.loads(v) for v in values if v]

# 3. If no IDs (cache empty), fallback to DB
else:
    trips = await db_query(location_id)
    await populate_redis_cache(location_id, trips)  # Self-heal
```

---

## 13. WSManager Internals — Event Routing

**File:** `features/trips/utils/ws_manager.py`

### Room System

```python
rooms: Dict[str, Set[WebSocket]]  # location_id → set of WebSocket connections
ws_meta: Dict[WebSocket, dict]     # WebSocket → metadata (location_id, user_id, role, org_id)
```

### Redis Listener (`_location_listener`)

One listener task per location. Subscribes to `loc:{location_id}` channel and routes messages:

```python
async def _location_listener(self, location_id):
    channel = f"loc:{location_id}"
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)

    async for msg in pubsub.listen():
        ev = decode(msg)
        event_type = ev.get("type")

        # Direct forwarding (no transformation)
        if event_type in ("location_delete_started", "location_deleted"):
            await self.route_location_event(location_id, ev)
            continue

        if event_type in ("step_applied", "step_reverted"):
            await self.route_location_event(location_id, ev)
            continue

        # Batch events (SEND_WS_BATCH=True: forward as-is)
        if event_type == "trips_batch":
            await self.route_location_event(location_id, ev)
            continue
```

### Batch Mode (SEND_WS_BATCH)

```python
SEND_WS_BATCH = True  # Currently enabled
```

When `True`: the entire `trips_batch` message is forwarded as **one WebSocket message** with the events array.

When `False` (currently unused): each event in the batch would be sent as individual `trip_event` messages.

### Listener Lifecycle

- Created when first client connects to a location: `ensure_location_listener(location_id)`
- Cancelled when last client disconnects from a location
- One task per location (reused across multiple clients viewing the same location)

---

## 14. Database Trigger — Trip Archival

**File:** `shared/db/triggers/trips_archive.py`

### Trigger: `trips_archive_on_dropoff`

**Event:** `AFTER UPDATE OF dropped_off_at, status ON trips.trips`

**Fires when:**
- `dropped_off_at` transitions from `NULL` to `NOT NULL` (trip completed)
- `status` changes to `'canceled'`

**Action:**
1. `INSERT` into `trips.trips_history` (archive table — copies ALL columns)
2. `DELETE` from `trips.trips` (active table — trip disappears from active queries)

### Columns Archived

All trip columns including: `trip_type`, `original_pick_up_time`, `reduce_applied`, `combine_applied`, `expand_applied`, `filtered_at`, `current_step_id`, `status`

### No WebSocket Notification

This trigger is purely DB-scoped. **No Redis publish, no WS event.** The trip silently disappears from the active table.

### Frontend Impact

- After a trip is dropped off or canceled, it will be **absent** from the next WS snapshot
- Connected clients won't be notified that the trip was archived
- The trip moves to `trips_history` table (queryable via history endpoints)

---

## 15. Complete Event Flow Diagrams

### External Webhook → Frontend

```
External System
    │
    POST /v1/webhooks/trips/batch (HMAC signed)
    │
    ▼
trip_webhooks.py
    │
    ├─ Dedup (Redis SETNX)
    ├─ Redis Pipeline: SET trip:{id}, SADD loc:{loc}:trips
    └─ PUBLISH loc:{location_id} → {"type":"trips_batch","events":[...]}
                                              │
                                              ▼
                                    WSManager._location_listener()
                                              │
                                              ▼
                                    route_location_event(location_id, payload)
                                              │
                                              ▼
                                    All ws/trips clients for this location
                                    receive: {"type":"trips_batch","events":[...]}
```

### XLS Upload → Frontend

```
Manager uploads file
    │
    POST /v1/trips/upload-trips
    │
    ▼
trips_router.py:upload_trips()
    │
    ├─ Parse file
    ├─ BulkInsert to DB
    ├─ COMMIT
    ├─ Auto-apply preset (if exists)
    ├─ PUBLISH loc:{location_id} → {"type":"batch_insert",...}
    └─ PUBLISH org:{org_id} → {"type":"batch_insert",...}
                                    │               │
                                    ▼               ▼
                              ws/trips clients  ws/org clients
                              receive:          receive:
                              batch_insert      batch_insert
                              → refetch trips   → show toast
```

### Trip Relief → Frontend

```
Driver calls POST /v1/trips/{id}/relief
    │
    ▼
trips_router.py:relief_trip()
    │
    ├─ Reset trip fields in DB
    ├─ COMMIT
    ├─ PUBLISH loc:{location_id} → {"type":"trips_batch","events":[{event_type:"trip_relieved",...}]}
    └─ PUBLISH org:{org_id} → same payload
                                    │                │
                                    ▼                ▼
                              ws/trips clients  ws/org clients
                              receive:          receive:
                              trips_batch       trips_batch
                              → update trip     → update trip
```

---

## 16. Critical Gaps — What Does NOT Trigger WS

These operations modify trips in the database but send **NO WebSocket notification**:

| Operation | Endpoint | What Changes | Why No WS? |
|---|---|---|---|
| **Create trip** | `POST /v1/locations/{id}/trips` | New trip in DB | Not implemented |
| **Update trip** | `PATCH /v1/locations/{id}/trips/{id}` | Modified fields | Not implemented |
| **Delete trips** | `DELETE /v1/locations/{id}/trips` | Trips removed | Not implemented |
| **Delete all trips** | `DELETE /v1/locations/{id}/trips/all` | All trips removed | Not implemented |
| **Delete by airline** | `DELETE .../airlines/{a}/trips/all` | Airline trips removed | Not implemented |
| **Assign driver** | `PATCH .../trips/{id}/assign` | `assigned_driver`, maybe `status`, `started_at` | Not implemented |
| **Start trip** | `POST /v1/trips/{id}/start` | `started_at`, `status=EN_ROUTE` | Not implemented |
| **Pick-up trip** | `POST /v1/trips/{id}/pick-up` | `picked_up_at` | Not implemented |
| **Drop-off trip** | `POST /v1/trips/{id}/drop-off` | `dropped_off_at`, `status=COMPLETED` + **archived** | Not implemented |
| **Log arrival** | `POST /v1/trips/{id}/log-arrival` | `arrived_pickup_at` or `arrived_dropoff_at` | Not implemented |

### Impact on Connected Clients

If **Manager A** creates/edits/deletes a trip via REST API while **Manager B** is viewing the same location via WebSocket:

- Manager B will **NOT** see the change in real-time
- Manager B will see the change only after:
  - Reconnecting the WebSocket (triggers new snapshot from DB)
  - Or waiting for Redis cache TTL (300s) to expire + reconnecting
  - Or receiving another event that triggers a snapshot/refetch

---

## 17. Frontend Implications & Recommendations

### Event Handler (Complete)

```typescript
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  switch (msg.type) {
    // ─── Initial Data ───────────────────────────
    case 'snapshot':
      setTrips(msg.trips);
      setLocationInfo(msg.location_info);
      break;

    // ─── External Webhook Events ────────────────
    case 'trips_batch':
      for (const ev of msg.events) {
        switch (ev.event_type) {
          case 'delete':
            removeTrip(ev.trip_id);
            break;
          case 'trip_relieved':
            // Merge partial data (only reset fields included)
            updateTrip(ev.trip_id, ev.trip);
            break;
          default: // 'db_update', 'insert', 'update'
            upsertTrip(ev.trip_id, ev.trip);
        }
      }
      break;

    // ─── XLS Upload ─────────────────────────────
    case 'batch_insert':
      showToast(`${msg.trips_count} trips uploaded`);
      // No trip data included → MUST refetch
      refetchTrips();
      break;

    // ─── Filter Events ──────────────────────────
    case 'step_applied':
    case 'step_reverted':
      showToast(msg.message);
      // No trip data included → MUST refetch
      refetchTrips();
      break;

    // ─── Location Lifecycle ─────────────────────
    case 'location_delete_started':
      setIgnoreEvents(true); // Stop processing events for this location
      showLoading('Deleting location...');
      break;

    case 'location_deleted':
      navigateTo('/dashboard');
      showToast(msg.message);
      break;

    // ─── Connection ─────────────────────────────
    case 'pong':
      break;

    case 'subscribed':
    case 'unsubscribed':
      break;

    case 'error':
      if (msg.code === 401) handleAuthError();
      break;
  }
};
```

### When to Refetch Trips

| Event | Action | Trip Data Included? |
|---|---|---|
| `snapshot` | Replace all trips | **Yes** — full trip objects |
| `trips_batch` | Apply each event (upsert/delete) | **Yes** — full trip in each event |
| `batch_insert` | **Refetch** (reconnect WS or call REST) | **No** |
| `step_applied` | **Refetch** (trip times changed) | **No** |
| `step_reverted` | **Refetch** (trip times recalculated) | **No** |
| `trip_relieved` | Merge partial data | **Partial** — only reset fields |

### Handling the Cache Gap

Since individual CRUD operations don't trigger WS events, consider these strategies:

1. **Optimistic Updates**: After the manager's own REST call succeeds, immediately update local state with the response data. This keeps _their_ view up to date.

2. **Periodic Refetch**: For multi-manager scenarios, periodically reconnect the WebSocket (e.g., every 5 minutes) to get a fresh snapshot from DB.

3. **Manual Refresh Button**: Give users the ability to force-refresh the trip list.

### Reconnection = Fresh Snapshot

The most reliable way to get fresh data is to **reconnect the WebSocket**. The snapshot always falls back to PostgreSQL if the Redis cache is stale or empty, guaranteeing up-to-date data.
