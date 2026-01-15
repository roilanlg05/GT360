# Bug Fix: Missing Status Column in Trips Table

**Date:** 2026-01-14
**Severity:** Critical (500 Internal Server Error)
**Status:** ✅ Fixed

## Problem Summary

The backend was returning 500 errors for all trips-related endpoints, causing CORS errors to appear in the frontend. The root cause was a missing database column that existed in the Python model but not in the actual database table.

## Root Cause

**Error Message:**
```
asyncpg.exceptions.UndefinedColumnError: column trips.status does not exist
```

### Why This Happened

1. The `status` field was added to the Trip model in [shared/db/schemas/trips/trips.py:133-137](shared/db/schemas/trips/trips.py#L133-L137):
   ```python
   status: str = Column(
       default=TripStatus.SCHEDULED,
       nullable=False,
       index=True
   )
   ```

2. However, the database migration was **never executed**, so the column didn't exist in the actual PostgreSQL table.

3. When any endpoint tried to query the trips table, PostgreSQL threw an error because it couldn't find the `status` column.

## Affected Endpoints

All endpoints that query the trips table were failing:
- `GET /v1/locations/{location_id}/trips` ❌
- `GET /v1/locations/{location_id}/trips?airline={airline}` ❌
- WebSocket connections to `/ws/trips` ❌

## Solution Applied

### 1. Added Missing Column
```sql
ALTER TABLE trips.trips
ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'scheduled';
```

### 2. Created Index
```sql
CREATE INDEX IF NOT EXISTS idx_trips_status ON trips.trips(status);
```

### 3. Verified Schema
```bash
docker exec postgres psql -U gt360 -d gt360 -c "\d trips.trips" | grep status
```

**Result:**
```
status | text | not null | 'scheduled'::text
"idx_trips_status" btree (status)
```

## Migration File

Created migration file: [migrations/001_add_status_column_to_trips.sql](migrations/001_add_status_column_to_trips.sql)

## Impact

### Before Fix
- ❌ All trips endpoints returned 500 errors
- ❌ Frontend showed CORS errors (caused by 500 responses)
- ❌ WebSocket connections failed
- ❌ Users couldn't view any trip data

### After Fix
- ✅ Trips endpoints return data correctly
- ✅ No more CORS errors
- ✅ WebSocket connections work
- ✅ Users can view and manage trips

## Lessons Learned

1. **Schema Mismatch:** Always ensure database migrations are applied after model changes
2. **CORS Confusion:** 500 errors often appear as CORS errors in the browser because error responses don't include CORS headers
3. **Import Errors First:** Before checking CORS, always verify the backend is actually running (in this case, it wasn't due to import errors)

## Related Fixes

This fix session also resolved an earlier issue:
- Fixed `ImportError: cannot import name 'TripStatus'` by adding it to [shared/db/schemas/__init__.py](shared/db/schemas/__init__.py)

## Testing

To verify the fix:
```bash
# Check column exists
docker exec postgres psql -U gt360 -d gt360 -c "\d trips.trips" | grep status

# Check backend logs
docker logs gt360 --tail 50

# Test endpoint (requires valid token)
curl https://api.gt360.app/v1/locations/{location_id}/trips?limit=1 \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Status Values

The `status` column supports these values (defined in `TripStatus` class):
- `scheduled` - Trip is scheduled (default)
- `canceled` - Trip has been canceled
- `en_route` - Trip is currently in progress
