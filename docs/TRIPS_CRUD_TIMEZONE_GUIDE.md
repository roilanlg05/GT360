# Trips CRUD Endpoints - Timezone Guide

**Version:** 1.0
**Last Updated:** 2026-02-11
**Backend:** GT360 API

---

## Overview

Esta guía documenta los endpoints de creación y actualización de trips, con énfasis especial en el manejo correcto de timezones.

**REGLA FUNDAMENTAL:** Todos los tiempos de trips (`pick_up_time`) deben enviarse en el **timezone local de la location** (aeropuerto), NO en UTC.

---

## Table of Contents

1. [Timezone Management](#1-timezone-management)
2. [Upload Trips (Bulk)](#2-upload-trips-bulk)
3. [Create Trip (Single)](#3-create-trip-single)
4. [Update Trip](#4-update-trip)
5. [Examples](#5-examples)
6. [Common Mistakes](#6-common-mistakes)

---

## 1. Timezone Management

### 1.1 How Timezones Work

Cada location (aeropuerto) tiene un timezone específico basado en sus coordenadas geográficas:

```
Location Creation:
1. Se registra el código del aeropuerto (ej: "SDF")
2. Se obtienen las coordenadas del aeropuerto
3. Se determina el timezone usando timezonefinder (ej: "America/New_York")
4. El timezone se guarda en location.timezone
```

### 1.2 Timezone Assignment

Cuando se crea o actualiza un trip:

```python
# 1. Se recibe el pick_up_time del cliente (hora local, sin tzinfo)
pick_up_time = "14:30:00"  # 2:30 PM hora local

# 2. Se obtiene el timezone de la location
location_tz = ZoneInfo(location.timezone)  # "America/New_York"

# 3. Se asigna el timezone al tiempo
pick_up_time_aware = pick_up_time.replace(tzinfo=location_tz)
# Resultado: 14:30:00-05:00 (EST) o 14:30:00-04:00 (EDT según fecha)

# 4. PostgreSQL almacena en UTC internamente
# 14:30:00-05:00 → 19:30:00+00:00 UTC
```

### 1.3 Important Concepts

| Concepto | Descripción |
|----------|-------------|
| **Naive time** | Tiempo sin timezone info (ej: `14:30:00`) |
| **Aware time** | Tiempo con timezone info (ej: `14:30:00-05:00`) |
| **Local time** | Hora en el timezone de la location |
| **UTC time** | Hora en UTC (almacenada en DB) |

**SIEMPRE enviar naive times en hora local. El backend asigna el timezone correcto.**

---

## 2. Upload Trips (Bulk)

### 2.1 Endpoint

```http
POST /v1/trips/upload-trips
Authorization: Bearer <manager_token>
Content-Type: multipart/form-data

Form Data:
- airport: string (Airport code, ej: "SDF")
- provider: string (Provider name)
- airline: string (Airline name)
- file: Excel file (.xlsx, .xlsm, .xls)
```

### 2.2 Excel File Format

El archivo Excel debe contener los siguientes campos:

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| Date | Date | Pickup date | 2026-02-15 |
| Time | Time | **Pickup time in LOCAL timezone** | 14:30:00 |
| Pickup | String | Pickup location name | The Galt House |
| Dropoff | String | Dropoff location name | SDF |
| Airline | String | Airline name | Southwest Airlines |
| Flight | String | Flight number | WN 1234 |
| Pilots | Integer | Number of pilots | 2 |
| FA | Integer | Number of flight attendants | 2 |

### 2.3 Timezone Handling

**CRÍTICO:** Los tiempos en el Excel deben estar en el timezone LOCAL del aeropuerto.

```
Ejemplo: Aeropuerto SDF (Louisville, KY)
Timezone: America/New_York (EST/EDT)

✅ CORRECTO:
Date: 2026-02-15
Time: 14:30:00
→ Se interpreta como: 2026-02-15 14:30:00 America/New_York
→ Se almacena como: 2026-02-15 19:30:00 UTC (si es EST)

❌ INCORRECTO:
Date: 2026-02-15
Time: 19:30:00 (pensando que es UTC)
→ Se interpreta como: 2026-02-15 19:30:00 America/New_York
→ Se almacena como: 2026-02-16 00:30:00 UTC
→ ¡El trip aparecerá 5 horas más tarde de lo esperado!
```

### 2.4 Process Flow

```
1. Upload Excel file
2. Parse rows (fecha, hora, locations, etc.)
3. Buscar/crear location con timezone automático
4. Para cada trip:
   a. parse_time → naive time
   b. assign location.timezone → aware time
   c. PostgreSQL convierte a UTC
5. Bulk insert a DB
6. Enviar evento WebSocket con trips creados
```

### 2.5 Response

```json
{
  "status": "ok",
  "uploaded_rows": 150,
  "location_id": "550e8400-e29b-41d4-a716-446655440000",
  "airport_code": "SDF",
  "trips": [
    {
      "id": "trip-uuid-1",
      "pick_up_date": "2026-02-15",
      "pick_up_time": "14:30:00-05:00",
      "pick_up_location": "The Galt House",
      "drop_off_location": "SDF",
      "airline": "Southwest Airlines",
      "flight_number": "WN 1234",
      "trip_type": "outbound",
      "status": "scheduled",
      ...
    }
  ],
  "hotels": [...],
  "auto_apply": {
    "applied": true,
    "reason": "Preset auto-applied",
    "trips_affected": 45,
    "days_processed": 5
  }
}
```

---

## 3. Create Trip (Single)

### 3.1 Endpoint

```http
POST /v1/locations/{location_id}/trips
Authorization: Bearer <manager_token>
Content-Type: application/json

{
  "pick_up_date": "2026-02-15",
  "pick_up_time": "14:30:00",
  "pick_up_location": "The Galt House",
  "drop_off_location": "SDF",
  "assigned_driver": "driver-uuid" (optional),
  "airline": "Southwest Airlines",
  "flight_number": "WN 1234",
  "riders": {
    "pilots": 2,
    "flight_attendants": 2
  },
  "trip_type": "outbound" (optional, auto-calculated if omitted)
}
```

### 3.2 Timezone Handling

**IMPORTANTE:** El campo `pick_up_time` debe enviarse en el timezone LOCAL de la location.

```javascript
// ✅ CORRECTO
const tripData = {
  pick_up_date: "2026-02-15",
  pick_up_time: "14:30:00",  // Hora local de SDF (America/New_York)
  ...
};

// ❌ INCORRECTO
const now = new Date();
const tripData = {
  pick_up_date: "2026-02-15",
  pick_up_time: now.toISOString().split('T')[1].split('.')[0],  // UTC time!
  ...
};
```

### 3.3 Process Flow

```
1. Validar location_id
2. Obtener location y su timezone
3. Parse pick_up_time como naive time
4. Asignar timezone de la location
5. Calcular trip_type si no se proporciona
6. Calcular trip_hash
7. Insertar en DB (PostgreSQL convierte a UTC)
8. Trigger envía evento WebSocket
```

### 3.4 Response

```json
{
  "data": {
    "id": "trip-uuid-1",
    "location_id": "location-uuid",
    "pick_up_date": "2026-02-15",
    "pick_up_time": "14:30:00-05:00",
    "pick_up_location": "The Galt House",
    "drop_off_location": "SDF",
    "airline": "Southwest Airlines",
    "flight_number": "WN 1234",
    "trip_type": "outbound",
    "trip_hash": "1234567890",
    "status": "scheduled",
    "assigned_driver": null,
    "started_at": null,
    "picked_up_at": null,
    "dropped_off_at": null,
    "created_at": "2026-02-11T10:00:00.000Z",
    "updated_at": "2026-02-11T10:00:00.000Z"
  }
}
```

---

## 4. Update Trip

### 4.1 Endpoint

```http
PATCH /v1/locations/{location_id}/trips/{trip_id}
Authorization: Bearer <manager_token>
Content-Type: application/json

{
  "assigned_driver": "driver-uuid" (optional),
  "pick_up_date": "2026-02-16" (optional),
  "pick_up_time": "15:45:00" (optional),
  "pick_up_location": "Hyatt Regency" (optional),
  "drop_off_location": "SDF" (optional),
  "airline": "Delta" (optional),
  "flight_number": "DL 5678" (optional),
  "riders": {"pilots": 3, "flight_attendants": 4} (optional),
  "trip_type": "outbound" (optional),
  "started_at": "2026-02-15T14:25:00Z" (optional),
  "picked_up_at": "2026-02-15T14:35:00Z" (optional),
  "dropped_off_at": "2026-02-15T15:10:00Z" (optional)
}
```

### 4.2 Timezone Handling

Si se actualiza `pick_up_time`, **debe enviarse en hora local** de la location:

```javascript
// ✅ CORRECTO
const updateData = {
  pick_up_time: "15:45:00"  // Hora local
};

fetch(`/v1/locations/${locationId}/trips/${tripId}`, {
  method: 'PATCH',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(updateData)
});

// ❌ INCORRECTO - No convertir a UTC antes de enviar
const utcTime = new Date(`2026-02-15T15:45:00-05:00`).toISOString();
const updateData = {
  pick_up_time: utcTime.split('T')[1].split('.')[0]  // "20:45:00" UTC - WRONG!
};
```

### 4.3 Auto-Recalculation

Si se actualizan `pick_up_location` o `drop_off_location`, el sistema recalcula automáticamente el `trip_type`:

```
Ejemplo:
Actualización: { "drop_off_location": "The Galt House" }
Location name: "SDF"

Resultado:
- pick_up_location: "SDF" (sin cambios)
- drop_off_location: "The Galt House" (actualizado)
- trip_type: "inbound" (recalculado automáticamente)
```

### 4.4 Response

```json
{
  "status": "ok",
  "trip": {
    "id": "trip-uuid-1",
    "location_id": "location-uuid",
    "pick_up_date": "2026-02-16",
    "pick_up_time": "15:45:00-05:00",
    "pick_up_location": "Hyatt Regency",
    "drop_off_location": "SDF",
    "trip_type": "outbound",
    "updated_at": "2026-02-11T10:30:00.000Z",
    ...
  }
}
```

---

## 5. Examples

### 5.1 Complete Flow - Create Trip

```javascript
// 1. Get location info (includes timezone)
const location = await fetch('/v1/locations')
  .then(r => r.json())
  .then(data => data.locations.find(l => l.name === 'SDF'));

console.log(location.timezone); // "America/New_York"

// 2. User selects date/time in a date picker (local time)
const pickupDateTime = {
  date: "2026-02-15",
  time: "14:30:00"  // 2:30 PM local time
};

// 3. Create trip with local time
const tripData = {
  pick_up_date: pickupDateTime.date,
  pick_up_time: pickupDateTime.time,  // Send as-is (local time)
  pick_up_location: "The Galt House",
  drop_off_location: "SDF",
  airline: "Southwest Airlines",
  flight_number: "WN 1234",
  riders: { pilots: 2, flight_attendants: 2 }
};

const response = await fetch(`/v1/locations/${location.id}/trips`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify(tripData)
});

const result = await response.json();
console.log(result.data.pick_up_time); // "14:30:00-05:00" (with timezone)
```

### 5.2 Update Trip Time

```javascript
// User changes time to 3:45 PM in the UI
const newTime = "15:45:00";  // Local time

const response = await fetch(`/v1/locations/${locationId}/trips/${tripId}`, {
  method: 'PATCH',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    pick_up_time: newTime  // Send local time directly
  })
});

const result = await response.json();
console.log(result.trip.pick_up_time); // "15:45:00-05:00"
```

### 5.3 Display Time in UI

```javascript
// When receiving trip data from API
const trip = {
  pick_up_date: "2026-02-15",
  pick_up_time: "14:30:00-05:00",  // Aware time from backend
  ...
};

// Option 1: Parse and display in location's timezone
import { DateTime } from 'luxon';

const pickupDateTime = DateTime.fromISO(
  `${trip.pick_up_date}T${trip.pick_up_time}`,
  { zone: location.timezone }
);

console.log(pickupDateTime.toLocaleString(DateTime.TIME_SIMPLE));
// "2:30 PM"

// Option 2: Just show the time part (already in local timezone)
const timeOnly = trip.pick_up_time.split('-')[0]; // "14:30:00"
console.log(timeOnly); // "14:30:00"
```

---

## 6. Common Mistakes

### 6.1 Mistake: Converting to UTC Before Sending

```javascript
// ❌ WRONG
const localTime = "14:30:00";
const date = "2026-02-15";
const utcDateTime = new Date(`${date}T${localTime}-05:00`).toISOString();
const utcTime = utcDateTime.split('T')[1].split('.')[0]; // "19:30:00" UTC

fetch('/v1/locations/xxx/trips', {
  body: JSON.stringify({
    pick_up_time: utcTime  // WRONG! Server expects local time
  })
});

// ✅ CORRECT
fetch('/v1/locations/xxx/trips', {
  body: JSON.stringify({
    pick_up_time: "14:30:00"  // Send local time as-is
  })
});
```

### 6.2 Mistake: Using Browser's Timezone

```javascript
// ❌ WRONG - User's browser might be in different timezone
const now = new Date();
const localTime = now.toLocaleTimeString('en-US', {
  hour12: false,
  timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone
});
// If user is in California but location is in New York, this is wrong!

// ✅ CORRECT - Always use location's timezone
const localTime = now.toLocaleTimeString('en-US', {
  hour12: false,
  timeZone: location.timezone  // Use location's timezone
});
```

### 6.3 Mistake: Ignoring Daylight Saving Time

```javascript
// ❌ WRONG - Hardcoding offset
const time = "14:30:00-05:00";  // Always EST, what about EDT?

// ✅ CORRECT - Let the system handle DST
const time = "14:30:00";  // Backend applies correct offset based on date
// 2026-02-15: 14:30:00-05:00 (EST in winter)
// 2026-07-15: 14:30:00-04:00 (EDT in summer)
```

### 6.4 Mistake: Mixing Timezones

```javascript
// ❌ WRONG - Different locations with different timezones
const tripDataSDF = {
  pick_up_time: "14:30:00",  // America/New_York
  location_id: sdfLocationId
};

const tripDataLAX = {
  pick_up_time: "14:30:00",  // Should be America/Los_Angeles, not NY time!
  location_id: laxLocationId
};

// ✅ CORRECT - Use appropriate time for each location's timezone
const tripDataSDF = {
  pick_up_time: "14:30:00",  // 2:30 PM Eastern
  location_id: sdfLocationId
};

const tripDataLAX = {
  pick_up_time: "11:30:00",  // 11:30 AM Pacific (same moment in time)
  location_id: laxLocationId
};
```

---

## Best Practices

### ✅ DO:

1. **Always send times in location's local timezone**
2. **Store location.timezone in your frontend state**
3. **Use timezone-aware libraries** (Luxon, date-fns-tz, moment-timezone)
4. **Display times in location's timezone**, not user's browser timezone
5. **Let the backend handle timezone conversion to UTC**

### ❌ DON'T:

1. **Don't convert times to UTC before sending to API**
2. **Don't use browser's timezone for location-based times**
3. **Don't hardcode timezone offsets** (DST changes them)
4. **Don't assume all locations have the same timezone**
5. **Don't parse `pick_up_time` without considering its timezone info**

---

## Summary

| Operation | Time Format | Timezone | Example |
|-----------|-------------|----------|---------|
| **Upload Excel** | HH:MM:SS | Location local | `14:30:00` |
| **Create Trip (API)** | HH:MM:SS | Location local | `14:30:00` |
| **Update Trip (API)** | HH:MM:SS | Location local | `15:45:00` |
| **Backend Storage** | HH:MM:SS±HH:MM | UTC internally | `19:30:00+00:00` |
| **API Response** | HH:MM:SS±HH:MM | Location timezone | `14:30:00-05:00` |
| **UI Display** | Parse with timezone | Location timezone | "2:30 PM EST" |

**Remember:** The backend handles all timezone conversions. Just send naive times in the location's local timezone, and everything works correctly! 🎯

---

**Document End**
