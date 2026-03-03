# Ground Filters V2 — Sin Fechas
## Guía completa para el frontend

Los filtros ahora aplican **globalmente** a todos los trips del `location + airline`.
No hay selección de fecha — hay un solo stack activo por `location+airline`.

---

## Cambio conceptual central

**Antes**: Usuario elegía una fecha → aplicaba filtros a esa fecha → cada fecha tenía su propio stack.

**Ahora**: Usuario aplica filtros → afectan **todos los trips del location+airline** → hay un solo stack global.

---

## Types / Interfaces actualizados

```typescript
// FilterStepConfig — body de preview y apply
interface FilterStepConfig {
  // pick_up_date ya no existe
  filter_type: "reduce" | "combine" | "expand"
  windows: TimeWindow[]
}

// StepResult — response de preview y apply
interface StepResult {
  step_id: string | null       // null en preview, UUID tras apply
  filter_type: string
  // pick_up_date ya no existe
  trips_modified: number       // trips NUEVOS afectados por este step
  changes: TripChange[]
  exclusions: FilterExclusion[]
  summary: {
    modified: number
    total_changes: number
    excluded: number
  }
}

// StackState — response de GET /filters/stack
interface StackState {
  location_id: string
  airline: string
  // pick_up_date ya no existe
  steps: FilterStepInfo[]
  total_trips_affected: number
}

// FilterStepInfo — cada step dentro del stack
interface FilterStepInfo {
  step_id: string
  step_order: number           // 1, 2, 3… usar para orden de iconos
  filter_type: string
  windows_count: number
  windows: TimeWindow[]        // config completa para rehidratar el form
  trips_affected: number
  created_at: string
  is_active: boolean
  config: object
}

// TimeWindow — config por ventana de tiempo
interface TimeWindow {
  start: string                // "HH:MM"
  end: string                  // "HH:MM" o "24:00"
  enabled: boolean
  minutes_to_reduce?: number   // solo Reduce
  min_gap?: number             // Combine y Expand
  max_gap?: number             // Combine y Expand
  max_shift?: number           // solo Expand
  hotel_names?: string[]       // opcional en cualquier tipo
}

// TripChange — dentro de StepResult.changes
interface TripChange {
  trip_id: string
  original_time: string        // tiempo ANTES de esta modificación
  new_time: string             // tiempo DESPUÉS
  filter_applied: string
  hotel_name: string
  pick_up_date: string | null  // metadata informativa del trip (sigue existiendo)
  airline: string
  flight_number: string
}

// EligibilityResult
interface EligibilityResult {
  location_id: string
  airline: string
  // pick_up_date ya no existe
  filter_type: string | null
  total_trips: number
  eligible_trips: number
  already_filtered: number
  trips_with_filter: number | null   // solo si se pasó filter_type
  trips_new: number | null           // solo si se pasó filter_type
  by_hotel: Record<string, number>
  by_time_range: Record<string, number>
}

// AutoApplyResult — response de preset/test
interface AutoApplyResult {
  applied: boolean
  reason: string | null
  days_processed: number
  days_skipped: number
  trips_affected: number
  stack_cloned_from_preset: boolean
  days_with_existing_stack: number
}
```

---

## Endpoints — request y response completos

### 1. Preview Step

```
POST /v2/locations/{location_id}/airlines/{airline}/filters/step/preview
Authorization: Bearer <token>
Content-Type: application/json
```

**Request body**
```json
{
  "filter_type": "reduce",
  "windows": [
    {
      "start": "05:00",
      "end": "12:00",
      "enabled": true,
      "minutes_to_reduce": 15
    },
    {
      "start": "12:00",
      "end": "24:00",
      "enabled": true,
      "minutes_to_reduce": 10
    }
  ]
}
```

**Response 200**
```json
{
  "step_id": null,
  "filter_type": "reduce",
  "trips_modified": 8,
  "changes": [
    {
      "trip_id": "a1b2c3d4-0000-0000-0000-000000000001",
      "original_time": "08:30",
      "new_time": "08:15",
      "filter_applied": "reduce",
      "hotel_name": "Marriott LAX",
      "pick_up_date": "2025-03-15",
      "airline": "WN",
      "flight_number": "WN1234"
    }
  ],
  "exclusions": [
    {
      "operation": "reduce(trip-uuid-...)",
      "trip_ids": ["uuid..."],
      "reason": "Already has Reduce applied",
      "gap_before": 0,
      "gap_after": 0,
      "trips_info": []
    }
  ],
  "summary": {
    "modified": 8,
    "total_changes": 8,
    "excluded": 1
  }
}
```

---

### 2. Apply Step

```
POST /v2/locations/{location_id}/airlines/{airline}/filters/step/apply
Authorization: Bearer <token>
Content-Type: application/json
```

**Request body** — mismo formato que preview
```json
{
  "filter_type": "combine",
  "windows": [
    {
      "start": "00:00",
      "end": "24:00",
      "enabled": true,
      "min_gap": 5,
      "max_gap": 20
    }
  ]
}
```

**Response 200**
```json
{
  "step_id": "f7e6d5c4-b3a2-1234-abcd-000000000001",
  "filter_type": "combine",
  "trips_modified": 4,
  "changes": [
    {
      "trip_id": "uuid...",
      "original_time": "09:00",
      "new_time": "09:07",
      "filter_applied": "combine",
      "hotel_name": "Hilton LAX",
      "pick_up_date": "2025-03-15",
      "airline": "WN",
      "flight_number": "WN5678"
    }
  ],
  "exclusions": [],
  "summary": {
    "modified": 4,
    "total_changes": 4,
    "excluded": 0
  }
}
```

> Guardar `step_id` si se quiere revertir ese step específico después.

---

### 3. Get Stack

```
GET /v2/locations/{location_id}/airlines/{airline}/filters/stack
Authorization: Bearer <token>
```

**Response 200**
```json
{
  "location_id": "11111111-2222-3333-4444-555555555555",
  "airline": "WN",
  "steps": [
    {
      "step_id": "aaaa-0000-0000-0000-000000000001",
      "step_order": 1,
      "filter_type": "reduce",
      "windows_count": 2,
      "windows": [
        {
          "start": "05:00",
          "end": "12:00",
          "enabled": true,
          "minutes_to_reduce": 15
        },
        {
          "start": "12:00",
          "end": "24:00",
          "enabled": true,
          "minutes_to_reduce": 10
        }
      ],
      "trips_affected": 8,
      "created_at": "2025-03-15T10:30:00Z",
      "is_active": true,
      "config": { "filter_type": "reduce" }
    },
    {
      "step_id": "bbbb-0000-0000-0000-000000000002",
      "step_order": 2,
      "filter_type": "combine",
      "windows_count": 1,
      "windows": [
        {
          "start": "00:00",
          "end": "24:00",
          "enabled": true,
          "min_gap": 5,
          "max_gap": 20
        }
      ],
      "trips_affected": 4,
      "created_at": "2025-03-15T10:35:00Z",
      "is_active": true,
      "config": { "filter_type": "combine" }
    }
  ],
  "total_trips_affected": 12
}
```

> Usar `steps[].windows` para rehidratar el formulario cuando el usuario edita un step.
> Usar `steps[].step_order` para el orden cronológico de los iconos.

---

### 4. Revert Last Step

```
POST /v2/locations/{location_id}/airlines/{airline}/filters/revert-last
Authorization: Bearer <token>
```
_(Sin body)_

**Response 200**
```json
{
  "step_id": "bbbb-0000-0000-0000-000000000002",
  "filter_type": "combine",
  "trips_recalculated": 12,
  "remaining_steps": 1,
  "stack_state": {
    "location_id": "11111111-2222-3333-4444-555555555555",
    "airline": "WN",
    "steps": [
      {
        "step_id": "aaaa-0000-0000-0000-000000000001",
        "step_order": 1,
        "filter_type": "reduce",
        "windows_count": 2,
        "windows": [...],
        "trips_affected": 8,
        "created_at": "2025-03-15T10:30:00Z",
        "is_active": true,
        "config": {}
      }
    ],
    "total_trips_affected": 8
  }
}
```

**Response 400** — si no hay steps activos
```json
{ "detail": "No active steps found for location=..., airline=WN" }
```

---

### 5. Revert Step by ID

```
POST /v2/locations/{location_id}/airlines/{airline}/filters/step/{step_id}/revert
Authorization: Bearer <token>
```
_(Sin body)_

**Response 200** — mismo formato que Revert Last
```json
{
  "step_id": "aaaa-0000-0000-0000-000000000001",
  "filter_type": "reduce",
  "trips_recalculated": 4,
  "remaining_steps": 0,
  "stack_state": {
    "location_id": "...",
    "airline": "WN",
    "steps": [],
    "total_trips_affected": 0
  }
}
```

---

### 6. Eligibility

```
GET /v2/locations/{location_id}/airlines/{airline}/filters/eligibility
GET /v2/locations/{location_id}/airlines/{airline}/filters/eligibility?filter_type=reduce
Authorization: Bearer <token>
```

**Response 200** — sin `filter_type`
```json
{
  "location_id": "...",
  "airline": "WN",
  "filter_type": null,
  "total_trips": 25,
  "eligible_trips": 25,
  "already_filtered": 12,
  "trips_with_filter": null,
  "trips_new": null,
  "by_hotel": {
    "Marriott LAX": 10,
    "Hilton LAX": 8,
    "Sheraton LAX": 7
  },
  "by_time_range": {}
}
```

**Response 200** — con `?filter_type=reduce`
```json
{
  "location_id": "...",
  "airline": "WN",
  "filter_type": "reduce",
  "total_trips": 25,
  "eligible_trips": 25,
  "already_filtered": 12,
  "trips_with_filter": 8,
  "trips_new": 17,
  "by_hotel": {
    "Marriott LAX": 10,
    "Hilton LAX": 8,
    "Sheraton LAX": 7
  },
  "by_time_range": {}
}
```

> `trips_new` = trips que serían afectados por primera vez si aplicas este `filter_type`.

---

### 7. Preset — CRUD

**Crear o actualizar**
```
POST /v2/locations/{location_id}/airlines/{airline}/filters/preset
Authorization: Bearer <token>
Content-Type: application/json
```
```json
{
  "stack_template": [
    {
      "filter_type": "reduce",
      "windows": [
        { "start": "05:00", "end": "24:00", "enabled": true, "minutes_to_reduce": 15 }
      ]
    },
    {
      "filter_type": "combine",
      "windows": [
        { "start": "00:00", "end": "24:00", "enabled": true, "min_gap": 5, "max_gap": 20 }
      ]
    }
  ]
}
```

**Response 200**
```json
{
  "id": "cccc-0000-0000-0000-000000000003",
  "location_id": "...",
  "airline": "WN",
  "stack_template": [
    { "filter_type": "reduce", "windows": [...] },
    { "filter_type": "combine", "windows": [...] }
  ],
  "created_at": "2025-03-15T10:00:00Z",
  "updated_at": "2025-03-15T10:45:00Z",
  "created_by": null
}
```

**Obtener**
```
GET /v2/locations/{location_id}/airlines/{airline}/filters/preset
```
Mismo response. `404` si no existe.

**Eliminar**
```
DELETE /v2/locations/{location_id}/airlines/{airline}/filters/preset
```
```json
{ "status": "deleted" }
```

---

### 8. Preset — Guardar stack actual como preset

```
POST /v2/locations/{location_id}/airlines/{airline}/filters/preset/from-stack
Authorization: Bearer <token>
```
_(Sin body)_

**Response 200** — mismo formato que Preset CRUD.

**Response 404** — si no hay stack activo
```json
{ "detail": "No active filter stack found. Apply filters first, then save as preset." }
```

---

### 9. Preset — Test

```
POST /v2/locations/{location_id}/airlines/{airline}/filters/preset/test
Authorization: Bearer <token>
```
_(Sin body)_

**Response 200** — si ya tiene stack (no aplicaría)
```json
{
  "applied": false,
  "reason": "Stack already exists",
  "days_processed": 0,
  "days_skipped": 1,
  "trips_affected": 0,
  "stack_cloned_from_preset": false,
  "days_with_existing_stack": 0
}
```

**Response 200** — si aplicaría
```json
{
  "applied": true,
  "reason": null,
  "days_processed": 1,
  "days_skipped": 0,
  "trips_affected": 12,
  "stack_cloned_from_preset": true,
  "days_with_existing_stack": 0
}
```

---

## Cambios en el código del frontend

### fetchStackState — quitar pick_up_date

```typescript
// ❌ Antes
async function fetchStackState(locationId: string, airline: string, pickUpDate: string) {
  return fetch(`/v2/locations/${locationId}/airlines/${airline}/filters/stack?pick_up_date=${pickUpDate}`)
    .then(r => r.json())
}

// ✅ Ahora
async function fetchStackState(locationId: string, airline: string) {
  return fetch(`/v2/locations/${locationId}/airlines/${airline}/filters/stack`)
    .then(r => r.json())
}
```

### Preview / Apply — quitar pick_up_date del body

```typescript
// ❌ Antes
const config = {
  pick_up_date: selectedDate,
  filter_type: filterType,
  windows: windows,
}

// ✅ Ahora
const config = {
  filter_type: filterType,
  windows: windows,
}
```

### showPreview — quitar fecha de las sub-llamadas

```typescript
// ❌ Antes
async function showPreview(locationId, airline, config) {
  const previewResult = await previewStep(config)
  const trips = await fetchTrips(locationId, airline, config.pick_up_date)
  const stackState = await fetchStackState(locationId, airline, config.pick_up_date)
  ...
}

// ✅ Ahora
async function showPreview(locationId, airline, config) {
  const previewResult = await previewStep(config)
  const trips = await fetchTrips(locationId, airline)      // todos los trips
  const stackState = await fetchStackState(locationId, airline)
  ...
}
```

### Preset endpoints

```typescript
// Test — ya no lleva query param
// ❌ POST /v2/.../filters/preset/test?pick_up_date=2025-03-15
// ✅ POST /v2/.../filters/preset/test

// Guardar como preset — endpoint renombrado
// ❌ POST /v2/.../filters/preset/from-day?pick_up_date=2025-03-15
// ✅ POST /v2/.../filters/preset/from-stack
```

---

## Lo que NO cambia

La lógica de clasificación y display de trips es idéntica:

```typescript
// Counters — sin cambios
function calculateFilterCounters(trips: Trip[]) {
  return {
    reduce: trips.filter(t => t.reduce_applied).length,
    combine: trips.filter(t => t.combine_applied).length,
    expand: trips.filter(t => t.expand_applied).length,
  }
}

// classifyTrip — sin cambios, sigue usando step_order para el orden de iconos
function classifyTrip(trip: Trip, stackState: StackState) {
  const orderedSteps = [...stackState.steps].sort((a, b) => a.step_order - b.step_order)
  const appliedFilters = []

  for (const step of orderedSteps) {
    if (step.filter_type === 'reduce' && trip.reduce_applied)
      appliedFilters.push({ type: 'reduce', icon: '➖', color: 'blue' })
    else if (step.filter_type === 'combine' && trip.combine_applied)
      appliedFilters.push({ type: 'combine', icon: '⊡', color: 'purple' })
    else if (step.filter_type === 'expand' && trip.expand_applied)
      appliedFilters.push({ type: 'expand', icon: '⤢', color: 'orange' })
  }

  const finalTimeColor = appliedFilters.at(-1)?.color ?? null

  return { icons: appliedFilters, originalTime: trip.original_pick_up_time, finalTime: trip.pick_up_time, finalTimeColor }
}
```

---

## Errores comunes

| Status | Cuándo ocurre |
|--------|---------------|
| `400` | `location_id` o `step_id` no es UUID válido |
| `400` | `filter_type` inválido (debe ser `reduce`, `combine` o `expand`) |
| `400` | Ventanas solapadas o sin ninguna habilitada |
| `404` | No hay stack activo (revert o from-stack sin filters aplicados) |
| `500` | Error interno del servidor |

---

## Config por filter_type

| Campo | `reduce` | `combine` | `expand` |
|-------|:--------:|:---------:|:--------:|
| `minutes_to_reduce` | ✅ requerido | — | — |
| `min_gap` | — | ✅ requerido | ✅ requerido |
| `max_gap` | — | ✅ requerido | ✅ requerido |
| `max_shift` | — | — | ✅ requerido |
| `hotel_names` | opcional | opcional | opcional |
| `start` / `end` / `enabled` | ✅ | ✅ | ✅ |

---

## Resumen de todos los cambios

| Qué | Cambio |
|-----|--------|
| `pick_up_date` en body de preview/apply | Eliminar |
| `?pick_up_date=` en stack, revert-last, eligibility | Eliminar |
| `StepResult.pick_up_date` | Eliminar del type |
| `StackState.pick_up_date` | Eliminar del type |
| Date picker en el panel de filtros | Eliminar |
| `fetchStackState(id, airline, date)` | Quitar el tercer param |
| `preset/test?pick_up_date=` | Quitar el query param |
| `preset/from-day?pick_up_date=` | Cambiar a `preset/from-stack` sin params |
| Bulk endpoints (preview/apply/eligibility/revert bulk) | Eliminar si se usan |
| Lógica de clasificación de trips (`classifyTrip`) | Sin cambios |
| Counters (`reduce_applied`, etc.) | Sin cambios |
| `TripChange.pick_up_date` | Sigue existiendo (metadata del trip) |
