# Frontend Generates QR ID - Architecture Documentation

## 📋 Overview

**Important**: The QR code system has been designed so that **the frontend generates the QR ID** (UUID), not the backend.

This document explains the architecture decision and how backend should integrate.

---

## 🏗️ Architecture Decision

### **Why Frontend Generates the QR ID?**

1. ✅ **Immediate Display**: QR code visible to users instantly, no waiting for backend
2. ✅ **Simplified Backend**: No management endpoints needed initially
3. ✅ **No Dependencies**: Works even if management endpoints are TODO
4. ✅ **User Control**: User sees the exact UUID they need to activate
5. ✅ **Persistent**: UUID stored in localStorage, consistent across sessions

### **Traditional Flow (Not Used)**
```
❌ User creates location
❌ Backend auto-creates QR code in DB
❌ Backend returns QR ID to frontend
❌ Frontend displays QR code
```

### **Our Flow (Implemented)**
```
✅ User opens /dashboard/crew-members
✅ Frontend generates UUID using crypto.randomUUID()
✅ Frontend stores UUID in localStorage
✅ Frontend displays QR code immediately
✅ Frontend shows SQL with generated UUID
✅ User copies SQL and runs it in backend
✅ QR code becomes active in backend
```

---

## 🔄 Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND (React/Next.js)                                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. User opens: /dashboard/crew-members                    │
│                                                             │
│  2. Component runs:                                         │
│     const [qrId] = useState(() => {                        │
│       const stored = localStorage.getItem('crew-qr-id');   │
│       if (stored) return stored;                           │
│                                                             │
│       const newQrId = crypto.randomUUID();                 │
│       localStorage.setItem('crew-qr-id', newQrId);         │
│       return newQrId;                                       │
│     });                                                     │
│                                                             │
│  3. QR Code displays with:                                 │
│     URL: https://web.gt360.app/crew-lookup?qr={qrId}       │
│     Visual: QRCodeSVG component generates image            │
│                                                             │
│  4. Setup instructions box shows:                          │
│     ┌─────────────────────────────────────────────┐        │
│     │ INSERT INTO entities.qr_codes (             │        │
│     │     id,                                     │        │
│     │     organization_id,                        │        │
│     │     location_id,                            │        │
│     │     name,                                   │        │
│     │     status                                  │        │
│     │ ) VALUES (                                  │        │
│     │     'c743011f-cc55-416b-ba08-8ea903bdfc0e', │  ← UUID│
│     │     '{your-org-uuid}',                      │        │
│     │     '{your-location-uuid}',                 │        │
│     │     'Van 1',                                │        │
│     │     'active'                                │        │
│     │ );                                          │        │
│     └─────────────────────────────────────────────┘        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ User copies SQL
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ BACKEND (FastAPI/PostgreSQL)                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. User runs SQL INSERT with frontend-generated UUID      │
│                                                             │
│  2. Database creates record:                                │
│     entities.qr_codes {                                     │
│       id: 'c743011f-cc55-416b-ba08-8ea903bdfc0e'  ← From   │
│       organization_id: '...'                       frontend │
│       location_id: '...'                                    │
│       name: 'Van 1'                                         │
│       status: 'active'                                      │
│       scan_count: 0                                         │
│       created_at: NOW()                                     │
│     }                                                       │
│                                                             │
│  3. Public endpoints now work:                              │
│     GET /v1/crew-lookup/config?qr_id={qrId}                │
│     → Returns: airlines, location_name, etc.                │
│                                                             │
│     GET /v1/trips/search/qr?qr_id={qrId}&...               │
│     → Returns: trip with van time                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ Crew member scans QR
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ CREW MEMBER (Mobile Browser)                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Scans QR code in van                                   │
│     Opens: https://web.gt360.app/crew-lookup?qr={qrId}     │
│                                                             │
│  2. Page loads → Calls backend:                            │
│     GET /v1/crew-lookup/config?qr_id={qrId}                │
│                                                             │
│  3. Fills form:                                            │
│     - Airline: WN                                          │
│     - Date: 2026-01-22                                     │
│     - Flight: 1234                                         │
│                                                             │
│  4. Submits → Calls backend:                               │
│     GET /v1/trips/search/qr?qr_id={qrId}&...               │
│                                                             │
│  5. Sees result:                                           │
│     Van Time: 2:30 PM                                      │
│     Pickup: PHX Airport                                     │
│     Pilots: 2, FAs: 5                                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔑 Key Implementation Details

### **Frontend Code**

**Location**: `/src/app/(main)/dashboard/crew-members/page.tsx`

```typescript
export default function CrewMembersPage() {
  // AUTO-GENERATE QR ID (client-side)
  const [qrId] = useState(() => {
    if (typeof window === 'undefined') return 'generating...';

    // Try to get existing QR ID from localStorage
    const stored = localStorage.getItem('crew-qr-id');
    if (stored) return stored;

    // Generate new UUID for QR code
    const newQrId = crypto.randomUUID();
    localStorage.setItem('crew-qr-id', newQrId);
    return newQrId;
  });

  const hasQRCode = true; // Always show QR (generated client-side)

  return (
    <QRCodeGenerator qrId={qrId} orgName="Bentine" />
  );
}
```

**QR Code Component**: `/src/app/(main)/dashboard/crew-members/_components/qr-code-generator.tsx`

```typescript
export function QRCodeGenerator({ qrId }: { qrId: string }) {
  const qrUrl = `${window.location.origin}/crew-lookup?qr=${qrId}`;

  return (
    <Card>
      {/* QR Code SVG */}
      <QRCodeSVG value={qrUrl} size={256} level="H" />

      {/* Setup Instructions with pre-filled UUID */}
      <div className="instructions">
        <code>{`
INSERT INTO entities.qr_codes (
    id,
    organization_id,
    location_id,
    name,
    status
) VALUES (
    '${qrId}',  ← Frontend-generated UUID
    '{your-org-uuid}',
    '{your-location-uuid}',
    'Van 1',
    'active'
);
        `}</code>
      </div>
    </Card>
  );
}
```

---

## 📝 Backend Integration Instructions

### **What Backend Needs to Do**

The backend does **NOT** need to generate QR IDs. Instead:

1. **Accept the UUID from frontend** in the SQL INSERT
2. **Validate the UUID** when public endpoints are called
3. **Return configuration** based on that UUID

### **Database Schema** (Already Implemented)

```sql
CREATE TABLE entities.qr_codes (
    id UUID PRIMARY KEY,  -- ← Frontend provides this
    organization_id UUID NOT NULL REFERENCES entities.organizations(id),
    location_id UUID NOT NULL REFERENCES entities.locations(id),
    name VARCHAR(100),
    airlines JSONB,
    status VARCHAR(20) DEFAULT 'active',
    scan_count INTEGER DEFAULT 0,
    last_scanned_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### **Manual QR Creation** (Current Method)

```sql
-- User copies this from frontend, replaces org/location UUIDs, and runs
INSERT INTO entities.qr_codes (
    id,                                        -- Frontend-generated
    organization_id,                           -- User fills
    location_id,                               -- User fills
    name,                                      -- User chooses
    status
) VALUES (
    'c743011f-cc55-416b-ba08-8ea903bdfc0e',   -- From frontend
    '550e8400-e29b-41d4-a716-446655440000',   -- User's org
    '123e4567-e89b-12d3-a456-426614174000',   -- User's location
    'Van 1 - Louisville',
    'active'
);
```

### **Future: Management Endpoint** (Optional, When Implemented)

If you want to add a management endpoint later:

```python
@router.post("/v1/organizations/{org_id}/locations/{loc_id}/qr-codes")
async def create_qr_code(
    org_id: UUID,
    loc_id: UUID,
    qr_id: UUID,  # ← Frontend sends this
    name: str,
    airlines: Optional[List[str]] = None
):
    """
    Create QR code with frontend-provided UUID

    Frontend generates the UUID and sends it here.
    Backend just creates the record.
    """
    qr_code = QRCode(
        id=qr_id,  # ← Use frontend UUID
        organization_id=org_id,
        location_id=loc_id,
        name=name,
        airlines=airlines,
        status="active"
    )

    await qr_code.save()
    return {"id": qr_id, "status": "active"}
```

---

## ⚠️ Important Considerations

### **UUID Collision Risk**

**Q**: What if two users generate the same UUID?

**A**: Virtually impossible.
- UUID v4 has 122 random bits
- Collision probability: 1 in 5.3 × 10³⁶
- More likely to win the lottery 7 times in a row

### **localStorage Persistence**

**Q**: What if user clears localStorage?

**A**: New UUID is generated, but:
- Old QR still works (backend has the record)
- User can see the old UUID in the SQL they ran
- Or backend can list QR codes: `GET /v1/organizations/{org}/locations/{loc}/qr-codes`

### **Multiple QR Codes per Location**

**Q**: Can one location have multiple QR codes?

**A**: Yes!
- User clears localStorage → New UUID generated
- Runs new SQL INSERT → Second QR created
- Both QR codes work simultaneously
- Useful for: Van 1, Van 2, Van 3, etc.

---

## ✅ Validation Rules

### **Frontend Validation**
```typescript
// UUID format: XXXXXXXX-XXXX-4XXX-YXXX-XXXXXXXXXXXX
const isValidUUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(qrId);
```

### **Backend Validation**
```python
# In /v1/crew-lookup/config endpoint
qr_code = await QRCode.find_one({"id": qr_id})

if not qr_code:
    raise HTTPException(status_code=404, detail="QR code not found")

if qr_code.status != "active":
    raise HTTPException(status_code=403, detail="QR code is disabled")

return {
    "qr_id": str(qr_code.id),
    "location_id": str(qr_code.location_id),
    "airlines": qr_code.airlines or [],
    # ...
}
```

---

## 📊 Comparison: Old vs New Flow

### **Traditional Backend-First**
```
User → Backend API → Generate UUID → Return to Frontend → Display QR
         ↓
    Requires management endpoints
    More backend complexity
    Slower UX (wait for API)
```

### **Our Frontend-First**
```
User → Frontend → Generate UUID → Display QR
                         ↓
                    Show SQL with UUID
                    User runs SQL
                         ↓
                    Backend ready
```

**Advantages**:
- ✅ Instant QR display
- ✅ No API calls needed initially
- ✅ Works even if endpoints TODO
- ✅ User has full control
- ✅ Simpler backend integration

---

## 🔐 Security Considerations

### **Is it safe for frontend to generate UUIDs?**

✅ **Yes**, because:

1. **UUIDs are not secrets**: They're public identifiers
2. **Backend validates**: All requests check if QR exists and is active
3. **No privilege escalation**: UUID alone doesn't grant access
4. **Same as user-generated IDs**: Like YouTube video IDs or Stripe invoice IDs

### **What backend must validate:**

```python
# In every public endpoint
qr_code = await validate_qr_code(qr_id)

# Check:
if qr_code.status != "active":
    raise HTTPException(403, "QR disabled")

if request.airline not in (qr_code.airlines or []):
    raise HTTPException(403, "Airline not allowed")

# Only return data scoped to that QR's location
trips = await Trip.find({
    "location_id": qr_code.location_id,
    "airline": request.airline,
    # ...
})
```

---

## 🎯 Summary for Backend Team

### **What You Need to Know**

1. **Frontend generates the QR ID** using `crypto.randomUUID()`
2. **Frontend shows SQL** with that UUID to the user
3. **User runs the SQL** to create the record in `entities.qr_codes`
4. **Backend validates** the UUID when endpoints are called
5. **No backend UUID generation** is needed

### **What You Need to Do**

1. ✅ **Accept frontend-provided UUIDs** in `entities.qr_codes.id`
2. ✅ **Validate UUIDs** in public endpoints (already implemented)
3. ✅ **Return correct data** scoped to the QR's location (already implemented)
4. ⏳ **Optional**: Create management endpoint that accepts frontend UUID

### **What You Don't Need to Do**

- ❌ Generate UUIDs in backend
- ❌ Auto-create QR codes when location is created
- ❌ Implement UUID generation logic
- ❌ Worry about UUID collisions (statistically impossible)

---

## 📞 Questions?

If backend team has questions about this approach:

1. **Why not backend-generate UUIDs?**
   - Requires management endpoints (TODO)
   - Slower UX (API round-trip)
   - More complex integration

2. **Is this secure?**
   - Yes, UUIDs are public identifiers
   - Backend validates all requests
   - No different from other user-generated IDs

3. **What if we want to auto-create QR codes?**
   - Can implement later with management endpoint
   - Frontend can call POST with its generated UUID
   - Or backend can ignore frontend UUID and generate its own

4. **Can we change this later?**
   - Yes, it's backwards compatible
   - Existing QRs will continue working
   - New QRs can use backend-generated UUIDs

---

## 🚀 Next Steps

1. **For Frontend**: Already implemented and working ✅
2. **For Backend**: No changes needed, current implementation works ✅
3. **For Users**: Copy SQL from UI, run it, QR works ✅
4. **Future**: Optionally implement management endpoints

---

**TL;DR**: Frontend generates UUIDs, shows SQL, user runs SQL, backend validates. Simple, fast, works.
