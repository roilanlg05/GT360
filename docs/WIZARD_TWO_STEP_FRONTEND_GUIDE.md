# WIZARD DE DOS PASOS - GUÍA COMPLETA PARA FRONTEND

## Resumen Ejecutivo

Este documento describe la implementación de un wizard de dos pasos para configurar locations y geofencing:

| Paso | Descripción | Resultado |
|------|-------------|-----------|
| **1** | Upload de horario | Location creada, trips importados, hoteles extraídos |
| **2** | Configuración de geofences | Hoteles validados, aeropuerto configurado, zona de visibilidad |

---

# PASO 1: UPLOAD DE HORARIO

## 1.1 Endpoint Principal

```
POST /v1/trips/upload-trips?airport={code}&provider={provider}&airline={airline}
Content-Type: multipart/form-data
Authorization: Bearer {jwt_token}
```

### Parámetros Query (REQUERIDOS)

| Parámetro | Tipo | Descripción | Ejemplo |
|-----------|------|-------------|---------|
| `airport` | string | Código IATA del aeropuerto | `SDF`, `JFK`, `LAX` |
| `provider` | string | Identificador del proveedor API | `flightaware`, `cirium` |
| `airline` | string | Código IATA de aerolínea | `WN`, `AA`, `DL` |

### Body (multipart/form-data)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `file` | File | Archivo Excel (.xlsx, .xlsm, .xls) |

### Autenticación

- **Role requerido**: `manager`
- **Header**: `Authorization: Bearer {jwt_token}`

---

## 1.2 Formato del Archivo Excel

### Nombre de Hoja
La hoja DEBE llamarse exactamente: **`Schedule`** (case-sensitive)

### Estructura Requerida

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Fila 1-40: Búsqueda de "CITY: {code}"                                          │
│            Ejemplo: CITY: SDF                                                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│ Header Row (contiene DATE, PICK UP, DROP OFF):                                  │
│                                                                                 │
│ DATE    │ PICK UP           │ DROP OFF          │ RIDERS                       │
│         │ FROM   │ LOCATION │ TO     │ LOCATION │                              │
├─────────┼────────┼──────────┼────────┼──────────┼──────────────────────────────┤
│ Nov 01  │ WN 2453│ SDF      │ Hotel A│ SDF      │ Flight (2)/ InFlight (4)     │
│ Nov 01  │ Hotel B│ SDF      │ WN 2668│ SDF      │ InFlight (3)                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Columnas Requeridas

| Columna | Subheader | Descripción |
|---------|-----------|-------------|
| `DATE` | - | Fecha del pickup |
| `PICK UP` | `FROM` | Origen (vuelo o hotel) |
| `PICK UP` | `LOCATION` | Código de ubicación |
| `DROP OFF` | `TO` | Destino (vuelo o hotel) |
| `DROP OFF` | `LOCATION` | Código de ubicación |
| `RIDERS` | - | Cantidad de pasajeros (opcional) |
| `DEPARTMENT` | - | Departamento (opcional) |

### Formatos de Fecha Soportados

```
01-Nov-2025    (DD-Mmm-YYYY)
2025-11-01     (YYYY-MM-DD)
11/01/2025     (MM/DD/YYYY)
01/11/2025     (DD/MM/YYYY)
Nov 01, 2025   (Mmm DD, YYYY)
```

### Formatos de Vuelo Soportados

```
WN 2453           → airline: "WN", flight: "2453"
WN 2453-01        → airline: "WN", flight: "2453-01"
WN 2668-01 Nov    → airline: "WN", flight: "2668-01", month: Nov
WN 4285-16 04:45  → airline: "WN", flight: "4285-16", time: 04:45
```

### Marcadores de Fin de Archivo

El parser detiene la lectura cuando encuentra:
- `"END OF TRANSPORTATION SCHEDULE"`
- `"THIS SCHEDULE REPRESENTS"`

---

## 1.3 Respuesta del Endpoint

### Respuesta Exitosa (201 Created)

```typescript
interface UploadTripsResponse {
  status: "ok";
  uploaded_rows: number;
  location_id: string;      // UUID de la location creada/existente
  airport_code: string;     // Código del aeropuerto
  trips: Trip[];            // Primeros 50 trips creados
  hotels: Hotel[];          // Hoteles extraídos automáticamente
}

interface Trip {
  id: string;               // UUID
  pick_up_date: string;     // "2025-11-01"
  pick_up_time: string;     // "04:55:00"
  pick_up_location: string; // "AIRPORT" o nombre de hotel
  drop_off_location: string;
  airline: string;          // "WN"
  flight_number: string;    // "2453"
  riders: {
    fligth: number;         // Nota: typo intencional en backend
    in_fligth: number;
  };
  location_id: string;
  assigned_driver: string | null;
  started_at: string | null;
  picked_up_at: string | null;
  dropped_off_at: string | null;
  created_at: string;
  updated_at: string;
}

interface Hotel {
  id: string;
  name: string;
  location_id: string;
  point: GeoJSONPoint | null;     // null hasta validación
  radio_zone: number | null;       // null hasta validación
  address: string | null;
  validation_status: "NEEDS_VALIDATION" | "VALIDATED" | "DISABLED";
  validated_at: string | null;
  validated_by: string | null;
  created_at: string;
  updated_at: string;
}

interface GeoJSONPoint {
  type: "Point";
  coordinates: [number, number];  // [longitude, latitude]
}
```

### Respuestas de Error

| Código | Descripción | Causa |
|--------|-------------|-------|
| `400` | Formato de archivo inválido | Extensión no es .xlsx, .xlsm, .xls |
| `404` | Aeropuerto no encontrado | Código de aeropuerto no existe |
| `404` | Organización no encontrada | JWT inválido o usuario sin org |
| `422` | Error de procesamiento | Archivo mal formado, múltiples aerolíneas, etc. |

### Ejemplo de Error 422

```json
{
  "detail": "Se ha detectado mas de una aerolinea en el archivo, necesitas una subscripcion para cargar mas de una aerolinea"
}
```

---

## 1.4 Ejemplo de Implementación TypeScript

```typescript
async function uploadSchedule(
  file: File,
  airport: string,
  provider: string,
  airline: string,
  token: string
): Promise<UploadTripsResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const url = new URL('/v1/trips/upload-trips', API_BASE);
  url.searchParams.set('airport', airport);
  url.searchParams.set('provider', provider);
  url.searchParams.set('airline', airline);

  const response = await fetch(url.toString(), {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Upload failed');
  }

  return response.json();
}
```

---

## 1.5 Lo que Sucede Automáticamente en Paso 1

1. **Location**: Se crea automáticamente si no existe
   - Nombre = código del aeropuerto
   - Coordenadas = lat/lon del aeropuerto
   - Timezone = detectado automáticamente
   - Visibilidad = 40 millas (default)

2. **Trips**: Se insertan en batch (chunks de 5000)
   - Timezone ajustado a la location
   - Constraint único previene duplicados

3. **Hoteles**: Se extraen de pickup/dropoff locations
   - Status inicial: `NEEDS_VALIDATION`
   - Sin coordenadas ni radio (requiere Paso 2)

---

# PASO 2: CONFIGURACIÓN DE GEOFENCES

Después del upload exitoso, el frontend debe guiar al usuario para configurar:

1. **Zona de Visibilidad** (Location level)
2. **Geofence del Aeropuerto**
3. **Geofences de Hoteles** (validación)
4. **Configuración General** (opcional)

---

## 2.1 Zona de Visibilidad de Location

### Concepto
Define el radio máximo donde se trackean usuarios. Usuarios fuera de esta zona NO son visibles en el sistema.

### Endpoint GET

```
GET /v1/locations/{location_id}/visibility
Authorization: Bearer {token}
```

**Respuesta:**
```typescript
interface VisibilityResponse {
  id: string;
  name: string;
  organization_id: string;
  point: GeoJSONPoint;
  visibility_radius: number;        // metros (default: 64373.76)
  visibility_radius_miles: number;  // millas (default: 40)
  max_visibility_radius: number;    // 64373.76 metros
  max_visibility_radius_miles: number; // 40 millas
  visibility_modified_at: string | null;
  visibility_modified_by: string | null;
}
```

### Endpoint PATCH

```
PATCH /v1/locations/{location_id}/visibility?visibility_radius={meters}
Authorization: Bearer {token}
```

**Parámetros:**
| Parámetro | Tipo | Rango | Descripción |
|-----------|------|-------|-------------|
| `visibility_radius` | number | 0 < x ≤ 64373.76 | Radio en metros |

**Conversión útil:**
```typescript
const METERS_PER_MILE = 1609.344;
const milesToMeters = (miles: number) => miles * METERS_PER_MILE;
const metersToMiles = (meters: number) => meters / METERS_PER_MILE;
```

---

## 2.2 Geofence del Aeropuerto

### Concepto
El aeropuerto tiene coordenadas fijas (master data). Solo se puede ajustar el radio del geofence.

### Endpoint GET

```
GET /v1/airports/{airport_id}
Authorization: Bearer {token}
```

**Respuesta:**
```typescript
interface AirportResponse {
  id: string;
  code: string;           // "SDF"
  name: string;           // "Louisville International"
  latitude: number;       // Solo lectura
  longitude: number;      // Solo lectura
  country_code: string;
  zone_code: string;
  radio_zone: number;     // metros (default: 1609.344 = 1 milla)
  last_modified_at: string | null;
  last_modified_by: string | null;
}
```

### Endpoint PATCH (Solo Radio)

```
PATCH /v1/airports/{airport_id}/geofence
Authorization: Bearer {token}
Content-Type: application/json

{
  "radio_zone": 1609.344
}
```

**Body:**
```typescript
interface AirportGeofenceUpdate {
  radio_zone: number;  // 0 < x ≤ 3218.688 metros (2 millas max)
}
```

**Límites:**
- Mínimo: > 0 metros
- Máximo: 3218.688 metros (2 millas)
- Default: 1609.344 metros (1 milla)

---

## 2.3 Validación de Hoteles

### Concepto
Los hoteles extraídos del archivo tienen status `NEEDS_VALIDATION`. El manager debe asignarles coordenadas y radio para activar el geofencing.

### Flujo de Estados

```
NEEDS_VALIDATION → VALIDATED → DISABLED
       ↑              ↓           ↓
       └──────────────┴───────────┘
                (enable)
```

### Endpoint: Listar Hoteles Pendientes

```
GET /v1/locations/{location_id}/hotels/pending-validation
Authorization: Bearer {token}
```

**Respuesta:**
```typescript
interface HotelPendingValidation {
  id: string;
  name: string;
  location_id: string;
  address: string | null;
  created_at: string;
}
```

### Endpoint: Listar Todos los Hoteles

```
GET /v1/locations/{location_id}/hotels?status={status}
Authorization: Bearer {token}
```

**Query params:**
| Parámetro | Valores | Descripción |
|-----------|---------|-------------|
| `status` | `NEEDS_VALIDATION`, `VALIDATED`, `DISABLED` | Filtro opcional |

**Respuesta:**
```typescript
interface HotelValidationResponse {
  id: string;
  name: string;
  location_id: string;
  address: string | null;
  point: GeoJSONPoint | null;
  radio_zone: number | null;
  validation_status: "NEEDS_VALIDATION" | "VALIDATED" | "DISABLED";
  validated_at: string | null;
  validated_by: string | null;
}
```

### Endpoint: Validar Hotel

```
POST /v1/locations/{location_id}/hotels/{hotel_id}/validate
Authorization: Bearer {token}
Content-Type: application/json

{
  "point": {
    "type": "Point",
    "coordinates": [-85.7585, 38.1781]
  },
  "radio_zone": 500,
  "address": "123 Main St, Louisville, KY"
}
```

**Body:**
```typescript
interface HotelValidateRequest {
  point: GeoJSONPoint;           // REQUERIDO
  radio_zone: number;            // REQUERIDO, 0 < x ≤ 3218.688
  address?: string;              // Opcional, max 250 chars
}
```

**Límites de radio_zone:**
- Mínimo: > 0 metros
- Máximo: 3218.688 metros (2 millas)
- Recomendado: 200-500 metros para hoteles urbanos

### Endpoint: Actualizar Geofence de Hotel Validado

```
PATCH /v1/locations/{location_id}/hotels/{hotel_id}/geofence
Authorization: Bearer {token}
Content-Type: application/json

{
  "point": {
    "type": "Point",
    "coordinates": [-85.7585, 38.1781]
  },
  "radio_zone": 300
}
```

**Body:**
```typescript
interface HotelGeofenceUpdate {
  point?: GeoJSONPoint;    // Opcional
  radio_zone?: number;     // Opcional, 0 < x ≤ 3218.688
}
```

**Nota:** El hotel debe tener status `VALIDATED` para actualizar su geofence.

### Endpoint: Deshabilitar Hotel

```
POST /v1/locations/{location_id}/hotels/{hotel_id}/disable
Authorization: Bearer {token}
```

Cambia status a `DISABLED`. No generará eventos de geofencing.

### Endpoint: Habilitar Hotel

```
POST /v1/locations/{location_id}/hotels/{hotel_id}/enable
Authorization: Bearer {token}
```

**Requisito:** Hotel debe tener `point` y `radio_zone` válidos.

Cambia status de `DISABLED` a `VALIDATED`.

---

## 2.4 Configuración General de Geofencing

### Concepto
Configuración a nivel de organización que afecta todos los geofences.

### Endpoint GET

```
GET /v1/organization/geofence-settings
Authorization: Bearer {token}
```

**Respuesta:**
```typescript
interface GeofenceSettingsResponse {
  id: string;
  organization_id: string;
  dwell_interval_minutes: number;      // default: 5
  min_consecutive_readings: number;    // default: 3
  cooldown_seconds: number;            // default: 30
  created_at: string;
  updated_at: string;
  updated_by: string | null;
}
```

### Endpoint PATCH

```
PATCH /v1/organization/geofence-settings
Authorization: Bearer {token}
Content-Type: application/json

{
  "dwell_interval_minutes": 10,
  "min_consecutive_readings": 5,
  "cooldown_seconds": 60
}
```

**Body (todos opcionales, al menos uno requerido):**
```typescript
interface GeofenceSettingsUpdate {
  dwell_interval_minutes?: number;      // 1-60
  min_consecutive_readings?: number;    // 1-10
  cooldown_seconds?: number;            // 10-300
}
```

### Explicación de Configuraciones

| Setting | Rango | Default | Descripción |
|---------|-------|---------|-------------|
| `dwell_interval_minutes` | 1-60 | 5 | Cada cuántos minutos emitir evento DWELL |
| `min_consecutive_readings` | 1-10 | 3 | Lecturas GPS consecutivas para confirmar ENTER/EXIT (anti-jitter) |
| `cooldown_seconds` | 10-300 | 30 | Tiempo mínimo entre eventos opuestos (previene ping-pong) |

---

# EVENTOS WEBSOCKET

## Conexión WebSocket para Geofencing

```
ws://host/ws/org?organization_id={org_id}&token={jwt_token}
```

## Tipos de Eventos

### Evento ENTER
```typescript
{
  type: "geofence_enter",
  actor_type: "driver" | "crew",
  actor_id: string,
  target_type: "hotel" | "airport",
  target_id: string,
  target_name: string,
  location_id: string,
  timestamp: string,
  distance: number          // metros al centro del geofence
}
```

### Evento DWELL
```typescript
{
  type: "geofence_dwell",
  actor_type: "driver" | "crew",
  actor_id: string,
  target_type: "hotel" | "airport",
  target_id: string,
  target_name: string,
  location_id: string,
  dwell_minutes: number,    // minutos desde ENTER
  timestamp: string
}
```

### Evento EXIT
```typescript
{
  type: "geofence_exit",
  actor_type: "driver" | "crew",
  actor_id: string,
  target_type: "hotel" | "airport",
  target_id: string,
  target_name: string,
  location_id: string,
  total_time_inside_seconds: number,
  timestamp: string
}
```

### Eventos de Visibilidad
```typescript
// Usuario salió de zona de visibilidad
{
  type: "user_outside_visibility",
  actor_type: "driver" | "crew",
  actor_id: string,
  location_id: string,
  location_name: string,
  distance_to_center: number,
  visibility_radius: number,
  timestamp: string
}

// Usuario entró a zona de visibilidad
{
  type: "user_inside_visibility",
  actor_type: "driver" | "crew",
  actor_id: string,
  location_id: string,
  location_name: string,
  distance_to_center: number,
  timestamp: string
}
```

---

# FLUJO COMPLETO DEL WIZARD

```
┌─────────────────────────────────────────────────────────────────┐
│                        PASO 1                                   │
├─────────────────────────────────────────────────────────────────┤
│  1. Usuario selecciona:                                         │
│     - Aeropuerto (dropdown de códigos IATA)                     │
│     - Aerolínea (dropdown de códigos IATA)                      │
│     - Proveedor API (dropdown)                                  │
│     - Archivo Excel                                             │
│                                                                 │
│  2. Frontend llama: POST /v1/trips/upload-trips                 │
│                                                                 │
│  3. Backend retorna:                                            │
│     - location_id (guardar para Paso 2)                         │
│     - trips[] (mostrar resumen)                                 │
│     - hotels[] (mostrar lista pendiente)                        │
│                                                                 │
│  4. Mostrar resumen:                                            │
│     - "X trips importados"                                      │
│     - "X hoteles detectados (pendientes de validación)"         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        PASO 2                                   │
├─────────────────────────────────────────────────────────────────┤
│  SECCIÓN A: Zona de Visibilidad                                 │
│  ─────────────────────────────                                  │
│  - GET /v1/locations/{location_id}/visibility                   │
│  - Mostrar mapa con círculo de 40 millas (default)              │
│  - Slider para ajustar (0-40 millas)                            │
│  - PATCH para guardar cambios                                   │
│                                                                 │
│  SECCIÓN B: Geofence del Aeropuerto                             │
│  ───────────────────────────────────                            │
│  - GET /v1/airports/{airport_id}                                │
│  - Mostrar pin en mapa (coordenadas fijas)                      │
│  - Slider para radio (0-2 millas, default 1 milla)              │
│  - PATCH /v1/airports/{id}/geofence para guardar                │
│                                                                 │
│  SECCIÓN C: Validación de Hoteles                               │
│  ─────────────────────────────────                              │
│  - GET /v1/locations/{location_id}/hotels/pending-validation    │
│  - Para cada hotel:                                             │
│    - Buscar dirección en Google Maps/Mapbox                     │
│    - Obtener coordenadas                                        │
│    - Ajustar radio (recomendado 200-500m)                       │
│    - POST .../hotels/{hotel_id}/validate                        │
│                                                                 │
│  SECCIÓN D: Configuración General (Opcional)                    │
│  ──────────────────────────────────────────                     │
│  - GET /v1/organization/geofence-settings                       │
│  - Mostrar configuración actual                                 │
│  - Permitir ajustes avanzados                                   │
│  - PATCH para guardar                                           │
└─────────────────────────────────────────────────────────────────┘
```

---

# CONSTANTES IMPORTANTES

```typescript
// Conversiones
const METERS_PER_MILE = 1609.344;

// Límites de Location
const MAX_VISIBILITY_RADIUS_METERS = 64373.76;  // 40 millas
const DEFAULT_VISIBILITY_RADIUS_METERS = 64373.76;

// Límites de Airport/Hotel
const MAX_GEOFENCE_RADIUS_METERS = 3218.688;    // 2 millas
const DEFAULT_AIRPORT_RADIUS_METERS = 1609.344; // 1 milla

// Geofence Settings
const MIN_DWELL_INTERVAL = 1;
const MAX_DWELL_INTERVAL = 60;
const DEFAULT_DWELL_INTERVAL = 5;

const MIN_CONSECUTIVE_READINGS = 1;
const MAX_CONSECUTIVE_READINGS = 10;
const DEFAULT_CONSECUTIVE_READINGS = 3;

const MIN_COOLDOWN_SECONDS = 10;
const MAX_COOLDOWN_SECONDS = 300;
const DEFAULT_COOLDOWN_SECONDS = 30;

// Validation Status
type HotelValidationStatus = "NEEDS_VALIDATION" | "VALIDATED" | "DISABLED";
```

---

# EJEMPLO COMPLETO DE IMPLEMENTACIÓN

```typescript
// ==========================================
// PASO 1: Upload de Schedule
// ==========================================

interface WizardStep1State {
  airport: string;
  airline: string;
  provider: string;
  file: File | null;
}

async function executeStep1(state: WizardStep1State, token: string) {
  if (!state.file) throw new Error('File required');

  const formData = new FormData();
  formData.append('file', state.file);

  const url = `/v1/trips/upload-trips?airport=${state.airport}&provider=${state.provider}&airline=${state.airline}`;

  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` },
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail);
  }

  const data: UploadTripsResponse = await response.json();

  return {
    locationId: data.location_id,
    tripsCount: data.uploaded_rows,
    pendingHotels: data.hotels.filter(h => h.validation_status === 'NEEDS_VALIDATION'),
  };
}

// ==========================================
// PASO 2A: Configurar Visibilidad
// ==========================================

async function getVisibility(locationId: string, token: string) {
  const response = await fetch(`/v1/locations/${locationId}/visibility`, {
    headers: { 'Authorization': `Bearer ${token}` },
  });
  return response.json();
}

async function updateVisibility(locationId: string, radiusMeters: number, token: string) {
  const response = await fetch(
    `/v1/locations/${locationId}/visibility?visibility_radius=${radiusMeters}`,
    {
      method: 'PATCH',
      headers: { 'Authorization': `Bearer ${token}` },
    }
  );
  return response.json();
}

// ==========================================
// PASO 2B: Configurar Aeropuerto
// ==========================================

async function getAirport(airportId: string, token: string) {
  const response = await fetch(`/v1/airports/${airportId}`, {
    headers: { 'Authorization': `Bearer ${token}` },
  });
  return response.json();
}

async function updateAirportGeofence(airportId: string, radiusMeters: number, token: string) {
  const response = await fetch(`/v1/airports/${airportId}/geofence`, {
    method: 'PATCH',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ radio_zone: radiusMeters }),
  });
  return response.json();
}

// ==========================================
// PASO 2C: Validar Hoteles
// ==========================================

async function getPendingHotels(locationId: string, token: string) {
  const response = await fetch(
    `/v1/locations/${locationId}/hotels/pending-validation`,
    { headers: { 'Authorization': `Bearer ${token}` } }
  );
  return response.json();
}

async function validateHotel(
  locationId: string,
  hotelId: string,
  coordinates: [number, number],  // [lon, lat]
  radiusMeters: number,
  address: string | null,
  token: string
) {
  const body: HotelValidateRequest = {
    point: {
      type: 'Point',
      coordinates,
    },
    radio_zone: radiusMeters,
  };

  if (address) {
    body.address = address;
  }

  const response = await fetch(
    `/v1/locations/${locationId}/hotels/${hotelId}/validate`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    }
  );
  return response.json();
}

// ==========================================
// PASO 2D: Configuración General (Opcional)
// ==========================================

async function getGeofenceSettings(token: string) {
  const response = await fetch('/v1/organization/geofence-settings', {
    headers: { 'Authorization': `Bearer ${token}` },
  });
  return response.json();
}

async function updateGeofenceSettings(
  settings: Partial<GeofenceSettingsUpdate>,
  token: string
) {
  const response = await fetch('/v1/organization/geofence-settings', {
    method: 'PATCH',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(settings),
  });
  return response.json();
}
```

---

# NOTAS IMPORTANTES

1. **GeoJSON**: Las coordenadas son `[longitude, latitude]`, NO `[lat, lon]`

2. **Typo en riders**: El backend usa `"fligth"` y `"in_fligth"` (typo intencional, no cambiar)

3. **Timezone**: Se detecta automáticamente de las coordenadas del aeropuerto

4. **Hoteles duplicados**: El backend previene duplicados por (name, location_id)

5. **Airport ID**: Para obtener el airport_id, buscar por código en la tabla de aeropuertos o usar el endpoint de búsqueda

6. **Validación visual**: Usar un mapa para que el usuario:
   - Vea la zona de visibilidad como círculo exterior
   - Vea el geofence del aeropuerto
   - Pueda buscar y ubicar hoteles en el mapa
   - Ajuste radios visualmente

---

# ENDPOINTS ADICIONALES ÚTILES

## Buscar Aeropuerto por Código

```
GET /v1/airports?code={airport_code}
Authorization: Bearer {token}
```

Usar para obtener el `airport_id` necesario para el Paso 2B.

## Listar Locations de la Organización

```
GET /v1/locations
Authorization: Bearer {token}
```

Útil para mostrar locations existentes antes del wizard.

---

# CHECKLIST DE IMPLEMENTACIÓN

## Paso 1
- [ ] Formulario con selección de aeropuerto (dropdown códigos IATA)
- [ ] Formulario con selección de aerolínea (dropdown códigos IATA)
- [ ] Formulario con selección de proveedor API
- [ ] Input para archivo Excel (.xlsx, .xlsm, .xls)
- [ ] Validación de formato de archivo en frontend
- [ ] Llamada a `POST /v1/trips/upload-trips`
- [ ] Manejo de errores (400, 404, 422)
- [ ] Mostrar resumen de trips importados
- [ ] Mostrar lista de hoteles pendientes
- [ ] Guardar `location_id` para Paso 2

## Paso 2
- [ ] Mapa interactivo con Mapbox/Google Maps
- [ ] Círculo de zona de visibilidad (ajustable)
- [ ] Pin de aeropuerto con radio ajustable
- [ ] Lista de hoteles pendientes con búsqueda en mapa
- [ ] Validación individual de hoteles
- [ ] Panel de configuración general (opcional)
- [ ] Persistir cambios con endpoints PATCH/POST
