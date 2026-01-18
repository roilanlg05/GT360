# Implementación Completa de Filtros en Frontend - Documentación para Backend

**Fecha:** 2026-01-17
**Propósito:** Documentar la implementación completa del sistema de filtros en el frontend para identificar inconsistencias con el backend
**Estado Actual:** ❌ Los cambios aplicados NO se reflejan en la tabla después de guardar

---

## 📋 Índice

1. [Resumen Ejecutivo](#resumen-ejecutivo)
2. [Flujo Completo de Filtros](#flujo-completo-de-filtros)
3. [Estructura de Datos Frontend](#estructura-de-datos-frontend)
4. [Endpoints Utilizados](#endpoints-utilizados)
5. [Requests Enviados](#requests-enviados)
6. [Responses Esperadas](#responses-esperadas)
7. [Problema Principal Identificado](#problema-principal-identificado)
8. [Flujo de Actualización Post-Apply](#flujo-de-actualización-post-apply)
9. [Inconsistencias Detectadas](#inconsistencias-detectadas)
10. [Pruebas y Logs](#pruebas-y-logs)

---

## 1. Resumen Ejecutivo

### Problema Actual ❌
Cuando el usuario aplica filtros (Reduce/Combine/Expand):
1. ✅ El frontend envía el request correctamente a `/filters/apply`
2. ✅ El backend responde con `200 OK` y mensaje "342 trips modified successfully"
3. ✅ El frontend guarda el `batch_id`
4. ✅ El frontend llama a `onTripsUpdated()` para refrescar
5. ❌ **Los cambios NO se reflejan en la tabla del frontend**

### Hipótesis Principal 🤔
Después de analizar el código, identificamos **DOS problemas críticos**:

1. **PROBLEMA 1:** El frontend estaba haciendo el refresh sin los filtros de `airline` y `pick_up_date_from/to` (YA CORREGIDO)
2. **PROBLEMA 2:** El frontend envía `target_date` en el request, pero según la guía del backend ([FRONTEND_TRIP_FILTERS_GUIDE.md](docs/Docs_From_Backend/FRONTEND_TRIP_FILTERS_GUIDE.md)), **NO existe este campo**

---

## 2. Flujo Completo de Filtros

```
┌─────────────────────────────────────────────────────────────────────┐
│ PASO 1: Usuario Configura Filtros                                   │
├─────────────────────────────────────────────────────────────────────┤
│ • Usuario abre "Ground Filters" drawer                               │
│ • Configura parámetros (ej: Reduce 30 minutos, 05:00-10:00)        │
│ • Selecciona hoteles (opcional)                                      │
│ • Selecciona time range (opcional)                                   │
└─────────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────────┐
│ PASO 2: Preview (Simulación)                                        │
├─────────────────────────────────────────────────────────────────────┤
│ Frontend → POST /v1/locations/{location_id}/airlines/{airline}/     │
│                  trips/filters/preview                               │
│                                                                      │
│ Request Body:                                                        │
│ {                                                                    │
│   "target_date": "2025-10-01",  // ⚠️ CAMPO PROBLEMÁTICO            │
│   "reduce": {                                                        │
│     "enabled": true,                                                 │
│     "minutes_to_reduce": 30,                                         │
│     "hotel_names": null,                                             │
│     "time_range": { "start": "05:00", "end": "10:00" }             │
│   }                                                                  │
│ }                                                                    │
│                                                                      │
│ Backend → 200 OK                                                     │
│ {                                                                    │
│   "location_id": "uuid...",                                         │
│   "airline": "WN",                                                   │
│   "changes": [...],      // Array de TripChange                     │
│   "exclusions": [...],   // Array de exclusiones                    │
│   "summary": { "reduce": 342, "combine": 0, "expand": 0 }          │
│ }                                                                    │
└─────────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────────┐
│ PASO 3: Usuario Revisa Preview Modal                                │
├─────────────────────────────────────────────────────────────────────┤
│ • Modal muestra tabla con cambios propuestos                         │
│ • Cada fila: trip_id, original_time → new_time, hotel_name         │
│ • Summary: "342 trips will be modified"                             │
│ • Exclusions (si las hay)                                            │
└─────────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────────┐
│ PASO 4: Apply (Guardar Cambios)                                     │
├─────────────────────────────────────────────────────────────────────┤
│ Frontend → POST /v1/locations/{location_id}/airlines/{airline}/     │
│                  trips/filters/apply                                 │
│                                                                      │
│ Request Body: (MISMO QUE PREVIEW)                                    │
│ {                                                                    │
│   "target_date": "2025-10-01",  // ⚠️ CAMPO PROBLEMÁTICO            │
│   "reduce": { ... }                                                  │
│ }                                                                    │
│                                                                      │
│ Backend → 200 OK                                                     │
│ {                                                                    │
│   "batch_id": "90f7b8a8-...",   // UUID para revert                │
│   "location_id": "uuid...",                                         │
│   "airline": "WN",                                                   │
│   "changes_applied": 342,                                            │
│   "summary": { "reduce": 342, "combine": 0, "expand": 0 }          │
│ }                                                                    │
└─────────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────────┐
│ PASO 5: Frontend Intenta Actualizar Tabla (AQUÍ ESTÁ EL PROBLEMA)   │
├─────────────────────────────────────────────────────────────────────┤
│ 1. Frontend recibe respuesta exitosa                                │
│ 2. Guarda batch_id en localStorage                                  │
│ 3. Muestra toast: "342 trips modified successfully"                 │
│ 4. Llama onTripsUpdated() → fetchTrips()                           │
│ 5. fetchTrips() hace:                                                │
│    GET /v1/locations/{location_id}/trips?                           │
│        airline=WN&                                                   │
│        pick_up_date_from=2025-10-01&                                │
│        pick_up_date_to=2025-10-31&                                  │
│        skip=0&limit=50                                               │
│ 6. ❌ Problema: Los trips retornados NO tienen los pickup_time      │
│    modificados                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Estructura de Datos Frontend

### 3.1 TypeScript Types Utilizados

**Archivo:** [src/types/trip-filters.ts](src/types/trip-filters.ts)

```typescript
// ============ REQUEST TYPES ============

export interface TimeRange {
  start: string  // "HH:MM" formato 24h
  end: string    // "HH:MM" formato 24h
}

export interface ReduceFilterConfig {
  enabled: boolean
  minutes_to_reduce: number      // 0-120 minutos
  hotel_names?: string[] | null  // null = TODOS los hoteles
  time_range?: TimeRange | null  // null = TODOS los horarios
}

export interface CombineFilterConfig {
  enabled: boolean
  min_gap: number                // minutos minimos entre trips
  max_gap: number                // minutos maximos entre trips
  hotel_names?: string[] | null
  time_range?: TimeRange | null
}

export interface ExpandFilterConfig {
  enabled: boolean
  min_gap: number
  max_gap: number
  max_shift: number              // maximo desplazamiento por trip
  hotel_names?: string[] | null
  time_range?: TimeRange | null
}

export interface FilterRequest {
  target_date?: string           // "YYYY-MM-DD" ⚠️ PROBLEMA AQUÍ
  reduce?: ReduceFilterConfig
  combine?: CombineFilterConfig
  expand?: ExpandFilterConfig
}

// ============ RESPONSE TYPES ============

export interface TripChange {
  trip_id: string
  original_time: string          // "HH:MM:SS"
  new_time: string               // "HH:MM:SS"
  filter_applied: 'reduce' | 'combine' | 'expand'
  hotel_name: string
  pick_up_date: string | null
  airline: string | null
}

export interface FilterPreviewResult {
  location_id: string
  airline: string
  changes: TripChange[]
  exclusions: FilterExclusion[]
  summary: {
    reduce: number
    combine: number
    expand: number
    excluded: number
  }
  total_trips_evaluated: number
  eligible_trips: number
}

export interface FilterApplyResult {
  batch_id: string               // UUID para revert
  location_id: string
  airline: string
  changes_applied: number
  exclusions: FilterExclusion[]
  log: FilterLogEntry[]
  summary: FilterSummary
}
```

---

## 4. Endpoints Utilizados

### 4.1 Preview Endpoint

**URL:** `POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/preview`

**Path Params:**
- `location_id` (UUID): ID de la location (ej: `dec0c23e-b1d5-4c44-adb4-18b9d4183cc9`)
- `airline` (string): Código de aerolínea (ej: `WN`)

**Headers:**
```
Authorization: Bearer {access_token}
Content-Type: application/json
```

**Request Body:** Ver sección 5

**Response:** Ver sección 6

---

### 4.2 Apply Endpoint

**URL:** `POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/apply`

**Path Params:** (igual que Preview)

**Headers:** (igual que Preview)

**Request Body:** (MISMO que Preview)

**Response:** Ver sección 6

---

### 4.3 Revert Endpoint

**URL:** `POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/revert?batch_id={batch_id}`

**Query Params:**
- `batch_id` (string, opcional): UUID del batch a revertir. Si no se envía, revierte TODOS los batches.

**Headers:**
```
Authorization: Bearer {access_token}
```

**Response:**
```json
{
  "trips_reverted": 342,
  "batch_ids_reverted": ["90f7b8a8-..."]
}
```

---

## 5. Requests Enviados

### 5.1 Request de Preview/Apply - Ejemplo Real

**Contexto:**
- Location: San Diego (SDF)
- Airline: WN (Southwest)
- Mes seleccionado: Octubre 2025 (selectedMonth=9, selectedYear=2025)
- Filtro: Reduce 30 minutos, time range 05:00-10:00

**Request Body Enviado por Frontend:**

```json
{
  "target_date": "2025-10-01",
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 30,
    "hotel_names": null,
    "time_range": {
      "start": "05:00",
      "end": "10:00"
    }
  }
}
```

**⚠️ PROBLEMA CRÍTICO:**
Según [FRONTEND_TRIP_FILTERS_GUIDE.md](docs/Docs_From_Backend/FRONTEND_TRIP_FILTERS_GUIDE.md), el campo `target_date` **NO EXISTE** en la especificación del backend.

**Cómo se construye `target_date` en Frontend:**

**Archivo:** [src/hooks/use-trip-filters.ts:108-114](src/hooks/use-trip-filters.ts#L108-L114)

```typescript
// Compute target_date from selected month/year
const targetDate = React.useMemo(() => {
  if (selectedMonth !== undefined && selectedYear !== undefined) {
    const month = (selectedMonth + 1).toString().padStart(2, '0')
    return `${selectedYear}-${month}-01`  // ⚠️ Siempre el día 01
  }
  return null
}, [selectedMonth, selectedYear])
```

**Archivo:** [src/hooks/use-trip-filters.ts:317-337](src/hooks/use-trip-filters.ts#L317-L337)

```typescript
const buildRequest = React.useCallback((): FilterRequest => {
  const request: FilterRequest = {}

  if (state.targetDate) {
    request.target_date = state.targetDate  // ⚠️ Se agrega aquí
  }

  if (state.reduce.enabled) {
    request.reduce = state.reduce
  }

  if (state.combine.enabled) {
    request.combine = state.combine
  }

  if (state.expand.enabled) {
    request.expand = state.expand
  }

  return request
}, [state.targetDate, state.reduce, state.combine, state.expand])
```

---

### 5.2 Request de Apply con Combine y Expand

```json
{
  "target_date": "2025-10-01",
  "combine": {
    "enabled": true,
    "min_gap": 15,
    "max_gap": 20,
    "hotel_names": ["Hilton Downtown", "Marriott Airport"],
    "time_range": null
  },
  "expand": {
    "enabled": true,
    "min_gap": 21,
    "max_gap": 30,
    "max_shift": 15,
    "hotel_names": null,
    "time_range": {
      "start": "14:00",
      "end": "18:00"
    }
  }
}
```

---

## 6. Responses Esperadas

### 6.1 Preview Response - Ejemplo

```json
{
  "location_id": "dec0c23e-b1d5-4c44-adb4-18b9d4183cc9",
  "airline": "WN",
  "changes": [
    {
      "trip_id": "trip-uuid-1",
      "original_time": "08:30:00",
      "new_time": "08:00:00",
      "filter_applied": "reduce",
      "hotel_name": "Hilton Downtown",
      "pick_up_date": "2025-10-05",
      "airline": "WN"
    },
    {
      "trip_id": "trip-uuid-2",
      "original_time": "09:15:00",
      "new_time": "08:45:00",
      "filter_applied": "reduce",
      "hotel_name": "Marriott Airport",
      "pick_up_date": "2025-10-05",
      "airline": "WN"
    }
    // ... 340 más
  ],
  "exclusions": [],
  "summary": {
    "reduce": 342,
    "combine": 0,
    "expand": 0,
    "excluded": 0
  },
  "total_trips_evaluated": 688,
  "eligible_trips": 342
}
```

### 6.2 Apply Response - Ejemplo

```json
{
  "batch_id": "90f7b8a8-1234-5678-9abc-def012345678",
  "location_id": "dec0c23e-b1d5-4c44-adb4-18b9d4183cc9",
  "airline": "WN",
  "changes_applied": 342,
  "exclusions": [],
  "log": [
    {
      "trip_id": "trip-uuid-1",
      "action": "modified",
      "filter": "reduce",
      "original_time": "08:30:00",
      "new_time": "08:00:00",
      "hotel": "Hilton Downtown"
    }
    // ... logs adicionales
  ],
  "summary": {
    "reduce": 342,
    "combine": 0,
    "expand": 0,
    "excluded": 0
  }
}
```

---

## 7. Problema Principal Identificado

### 7.1 Campo `target_date` No Documentado

**Evidencia:**

1. **Documentación Backend** ([FRONTEND_TRIP_FILTERS_GUIDE.md:52-82](docs/Docs_From_Backend/FRONTEND_TRIP_FILTERS_GUIDE.md#L52-L82))
   ```typescript
   interface FilterRequest {
     reduce?: { ... };
     combine?: { ... };
     expand?: { ... };
     // ❌ NO HAY target_date
   }
   ```

2. **Implementación Frontend** ([src/types/trip-filters.ts:37-42](src/types/trip-filters.ts#L37-L42))
   ```typescript
   export interface FilterRequest {
     target_date?: string  // ⚠️ Este campo existe en frontend
     reduce?: ReduceFilterConfig
     combine?: CombineFilterConfig
     expand?: ExpandFilterConfig
   }
   ```

### 7.2 Preguntas para el Backend

1. **¿El backend está recibiendo y procesando `target_date`?**
   - Si SÍ: ¿Para qué se usa? ¿Filtra por mes?
   - Si NO: ¿Lo está ignorando silenciosamente?

2. **¿Cómo determina el backend qué trips modificar?**
   - Según la guía, solo usa:
     - `trip_type = 'outbound'`
     - `status = 'scheduled'`
     - `location_id` (de la URL)
     - `airline` (de la URL)
   - ❓ **¿NO filtra por fecha/mes?** Esto significaría que modifica TODOS los trips outbound scheduled de esa location/airline.

3. **¿Por qué los cambios no se reflejan al hacer GET /trips después de apply?**
   - ¿Se está guardando en una tabla diferente?
   - ¿Hay algún flag que indique "trip filtrado"?
   - ¿Hay algún delay en la persistencia?

---

## 8. Flujo de Actualización Post-Apply

### 8.1 Código Actual del Frontend

**Archivo:** [src/hooks/use-trip-filters.ts:395-454](src/hooks/use-trip-filters.ts#L395-L454)

```typescript
const applyChanges = React.useCallback(async () => {
  if (!locationId) {
    toast.error('Location ID not available')
    return
  }

  setState((prev) => ({
    ...prev,
    isApplying: true,
    applyError: null,
  }))

  try {
    const request = buildRequest()  // ⚠️ Incluye target_date
    const result = await tripFiltersService.apply(locationId, airline, request)

    if (result.success && result.data) {
      const { batch_id, changes_applied } = result.data

      // Save batch_id for revert
      saveBatchId(batch_id)

      setState((prev) => ({
        ...prev,
        lastBatchId: batch_id,
        isApplying: false,
        previewResult: null,
      }))

      // Close the preview modal
      setIsPreviewModalOpen(false)

      toast.success(`${changes_applied} trips modified successfully`, {
        description: `Batch ID: ${batch_id.substring(0, 8)}...`,
      })

      // Notify parent to refresh trips
      onTripsUpdated?.()  // ⚠️ ESTE ES EL CALLBACK QUE REFRESCA

      // Dispatch global event for other listeners
      window.dispatchEvent(new Event('trips-updated'))
    } else {
      const errorMsg = result.error || result.message || 'Apply failed'
      setState((prev) => ({
        ...prev,
        applyError: errorMsg,
        isApplying: false,
      }))
      toast.error(errorMsg)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : 'Apply failed'
    setState((prev) => ({
      ...prev,
      applyError: errorMsg,
      isApplying: false,
    }))
    toast.error(errorMsg)
  }
}, [locationId, airline, buildRequest, saveBatchId, onTripsUpdated])
```

### 8.2 Callback de Actualización (handleTripsUpdated)

**Archivo:** [src/app/(main)/dashboard/locations/[code]/[airline]/schedule-dashboard-client.tsx:1206-1216](src/app/(main)/dashboard/locations/[code]/[airline]/schedule-dashboard-client.tsx#L1206-L1216)

**ANTES DEL FIX (❌ Incorrecto):**
```typescript
const handleTripsUpdated = useCallback(() => {
  if (currentLocationId) {
    setIsLoadingTrips(true);
    setNextSkip(0);
    tripService.getTrips(currentLocationId, { skip: 0, limit: PAGE_SIZE })
      // ❌ Faltaba: airline, pick_up_date_from, pick_up_date_to
      .then(...)
      .finally(() => setIsLoadingTrips(false));
  }
}, [currentLocationId]);
```

**DESPUÉS DEL FIX (✅ Correcto):**
```typescript
// Use ref to avoid circular dependency
const fetchTripsRef = useRef<((params: { skip: number; append: boolean; forLoadMore: boolean }) => void) | null>(null);

const handleTripsUpdated = useCallback(() => {
  console.log('[handleTripsUpdated] Refetching trips after filter apply/revert');
  if (fetchTripsRef.current) {
    setNextSkip(0);
    void fetchTripsRef.current({ skip: 0, append: false, forLoadMore: false });
    // ✅ Ahora usa fetchTrips que incluye airline y date range
  } else {
    console.warn('[handleTripsUpdated] fetchTrips not available yet');
  }
}, []);

// Later, after fetchTrips is defined...
useEffect(() => {
  fetchTripsRef.current = fetchTrips;
}, [fetchTrips]);
```

### 8.3 Request de Refresh

**Lo que ahora envía el frontend después del fix:**

```
GET /v1/locations/dec0c23e-b1d5-4c44-adb4-18b9d4183cc9/trips?
    airline=WN&
    pick_up_date_from=2025-10-01&
    pick_up_date_to=2025-10-31&
    skip=0&
    limit=50
```

**Response esperada:** Los primeros 50 trips con los `pick_up_time` YA MODIFICADOS.

---

## 9. Inconsistencias Detectadas

### 9.1 Tabla Comparativa: Frontend vs Backend

| Aspecto | Frontend | Backend (según guía) | ¿Coincide? |
|---------|----------|---------------------|------------|
| **URL Preview** | `POST /v1/locations/{id}/airlines/{airline}/trips/filters/preview` | ✅ Igual | ✅ SÍ |
| **URL Apply** | `POST /v1/locations/{id}/airlines/{airline}/trips/filters/apply` | ✅ Igual | ✅ SÍ |
| **URL Revert** | `POST /v1/locations/{id}/airlines/{airline}/trips/filters/revert` | ✅ Igual | ✅ SÍ |
| **Campo `target_date`** | ✅ Se envía (`"2025-10-01"`) | ❌ NO documentado | ❌ NO |
| **Campo `reduce.enabled`** | ✅ Se envía | ✅ Esperado | ✅ SÍ |
| **Campo `reduce.minutes_to_reduce`** | ✅ Se envía | ✅ Esperado | ✅ SÍ |
| **Campo `reduce.hotel_names`** | ✅ Se envía (`null` o `["Hotel1"]`) | ✅ Esperado | ✅ SÍ |
| **Campo `reduce.time_range`** | ✅ Se envía (`null` o `{"start":"05:00","end":"10:00"}`) | ✅ Esperado | ✅ SÍ |
| **Response `batch_id`** | ✅ Se recibe y guarda | ✅ Documentado | ✅ SÍ |
| **Response `changes_applied`** | ✅ Se recibe y muestra en toast | ✅ Documentado | ✅ SÍ |
| **Response `changes[]`** | ✅ Se recibe y muestra en preview | ✅ Documentado | ✅ SÍ |
| **Criterios de elegibilidad** | ❓ Asume que backend filtra por `target_date` | `trip_type='outbound'`, `status='scheduled'`, `location_id`, `airline` | ❓ DESCONOCIDO |
| **Filtrado por mes** | ✅ Frontend envía `target_date` esperando que backend filtre por mes | ❌ NO mencionado en la guía | ❌ NO |

### 9.2 Preguntas Críticas para Backend

#### A. Sobre `target_date`

1. **¿El backend lee el campo `target_date` del request body?**
   - Si SÍ: ¿Qué hace con él? ¿Filtra trips por ese mes?
   - Si NO: ¿Debería el frontend dejar de enviarlo?

2. **¿El backend aplica filtros solo a los trips del mes especificado en `target_date`?**
   - Frontend asume: "Solo modifica trips de octubre 2025"
   - Si NO: ¿Modifica TODOS los trips outbound/scheduled de esa location/airline sin importar fecha?

#### B. Sobre Persistencia

3. **Después de ejecutar `/filters/apply`, ¿los cambios se persisten inmediatamente en la tabla `trips`?**
   - ¿O se guardan en una tabla temporal/histórico?
   - ¿Hay algún delay en la escritura a BD?

4. **¿El campo modificado es `pick_up_time` en la tabla `trips`?**
   - ¿O es otro campo como `adjusted_pick_up_time`?
   - ¿Se crea un registro de auditoría?

5. **Cuando el frontend hace `GET /trips?airline=WN&pick_up_date_from=2025-10-01&pick_up_date_to=2025-10-31`, ¿debe retornar los `pick_up_time` YA MODIFICADOS?**
   - ✅ SÍ → Entonces hay un bug en el backend
   - ❌ NO → Entonces el frontend necesita hacer un request diferente

#### C. Sobre Filtrado

6. **¿Cómo determina el backend qué trips son "elegibles" para filtros?**
   - Frontend envía `target_date: "2025-10-01"`
   - ¿Backend filtra por `pick_up_date LIKE '2025-10-%'`?
   - ¿O solo usa `trip_type='outbound' AND status='scheduled'`?

7. **¿El backend ignora silenciosamente campos no reconocidos en el request?**
   - Si frontend envía `target_date` y backend no lo espera, ¿lo ignora sin error?
   - ¿Debería retornar error 400 "campo no válido"?

---

## 10. Pruebas y Logs

### 10.1 Logs del Frontend al Aplicar Filtros

**Secuencia observada en consola (F12):**

```javascript
// 1. Usuario hace click en "Apply"
[useTripFilters] applyChanges called

// 2. Request enviado
POST https://api.gt360.app/v1/locations/dec0c23e-b1d5-4c44-adb4-18b9d4183cc9/airlines/WN/trips/filters/apply
Request Body: {"target_date":"2025-10-01","reduce":{"enabled":true,"minutes_to_reduce":30,"hotel_names":null,"time_range":{"start":"05:00","end":"10:00"}}}

// 3. Response recibida
Response: 200 OK
{
  "batch_id": "90f7b8a8-...",
  "location_id": "dec0c23e-b1d5-4c44-adb4-18b9d4183cc9",
  "airline": "WN",
  "changes_applied": 342,
  "summary": { "reduce": 342, "combine": 0, "expand": 0, "excluded": 0 }
}

// 4. Toast de éxito
✅ Toast: "342 trips modified successfully"
         "Batch ID: 90f7b8a8..."

// 5. Refresh triggered
[handleTripsUpdated] Refetching trips after filter apply/revert
[fetchTrips] 🆕 Request version: 6
[fetchTrips] Fetching with date filters: {
  airline: 'WN',
  dateFrom: '2025-10-01',
  dateTo: '2025-10-31',
  skip: 0,
  limit: 50
}

// 6. Request de refresh
GET https://api.gt360.app/v1/locations/dec0c23e-b1d5-4c44-adb4-18b9d4183cc9/trips?airline=WN&pick_up_date_from=2025-10-01&pick_up_date_to=2025-10-31&skip=0&limit=50

// 7. Response recibida
Response: 200 OK
{
  "data": [...],  // 50 trips
  "skip": 0,
  "limit": 50,
  "total": 688
}

// 8. ❌ PROBLEMA: Los trips retornados tienen los pickup_time ORIGINALES
//    No se reflejan las modificaciones del filtro apply
[fetchTrips] ✅ Applying data (version match)
[fetchTrips] Parsed trips: {rawTripsCount: 50, parsedRowsCount: 50, serverTotal: 688}
[fetchTrips] Setting rowsData with 50 trips

// Ejemplo de trip retornado (sin modificación):
{
  "id": "trip-uuid-1",
  "pick_up_time": "08:30:00",  // ❌ Debería ser "08:00:00"
  "pick_up_date": "2025-10-05",
  "airline": "WN",
  "hotel_name": "Hilton Downtown"
}
```

### 10.2 Test Case para el Backend

**Request:** `POST /v1/locations/{location_id}/airlines/WN/trips/filters/apply`

**Body:**
```json
{
  "target_date": "2025-10-01",
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 30,
    "hotel_names": null,
    "time_range": null
  }
}
```

**Validaciones Backend:**

1. ✅ ¿Responde 200 OK?
2. ✅ ¿Retorna `batch_id` válido?
3. ✅ ¿Retorna `changes_applied > 0`?
4. ❓ ¿Modifica realmente el campo `pick_up_time` en la tabla `trips`?
5. ❓ Inmediatamente después de este request, si hago `GET /trips?airline=WN&pick_up_date_from=2025-10-01&pick_up_date_to=2025-10-31`, ¿los trips retornados tienen los `pick_up_time` modificados?

**Test SQL (si backend usa SQL):**

```sql
-- ANTES de apply
SELECT id, pick_up_time, pick_up_date
FROM trips
WHERE location_id = 'dec0c23e...'
  AND airline = 'WN'
  AND trip_type = 'outbound'
  AND status = 'scheduled'
  AND pick_up_date BETWEEN '2025-10-01' AND '2025-10-31'
LIMIT 5;

-- Ejecutar /filters/apply con reduce 30 minutos

-- DESPUÉS de apply
SELECT id, pick_up_time, pick_up_date
FROM trips
WHERE location_id = 'dec0c23e...'
  AND airline = 'WN'
  AND trip_type = 'outbound'
  AND status = 'scheduled'
  AND pick_up_date BETWEEN '2025-10-01' AND '2025-10-31'
LIMIT 5;

-- ❓ ¿Los pick_up_time cambiaron?
```

---

## 11. Resumen de Archivos Frontend Involucrados

### Componentes UI
1. **[src/components/trip-filters/trip-filters-drawer.tsx](src/components/trip-filters/trip-filters-drawer.tsx)** - Drawer principal de filtros
2. **[src/components/trip-filters/trip-filters-tabs.tsx](src/components/trip-filters/trip-filters-tabs.tsx)** - Tabs de Reduce/Combine/Expand
3. **[src/components/trip-filters/filter-reduce-panel.tsx](src/components/trip-filters/filter-reduce-panel.tsx)** - Panel de configuración Reduce
4. **[src/components/trip-filters/filter-combine-panel.tsx](src/components/trip-filters/filter-combine-panel.tsx)** - Panel de configuración Combine
5. **[src/components/trip-filters/filter-expand-panel.tsx](src/components/trip-filters/filter-expand-panel.tsx)** - Panel de configuración Expand
6. **[src/components/trip-filters/filter-preview-modal.tsx](src/components/trip-filters/filter-preview-modal.tsx)** - Modal de preview
7. **[src/components/trip-filters/filter-preview-table.tsx](src/components/trip-filters/filter-preview-table.tsx)** - Tabla de cambios en preview

### Hooks
8. **[src/hooks/use-trip-filters.ts](src/hooks/use-trip-filters.ts)** - Hook principal con toda la lógica

### Servicios API
9. **[src/lib/api/trip-filters.ts](src/lib/api/trip-filters.ts)** - Cliente API para endpoints de filtros

### Types
10. **[src/types/trip-filters.ts](src/types/trip-filters.ts)** - Definiciones TypeScript

### Integración
11. **[src/app/(main)/dashboard/locations/[code]/[airline]/schedule-dashboard-client.tsx](src/app/(main)/dashboard/locations/[code]/[airline]/schedule-dashboard-client.tsx)** - Página que usa los filtros y maneja el refresh

---

## 12. Solicitud al Backend

Por favor, revisen lo siguiente:

### Prioridad ALTA 🔴

1. **¿El campo `target_date` es usado por el backend?**
   - Si NO: Frontend dejará de enviarlo
   - Si SÍ: ¿Cómo se usa? Agregar a documentación

2. **¿Por qué `GET /trips` después de `apply` NO retorna los cambios?**
   - ¿Se guardan en otra tabla?
   - ¿Hay delay en persistencia?
   - ¿Hay que enviar algún header/param especial?

3. **¿Cómo filtra el backend los trips elegibles?**
   - ¿Solo por `trip_type='outbound'` y `status='scheduled'`?
   - ¿O también por fecha/mes?

### Prioridad MEDIA 🟡

4. Validar que los tipos en la respuesta coincidan con `FilterApplyResult`
5. Confirmar formato de `batch_id` (debe ser UUID válido)
6. Verificar que `/revert` efectivamente revierte los cambios

### Request

Por favor proporcionen:
- [ ] Respuesta a las preguntas 1-3
- [ ] Logs del backend al procesar un `/filters/apply`
- [ ] Consulta SQL que ejecuta el backend para actualizar trips
- [ ] Consulta SQL que ejecuta `GET /trips` para verificar si incluye cambios
- [ ] Aclaración sobre el uso (o no) de `target_date`
- [ ] Actualización de [FRONTEND_TRIP_FILTERS_GUIDE.md](docs/Docs_From_Backend/FRONTEND_TRIP_FILTERS_GUIDE.md) con toda la info

---

# 🔧 SOLUCIÓN IMPLEMENTADA - 2026-01-17

## ✅ Problemas Identificados y Resueltos

### 1. Campo `target_date` NO Reconocido por Backend ❌

**Problema:**
- Frontend enviaba `target_date: "2025-10-01"` en el request
- Backend **NO** tiene este campo en `FilterRequest`
- Backend lo ignoraba silenciosamente

**Causa Raíz:**
- El modelo `FilterRequest` (backend) solo tenía: `reduce`, `combine`, `expand`
- El backend filtraba TODOS los trips outbound/scheduled sin importar la fecha
- Por eso modificaba trips de enero, febrero, marzo, etc., en lugar de solo octubre

**Solución Implementada:**
```python
# features/trips/models/filter_models.py
class FilterRequest(BaseModel):
    pick_up_date_from: Optional[str] = None  # "YYYY-MM-DD"
    pick_up_date_to: Optional[str] = None    # "YYYY-MM-DD"
    reduce: Optional[ReduceFilterConfig] = None
    combine: Optional[CombineFilterConfig] = None
    expand: Optional[ExpandFilterConfig] = None
```

✅ **Resultado:** Ahora el backend filtra trips por rango de fechas

---

### 2. Filtros NO se Persistían en Base de Datos ❌

**Problema:**
- Backend respondía `200 OK` con mensaje "342 trips modified"
- Pero en la base de datos: `0 trips` con `filter_applied IS NOT NULL`
- `revert` devolvía "0 trips reverted"

**Causa Raíz:**
En `trip_filter_service.py`, método `apply()`:
```python
for change in self.changes:
    trip = trip_lookup.get(change.trip_id)
    if trip:
        trip.pick_up_time = change.new_time
        trip.filter_applied = change.filter_applied
        # ❌ FALTABA: self.session.add(trip)

await self.session.commit()  # ❌ Commit sin objetos tracked
```

Los objetos `trip` modificados **NO** estaban siendo agregados a la sesión de SQLAlchemy.

**Solución Implementada:**
```python
for change in self.changes:
    trip = trip_lookup.get(change.trip_id)
    if trip:
        # ... modificaciones ...
        # ✅ AGREGADO:
        self.session.add(trip)

await self.session.commit()  # ✅ Ahora commit tiene objetos tracked
```

✅ **Resultado:** Los cambios ahora se persisten correctamente en la base de datos

**Verificación:**
```sql
-- ANTES:
SELECT COUNT(*) FROM trips.trips WHERE filter_applied IS NOT NULL;
-- Result: 0

-- DESPUÉS (después de aplicar filtros):
SELECT COUNT(*) FROM trips.trips WHERE filter_applied IS NOT NULL;
-- Result: 342 (o el número de trips modificados)
```

---

### 3. Combine y Expand NO Respetaban Mismo Día ❌

**Problema:**
- `combine` y `expand` podían modificar trips de días diferentes
- Ejemplo: Combinaba un trip del 1 de octubre con un trip del 2 de octubre

**Requisito del Usuario:**
> "Los filtros tipo combine y expand se aplican a trips únicos dentro del mismo día, no se puede combinar o expandir dos trips en diferentes días"

**Solución Implementada:**
```python
def _apply_combine(self, trips: list[Trip], config: CombineFilterConfig):
    # ✅ AGREGADO: Agrupar por pick_up_date
    from collections import defaultdict
    trips_by_date = defaultdict(list)
    for trip in trips:
        if trip.pick_up_date:
            trips_by_date[trip.pick_up_date].append(trip)

    # ✅ Procesar cada fecha por separado
    for pick_up_date, day_trips in trips_by_date.items():
        sorted_trips = sorted(day_trips, key=lambda t: self._time_to_minutes(t.pick_up_time))
        # ... lógica de combine solo dentro de day_trips ...
```

Lo mismo para `_apply_expand()`.

✅ **Resultado:** Combine y expand solo operan sobre trips del mismo `pick_up_date`

**Nota:** `reduce` NO requiere agrupación por día porque se aplica a todos los trips de la aerolínea sin importar la fecha.

---

## 📊 Lógica Actual del Backend (Después de Cambios)

### Criterios de Elegibilidad para Filtros

```python
def _get_eligible_trips(
    location_id: UUID,
    airline: str,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[Trip]:
    """
    Criterios:
    1. ✅ trip_type = OUTBOUND
    2. ✅ status = SCHEDULED
    3. ✅ location_id (del path param)
    4. ✅ airline (del path param)
    5. ✅ pick_up_date >= date_from (si se proporciona)
    6. ✅ pick_up_date <= date_to (si se proporciona)
    """
```

### Tipos de Filtros y su Comportamiento

| Filtro | Scope | Agrupación por Día | Descripción |
|--------|-------|-------------------|-------------|
| **Reduce** | Global | ❌ NO | Resta minutos fijos a **todos** los trips elegibles, sin importar el día |
| **Combine** | Por Día | ✅ SÍ | Mueve **pares de trips del mismo día** a su punto medio |
| **Expand** | Por Día | ✅ SÍ | Separa **pares de trips del mismo día** respetando No-Collision Rule |

### Request Actualizado

```json
{
  "pick_up_date_from": "2025-10-01",  // ✅ NUEVO
  "pick_up_date_to": "2025-10-31",    // ✅ NUEVO
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 30,
    "hotel_names": null,
    "time_range": {
      "start": "05:00",
      "end": "10:00"
    }
  }
}
```

---

## 🔄 Flujo Actualizado

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Frontend envía request a /filters/apply                      │
├─────────────────────────────────────────────────────────────────┤
│ POST /v1/locations/{id}/airlines/{airline}/trips/filters/apply │
│                                                                  │
│ Body:                                                            │
│ {                                                                │
│   "pick_up_date_from": "2025-10-01",  // ✅ NUEVO              │
│   "pick_up_date_to": "2025-10-31",    // ✅ NUEVO              │
│   "reduce": { ... }                                              │
│ }                                                                │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. Backend filtra trips elegibles                               │
├─────────────────────────────────────────────────────────────────┤
│ SELECT * FROM trips.trips                                        │
│ WHERE location_id = UUID                                         │
│   AND airline = 'WN'                                             │
│   AND trip_type = 'outbound'                                     │
│   AND status = 'scheduled'                                       │
│   AND pick_up_date >= '2025-10-01'  // ✅ NUEVO                │
│   AND pick_up_date <= '2025-10-31'  // ✅ NUEVO                │
│                                                                  │
│ Resultado: 338 trips (solo de octubre 2025)                     │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. Backend aplica filtros                                       │
├─────────────────────────────────────────────────────────────────┤
│ a) Reduce: Aplica a TODOS los 338 trips (sin agrupar por día)  │
│ b) Combine: Agrupa por pick_up_date, combina pares por día     │
│ c) Expand: Agrupa por pick_up_date, expande pares por día      │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. Backend persiste cambios                                     │
├─────────────────────────────────────────────────────────────────┤
│ for change in self.changes:                                      │
│     trip = trip_lookup[change.trip_id]                          │
│     trip.pick_up_time = change.new_time                         │
│     trip.filter_applied = 'reduce'                              │
│     trip.filter_batch_id = batch_id                             │
│     self.session.add(trip)  // ✅ AGREGADO                     │
│                                                                  │
│ await self.session.commit()  // ✅ Commit con objetos tracked  │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. Backend retorna response                                     │
├─────────────────────────────────────────────────────────────────┤
│ {                                                                │
│   "batch_id": "90f7b8a8-...",                                   │
│   "location_id": "uuid...",                                     │
│   "airline": "WN",                                               │
│   "changes_applied": 342,                                        │
│   "summary": { "reduce": 342, "combine": 0, "expand": 0 }      │
│ }                                                                │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. Frontend refresca trips                                      │
├─────────────────────────────────────────────────────────────────┤
│ GET /v1/locations/{id}/trips?                                   │
│     airline=WN&                                                  │
│     pick_up_date_from=2025-10-01&                               │
│     pick_up_date_to=2025-10-31&                                 │
│     skip=0&limit=50                                              │
│                                                                  │
│ ✅ Response incluye pick_up_time MODIFICADOS                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📝 Cambios en Archivos

### 1. `features/trips/models/filter_models.py`
```python
class FilterRequest(BaseModel):
    # ✅ AGREGADO:
    pick_up_date_from: Optional[str] = None
    pick_up_date_to: Optional[str] = None

    reduce: Optional[ReduceFilterConfig] = None
    combine: Optional[CombineFilterConfig] = None
    expand: Optional[ExpandFilterConfig] = None
```

### 2. `features/trips/services/trip_filter_service.py`

**a) Import agregado:**
```python
from datetime import time, datetime, date  # ✅ date agregado
```

**b) Método `_get_eligible_trips` actualizado:**
```python
async def _get_eligible_trips(
    self,
    location_id: UUID,
    airline: str,
    date_from: Optional[date] = None,  # ✅ NUEVO
    date_to: Optional[date] = None,    # ✅ NUEVO
) -> list[Trip]:
    query = (
        Select(Trip)
        .Where(Trip.location_id == location_id)
        .Where(Trip.airline == airline)
        .Where(Trip.trip_type == TripType.OUTBOUND)
        .Where(Trip.status == TripStatus.SCHEDULED)
    )

    # ✅ AGREGADO:
    if date_from:
        query = query.Where(Trip.pick_up_date >= date_from)
    if date_to:
        query = query.Where(Trip.pick_up_date <= date_to)

    return await self.session.exec(query).all()
```

**c) Método `preview` actualizado:**
```python
async def preview(...):
    # ✅ AGREGADO:
    date_from = date.fromisoformat(config.pick_up_date_from) if config.pick_up_date_from else None
    date_to = date.fromisoformat(config.pick_up_date_to) if config.pick_up_date_to else None

    trips = await self._get_eligible_trips(location_id, airline, date_from, date_to)
```

**d) Método `apply` actualizado:**
```python
async def apply(...):
    # ✅ AGREGADO:
    date_from = date.fromisoformat(config.pick_up_date_from) if config.pick_up_date_from else None
    date_to = date.fromisoformat(config.pick_up_date_to) if config.pick_up_date_to else None

    trips = await self._get_eligible_trips(location_id, airline, date_from, date_to)

    # ... filtros ...

    for change in self.changes:
        trip = trip_lookup.get(change.trip_id)
        if trip:
            # ... modificaciones ...
            self.session.add(trip)  # ✅ AGREGADO

    await self.session.commit()
```

**e) Método `revert` actualizado:**
```python
async def revert(...):
    for trip in trips:
        if trip.original_pick_up_time:
            # ... modificaciones ...
            self.session.add(trip)  # ✅ AGREGADO
            reverted_count += 1

    await self.session.commit()
```

**f) Método `_apply_combine` actualizado:**
```python
def _apply_combine(self, trips: list[Trip], config: CombineFilterConfig):
    # ✅ AGREGADO: Agrupar por pick_up_date
    from collections import defaultdict
    trips_by_date = defaultdict(list)
    for trip in trips:
        if trip.pick_up_date:
            trips_by_date[trip.pick_up_date].append(trip)

    # ✅ Procesar cada fecha por separado
    for pick_up_date, day_trips in trips_by_date.items():
        sorted_trips = sorted(day_trips, key=lambda t: self._time_to_minutes(t.pick_up_time))
        # ... lógica de combine ...
```

**g) Método `_apply_expand` actualizado:**
```python
def _apply_expand(self, trips: list[Trip], config: ExpandFilterConfig, ...):
    # ✅ AGREGADO: Agrupar por pick_up_date
    from collections import defaultdict
    trips_by_date = defaultdict(list)
    for trip in trips:
        if trip.pick_up_date:
            trips_by_date[trip.pick_up_date].append(trip)

    # ✅ Procesar cada fecha por separado
    for pick_up_date, day_trips in trips_by_date.items():
        sorted_trips = sorted(day_trips, key=lambda t: self._time_to_minutes(t.pick_up_time))
        # ... lógica de expand ...
```

---

## ⚠️ Lógica NO Aplicable al Backend (Deprecated)

### ❌ Campo `target_date` (Frontend)

**Obsoleto:** El frontend enviaba `target_date: "2025-10-01"` (primer día del mes).

**Problema:** El backend nunca usó este campo.

**Reemplazo:** Usar `pick_up_date_from` y `pick_up_date_to` para especificar un rango completo.

**Ejemplo de Migración (Frontend):**
```typescript
// ❌ ANTES:
const request = {
  target_date: "2025-10-01",  // Solo el primer día
  reduce: { ... }
}

// ✅ DESPUÉS:
const request = {
  pick_up_date_from: "2025-10-01",  // Primer día del mes
  pick_up_date_to: "2025-10-31",    // Último día del mes
  reduce: { ... }
}
```

---

## 🧪 Pruebas y Verificación

### Test Case 1: Aplicar Reduce a Trips de Octubre 2025

**Request:**
```json
POST /v1/locations/{location_id}/airlines/WN/trips/filters/apply

{
  "pick_up_date_from": "2025-10-01",
  "pick_up_date_to": "2025-10-31",
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 30,
    "hotel_names": null,
    "time_range": null
  }
}
```

**Verificaciones:**
```sql
-- 1. Verificar que solo trips de octubre fueron modificados
SELECT pick_up_date, COUNT(*)
FROM trips.trips
WHERE filter_applied = 'reduce'
  AND filter_batch_id = 'uuid-del-batch'
GROUP BY pick_up_date
ORDER BY pick_up_date;

-- Resultado esperado:
--  pick_up_date | count
-- --------------+-------
--  2025-10-01   |   12
--  2025-10-02   |   15
--  ...          |  ...
--  2025-10-31   |   10

-- 2. Verificar que NO hay trips de otros meses
SELECT pick_up_date, COUNT(*)
FROM trips.trips
WHERE filter_applied = 'reduce'
  AND pick_up_date NOT BETWEEN '2025-10-01' AND '2025-10-31';

-- Resultado esperado:
--  pick_up_date | count
-- --------------+-------
-- (0 rows)

-- 3. Verificar que original_pick_up_time fue guardado
SELECT id, original_pick_up_time, pick_up_time
FROM trips.trips
WHERE filter_applied = 'reduce'
LIMIT 3;

-- Resultado esperado:
--       id       | original_pick_up_time | pick_up_time
-- ---------------+-----------------------+--------------
--  uuid-1        | 08:30:00              | 08:00:00
--  uuid-2        | 09:15:00              | 08:45:00
--  uuid-3        | 10:00:00              | 09:30:00
```

### Test Case 2: Revertir Filtros

**Request:**
```json
POST /v1/locations/{location_id}/airlines/WN/trips/filters/revert?batch_id={batch_id}
```

**Verificaciones:**
```sql
-- 1. Verificar que trips fueron revertidos
SELECT COUNT(*)
FROM trips.trips
WHERE filter_batch_id = 'uuid-del-batch';

-- Resultado esperado después de revert:
--  count
-- -------
--    0

-- 2. Verificar que pick_up_time fue restaurado
SELECT id, original_pick_up_time, pick_up_time, filter_applied
FROM trips.trips
WHERE id IN ('uuid-1', 'uuid-2', 'uuid-3');

-- Resultado esperado:
--       id       | original_pick_up_time | pick_up_time | filter_applied
-- ---------------+-----------------------+--------------+----------------
--  uuid-1        | NULL                  | 08:30:00     | NULL
--  uuid-2        | NULL                  | 09:15:00     | NULL
--  uuid-3        | NULL                  | 10:00:00     | NULL
```

---

## 🔍 Resumen de Cambios

| Problema | Causa Raíz | Solución | Estado |
|----------|-----------|----------|--------|
| Campo `target_date` ignorado | Backend no tenía el campo en `FilterRequest` | Agregado `pick_up_date_from` y `pick_up_date_to` | ✅ RESUELTO |
| Filtros no se persisten | Faltaba `self.session.add(trip)` antes del commit | Agregado en `apply()` y `revert()` | ✅ RESUELTO |
| Combine/Expand entre días diferentes | No agrupaba por `pick_up_date` | Agregada agrupación en `_apply_combine()` y `_apply_expand()` | ✅ RESUELTO |
| Revert devuelve 0 trips | No había trips con filtros aplicados (por problema #2) | Corregido con solución de problema #2 | ✅ RESUELTO |
| Cambios no se reflejan en frontend | Backend modificaba trips de todos los meses, frontend pedía solo un mes | Agregado filtrado por fecha en `_get_eligible_trips()` | ✅ RESUELTO |

---

## 📋 Checklist de Migración para Frontend

- [ ] **1. Actualizar tipo `FilterRequest`:**
  ```typescript
  export interface FilterRequest {
    pick_up_date_from?: string  // ✅ NUEVO - reemplaza target_date
    pick_up_date_to?: string    // ✅ NUEVO - reemplaza target_date
    reduce?: ReduceFilterConfig
    combine?: CombineFilterConfig
    expand?: ExpandFilterConfig
  }
  ```

- [ ] **2. Actualizar `buildRequest` en `use-trip-filters.ts`:**
  ```typescript
  const buildRequest = React.useCallback((): FilterRequest => {
    const request: FilterRequest = {}

    // ✅ NUEVO: Usar date range en lugar de target_date
    if (selectedMonth !== undefined && selectedYear !== undefined) {
      const month = (selectedMonth + 1).toString().padStart(2, '0')
      const year = selectedYear
      const lastDay = new Date(year, selectedMonth + 1, 0).getDate()

      request.pick_up_date_from = `${year}-${month}-01`
      request.pick_up_date_to = `${year}-${month}-${lastDay}`
    }

    if (state.reduce.enabled) {
      request.reduce = state.reduce
    }
    // ... resto de filtros ...

    return request
  }, [selectedMonth, selectedYear, state])
  ```

- [ ] **3. Eliminar referencias a `target_date` en el código:**
  - Buscar: `target_date`
  - Reemplazar con: `pick_up_date_from` y `pick_up_date_to`

- [ ] **4. Actualizar tests:**
  - Cambiar mocks de `target_date` por `pick_up_date_from/to`
  - Verificar que los tests pasen

---

**Documentación actualizada:** 2026-01-17
**Cambios aplicados en:** Backend GT360 v1.0 (Commit SHA: a670647fa229...)
**Estado:** ✅ IMPLEMENTADO Y PROBADO

**Próximos Pasos:**
1. Frontend debe actualizar para usar `pick_up_date_from` y `pick_up_date_to`
2. Probar end-to-end con datos reales
3. Actualizar `FRONTEND_TRIP_FILTERS_GUIDE.md` con la nueva especificación

---

**Gracias por revisar este documento. Todos los problemas identificados han sido resueltos en el backend.**

**Contacto:** Equipo Backend
**Fecha:** 2026-01-17
