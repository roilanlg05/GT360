# Driver Background Location Tracking — Backend API Guide

## Overview

The backend now supports driver location updates via **two transport methods**:

1. **WebSocket** (`ws/driver-locations`) — for foreground (real-time, bidirectional)
2. **HTTP POST** (`POST /v1/drivers/me/location`) — for background (iOS/Android background tasks)

Both methods write to the same Redis store and publish to the same channel. **Managers on Mapbox receive identical `location_update` events regardless of which method the driver uses.**

---

## For the Driver App Developer

### New Endpoint: `POST /v1/drivers/me/location`

Use this endpoint from the `expo-location` background task (`startLocationUpdatesAsync` callback) when the WebSocket is unavailable.

**Request:**

```
POST /v1/drivers/me/location
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "lat": 25.7617,
  "lng": -80.1918
}
```

**Response:** `204 No Content` (no body)

**Errors:**

| Status | Detail | Cause |
|--------|--------|-------|
| 401 | Missing or invalid authentication | Token expired or missing |
| 403 | Not Authorized | Token role is not `driver` |
| 404 | Driver not found | Driver record doesn't exist in DB |
| 422 | Validation error | `lat` or `lng` missing or not a number |

### Recommended Architecture: Dual-Mode

```
App in FOREGROUND:
  - Use WebSocket (ws/driver-locations?token=<jwt>)
  - Send {"action": "location_update", "lat": ..., "lng": ...} every 5s
  - Receive other drivers' locations (if sharing enabled)

App in BACKGROUND (iOS suspends process in ~5-10s):
  - WebSocket will die — this is expected on iOS
  - expo-location's startLocationUpdatesAsync wakes app briefly (~30s)
  - In the callback: POST /v1/drivers/me/location with GPS coords
  - No need to open/maintain WebSocket in background

App returns to FOREGROUND:
  - Detect via AppState listener
  - Reconnect WebSocket for real-time features
  - Stop using HTTP POST
```

### Token Management

- Access token duration: **60 minutes** (configured via `TOKEN_DURATION` env var)
- Refresh endpoint: `POST /v1/auth/refresh` (uses refresh token from sign-in)
- **Refresh the token at ~50 minutes**, before it expires
- Both WebSocket and HTTP POST use the same JWT access token
- If the HTTP POST returns `401`, refresh the token and retry

### WebSocket Duplicate Connection Prevention

The backend now enforces **one WebSocket per driver**. If the driver opens a second WebSocket connection:

- The **old connection is closed** with code `4001` and reason `"New connection established"`
- The **new connection becomes active**
- No manual cleanup needed on the client side

Handle code `4001` in your WebSocket `onClose` — it means another session took over. Do **not** reconnect automatically on `4001` unless the user explicitly reopens the app.

### Going Offline

When the driver sets status to offline (`PATCH /v1/drivers/me/active` with `{"is_active": false}`):

- The backend **immediately removes** the driver's location from Redis
- The manager sees the driver disappear from the map instantly
- Background location tracking should **stop** when the driver goes offline
- Background location tracking should **restart** when the driver goes back online

### WebSocket Disconnect Behavior Change

**Before**: When the WebSocket disconnected, the driver's location was immediately deleted from Redis, causing the driver to disappear from the manager's map.

**Now**: When the WebSocket disconnects, the location **stays in Redis**. This means:

- If the driver transitions to background and starts sending HTTP POSTs, they remain visible on the map without any gap
- If the driver truly goes offline (app killed, no battery), the **stale cleanup task** removes them after **3 minutes** of no updates
- If the driver explicitly goes offline via the status toggle, the location is removed immediately

### Ping/Pong (unchanged)

The WebSocket ping mechanism works the same:

```json
// Client sends:
{"action": "ping", "token": "<current_access_token>"}

// Server responds:
{"type": "pong"}

// If token expired, server responds and closes:
{"type": "error", "code": 401, "detail": "Invalid or expired token"}
// WebSocket closed with code 1008
```

Send pings every 30-45 seconds while in foreground to detect token expiry early.

---

## For the Manager Frontend (Web) Developer

### No Changes Required to Your WebSocket Connection

The manager WebSocket connection and events are **unchanged**. You connect the same way:

```
ws://host/ws/driver-locations?token=<manager_jwt>&location_id=<optional_filter>
```

### Events You Already Handle

These events continue to work exactly the same:

```json
// Initial snapshot (on connect)
{"type": "snapshot", "drivers": [...]}

// Real-time location update (from WS or HTTP — identical format)
{
  "type": "location_update",
  "driver_id": "uuid",
  "first_name": "John",
  "last_name": "Doe",
  "location_id": "uuid",
  "lat": 25.7617,
  "lng": -80.1918,
  "updated_at": "2026-02-27T15:30:00+00:00"
}

// Sharing toggle events (for driver-to-driver visibility)
{"type": "sharing_enabled", "drivers": [...]}
{"type": "sharing_disabled"}
```

### New Event: `driver_offline`

There is **one new event type** you should handle:

```json
{
  "type": "driver_offline",
  "driver_id": "uuid"
}
```

**When it fires:**

- The stale cleanup task removes a driver who hasn't sent any location update (via WS or HTTP) for **3 minutes**
- The driver explicitly went offline (`is_active: false`) — their location is removed from Redis and this event is broadcast

**What to do on the frontend:**

- Remove the driver's marker/pin from the Mapbox map
- Or visually mark them as offline (grey icon, tooltip "Last seen X min ago", etc.)

### Optional: Stale Indicator

You can use the `updated_at` field from `location_update` events to show staleness in the UI:

```javascript
const age = Date.now() - new Date(event.updated_at).getTime();

if (age > 30_000) {
  // > 30 seconds: show driver marker as "stale" (e.g. grey or faded)
}
if (age > 180_000) {
  // > 3 minutes: driver will be removed by backend cleanup
}
```

This gives managers a visual cue that a driver might be in a tunnel, have bad connectivity, or have the app backgrounded without HTTP fallback.

### `location_id` Filter (unchanged)

If you connect with `?location_id=<uuid>`, you only receive updates for drivers assigned to that location. The `driver_offline` event is broadcast to **all** managers regardless of filter, since it only contains `driver_id` (no `location_id`).

---

## Summary of Backend Changes

| Change | Impact on Driver App | Impact on Manager Web |
|--------|---------------------|----------------------|
| New `POST /v1/drivers/me/location` | Use in background tasks | None — transparent |
| WS disconnect no longer removes location | Driver stays on map during transitions | Driver doesn't "blink" off map |
| `PATCH /v1/drivers/me/active` clears Redis | Stop background tracking on offline | Driver disappears instantly on offline |
| Duplicate WS prevention (code `4001`) | Handle gracefully, don't auto-reconnect | None |
| Stale cleanup (3 min, every 60s) | None — transparent | Handle new `driver_offline` event |
| `ws_ping_interval` stays disabled | No server-side pings that kill background WS | None |

---

## Redis Data Flow (for reference)

```
Driver App (foreground)                    Driver App (background)
        |                                          |
  WebSocket message:                        HTTP POST:
  {"action":"location_update",             POST /v1/drivers/me/location
   "lat":25.76, "lng":-80.19}              {"lat":25.76, "lng":-80.19}
        |                                          |
        v                                          v
   location_websocket.py                   drivers_router.py
        |                                          |
        +------------------------------------------+
                            |
                            v
          store_driver_location(org_id, driver_id, data)
                            |
                    +-------+-------+
                    |               |
                    v               v
            Redis HSET          Redis PUBLISH
    driver_locations:{org_id}   driver_locations:{org_id}
                                    |
                                    v
                            _org_listener()
                                    |
                                    v
                          broadcast_to_org()
                                    |
                                    v
                    Manager WebSocket receives:
                    {"type":"location_update", ...}
                                    |
                                    v
                         Mapbox map updates pin
```
