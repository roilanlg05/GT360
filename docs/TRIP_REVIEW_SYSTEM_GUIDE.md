# Trip Review System Guide

## Overview

When a driver forgets to perform pick-up or drop-off while inside the geofence (or is outside of it), they can use the review-action endpoint to mark the trip as picked up or dropped off **without geofence validation**. These actions are flagged as "needs review" so a manager can later verify them.

## Architecture

### Database Schema

**Schema:** `reviews`
**Table:** `reviews.trip_reviews`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Auto-generated |
| `trip_id` | UUID (indexed) | Reference to trip (no FK CASCADE - trips get archived) |
| `trip_hash` | TEXT | Correlates with `trips_history` after archival |
| `driver_id` | UUID (FK) | References `entities.drivers.id`, SET NULL on delete |
| `location_id` | UUID (FK) | References `entities.locations.id`, CASCADE on delete |
| `review_pickup` | BOOLEAN | Pickup needs review |
| `review_dropoff` | BOOLEAN | Dropoff needs review |
| `pickup_flagged_at` | TIMESTAMPTZ | When pickup was flagged |
| `dropoff_flagged_at` | TIMESTAMPTZ | When dropoff was flagged |
| `pickup_reviewed_at` | TIMESTAMPTZ | When manager reviewed pickup |
| `dropoff_reviewed_at` | TIMESTAMPTZ | When manager reviewed dropoff |
| `pickup_reviewed_by` | UUID (FK) | Manager who reviewed pickup |
| `dropoff_reviewed_by` | UUID (FK) | Manager who reviewed dropoff |
| `created_at` | TIMESTAMPTZ | Record creation time |
| `updated_at` | TIMESTAMPTZ | Last update time |

**Design Decision:** Separate boolean columns instead of JSONB for direct indexability, type safety, and simpler queries.

**No FK on `trip_id`:** The `trip_id` column intentionally has no foreign key constraint because trips are deleted from `trips.trips` when archived to `trips.trips_history` via the drop-off trigger. The `trip_hash` field allows correlation with archived trips.

---

## Endpoints

### 1. POST `/v1/trips/{trip_id}/review-action` (Driver)

Marks pickup or dropoff without geofence validation and flags for manager review.

**Auth:** `driver` role

**Request Body:**
```json
{
  "type": "pick-up",
  "driver_id": "uuid"
}
```

**Validations:**
- `type` must be `"pick-up"` or `"drop-off"`
- Driver must be active
- Driver must be assigned to the trip
- Trip must not already have `picked_up_at` / `dropped_off_at`

**Pick-up flow:**
1. Creates/updates `TripReview` with `review_pickup=true`, `pickup_flagged_at=now`
2. Flushes review to DB
3. Updates trip: `picked_up_at=now`, `status=EN_ROUTE`
4. Commits transaction

**Drop-off flow:**
1. Creates/updates `TripReview` with `review_dropoff=true`, `dropoff_flagged_at=now`
2. **Flushes review BEFORE updating trip** (critical: the archive trigger deletes the trip)
3. Updates trip: `dropped_off_at=now`, `status=COMPLETED`
4. Archive trigger fires: copies trip to `trips_history`, deletes from `trips`
5. Commits transaction - review record survives because it has no FK CASCADE

**Response (200):**
```json
{
  "status": "ok",
  "message": "Pickup registered - needs review",
  "trip_id": "uuid",
  "picked_up_at": "2025-01-15T10:30:00+00:00",
  "needs_review": true
}
```

### 2. GET `/v1/reviews` (Manager)

Lists reviews, filterable by location and pending status.

**Auth:** `manager` role

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `location_id` | UUID | null | Filter by location |
| `pending_only` | bool | true | Only show unreviewed items |
| `limit` | int | 50 | Max results (1-200) |
| `skip` | int | 0 | Offset for pagination |

**Response (200):**
```json
{
  "reviews": [
    {
      "id": "uuid",
      "trip_id": "uuid",
      "trip_hash": "abc123",
      "driver_id": "uuid",
      "location_id": "uuid",
      "review_pickup": true,
      "review_dropoff": false,
      "pickup_flagged_at": "2025-01-15T10:30:00+00:00",
      "dropoff_flagged_at": null,
      "pickup_reviewed_at": null,
      "dropoff_reviewed_at": null,
      "pickup_reviewed_by": null,
      "dropoff_reviewed_by": null,
      "created_at": "2025-01-15T10:30:00+00:00",
      "updated_at": "2025-01-15T10:30:00+00:00"
    }
  ],
  "total": 1,
  "limit": 50,
  "skip": 0
}
```

### 3. PATCH `/v1/reviews/{review_id}` (Manager)

Marks a pickup or dropoff review as resolved.

**Auth:** `manager` role

**Request Body:**
```json
{
  "type": "pick-up"
}
```

**Validations:**
- `type` must be `"pick-up"` or `"drop-off"`
- The corresponding flag must be `true` (was flagged for review)
- Must not already be reviewed (409 Conflict)

**Response (200):**
```json
{
  "status": "ok",
  "message": "pick-up reviewed successfully",
  "review": { ... }
}
```

---

## Flow Diagram

```
Driver at location but outside geofence
          |
          v
POST /v1/trips/{trip_id}/review-action { type: "pick-up" }
          |
          v
    +-----+------+
    | TripReview  |  review_pickup=true, pickup_flagged_at=now
    +-----+------+
          |
          v
    +-----+------+
    | Trip        |  picked_up_at=now, status=EN_ROUTE
    +-----+------+
          |
          v
POST /v1/trips/{trip_id}/review-action { type: "drop-off" }
          |
          v
    +-----+------+
    | TripReview  |  review_dropoff=true, dropoff_flagged_at=now
    +-----+------+  (flushed BEFORE trip update)
          |
          v
    +-----+------+
    | Trip        |  dropped_off_at=now, status=COMPLETED
    +-----+------+
          |
          v  (archive trigger fires)
    +-----+------+
    | TripHistory |  trip copied here
    +-----+------+
          |
    Trip deleted from trips.trips
    TripReview survives (no FK CASCADE)
          |
          v
Manager sees review in GET /v1/reviews
          |
          v
PATCH /v1/reviews/{id} { type: "pick-up" }
PATCH /v1/reviews/{id} { type: "drop-off" }
```

---

## Migration

The `reviews` schema is created automatically during app startup in `main.py`:

```python
async with AsyncSession(engine) as _s:
    await _s.exec("CREATE SCHEMA IF NOT EXISTS reviews")
    await _s.commit()
```

The `reviews.trip_reviews` table is created automatically by PSQLModel via `ensure_tables=True`.

---

## Files

| File | Purpose |
|------|---------|
| `shared/db/schemas/reviews/trip_reviews.py` | PSQLModel schema definition |
| `shared/db/schemas/reviews/__init__.py` | Schema exports |
| `features/trips/models/review_models.py` | Pydantic request/response models |
| `features/trips/routes/review_router.py` | FastAPI router with 3 endpoints |
| `docs/TRIP_REVIEW_SYSTEM_GUIDE.md` | This guide |
