# Driver Rating System Guide

## Overview

Crew members (airline crew) can rate drivers after completed trips. Ratings include a score from 1 to 5, an optional comment, and optional predefined stamps (tags like "smooth_driving", "late", "nice", etc.). Managers can view all ratings for any driver; drivers can see their own aggregated summary.

## Architecture

### Database Schema

**Schema:** `ratings`
**Table:** `ratings.driver_ratings`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Auto-generated |
| `trip_id` | UUID (indexed) | Reference to trip (no FK - trips get archived) |
| `trip_hash` | TEXT (indexed) | Correlates with `trips_history` after archival |
| `driver_id` | UUID (FK) | References `entities.drivers.id`, SET NULL on delete |
| `crew_id` | UUID (FK) | References `entities.users.id`, SET NULL on delete |
| `score` | SMALLINT | Rating score (1-5), enforced by CHECK constraint |
| `comment` | TEXT | Optional text comment (max 500 chars validated at API level) |
| `stamps` | JSONB | Optional array of predefined stamp strings |
| `created_at` | TIMESTAMPTZ | Record creation time |

**Constraints:**
- `uq_crew_trip_rating` — UNIQUE on `(crew_id, trip_id)` prevents duplicate ratings
- `valid_score` — CHECK `score >= 1 AND score <= 5`

**No FK on `trip_id`:** The `trip_id` column intentionally has no foreign key constraint because trips are deleted from `trips.trips` when archived to `trips.trips_history` via the drop-off trigger. The `trip_hash` field allows correlation with archived trips.

**No `updated_at`:** Ratings are immutable once submitted.

### Available Stamps

| Stamp | Description |
|-------|-------------|
| `smooth_driving` | Driver drove smoothly |
| `late` | Driver was late |
| `nice` | Driver was nice/friendly |
| `professional` | Driver was professional |
| `clean_vehicle` | Vehicle was clean |
| `rude` | Driver was rude |
| `unsafe_driving` | Driver drove unsafely |
| `helpful` | Driver was helpful |

---

## Endpoints

### 1. POST `/v1/ratings/trips/{trip_id}` (Crew)

Submits a rating for a driver after a completed trip.

**Auth:** `crew` role

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `trip_id` | UUID | ID of the completed trip |

**Request Body:**
```json
{
  "score": 5,
  "comment": "Great driver, very professional",
  "stamps": ["smooth_driving", "professional", "clean_vehicle"]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `score` | int | Yes | Rating from 1 to 5 |
| `comment` | string | No | Optional comment (max 500 chars) |
| `stamps` | string[] | No | Optional list of valid stamp strings |

**Validations:**
- Trip must exist in `trips_history` (completed trips)
- Trip must have `dropped_off_at` (fully completed)
- Crew airline must match trip airline
- No duplicate rating for same crew + trip (409 Conflict)
- Stamps must be from the valid list

**Response (201):**
```json
{
  "status": "ok",
  "message": "Rating submitted successfully",
  "rating": {
    "id": "a1b2c3d4-...",
    "trip_id": "e5f6g7h8-...",
    "trip_hash": "abc123",
    "driver_id": "i9j0k1l2-...",
    "crew_id": "m3n4o5p6-...",
    "crew_name": "John Smith",
    "score": 5,
    "comment": "Great driver, very professional",
    "stamps": ["smooth_driving", "professional", "clean_vehicle"],
    "created_at": "2026-02-17T10:30:00+00:00"
  }
}
```

**Error Responses:**
| Code | Detail |
|------|--------|
| 400 | Invalid trip ID |
| 400 | Invalid stamps: [...] |
| 400 | Trip is not completed yet |
| 403 | Your airline does not match the trip airline |
| 404 | Completed trip not found |
| 404 | Crew record not found |
| 409 | You have already rated this trip |

---

### 2. GET `/v1/ratings/drivers/{driver_id}` (Manager)

Lists all ratings for a specific driver with pagination.

**Auth:** `manager` role

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `driver_id` | UUID | ID of the driver |

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | int | 1 | Page number (min 1) |
| `page_size` | int | 20 | Items per page (1-100) |

**Response (200):**
```json
{
  "ratings": [
    {
      "id": "a1b2c3d4-...",
      "trip_id": "e5f6g7h8-...",
      "trip_hash": "abc123",
      "driver_id": "i9j0k1l2-...",
      "crew_id": "m3n4o5p6-...",
      "crew_name": "John Smith",
      "score": 5,
      "comment": "Great driver",
      "stamps": ["smooth_driving", "professional"],
      "created_at": "2026-02-17T10:30:00+00:00"
    },
    {
      "id": "q7r8s9t0-...",
      "trip_id": "u1v2w3x4-...",
      "trip_hash": "def456",
      "driver_id": "i9j0k1l2-...",
      "crew_id": "y5z6a7b8-...",
      "crew_name": "Jane Doe",
      "score": 3,
      "comment": null,
      "stamps": ["late"],
      "created_at": "2026-02-16T14:00:00+00:00"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_ratings": 2,
    "total_pages": 1
  }
}
```

---

### 3. GET `/v1/ratings/drivers/{driver_id}/summary` (Manager, Driver)

Returns aggregated rating summary for a driver.

**Auth:** `manager` or `driver` role (drivers can only view their own summary)

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `driver_id` | UUID | ID of the driver |

**Response (200):**
```json
{
  "driver_id": "i9j0k1l2-...",
  "average_score": 4.25,
  "total_ratings": 12,
  "score_distribution": {
    "1": 0,
    "2": 1,
    "3": 2,
    "4": 4,
    "5": 5
  },
  "stamp_counts": [
    { "stamp": "professional", "count": 8 },
    { "stamp": "smooth_driving", "count": 6 },
    { "stamp": "clean_vehicle", "count": 5 },
    { "stamp": "nice", "count": 3 },
    { "stamp": "helpful", "count": 2 },
    { "stamp": "late", "count": 1 }
  ]
}
```

**Error Responses:**
| Code | Detail |
|------|--------|
| 403 | Drivers can only view their own rating summary |
| 404 | Driver not found |

---

### 4. GET `/v1/ratings/stamps` (Crew)

Returns the list of valid stamp strings that crew can use when rating.

**Auth:** `crew` role

**Response (200):**
```json
{
  "stamps": [
    "smooth_driving",
    "late",
    "nice",
    "professional",
    "clean_vehicle",
    "rude",
    "unsafe_driving",
    "helpful"
  ]
}
```

---

## Flow Diagram

```
Crew completes trip (dropped off)
          |
          v
GET /v1/ratings/stamps  (optional - get valid stamps)
          |
          v
POST /v1/ratings/trips/{trip_id}  { score: 5, stamps: [...] }
          |
          v
    +-----+----------+
    | DriverRating    |  trip_id, driver_id, crew_id, score, stamps
    +-----+----------+
          |
          v
Manager views ratings:
    GET /v1/ratings/drivers/{driver_id}
    GET /v1/ratings/drivers/{driver_id}/summary
          |
Driver views own summary:
    GET /v1/ratings/drivers/{driver_id}/summary
```

---

## Migration

The `ratings` schema is created automatically during app startup in `main.py`:

```python
async with AsyncSession(engine) as _s:
    await _s.exec("CREATE SCHEMA IF NOT EXISTS ratings")
    await _s.commit()
```

The `ratings.driver_ratings` table is created automatically by PSQLModel via `ensure_tables=True`.

Manual migration available at `migrations/create_driver_ratings_table.sql` for manual setup if needed.

---

## Files

| File | Purpose |
|------|---------|
| `shared/db/schemas/ratings/driver_ratings.py` | PSQLModel schema + RatingStamp constants |
| `shared/db/schemas/ratings/__init__.py` | Schema exports |
| `features/drivers/models/rating_models.py` | Pydantic request/response models |
| `features/drivers/routes/rating_router.py` | FastAPI router with 4 endpoints |
| `migrations/create_driver_ratings_table.sql` | SQL migration |
| `docs/DRIVER_RATING_SYSTEM_GUIDE.md` | This guide |
