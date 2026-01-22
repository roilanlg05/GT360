# Ground Filters V5 - Frontend Integration Guide

## Resumen de Cambios Recientes

Este documento describe los cambios realizados al sistema de Ground Filters y cómo integrarlos en el frontend.

---

## 1. Nuevos Campos en el Modelo Trip

### Campos Booleanos Independientes (V4/V5)

Se agregaron tres campos booleanos independientes para rastrear qué filtros están aplicados a cada trip:

```typescript
interface Trip {
  // ... campos existentes ...

  // NUEVOS: Campos V4/V5 para rastreo independiente
  reduce_applied: boolean;   // true si el filtro REDUCE está activo
  combine_applied: boolean;  // true si el filtro COMBINE está activo
  expand_applied: boolean;   // true si el filtro EXPAND está activo

  // DEPRECADO: Se mantiene por compatibilidad
  filter_applied: string | null;  // "reduce" | "combine" | "expand" | null
}
```

### Ventajas del Nuevo Sistema

| Antes (V3) | Ahora (V5) |
|------------|-----------|
| `filter_applied = "reduce"` | `reduce_applied = true, combine_applied = false, expand_applied = false` |
| Solo un filtro activo a la vez | Múltiples filtros pueden estar activos simultáneamente |
| Para saber filtros activos: consultar `FilterBatch.filters_applied` | Consultar directamente los campos booleanos del Trip |

---

## 2. Nuevos Endpoints

### 2.1 GET `/filters/current` - Estado Actual de Filtros

Obtiene la configuración de filtros actualmente aplicada.

```
GET /v1/locations/{location_id}/airlines/{airline}/trips/filters/current
```

**Response:**
```typescript
interface FilterCurrentResponse {
  has_active_filters: boolean;
  batch_id: string | null;        // UUID del batch activo
  applied_at: string | null;      // ISO datetime
  filters_active: string[];       // ["reduce", "combine", "expand"]
  config: FilterRequest | null;   // Configuración completa
  trips_affected: number;
  summary: {
    reduced: number;
    combined: number;
    expanded: number;
  } | null;
}
```

**Ejemplo de respuesta con filtros activos:**
```json
{
  "has_active_filters": true,
  "batch_id": "a1b2c3d4-...",
  "applied_at": "2026-01-20T10:30:00Z",
  "filters_active": ["reduce", "combine"],
  "config": {
    "pick_up_date_from": "2026-01-15",
    "pick_up_date_to": "2026-01-31",
    "reduce": { "enabled": true, "minutes_to_reduce": 20 },
    "combine": { "enabled": true, "min_gap": 10, "max_gap": 30 },
    "expand": { "enabled": false }
  },
  "trips_affected": 150,
  "summary": {
    "reduced": 100,
    "combined": 50,
    "expanded": 0
  }
}
```

**Ejemplo de respuesta sin filtros:**
```json
{
  "has_active_filters": false,
  "batch_id": null,
  "applied_at": null,
  "filters_active": [],
  "config": null,
  "trips_affected": 0,
  "summary": null
}
```

**Uso en Frontend:**
```typescript
// Al cargar la página de filtros
const loadCurrentFilters = async () => {
  const response = await fetch(`/v1/locations/${locationId}/airlines/${airline}/trips/filters/current`);
  const data: FilterCurrentResponse = await response.json();

  if (data.has_active_filters) {
    // Mostrar estado actual en UI
    setActiveFilters(data.filters_active);
    setFilterConfig(data.config);
    setTripsAffected(data.trips_affected);
  } else {
    // Mostrar formulario para crear nuevos filtros
    showFilterForm();
  }
};
```

---

### 2.2 GET `/filters/preview/last` - Último Preview Guardado

Recupera el último preview generado para sincronizar entre dispositivos.

```
GET /v1/locations/{location_id}/airlines/{airline}/trips/filters/preview/last
```

**Response:**
```typescript
interface FilterPreviewSaved {
  preview_id: string;
  location_id: string;
  airline: string;
  config: FilterRequest;
  result: FilterPreviewResult;
  created_at: string;
}
```

**Caso de uso:** Usuario genera preview en Device A, luego abre Device B y puede ver el mismo preview.

```typescript
// Al abrir la página de filtros, verificar si hay preview pendiente
const checkExistingPreview = async () => {
  const response = await fetch(`/v1/locations/${locationId}/airlines/${airline}/trips/filters/preview/last`);

  if (response.status === 200) {
    const preview: FilterPreviewSaved = await response.json();
    // Mostrar preview existente
    setPreviewData(preview.result);
    setFilterConfig(preview.config);
  } else {
    // No hay preview, mostrar formulario vacío
  }
};
```

---

### 2.3 GET `/filters/eligibility` - Diagnóstico de Elegibilidad

Endpoint de diagnóstico para entender por qué ciertos trips no son elegibles para filtros.

```
GET /v1/locations/{location_id}/airlines/{airline}/trips/filters/eligibility
    ?pick_up_date_from=2026-01-15
    &pick_up_date_to=2026-01-31
```

**Response:**
```json
{
  "total_trips": 674,
  "eligible_trips": 0,
  "by_trip_type": {
    "outbound": 0,
    "inbound": 337,
    "ground": 337
  },
  "by_status": {
    "scheduled": 674,
    "completed": 0
  },
  "eligible_breakdown": {
    "outbound_scheduled_no_filter": 0,
    "outbound_scheduled_with_filter": 0,
    "outbound_other_status": 0
  },
  "reason": "No trips with trip_type='outbound' found",
  "criteria": {
    "info": "Ground Filters only apply to trips matching ALL criteria below",
    "required": {
      "trip_type": "outbound",
      "status": "scheduled",
      "filter_applied": null
    }
  }
}
```

**Uso:** Mostrar este diagnóstico cuando el preview retorna 0 trips elegibles.

---

### 2.4 GET `/filters/history` - Historial de Batches

Lista paginada del historial de aplicaciones de filtros.

```
GET /v1/locations/{location_id}/airlines/{airline}/trips/filters/history
    ?skip=0&limit=20
```

**Response:**
```typescript
interface FilterHistoryResponse {
  data: FilterHistoryItem[];
  total: number;
  skip: number;
  limit: number;
}

interface FilterHistoryItem {
  batch_id: string;
  applied_at: string;          // ISO datetime
  filters_applied: string[];   // ["reduce", "combine"]
  trips_affected: number;
  is_active: boolean;          // true si hay trips con este batch_id
  reverted_filters: string[];  // Filtros que fueron parcialmente revertidos
}
```

---

## 3. Cambios en Endpoints Existentes

### 3.1 POST `/filters/preview`

**Cambio:** Ahora guarda automáticamente el preview en la base de datos.

- El preview se guarda con `location_id + airline` como clave única
- Si ya existe un preview para esa combinación, se reemplaza
- Permite sincronización entre dispositivos

**Cambio en Response - Nuevos campos en TripChange:**
```typescript
interface TripChange {
  trip_id: string;
  original_time: string;
  new_time: string;
  filter_applied: string;
  hotel_name: string;
  pick_up_date: string | null;
  airline: string | null;
  flight_number: string | null;  // NUEVO: Para mostrar en UI
}
```

**Cambio en Response - FilterExclusion ahora incluye trips_info:**
```typescript
interface FilterExclusion {
  operation: string;
  trip_ids: string[];
  reason: string;
  gap_before: number;
  gap_after: number;
  trips_info: TripExclusionInfo[];  // NUEVO: Detalles de trips
}

interface TripExclusionInfo {
  trip_id: string;
  airline: string;
  flight_number: string | null;
  hotel_name: string;
  pick_up_date: string | null;
  pick_up_time: string | null;
  original_pick_up_time: string | null;
}
```

### 3.2 POST `/filters/apply`

**Cambio:** Ahora limpia el preview guardado después de aplicar.

- Después de aplicar filtros exitosamente, el preview se elimina
- Esto evita que Device B vea un preview obsoleto

**Cambio en lógica interna:**
- Ya no hace auto-revert antes de aplicar (V4 independent filters)
- Cada filtro se aplica independientemente usando campos booleanos

---

## 4. Flujo Recomendado para Frontend

### 4.1 Inicialización de la Página de Filtros

```typescript
const initFiltersPage = async () => {
  // 1. Verificar filtros activos
  const current = await fetchCurrentFilters();

  if (current.has_active_filters) {
    // Mostrar estado actual
    displayActiveFilters(current);
    showRevertOptions(current.batch_id, current.filters_active);
  } else {
    // 2. Verificar si hay preview pendiente
    const preview = await fetchLastPreview();

    if (preview) {
      displayPreview(preview);
      showApplyButton();
    } else {
      // Mostrar formulario vacío
      showFilterForm();
    }
  }
};
```

### 4.2 Generar Preview

```typescript
const generatePreview = async (config: FilterRequest) => {
  const result = await fetch(`/v1/locations/${locationId}/airlines/${airline}/trips/filters/preview`, {
    method: 'POST',
    body: JSON.stringify(config)
  });

  const preview: FilterPreviewResult = await result.json();

  if (preview.eligible_trips === 0) {
    // Mostrar diagnóstico de elegibilidad
    const eligibility = await fetchEligibility(config.pick_up_date_from, config.pick_up_date_to);
    showEligibilityDiagnosis(eligibility);
  } else {
    displayPreview(preview);
  }
};
```

### 4.3 Aplicar Filtros

```typescript
const applyFilters = async (config: FilterRequest) => {
  const result = await fetch(`/v1/locations/${locationId}/airlines/${airline}/trips/filters/apply`, {
    method: 'POST',
    body: JSON.stringify(config)
  });

  const applied: FilterApplyResult = await result.json();

  // Actualizar UI
  showSuccessMessage(`${applied.changes_applied} trips modificados`);

  // Recargar estado actual
  await initFiltersPage();
};
```

### 4.4 Revertir Filtro Parcialmente

```typescript
const revertPartialFilter = async (batchId: string, filterType: 'reduce' | 'combine' | 'expand') => {
  const result = await fetch(
    `/v1/locations/${locationId}/airlines/${airline}/trips/filters/batch/${batchId}/revert-partial?filter_type=${filterType}`,
    { method: 'POST' }
  );

  const reverted: FilterRevertPartialResult = await result.json();

  showSuccessMessage(`Filtro ${filterType} revertido. ${reverted.filters_reapplied.length} filtros re-aplicados.`);

  // Recargar estado
  await initFiltersPage();
};
```

---

## 5. Ejemplo de UI para Estado de Filtros

```tsx
const FilterStatusCard = ({ current }: { current: FilterCurrentResponse }) => {
  if (!current.has_active_filters) {
    return <EmptyState message="No hay filtros activos" />;
  }

  return (
    <Card>
      <CardHeader>
        <Title>Filtros Activos</Title>
        <Subtitle>Aplicados: {formatDate(current.applied_at)}</Subtitle>
      </CardHeader>

      <CardBody>
        <FilterBadges filters={current.filters_active} />

        <Stats>
          <Stat label="Trips Afectados" value={current.trips_affected} />
          {current.summary && (
            <>
              <Stat label="Reducidos" value={current.summary.reduced} />
              <Stat label="Combinados" value={current.summary.combined} />
              <Stat label="Expandidos" value={current.summary.expanded} />
            </>
          )}
        </Stats>
      </CardBody>

      <CardFooter>
        {current.filters_active.map(filter => (
          <Button
            key={filter}
            onClick={() => revertPartialFilter(current.batch_id, filter)}
          >
            Revertir {filter}
          </Button>
        ))}
        <Button variant="danger" onClick={() => revertAll(current.batch_id)}>
          Revertir Todo
        </Button>
      </CardFooter>
    </Card>
  );
};
```

---

## 6. Consideraciones Importantes

### 6.1 Sincronización Entre Dispositivos

- El preview se guarda automáticamente en DB al generarlo
- Al aplicar filtros, el preview se elimina
- Usar `/filters/current` para obtener estado real (no preview)

### 6.2 Filtros Independientes (V5)

- Cada filtro (reduce, combine, expand) se rastrea independientemente
- Un trip puede tener `reduce_applied=true` Y `combine_applied=true` simultáneamente
- Al revertir parcialmente un filtro, los otros se re-aplican automáticamente

### 6.3 Elegibilidad de Trips

Solo trips con estas características son elegibles para Ground Filters:
- `trip_type = "outbound"` (Hotel → Airport)
- `status = "scheduled"`

NO elegibles:
- `trip_type = "inbound"` o `"ground"`
- `status = "completed"`, `"cancelled"`, `"en_route"`

---

## 7. Tipos TypeScript Completos

```typescript
// ============ Request Types ============

interface FilterRequest {
  pick_up_date_from?: string;  // "2026-01-15"
  pick_up_date_to?: string;    // "2026-01-31"
  rounding_mode?: 'exact' | 'multiple_of_5';
  reduce?: ReduceFilterConfig;
  combine?: CombineFilterConfig;
  expand?: ExpandFilterConfig;
}

interface ReduceFilterConfig {
  enabled: boolean;
  minutes_to_reduce: number;
  hotel_names?: string[];
  time_range?: TimeRange;
}

interface CombineFilterConfig {
  enabled: boolean;
  min_gap: number;
  max_gap: number;
  hotel_names?: string[];
  time_range?: TimeRange;
}

interface ExpandFilterConfig {
  enabled: boolean;
  min_gap: number;
  max_gap: number;
  hotel_names?: string[];
  time_range?: TimeRange;
}

interface TimeRange {
  start: string;  // "06:00"
  end: string;    // "22:00"
}

// ============ Response Types ============

interface FilterPreviewResult {
  location_id: string;
  airline: string;
  changes: TripChange[];
  exclusions: FilterExclusion[];
  summary: FilterSummary;
  total_trips_evaluated: number;
  eligible_trips: number;
}

interface TripChange {
  trip_id: string;
  original_time: string;
  new_time: string;
  filter_applied: 'reduce' | 'combine' | 'expand';
  hotel_name: string;
  pick_up_date?: string;
  airline?: string;
  flight_number?: string;
}

interface FilterExclusion {
  operation: string;
  trip_ids: string[];
  reason: string;
  gap_before: number;
  gap_after: number;
  trips_info: TripExclusionInfo[];
}

interface TripExclusionInfo {
  trip_id: string;
  airline: string;
  flight_number?: string;
  hotel_name: string;
  pick_up_date?: string;
  pick_up_time?: string;
  original_pick_up_time?: string;
}

interface FilterSummary {
  reduce: number;
  combine: number;
  expand: number;
  excluded: number;
}

interface FilterApplyResult {
  batch_id: string;
  location_id: string;
  airline: string;
  changes_applied: number;
  exclusions: FilterExclusion[];
  log: any[];
  summary: FilterSummary;
}

interface FilterCurrentResponse {
  has_active_filters: boolean;
  batch_id?: string;
  applied_at?: string;
  filters_active: string[];
  config?: FilterRequest;
  trips_affected: number;
  summary?: {
    reduced: number;
    combined: number;
    expanded: number;
  };
}

interface FilterPreviewSaved {
  preview_id: string;
  location_id: string;
  airline: string;
  config: FilterRequest;
  result: FilterPreviewResult;
  created_at: string;
}

interface FilterHistoryResponse {
  data: FilterHistoryItem[];
  total: number;
  skip: number;
  limit: number;
}

interface FilterHistoryItem {
  batch_id: string;
  applied_at: string;
  filters_applied: string[];
  trips_affected: number;
  is_active: boolean;
  reverted_filters: string[];
}

interface FilterRevertPartialResult {
  batch_id: string;
  filter_reverted: string;
  trips_affected: number;
  filters_reapplied: string[];
  changes_applied: number;
  summary: FilterSummary;
}
```

---

## 8. Endpoints Resumen

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/filters/current` | Estado actual de filtros activos |
| GET | `/filters/preview/last` | Último preview guardado |
| GET | `/filters/eligibility` | Diagnóstico de elegibilidad |
| GET | `/filters/history` | Historial de batches |
| POST | `/filters/preview` | Generar preview (se guarda automáticamente) |
| POST | `/filters/apply` | Aplicar filtros (limpia preview) |
| POST | `/filters/revert` | Revertir todos los filtros |
| POST | `/filters/batch/{id}/revert-partial` | Revertir un filtro específico |
