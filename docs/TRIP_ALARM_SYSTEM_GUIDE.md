# Trip Alarm System Guide

## Overview

Drivers and managers can configure personal alarms associated with specific trips. When the frontend loads trips, it also fetches the user's alarms to schedule local notifications at the specified time. Alarms are **per-user** — if a user sets an alarm on a trip, only that user sees it. Alarms are **not** archived to `trips_history`.

## Architecture

### Design Decision: Separate Table

A separate `trips.trip_alarms` table was chosen over a field in the `trips` table because:

- Alarms are per-user; a field in `trips` would be shared across all users
- FK CASCADE to `trips.trips.id` ensures automatic cleanup when a trip is archived/deleted
- Allows multiple alarms per trip (one per user)
- `UNIQUE(trip_id, user_id)` enforces max 1 alarm per user per trip

### Database Schema

**Schema:** `trips`
**Table:** `trips.trip_alarms`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Auto-generated |
| `trip_id` | UUID (FK) | References `trips.trips.id`, CASCADE on delete |
| `user_id` | UUID (FK) | References `entities.users.id`, CASCADE on delete |
| `alarm_at` | TIMESTAMPTZ | When the alarm should fire |
| `is_active` | BOOLEAN | Whether the alarm is active (default: true) |
| `created_at` | TIMESTAMPTZ | Record creation time |
| `updated_at` | TIMESTAMPTZ | Last update time |

**Constraints:**
- `UNIQUE(trip_id, user_id)` — one alarm per user per trip

**FK CASCADE behavior:**
- When a trip is deleted (archive trigger on drop-off), the alarm is automatically deleted
- When a user is deleted, their alarms are automatically deleted

---

## Endpoints

### 1. POST `/v1/trips/{trip_id}/alarm` (Driver/Manager)

Creates an alarm for the authenticated user on a specific trip.

**Auth:** `driver` or `manager` role

**Request Body:**
```json
{
  "alarm_at": "2025-01-15T06:00:00-05:00"
}
```

**Validations:**
- Trip must exist
- User must not already have an alarm for this trip (409 Conflict)
- `user_id` is extracted from the auth token (not from the body)

**Response (201):**
```json
{
  "status": "ok",
  "message": "Alarm created",
  "alarm": {
    "id": "uuid",
    "trip_id": "uuid",
    "user_id": "uuid",
    "alarm_at": "2025-01-15T11:00:00+00:00",
    "is_active": true,
    "created_at": "2025-01-14T20:00:00+00:00",
    "updated_at": "2025-01-14T20:00:00+00:00"
  }
}
```

### 2. GET `/v1/trips/alarms` (Driver/Manager)

Lists all active alarms for the authenticated user. The frontend calls this on app startup to schedule local notifications.

**Auth:** `driver` or `manager` role

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `location_id` | UUID | null | Filter alarms by trip location |

**Response (200):**
```json
{
  "alarms": [
    {
      "id": "uuid",
      "trip_id": "uuid",
      "user_id": "uuid",
      "alarm_at": "2025-01-15T11:00:00+00:00",
      "is_active": true,
      "created_at": "2025-01-14T20:00:00+00:00",
      "updated_at": "2025-01-14T20:00:00+00:00"
    }
  ],
  "total": 1
}
```

### 3. PATCH `/v1/trips/{trip_id}/alarm` (Driver/Manager)

Updates the alarm for the authenticated user on a specific trip. Can change the alarm time and/or toggle active status.

**Auth:** `driver` or `manager` role

**Request Body (all fields optional):**
```json
{
  "alarm_at": "2025-01-15T07:00:00-05:00",
  "is_active": false
}
```

**Validations:**
- Alarm must exist for this user+trip (404 if not found)
- Only the owner can modify their alarm

**Response (200):**
```json
{
  "status": "ok",
  "message": "Alarm updated",
  "alarm": {
    "id": "uuid",
    "trip_id": "uuid",
    "user_id": "uuid",
    "alarm_at": "2025-01-15T12:00:00+00:00",
    "is_active": false,
    "created_at": "2025-01-14T20:00:00+00:00",
    "updated_at": "2025-01-14T20:05:00+00:00"
  }
}
```

### 4. DELETE `/v1/trips/{trip_id}/alarm` (Driver/Manager)

Deletes the alarm for the authenticated user on a specific trip.

**Auth:** `driver` or `manager` role

**Response (200):**
```json
{
  "status": "ok",
  "message": "Alarm deleted",
  "trip_id": "uuid"
}
```

---

## Flow Diagram

```
1. Driver sees a trip and taps alarm button
          |
          v
2. Frontend shows time picker
          |
          v
3. POST /v1/trips/{trip_id}/alarm { alarm_at: "2025-01-15T06:00:00-05:00" }
          |
          v
    +------------+
    | TripAlarm  |  trip_id, user_id, alarm_at saved
    +------------+
          |
          v
4. On app startup: GET /v1/trips/alarms
          |
          v
5. Frontend schedules local notifications for each alarm_at
          |
          v
6. To deactivate: PATCH /v1/trips/{trip_id}/alarm { is_active: false }
   To change time: PATCH /v1/trips/{trip_id}/alarm { alarm_at: "..." }
   To delete:      DELETE /v1/trips/{trip_id}/alarm
          |
          v
7. When trip completes (drop-off trigger):
   Trip deleted from trips.trips
          |
          v
   FK CASCADE deletes alarm automatically
```

---

## Error Codes

| Code | Endpoint | Cause |
|------|----------|-------|
| 400 | All | Invalid trip ID or location_id format |
| 401 | All | Missing or invalid authentication |
| 403 | All | User role is not `driver` or `manager` |
| 404 | POST | Trip not found |
| 404 | PATCH/DELETE | Alarm not found for this user+trip |
| 409 | POST | Alarm already exists for this user on this trip |

---

## Migration

The `trips.trip_alarms` table is created automatically by PSQLModel on app startup. No manual migration is needed.

---

## Files

| File | Purpose |
|------|---------|
| `shared/db/schemas/trips/trip_alarms.py` | PSQLModel schema definition |
| `features/trips/models/alarm_models.py` | Pydantic request/response models |
| `features/trips/routes/alarm_router.py` | FastAPI router with 4 endpoints |
| `docs/TRIP_ALARM_SYSTEM_GUIDE.md` | This guide |
