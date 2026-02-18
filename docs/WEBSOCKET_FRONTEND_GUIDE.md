# WebSocket Integration Guide for Frontend Developers

**Version:** 1.1
**Last Updated:** 2026-02-11
**Backend:** GT360 API

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [WebSocket Endpoints](#2-websocket-endpoints)
3. [Authentication System](#3-authentication-system)
4. [Message Formats](#4-message-formats)
5. [Trip Operations & Real-Time Updates](#5-trip-operations--real-time-updates)
6. [Ping/Pong & Token Revalidation](#6-pingpong--token-revalidation)
7. [Token Refresh Flow](#7-token-refresh-flow)
8. [Reconnection Strategy](#8-reconnection-strategy)
9. [Error Codes & Close Codes](#9-error-codes--close-codes)
10. [TypeScript Implementation Examples](#10-typescript-implementation-examples)
11. [Best Practices](#11-best-practices)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Architecture Overview

### 1.1 Data Flow Diagram

```
PostgreSQL (Trips Table)
         |
         | DB NOTIFY (INSERT/UPDATE/DELETE)
         v
+---------------------------+
|   trip_streaming.py       |  External process
|   (psqlmodel.Subscribe)   |  Listens to DB changes
+------------+--------------+
             |
             | HTTP POST (HMAC signed)
             | /v1/webhooks/trips/batch
             v
+---------------------------+
|   FastAPI Webhook         |
|   trip_webhooks.py        |
+------------+--------------+
             |
             | Redis Pipeline
             v
+---------------------------+
|        Redis              |
| - Cache: trip:{id}        |
| - Index: loc:{id}:trips   |
| - Pub/Sub: loc:{id}       |
| - Pub/Sub: org:{id}       |
+------------+--------------+
             |
             | Subscribe (async listener)
             v
+---------------------------+
|   WSManager /             |
|   OrgWSManager            |
|   (WebSocket handlers)    |
+------------+--------------+
             |
             | ws.send_json()
             v
+---------------------------+
|   Frontend WebSocket      |
|   Client                  |
+---------------------------+
```

### 1.2 Components

| Component | Purpose | File |
|-----------|---------|------|
| trip_streaming.py | Detects DB changes, batches events, sends to webhook | services/streaming/trip_streaming.py |
| trip_webhooks.py | Receives webhook, updates Redis cache, publishes to Pub/Sub | features/trips/webhooks/trip_webhooks.py |
| WSManager | Manages WebSocket connections for location trips | features/trips/utils/ws_manager.py |
| OrgWSManager | Manages WebSocket connections for org events | features/trips/utils/org_ws_manager.py |
| trip_websockets.py | /ws/trips endpoint | features/trips/websockets/trip_websockets.py |
| org_websockets.py | /ws/org endpoint | features/trips/websockets/org_websockets.py |

### 1.3 Expected Latency

| Stage | Latency |
|-------|---------|
| DB change -> Webhook | ~50-200ms (batching interval: 200ms) |
| Webhook -> Redis | ~5-10ms |
| Redis Pub/Sub -> WebSocket | ~1-5ms |
| **Total end-to-end** | **~100-300ms** |

---

## 2. WebSocket Endpoints

### 2.1 /ws/trips - Trips by Location

Monitor real-time trip changes for a specific location.

**URL:**
```
wss://api.gt360.app/ws/trips?location_id={UUID}&token={JWT}
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| location_id | UUID | Yes | The location UUID to monitor |
| token | String | Yes | Valid JWT access token |

**Connection Flow:**

```
1. Client connects with location_id and token
2. Server validates JWT token
3. Server extracts organization_id from token metadata
4. Server validates user has access to location (org match)
5. Server accepts connection
6. Server subscribes to Redis channel loc:{location_id}
7. Server sends snapshot of current trips
8. Client receives real-time events
```

**Initial Response (Snapshot):**

Upon successful connection, the server immediately sends a snapshot of all current trips:

```json
{
  "type": "snapshot",
  "location_id": "550e8400-e29b-41d4-a716-446655440000",
  "location_info": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "SDF",
    "timezone": "America/New_York"
  },
  "trips": [
    {
      "id": "trip-uuid-1",
      "assigned_driver": null,
      "location_id": "550e8400-e29b-41d4-a716-446655440000",
      "trip_hash": "abc123def456",
      "pick_up_date": "2026-01-05",
      "pick_up_time": "14:30:00-05:00",
      "pick_up_location": "The Galt House",
      "drop_off_location": "SDF",
      "airline": "Southwest Airlines",
      "flight_number": "WN 1234",
      "trip_type": "outbound",
      "riders": {"pilots": 2, "flight_attendants": 2},
      "status": "scheduled",
      "started_at": null,
      "picked_up_at": null,
      "dropped_off_at": null,
      "arrived_pickup_at": null,
      "arrived_dropoff_at": null,
      "original_pick_up_time": null,
      "reduce_applied": false,
      "combine_applied": false,
      "expand_applied": false,
      "filtered_at": null,
      "current_step_id": null,
      "created_at": "2026-01-05T10:00:00.000Z",
      "updated_at": "2026-01-05T10:00:00.000Z"
    }
  ]
}
```

**Note:** The `pick_up_time` includes timezone offset (e.g., `-05:00` for EST) which represents the local time at the location.

**Supported Client Actions:**

| Action | Payload | Description |
|--------|---------|-------------|
| ping | `{"action": "ping", "token": "..."}` | Heartbeat with token revalidation |
| subscribe | `{"action": "subscribe"}` | Confirm subscription (optional) |
| unsubscribe | `{"action": "unsubscribe"}` | Unsubscribe from events (keeps connection) |

---

### 2.2 /ws/org - Organization Events

Monitor organization-level events (e.g., location deletions).

**URL:**
```
wss://api.gt360.app/ws/org?organization_id={UUID}&token={JWT}
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | UUID | Yes | The organization UUID (must match token) |
| token | String | Yes | Valid JWT access token |

**Connection Flow:**

```
1. Client connects with organization_id and token
2. Server validates JWT token
3. Server extracts organization_id from token metadata
4. Server validates organization_id matches token's org
5. Server accepts connection
6. Server subscribes to Redis channel org:{organization_id}
7. Server sends connection confirmation
8. Client receives org-level events
```

**Initial Response (Connected):**

```json
{
  "type": "connected",
  "organization_id": "6aa6e178-3efa-44d7-8602-2d2b893882e0",
  "message": "Connected to organization events"
}
```

**Supported Client Actions:**

| Action | Payload | Description |
|--------|---------|-------------|
| ping | `{"action": "ping", "token": "..."}` | Heartbeat with token revalidation |

---

## 3. Authentication System

### 3.1 JWT Access Token

**Structure:**

```json
{
  "sub": "user-uuid",
  "iat": 1704326400,
  "exp": 1704330000,
  "metadata": {
    "email": "user@example.com",
    "phone": "+1234567890",
    "role": "manager",
    "organization_id": "org-uuid"
  }
}
```

**Configuration:**

| Property | Value |
|----------|-------|
| Algorithm | HS256 |
| Duration | 60 minutes |
| Issued At | `iat` (Unix timestamp) |
| Expiration | `exp` (Unix timestamp) |

**Metadata Fields:**

| Field | Type | Present When |
|-------|------|--------------|
| email | string | Always |
| phone | string | role = manager |
| role | string | Always ("manager" or "crew") |
| organization_id | UUID | role = manager |
| airline | string | role = crew |

---

### 3.2 Refresh Token

**Characteristics:**

| Property | Value |
|----------|-------|
| Type | Opaque (not JWT) |
| Length | 64 bytes (base64url encoded) |
| Duration | 30 days |
| Storage | Cookie (httpOnly) |
| Rotation | New token on each refresh |

**Important:** Refresh tokens are rotated on every use. The old token becomes invalid immediately after a successful refresh.

---

### 3.3 Cookies

The backend sets the following cookies on login/refresh:

| Cookie | Value | Attributes |
|--------|-------|------------|
| refresh_token | 64-byte opaque token | httpOnly, SameSite=lax, Path=/, Max-Age=2592000 (30 days) |
| expires_at | ISO datetime string | httpOnly, SameSite=lax, Path=/, Max-Age=2592000 (30 days) |

**Note:** `secure=false` currently (should be `true` in production with HTTPS).

---

### 3.4 Authentication Endpoints

#### Sign In

```http
POST /v1/auth/sign-in
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

**Response:**

```json
{
  "data": {
    "session": {
      "access_token": "eyJhbGciOiJIUzI1NiIs...",
      "expires_at": 1704330000,
      "type": "Bearer"
    },
    "user_data": {
      "id": "user-uuid",
      "email": "user@example.com",
      "phone": "+1234567890",
      "role": "manager",
      "organization_id": "org-uuid"
    }
  }
}
```

**Headers Set:**
```
Set-Cookie: refresh_token=Dy...Zy; HttpOnly; SameSite=lax; Path=/; Max-Age=2592000
Set-Cookie: expires_at=2026-02-05T00:00:00+00:00; HttpOnly; SameSite=lax; Path=/; Max-Age=2592000
```

---

#### Refresh Token

```http
POST /v1/auth/refresh
Cookie: refresh_token=<current_refresh_token>
```

**Response:**

```json
{
  "data": {
    "session": {
      "access_token": "eyJhbGciOiJIUzI1NiIs...",
      "exp": 1704330000,
      "type": "bearer"
    },
    "user_data": {
      "id": "user-uuid",
      "email": "user@example.com",
      ...
    }
  }
}
```

**Headers Set:**
```
Set-Cookie: refresh_token=<NEW_TOKEN>; HttpOnly; SameSite=lax; Path=/; Max-Age=2592000
```

**Important:** The refresh token in the cookie is replaced with a NEW token.

---

#### Sign Out

```http
POST /v1/auth/sign-out
Authorization: Bearer <access_token>
```

**Response:**

```json
{
  "message": "All cookies revoked"
}
```

**Actions Performed:**
1. Access token added to blacklist (Redis, 5 min TTL)
2. All refresh tokens for user revoked in database
3. Cookies deleted

---

## 4. Message Formats

### 4.1 Server -> Client Messages

#### Snapshot (on connect to /ws/trips)

```json
{
  "type": "snapshot",
  "location_id": "550e8400-e29b-41d4-a716-446655440000",
  "location_info": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "SDF",
    "timezone": "America/New_York"
  },
  "trips": [
    {
      "id": "trip-uuid",
      "assigned_driver": null,
      "location_id": "location-uuid",
      "trip_hash": "abc123def456",
      "pick_up_date": "2026-01-05",
      "pick_up_time": "14:30:00-05:00",
      "pick_up_location": "Hotel Name",
      "drop_off_location": "Airport Code",
      "airline": "Airline Name",
      "flight_number": "XX 1234",
      "trip_type": "outbound",
      "riders": {"pilots": 2, "flight_attendants": 2},
      "status": "scheduled",
      "started_at": null,
      "picked_up_at": null,
      "dropped_off_at": null,
      "arrived_pickup_at": null,
      "arrived_dropoff_at": null,
      "original_pick_up_time": null,
      "reduce_applied": false,
      "combine_applied": false,
      "expand_applied": false,
      "filtered_at": null,
      "current_step_id": null,
      "created_at": "2026-01-05T10:00:00.000Z",
      "updated_at": "2026-01-05T10:00:00.000Z"
    }
  ]
}
```

---

#### Trips Batch Event (real-time updates, default mode)

The server sends batched events by default (`SEND_WS_BATCH = True`). Each batch contains one or more trip events:

```json
{
  "type": "trips_batch",
  "location_id": "550e8400-e29b-41d4-a716-446655440000",
  "events": [
    {
      "event_type": "insert",
      "trip_id": "trip-uuid-1",
      "trip": {
        "id": "trip-uuid-1",
        "assigned_driver": null,
        "location_id": "location-uuid",
        "trip_hash": "abc123",
        "pick_up_date": "2026-01-05",
        "pick_up_time": "14:30:00-05:00",
        "pick_up_location": "Hotel Name",
        "drop_off_location": "SDF",
        "airline": "Southwest Airlines",
        "flight_number": "WN 1234",
        "trip_type": "outbound",
        "riders": {"pilots": 2, "flight_attendants": 2},
        "status": "scheduled",
        "started_at": null,
        "picked_up_at": null,
        "dropped_off_at": null,
        "arrived_pickup_at": null,
        "arrived_dropoff_at": null,
        "original_pick_up_time": null,
        "reduce_applied": false,
        "combine_applied": false,
        "expand_applied": false,
        "filtered_at": null,
        "current_step_id": null,
        "created_at": "2026-01-05T10:00:00.000Z",
        "updated_at": "2026-01-05T10:00:00.000Z"
      }
    },
    {
      "event_type": "update",
      "trip_id": "trip-uuid-2",
      "trip": { "...": "full trip object with updated fields" }
    },
    {
      "event_type": "delete",
      "trip_id": "trip-uuid-3",
      "trip": {
        "id": "trip-uuid-3",
        "pick_up_location": "Hotel Name",
        "drop_off_location": "SDF",
        "airline": "Southwest Airlines",
        "flight_number": "WN 1234"
      }
    }
  ]
}
```

**Event types inside `events` array:**

| event_type | Description | `trip` contains |
|------------|-------------|-----------------|
| `insert` | Trip created | Full trip object |
| `update` | Trip modified | Full trip object with updated fields |
| `delete` | Trip deleted | Partial trip (for UI notification) |

**Note:** Delete events include trip data so you can show useful notifications like:
```
"Deleted: Hotel Name -> SDF (WN 1234)"
```

---

#### Filter Step Events

When a ground filter step is applied or reverted, the server forwards these events:

**Step Applied:**
```json
{
  "type": "step_applied",
  "location_id": "550e8400-e29b-41d4-a716-446655440000",
  "filter_type": "reduce"
}
```

**Step Reverted:**
```json
{
  "type": "step_reverted",
  "location_id": "550e8400-e29b-41d4-a716-446655440000",
  "filter_type": "reduce"
}
```

---

#### Connected (on connect to /ws/org)

```json
{
  "type": "connected",
  "organization_id": "6aa6e178-3efa-44d7-8602-2d2b893882e0",
  "message": "Connected to organization events"
}
```

---

#### Location Deleted (from /ws/org)

```json
{
  "type": "location_deleted",
  "location_id": "550e8400-e29b-41d4-a716-446655440000",
  "location_name": "Southwest Airlines - SDF",
  "message": "Location 'Southwest Airlines - SDF' deleted successfully",
  "hotels": [
    {"id": "hotel-uuid-1", "name": "The Galt House", "status": "deleted"},
    {"id": "hotel-uuid-2", "name": "Hyatt Regency Louisville", "status": "deleted"}
  ],
  "hotels_count": 2
}
```

---

#### Pong (response to ping)

```json
{
  "type": "pong"
}
```

---

#### Error

```json
{
  "type": "error",
  "code": 401,
  "detail": "Invalid or expired token"
}
```

---

#### Subscribed / Unsubscribed

```json
{
  "type": "subscribed",
  "location_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

```json
{
  "type": "unsubscribed",
  "location_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

### 4.2 Client -> Server Messages

#### Ping (with token validation)

```json
{
  "action": "ping",
  "token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**Important:** The token field is REQUIRED. If missing or invalid, the server will close the connection with code 1008.

---

#### Subscribe

```json
{
  "action": "subscribe"
}
```

---

#### Unsubscribe

```json
{
  "action": "unsubscribe"
}
```

---

## 5. Trip Data Model & Real-Time Updates

### 5.1 How Updates Work

When trip data changes (through driver actions, manager updates, or system operations), the changes are automatically propagated via WebSocket:

**Flow:**
```
1. Trip data modified in database (via REST API or system operation)
2. Database trigger sends NOTIFY
3. Webhook receives notification
4. Redis cache updated
5. WebSocket broadcasts trips_batch event with updated trip
6. All connected clients receive the update
```

### 5.2 Complete Trip Schema

The complete trip object received in WebSocket events includes:

```typescript
interface Trip {
  // Basic info
  id: string;
  location_id: string;
  trip_hash: string;
  pick_up_date: string;      // "YYYY-MM-DD"
  pick_up_time: string;      // "HH:MM:SS±HH:MM" (with timezone offset, e.g., "14:30:00-05:00")
  pick_up_location: string;
  drop_off_location: string;
  airline: string;
  flight_number: string;
  trip_type: string | null;  // "inbound" | "outbound" | "ground"
  riders: Record<string, number> | null;

  // Assignment & Status
  assigned_driver: string | null;
  status: string | null;     // "scheduled" | "en_route" | "completed" | "canceled"

  // Lifecycle timestamps (all ISO 8601 UTC)
  started_at: string | null;           // Trip started (e.g., "2026-02-11T14:25:00.000Z")
  arrived_pickup_at: string | null;    // Driver arrived at pickup location
  picked_up_at: string | null;         // Passengers picked up
  arrived_dropoff_at: string | null;   // Driver arrived at dropoff location
  dropped_off_at: string | null;       // Passengers dropped off

  // Ground filters
  original_pick_up_time: string | null; // "HH:MM:SS±HH:MM" (if trip was modified by filters)
  reduce_applied: boolean;
  combine_applied: boolean;
  expand_applied: boolean;
  filtered_at: string | null;          // ISO 8601 UTC
  current_step_id: string | null;

  // Metadata
  created_at: string;        // ISO 8601 UTC
  updated_at: string;        // ISO 8601 UTC
}
```

**Status Values:**
- `scheduled`: Trip created, not started
- `en_route`: Trip started or picked up, in progress
- `completed`: Trip completed with drop-off
- `canceled`: Trip canceled

---

### 5.3 Timezone Handling

**IMPORTANT:** Trip times are timezone-aware and reflect the location's local timezone.

#### Time Field Formats

| Field | Format | Timezone | Example |
|-------|--------|----------|---------|
| `pick_up_time` | `HH:MM:SS±HH:MM` | Location local | `"14:30:00-05:00"` |
| `original_pick_up_time` | `HH:MM:SS±HH:MM` | Location local | `"14:00:00-05:00"` |
| `started_at` | ISO 8601 | UTC | `"2026-02-11T19:25:00.000Z"` |
| `picked_up_at` | ISO 8601 | UTC | `"2026-02-11T19:35:00.000Z"` |
| `dropped_off_at` | ISO 8601 | UTC | `"2026-02-11T20:10:00.000Z"` |
| `created_at` | ISO 8601 | UTC | `"2026-02-11T10:00:00.000Z"` |

#### Understanding pick_up_time

The `pick_up_time` field includes timezone offset information:

```json
{
  "pick_up_date": "2026-02-15",
  "pick_up_time": "14:30:00-05:00",
  "location_info": {
    "timezone": "America/New_York"
  }
}
```

This means:
- **Local time:** 2:30 PM Eastern Time (EST/EDT depending on date)
- **Offset:** `-05:00` (EST) or `-04:00` (EDT during daylight saving)
- **UTC equivalent:** 7:30 PM UTC (during EST)

#### Displaying Times in UI

```typescript
// Example trip data from WebSocket
const trip = {
  pick_up_date: "2026-02-15",
  pick_up_time: "14:30:00-05:00",
  started_at: "2026-02-15T19:25:00.000Z",
  ...
};

const locationInfo = {
  timezone: "America/New_York"
};

// Option 1: Parse pick_up_time with Luxon
import { DateTime } from 'luxon';

const pickupDateTime = DateTime.fromISO(
  `${trip.pick_up_date}T${trip.pick_up_time}`
);

console.log(pickupDateTime.toLocaleString(DateTime.TIME_SIMPLE));
// Output: "2:30 PM"

console.log(pickupDateTime.zoneName);
// Output: "America/New_York"

// Option 2: Display lifecycle timestamps in location's timezone
const startedAt = DateTime.fromISO(trip.started_at, { zone: 'utc' })
  .setZone(locationInfo.timezone);

console.log(startedAt.toLocaleString(DateTime.DATETIME_SHORT));
// Output: "2/15/2026, 2:25 PM" (converted from UTC to location timezone)

// Option 3: Simple string parsing (if you just need the time)
const timeOnly = trip.pick_up_time.split(/[+-]/)[0]; // "14:30:00"
const [hours, minutes] = timeOnly.split(':');
console.log(`${hours}:${minutes}`); // "14:30"
```

#### Timezone Offset Changes (DST)

The timezone offset in `pick_up_time` changes based on Daylight Saving Time:

```typescript
// Winter trip (EST)
{
  "pick_up_date": "2026-01-15",
  "pick_up_time": "14:30:00-05:00"  // EST (UTC-5)
}

// Summer trip (EDT)
{
  "pick_up_date": "2026-07-15",
  "pick_up_time": "14:30:00-04:00"  // EDT (UTC-4)
}
```

Both represent 2:30 PM local time, but the UTC equivalent differs:
- Winter: `19:30:00 UTC`
- Summer: `18:30:00 UTC`

**Best Practice:** Always use the `location_info.timezone` field from the snapshot to properly interpret times. Don't rely solely on the offset.

---

### 5.4 Lifecycle Timestamp Progression
```
created_at
    ↓
started_at (status → "en_route")
    ↓
arrived_pickup_at
    ↓
picked_up_at (status → "en_route")
    ↓
arrived_dropoff_at
    ↓
dropped_off_at (status → "completed")
```

### 5.5 Common Update Scenarios

When you receive a `trips_batch` event with `event_type: "update"`, here are the most common field changes:

| Scenario | Fields Updated | New Status |
|----------|---------------|------------|
| Driver starts trip | `started_at`, `assigned_driver` | `en_route` |
| Driver arrives at pickup | `arrived_pickup_at` | (unchanged) |
| Driver picks up passengers | `picked_up_at` | `en_route` |
| Driver arrives at destination | `arrived_dropoff_at` | (unchanged) |
| Driver completes drop-off | `dropped_off_at` | `completed` |
| Manager assigns driver | `assigned_driver` | (unchanged) |
| Manager cancels trip | `status` | `canceled` |
| Ground filter applied | `reduce_applied`, `combine_applied`, or `expand_applied`, `filtered_at`, `current_step_id` | (unchanged) |

**Note:** All timestamp fields are in ISO 8601 UTC format.

---

## 6. Ping/Pong & Token Revalidation

### 6.1 Why Ping/Pong is Important

1. **Keep-alive:** Prevents connection timeout
2. **Token validation:** Server validates the token on each ping
3. **Early detection:** Catches expired tokens before they cause issues

### 6.2 Recommended Interval

Send a ping every **30-60 seconds** with the current access token.

### 6.3 Flow

```
Client                                    Server
   |                                         |
   |------ {"action": "ping",  ------------>|
   |        "token": "eyJ..."} ------------>|
   |                                         |
   |                          [Validate JWT] |
   |                                         |
   |<----- {"type": "pong"} ----------------|
   |                                         |
```

### 6.4 Token Expiration During Connection

If the token expires and the client sends a ping with the expired token:

```
Client                                    Server
   |                                         |
   |------ {"action": "ping",  ------------>|
   |        "token": "expired"} ----------->|
   |                                         |
   |                     [Token invalid/exp] |
   |                                         |
   |<----- {"type": "error",  --------------|
   |        "code": 401,      --------------|
   |        "detail": "..."}  --------------|
   |                                         |
   |<----- WebSocket Close (1008) ----------|
   |                                         |
```

### 6.5 Implementation Pattern

```typescript
// Send ping every 30 seconds
const PING_INTERVAL = 30000;

let pingInterval: NodeJS.Timer;

function startPingInterval(ws: WebSocket, getToken: () => string) {
  pingInterval = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        action: "ping",
        token: getToken() // Get CURRENT token (may have been refreshed)
      }));
    }
  }, PING_INTERVAL);
}

function stopPingInterval() {
  if (pingInterval) {
    clearInterval(pingInterval);
  }
}
```

---

## 7. Token Refresh Flow

### 7.1 When to Refresh

Refresh the token **before it expires**. Recommended: 5 minutes before expiration.

```typescript
function shouldRefreshToken(expiresAt: number): boolean {
  const now = Math.floor(Date.now() / 1000);
  const bufferSeconds = 5 * 60; // 5 minutes
  return (expiresAt - now) <= bufferSeconds;
}
```

### 7.2 Refresh Flow with WebSocket

```
1. Check token expiration before sending ping
2. If near expiration:
   a. Call POST /v1/auth/refresh
   b. Update access_token in memory
   c. Cookie is automatically updated by browser
3. Send ping with NEW token
4. Continue normal operation
```

### 7.3 Implementation Example

```typescript
async function refreshTokenIfNeeded(
  currentToken: string,
  expiresAt: number,
  setToken: (token: string, exp: number) => void
): Promise<string> {
  if (!shouldRefreshToken(expiresAt)) {
    return currentToken;
  }

  try {
    const response = await fetch('/v1/auth/refresh', {
      method: 'POST',
      credentials: 'include', // Important: send cookies
    });

    if (!response.ok) {
      throw new Error('Refresh failed');
    }

    const data = await response.json();
    const newToken = data.data.session.access_token;
    const newExp = data.data.session.exp;

    setToken(newToken, newExp);
    return newToken;
  } catch (error) {
    // Refresh failed - user needs to re-login
    throw error;
  }
}
```

---

## 8. Reconnection Strategy

### 8.1 WebSocket Close Codes

| Code | Meaning | Action |
|------|---------|--------|
| 1000 | Normal closure | Reconnect if needed |
| 1001 | Going away | Reconnect |
| 1006 | Abnormal closure | Reconnect with backoff |
| 1008 | Policy violation (auth) | Refresh token, then reconnect |
| 1011 | Server error | Reconnect with backoff |

### 8.2 Reconnection Algorithm

Use exponential backoff with jitter:

```typescript
function calculateBackoff(attempt: number): number {
  const baseDelay = 1000; // 1 second
  const maxDelay = 30000; // 30 seconds
  const exponentialDelay = Math.min(baseDelay * Math.pow(2, attempt), maxDelay);
  const jitter = Math.random() * 1000; // 0-1 second jitter
  return exponentialDelay + jitter;
}
```

### 8.3 Reconnection Flow

```
1. WebSocket closes unexpectedly
2. Check close code:
   - If 1008 (Policy violation): Try refresh token first
   - Otherwise: Proceed to reconnect
3. Wait with exponential backoff
4. Attempt reconnection with current token
5. If successful: Reset attempt counter
6. If failed: Increment attempt, go to step 3
7. After N failures: Give up, prompt re-login
```

### 8.4 Implementation Example

```typescript
class WebSocketManager {
  private ws: WebSocket | null = null;
  private reconnectAttempt = 0;
  private maxReconnectAttempts = 10;
  private reconnectTimeout: NodeJS.Timer | null = null;

  async connect(url: string, token: string) {
    this.ws = new WebSocket(`${url}&token=${token}`);

    this.ws.onopen = () => {
      this.reconnectAttempt = 0; // Reset on successful connection
    };

    this.ws.onclose = async (event) => {
      if (event.code === 1008) {
        // Token issue - try refresh
        try {
          const newToken = await this.refreshToken();
          this.scheduleReconnect(url, newToken);
        } catch {
          // Refresh failed - need re-login
          this.onAuthError();
        }
      } else {
        this.scheduleReconnect(url, token);
      }
    };
  }

  private scheduleReconnect(url: string, token: string) {
    if (this.reconnectAttempt >= this.maxReconnectAttempts) {
      this.onMaxReconnectAttempts();
      return;
    }

    const delay = this.calculateBackoff(this.reconnectAttempt);
    this.reconnectAttempt++;

    this.reconnectTimeout = setTimeout(() => {
      this.connect(url, token);
    }, delay);
  }

  private calculateBackoff(attempt: number): number {
    const baseDelay = 1000;
    const maxDelay = 30000;
    const exponentialDelay = Math.min(baseDelay * Math.pow(2, attempt), maxDelay);
    const jitter = Math.random() * 1000;
    return exponentialDelay + jitter;
  }
}
```

---

## 9. Error Codes & Close Codes

### 9.1 WebSocket Close Codes

| Code | Name | Description | Client Action |
|------|------|-------------|---------------|
| 1000 | Normal | Clean close | Reconnect if needed |
| 1001 | Going Away | Server/client leaving | Reconnect |
| 1006 | Abnormal | No close frame received | Reconnect with backoff |
| 1008 | Policy Violation | Authentication failed | Refresh token, reconnect |
| 1011 | Internal Error | Server error | Reconnect with backoff |

### 9.2 HTTP Error Codes (Auth Endpoints)

| Code | Endpoint | Meaning |
|------|----------|---------|
| 401 | sign-in | Invalid credentials |
| 401 | sign-in | Email not verified |
| 401 | refresh | Invalid/missing refresh token |
| 401 | refresh | Refresh token expired/revoked |
| 401 | * | Missing/invalid access token |
| 403 | change-password | Incorrect current password |
| 409 | register | Email/phone already in use |

### 9.3 WebSocket Error Messages

```json
{
  "type": "error",
  "code": 401,
  "detail": "Token required"
}
```

```json
{
  "type": "error",
  "code": 401,
  "detail": "Invalid or expired token"
}
```

```json
{
  "type": "error",
  "detail": "Unknown action"
}
```

---

## 10. TypeScript Implementation Examples

### 10.1 useWebSocketTrips Hook

```typescript
import { useEffect, useRef, useCallback, useState } from 'react';

interface LocationInfo {
  id: string;
  name: string;       // Airport code (e.g., "SDF")
  timezone: string;   // e.g., "America/New_York"
}

interface Trip {
  id: string;
  assigned_driver: string | null;
  location_id: string;
  trip_hash: string;
  pick_up_date: string;      // "YYYY-MM-DD"
  pick_up_time: string;      // "HH:MM:SS±HH:MM" (e.g., "14:30:00-05:00")
  pick_up_location: string;
  drop_off_location: string;
  airline: string;
  flight_number: string;
  trip_type: string | null;  // "inbound" | "outbound" | "ground"
  riders: Record<string, number> | null;  // e.g., {"pilots": 2, "flight_attendants": 2}
  status: string | null;     // "scheduled" | "canceled" | "en_route" | "completed"
  started_at: string | null;           // ISO 8601 UTC
  picked_up_at: string | null;         // ISO 8601 UTC
  dropped_off_at: string | null;       // ISO 8601 UTC
  arrived_pickup_at: string | null;    // ISO 8601 UTC
  arrived_dropoff_at: string | null;   // ISO 8601 UTC
  original_pick_up_time: string | null; // "HH:MM:SS±HH:MM" (if modified by filters)
  reduce_applied: boolean;
  combine_applied: boolean;
  expand_applied: boolean;
  filtered_at: string | null;          // ISO 8601 UTC
  current_step_id: string | null;
  created_at: string;        // ISO 8601 UTC
  updated_at: string;        // ISO 8601 UTC
}

interface TripBatchEvent {
  event_type: 'insert' | 'update' | 'delete';
  trip_id: string;
  trip: Trip;
}

interface TripsBatchMessage {
  type: 'trips_batch';
  location_id: string;
  events: TripBatchEvent[];
}

interface SnapshotEvent {
  type: 'snapshot';
  location_id: string;
  location_info: LocationInfo | null;
  trips: Trip[];
}

interface StepEvent {
  type: 'step_applied' | 'step_reverted';
  location_id: string;
  filter_type: string;  // "reduce" | "combine" | "expand"
}

interface UseWebSocketTripsOptions {
  locationId: string;
  token: string;
  tokenExpiresAt: number;
  onRefreshToken: () => Promise<{ token: string; expiresAt: number }>;
  enabled?: boolean;
}

export function useWebSocketTrips({
  locationId,
  token,
  tokenExpiresAt,
  onRefreshToken,
  enabled = true,
}: UseWebSocketTripsOptions) {
  const [trips, setTrips] = useState<Map<string, Trip>>(new Map());
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const pingIntervalRef = useRef<NodeJS.Timer | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timer | null>(null);
  const reconnectAttemptRef = useRef(0);
  const currentTokenRef = useRef(token);
  const currentExpiresAtRef = useRef(tokenExpiresAt);

  // Update refs when props change
  useEffect(() => {
    currentTokenRef.current = token;
    currentExpiresAtRef.current = tokenExpiresAt;
  }, [token, tokenExpiresAt]);

  const shouldRefreshToken = useCallback(() => {
    const now = Math.floor(Date.now() / 1000);
    const bufferSeconds = 5 * 60; // 5 minutes
    return (currentExpiresAtRef.current - now) <= bufferSeconds;
  }, []);

  const refreshTokenIfNeeded = useCallback(async () => {
    if (!shouldRefreshToken()) {
      return currentTokenRef.current;
    }

    try {
      const { token: newToken, expiresAt } = await onRefreshToken();
      currentTokenRef.current = newToken;
      currentExpiresAtRef.current = expiresAt;
      return newToken;
    } catch (err) {
      throw err;
    }
  }, [shouldRefreshToken, onRefreshToken]);

  const startPingInterval = useCallback(() => {
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
    }

    pingIntervalRef.current = setInterval(async () => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        try {
          const validToken = await refreshTokenIfNeeded();
          wsRef.current.send(JSON.stringify({
            action: 'ping',
            token: validToken,
          }));
        } catch (err) {
          // Token refresh failed
          wsRef.current?.close(1008, 'Token refresh failed');
        }
      }
    }, 30000); // Every 30 seconds
  }, [refreshTokenIfNeeded]);

  const stopPingInterval = useCallback(() => {
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }
  }, []);

  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'snapshot':
          const snapshot = data as SnapshotEvent;
          const snapshotTrips = new Map<string, Trip>();
          snapshot.trips.forEach(trip => {
            snapshotTrips.set(trip.id, trip);
          });
          setTrips(snapshotTrips);
          // snapshot.location_info has timezone, name (airport code)
          break;

        case 'trips_batch':
          const batch = data as TripsBatchMessage;
          setTrips(prev => {
            const newMap = new Map(prev);
            for (const ev of batch.events) {
              if (ev.event_type === 'delete') {
                newMap.delete(ev.trip_id);
              } else {
                newMap.set(ev.trip_id, ev.trip);
              }
            }
            return newMap;
          });
          break;

        case 'step_applied':
        case 'step_reverted':
          // Filter step changed - you may want to refresh UI
          // data.filter_type = "reduce" | "combine" | "expand"
          break;

        case 'pong':
          // Heartbeat acknowledged
          break;

        case 'error':
          setError(new Error(data.detail));
          break;
      }
    } catch (err) {
      console.error('Failed to parse WebSocket message:', err);
    }
  }, []);

  const connect = useCallback(async () => {
    if (!enabled || !locationId) return;

    try {
      const validToken = await refreshTokenIfNeeded();
      const url = `wss://api.gt360.app/ws/trips?location_id=${locationId}&token=${validToken}`;

      wsRef.current = new WebSocket(url);

      wsRef.current.onopen = () => {
        setIsConnected(true);
        setError(null);
        reconnectAttemptRef.current = 0;
        startPingInterval();
      };

      wsRef.current.onmessage = handleMessage;

      wsRef.current.onclose = (event) => {
        setIsConnected(false);
        stopPingInterval();

        if (event.code === 1008) {
          // Auth error - try refresh then reconnect
          onRefreshToken()
            .then(() => scheduleReconnect())
            .catch(() => setError(new Error('Authentication failed')));
        } else if (event.code !== 1000) {
          // Unexpected close - reconnect
          scheduleReconnect();
        }
      };

      wsRef.current.onerror = () => {
        setError(new Error('WebSocket connection error'));
      };
    } catch (err) {
      setError(err as Error);
    }
  }, [enabled, locationId, refreshTokenIfNeeded, handleMessage, startPingInterval, stopPingInterval, onRefreshToken]);

  const scheduleReconnect = useCallback(() => {
    if (reconnectAttemptRef.current >= 10) {
      setError(new Error('Max reconnection attempts reached'));
      return;
    }

    const baseDelay = 1000;
    const maxDelay = 30000;
    const delay = Math.min(
      baseDelay * Math.pow(2, reconnectAttemptRef.current),
      maxDelay
    ) + Math.random() * 1000;

    reconnectAttemptRef.current++;

    reconnectTimeoutRef.current = setTimeout(() => {
      connect();
    }, delay);
  }, [connect]);

  const disconnect = useCallback(() => {
    stopPingInterval();
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (wsRef.current) {
      wsRef.current.close(1000, 'Client disconnect');
      wsRef.current = null;
    }
  }, [stopPingInterval]);

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return {
    trips: Array.from(trips.values()),
    isConnected,
    error,
    reconnect: connect,
    disconnect,
  };
}
```

---

### 10.2 useWebSocketOrg Hook

```typescript
import { useEffect, useRef, useCallback, useState } from 'react';

interface Hotel {
  id: string;
  name: string;
  status: string;
}

interface LocationDeletedEvent {
  type: 'location_deleted';
  location_id: string;
  location_name: string;
  message: string;
  hotels: Hotel[];
  hotels_count: number;
}

interface UseWebSocketOrgOptions {
  organizationId: string;
  token: string;
  tokenExpiresAt: number;
  onRefreshToken: () => Promise<{ token: string; expiresAt: number }>;
  onLocationDeleted?: (event: LocationDeletedEvent) => void;
  enabled?: boolean;
}

export function useWebSocketOrg({
  organizationId,
  token,
  tokenExpiresAt,
  onRefreshToken,
  onLocationDeleted,
  enabled = true,
}: UseWebSocketOrgOptions) {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const pingIntervalRef = useRef<NodeJS.Timer | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timer | null>(null);
  const reconnectAttemptRef = useRef(0);
  const currentTokenRef = useRef(token);
  const currentExpiresAtRef = useRef(tokenExpiresAt);

  useEffect(() => {
    currentTokenRef.current = token;
    currentExpiresAtRef.current = tokenExpiresAt;
  }, [token, tokenExpiresAt]);

  const shouldRefreshToken = useCallback(() => {
    const now = Math.floor(Date.now() / 1000);
    const bufferSeconds = 5 * 60;
    return (currentExpiresAtRef.current - now) <= bufferSeconds;
  }, []);

  const refreshTokenIfNeeded = useCallback(async () => {
    if (!shouldRefreshToken()) {
      return currentTokenRef.current;
    }
    const { token: newToken, expiresAt } = await onRefreshToken();
    currentTokenRef.current = newToken;
    currentExpiresAtRef.current = expiresAt;
    return newToken;
  }, [shouldRefreshToken, onRefreshToken]);

  const startPingInterval = useCallback(() => {
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
    }

    pingIntervalRef.current = setInterval(async () => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        try {
          const validToken = await refreshTokenIfNeeded();
          wsRef.current.send(JSON.stringify({
            action: 'ping',
            token: validToken,
          }));
        } catch {
          wsRef.current?.close(1008, 'Token refresh failed');
        }
      }
    }, 30000);
  }, [refreshTokenIfNeeded]);

  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'connected':
          console.log('Connected to org events:', data.message);
          break;

        case 'location_deleted':
          onLocationDeleted?.(data as LocationDeletedEvent);
          break;

        case 'pong':
          break;

        case 'error':
          setError(new Error(data.detail));
          break;
      }
    } catch (err) {
      console.error('Failed to parse WebSocket message:', err);
    }
  }, [onLocationDeleted]);

  const connect = useCallback(async () => {
    if (!enabled || !organizationId) return;

    try {
      const validToken = await refreshTokenIfNeeded();
      const url = `wss://api.gt360.app/ws/org?organization_id=${organizationId}&token=${validToken}`;

      wsRef.current = new WebSocket(url);

      wsRef.current.onopen = () => {
        setIsConnected(true);
        setError(null);
        reconnectAttemptRef.current = 0;
        startPingInterval();
      };

      wsRef.current.onmessage = handleMessage;

      wsRef.current.onclose = (event) => {
        setIsConnected(false);
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
        }

        if (event.code === 1008) {
          onRefreshToken()
            .then(() => scheduleReconnect())
            .catch(() => setError(new Error('Authentication failed')));
        } else if (event.code !== 1000) {
          scheduleReconnect();
        }
      };

      wsRef.current.onerror = () => {
        setError(new Error('WebSocket connection error'));
      };
    } catch (err) {
      setError(err as Error);
    }
  }, [enabled, organizationId, refreshTokenIfNeeded, handleMessage, startPingInterval, onRefreshToken]);

  const scheduleReconnect = useCallback(() => {
    if (reconnectAttemptRef.current >= 10) {
      setError(new Error('Max reconnection attempts reached'));
      return;
    }

    const delay = Math.min(
      1000 * Math.pow(2, reconnectAttemptRef.current),
      30000
    ) + Math.random() * 1000;

    reconnectAttemptRef.current++;

    reconnectTimeoutRef.current = setTimeout(() => {
      connect();
    }, delay);
  }, [connect]);

  const disconnect = useCallback(() => {
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (wsRef.current) {
      wsRef.current.close(1000, 'Client disconnect');
      wsRef.current = null;
    }
  }, []);

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return {
    isConnected,
    error,
    reconnect: connect,
    disconnect,
  };
}
```

---

### 10.3 Usage Example

```typescript
// In your component
import { useWebSocketTrips } from '@/hooks/useWebSocketTrips';
import { useWebSocketOrg } from '@/hooks/useWebSocketOrg';
import { useAuth } from '@/hooks/useAuth';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';

function TripsPage({ locationId }: { locationId: string }) {
  const router = useRouter();
  const { token, expiresAt, organizationId, refreshToken } = useAuth();

  // Trips WebSocket
  const { trips, isConnected, error } = useWebSocketTrips({
    locationId,
    token,
    tokenExpiresAt: expiresAt,
    onRefreshToken: refreshToken,
    enabled: !!locationId && !!token,
  });

  // Org WebSocket (for location deletions)
  useWebSocketOrg({
    organizationId,
    token,
    tokenExpiresAt: expiresAt,
    onRefreshToken: refreshToken,
    onLocationDeleted: (event) => {
      toast.success(event.message, {
        description: event.hotels.map(h => `${h.name} (deleted)`).join(', '),
      });

      // Redirect if current location was deleted
      if (event.location_id === locationId) {
        router.push('/dashboard/locations');
      }
    },
    enabled: !!organizationId && !!token,
  });

  if (error) {
    return <div>Error: {error.message}</div>;
  }

  return (
    <div>
      <div>Status: {isConnected ? 'Connected' : 'Disconnected'}</div>
      <ul>
        {trips.map(trip => (
          <li key={trip.id}>
            {trip.pick_up_location} -> {trip.drop_off_location} ({trip.flight_number})
          </li>
        ))}
      </ul>
    </div>
  );
}
```

---

## 11. Best Practices

### 11.1 Token Storage

| Storage | Recommendation |
|---------|----------------|
| Access Token | Store in memory (React state/context) |
| Refresh Token | Cookie only (httpOnly, set by server) |
| localStorage | **NEVER** store tokens here |

### 11.2 Connection Management

1. **Single connection per location:** Don't create multiple WebSocket connections to the same location
2. **Cleanup on unmount:** Always close WebSocket when component unmounts
3. **Debounce reconnection:** Use exponential backoff to avoid overwhelming the server

### 11.3 Token Refresh

1. **Proactive refresh:** Refresh token before it expires (5 min buffer)
2. **Update ping token:** Always use the latest token in ping messages
3. **Handle refresh failures:** Redirect to login if refresh fails

### 11.4 Error Handling

1. **Graceful degradation:** Show appropriate UI when disconnected
2. **Retry limits:** Set maximum reconnection attempts
3. **User feedback:** Inform user of connection status

### 11.5 Performance

1. **Use Map for trips:** O(1) lookup/update vs O(n) for arrays
2. **Memoize callbacks:** Prevent unnecessary re-renders
3. **Batch state updates:** React 18+ does this automatically

---

## 12. Troubleshooting

### 12.1 Connection Fails Immediately (Code 1008)

**Possible Causes:**
- Token is expired
- Token is invalid (malformed JWT)
- organization_id doesn't match token (for /ws/org)
- User doesn't have access to location (for /ws/trips)

**Solution:**
1. Check token expiration (`exp` claim)
2. Verify organization_id in token metadata
3. Try refreshing the token first

### 12.2 No Events Received

**Possible Causes:**
- Subscribed to wrong location_id
- No changes happening in database
- Redis Pub/Sub not working

**Solution:**
1. Verify location_id matches expected
2. Check browser Network tab for WebSocket messages
3. Verify snapshot was received on connect

### 12.3 Frequent Disconnections

**Possible Causes:**
- Token expiring without refresh
- Network instability
- Server restarting

**Solution:**
1. Implement token refresh before expiration
2. Implement reconnection with backoff
3. Check server logs for errors

### 12.4 "Token required" Error on Ping

**Cause:** Sending ping without token field

**Solution:**
```json
// Wrong
{"action": "ping"}

// Correct
{"action": "ping", "token": "eyJhbGc..."}
```

### 12.5 Getting Old Data After Reconnect

**Cause:** Snapshot data is cached in Redis (5 min TTL)

**Solution:** This is expected behavior. Snapshot reflects current cached state. New events will arrive in real-time.

---

## Appendix A: Complete Message Reference

### Server -> Client

| type | When | Fields |
|------|------|--------|
| snapshot | On connect (/ws/trips) | location_id, location_info, trips[] |
| trips_batch | Trip(s) created/updated/deleted | location_id, events[] (each with event_type, trip_id, trip) |
| step_applied | Filter step applied | location_id, filter_type |
| step_reverted | Filter step reverted | location_id, filter_type |
| connected | On connect (/ws/org) | organization_id, message |
| location_delete_started | Location deletion in progress | location_id |
| location_deleted | Location deleted | location_id, location_name, message, hotels[], hotels_count |
| pong | Response to ping | - |
| subscribed | Response to subscribe | location_id |
| unsubscribed | Response to unsubscribe | location_id |
| error | Error occurred | code, detail |

### Client -> Server

| action | Required Fields | Description |
|--------|----------------|-------------|
| ping | token | Heartbeat with token validation |
| subscribe | - | Confirm subscription |
| unsubscribe | - | Stop receiving events |

---

## Appendix B: Configuration Reference

### Backend Configuration

| Setting | Value | File |
|---------|-------|------|
| JWT Algorithm | HS256 | shared/settings.py |
| Access Token Duration | 60 minutes | shared/settings.py |
| Refresh Token Duration | 30 days | features/auth/utils/utils.py |
| Redis Trip TTL | 300 seconds (5 min) | features/trips/webhooks/trip_webhooks.py |
| Ping Validation | Required | features/trips/websockets/*.py |

### Recommended Client Configuration

| Setting | Value |
|---------|-------|
| Ping Interval | 30 seconds |
| Token Refresh Buffer | 5 minutes before expiration |
| Max Reconnect Attempts | 10 |
| Reconnect Base Delay | 1 second |
| Reconnect Max Delay | 30 seconds |

---

## Related Documentation

- **[Trips CRUD Timezone Guide](./TRIPS_CRUD_TIMEZONE_GUIDE.md)** - Detailed guide on creating and updating trips with proper timezone handling
- **[Trip Type Classification](./TRIP_TYPE_CLASSIFICATION.md)** - How trip types (inbound/outbound/ground) are determined
- **[Trip Filters Frontend Guide](./TRIP_FILTERS_FRONTEND_GUIDE.md)** - Ground filtering system documentation

---

**Document End**
