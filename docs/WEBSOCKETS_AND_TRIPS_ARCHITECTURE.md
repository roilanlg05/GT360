# GT360 WebSockets & Trips Architecture

## Overview

GT360 implements a real-time architecture using WebSockets for three main domains:

1. **Trips WebSocket** (`/ws/trips`) - Real-time trip updates
2. **Flight Tracking WebSocket** (`/ws/flights/tracking`) - Aircraft position streaming
3. **Flight Push WebSocket** (`/ws/flights/push`) - Flight status notifications

All WebSockets share common patterns:
- JWT authentication via query parameter
- Ping/pong with token revalidation
- Redis pub/sub for cross-instance communication
- Room-based broadcasting

---

## 1. Trips WebSocket

### Endpoint
```
ws://host/ws/trips?location_id={uuid}&token={jwt}
```

### Purpose
Streams trip CRUD events to connected clients in real-time. When trips are created, updated, or deleted, all connected clients for that location receive the changes immediately.

### Connection Flow

```
Client                          Backend                         Redis
  |                                |                               |
  |--- WS Connect (token) -------->|                               |
  |                                |-- Validate JWT                |
  |                                |-- Check location access       |
  |                                |                               |
  |<-- {"type": "snapshot"} -------|                               |
  |    (all trips for location)    |                               |
  |                                |-- Subscribe to loc:{id}  ---->|
  |                                |                               |
  |<-- {"type": "trips_batch"} ----|<-- Redis pub/sub -------------|
  |                                |                               |
```

### Message Types

#### Server to Client

| Type | Description | Payload |
|------|-------------|---------|
| `snapshot` | Initial dump of all trips | `{type, location_id, location_info, trips[]}` |
| `trips_batch` | Batch of trip events | `{type, location_id, events[]}` |
| `trip_event` | Single trip event (legacy) | `{type, event_type, location_id, trip_id, trip}` |
| `location_delete_started` | Location deletion in progress | `{type, location_id, trips_count}` |
| `location_deleted` | Location fully deleted | `{type, location_id, trips_deleted}` |
| `pong` | Response to ping | `{type: "pong"}` |
| `error` | Error message | `{type, code, detail}` |

#### Client to Server

| Action | Description | Payload |
|--------|-------------|---------|
| `ping` | Keep-alive with token validation | `{action: "ping", token: "..."}` |
| `subscribe` | Confirm subscription | `{action: "subscribe"}` |
| `unsubscribe` | Unsubscribe from location | `{action: "unsubscribe"}` |

### Event Structure in `trips_batch`

```json
{
  "type": "trips_batch",
  "location_id": "uuid",
  "events": [
    {
      "event_type": "insert",
      "trip_id": "uuid",
      "trip": { /* full trip object */ }
    },
    {
      "event_type": "update",
      "trip_id": "uuid",
      "trip": { /* full trip object */ }
    },
    {
      "event_type": "delete",
      "trip_id": "uuid"
    }
  ]
}
```

### Redis Channels

| Channel | Purpose |
|---------|---------|
| `loc:{location_id}` | Trip events for a location |
| `loc:{location_id}:trips` | Trip ID index set |
| `trip:{trip_id}` | Cached trip data (TTL: 300s) |

### Snapshot Flow

1. Check Redis cache (`loc:{id}:trips` set)
2. If cache hit: fetch trips from Redis
3. If cache miss: query PostgreSQL, repopulate cache
4. Send snapshot with `location_info` (timezone, airport code)

---

## 2. Flight Tracking WebSocket

### Endpoint
```
ws://host/ws/flights/tracking?token={jwt}
```

### Purpose
Streams real-time aircraft positions from ADSB.lol API with adaptive polling intervals based on ETA to destination.

### Connection Flow

```
Client                          Backend                         ADSB.lol
  |                                |                               |
  |--- WS Connect (token) -------->|                               |
  |<-- {"type": "connected"} ------|                               |
  |                                |                               |
  |--- track(flight, trip_id) ---->|                               |
  |<-- {"type": "tracking_started"}|                               |
  |                                |--- Poll position ------------>|
  |<-- {"type": "position_update"} |<------------------------------|
  |                                |                               |
  |    (repeat at interval)        |                               |
  |                                |                               |
  |--- stop(flight, trip_id) ----->|                               |
  |<-- {"type": "tracking_stopped"}|                               |
```

### Adaptive Polling Intervals

| ETA to Destination | Interval |
|--------------------|----------|
| > 60 minutes | 20 minutes |
| 30-60 minutes | 5 minutes |
| 20-30 minutes | 2.5 minutes |
| 10-20 minutes | 1 minute |
| < 10 minutes | 1 second (real-time) |

### Message Types

#### Server to Client

| Type | Description |
|------|-------------|
| `connected` | Connection established |
| `tracking_started` | Tracking initiated for flight |
| `tracking_stopped` | Tracking stopped for flight |
| `position_update` | Aircraft position data |
| `pong` | Response to ping |
| `error` | Error message |

#### Client to Server

| Action | Description | Required Fields |
|--------|-------------|-----------------|
| `ping` | Keep-alive | `token` |
| `track` | Start tracking | `flight_number`, `trip_id`, `origin_icao?`, `destination_icao?` |
| `stop` | Stop tracking | `flight_number`, `trip_id` |

### Position Update Structure

```json
{
  "type": "position_update",
  "position": {
    "flight_number": "WN1234",
    "trip_id": "uuid",
    "latitude": 38.123456,
    "longitude": -85.654321,
    "altitude_ft": 35000,
    "ground_speed_knots": 450,
    "heading": 270,
    "vertical_rate_fpm": 0,
    "on_ground": false,
    "timestamp": "2026-01-20T10:30:00Z",
    "eta_minutes": 45,
    "interval_seconds": 300
  }
}
```

### Caching (Singleflight Pattern)

- Position cache: 2-second TTL
- Lock mechanism prevents duplicate API calls
- Multiple clients requesting same flight share one API call

---

## 3. Flight Push WebSocket

### Endpoint
```
ws://host/ws/flights/push?trip_id={uuid}&token={jwt}
```

### Purpose
Receives flight status change notifications from AeroDataBox webhooks and broadcasts to subscribed clients.

### Connection Flow

```
AeroDataBox              Backend                    Client
     |                      |                          |
     |--- Webhook POST ---->|                          |
     |                      |-- Publish to Redis ----->|
     |                      |                          |
     |                      |<-- Subscribed clients ---|
     |                      |--- push_notification --->|
```

### Message Types

#### Server to Client

| Type | Description |
|------|-------------|
| `connected` | Connection established with trip_id |
| `subscribed` | Subscribed to additional trip |
| `unsubscribed` | Unsubscribed from trip |
| `push_notification` | Flight status change |
| `pong` | Response to ping |
| `error` | Error message |

#### Client to Server

| Action | Description | Required Fields |
|--------|-------------|-----------------|
| `ping` | Keep-alive | `token` |
| `subscribe` | Subscribe to trip | `trip_id` |
| `unsubscribe` | Unsubscribe from trip | `trip_id` |

### Push Notification Structure

```json
{
  "type": "push_notification",
  "trip_id": "uuid",
  "notification": {
    "flight_number": "WN1234",
    "status": "departed",
    "departure_time": "2026-01-20T10:00:00Z",
    "arrival_time_estimated": "2026-01-20T12:30:00Z",
    "gate": "B12"
  }
}
```

### Status Values

| Status | Tracking Action |
|--------|-----------------|
| `departed`, `airborne` | Activate tracking |
| `landed`, `arrived`, `cancelled` | Stop tracking |

---

## 4. Trips System

### Trip Schema

```python
class Trip:
    id: UUID
    location_id: UUID
    pick_up_date: date
    pick_up_time: time
    pick_up_location: str
    drop_off_location: str
    airline: str
    flight_number: str
    trip_type: str  # inbound | outbound | ground
    status: str     # scheduled | en_route | canceled
    assigned_driver: UUID?
    riders: JSON

    # Filter tracking
    original_pick_up_time: time?
    filter_applied: str?           # deprecated
    reduce_applied: bool
    combine_applied: bool
    expand_applied: bool
    filter_batch_id: UUID?
    filtered_at: datetime?

    # Timestamps
    started_at: datetime?
    picked_up_at: datetime?
    dropped_off_at: datetime?
    created_at: datetime
    updated_at: datetime
```

### Trip Types

| Type | Description | Direction |
|------|-------------|-----------|
| `inbound` | Airport to Hotel | Airport -> Hotel |
| `outbound` | Hotel to Airport | Hotel -> Airport |
| `ground` | Hotel to Hotel | Hotel -> Hotel |

### Trip Filters (Ground Filters)

Only apply to trips with:
- `trip_type = outbound`
- `status = scheduled`

#### Filter Types

| Filter | Priority | Description |
|--------|----------|-------------|
| `reduce` | 0 | Subtract fixed minutes from pickup time |
| `combine` | 1 | Move pairs of trips to midpoint |
| `expand` | 1 | Separate pairs while respecting collision rules |

#### Rules

- **Rule A**: A trip modified by Combine/Expand cannot be modified again
- **Rule B** (No-Collision): Expand must not create gaps that fall into Combine range
- **Rounding**: Results rounded to nearest 5 minutes (or odd minutes mode)

### Filter Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/filters/preview` | POST | Simulate without applying |
| `/filters/preview/last` | GET | Get last saved preview |
| `/filters/apply` | POST | Apply and persist |
| `/filters/revert` | POST | Revert to original times |
| `/filters/revert-partial` | POST | Revert specific filter only |
| `/filters/current` | GET | Get active filter state |
| `/filters/history` | GET | Get filter application history |
| `/filters/eligibility` | GET | Diagnose why trips aren't eligible |

---

## 5. Infrastructure Questions Answered

### 9. Delivery Guarantee (FIFO by trip_id)

**Short Answer**: Partial guarantee. Order is preserved within a connection but NOT globally.

**Detailed Analysis**:

1. **TCP Guarantees**: WebSocket runs over TCP, which guarantees ordered delivery within a single connection. Messages sent in order A, B, C will arrive in order A, B, C.

2. **Redis Pub/Sub**: Does NOT guarantee ordering across different publishers. If two processes publish:
   - Process 1: `INSERT trip_123`
   - Process 2: `UPDATE trip_123`

   The client might receive UPDATE before INSERT if:
   - Network latency differs between processes
   - Redis processes messages from different connections

3. **Batch Ordering**: Within a `trips_batch` message, events ARE ordered (array order is preserved).

4. **Practical Impact**:
   ```
   Scenario: trip_123 created and immediately updated

   Possible outcomes:
   - Normal:  [INSERT, UPDATE] -> Client sees both correctly
   - Race:    [UPDATE, INSERT] -> Client might show stale data
   ```

5. **Mitigation Strategies** (if needed):
   - Include `updated_at` timestamp in trip objects
   - Client-side: only apply update if `updated_at > current`
   - Server-side: sequence numbers per trip_id

**Current Implementation**: No explicit FIFO guarantee per trip_id. The system relies on:
- Database triggers publishing in transaction order
- Redis processing messages sequentially per channel
- Low probability of reordering in practice

### 10. Heartbeat/Ping Mechanism

**Does the backend respond with pong?**

**YES**. All three WebSocket endpoints implement ping/pong:

```python
# From tracking_websocket.py, push_websocket.py, trip_websockets.py
if action == "ping":
    ping_token = msg.get("token")
    if not ping_token:
        await ws.send_json({"type": "error", "code": 401, "detail": "Token required"})
        await ws.close(code=1008)
        return

    try:
        decode_token(ping_token)
        await ws.send_json({"type": "pong"})  # <-- YES, responds with pong
    except Exception:
        await ws.send_json({"type": "error", "code": 401, "detail": "Invalid or expired token"})
        await ws.close(code=1008)
        return
```

**Does the backend close inactive connections?**

**NO**, there is no server-side inactivity timeout. However:

1. **Token Expiration**: The ping mechanism validates the token. If the token expires between pings, the next ping will fail and close the connection.

2. **Connection Closure Events**: The backend handles:
   - `WebSocketDisconnect` - Client closed connection
   - `ConnectionClosedError` - Network failure
   - `ConnectionClosedOK` - Clean close

3. **Cleanup on Disconnect**: When any disconnection occurs:
   ```python
   finally:
       # Cancel tracking tasks (for tracking WS)
       if ws in _tracking_tasks:
           for task in _tracking_tasks[ws].values():
               task.cancel()
           del _tracking_tasks[ws]

       # Remove from rooms
       await manager.disconnect(ws)
   ```

**Recommended Client Implementation**:

```javascript
// Frontend ping interval (60s as mentioned)
const PING_INTERVAL = 60000;

let pingInterval;

ws.onopen = () => {
    pingInterval = setInterval(() => {
        ws.send(JSON.stringify({
            action: "ping",
            token: getCurrentToken()  // Fresh token on each ping
        }));
    }, PING_INTERVAL);
};

ws.onclose = () => {
    clearInterval(pingInterval);
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "pong") {
        // Connection alive, token still valid
    } else if (data.type === "error" && data.code === 401) {
        // Token expired, need to refresh and reconnect
        refreshTokenAndReconnect();
    }
};
```

---

## 6. Architecture Diagram

```
                                    ┌─────────────────┐
                                    │   AeroDataBox   │
                                    │   (Webhooks)    │
                                    └────────┬────────┘
                                             │
                                             ▼
┌─────────────┐    ┌─────────────────────────────────────────────────────┐
│   Client    │    │                    Backend                          │
│  (Browser)  │    │                                                     │
│             │    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│ ┌─────────┐ │    │  │   /ws/trips │  │ /ws/flights │  │ /ws/flights │  │
│ │ WS Trips│◄├────┼──┤             │  │  /tracking  │  │   /push     │  │
│ └─────────┘ │    │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  │
│             │    │         │                │                │         │
│ ┌─────────┐ │    │         │         ┌──────┴──────┐         │         │
│ │WS Track │◄├────┼─────────┼─────────┤  Tracking   │         │         │
│ └─────────┘ │    │         │         │   Cache     │         │         │
│             │    │         │         └──────┬──────┘         │         │
│ ┌─────────┐ │    │         │                │                │         │
│ │ WS Push │◄├────┼─────────┼────────────────┼────────────────┘         │
│ └─────────┘ │    │         │                │                          │
└─────────────┘    │         ▼                ▼                          │
                   │  ┌─────────────────────────────┐                    │
                   │  │           Redis             │                    │
                   │  │  - Pub/Sub (loc:*, flight:*)│                    │
                   │  │  - Cache (trip:*, flight:*) │                    │
                   │  └─────────────────────────────┘                    │
                   │                │                                    │
                   │                ▼                                    │
                   │  ┌─────────────────────────────┐                    │
                   │  │        PostgreSQL           │                    │
                   │  │  - trips.trips              │                    │
                   │  │  - trips.filter_batches     │                    │
                   │  │  - trips.filter_previews    │                    │
                   │  └─────────────────────────────┘                    │
                   │                │                                    │
                   └────────────────┼────────────────────────────────────┘
                                    │
                                    ▼
                           ┌─────────────────┐
                           │   ADSB.lol API  │
                           │  (Positions)    │
                           └─────────────────┘
```

---

## 7. Quick Reference

### WebSocket URLs

| WebSocket | URL | Auth |
|-----------|-----|------|
| Trips | `/ws/trips?location_id={uuid}&token={jwt}` | Query param |
| Flight Tracking | `/ws/flights/tracking?token={jwt}` | Query param |
| Flight Push | `/ws/flights/push?trip_id={uuid}&token={jwt}` | Query param |

### Redis Key Patterns

| Pattern | Description | TTL |
|---------|-------------|-----|
| `loc:{id}` | Pub/sub channel for location | - |
| `loc:{id}:trips` | Trip ID set for location | 300s |
| `trip:{id}` | Cached trip JSON | 300s |
| `flight:pos:{flight}:{trip}` | Cached position | 2s |
| `flight:track:{trip}` | Pub/sub for positions | - |
| `flight:push:{trip}` | Pub/sub for notifications | - |
| `flight:active` | Set of active flight tracks | - |

### Error Codes

| Code | Meaning | Action |
|------|---------|--------|
| 1008 | Policy Violation (Auth) | Reconnect with valid token |
| 1011 | Unexpected Condition | Retry connection |
| 1000 | Normal Closure | No action needed |

---

## 8. Security Considerations

1. **Token Validation**: Every ping revalidates the JWT
2. **Location Access**: Verified against organization membership
3. **Rate Limiting**: Applied at middleware level
4. **CORS**: Restricted to allowed origins
5. **No Token in Logs**: Tokens passed as query params, not logged

---

## 9. Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| Trip Cache TTL | 300s | Self-healing from PostgreSQL |
| Position Cache TTL | 2s | Singleflight prevents duplicate API calls |
| Batch Mode | Enabled | Single message per batch, not N individual |
| Adaptive Polling | 1s - 20min | Based on ETA to destination |
| Max Connections | Unlimited | Limited by server resources |
