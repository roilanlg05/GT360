# QR Code System - Guía de Implementación

## Arquitectura y Jerarquía

```
Organization
    └── Location (1 o muchas)
            └── QR Code (exactamente 1 por Location)
                    └── Airlines (múltiples, switch en UI)
                            └── Trips (consultables via QR)
```

### Reglas Fundamentales

| Regla | Descripción |
|-------|-------------|
| **1 QR = 1 Location** | Relación 1:1 estricta (UNIQUE constraint en DB) |
| **QR inmutable** | El UUID/URL del QR nunca cambia una vez creado |
| **Datos dinámicos** | Lo que cambia son los trips/airlines, no el QR |
| **CASCADE delete** | Si se elimina Location → QR se elimina automáticamente |
| **UUID del frontend** | El frontend genera el UUID con `crypto.randomUUID()` |

---

## Esquema de Base de Datos

### Tabla: `entities.qr_codes`

```sql
CREATE TABLE entities.qr_codes (
    id UUID PRIMARY KEY,                    -- UUID generado por frontend
    organization_id UUID NOT NULL,          -- FK → organizations (CASCADE)
    location_id UUID NOT NULL UNIQUE,       -- FK → locations (CASCADE) ← UNIQUE!
    name VARCHAR(100),                      -- Nombre legible (ej: "QR - Louisville")
    airlines JSONB,                         -- Airlines permitidas ["WN", "AA"] o null=todas
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- 'active' | 'disabled'
    metadata JSONB,                         -- Metadata adicional
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    last_scanned_at TIMESTAMPTZ,            -- Último escaneo (analytics)
    scan_count INTEGER NOT NULL DEFAULT 0   -- Contador de escaneos
);

-- Índices
CREATE INDEX idx_qr_codes_organization_id ON entities.qr_codes(organization_id);
CREATE INDEX idx_qr_codes_location_id ON entities.qr_codes(location_id);
CREATE INDEX idx_qr_codes_status ON entities.qr_codes(status);
CREATE INDEX idx_qr_codes_created_at ON entities.qr_codes(created_at);
```

### Constraint UNIQUE

```sql
-- Garantiza exactamente 1 QR por Location
ALTER TABLE entities.qr_codes
ADD CONSTRAINT uq_qr_codes_location_id UNIQUE (location_id);
```

---

## Endpoints

### 1. Obtener QR de una Location

```
GET /v1/organizations/{organization_id}/locations/{location_id}/qr-code
```

**Headers:**
```
Authorization: Bearer {token}
```

**Respuesta 200 (QR existe):**
```json
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "organization_id": "org-uuid",
    "location_id": "loc-uuid",
    "name": "QR - Louisville Airport",
    "airlines": ["WN", "AA"],
    "status": "active",
    "qr_url": "https://web.gt360.app/crew-lookup?qr=550e8400-e29b-41d4-a716-446655440000",
    "scan_count": 142,
    "last_scanned_at": "2026-01-22T10:30:00Z",
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-15T00:00:00Z"
}
```

**Respuesta 404 (QR no existe):**
```json
{
    "detail": "No QR code exists for this location. Use POST to create one."
}
```

---

### 2. Crear/Obtener QR (Idempotente)

```
POST /v1/organizations/{organization_id}/locations/{location_id}/qr-code
```

**Headers:**
```
Authorization: Bearer {token}
Content-Type: application/json
```

**Body:**
```json
{
    "id": "550e8400-e29b-41d4-a716-446655440000",  // UUID generado por frontend
    "name": "QR - Louisville Airport",             // Opcional
    "airlines": ["WN", "AA"],                      // Opcional (null = todas)
    "metadata": { "van_number": 1 }                // Opcional
}
```

**Respuesta 201 (QR creado):**
```json
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "organization_id": "org-uuid",
    "location_id": "loc-uuid",
    "name": "QR - Louisville Airport",
    "airlines": ["WN", "AA"],
    "status": "active",
    "qr_url": "https://web.gt360.app/crew-lookup?qr=550e8400-e29b-41d4-a716-446655440000",
    "scan_count": 0,
    "last_scanned_at": null,
    "created_at": "2026-01-22T12:00:00Z",
    "updated_at": "2026-01-22T12:00:00Z",
    "created": true  // ← Indica que se creó nuevo
}
```

**Respuesta 200 (QR ya existía):**
```json
{
    "id": "existing-qr-uuid",  // ← UUID del QR existente (NO el enviado)
    "organization_id": "org-uuid",
    "location_id": "loc-uuid",
    "name": "QR - Louisville Airport",
    "airlines": ["WN"],
    "status": "active",
    "qr_url": "https://web.gt360.app/crew-lookup?qr=existing-qr-uuid",
    "scan_count": 142,
    "last_scanned_at": "2026-01-22T10:30:00Z",
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-15T00:00:00Z",
    "created": false  // ← Indica que ya existía
}
```

---

### 3. Buscar Trip via QR (Público - Sin Auth)

```
GET /v1/trips/search/qr?qr_id={uuid}&airline={code}&date={YYYY-MM-DD}&flight={number}
```

**Parámetros:**

| Param | Requerido | Descripción |
|-------|-----------|-------------|
| `qr_id` | ✅ | UUID del QR code |
| `airline` | ✅ | Código de aerolínea (WN, AA, DL...) |
| `date` | ✅ | Fecha pickup YYYY-MM-DD (en timezone de location) |
| `flight` | ✅ | Número de vuelo |
| `type` | ❌ | Filtro opcional: `inbound`, `outbound`, `ground` |

**Ejemplo:**
```
GET /v1/trips/search/qr?qr_id=550e8400-e29b-41d4-a716-446655440000&airline=WN&date=2026-01-22&flight=1234
```

**Respuesta 200 (1 trip encontrado):**
```json
{
    "location": {
        "id": "loc-uuid",
        "name": "Louisville Airport",
        "timezone": "America/New_York"
    },
    "query": {
        "airline": "WN",
        "flight_number": "1234",
        "date": "2026-01-22",
        "type_filter": null
    },
    "data": {
        "id": "trip-uuid",
        "pick_up_time": "06:30",
        "pick_up_location": "Hotel Marriott - Lobby",
        "drop_off_location": "Louisville Airport - Terminal 1",
        "airline": "WN",
        "flight_number": "1234",
        "trip_type": "outbound",
        "status": "scheduled",
        "riders": {
            "pilots": 2,
            "flight_attendants": 4
        }
    },
    "multiple_results": false
}
```

**Respuesta 200 (múltiples trips encontrados):**
```json
{
    "location": {
        "id": "loc-uuid",
        "name": "Louisville Airport",
        "timezone": "America/New_York"
    },
    "query": {
        "airline": "WN",
        "flight_number": "1234",
        "date": "2026-01-22",
        "type_filter": null
    },
    "data": [
        {
            "id": "trip-1-uuid",
            "pick_up_time": "06:30",
            "trip_type": "outbound",
            "riders": { "pilots": 2, "flight_attendants": 4 },
            ...
        },
        {
            "id": "trip-2-uuid",
            "pick_up_time": "14:00",
            "trip_type": "inbound",
            "riders": { "pilots": 2, "flight_attendants": 3 },
            ...
        }
    ],
    "multiple_results": true,
    "message": "Found 2 trips. Please select one or add type filter (inbound/outbound/ground)."
}
```

**Errores posibles:**

| Status | Detalle |
|--------|---------|
| 400 | Invalid QR code ID format |
| 400 | Invalid date format. Use YYYY-MM-DD |
| 403 | QR code is disabled |
| 403 | Airline {X} is not allowed for this QR code |
| 404 | QR code not found |
| 404 | No trips found matching criteria |

---

## Flujos de Implementación Frontend

### Flujo 1: Manager crea Location → QR se inicializa

```typescript
// 1. Manager crea una Location (flujo existente)
const location = await createLocation({ name: "Louisville Airport", ... });

// 2. Inmediatamente después, inicializar el QR
const qrId = crypto.randomUUID();  // Frontend genera UUID

const qrResponse = await fetch(
    `/v1/organizations/${orgId}/locations/${location.id}/qr-code`,
    {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ id: qrId })
    }
);

const qrData = await qrResponse.json();
// qrData.created === true (nuevo) o false (ya existía)
// qrData.qr_url contiene la URL para generar el código QR
```

### Flujo 2: Manager ve/gestiona QR en Settings

```typescript
// Obtener QR existente de una Location
async function getLocationQR(orgId: string, locationId: string) {
    const response = await fetch(
        `/v1/organizations/${orgId}/locations/${locationId}/qr-code`,
        { headers: { 'Authorization': `Bearer ${token}` } }
    );

    if (response.status === 404) {
        // QR no existe, crear uno
        return await createQRCode(orgId, locationId);
    }

    return await response.json();
}

// UI muestra:
// - Imagen QR generada desde qr_url
// - Botón "Copiar URL"
// - Botón "Imprimir"
// - Stats: scan_count, last_scanned_at
```

### Flujo 3: Crew escanea QR

```typescript
// El QR contiene URL: https://web.gt360.app/crew-lookup?qr=550e8400-...
// La página crew-lookup extrae el qr_id de la URL

// 1. Crew selecciona/ingresa datos
interface CrewSearchParams {
    qrId: string;      // Extraído de URL
    airline: string;   // Seleccionado en UI (switch si hay múltiples)
    date: string;      // Seleccionado en datepicker
    flight: string;    // Ingresado manualmente
}

// 2. Buscar trip
async function searchTrip(params: CrewSearchParams) {
    const url = new URL('/v1/trips/search/qr', API_BASE);
    url.searchParams.set('qr_id', params.qrId);
    url.searchParams.set('airline', params.airline);
    url.searchParams.set('date', params.date);
    url.searchParams.set('flight', params.flight);

    const response = await fetch(url.toString());
    const data = await response.json();

    if (data.multiple_results) {
        // Mostrar lista para que crew seleccione
        return { type: 'multiple', trips: data.data };
    }

    // Trip único encontrado
    return { type: 'single', trip: data.data };
}

// 3. Mostrar resultado
function displayTripInfo(trip: TripData) {
    return {
        pickupTime: trip.pick_up_time,        // "06:30"
        pickupLocation: trip.pick_up_location, // "Hotel Marriott - Lobby"
        dropoffLocation: trip.drop_off_location,
        pilots: trip.riders.pilots,            // 2
        flightAttendants: trip.riders.flight_attendants  // 4
    };
}
```

---

## TypeScript Interfaces

```typescript
// QR Code
interface QRCode {
    id: string;
    organization_id: string;
    location_id: string;
    name: string | null;
    airlines: string[] | null;  // null = todas permitidas
    status: 'active' | 'disabled';
    qr_url: string;
    scan_count: number;
    last_scanned_at: string | null;
    created_at: string;
    updated_at: string;
}

interface QRCodeCreateResponse extends QRCode {
    created: boolean;  // true = nuevo, false = ya existía
}

// Crew Search
interface TripSearchResult {
    location: {
        id: string;
        name: string;
        timezone: string;
    };
    query: {
        airline: string;
        flight_number: string;
        date: string;
        type_filter: string | null;
    };
    data: TripData | TripData[];
    multiple_results: boolean;
    message?: string;
}

interface TripData {
    id: string;
    pick_up_time: string;      // "HH:MM" formato 24h
    pick_up_location: string;
    drop_off_location: string;
    airline: string;
    flight_number: string;
    trip_type: 'inbound' | 'outbound' | 'ground';
    status: 'scheduled' | 'en_route' | 'completed' | 'canceled';
    riders: {
        pilots: number;
        flight_attendants: number;
    };
}

// Create QR Request
interface CreateQRCodeRequest {
    id: string;                    // UUID generado por frontend
    name?: string;                 // Nombre opcional
    airlines?: string[];           // Filtro de airlines (null = todas)
    metadata?: Record<string, any>;
}
```

---

## Generación del Código QR (Frontend)

El backend NO genera la imagen QR. El frontend debe:

1. Usar `qr_url` del response
2. Generar imagen QR con librería (ej: `qrcode.react`, `qrcode`)

```typescript
import QRCode from 'qrcode.react';

function QRCodeDisplay({ qrUrl }: { qrUrl: string }) {
    return (
        <div className="qr-container">
            <QRCode
                value={qrUrl}
                size={256}
                level="H"  // Alta corrección de errores
            />
            <p className="qr-instruction">
                Scan to view pickup details
            </p>
        </div>
    );
}
```

---

## Migración SQL (Si se aplica desde cero)

```sql
-- 1. Crear tabla si no existe
CREATE TABLE IF NOT EXISTS entities.qr_codes (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES entities.organizations(id) ON DELETE CASCADE,
    location_id UUID NOT NULL REFERENCES entities.locations(id) ON DELETE CASCADE,
    name VARCHAR(100),
    airlines JSONB,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_scanned_at TIMESTAMPTZ,
    scan_count INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT uq_qr_codes_location_id UNIQUE (location_id)
);

-- 2. Crear índices
CREATE INDEX IF NOT EXISTS idx_qr_codes_organization_id ON entities.qr_codes(organization_id);
CREATE INDEX IF NOT EXISTS idx_qr_codes_status ON entities.qr_codes(status);
CREATE INDEX IF NOT EXISTS idx_qr_codes_created_at ON entities.qr_codes(created_at);

-- 3. Si ya existe la tabla sin UNIQUE, agregar constraint
-- NOTA: Primero verificar que no haya duplicados
SELECT location_id, COUNT(*)
FROM entities.qr_codes
GROUP BY location_id
HAVING COUNT(*) > 1;

-- Si hay duplicados, eliminarlos primero (mantener el más reciente)
DELETE FROM entities.qr_codes a
USING entities.qr_codes b
WHERE a.location_id = b.location_id
AND a.created_at < b.created_at;

-- Luego agregar constraint
ALTER TABLE entities.qr_codes
ADD CONSTRAINT uq_qr_codes_location_id UNIQUE (location_id);
```

---

## Checklist de Implementación

### Backend
- [x] Esquema `QRCode` con `UNIQUE` en `location_id`
- [x] Endpoint GET `/qr-code` (singular)
- [x] Endpoint POST `/qr-code` (get-or-create idempotente)
- [x] Endpoint GET `/trips/search/qr` (público)
- [x] Manejo de múltiples trips en búsqueda
- [x] Analytics: `scan_count`, `last_scanned_at`
- [x] Timezone incluido en respuesta

### Frontend
- [ ] Generar UUID con `crypto.randomUUID()` al crear QR
- [ ] Llamar POST `/qr-code` al crear Location
- [ ] Mostrar QR en sección Settings de Location
- [ ] Página `/crew-lookup` para escaneo público
- [ ] UI para seleccionar Airline/Date/Flight
- [ ] Manejo de múltiples resultados (lista seleccionable)
- [ ] Generar imagen QR con librería
- [ ] Botones: Copiar URL, Imprimir

---

## Notas de Seguridad

1. **UUID no adivinable**: El QR usa UUID v4, prácticamente imposible de enumerar
2. **Endpoint público limitado**: Solo devuelve datos mínimos del trip (no PII)
3. **Airlines restringidas**: Si `airlines` está configurado, solo esas pueden consultarse
4. **Status disabled**: QR puede desactivarse sin eliminar Location
5. **CASCADE delete**: Eliminar Location invalida automáticamente el QR
