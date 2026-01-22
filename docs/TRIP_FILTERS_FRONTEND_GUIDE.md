# Trip Filters System - Frontend Integration Guide

## Overview

El sistema de filtros permite optimizar los horarios de pickup de trips **Outbound** con status **Scheduled**. Los filtros ajustan los tiempos para reducir lead time, combinar trips cercanos, o expandir trips muy juntos.

### Flujo General

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FLUJO DE FILTROS                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. Usuario configura filtros en la UI                                       │
│     - Reduce: Restar X minutos al pickup_time                                │
│     - Combine: Juntar trips con gap de 15-20 min                             │
│     - Expand: Separar trips con gap de 21-30 min                             │
│                                                                              │
│  2. Frontend llama a PREVIEW para simular cambios                            │
│     POST /v1/locations/{loc}/airlines/{airline}/trips/filters/preview        │
│                                                                              │
│  3. Usuario revisa los cambios propuestos en la UI                           │
│     - Ver lista de trips afectados                                           │
│     - Ver tiempos originales vs nuevos                                       │
│     - Ver exclusiones (trips que no se pueden modificar)                     │
│                                                                              │
│  4. Si está conforme, llama a APPLY para persistir los cambios               │
│     POST /v1/locations/{loc}/airlines/{airline}/trips/filters/apply          │
│                                                                              │
│  5. Backend retorna batch_id para poder revertir después                     │
│                                                                              │
│  6. Si necesita deshacer:                                                    │
│     - Revert completo: POST .../filters/revert?batch_id=...                  │
│     - Revert parcial: POST .../filters/revert-partial?batch_id=...&filter_type=reduce │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Filtros Disponibles

### 1. Reduce (Lead Time Reduction)

Resta una cantidad fija de minutos al pickup_time original.

**Uso típico:** Reducir el tiempo de espera antes del vuelo.

```json
{
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 15,
    "hotel_names": ["Hilton", "Marriott"],  // null = todos los hoteles
    "time_range": {                          // null = todo el día
      "start": "05:00",
      "end": "10:00"
    }
  }
}
```

### 2. Combine (Contraction)

Mueve pares de trips con gap pequeño a su punto medio.

**Uso típico:** Combinar pickups cercanos para usar un solo driver.

```json
{
  "combine": {
    "enabled": true,
    "min_gap": 15,   // Gap mínimo (minutos)
    "max_gap": 20,   // Gap máximo (minutos)
    "hotel_names": null,
    "time_range": null
  }
}
```

**Ejemplo:**
- Trip A: 08:00, Trip B: 08:18 (gap = 18 min, dentro de 15-20)
- Ambos se mueven a 08:09 (punto medio)

### 3. Expand (Separation)

Separa pares de trips muy juntos para evitar conflictos.

**Uso típico:** Dar más tiempo entre pickups para evitar retrasos en cadena.

```json
{
  "expand": {
    "enabled": true,
    "min_gap": 21,    // Gap mínimo (minutos)
    "max_gap": 30,    // Gap máximo (minutos)
    "max_shift": 10,  // Máximo desplazamiento por trip
    "hotel_names": null,
    "time_range": null
  }
}
```

**Distribución:** 1/3 hacia atrás (trip anterior), 2/3 hacia adelante (trip posterior).

**Ejemplo con max_shift=10:**
- Trip A: 08:00, Trip B: 08:25 (gap = 25 min, dentro de 21-30)
- Trip A se mueve 3 min atrás → 07:57
- Trip B se mueve 7 min adelante → 08:32

---

## Reglas del Sistema

### Regla A: No Re-modificación
Un trip modificado por **Combine** o **Expand** NO puede ser modificado nuevamente por Combine o Expand en la misma corrida.

**Nota:** Reduce NO está sujeto a esta regla. Reduce siempre opera sobre el tiempo original.

### Regla B: No-Collision Rule
**Expand** no puede crear gaps que caigan dentro del rango de **Combine**.

**Ejemplo:**
- Combine configurado: 15-20 min
- Expand quiere separar Trip A y B
- Si el nuevo gap entre Trip A y el trip anterior cae en 15-20 min → **EXCLUIDO**

### Prioridad de Filtros
1. **Reduce** (Priority 0): Siempre opera sobre `original_pick_up_time`
2. **Combine** (Priority 1): Opera sobre tiempos ya reducidos (si reduce está activo)
3. **Expand** (Priority 1): Opera sobre tiempos ya reducidos (si reduce está activo)

### Cálculo desde Tiempo Original (Preview y Apply)

**IMPORTANTE:** Tanto Preview como Apply **SIEMPRE** calculan los filtros desde el tiempo original del trip (`original_pick_up_time`), NO desde el tiempo actualmente modificado en la base de datos.

Esto significa que si un trip tiene:
- `original_pick_up_time`: 10:00 AM (tiempo original real)
- `pick_up_time`: 9:30 AM (tiempo actual después de aplicar filtros)

Cuando llamas a **Preview** o **Apply** con una nueva configuración de filtros, el sistema:
1. **Ignora** el `pick_up_time` actual (9:30 AM)
2. **Usa** el `original_pick_up_time` (10:00 AM) como base
3. Aplica los filtros seleccionados desde cero

**Ejemplo práctico:**

| Escenario | Filtros en Request | Base para cálculo | Resultado |
|-----------|-------------------|-------------------|-----------|
| Trip original 10:00 AM | Solo Reduce (-15 min) | 10:00 AM | 9:45 AM |
| Trip original 10:00 AM | Solo Combine | 10:00 AM | Depende de vecinos |
| Trip original 10:00 AM | Reduce + Combine | Reduce usa 10:00 AM, Combine usa resultado de Reduce | 9:45 AM → Combine |
| Trip con filtros previos | Solo Combine (sin Reduce) | 10:00 AM (original) | Ignora filtros previos |

**Beneficio:** Esto permite al usuario "experimentar" con diferentes combinaciones de filtros sin preocuparse por el estado actual. Cada preview muestra exactamente lo que pasaría si se aplicaran esos filtros desde el inicio.

### Redondeo de Tiempos
Dos modos disponibles:

| Modo | Descripción | Ejemplo |
|------|-------------|---------|
| `multiple_of_5` | Redondea a múltiplos de 5 min (default) | 08:17 → 08:15 |
| `odd_minutes` | Sin redondeo, mantiene minutos exactos | 08:17 → 08:17 |

---

## REST API Endpoints

Base URL: `/v1/locations/{location_id}/airlines/{airline}/trips/filters`

### 1. Preview (Simular Cambios)

Simula los filtros sin aplicarlos. **SIEMPRE llamar primero antes de Apply.**

```http
POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/preview
Authorization: Bearer {jwt_token}
Content-Type: application/json
```

**Request Body:**
```json
{
  "pick_up_date_from": "2026-01-20",
  "pick_up_date_to": "2026-01-31",
  "rounding_mode": "multiple_of_5",
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 15,
    "hotel_names": null,
    "time_range": null
  },
  "combine": {
    "enabled": true,
    "min_gap": 15,
    "max_gap": 20,
    "hotel_names": null,
    "time_range": null
  },
  "expand": {
    "enabled": false,
    "min_gap": 21,
    "max_gap": 30,
    "max_shift": 10,
    "hotel_names": null,
    "time_range": null
  }
}
```

**Response (200 OK):**
```json
{
  "location_id": "uuid-location",
  "airline": "WN",
  "changes": [
    {
      "trip_id": "uuid-trip-1",
      "original_time": "08:30",
      "new_time": "08:15",
      "filter_applied": "reduce",
      "hotel_name": "Hilton Downtown",
      "pick_up_date": "2026-01-20",
      "airline": "WN"
    },
    {
      "trip_id": "uuid-trip-2",
      "original_time": "08:45",
      "new_time": "08:30",
      "filter_applied": "reduce",
      "hotel_name": "Marriott Airport",
      "pick_up_date": "2026-01-20",
      "airline": "WN"
    },
    {
      "trip_id": "uuid-trip-3",
      "original_time": "09:00",
      "new_time": "08:52",
      "filter_applied": "combine",
      "hotel_name": "Holiday Inn",
      "pick_up_date": "2026-01-20",
      "airline": "WN"
    },
    {
      "trip_id": "uuid-trip-4",
      "original_time": "09:15",
      "new_time": "08:52",
      "filter_applied": "combine",
      "hotel_name": "Best Western",
      "pick_up_date": "2026-01-20",
      "airline": "WN"
    }
  ],
  "exclusions": [
    {
      "operation": "expand(uuid-trip-5, uuid-trip-6)",
      "trip_ids": ["uuid-trip-5", "uuid-trip-6"],
      "reason": "Collision: gap with previous trip would enter Combine range (18 min)",
      "gap_before": 25,
      "gap_after": 18
    }
  ],
  "summary": {
    "reduce": 2,
    "combine": 2,
    "expand": 0,
    "excluded": 1
  },
  "total_trips_evaluated": 50,
  "eligible_trips": 10
}
```

**Notas:**
- `original_time` y `new_time` se formatean según la preferencia del usuario (24h o 12h AM/PM)
- `eligible_trips` = trips que cumplen: OUTBOUND + SCHEDULED + airline correcto
- `exclusions` muestra operaciones que no se pudieron aplicar por Regla B
- **IMPORTANTE:** Preview SIEMPRE calcula desde `original_pick_up_time`, no desde el tiempo actual del trip
- Si un trip ya tiene filtros aplicados, el preview muestra lo que pasaría si se re-aplicaran desde el tiempo original

---

### 2. Apply (Aplicar Cambios)

Aplica los filtros y persiste los cambios en la base de datos.

```http
POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/apply
Authorization: Bearer {jwt_token}
Content-Type: application/json
```

**Request Body:** Igual que Preview.

**Comportamiento:**
- Apply usa la **misma lógica** que Preview para calcular los cambios
- Siempre calcula desde `original_pick_up_time` (tiempo original real)
- Esto garantiza que los resultados de Apply coincidan exactamente con lo que se mostró en Preview
- Si el trip no tenía `original_pick_up_time`, se guarda el `pick_up_time` actual como original antes de modificar

**Response (200 OK):**
```json
{
  "batch_id": "uuid-batch-123",
  "location_id": "uuid-location",
  "airline": "WN",
  "changes_applied": 4,
  "exclusions": [],
  "log": [
    {
      "trip_id": "uuid-trip-1",
      "action": "modified",
      "filter": "reduce",
      "original_time": "08:30:00",
      "new_time": "08:15:00",
      "hotel": "Hilton Downtown",
      "airline": "WN"
    }
  ],
  "summary": {
    "reduce": 2,
    "combine": 2,
    "expand": 0,
    "excluded": 0
  }
}
```

**Importante:** Guardar el `batch_id` para poder revertir los cambios después.

---

### 3. Revert (Revertir Todo)

Revierte todos los cambios de un batch específico o de toda la location+airline.

```http
POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/revert?batch_id={uuid}
Authorization: Bearer {jwt_token}
```

**Query Parameters:**
| Param | Required | Description |
|-------|----------|-------------|
| batch_id | No | Si se proporciona, revierte solo ese batch. Si no, revierte todo. |

**Response (200 OK):**
```json
{
  "trips_reverted": 4,
  "batch_ids_reverted": ["uuid-batch-123"]
}
```

---

### 4. Revert Partial (Revertir Filtro Específico)

Revierte un filtro específico mientras mantiene los otros activos.

```http
POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/revert-partial?batch_id={uuid}&filter_type=reduce
Authorization: Bearer {jwt_token}
```

**Query Parameters:**
| Param | Required | Description |
|-------|----------|-------------|
| batch_id | Yes | ID del batch a revertir parcialmente |
| filter_type | Yes | `reduce`, `combine`, o `expand` |

**Response (200 OK):**
```json
{
  "batch_id": "uuid-batch-123",
  "filter_reverted": "reduce",
  "trips_affected": 2,
  "filters_reapplied": ["combine"],
  "changes_applied": 2,
  "summary": {
    "reduce": 0,
    "combine": 2,
    "expand": 0,
    "excluded": 0
  }
}
```

**Caso de uso:**
- Usuario aplicó Reduce + Combine
- Quiere quitar solo Reduce pero mantener Combine
- Llama a revert-partial con `filter_type=reduce`
- Backend revierte todo, re-aplica solo Combine

---

## TypeScript Interfaces

```typescript
// ============================================================================
// Request Models
// ============================================================================

type RoundingMode = "multiple_of_5" | "odd_minutes";

interface TimeRange {
  start: string;  // "HH:MM" format (e.g., "05:00")
  end: string;    // "HH:MM" format (e.g., "10:00")
}

interface ReduceFilterConfig {
  enabled: boolean;
  minutes_to_reduce: number;      // 0-120
  hotel_names?: string[] | null;  // null = ALL hotels
  time_range?: TimeRange | null;  // null = ALL day
}

interface CombineFilterConfig {
  enabled: boolean;
  min_gap: number;                // 1-60 minutes
  max_gap: number;                // 1-120 minutes (must be >= min_gap)
  hotel_names?: string[] | null;
  time_range?: TimeRange | null;
}

interface ExpandFilterConfig {
  enabled: boolean;
  min_gap: number;                // 1-60 minutes
  max_gap: number;                // 1-120 minutes (must be >= min_gap)
  max_shift: number;              // 1-30 minutes per trip
  hotel_names?: string[] | null;
  time_range?: TimeRange | null;
}

interface FilterRequest {
  pick_up_date_from?: string | null;  // "YYYY-MM-DD"
  pick_up_date_to?: string | null;    // "YYYY-MM-DD"
  rounding_mode?: RoundingMode;       // default: "multiple_of_5"
  reduce?: ReduceFilterConfig | null;
  combine?: CombineFilterConfig | null;
  expand?: ExpandFilterConfig | null;
}

// ============================================================================
// Response Models
// ============================================================================

interface TripChange {
  trip_id: string;
  original_time: string;    // Formatted based on user preference ("08:30" or "8:30 AM")
  new_time: string;
  filter_applied: "reduce" | "combine" | "expand";
  hotel_name: string;
  pick_up_date: string | null;
  airline: string | null;
  flight_number: string | null;  // ✨ NUEVO: Incluido directamente para mostrar en preview UI
}

interface FilterExclusion {
  operation: string;       // e.g., "expand(uuid1, uuid2)"
  trip_ids: string[];
  reason: string;
  gap_before: number;
  gap_after: number;
}

interface FilterSummary {
  reduce: number;
  combine: number;
  expand: number;
  excluded: number;
}

interface FilterPreviewResult {
  location_id: string;
  airline: string;
  changes: TripChange[];
  exclusions: FilterExclusion[];
  summary: FilterSummary;
  total_trips_evaluated: number;
  eligible_trips: number;
}

interface FilterApplyResult {
  batch_id: string;
  location_id: string;
  airline: string;
  changes_applied: number;
  exclusions: FilterExclusion[];
  log: object[];
  summary: FilterSummary;
}

interface FilterRevertResult {
  trips_reverted: number;
  batch_ids_reverted: string[];
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

## Ejemplo de Implementación (React)

### Hook para Filtros

```typescript
import { useState, useCallback } from 'react';

interface UseFilterOptions {
  locationId: string;
  airline: string;
  token: string;
}

export function useTripFilters({ locationId, airline, token }: UseFilterOptions) {
  const [previewResult, setPreviewResult] = useState<FilterPreviewResult | null>(null);
  const [applyResult, setApplyResult] = useState<FilterApplyResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const baseUrl = `/v1/locations/${locationId}/airlines/${airline}/trips/filters`;

  const preview = useCallback(async (config: FilterRequest) => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${baseUrl}/preview`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(config),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Error al previsualizar filtros');
      }

      const result: FilterPreviewResult = await response.json();
      setPreviewResult(result);
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido');
      throw err;
    } finally {
      setLoading(false);
    }
  }, [baseUrl, token]);

  const apply = useCallback(async (config: FilterRequest) => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${baseUrl}/apply`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(config),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Error al aplicar filtros');
      }

      const result: FilterApplyResult = await response.json();
      setApplyResult(result);
      setPreviewResult(null); // Clear preview after applying
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido');
      throw err;
    } finally {
      setLoading(false);
    }
  }, [baseUrl, token]);

  const revert = useCallback(async (batchId?: string) => {
    setLoading(true);
    setError(null);

    try {
      const url = batchId
        ? `${baseUrl}/revert?batch_id=${batchId}`
        : `${baseUrl}/revert`;

      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Error al revertir filtros');
      }

      const result: FilterRevertResult = await response.json();
      setApplyResult(null);
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido');
      throw err;
    } finally {
      setLoading(false);
    }
  }, [baseUrl, token]);

  const revertPartial = useCallback(async (batchId: string, filterType: string) => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `${baseUrl}/revert-partial?batch_id=${batchId}&filter_type=${filterType}`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Error al revertir filtro parcial');
      }

      const result: FilterRevertPartialResult = await response.json();
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido');
      throw err;
    } finally {
      setLoading(false);
    }
  }, [baseUrl, token]);

  return {
    preview,
    apply,
    revert,
    revertPartial,
    previewResult,
    applyResult,
    loading,
    error,
    clearError: () => setError(null),
    clearPreview: () => setPreviewResult(null),
  };
}
```

### Componente de UI para Filtros

```tsx
import React, { useState } from 'react';
import { useTripFilters } from './useTripFilters';

interface FilterConfigFormProps {
  locationId: string;
  airline: string;
  token: string;
}

export function FilterConfigForm({ locationId, airline, token }: FilterConfigFormProps) {
  const {
    preview,
    apply,
    revert,
    previewResult,
    applyResult,
    loading,
    error,
  } = useTripFilters({ locationId, airline, token });

  // Reduce config
  const [reduceEnabled, setReduceEnabled] = useState(false);
  const [reduceMinutes, setReduceMinutes] = useState(15);

  // Combine config
  const [combineEnabled, setCombineEnabled] = useState(false);
  const [combineMinGap, setCombineMinGap] = useState(15);
  const [combineMaxGap, setCombineMaxGap] = useState(20);

  // Expand config
  const [expandEnabled, setExpandEnabled] = useState(false);
  const [expandMinGap, setExpandMinGap] = useState(21);
  const [expandMaxGap, setExpandMaxGap] = useState(30);
  const [expandMaxShift, setExpandMaxShift] = useState(10);

  // Date range
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const buildConfig = (): FilterRequest => ({
    pick_up_date_from: dateFrom || null,
    pick_up_date_to: dateTo || null,
    rounding_mode: 'multiple_of_5',
    reduce: {
      enabled: reduceEnabled,
      minutes_to_reduce: reduceMinutes,
      hotel_names: null,
      time_range: null,
    },
    combine: {
      enabled: combineEnabled,
      min_gap: combineMinGap,
      max_gap: combineMaxGap,
      hotel_names: null,
      time_range: null,
    },
    expand: {
      enabled: expandEnabled,
      min_gap: expandMinGap,
      max_gap: expandMaxGap,
      max_shift: expandMaxShift,
      hotel_names: null,
      time_range: null,
    },
  });

  const handlePreview = async () => {
    await preview(buildConfig());
  };

  const handleApply = async () => {
    const result = await apply(buildConfig());
    // Guardar batch_id para poder revertir después
    localStorage.setItem('lastFilterBatchId', result.batch_id);
  };

  const handleRevert = async () => {
    const batchId = applyResult?.batch_id;
    await revert(batchId);
  };

  return (
    <div className="filter-form">
      {/* Date Range */}
      <section>
        <h3>Rango de Fechas</h3>
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          placeholder="Desde"
        />
        <input
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          placeholder="Hasta"
        />
      </section>

      {/* Reduce */}
      <section>
        <h3>
          <input
            type="checkbox"
            checked={reduceEnabled}
            onChange={(e) => setReduceEnabled(e.target.checked)}
          />
          Reduce (Restar Tiempo)
        </h3>
        {reduceEnabled && (
          <label>
            Minutos a restar:
            <input
              type="number"
              min={0}
              max={120}
              value={reduceMinutes}
              onChange={(e) => setReduceMinutes(Number(e.target.value))}
            />
          </label>
        )}
      </section>

      {/* Combine */}
      <section>
        <h3>
          <input
            type="checkbox"
            checked={combineEnabled}
            onChange={(e) => setCombineEnabled(e.target.checked)}
          />
          Combine (Juntar Trips)
        </h3>
        {combineEnabled && (
          <>
            <label>
              Gap mínimo:
              <input
                type="number"
                min={1}
                max={60}
                value={combineMinGap}
                onChange={(e) => setCombineMinGap(Number(e.target.value))}
              />
            </label>
            <label>
              Gap máximo:
              <input
                type="number"
                min={1}
                max={120}
                value={combineMaxGap}
                onChange={(e) => setCombineMaxGap(Number(e.target.value))}
              />
            </label>
          </>
        )}
      </section>

      {/* Expand */}
      <section>
        <h3>
          <input
            type="checkbox"
            checked={expandEnabled}
            onChange={(e) => setExpandEnabled(e.target.checked)}
          />
          Expand (Separar Trips)
        </h3>
        {expandEnabled && (
          <>
            <label>
              Gap mínimo:
              <input
                type="number"
                min={1}
                max={60}
                value={expandMinGap}
                onChange={(e) => setExpandMinGap(Number(e.target.value))}
              />
            </label>
            <label>
              Gap máximo:
              <input
                type="number"
                min={1}
                max={120}
                value={expandMaxGap}
                onChange={(e) => setExpandMaxGap(Number(e.target.value))}
              />
            </label>
            <label>
              Max shift por trip:
              <input
                type="number"
                min={1}
                max={30}
                value={expandMaxShift}
                onChange={(e) => setExpandMaxShift(Number(e.target.value))}
              />
            </label>
          </>
        )}
      </section>

      {/* Actions */}
      <div className="actions">
        <button onClick={handlePreview} disabled={loading}>
          {loading ? 'Procesando...' : 'Preview'}
        </button>
        <button
          onClick={handleApply}
          disabled={loading || !previewResult}
        >
          Aplicar
        </button>
        <button
          onClick={handleRevert}
          disabled={loading || !applyResult}
        >
          Revertir
        </button>
      </div>

      {/* Error */}
      {error && <div className="error">{error}</div>}

      {/* Preview Results */}
      {previewResult && (
        <div className="preview-results">
          <h3>Preview de Cambios</h3>
          <p>
            Trips evaluados: {previewResult.total_trips_evaluated}<br />
            Trips elegibles: {previewResult.eligible_trips}<br />
            Cambios propuestos: {previewResult.changes.length}
          </p>

          <h4>Resumen</h4>
          <ul>
            <li>Reduce: {previewResult.summary.reduce}</li>
            <li>Combine: {previewResult.summary.combine}</li>
            <li>Expand: {previewResult.summary.expand}</li>
            <li>Excluidos: {previewResult.summary.excluded}</li>
          </ul>

          <h4>Cambios Detallados</h4>
          <table>
            <thead>
              <tr>
                <th>Hotel</th>
                <th>Fecha</th>
                <th>Hora Original</th>
                <th>Hora Nueva</th>
                <th>Filtro</th>
              </tr>
            </thead>
            <tbody>
              {previewResult.changes.map((change) => (
                <tr key={change.trip_id}>
                  <td>{change.hotel_name}</td>
                  <td>{change.pick_up_date}</td>
                  <td>{change.original_time}</td>
                  <td>{change.new_time}</td>
                  <td>{change.filter_applied}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {previewResult.exclusions.length > 0 && (
            <>
              <h4>Exclusiones (No Aplicadas)</h4>
              <ul>
                {previewResult.exclusions.map((ex, i) => (
                  <li key={i}>
                    {ex.operation}: {ex.reason}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {/* Apply Results */}
      {applyResult && (
        <div className="apply-results">
          <h3>Filtros Aplicados</h3>
          <p>
            Batch ID: <code>{applyResult.batch_id}</code><br />
            Cambios aplicados: {applyResult.changes_applied}
          </p>
          <p className="hint">
            Guarda este Batch ID para poder revertir los cambios después.
          </p>
        </div>
      )}
    </div>
  );
}
```

---

## Criterios de Elegibilidad

Solo los siguientes trips son procesados por los filtros:

| Campo | Valor Requerido |
|-------|-----------------|
| `trip_type` | `outbound` |
| `status` | `scheduled` |
| `airline` | Debe coincidir con el parámetro |
| `location_id` | Debe coincidir con el parámetro |

Los trips con otros valores (inbound, ground, en_route, completed, etc.) son **ignorados**.

---

## Validaciones de Rangos

| Campo | Mín | Máx | Descripción |
|-------|-----|-----|-------------|
| `reduce.minutes_to_reduce` | 0 | 120 | Minutos a restar |
| `combine.min_gap` | 1 | 60 | Gap mínimo para combinar |
| `combine.max_gap` | 1 | 120 | Gap máximo para combinar |
| `expand.min_gap` | 1 | 60 | Gap mínimo para expandir |
| `expand.max_gap` | 1 | 120 | Gap máximo para expandir |
| `expand.max_shift` | 1 | 30 | Desplazamiento máximo por trip |

**Importante:** `max_gap` siempre debe ser >= `min_gap`.

---

## Códigos de Error

| Code | Descripción | Acción |
|------|-------------|--------|
| 400 | Parámetros inválidos | Verificar payload |
| 401 | Token inválido | Renovar token |
| 403 | Sin permiso (solo managers) | Verificar rol |
| 404 | Location no encontrada | Verificar location_id |
| 422 | Validación fallida | Revisar valores de filtros |

---

## Formato de Hora

Los tiempos en las respuestas (`original_time`, `new_time`) se formatean según la preferencia del usuario:

| Preferencia | Formato | Ejemplo |
|-------------|---------|---------|
| `24h` | HH:MM | 08:30, 14:45 |
| `12h` | h:MM AM/PM | 8:30 AM, 2:45 PM |

La preferencia se lee automáticamente del endpoint `/v1/profile/settings`.
