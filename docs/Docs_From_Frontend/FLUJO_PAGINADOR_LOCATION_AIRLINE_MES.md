# Flujo del Paginador - Location/Airline/Mes-Año

## Índice
1. [Arquitectura General](#arquitectura-general)
2. [Componentes Principales](#componentes-principales)
3. [Flujos de Datos](#flujos-de-datos)
4. [Casos de Uso](#casos-de-uso)
5. [Diagrama de Flujo](#diagrama-de-flujo)

---

## Arquitectura General

### Sistema Híbrido: REST + WebSocket

El sistema utiliza una arquitectura híbrida que combina:
- **REST API**: Source of truth para datos históricos y paginación server-side
- **WebSocket**: Real-time updates para cambios en tiempo real

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │
       ├─────────────┐
       │             │
       ▼             ▼
┌──────────┐  ┌─────────────┐
│ REST API │  │  WebSocket  │
│(Paginated│  │ (Real-time) │
│ + Filtered)  │  (Snapshot) │
└──────────┘  └─────────────┘
       │             │
       └──────┬──────┘
              ▼
      ┌───────────────┐
      │ Zustand Store │
      │  (storeTrips) │
      └───────────────┘
              │
              ▼
      ┌───────────────┐
      │   UI Layer    │
      │  (rowsData)   │
      └───────────────┘
```

---

## Componentes Principales

### 1. State Management

#### Estados Locales (Component State)
```typescript
// Datos paginados que se muestran en la tabla
const [rowsData, setRowsData] = useState<Row[]>([])

// Paginación
const [nextSkip, setNextSkip] = useState(0)
const [serverTotalTrips, setServerTotalTrips] = useState<number | null>(null)
const [isLoadingTrips, setIsLoadingTrips] = useState(false)
const [isLoadingMoreTrips, setIsLoadingMoreTrips] = useState(false)

// Filtros activos
const [selectedMonth, selectedYear] = props // Desde URL/props
```

#### Store Global (Zustand)
```typescript
// Trips del WebSocket (TODOS los trips de la location, sin filtrar)
const storeTrips = useTripsStore((state) => state.trips)

// Location info (timezone, etc)
const locationInfo = useTripsStore((state) => state.locationInfo)
```

### 2. Filtrado por Location/Airline/Mes-Año

#### Nivel de Filtrado
```
Location ID → Airline → Mes-Año
   (WS)        (BE)      (BE)
```

- **Location ID**: WebSocket subscribe a una location específica
- **Airline**: Backend filtra en REST API (`?airline=GEN`)
- **Mes-Año**: Backend filtra en REST API (`?pick_up_date_from=2026-01-01&pick_up_date_to=2026-01-31`)

#### Código de Filtrado Server-Side
```typescript
// src/app/(main)/dashboard/locations/[code]/[airline]/schedule-dashboard-client.tsx
// Líneas 1403-1411

const { from: dateFrom, to: dateTo } = getMonthDateRange(selectedMonth, selectedYear)

const params = new URLSearchParams({
  skip: String(skip),
  limit: String(PAGE_SIZE), // 50
  ...(airline ? { airline } : {}),
  pick_up_date_from: dateFrom,  // "2026-01-01"
  pick_up_date_to: dateTo,      // "2026-01-31"
})
```

---

## Flujos de Datos

### 1. Carga Inicial (Mount Component)

```
┌─────────────────────────────────────────────────────┐
│ 1. Component Mount                                  │
└────────────────┬────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────┐
│ 2. Resolve Location ID                              │
│    - Check localStorage                             │
│    - Fetch from backend if missing                  │
└────────────────┬────────────────────────────────────┘
                 │
                 ├──────────────────┬─────────────────┐
                 ▼                  ▼                 ▼
      ┌──────────────────┐  ┌────────────┐  ┌──────────────┐
      │ 3a. WebSocket    │  │ 3b. Fetch  │  │ 3c. Compute  │
      │     Connect      │  │     Trips  │  │   Available  │
      │   (locationId)   │  │   via REST │  │    Months    │
      └────────┬─────────┘  └─────┬──────┘  └──────┬───────┘
               │                  │                 │
               ▼                  ▼                 ▼
      ┌──────────────────────────────────────────────┐
      │ Snapshot Event   REST Response   storeTrips  │
      │    (ALL trips)   (Filtered)      → Filtered  │
      └───────┬──────────────┬────────────────┬──────┘
              │              │                │
              ▼              ▼                ▼
      ┌──────────────┐  ┌────────────┐  ┌─────────────┐
      │  storeTrips  │  │  rowsData  │  │availableMonths│
      │   Updated    │  │  Rendered  │  │   Computed   │
      └──────────────┘  └────────────┘  └─────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │ 4. Auto-Navigate │
                    │  to Closest Month│
                    │  (if no trips)   │
                    └──────────────────┘
```

**Líneas de código relevantes:**
- Mount effect: `lines 1939-1968`
- Resolve Location ID: `lines 825-874`
- WebSocket connect: `lines 891-895`
- Fetch trips REST: `lines 1322-1559` (función `fetchTrips`)
- Available months: `lines 970-981`
- Auto-navigate: `lines 993-1021`

### 2. Cambio de Mes/Año

```
┌──────────────────────────────────────────┐
│ User clicks MonthYearPicker              │
│ onMonthYearChange(newMonth, newYear)     │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ Effect detecta cambio (lines 1612-1634) │
│ prevMonthYearRef !== current             │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ Reset State:                             │
│ - setRowsData([])                        │
│ - setServerTotalTrips(null)              │
│ - setNextSkip(0)                         │
│ - setTripsError(null)                    │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ loadInitialTrips()                       │
│ fetchTrips({                             │
│   skip: 0,                               │
│   append: false,                         │
│   forLoadMore: false                     │
│ })                                       │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ REST API Call:                           │
│ GET /v1/locations/{id}/trips?            │
│   airline=GEN&                           │
│   pick_up_date_from=2026-02-01&          │
│   pick_up_date_to=2026-02-28&            │
│   skip=0&                                │
│   limit=50                               │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ Update UI:                               │
│ - setRowsData(trips)                     │
│ - setServerTotalTrips(total)             │
│ - setNextSkip(50)                        │
└──────────────────────────────────────────┘
```

**Características importantes:**
- El **WebSocket NO se reconecta** (mantiene snapshot completo)
- Solo se recargan los datos via **REST API**
- `availableMonths` **NO cambia** (sigue calculándose de `storeTrips`)

### 3. Scroll Infinito (Load More)

```
┌──────────────────────────────────────────┐
│ User scrolls to bottom                   │
│ IntersectionObserver triggers            │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ loadMoreTrips() (lines 1590-1606)       │
│ Guards:                                  │
│ - Already loading? Skip                  │
│ - All loaded? Skip                       │
│   (rowsData.length >= serverTotalTrips)  │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ fetchTrips({                             │
│   skip: nextSkip,  // e.g., 50          │
│   append: true,    // Important!         │
│   forLoadMore: true                      │
│ })                                       │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ REST API Call:                           │
│ GET /v1/locations/{id}/trips?            │
│   ...same filters...                     │
│   skip=50&                               │
│   limit=50                               │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ Append to rowsData (lines 1531-1542):   │
│ setRowsData(prev => {                    │
│   const seen = new Set(prev.map(r=>r.id))│
│   const merged = [...prev]               │
│   for (const row of nextRows) {          │
│     if (!seen.has(row.id)) {             │
│       merged.push(row)                   │
│     }                                    │
│   }                                      │
│   return merged                          │
│ })                                       │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ Update pagination state:                 │
│ - setNextSkip(skip + trips.length)       │
│ - setIsLoadingMoreTrips(false)           │
└──────────────────────────────────────────┘
```

**Deduplicación:**
- Se usa un `Set` para evitar duplicados al hacer append
- Compara por `row.id`

### 4. Upload de Trips (Update Button)

```
┌──────────────────────────────────────────┐
│ User clicks "Update" button              │
│ Uploads Excel with new trips             │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ UpdateTripsButton component              │
│ - Parses Excel                           │
│ - POST /v1/locations/{id}/trips/upload   │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ Backend:                                 │
│ - Inserts trips in DB                    │
│ - Sends WebSocket "insert" events        │
│   (1 per trip)                           │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ UpdateTripsButton dispatches:            │
│ window.dispatchEvent(                    │
│   new CustomEvent('trips-uploaded', {    │
│     detail: { uploadedRows, locationId } │
│   })                                     │
│ )                                        │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ schedule-dashboard-client.tsx            │
│ useEffect listener (lines 1971-2010)     │
│ handleUploaded() triggers:               │
└────────────────┬─────────────────────────┘
                 │
                 ├──────────────┬───────────────┐
                 ▼              ▼               ▼
        ┌────────────┐  ┌──────────┐  ┌────────────┐
        │ 1. Reset   │  │ 2. Load  │  │ 3. Reconnect│
        │   State    │  │   REST   │  │  WebSocket  │
        └────┬───────┘  └────┬─────┘  └─────┬──────┘
             │               │               │
             ▼               ▼               ▼
    ┌────────────┐  ┌───────────────┐  ┌──────────┐
    │setRowsData │  │loadInitialTrips│  │wsReconnect│
    │    ([])    │  │      ()        │  │    ()     │
    └────────────┘  └───────────────┘  └──────┬────┘
                            │                  │
                            ▼                  ▼
                    ┌───────────────┐  ┌─────────────┐
                    │ REST loads    │  │ WS sends    │
                    │ trips for     │  │ snapshot    │
                    │ current month │  │ (ALL trips) │
                    └───────┬───────┘  └──────┬──────┘
                            │                 │
                            ▼                 ▼
                    ┌──────────────┐  ┌──────────────┐
                    │  rowsData    │  │  storeTrips  │
                    │  updated     │  │  updated     │
                    └──────┬───────┘  └──────┬───────┘
                           │                 │
                           └────────┬────────┘
                                    ▼
                          ┌──────────────────┐
                          │ availableMonths  │
                          │ RECALCULATED     │
                          │ (Fix aplicado)   │
                          └──────────────────┘
```

**Fix Aplicado (2026-01-15):**
- **Problema**: `availableMonths` no se actualizaba porque solo `rowsData` cambiaba (REST), pero `storeTrips` (WebSocket) no
- **Solución**: Llamar `wsReconnect()` después del upload para forzar snapshot fresco
- **Líneas**: `1992-1995`

### 5. Real-Time Updates (WebSocket)

#### 5.1 Insert Event (Otro usuario agrega trip)

```
┌──────────────────────────────────────────┐
│ Backend: Another user creates trip       │
│ WebSocket → "insert" event               │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ TripsWebSocketProvider                   │
│ handleTripEvent() (lines 110-165)        │
└────────────────┬─────────────────────────┘
                 │
                 ├─ Check if optimistic? Skip
                 ├─ Check if duplicate event? Skip
                 │
                 ▼
┌──────────────────────────────────────────┐
│ addTrip(event.trip)                      │
│ → storeTrips updated                     │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ schedule-dashboard-client.tsx            │
│ useEffect (lines 1047-1140)              │
│ Monitors storeTrips changes              │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ Filter by current month:                 │
│ const { from, to } = getMonthDateRange() │
│ const filtered = addedTrips.filter(      │
│   trip => trip.date >= from &&           │
│           trip.date <= to                │
│ )                                        │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ Update rowsData (lines 1087-1105):      │
│ - Only add trips matching current month  │
│ - Check if not already in rowsData       │
│ - Append to rowsData                     │
│ - Update serverTotalTrips                │
└──────────────────────────────────────────┘
```

**Filtrado Server-Side:**
- WebSocket envía **TODOS** los trips (sin filtro de fecha)
- Cliente **filtra** por mes actual antes de agregar a `rowsData`
- Esto evita mostrar trips de otros meses en la tabla actual

#### 5.2 Update Event (Otro usuario edita trip)

```
┌──────────────────────────────────────────┐
│ Backend: Another user edits trip         │
│ WebSocket → "update" event               │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ updateTrip(tripId, updatedTrip)          │
│ → storeTrips updated                     │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ Update rowsData (lines 1107-1114):      │
│ - Only update if trip exists in rowsData │
│ - Map and replace with updated version   │
└──────────────────────────────────────────┘
```

**Importante:**
- Solo actualiza si el trip **ya está en `rowsData`**
- No agrega trips de otros meses

#### 5.3 Delete Event (Otro usuario elimina trip)

```
┌──────────────────────────────────────────┐
│ Backend: Another user deletes trip       │
│ WebSocket → "delete" event               │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ deleteTrip(tripId)                       │
│ → storeTrips updated                     │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ Update rowsData (lines 1091-1095):      │
│ - Filter out deleted trip                │
│ - Update serverTotalTrips                │
└──────────────────────────────────────────┘
```

---

## Casos de Uso

### Caso 1: Usuario A ve Enero, Usuario B agrega trip en Febrero

**Escenario:**
- Usuario A: viendo `/dashboard/locations/ORD/GEN?month=0&year=2026` (Enero)
- Usuario B: sube trips.xlsx con trips de Febrero 2026

**Flujo:**

1. **Usuario B sube trips:**
   - Backend inserta trips con `pick_up_date = 2026-02-XX`
   - WebSocket envía eventos `insert` a TODOS los clientes

2. **Usuario A recibe eventos WebSocket:**
   - `storeTrips` se actualiza (incluye trips de Febrero)
   - `availableMonths` se recalcula → **Ahora incluye Febrero**
   - MonthYearPicker **muestra Febrero** como disponible

3. **rowsData NO cambia:**
   - Filter by month: `trip.date >= 2026-01-01 && trip.date <= 2026-01-31`
   - Trips de Febrero **no pasan el filtro**
   - Tabla **no muestra los nuevos trips** (correcto!)

4. **Usuario A navega a Febrero:**
   - Click en MonthYearPicker → Febrero
   - `loadInitialTrips()` con `pick_up_date_from=2026-02-01`
   - **Ahora ve los trips de Febrero**

### Caso 2: Cambio de Airline (ORD/GEN → ORD/UAL)

**Escenario:**
- Usuario en `/dashboard/locations/ORD/GEN`
- Click dropdown → Selecciona "UAL"

**Flujo:**

1. **handleAirlineChange() (lines 820-822):**
   ```typescript
   router.push(`/dashboard/locations/ORD/UAL`)
   ```

2. **Component re-mounts con nuevos params:**
   - `code = "ORD"` (mismo)
   - `airline = "UAL"` (nuevo)

3. **WebSocket NO cambia:**
   - Sigue subscrito a `location_id`
   - `storeTrips` sigue teniendo **TODOS** los trips (GEN + UAL + otros)

4. **REST API filtra por airline:**
   ```
   GET /v1/locations/{id}/trips?airline=UAL&...
   ```
   - Solo devuelve trips con `airline = "UAL"`

5. **availableMonths se recalcula:**
   ```typescript
   // lines 973
   const months = extractAvailableMonths(storeTrips, "UAL")
   ```
   - Filtra `storeTrips` por airline
   - MonthYearPicker **solo muestra meses con trips de UAL**

### Caso 3: Paginación con Filtros Activos

**Escenario:**
- Location: ORD
- Airline: GEN
- Mes: Enero 2026
- Total trips: 150 (serverTotalTrips)
- Page size: 50

**Flujo:**

1. **Load inicial (skip=0):**
   ```
   GET /v1/locations/{id}/trips?
     airline=GEN&
     pick_up_date_from=2026-01-01&
     pick_up_date_to=2026-01-31&
     skip=0&
     limit=50
   ```
   - Response: 50 trips, total=150
   - `rowsData = [trip1...trip50]`
   - `nextSkip = 50`

2. **User scrolls → Load more (skip=50):**
   ```
   GET /v1/locations/{id}/trips?
     ...same filters...
     skip=50&
     limit=50
   ```
   - Response: 50 trips
   - `rowsData = [...prev, trip51...trip100]` (append)
   - `nextSkip = 100`

3. **User scrolls → Load more (skip=100):**
   ```
   GET /v1/locations/{id}/trips?
     ...same filters...
     skip=100&
     limit=50
   ```
   - Response: 50 trips
   - `rowsData = [...prev, trip101...trip150]` (append)
   - `nextSkip = 150`

4. **User scrolls → No more trips:**
   - Guard: `rowsData.length (150) >= serverTotalTrips (150)`
   - **No hace request**

### Caso 4: Trip Eliminado en Otro Mes

**Escenario:**
- Usuario A: viendo Enero (50 trips)
- Usuario B: elimina un trip de Febrero
- WebSocket envía evento `delete` del trip de Febrero

**Flujo:**

1. **storeTrips se actualiza:**
   - Trip de Febrero se elimina de `storeTrips`

2. **availableMonths se recalcula:**
   - Si era el último trip de Febrero → **Febrero desaparece del picker**

3. **rowsData NO cambia:**
   - Trip eliminado no estaba en `rowsData` (era de otro mes)
   - Tabla sigue mostrando los mismos 50 trips de Enero

---

## Diagrama de Flujo Completo

```
┌─────────────────────────────────────────────────────────────────┐
│                         PAGINADOR FLOW                          │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────┐
│ URL Parameters   │
│ /ORD/GEN?m=0&y=26│
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────┐
│                    DATA SOURCES                               │
├──────────────────────┬────────────────────────────────────────┤
│                      │                                        │
│   ┌─────────────┐   │   ┌──────────────┐                    │
│   │  WebSocket  │   │   │   REST API   │                    │
│   │  (Snapshot) │   │   │  (Paginated) │                    │
│   └──────┬──────┘   │   └──────┬───────┘                    │
│          │          │          │                             │
│          ▼          │          ▼                             │
│   ┌─────────────┐   │   ┌──────────────┐                    │
│   │ storeTrips  │   │   │   Filtered   │                    │
│   │ (ALL trips) │   │   │ by Airline + │                    │
│   │             │   │   │   Date Range │                    │
│   └──────┬──────┘   │   └──────┬───────┘                    │
└──────────┼──────────┴──────────┼────────────────────────────┘
           │                     │
           │  ┌──────────────────┘
           │  │
           ▼  ▼
    ┌──────────────────┐
    │   COMPUTATIONS   │
    ├──────────────────┤
    │ availableMonths  │← From storeTrips filtered by airline
    │ (for picker)     │
    ├──────────────────┤
    │    rowsData      │← From REST API (server-filtered)
    │ (table display)  │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │   UI RENDERING   │
    ├──────────────────┤
    │ MonthYearPicker  │← Shows availableMonths
    │    DataTable     │← Shows rowsData (paginated)
    └──────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                         INTERACTIONS                             │
└─────────────────────────────────────────────────────────────────┘

1. CHANGE MONTH/YEAR
   MonthYearPicker → onMonthYearChange()
   ↓
   Reset state → loadInitialTrips()
   ↓
   REST API with new date range
   ↓
   Update rowsData

2. SCROLL DOWN (Load More)
   IntersectionObserver → loadMoreTrips()
   ↓
   Guard: Already loading? All loaded?
   ↓
   REST API with skip=nextSkip
   ↓
   Append to rowsData

3. UPLOAD TRIPS
   UpdateButton → 'trips-uploaded' event
   ↓
   Reset + loadInitialTrips() + wsReconnect()
   ↓
   REST loads filtered data
   ↓
   WebSocket snapshot refreshes storeTrips
   ↓
   availableMonths recalculated

4. WEBSOCKET EVENT (insert/update/delete)
   WebSocket → handleTripEvent()
   ↓
   Update storeTrips
   ↓
   Filter by current month → Update rowsData (if applicable)
   ↓
   Recalculate availableMonths

┌─────────────────────────────────────────────────────────────────┐
│                      KEY PRINCIPLES                              │
└─────────────────────────────────────────────────────────────────┘

1. REST API is SOURCE OF TRUTH for table data
   - Server-side pagination (skip/limit)
   - Server-side filtering (airline, date range)

2. WebSocket is for REAL-TIME UPDATES only
   - Maintains full snapshot in storeTrips
   - Updates are filtered client-side before applying to rowsData

3. SEPARATION OF CONCERNS:
   - storeTrips: ALL trips (WebSocket, unfiltered by date)
   - rowsData: DISPLAYED trips (REST API, filtered by airline + date)

4. MONTH PICKER uses storeTrips:
   - Shows ALL months with trips (for the airline)
   - Not limited to currently loaded pages

5. PAGINATION is STATELESS:
   - Each page load is independent
   - Skip/limit are the only state
   - No client-side caching of previous pages

6. FILTERS are SERVER-SIDE:
   - Airline filter → Query param
   - Date filter → Query params (from/to)
   - Backend does the heavy lifting
```

---

## Archivos Relevantes

### Frontend
- **Main Component**: `src/app/(main)/dashboard/locations/[code]/[airline]/schedule-dashboard-client.tsx`
- **WebSocket Provider**: `src/providers/trips-websocket-provider.tsx`
- **WebSocket Hook**: `src/hooks/use-websocket-trips.ts`
- **Trips Store**: `src/stores/trips/trips-store.ts`
- **Available Months**: `src/lib/trips/available-months.ts`
- **Update Button**: `src/components/trips/update-trips-button.tsx`
- **Month Picker**: `src/components/ui/month-year-picker.tsx`

### Backend
- **Trips API**: `/v1/locations/{location_id}/trips`
  - Query params: `skip`, `limit`, `airline`, `pick_up_date_from`, `pick_up_date_to`
- **Upload API**: `/v1/locations/{location_id}/trips/upload`
- **WebSocket**: Real-time events (insert, update, delete, snapshot)

---

## Conclusión

El sistema utiliza un enfoque híbrido inteligente:

✅ **REST API**: Paginación server-side + filtros server-side
✅ **WebSocket**: Real-time updates + month availability
✅ **Client filtering**: Solo aplica trips del WebSocket que coincidan con el mes actual
✅ **Separation of concerns**: `storeTrips` (full snapshot) vs `rowsData` (filtered view)

Este diseño permite:
- **Escalabilidad**: Backend hace el trabajo pesado
- **Real-time**: Cambios instantáneos via WebSocket
- **Performance**: Solo carga data necesaria (paginada + filtrada)
- **UX fluido**: Month picker siempre actualizado, tabla sincronizada

---

**Última actualización**: 2026-01-15
**Fix aplicado**: WebSocket reconnect después de upload para actualizar availableMonths
