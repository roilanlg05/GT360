# 🎉 Preview Persistence - Cross-Device Synchronization

**Date:** 2026-01-19
**Status:** ✅ IMPLEMENTED & DEPLOYED
**Feature:** Filter preview results now persist in the database and sync across all devices

---

## 🎯 Objective

**Problem Solved:**
- **Before:** Device A creates a preview → stored in localStorage → Device B shows blank preview
- **After:** Device A creates a preview → saved to backend database → Device B retrieves and shows the same preview

**Goal:** Allow users to create filter previews on one device and view them on any other device without having to recreate the preview.

---

## 📊 What Changed in the Backend

### 1. New Database Table: `filter_previews`

```sql
CREATE TABLE trips.filter_previews (
    id UUID PRIMARY KEY,
    location_id UUID REFERENCES entities.locations(id),
    airline VARCHAR(10),
    config JSONB,         -- FilterRequest configuration
    result JSONB,         -- Preview result (changes, exclusions, summary)
    created_at TIMESTAMPTZ,

    UNIQUE(location_id, airline)  -- Only one preview per location+airline
);
```

**Key Features:**
- ✅ One preview per location+airline (UPSERT behavior)
- ✅ Automatically cleared when filters are applied
- ✅ Stores complete preview data (changes, exclusions, summary)

---

### 2. Modified Endpoint: POST `/filters/preview`

**Before:**
```python
# Calculate preview
result = await service.preview(location_uuid, airline, filters)
return result  # ← Just return, don't save
```

**After:**
```python
# Calculate preview
result = await service.preview(location_uuid, airline, filters)

# Save preview to database (replace existing if any)
await save_filter_preview(session, location_uuid, airline, filters, result)

return result
```

**Behavior:**
- Creates/updates preview automatically
- New preview replaces old one (UPSERT)
- Transparent to frontend - no changes needed in frontend preview call

---

### 3. New Endpoint: GET `/filters/preview/last`

**URL:** `/v1/locations/{location_id}/airlines/{airline}/trips/filters/preview/last`

**Response:**
```typescript
{
  preview_id: string;
  location_id: string;
  airline: string;
  config: {
    reduce: { enabled: boolean, minutes_to_reduce: number, ... },
    combine: { enabled: boolean, min_gap: number, ... },
    expand: { enabled: boolean, min_gap: number, ... },
  };
  result: {
    location_id: string;
    airline: string;
    changes: TripChange[];
    exclusions: FilterExclusion[];
    summary: { reduce: number, combine: number, expand: number };
    total_trips_evaluated: number;
    eligible_trips: number;
  };
  created_at: string;
}
```

**Returns `null` if:**
- No preview has been created yet
- Preview was cleared after applying filters

---

### 4. Modified Endpoint: POST `/filters/apply`

**Before:**
```python
result = await service.apply(location_uuid, airline, filters)
return result
```

**After:**
```python
result = await service.apply(location_uuid, airline, filters)

# Clear saved preview since it's now applied
await clear_filter_preview(session, location_uuid, airline)

return result
```

**Behavior:**
- Automatically clears preview after applying filters
- Prevents showing stale preview data
- Both devices will see empty preview after refresh

---

## 🎨 Frontend Integration

### TypeScript Interfaces

```typescript
interface FilterPreviewSaved {
  preview_id: string;
  location_id: string;
  airline: string;
  config: FilterRequest;
  result: FilterPreviewResult;
  created_at: string;
}

interface FilterPreviewResult {
  location_id: string;
  airline: string;
  changes: TripChange[];
  exclusions: FilterExclusion[];
  summary: {
    reduce: number;
    combined: number;
    expanded: number;
  };
  total_trips_evaluated: number;
  eligible_trips: number;
}
```

---

### Frontend Workflow

#### 1. On Page Load (Any Device)

```typescript
const loadSavedPreview = async () => {
  try {
    const response = await fetch(
      `/api/v1/locations/${locationId}/airlines/${airline}/trips/filters/preview/last`
    );

    if (response.ok) {
      const saved: FilterPreviewSaved | null = await response.json();

      if (saved) {
        // Display preview from any device
        setPreview(saved.result);
        setPreviewConfig(saved.config);
        setPreviewCreatedAt(saved.created_at);

        console.log('✅ Loaded saved preview from backend');
      } else {
        // No preview exists yet
        setPreview(null);
        console.log('ℹ️  No preview saved yet');
      }
    }
  } catch (error) {
    console.error('Error loading saved preview:', error);
  }
};

// Call on page mount
useEffect(() => {
  loadSavedPreview();
}, [locationId, airline]);
```

---

#### 2. Creating Preview (Device A)

```typescript
const createPreview = async (filters: FilterRequest) => {
  try {
    const response = await fetch(
      `/api/v1/locations/${locationId}/airlines/${airline}/trips/filters/preview`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(filters)
      }
    );

    if (response.ok) {
      const result: FilterPreviewResult = await response.json();

      // Display preview
      setPreview(result);

      // Backend automatically saved it - Device B can now retrieve it
      console.log('✅ Preview created and saved to backend');
    }
  } catch (error) {
    console.error('Error creating preview:', error);
  }
};
```

**No changes needed** - the endpoint now automatically saves the preview!

---

#### 3. Viewing Preview (Device B)

Device B just calls `loadSavedPreview()` on mount (same as step 1) and gets the preview created by Device A.

```typescript
// On Device B page load
useEffect(() => {
  loadSavedPreview();  // Will retrieve preview created on Device A
}, []);
```

---

#### 4. Applying Filters (Any Device)

```typescript
const applyFilters = async (filters: FilterRequest) => {
  try {
    const response = await fetch(
      `/api/v1/locations/${locationId}/airlines/${airline}/trips/filters/apply`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(filters)
      }
    );

    if (response.ok) {
      const result: FilterApplyResult = await response.json();

      // Clear preview from UI
      setPreview(null);

      // Backend automatically cleared the saved preview
      // Device B will also see null when it refreshes
      console.log('✅ Filters applied, preview cleared');
    }
  } catch (error) {
    console.error('Error applying filters:', error);
  }
};
```

**No changes needed** - the endpoint now automatically clears the saved preview!

---

## 🔄 Complete User Flow

### Scenario: User with Multiple Devices

**Step 1: Device A (Desktop)**
```
User opens filter page
→ Configures filters (reduce: 25 min)
→ Clicks "Preview Changes"
→ Backend saves preview to database
→ Preview shows 354 changes
```

**Step 2: Device B (Mobile)**
```
User opens filter page on phone
→ Frontend calls GET /filters/preview/last
→ Backend returns saved preview
→ Preview shows same 354 changes
→ User reviews and decides to apply
```

**Step 3: Device B applies filters**
```
User clicks "Apply Changes"
→ Backend applies filters
→ Backend automatically clears saved preview
→ Preview disappears
```

**Step 4: Device A refreshes**
```
Frontend calls GET /filters/preview/last
→ Backend returns null (preview was cleared)
→ Preview is empty (correct behavior)
```

---

## ✅ Benefits

1. **Cross-device sync:** Preview visible on all devices
2. **No manual sync:** Backend handles everything automatically
3. **No stale data:** Preview cleared when filters applied
4. **Backward compatible:** Existing preview calls work unchanged
5. **Simple frontend:** Just add one GET request on page load

---

## 📝 Frontend Implementation Checklist

### Required Changes:

- [ ] **Add TypeScript interface** `FilterPreviewSaved`
- [ ] **Add function** `loadSavedPreview()` that calls GET `/filters/preview/last`
- [ ] **Call** `loadSavedPreview()` on page mount (useEffect)
- [ ] **Update** preview display logic to handle saved previews
- [ ] **Handle null response** gracefully (no preview exists)

### Optional Improvements:

- [ ] Show timestamp of when preview was created
- [ ] Add "Refresh Preview" button to create new preview
- [ ] Show indicator if preview is from another device
- [ ] Auto-refresh preview every N seconds (polling)

---

## 🧪 Testing Verification

All tests passed successfully:

```
✅ Device A can create previews
✅ Device B can retrieve previews created by Device A
✅ Data integrity is maintained across devices
✅ Previews are correctly cleared when filters are applied
✅ Cleared previews return null (no stale data)
```

**Test Results:**
- ✅ Preview created: 354 changes
- ✅ Preview retrieved: 354 changes (matches)
- ✅ Preview cleared after apply
- ✅ Returns null after clearing

---

## 📊 Backend Files Modified

1. ✅ **NEW:** `shared/db/schemas/trips/filter_previews.py` - Database schema
2. ✅ **MODIFIED:** `shared/db/schemas/__init__.py` - Export FilterPreview
3. ✅ **MODIFIED:** `features/trips/models/filter_models.py` - Add FilterPreviewSaved model
4. ✅ **MODIFIED:** `features/trips/routes/trips_router.py`:
   - Added `save_filter_preview()` helper
   - Added `clear_filter_preview()` helper
   - Modified `preview_filters()` to save preview
   - Modified `apply_filters()` to clear preview
   - Added `get_last_preview()` endpoint
5. ✅ **NEW:** `migrations/add_filter_previews_table.sql` - Database migration

---

## 🚀 Deployment Status

**Backend:**
- ✅ Database table created
- ✅ Code deployed to Docker container
- ✅ All tests passing
- ✅ Container restarted and running

**Endpoints Available:**
- ✅ `POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/preview` - Creates and saves preview
- ✅ `GET /v1/locations/{location_id}/airlines/{airline}/trips/filters/preview/last` - Retrieves saved preview
- ✅ `POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/apply` - Applies and clears preview

---

## 💡 Frontend Example: Complete Implementation

```typescript
// State
const [preview, setPreview] = useState<FilterPreviewResult | null>(null);
const [previewConfig, setPreviewConfig] = useState<FilterRequest | null>(null);
const [previewTimestamp, setPreviewTimestamp] = useState<string | null>(null);

// Load saved preview on mount
useEffect(() => {
  const loadPreview = async () => {
    try {
      const res = await fetch(
        `/api/v1/locations/${locationId}/airlines/${airline}/trips/filters/preview/last`
      );

      if (res.ok) {
        const saved: FilterPreviewSaved | null = await res.json();
        if (saved) {
          setPreview(saved.result);
          setPreviewConfig(saved.config);
          setPreviewTimestamp(saved.created_at);
        }
      }
    } catch (error) {
      console.error('Error loading preview:', error);
    }
  };

  loadPreview();
}, [locationId, airline]);

// Create new preview
const handlePreview = async (filters: FilterRequest) => {
  const res = await fetch(
    `/api/v1/locations/${locationId}/airlines/${airline}/trips/filters/preview`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(filters)
    }
  );

  if (res.ok) {
    const result: FilterPreviewResult = await res.json();
    setPreview(result);
    setPreviewConfig(filters);
    setPreviewTimestamp(new Date().toISOString());
  }
};

// Apply filters
const handleApply = async (filters: FilterRequest) => {
  const res = await fetch(
    `/api/v1/locations/${locationId}/airlines/${airline}/trips/filters/apply`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(filters)
    }
  );

  if (res.ok) {
    setPreview(null);
    setPreviewConfig(null);
    setPreviewTimestamp(null);
  }
};
```

---

## 📞 Questions or Issues?

If you encounter any problems integrating this feature, check:

1. ✅ Are you calling GET `/filters/preview/last` on page load?
2. ✅ Are you handling null responses correctly?
3. ✅ Are you using the correct location_id and airline?
4. ✅ Is the user authenticated (manager role)?

**Last Updated:** 2026-01-19
**Backend Status:** ✅ Deployed and Tested
**Frontend Status:** ⏳ Pending Integration
