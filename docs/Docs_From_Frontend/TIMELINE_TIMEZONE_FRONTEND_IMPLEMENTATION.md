# Timeline con Soporte de Timezone - Implementacion Frontend

**Fecha:** 2026-01-05
**Estado:** Completado
**Version:** 1.0

---

## Resumen Ejecutivo

Se implemento soporte de timezone en el Timeline de Dashboard Home para ordenar las cards de trips usando la zona horaria de la location seleccionada. El backend envia `location_info` con el timezone en el snapshot de WebSocket.

---

## Tabla de Contenidos

1. [Cambios Implementados](#1-cambios-implementados)
2. [Definiciones Oficiales](#2-definiciones-oficiales)
3. [Arquitectura de Datos](#3-arquitectura-de-datos)
4. [Archivos Modificados](#4-archivos-modificados)
5. [Como Funciona](#5-como-funciona)
6. [Testing](#6-testing)
7. [Seccion para Backend Developer](#7-seccion-para-backend-developer)

---

## 1. Cambios Implementados

### Dependencias Agregadas

```bash
npm install date-fns-tz
```

### Resumen de Cambios

| Archivo | Cambio |
|---------|--------|
| `src/types/api.ts` | Nueva interface `LocationInfo` |
| `src/lib/websocket/types.ts` | `location_info` en `TripEventSnapshot` |
| `src/lib/trips/trip-helpers.ts` | Funciones timezone-aware |
| `src/lib/trips/card-transformers.ts` | Soporte para `locationInfo` |
| `src/stores/trips/trips-store.ts` | `locationInfo` en state |
| `src/hooks/use-websocket-trips.ts` | `SnapshotData` con `locationInfo` |
| `src/providers/trips-websocket-provider.tsx` | Procesa `location_info` |
| `src/app/(main)/dashboard/home/page.tsx` | Usa `locationInfo` del store |

---

## 2. Definiciones Oficiales

### Inbound Trip (ARRIVAL - Llegada)

| Aspecto | Valor |
|---------|-------|
| **Condicion** | `trip.pick_up_location === location_info.id` |
| **Significado** | El pasajero LLEGA al aeropuerto desde un vuelo |
| **Escenario** | Avion aterriza -> Conductor recoge EN el aeropuerto -> Lleva al hotel |
| **Icono** | Avion |
| **Tiempo Timeline** | ARRIVAL TIME (hora de llegada del vuelo) |

### Outbound Trip (DEPARTURE - Salida)

| Aspecto | Valor |
|---------|-------|
| **Condicion** | `trip.drop_off_location === location_info.id` |
| **Significado** | El pasajero SALE hacia el aeropuerto para tomar un vuelo |
| **Escenario** | Conductor recoge en hotel -> Lleva AL aeropuerto -> Pasajero toma vuelo |
| **Icono** | Carro |
| **Tiempo Timeline** | PICK UP TIME (van time) |

---

## 3. Arquitectura de Datos

### Interface LocationInfo

```typescript
// src/types/api.ts
export interface LocationInfo {
  id: string       // UUID de la location (aeropuerto)
  name: string     // Codigo del aeropuerto (e.g., "SDF", "JFK")
  timezone: string // IANA timezone (e.g., "America/New_York")
}
```

### Formato del Snapshot WebSocket

```json
{
  "type": "snapshot",
  "location_id": "uuid-de-la-location",
  "location_info": {
    "id": "uuid-de-la-location",
    "name": "SDF",
    "timezone": "America/New_York"
  },
  "trips": [...]
}
```

---

## 4. Archivos Modificados

### 4.1 src/types/api.ts

**Lineas 214-226:**
```typescript
/**
 * LocationInfo - Minimal location data sent with WebSocket snapshots
 * Used for timezone-aware trip ordering in the Timeline view
 */
export interface LocationInfo {
  id: string
  name: string
  timezone: string
}
```

### 4.2 src/lib/websocket/types.ts

**Lineas 20-25:**
```typescript
export interface TripEventSnapshot {
  type: 'snapshot'
  location_id: string
  location_info?: LocationInfo  // <- AGREGADO
  trips: Trip[]
}
```

### 4.3 src/lib/trips/trip-helpers.ts

**Funciones nuevas agregadas:**

```typescript
// Tipo para direccion del trip
export type TripDirection = 'inbound' | 'outbound' | 'unknown';

// Determina direccion por UUID
export function getTripDirection(
  trip: TripDataMinimal,
  locationId: string | null | undefined
): TripDirection

// Formatea tiempo con timezone
export function formatTimeWithTimezone(
  dateStr: string,
  timeStr: string,
  timezone: string
): string

// Obtiene day key con timezone
export function getDayKeyWithTimezone(
  dateStr: string,
  timeStr: string,
  timezone: string
): string

// Obtiene tiempo relevante para ordenamiento
export function getTimelineRelevantTime(
  trip: { pick_up_time?: string },
  direction: TripDirection
): string
```

### 4.4 src/lib/trips/card-transformers.ts

**Firma actualizada:**
```typescript
export function transformTripToCardViewModel(
  trip: Trip,
  locationCode: string,
  locationInfo?: LocationInfo | null  // <- AGREGADO
): CardViewModel

export function transformTripsToCardViewModels(
  trips: Trip[],
  locationCode: string,
  locationInfo?: LocationInfo | null  // <- AGREGADO
): CardViewModel[]
```

### 4.5 src/stores/trips/trips-store.ts

**State agregado:**
```typescript
export interface TripStoreState {
  // ... existing state
  locationInfo: LocationInfo | null  // <- AGREGADO

  // ... existing actions
  setLocationInfo: (locationInfo: LocationInfo | null) => void  // <- AGREGADO
}
```

### 4.6 src/hooks/use-websocket-trips.ts

**Nueva interface:**
```typescript
export interface SnapshotData {
  trips: Trip[]
  locationInfo?: LocationInfo
}

export interface UseWebSocketTripsOptions {
  // ...
  onSnapshot?: (data: SnapshotData) => void  // <- CAMBIADO
}
```

### 4.7 src/providers/trips-websocket-provider.tsx

**Handler actualizado:**
```typescript
const handleSnapshot = useCallback((data: SnapshotData) => {
  if (data.locationInfo) {
    setLocationInfo(data.locationInfo)
  }
  setTrips(data.trips)
  // ...
}, [setTrips, setLocationInfo, setError])
```

### 4.8 src/app/(main)/dashboard/home/page.tsx

**Uso de locationInfo:**
```typescript
const locationInfo = useTripsStore((state) => state.locationInfo);

const cardViewModels = useMemo(() => {
  if (!currentLocationCode || trips.length === 0) return [];
  return transformTripsToCardViewModels(trips, currentLocationCode, locationInfo);
}, [trips, currentLocationCode, locationInfo]);
```

---

## 5. Como Funciona

### Flujo de Datos

```
1. Usuario navega a /dashboard/home
   |
2. setLocationId(locationId) via WebSocket provider
   |
3. WebSocket conecta a /ws/trips?location_id=X&token=Y
   |
4. Backend envia snapshot con location_info
   {
     "type": "snapshot",
     "location_id": "uuid",
     "location_info": {
       "id": "uuid",
       "name": "SDF",
       "timezone": "America/New_York"
     },
     "trips": [...]
   }
   |
5. Provider recibe snapshot:
   - setLocationInfo(data.locationInfo)
   - setTrips(data.trips)
   |
6. home/page.tsx:
   - Obtiene locationInfo del store
   - Transforma trips con timezone-aware functions
   - Cards se ordenan por fecha/hora en timezone local
```

### Logica de Ordenamiento

```typescript
// En card-transformers.ts
if (locationInfo?.timezone) {
  // Formato timezone-aware: "2:30 PM EST"
  departure = formatTimeWithTimezone(
    trip.pick_up_date,
    trip.pick_up_time,
    locationInfo.timezone
  )
  // Day key con timezone correcto
  dayKey = getDayKeyWithTimezone(
    trip.pick_up_date,
    trip.pick_up_time,
    locationInfo.timezone
  )
} else {
  // Fallback sin timezone
  departure = formatTripTime(trip.pick_up_date, trip.pick_up_time)
  dayKey = trip.pick_up_date || ''
}
```

---

## 6. Testing

### Checklist de Testing

| # | Escenario | Esperado |
|---|-----------|----------|
| 1 | Trip inbound | `pick_up_location === airport.id` -> icono avion |
| 2 | Trip outbound | `drop_off_location === airport.id` -> icono carro |
| 3 | Agrupacion por dia | Trips separados por fecha con timezone |
| 4 | Ordenamiento | Ordenados por pick_up_time dentro del dia |
| 5 | Add Trip | Card aparece en posicion correcta del timeline |
| 6 | Edit Trip | Card se mueve si cambia fecha/hora |
| 7 | Delete Trip | Card desaparece del timeline |
| 8 | Sin timezone | Fallback funciona correctamente |

### Como Verificar

1. Abrir DevTools -> Console
2. Navegar a `/dashboard/home`
3. Verificar logs:
   ```
   [useWebSocketTrips] Received snapshot: X trips
   [useWebSocketTrips] Location info: SDF timezone: America/New_York
   [TripsWebSocketProvider] Location info: SDF timezone: America/New_York
   ```
4. Cards deben mostrar tiempo con timezone (e.g., "2:30 PM EST")

---

## 7. Seccion para Backend Developer

### Estado del Backend

> **El backend ya envia `location_info` en el snapshot WebSocket.**

Este documento asume que la implementacion backend documentada en `TIMELINE_WITH_TIMEZONE.md` esta completa.

### Verificacion de Datos

#### Estructura Requerida del Snapshot

```json
{
  "type": "snapshot",
  "location_id": "550e8400-e29b-41d4-a716-446655440000",
  "location_info": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "SDF",
    "timezone": "America/New_York"
  },
  "trips": [
    {
      "id": "trip-uuid",
      "location_id": "550e8400-e29b-41d4-a716-446655440000",
      "pick_up_date": "2026-01-15",
      "pick_up_time": "14:30:00",
      "pick_up_location": "550e8400-e29b-41d4-a716-446655440000",
      "drop_off_location": "hotel-uuid",
      "airline": "WN",
      "flight_number": "2445"
    }
  ]
}
```

#### Campos Criticos

| Campo | Tipo | Requerido | Descripcion |
|-------|------|-----------|-------------|
| `location_info.id` | UUID | Si | Debe coincidir con `location_id` del snapshot |
| `location_info.name` | string | Si | Codigo IATA del aeropuerto |
| `location_info.timezone` | string | Si | IANA timezone valido |
| `trip.pick_up_location` | UUID | Si | UUID de la location de pickup |
| `trip.drop_off_location` | UUID | Si | UUID de la location de dropoff |

### Validacion de Timezones

Timezones comunes para aeropuertos US:

| Aeropuertos | Timezone IANA |
|-------------|---------------|
| SDF, JFK, MIA, ATL, BOS, PHL | America/New_York |
| ORD, DFW, MDW, MSP, STL | America/Chicago |
| DEN, PHX, SLC | America/Denver |
| LAX, SEA, SFO, PDX, LAS | America/Los_Angeles |
| ANC | America/Anchorage |
| HNL | Pacific/Honolulu |

### Comandos de Verificacion

```bash
# Ver estructura del snapshot
wscat -c "wss://api.gt360.app/ws/trips?location_id=UUID&token=JWT"

# Verificar timezone en DB
psql -c "SELECT id, name, timezone FROM locations WHERE timezone IS NOT NULL LIMIT 5;"

# Buscar locations sin timezone
psql -c "SELECT id, name FROM locations WHERE timezone IS NULL OR timezone = '';"
```

### Logs Esperados en Frontend

Cuando funciona correctamente:
```
[useWebSocketTrips] Received snapshot: 15 trips
[useWebSocketTrips] Location info: SDF timezone: America/New_York
[TripsWebSocketProvider] Received snapshot: 15 trips
[TripsWebSocketProvider] Location info: SDF timezone: America/New_York
```

Cuando falta `location_info`:
```
[useWebSocketTrips] Received snapshot: 15 trips
// NO hay log de Location info - fallback a formateo simple
```

### Restriccion Importante

> **Dashboard Home NO soporta "All locations"**

El Timeline requiere UNA zona horaria especifica para ordenar correctamente. Si se intentara mostrar trips de multiples locations con diferentes timezones, el ordenamiento seria inconsistente.

### Resolucion de Problemas

| Problema | Causa | Solucion |
|----------|-------|----------|
| Cards sin timezone en hora | `location_info` no enviado | Verificar backend envia `location_info` |
| Timezone incorrecto | IANA timezone invalido | Verificar formato (e.g., "America/New_York" no "EST") |
| Direccion incorrecta | UUID no coincide | Verificar `pick_up_location`/`drop_off_location` son UUIDs |
| Fallback siempre activo | `location_info.timezone` vacio | Verificar campo timezone no es null/empty |

---

## Apendice A: Dependencias

```json
{
  "dependencies": {
    "date-fns": "^4.1.0",
    "date-fns-tz": "^3.x.x"
  }
}
```

## Apendice B: Documentacion Relacionada

| Documento | Descripcion |
|-----------|-------------|
| [TIMELINE_WITH_TIMEZONE.md](Docs_From_Backend/TIMELINE_WITH_TIMEZONE.md) | Documentacion backend del feature |
| [UNIFIED_TRIPS_WEBSOCKET_PIPELINE.md](UNIFIED_TRIPS_WEBSOCKET_PIPELINE.md) | Arquitectura WebSocket unificada |
| [WEBSOCKET_FRONTEND_GUIDE.md](WEBSOCKET_FRONTEND_GUIDE.md) | Guia de integracion WebSocket |

---

**Documento Creado:** 2026-01-05
**Ultima Actualizacion:** 2026-01-05
