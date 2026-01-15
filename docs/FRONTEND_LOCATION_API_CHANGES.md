# GUÍA COMPLETA PARA FRONTEND: CAMBIOS EN API DE LOCATIONS

**Fecha:** 2026-01-10
**Autor:** Backend Team
**Versión:** 2.0
**Estado:** ✅ IMPLEMENTADO Y DESPLEGADO

---

## 🚨 RESUMEN EJECUTIVO

El backend ha implementado **cambios críticos** en la gestión de locations que afectan directamente al frontend:

### Cambios Principales

| Cambio | Impacto | Acción Requerida |
|--------|---------|------------------|
| `location_id` ahora es **UUID** estricto | Alto | Validar UUIDs antes de enviar al backend |
| Nuevo campo **`timezone`** automático | Medio | Mostrar timezone en UI |
| Nuevo campo **`radio_zone`** para geofencing | Alto | Implementar UI de configuración |
| Nueva respuesta del endpoint `upload-trips` | Alto | Actualizar parsing de respuesta |
| Nuevos endpoints de **hoteles** | Alto | Implementar gestión de hoteles |
| Sistema de **validación de geofencing** | Alto | Implementar wizard de 2 pasos |

---

## 📋 CAMBIOS EN MODELOS DE DATOS

### 1. Location Model (Cambios)

#### ANTES (Versión 1.0)
```typescript
interface Location {
  id: string;                  // ⚠️ Era tratado como string
  organization_id: string;
  name: string;
  point: GeoJSONPoint | null;
  provider: string | null;
  created_at: string;
}
```

#### AHORA (Versión 2.0)
```typescript
interface Location {
  id: string;                          // ✅ UUID en formato string
  organization_id: string;             // ✅ UUID en formato string
  name: string;                        // Código del aeropuerto (ej: "SDF")
  point: GeoJSONPoint;                 // ✅ Ahora siempre presente
  address: string | null;              // 🆕 NUEVO: Dirección opcional
  radio_zone: number | null;           // 🆕 NUEVO: Radio del geofence en millas
  validation_status: ValidationStatus; // 🆕 NUEVO: Estado de validación
  provider: string | null;             // Proveedor API (ej: "flightaware")
  timezone: string;                    // 🆕 NUEVO: Timezone IANA (ej: "America/New_York")
  created_at: string;
}

type ValidationStatus =
  | "NEEDS_VALIDATION"  // Requiere configuración de geofence
  | "VALIDATED"         // Configurado y activo
  | "DISABLED";         // Deshabilitado

interface GeoJSONPoint {
  type: "Point";
  coordinates: [number, number];  // [longitude, latitude]
}
```

### 2. Hotel Model (NUEVO)

```typescript
interface Hotel {
  id: string;                          // UUID
  name: string;                        // Nombre del hotel
  location_id: string;                 // UUID de la location
  point: GeoJSONPoint | null;          // Coordenadas (null hasta validación)
  address: string | null;              // Dirección (opcional)
  radio_zone: number | null;           // Radio del geofence en metros
  validation_status: ValidationStatus; // Estado de validación
  validated_at: string | null;         // Timestamp de validación
  validated_by: string | null;         // UUID del usuario que validó
  created_at: string;
  updated_at: string;
}
```

### 3. Trip Model (Cambios en campos)

```typescript
interface Trip {
  id: string;                    // UUID
  location_id: string;           // ✅ Ahora validado como UUID
  pick_up_date: string;          // ISO date: "2025-11-01"
  pick_up_time: string;          // ✅ CAMBIO: Ahora incluye timezone de la location
  pick_up_location: string;
  drop_off_location: string;
  airline: string;
  flight_number: string;
  riders: {
    fligth: number;              // ⚠️ Typo intencional del backend
    in_fligth: number;           // ⚠️ Typo intencional del backend
  };
  trip_type: TripType | null;    // 🆕 NUEVO: Clasificación automática
  assigned_driver: string | null;
  started_at: string | null;
  picked_up_at: string | null;
  dropped_off_at: string | null;
  created_at: string;
  updated_at: string;
}

type TripType = "OUTBOUND" | "INBOUND";
```

---

## 🔄 CAMBIOS EN ENDPOINTS

### 1. POST `/v1/trips/upload-trips` (CAMBIOS CRÍTICOS)

#### Cambios en la Respuesta

**ANTES (Status: 200)**
```json
{
  "status": "ok",
  "uploaded_rows": 150,
  "location_id": "abc-123-def-456",
  "airport_code": "SDF",
  "trips": [...]
}
```

**AHORA (Status: 201 Created)**
```json
{
  "status": "ok",
  "uploaded_rows": 150,
  "location_id": "abc-123-def-456",
  "airport_code": "SDF",
  "trips": [...],
  "hotels": [                          // 🆕 NUEVO: Lista de hoteles extraídos
    {
      "id": "hotel-uuid-1",
      "name": "The Galt House",
      "location_id": "abc-123-def-456",
      "point": null,
      "radio_zone": null,
      "address": null,
      "validation_status": "NEEDS_VALIDATION",
      "validated_at": null,
      "validated_by": null,
      "created_at": "2026-01-10T10:00:00Z",
      "updated_at": "2026-01-10T10:00:00Z"
    }
  ]
}
```

#### Cambios en el Comportamiento

| Aspecto | ANTES | AHORA |
|---------|-------|-------|
| Status code | 200 OK | ✅ 201 Created |
| Campo `hotels` | ❌ No existía | ✅ Array de hoteles |
| `location.timezone` | ❌ Hardcoded UTC | ✅ Auto-detectado por coordenadas |
| `location.radio_zone` | ❌ No existía | ✅ Inicializado en 0.0 |
| `trip.pick_up_time` | Siempre UTC | ✅ Timezone de la location |
| `trip.trip_type` | ❌ No existía | ✅ Clasificado automáticamente |
| Duplicados de hoteles | Se insertaban duplicados | ✅ Prevenidos por constraint único |

#### ⚠️ ERROR ESPECÍFICO REPORTADO

**Error que el frontend está recibiendo:**
```
We couldn't validate the schedule: Connection.cursor() missing 1 required positional argument: 'query'
```

**Causa:** Este error ocurre cuando hay un problema con la conexión a la base de datos durante el procesamiento del archivo Excel. Específicamente, puede ocurrir cuando:

1. **El archivo Excel tiene un formato incorrecto** que causa una excepción durante el parsing
2. **El código de aeropuerto en el Excel no coincide** con el parámetro `airport` en la URL
3. **Hay múltiples aerolíneas en el archivo** y la organización no tiene plan premium

**Solución para el Frontend:**

```typescript
// ✅ Validar ANTES de enviar
async function uploadSchedule(file: File, airport: string, airline: string) {
  // 1. Validar que el archivo sea Excel
  const validExtensions = ['.xlsx', '.xlsm', '.xls'];
  const fileExt = file.name.toLowerCase().substring(file.name.lastIndexOf('.'));

  if (!validExtensions.includes(fileExt)) {
    throw new Error('El archivo debe ser formato Excel (.xlsx, .xlsm, .xls)');
  }

  // 2. Validar códigos IATA (3 letras)
  if (!/^[A-Z]{2,3}$/i.test(airport)) {
    throw new Error('Código de aeropuerto inválido (debe ser 2-3 letras)');
  }

  if (!/^[A-Z]{2}$/i.test(airline)) {
    throw new Error('Código de aerolínea inválido (debe ser 2 letras)');
  }

  // 3. Hacer el request
  const formData = new FormData();
  formData.append('file', file);

  const url = `/v1/trips/upload-trips?airport=${airport.toUpperCase()}&provider=flightaware&airline=${airline.toUpperCase()}`;

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json();

      // Parsear errores comunes
      if (error.detail.includes('Invalid Schedule')) {
        throw new Error(`El archivo no corresponde al aeropuerto ${airport}`);
      }

      if (error.detail.includes('mas de una aerolinea')) {
        throw new Error('Se detectaron múltiples aerolíneas. Necesitas un plan premium.');
      }

      if (error.detail.includes('Connection.cursor()')) {
        throw new Error('Error de base de datos. Verifica que el archivo Excel tenga el formato correcto y que el código de aeropuerto coincida con el archivo.');
      }

      throw new Error(error.detail || 'Error al subir el archivo');
    }

    const data = await response.json();

    // ✅ IMPORTANTE: Manejar la nueva estructura de respuesta
    return {
      locationId: data.location_id,
      airportCode: data.airport_code,
      tripsCount: data.uploaded_rows,
      trips: data.trips || [],
      hotels: data.hotels || [],  // 🆕 NUEVO
      pendingHotels: (data.hotels || []).filter(
        h => h.validation_status === 'NEEDS_VALIDATION'
      )
    };

  } catch (error) {
    console.error('Upload error:', error);
    throw error;
  }
}
```

---

### 2. PATCH `/v1/locations/{location_id}` (NUEVO)

Actualiza el geofence de una location.

#### Request
```typescript
PATCH /v1/locations/{location_id}
Authorization: Bearer {token}
Content-Type: application/json

{
  "point": {
    "type": "Point",
    "coordinates": [-85.7585, 38.1781]  // [lon, lat]
  },
  "radio_zone": 0.5,                    // Millas
  "address": "123 Main St",             // Opcional
  "validation_status": "VALIDATED"      // Opcional
}
```

#### Response (200 OK)
```json
{
  "status": "ok",
  "location": {
    "id": "abc-123",
    "name": "SDF",
    "point": {"type": "Point", "coordinates": [-85.7585, 38.1781]},
    "radio_zone": 0.5,
    "address": "123 Main St",
    "validation_status": "VALIDATED",
    "timezone": "America/Kentucky/Louisville",
    ...
  }
}
```

---

### 3. GET `/v1/locations/{location_id}/hotels` (NUEVO)

Obtiene la lista de hoteles de una location con paginación.

#### Request
```typescript
GET /v1/locations/{location_id}/hotels?name={search}&exact={bool}&skip={int}&limit={int}
Authorization: Bearer {token}

// Query params (todos opcionales)
- name: string        // Búsqueda por nombre
- exact: boolean      // true = match exacto, false = parcial (default: false)
- skip: number        // Offset para paginación (default: 0)
- limit: number       // Límite de resultados (default: 20, max: 100)
```

#### Response (200 OK)
```json
{
  "data": [
    {
      "id": "hotel-uuid",
      "name": "The Galt House",
      "location_id": "location-uuid",
      "point": null,
      "radio_zone": null,
      "address": null,
      "validation_status": "NEEDS_VALIDATION",
      "validated_at": null,
      "validated_by": null,
      "created_at": "2026-01-10T10:00:00Z",
      "updated_at": "2026-01-10T10:00:00Z"
    }
  ],
  "skip": 0,
  "limit": 20,
  "total": 15
}
```

---

### 4. PATCH `/v1/locations/{location_id}/hotels/{hotel_id}` (NUEVO)

Actualiza el geofence de un hotel.

#### Request
```typescript
PATCH /v1/locations/{location_id}/hotels/{hotel_id}
Authorization: Bearer {token}
Content-Type: application/json

{
  "point": {
    "type": "Point",
    "coordinates": [-85.7585, 38.1781]
  },
  "radio_zone": 300,                    // Metros (no millas)
  "address": "140 N 4th St, Louisville, KY",
  "validation_status": "VALIDATED"
}
```

#### Response (200 OK)
```json
{
  "status": "ok",
  "hotel": {
    "id": "hotel-uuid",
    "name": "The Galt House",
    "point": {"type": "Point", "coordinates": [-85.7585, 38.1781]},
    "radio_zone": 300,
    "address": "140 N 4th St, Louisville, KY",
    "validation_status": "VALIDATED",
    "validated_at": "2026-01-10T11:00:00Z",
    "validated_by": "user-uuid",
    ...
  }
}
```

---

## 🛠️ VALIDACIONES REQUERIDAS EN FRONTEND

### 1. Validación de UUIDs

Antes de llamar a cualquier endpoint que reciba `location_id`, `trip_id`, o `hotel_id`:

```typescript
function isValidUUID(uuid: string): boolean {
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  return uuidRegex.test(uuid);
}

// Uso
if (!isValidUUID(locationId)) {
  throw new Error('ID de location inválido');
}
```

### 2. Validación de Coordenadas GeoJSON

```typescript
interface GeoJSONPoint {
  type: "Point";
  coordinates: [number, number];  // [longitude, latitude]
}

function validateGeoJSONPoint(point: any): point is GeoJSONPoint {
  return (
    point &&
    point.type === "Point" &&
    Array.isArray(point.coordinates) &&
    point.coordinates.length === 2 &&
    typeof point.coordinates[0] === 'number' &&
    typeof point.coordinates[1] === 'number' &&
    point.coordinates[0] >= -180 && point.coordinates[0] <= 180 &&  // Longitude
    point.coordinates[1] >= -90 && point.coordinates[1] <= 90       // Latitude
  );
}
```

### 3. Validación de radio_zone

```typescript
// Para locations: máximo 1 milla
function validateLocationRadioZone(miles: number): boolean {
  return miles > 0 && miles <= 1.0;
}

// Para hoteles: máximo 2 millas (3218.688 metros)
function validateHotelRadioZone(meters: number): boolean {
  return meters > 0 && meters <= 3218.688;
}
```

---

## 🔄 NUEVO FLUJO: WIZARD DE 2 PASOS

El frontend debe implementar un wizard de 2 pasos para crear locations:

### Paso 1: Upload de Schedule

1. Usuario selecciona archivo Excel
2. Usuario selecciona aeropuerto, aerolínea y proveedor
3. Frontend llama a `POST /v1/trips/upload-trips`
4. Backend retorna:
   - `location_id` (guardar para Paso 2)
   - `trips[]` (mostrar resumen)
   - `hotels[]` (mostrar hoteles pendientes de validación)

### Paso 2: Configuración de Geofencing

1. **Configurar Location:**
   - Mostrar mapa con el punto de la location
   - Permitir ajustar `radio_zone` (0-1 milla)
   - Llamar a `PATCH /v1/locations/{location_id}`

2. **Validar Hoteles:**
   - Listar hoteles con `validation_status: "NEEDS_VALIDATION"`
   - Para cada hotel:
     - Buscar coordenadas (Google Maps API / Mapbox)
     - Ajustar radio (200-500 metros recomendado)
     - Llamar a `PATCH /v1/locations/{location_id}/hotels/{hotel_id}`

**Referencia:** Ver [docs/WIZARD_TWO_STEP_FRONTEND_GUIDE.md](./WIZARD_TWO_STEP_FRONTEND_GUIDE.md) para implementación completa.

---

## 🌍 MANEJO DE TIMEZONES

### Cambio Importante

El backend ahora maneja automáticamente los timezones basándose en las coordenadas de la location:

```typescript
// ANTES: Todo era UTC
pick_up_time: "04:55:00+00:00"

// AHORA: Timezone de la location
pick_up_time: "04:55:00-05:00"  // America/New_York (Eastern Time)
```

### Implementación en Frontend

```typescript
// Mostrar hora local al usuario
function displayLocalTime(trip: Trip, location: Location) {
  const time = trip.pick_up_time;  // "04:55:00-05:00"
  const timezone = location.timezone;  // "America/New_York"

  // Usar librería como date-fns-tz o luxon
  const localTime = formatInTimeZone(
    new Date(`${trip.pick_up_date}T${time}`),
    timezone,
    'hh:mm a'
  );

  return `${localTime} ${timezone}`;  // "4:55 AM America/New_York"
}
```

---

## 📊 TIPOS TYPESCRIPT COMPLETOS

```typescript
// ============ ENUMS ============

export enum ValidationStatus {
  NEEDS_VALIDATION = "NEEDS_VALIDATION",
  VALIDATED = "VALIDATED",
  DISABLED = "DISABLED"
}

export enum TripType {
  OUTBOUND = "OUTBOUND",  // Hotel → Airport
  INBOUND = "INBOUND"     // Airport → Hotel
}

// ============ MODELS ============

export interface Location {
  id: string;
  organization_id: string;
  name: string;
  point: GeoJSONPoint;
  address: string | null;
  radio_zone: number | null;
  validation_status: ValidationStatus;
  provider: string | null;
  timezone: string;
  created_at: string;
}

export interface Hotel {
  id: string;
  name: string;
  location_id: string;
  point: GeoJSONPoint | null;
  address: string | null;
  radio_zone: number | null;
  validation_status: ValidationStatus;
  validated_at: string | null;
  validated_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface Trip {
  id: string;
  location_id: string;
  pick_up_date: string;
  pick_up_time: string;
  pick_up_location: string;
  drop_off_location: string;
  airline: string;
  flight_number: string;
  riders: {
    fligth: number;
    in_fligth: number;
  };
  trip_type: TripType | null;
  assigned_driver: string | null;
  started_at: string | null;
  picked_up_at: string | null;
  dropped_off_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface GeoJSONPoint {
  type: "Point";
  coordinates: [number, number];  // [longitude, latitude]
}

// ============ API REQUESTS ============

export interface UploadTripsRequest {
  airport: string;    // Query param
  provider: string;   // Query param
  airline: string;    // Query param
  file: File;         // FormData body
}

export interface UpdateLocationRequest {
  point?: GeoJSONPoint;
  radio_zone?: number;
  address?: string;
  validation_status?: ValidationStatus;
}

export interface UpdateHotelRequest {
  point?: GeoJSONPoint;
  radio_zone?: number;
  address?: string;
  validation_status?: ValidationStatus;
}

// ============ API RESPONSES ============

export interface UploadTripsResponse {
  status: "ok";
  uploaded_rows: number;
  location_id: string;
  airport_code: string;
  trips: Trip[];
  hotels: Hotel[];
}

export interface GetHotelsResponse {
  data: Hotel[];
  skip: number;
  limit: number;
  total: number;
}

export interface UpdateLocationResponse {
  status: "ok";
  location: Location;
}

export interface UpdateHotelResponse {
  status: "ok";
  hotel: Hotel;
}
```

---

## ⚠️ BREAKING CHANGES CHECKLIST

- [ ] Actualizar parsing de respuesta de `POST /v1/trips/upload-trips`
- [ ] Añadir manejo del array `hotels` en la respuesta
- [ ] Validar UUIDs antes de llamar a endpoints
- [ ] Implementar gestión de hoteles (listado, edición)
- [ ] Mostrar campo `timezone` en la UI de locations
- [ ] Implementar configuración de `radio_zone` para locations
- [ ] Implementar configuración de `radio_zone` para hoteles
- [ ] Actualizar manejo de `pick_up_time` con timezone awareness
- [ ] Mostrar `trip_type` (OUTBOUND/INBOUND) en la UI
- [ ] Implementar wizard de 2 pasos (Schedule → Geofencing)
- [ ] Actualizar manejo de errores con nuevos códigos (400, 404, 422)
- [ ] Añadir validaciones de GeoJSON en formularios
- [ ] Implementar búsqueda de hoteles por nombre

---

## 📞 SOPORTE

Si encuentras problemas con estos cambios:

1. Verifica que estás usando las últimas versiones de los tipos TypeScript
2. Revisa la [documentación del wizard](./WIZARD_TWO_STEP_FRONTEND_GUIDE.md)
3. Consulta [BUGFIX_UUID_VALIDATION.md](./BUGFIX_UUID_VALIDATION.md) para problemas de validación
4. Reporta bugs en el canal de Slack `#backend-support`

---

**Última actualización:** 2026-01-10
**Versión del Backend:** 2.0.0
**Commit:** 2e1b818
