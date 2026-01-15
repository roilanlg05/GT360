# WebSocket Integration Guide for Frontend Developers

**Version:** 1.0
**Last Updated:** 2026-01-05
**Backend:** GT360 API

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [WebSocket Endpoints](#2-websocket-endpoints)
3. [Authentication System](#3-authentication-system)
4. [Message Formats](#4-message-formats)
5. [Ping/Pong & Token Revalidation](#5-pingpong--token-revalidation)
6. [Token Refresh Flow](#6-token-refresh-flow)
7. [Reconnection Strategy](#7-reconnection-strategy)
8. [Error Codes & Close Codes](#8-error-codes--close-codes)
9. [TypeScript Implementation Examples](#9-typescript-implementation-examples)
10. [Best Practices](#10-best-practices)
11. [Troubleshooting](#11-troubleshooting)

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
  "trips": [
    {
      "id": "trip-uuid-1",
      "location_id": "550e8400-e29b-41d4-a716-446655440000",
      "pick_up_date": "2026-01-05",
      "pick_up_time": "14:30:00+00:00",
      "pick_up_location": "The Galt House",
      "drop_off_location": "SDF",
      "airline": "Southwest Airlines",
      "flight_number": "WN 1234",
      "riders": 4,
      "started_at": null,
      "picked_up_at": null,
      "dropped_off_at": null,
      "created_at": "2026-01-05T10:00:00.000Z",
      "updated_at": "2026-01-05T10:00:00.000Z"
    }
  ]
}
```

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
  "trips": [
    {
      "id": "trip-uuid",
      "location_id": "location-uuid",
      "pick_up_date": "2026-01-05",
      "pick_up_time": "14:30:00+00:00",
      "pick_up_location": "Hotel Name",
      "drop_off_location": "Airport Code",
      "airline": "Airline Name",
      "flight_number": "XX 1234",
      "riders": 4,
      "started_at": null,
      "picked_up_at": null,
      "dropped_off_at": null,
      "created_at": "2026-01-05T10:00:00.000Z",
      "updated_at": "2026-01-05T10:00:00.000Z"
    }
  ]
}
```

---

#### Trip Event (real-time updates)

**Insert Event:**
```json
{
  "type": "trip_event",
  "event_type": "insert",
  "location_id": "550e8400-e29b-41d4-a716-446655440000",
  "trip_id": "trip-uuid",
  "trip": {
    "id": "trip-uuid",
    "location_id": "location-uuid",
    "pick_up_date": "2026-01-05",
    "pick_up_time": "14:30:00+00:00",
    "pick_up_location": "Hotel Name",
    "drop_off_location": "SDF",
    "airline": "Southwest Airlines",
    "flight_number": "WN 1234",
    "riders": 4,
    "started_at": null,
    "picked_up_at": null,
    "dropped_off_at": null,
    "created_at": "2026-01-05T10:00:00.000Z",
    "updated_at": "2026-01-05T10:00:00.000Z"
  }
}
```

**Update Event:**
```json
{
  "type": "trip_event",
  "event_type": "update",
  "location_id": "550e8400-e29b-41d4-a716-446655440000",
  "trip_id": "trip-uuid",
  "trip": {
    "id": "trip-uuid",
    "...": "updated fields",
    "updated_at": "2026-01-05T12:00:00.000Z"
  }
}
```

**Delete Event:**
```json
{
  "type": "trip_event",
  "event_type": "delete",
  "location_id": "550e8400-e29b-41d4-a716-446655440000",
  "trip_id": "trip-uuid",
  "trip": {
    "id": "trip-uuid",
    "pick_up_location": "Hotel Name",
    "drop_off_location": "SDF",
    "airline": "Southwest Airlines",
    "flight_number": "WN 1234"
  }
}
```

**Note:** Delete events include trip data so you can show useful notifications like:
```
"Deleted: Hotel Name -> SDF (WN 1234)"
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

## 5. Ping/Pong & Token Revalidation

### 5.1 Why Ping/Pong is Important

1. **Keep-alive:** Prevents connection timeout
2. **Token validation:** Server validates the token on each ping
3. **Early detection:** Catches expired tokens before they cause issues

### 5.2 Recommended Interval

Send a ping every **30-60 seconds** with the current access token.

### 5.3 Flow

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

### 5.4 Token Expiration During Connection

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

### 5.5 Implementation Pattern

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

## 6. Token Refresh Flow

### 6.1 When to Refresh

Refresh the token **before it expires**. Recommended: 5 minutes before expiration.

```typescript
function shouldRefreshToken(expiresAt: number): boolean {
  const now = Math.floor(Date.now() / 1000);
  const bufferSeconds = 5 * 60; // 5 minutes
  return (expiresAt - now) <= bufferSeconds;
}
```

### 6.2 Refresh Flow with WebSocket

```
1. Check token expiration before sending ping
2. If near expiration:
   a. Call POST /v1/auth/refresh
   b. Update access_token in memory
   c. Cookie is automatically updated by browser
3. Send ping with NEW token
4. Continue normal operation
```

### 6.3 Implementation Example

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

## 7. Reconnection Strategy

### 7.1 WebSocket Close Codes

| Code | Meaning | Action |
|------|---------|--------|
| 1000 | Normal closure | Reconnect if needed |
| 1001 | Going away | Reconnect |
| 1006 | Abnormal closure | Reconnect with backoff |
| 1008 | Policy violation (auth) | Refresh token, then reconnect |
| 1011 | Server error | Reconnect with backoff |

### 7.2 Reconnection Algorithm

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

### 7.3 Reconnection Flow

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

### 7.4 Implementation Example

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

## 8. Error Codes & Close Codes

### 8.1 WebSocket Close Codes

| Code | Name | Description | Client Action |
|------|------|-------------|---------------|
| 1000 | Normal | Clean close | Reconnect if needed |
| 1001 | Going Away | Server/client leaving | Reconnect |
| 1006 | Abnormal | No close frame received | Reconnect with backoff |
| 1008 | Policy Violation | Authentication failed | Refresh token, reconnect |
| 1011 | Internal Error | Server error | Reconnect with backoff |

### 8.2 HTTP Error Codes (Auth Endpoints)

| Code | Endpoint | Meaning |
|------|----------|---------|
| 401 | sign-in | Invalid credentials |
| 401 | sign-in | Email not verified |
| 401 | refresh | Invalid/missing refresh token |
| 401 | refresh | Refresh token expired/revoked |
| 401 | * | Missing/invalid access token |
| 403 | change-password | Incorrect current password |
| 409 | register | Email/phone already in use |

### 8.3 WebSocket Error Messages

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

## 9. TypeScript Implementation Examples

### 9.1 useWebSocketTrips Hook

```typescript
import { useEffect, useRef, useCallback, useState } from 'react';

interface Trip {
  id: string;
  location_id: string;
  pick_up_date: string;
  pick_up_time: string;
  pick_up_location: string;
  drop_off_location: string;
  airline: string;
  flight_number: string;
  riders: number;
  started_at: string | null;
  picked_up_at: string | null;
  dropped_off_at: string | null;
  created_at: string;
  updated_at: string;
}

interface TripEvent {
  type: 'trip_event';
  event_type: 'insert' | 'update' | 'delete';
  location_id: string;
  trip_id: string;
  trip: Trip;
}

interface SnapshotEvent {
  type: 'snapshot';
  location_id: string;
  trips: Trip[];
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
          const snapshotTrips = new Map<string, Trip>();
          (data as SnapshotEvent).trips.forEach(trip => {
            snapshotTrips.set(trip.id, trip);
          });
          setTrips(snapshotTrips);
          break;

        case 'trip_event':
          const tripEvent = data as TripEvent;
          setTrips(prev => {
            const newMap = new Map(prev);
            if (tripEvent.event_type === 'delete') {
              newMap.delete(tripEvent.trip_id);
            } else {
              newMap.set(tripEvent.trip_id, tripEvent.trip);
            }
            return newMap;
          });
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

### 9.2 useWebSocketOrg Hook

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

### 9.3 Usage Example

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

## 10. Best Practices

### 10.1 Token Storage

| Storage | Recommendation |
|---------|----------------|
| Access Token | Store in memory (React state/context) |
| Refresh Token | Cookie only (httpOnly, set by server) |
| localStorage | **NEVER** store tokens here |

### 10.2 Connection Management

1. **Single connection per location:** Don't create multiple WebSocket connections to the same location
2. **Cleanup on unmount:** Always close WebSocket when component unmounts
3. **Debounce reconnection:** Use exponential backoff to avoid overwhelming the server

### 10.3 Token Refresh

1. **Proactive refresh:** Refresh token before it expires (5 min buffer)
2. **Update ping token:** Always use the latest token in ping messages
3. **Handle refresh failures:** Redirect to login if refresh fails

### 10.4 Error Handling

1. **Graceful degradation:** Show appropriate UI when disconnected
2. **Retry limits:** Set maximum reconnection attempts
3. **User feedback:** Inform user of connection status

### 10.5 Performance

1. **Use Map for trips:** O(1) lookup/update vs O(n) for arrays
2. **Memoize callbacks:** Prevent unnecessary re-renders
3. **Batch state updates:** React 18+ does this automatically

---

## 11. Troubleshooting

### 11.1 Connection Fails Immediately (Code 1008)

**Possible Causes:**
- Token is expired
- Token is invalid (malformed JWT)
- organization_id doesn't match token (for /ws/org)
- User doesn't have access to location (for /ws/trips)

**Solution:**
1. Check token expiration (`exp` claim)
2. Verify organization_id in token metadata
3. Try refreshing the token first

### 11.2 No Events Received

**Possible Causes:**
- Subscribed to wrong location_id
- No changes happening in database
- Redis Pub/Sub not working

**Solution:**
1. Verify location_id matches expected
2. Check browser Network tab for WebSocket messages
3. Verify snapshot was received on connect

### 11.3 Frequent Disconnections

**Possible Causes:**
- Token expiring without refresh
- Network instability
- Server restarting

**Solution:**
1. Implement token refresh before expiration
2. Implement reconnection with backoff
3. Check server logs for errors

### 11.4 "Token required" Error on Ping

**Cause:** Sending ping without token field

**Solution:**
```json
// Wrong
{"action": "ping"}

// Correct
{"action": "ping", "token": "eyJhbGc..."}
```

### 11.5 Getting Old Data After Reconnect

**Cause:** Snapshot data is cached in Redis (5 min TTL)

**Solution:** This is expected behavior. Snapshot reflects current cached state. New events will arrive in real-time.

---

## Appendix A: Complete Message Reference

### Server -> Client

| type | event_type | When | Fields |
|------|------------|------|--------|
| snapshot | - | On connect (/ws/trips) | location_id, trips[] |
| trip_event | insert | Trip created | location_id, trip_id, trip |
| trip_event | update | Trip modified | location_id, trip_id, trip |
| trip_event | delete | Trip deleted | location_id, trip_id, trip |
| connected | - | On connect (/ws/org) | organization_id, message |
| location_deleted | - | Location deleted | location_id, location_name, message, hotels[], hotels_count |
| pong | - | Response to ping | - |
| subscribed | - | Response to subscribe | location_id |
| unsubscribed | - | Response to unsubscribe | location_id |
| error | - | Error occurred | code, detail |

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

**Document End**
