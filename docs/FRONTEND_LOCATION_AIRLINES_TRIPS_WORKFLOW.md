# Workflow Completo: Location → Airlines → Trips

**Fecha:** 2026-01-15
**Estado:** Backend funcionando - Frontend requiere fix de parsing
**Objetivo:** Documentar el flujo completo de navegación y paginación

---

## Resumen del Flujo

```
┌─────────────────────────────────────────────────────────────────┐
│                    JERARQUÍA DE NAVEGACIÓN                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. LOCATIONS (Lista)                                           │
│     └── GET /v1/locations                                       │
│         Response: [{ id, name: "SDF" }, { id, name: "ORD" }]    │
│                                                                 │
│  2. AIRLINES (Por Location)                                     │
│     └── GET /v1/locations/{location_id}/airlines                │
│         Response: { airlines: ["WN", "AA", "DL"], total: 3 }    │
│                                                                 │
│  3. TRIPS (Paginados por Airline + Mes/Año)                     │
│     └── GET /v1/locations/{location_id}/trips?airline=WN        │
│         &pick_up_date_from=2026-01-01                           │
│         &pick_up_date_to=2026-01-31                             │
│         Response: { data: [...trips], total: 150 }              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Ejemplo de URL en frontend:**
```
/dashboard/locations/SDF/WN?month=2026-01
                      │    │
                      │    └── Airline code (STRING "WN", no objeto)
                      └── Location name
```

---

## IMPORTANTE: Paginación de UNA Aerolínea a la Vez

El sistema está diseñado para mostrar trips de **UNA sola aerolínea** por vista.

### Flujo de Navegación

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────────────┐
│   LOCATIONS     │      │    AIRLINES     │      │    TRIPS (paginados)    │
│   (Lista)       │ ───► │  (Por Location) │ ───► │  (Por Airline + Mes)    │
├─────────────────┤      ├─────────────────┤      ├─────────────────────────┤
│                 │      │                 │      │                         │
│  • SDF ◄────────│      │  SDF:           │      │  SDF / WN / Enero 2026: │
│  • ORD          │      │  ┌─────────────┐│      │  ┌───────────────────┐  │
│  • LAX          │      │  │ WN ◄────────││      │  │ Trip 1: 08:30     │  │
│                 │      │  │ AA          ││      │  │ Trip 2: 09:15     │  │
│                 │      │  │ DL          ││      │  │ Trip 3: 10:00     │  │
│                 │      │  └─────────────┘│      │  │ ...               │  │
│                 │      │                 │      │  │ [Página 1 de 8]   │  │
│                 │      │                 │      │  └───────────────────┘  │
└─────────────────┘      └─────────────────┘      └─────────────────────────┘
     Paso 1                   Paso 2                      Paso 3
```

### Por qué UNA aerolínea a la vez

1. **Performance**: Cargar trips de todas las aerolíneas sería muy pesado
2. **UX**: El usuario puede enfocarse en una aerolínea específica
3. **Filtros**: Permite aplicar filtros (Reduce/Combine/Expand) por aerolínea
4. **Paginación clara**: Total de trips es específico a esa aerolínea

### Estructura de URLs

```
/dashboard/locations                        → Lista de locations
/dashboard/locations/SDF                    → Airlines de SDF
/dashboard/locations/SDF/WN                 → Trips de WN (default: mes actual)
/dashboard/locations/SDF/WN?month=2026-01   → Trips de WN en Enero 2026
/dashboard/locations/SDF/WN?month=2026-02   → Trips de WN en Febrero 2026
/dashboard/locations/SDF/AA                 → Trips de AA (otra aerolínea)
```

### Selector de Aerolínea en UI

```tsx
// El usuario ve tabs o chips para cambiar de aerolínea
// Solo UNA está activa a la vez

<div className="airline-tabs">
  <Link href="/dashboard/locations/SDF/WN" className="active">WN</Link>
  <Link href="/dashboard/locations/SDF/AA">AA</Link>
  <Link href="/dashboard/locations/SDF/DL">DL</Link>
</div>

// Debajo: trips SOLO de la aerolínea activa (WN)
<TripsList airline="WN" trips={trips} />
```

### Request al Backend

```http
GET /v1/locations/{location_id}/trips
    ?airline=WN                      ← UNA sola aerolínea
    &pick_up_date_from=2026-01-01    ← Primer día del mes
    &pick_up_date_to=2026-01-31      ← Último día del mes
    &skip=0                          ← Paginación
    &limit=20
```

**NO se hace:**
```http
# ❌ INCORRECTO - No cargar todas las aerolíneas juntas
GET /v1/locations/{location_id}/trips?skip=0&limit=20
```

---

## 1. Endpoint: Listar Locations

### Request
```http
GET /v1/locations
Authorization: Bearer {token}
```

### Response (200 OK)
```json
{
  "success": true,
  "data": [
    {
      "id": "72a1543b-5366-4096-b5d6-94fc9987e3e0",
      "name": "SDF",
      "organization_id": "uuid",
      "point": { "type": "Point", "coordinates": [-85.736, 38.174] },
      "radio_zone": 0.5,
      "timezone": "America/New_York",
      "created_at": "2026-01-10T12:00:00Z"
    },
    {
      "id": "abc123...",
      "name": "ORD",
      ...
    }
  ]
}
```

### TypeScript
```typescript
interface Location {
  id: string;           // UUID
  name: string;         // "SDF", "ORD"
  organization_id: string;
  point: {
    type: "Point";
    coordinates: [number, number]; // [lon, lat]
  };
  radio_zone: number;
  timezone: string;
  created_at: string;
}

// Uso en componente
const { data } = await api.get<{ data: Location[] }>('/v1/locations');
const locations = data.data;

locations.map(loc => (
  <Link href={`/dashboard/locations/${loc.name}`}>
    {loc.name}
  </Link>
))
```

---

## 2. Endpoint: Airlines por Location

### Request
```http
GET /v1/locations/{location_id}/airlines
Authorization: Bearer {token}
```

### Response (200 OK)
```json
{
  "location_id": "72a1543b-5366-4096-b5d6-94fc9987e3e0",
  "location_name": "SDF",
  "airlines": ["WN", "AA", "DL"],
  "total": 3
}
```

### TypeScript

```typescript
interface AirlinesResponse {
  location_id: string;
  location_name: string;
  airlines: string[];    // ⚠️ IMPORTANTE: Array de STRINGS, no objetos
  total: number;
}

// Uso correcto
const { data } = await api.get<AirlinesResponse>(
  `/v1/locations/${locationId}/airlines`
);

// airlines ES UN ARRAY DE STRINGS
// ["WN", "AA", "DL"]
// NO es [{code: "WN"}, {code: "AA"}]

data.airlines.map(airline => {
  // ✅ airline es "WN" (string)
  // ❌ airline NO es {W: 'N'} (objeto)

  return (
    <Link
      key={airline}
      href={`/dashboard/locations/${data.location_name}/${airline}`}
    >
      {airline}
    </Link>
  )
})
```

---

## 3. Endpoint: Trips Paginados

### Request
```http
GET /v1/locations/{location_id}/trips
Authorization: Bearer {token}
```

### Query Parameters

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `airline` | string | Filtrar por aerolínea (ej: "WN") |
| `pick_up_date` | string | Fecha exacta "YYYY-MM-DD" |
| `pick_up_date_from` | string | Fecha desde "YYYY-MM-DD" |
| `pick_up_date_to` | string | Fecha hasta "YYYY-MM-DD" |
| `pick_up_time_from` | string | Hora desde "HH:MM" |
| `pick_up_time_to` | string | Hora hasta "HH:MM" |
| `trip_type` | string | "inbound", "outbound", "ground" |
| `skip` | int | Offset para paginación (default: 0) |
| `limit` | int | Límite por página (1-50, default: 20) |

### Response (200 OK)
```json
{
  "data": [
    {
      "id": "uuid",
      "location_id": "uuid",
      "pick_up_date": "2026-01-15",
      "pick_up_time": "08:30:00",
      "pick_up_location": "Hilton Downtown",
      "drop_off_location": "SDF Airport",
      "airline": "WN",
      "flight_number": "WN1234",
      "trip_type": "outbound",
      "riders": null,
      "status": "scheduled",
      "created_at": "2026-01-10T12:00:00Z",
      "original_pick_up_time": null,
      "filter_applied": null,
      "filter_batch_id": null
    }
  ],
  "skip": 0,
  "limit": 20,
  "total": 150
}
```

### TypeScript

```typescript
interface Trip {
  id: string;
  location_id: string;
  pick_up_date: string;           // "2026-01-15"
  pick_up_time: string;           // "08:30:00"
  pick_up_location: string;
  drop_off_location: string;
  airline: string;                // "WN" - STRING
  flight_number: string;
  trip_type: "inbound" | "outbound" | "ground";
  riders: unknown[] | null;
  status: "scheduled" | "canceled" | "en_route";
  created_at: string;
  // Filter tracking
  original_pick_up_time: string | null;
  filter_applied: "reduce" | "combine" | "expand" | null;
  filter_batch_id: string | null;
  filtered_at: string | null;
}

interface TripsResponse {
  data: Trip[];
  skip: number;
  limit: number;
  total: number;
}
```

---

## 4. Paginación por Mes/Año

Para paginar trips por mes, usar `pick_up_date_from` y `pick_up_date_to`:

### Ejemplo: Enero 2026

```typescript
const getTripsForMonth = async (
  locationId: string,
  airline: string,
  year: number,
  month: number,
  page: number = 0,
  pageSize: number = 20
) => {
  // Calcular primer y último día del mes
  const firstDay = new Date(year, month - 1, 1);
  const lastDay = new Date(year, month, 0); // Último día del mes anterior = último de este mes

  const dateFrom = firstDay.toISOString().split('T')[0]; // "2026-01-01"
  const dateTo = lastDay.toISOString().split('T')[0];    // "2026-01-31"

  const params = new URLSearchParams({
    airline: airline,
    pick_up_date_from: dateFrom,
    pick_up_date_to: dateTo,
    skip: String(page * pageSize),
    limit: String(pageSize)
  });

  const response = await api.get<TripsResponse>(
    `/v1/locations/${locationId}/trips?${params}`
  );

  return response.data;
};

// Uso
const trips = await getTripsForMonth(
  "72a1543b-5366-4096-b5d6-94fc9987e3e0", // location_id
  "WN",                                    // airline
  2026,                                    // year
  1,                                       // month (enero)
  0,                                       // page
  20                                       // pageSize
);

console.log(`Total trips WN en Enero 2026: ${trips.total}`);
console.log(`Mostrando ${trips.data.length} trips (página 1)`);
```

---

## 5. Hook Completo: useLocationAirlines

### Implementación Correcta

```typescript
// hooks/use-location-airlines.ts

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';

interface AirlinesResponse {
  location_id: string;
  location_name: string;
  airlines: string[];
  total: number;
}

interface UseLocationAirlinesResult {
  airlines: string[];        // ⚠️ Array de STRINGS
  locationName: string;
  isLoading: boolean;
  error: string | null;
}

export function useLocationAirlines(locationId: string): UseLocationAirlinesResult {
  const [airlines, setAirlines] = useState<string[]>([]);
  const [locationName, setLocationName] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!locationId) {
      setAirlines([]);
      setIsLoading(false);
      return;
    }

    const fetchAirlines = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await api.get<AirlinesResponse>(
          `/v1/locations/${locationId}/airlines`
        );

        // ========================================
        // ⚠️ PUNTO CRÍTICO - PARSING CORRECTO
        // ========================================

        // Debug - verificar estructura
        console.log('[useLocationAirlines] Raw response:', response);
        console.log('[useLocationAirlines] response.data:', response.data);
        console.log('[useLocationAirlines] airlines array:', response.data.airlines);

        // Verificar que airlines es un array
        if (!Array.isArray(response.data.airlines)) {
          console.error('[useLocationAirlines] airlines is not array:',
            response.data.airlines);
          throw new Error('Invalid airlines format');
        }

        // ✅ CORRECTO: Extraer directamente el array de strings
        const airlinesArray = response.data.airlines;

        // Validar cada elemento
        const validAirlines = airlinesArray.filter((airline): airline is string => {
          if (typeof airline !== 'string') {
            console.error('[useLocationAirlines] Invalid airline (not string):', airline);
            return false;
          }
          return airline.length > 0;
        });

        console.log('[useLocationAirlines] Valid airlines:', validAirlines);
        // Debe mostrar: ["WN", "AA", "DL"]
        // NO debe mostrar: [{W:'N'}, {A:'A'}]

        setAirlines(validAirlines);
        setLocationName(response.data.location_name);

      } catch (err) {
        console.error('[useLocationAirlines] Error:', err);
        setError(err instanceof Error ? err.message : 'Error fetching airlines');
        setAirlines([]);
      } finally {
        setIsLoading(false);
      }
    };

    fetchAirlines();
  }, [locationId]);

  return { airlines, locationName, isLoading, error };
}
```

---

## 6. BUG CONOCIDO: String → Objeto {W: 'N'}

### El Problema

El frontend está convirtiendo el string `"WN"` en un objeto `{W: 'N'}`.

**Log del error:**
```
[useLocationAirlines] airline is object without code: {W: 'N'}
```

### Causa Raíz

El string `"WN"` está siendo iterado como si fuera un array/objeto:

```typescript
// ❌ INCORRECTO - Esto causa el bug
const airline = "WN";
const result = { ...airline };     // { "0": "W", "1": "N" }

// ❌ INCORRECTO - Object.entries en string
Object.entries("WN")               // [["0", "W"], ["1", "N"]]

// ❌ INCORRECTO - Spread en string
const arr = [..."WN"];             // ["W", "N"]

// ❌ INCORRECTO - Map con spread
airlines.map(a => ({...a}))        // Si a="WN" → {0:"W",1:"N"}
```

### Dónde Buscar el Bug

1. **En el hook `use-location-airlines.ts`** (líneas 50-80 aprox):
```typescript
// BUSCAR código como este:
const validatedAirlines = airlines.map((airline) => {
  // Si aquí se hace spread o Object.entries, está mal
  if (typeof airline === 'object') {
    // ⚠️ Si llega aquí, el bug ya ocurrió antes
  }
});
```

2. **En el cliente API**:
```typescript
// Verificar si hay transformación de responses
// que pueda convertir strings a objetos
```

3. **En el componente de navegación**:
```typescript
// Verificar cómo se mapea el array de airlines
airlines.map(airline => (
  <Link href={`.../${airline}`}>  // ⚠️ Si airline es objeto, genera [object Object]
    {airline}
  </Link>
))
```

### Solución

```typescript
// ✅ CORRECTO - Extraer directamente sin transformar
const fetchAirlines = async () => {
  const response = await api.get(`/v1/locations/${locationId}/airlines`);

  // NO hacer spread ni Object.entries
  // Solo extraer el array directamente
  const airlines = response.data.airlines; // ["WN", "AA", "DL"]

  // Validar tipos
  const validAirlines = airlines.filter(
    (a): a is string => typeof a === 'string' && a.length > 0
  );

  setAirlines(validAirlines);
};
```

---

## 7. Componente de Navegación: Ejemplo Correcto

```tsx
// components/airline-navigation.tsx

import Link from 'next/link';
import { useLocationAirlines } from '@/hooks/use-location-airlines';

interface AirlineNavigationProps {
  locationId: string;
  locationName: string;
  currentAirline?: string;
}

export function AirlineNavigation({
  locationId,
  locationName,
  currentAirline
}: AirlineNavigationProps) {
  const { airlines, isLoading, error } = useLocationAirlines(locationId);

  if (isLoading) return <div>Cargando airlines...</div>;
  if (error) return <div>Error: {error}</div>;
  if (airlines.length === 0) return <div>No hay airlines</div>;

  return (
    <nav className="flex gap-2">
      {airlines.map((airline) => {
        // ========================================
        // ⚠️ VALIDACIÓN CRÍTICA
        // ========================================

        // Asegurar que airline es string
        if (typeof airline !== 'string') {
          console.error('[AirlineNavigation] Invalid airline type:', airline);
          return null;
        }

        const isActive = airline === currentAirline;

        // ✅ airline es "WN", genera: /dashboard/locations/SDF/WN
        // ❌ Si fuera {W:'N'}, generaría: /dashboard/locations/SDF/[object Object]
        const href = `/dashboard/locations/${locationName}/${airline}`;

        return (
          <Link
            key={airline}
            href={href}
            className={isActive ? 'font-bold' : ''}
          >
            {airline}
          </Link>
        );
      })}
    </nav>
  );
}
```

---

## 8. Flujo Completo de Navegación

### Estructura de Páginas (App Router)

```
app/
├── dashboard/
│   └── locations/
│       ├── page.tsx                          # Lista de locations
│       └── [locationName]/
│           ├── page.tsx                      # Airlines de una location
│           └── [airline]/
│               └── page.tsx                  # Trips de una airline
```

### Página: Lista de Locations

```tsx
// app/dashboard/locations/page.tsx

export default async function LocationsPage() {
  const locations = await getLocations();

  return (
    <div>
      <h1>Locations</h1>
      {locations.map(loc => (
        <Link
          key={loc.id}
          href={`/dashboard/locations/${loc.name}`}
        >
          {loc.name}
        </Link>
      ))}
    </div>
  );
}
```

### Página: Airlines de una Location

```tsx
// app/dashboard/locations/[locationName]/page.tsx

export default async function LocationPage({
  params
}: {
  params: { locationName: string }
}) {
  const location = await getLocationByName(params.locationName);
  const { airlines } = await getAirlines(location.id);

  return (
    <div>
      <h1>Location: {params.locationName}</h1>
      <h2>Airlines disponibles:</h2>
      {airlines.map((airline: string) => (
        <Link
          key={airline}
          href={`/dashboard/locations/${params.locationName}/${airline}`}
        >
          {airline}
        </Link>
      ))}
    </div>
  );
}
```

### Página: Trips de una Airline

```tsx
// app/dashboard/locations/[locationName]/[airline]/page.tsx

export default async function AirlineTripsPage({
  params,
  searchParams
}: {
  params: { locationName: string; airline: string };
  searchParams: { month?: string; page?: string };
}) {
  const location = await getLocationByName(params.locationName);

  // Parsear mes/año de query params
  const monthParam = searchParams.month || getCurrentMonth(); // "2026-01"
  const [year, month] = monthParam.split('-').map(Number);
  const page = Number(searchParams.page || '0');

  const trips = await getTripsForMonth(
    location.id,
    params.airline,  // "WN" - string
    year,
    month,
    page
  );

  return (
    <div>
      <h1>{params.locationName} / {params.airline}</h1>
      <h2>Trips - {monthParam}</h2>

      {/* Selector de mes */}
      <MonthSelector
        currentMonth={monthParam}
        baseUrl={`/dashboard/locations/${params.locationName}/${params.airline}`}
      />

      {/* Lista de trips */}
      <TripsList trips={trips.data} />

      {/* Paginación */}
      <Pagination
        total={trips.total}
        page={page}
        pageSize={20}
      />
    </div>
  );
}
```

---

## 9. Resumen de Endpoints

| Endpoint | Método | Descripción | Respuesta Clave |
|----------|--------|-------------|-----------------|
| `/v1/locations` | GET | Lista todas las locations | `{ data: Location[] }` |
| `/v1/locations/{id}/airlines` | GET | Airlines de una location | `{ airlines: string[] }` |
| `/v1/locations/{id}/trips` | GET | Trips paginados con filtros | `{ data: Trip[], total }` |

---

## 10. Checklist de Verificación

### Backend (OK)

- [x] GET /v1/locations retorna array de locations
- [x] GET /v1/locations/{id}/airlines retorna `airlines: string[]`
- [x] GET /v1/locations/{id}/trips acepta filtro `airline`
- [x] GET /v1/locations/{id}/trips acepta `pick_up_date_from` y `pick_up_date_to`
- [x] Paginación con `skip` y `limit` funciona

### Frontend (Verificar)

- [ ] `useLocationAirlines` extrae `response.data.airlines` directamente
- [ ] NO se usa spread operator en strings (`{...airline}`)
- [ ] NO se usa `Object.entries()` en airlines
- [ ] Cada airline en el map es validado como string
- [ ] Links generan URLs como `/locations/SDF/WN` (no `[object Object]`)
- [ ] Logs muestran: `airlines: ["WN", "AA"]` (strings, no objetos)

---

## 11. Debug: Verificar que Airlines son Strings

Agregar este código temporalmente para diagnosticar:

```typescript
// En use-location-airlines.ts o donde se usen airlines

const validateAirlines = (airlines: unknown[]): string[] => {
  console.log('=== AIRLINES DEBUG ===');
  console.log('Input type:', typeof airlines);
  console.log('Input value:', airlines);
  console.log('Is array:', Array.isArray(airlines));

  if (!Array.isArray(airlines)) {
    console.error('ERROR: airlines is not an array');
    return [];
  }

  const result: string[] = [];

  airlines.forEach((airline, index) => {
    console.log(`[${index}] type: ${typeof airline}, value:`, airline);

    if (typeof airline === 'string') {
      console.log(`  ✅ Valid string: "${airline}"`);
      result.push(airline);
    } else if (typeof airline === 'object' && airline !== null) {
      console.error(`  ❌ Invalid object:`, airline);
      console.error(`     Keys:`, Object.keys(airline));
      console.error(`     Values:`, Object.values(airline));

      // Intentar recuperar el string original
      const values = Object.values(airline);
      if (values.every(v => typeof v === 'string')) {
        const recovered = values.join('');
        console.log(`     Recovered: "${recovered}"`);
        result.push(recovered);
      }
    } else {
      console.error(`  ❌ Unknown type:`, airline);
    }
  });

  console.log('=== END DEBUG ===');
  console.log('Result:', result);

  return result;
};
```

**Output esperado (correcto):**
```
=== AIRLINES DEBUG ===
Input type: object
Input value: ["WN", "AA", "DL"]
Is array: true
[0] type: string, value: WN
  ✅ Valid string: "WN"
[1] type: string, value: AA
  ✅ Valid string: "AA"
[2] type: string, value: DL
  ✅ Valid string: "DL"
=== END DEBUG ===
Result: ["WN", "AA", "DL"]
```

**Output problemático (bug):**
```
=== AIRLINES DEBUG ===
Input type: object
Input value: [{W: 'N'}, {A: 'A'}, {D: 'L'}]
Is array: true
[0] type: object, value: {W: 'N'}
  ❌ Invalid object: {W: 'N'}
     Keys: ["W"]
     Values: ["N"]
     Recovered: "N"
...
```

---

## 12. Contacto

Backend: Claude Code / GT360 Team
Fecha: 2026-01-15
