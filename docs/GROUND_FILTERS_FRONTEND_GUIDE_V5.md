# Ground Filters V5: Guía Frontend Completa

**Fecha:** 2026-01-20
**Status:** ✅ DEPLOYED
**Target:** Frontend Team

---

## TL;DR - Lo Más Importante

### ¿Qué cambió en V5?

**Antes (V4):** `enabled: false` = "no tocar ese filtro"
**Ahora (V5):** `enabled: false` = "desactivar ese filtro explícitamente"

### Ejemplo Rápido

```typescript
// Escenario: Tengo REDUCE y COMBINE aplicados
// Quiero: Desactivar REDUCE, mantener COMBINE

// ❌ V4: Tenías que usar /revert-partial
DELETE /filters/revert-partial?filter_type=reduce

// ✅ V5: Ahora puedes usar /apply directamente
POST /filters/apply
{
  "reduce": {"enabled": false},    // ← Desactiva REDUCE
  "combine": {"enabled": true},    // ← Mantiene COMBINE
  "expand": {"enabled": false}     // ← Desactiva EXPAND
}
```

---

## 1. Modelo de Datos: Campos Booleanos Independientes

### 1.1 Schema de Trip

```typescript
interface Trip {
  id: string;
  pick_up_time: string;          // Tiempo actual (puede estar filtrado)
  original_pick_up_time: string | null;  // Tiempo original sin filtros

  // V5: Tres campos booleanos independientes
  reduce_applied: boolean;       // ¿Filtro REDUCE está activo?
  combine_applied: boolean;      // ¿Filtro COMBINE está activo?
  expand_applied: boolean;       // ¿Filtro EXPAND está activo?

  // Deprecated (mantener para compatibilidad)
  filter_applied: string | null; // 'reduce', 'combine', 'expand' o null

  // Otros campos...
  location_id: string;
  airline: string;
  trip_type: 'outbound' | 'inbound';
  status: 'scheduled' | 'completed' | 'cancelled';
}
```

### 1.2 ¿Qué significa cada campo?

| Campo | Significado |
|-------|-------------|
| `reduce_applied: true` | Este trip tiene el filtro REDUCE activo (tiempo reducido) |
| `combine_applied: true` | Este trip fue combinado con otros trips |
| `expand_applied: true` | Este trip tiene el tiempo expandido |
| `original_pick_up_time != null` | Este trip tiene AL MENOS un filtro aplicado |

### 1.3 Estados Posibles de un Trip

```typescript
// Sin filtros
{
  reduce_applied: false,
  combine_applied: false,
  expand_applied: false,
  original_pick_up_time: null,
  pick_up_time: "10:00"
}

// Solo REDUCE aplicado
{
  reduce_applied: true,
  combine_applied: false,
  expand_applied: false,
  original_pick_up_time: "10:00",
  pick_up_time: "09:40"  // Reducido 20 min
}

// REDUCE + COMBINE aplicados
{
  reduce_applied: true,
  combine_applied: true,
  expand_applied: false,
  original_pick_up_time: "10:00",
  pick_up_time: "09:35"  // Reducido + combinado
}

// REDUCE desactivado, COMBINE mantiene
{
  reduce_applied: false,
  combine_applied: true,
  expand_applied: false,
  original_pick_up_time: "10:00",
  pick_up_time: "09:50"  // Solo combine ahora
}
```

---

## 2. API Request: Configuración de Filtros

### 2.1 Interfaz TypeScript

```typescript
interface FilterRequest {
  reduce?: {
    enabled: boolean;  // true = aplicar, false = desactivar, undefined = no tocar
    minutes_to_reduce?: number;
    round_direction?: 'up' | 'down';
    options?: FilterOptions;
  };

  combine?: {
    enabled: boolean;
    min_gap_minutes?: number;
    max_gap_minutes?: number;
    apply_to_small_groups?: boolean;
    options?: FilterOptions;
  };

  expand?: {
    enabled: boolean;
    minutes_to_expand?: number;
    round_direction?: 'up' | 'down';
    options?: FilterOptions;
  };

  pick_up_date_from?: string;  // YYYY-MM-DD
  pick_up_date_to?: string;    // YYYY-MM-DD
  time_format?: '12h' | '24h';
  rounding_mode?: 'ceil' | 'floor' | 'round';
}

interface FilterOptions {
  destinations?: string[];       // Filtrar por destinos
  specific_dates?: string[];     // YYYY-MM-DD
  hotels?: string[];
  exclude_destinations?: string[];
  exclude_hotels?: string[];
}
```

### 2.2 Semántica de `enabled`

| Valor | Comportamiento V5 |
|-------|-------------------|
| `enabled: true` | ✅ Aplicar filtro + marcar flag TRUE |
| `enabled: false` | ✅ NO aplicar + marcar flag FALSE (desactiva) |
| `undefined` (no especificar) | ✅ No tocar ese filtro (mantener estado actual) |

**IMPORTANTE:** En V5, `enabled: false` es diferente de omitir el campo completamente.

---

## 3. Casos de Uso Completos

### 3.1 Caso 1: Aplicar REDUCE por primera vez

**Estado inicial:**
```typescript
// Trips sin filtros
reduce_applied: false
combine_applied: false
expand_applied: false
```

**Request:**
```typescript
POST /v1/locations/{location_id}/airlines/WN/trips/filters/apply

{
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 20
  },
  "combine": {"enabled": false},
  "expand": {"enabled": false}
}
```

**Resultado:**
```typescript
// Response 200 OK
{
  "batch_id": "550e8400-e29b-41d4-a716-446655440000",
  "changes_applied": 150,
  "summary": {
    "reduce": 150,
    "combine": 0,
    "expand": 0
  }
}

// Trips actualizados
reduce_applied: true
combine_applied: false
expand_applied: false
original_pick_up_time: "10:00"
pick_up_time: "09:40"
```

---

### 3.2 Caso 2: Aplicar COMBINE sobre REDUCE existente

**Estado inicial:**
```typescript
// Ya tiene REDUCE aplicado
reduce_applied: true
combine_applied: false
expand_applied: false
```

**Request:**
```typescript
POST /filters/apply

{
  "reduce": {"enabled": true, "minutes_to_reduce": 20},
  "combine": {"enabled": true, "min_gap_minutes": 10, "max_gap_minutes": 20},
  "expand": {"enabled": false}
}
```

**Resultado:**
```typescript
// Response 200 OK
{
  "changes_applied": 200,
  "summary": {
    "reduce": 150,
    "combine": 50
  }
}

// Trips actualizados
reduce_applied: true   // ✅ Mantiene
combine_applied: true  // ✅ Agregado
expand_applied: false
pick_up_time: "09:35"  // Refleja AMBOS filtros
```

---

### 3.3 Caso 3: Desactivar REDUCE, mantener COMBINE (⭐ V5 Feature)

**Estado inicial:**
```typescript
// Ambos filtros aplicados
reduce_applied: true
combine_applied: true
expand_applied: false
pick_up_time: "09:35"
original_pick_up_time: "10:00"
```

**Request:**
```typescript
POST /filters/apply

{
  "reduce": {"enabled": false},  // ← Desactivar
  "combine": {"enabled": true, "min_gap_minutes": 10, "max_gap_minutes": 20},
  "expand": {"enabled": false}
}
```

**Resultado:**
```typescript
// Response 200 OK
{
  "changes_applied": 50,
  "summary": {
    "reduce": 0,
    "combine": 50
  }
}

// Trips actualizados
reduce_applied: false  // ✅ Desactivado
combine_applied: true  // ✅ Mantiene
expand_applied: false
pick_up_time: "09:50"  // Solo COMBINE ahora (reduce desaparece)
original_pick_up_time: "10:00"
```

**Explicación:** V5 revierte automáticamente a original y re-aplica solo COMBINE.

---

### 3.4 Caso 4: No tocar un filtro existente (omitir campo)

**Estado inicial:**
```typescript
reduce_applied: true
combine_applied: true
expand_applied: false
```

**Request:**
```typescript
POST /filters/apply

{
  "expand": {"enabled": true, "minutes_to_expand": 15}
  // ⚠️ reduce y combine NO especificados
}
```

**Resultado:**
```typescript
// Trips actualizados
reduce_applied: true   // ✅ No tocado (mantiene estado)
combine_applied: true  // ✅ No tocado (mantiene estado)
expand_applied: true   // ✅ Aplicado
pick_up_time: "09:50"  // Incluye reduce + combine + expand
```

**Nota:** Si no especificas un filtro en el request, V5 NO lo toca (mantiene su estado actual).

---

### 3.5 Caso 5: Revertir TODO (limpiar todos los filtros)

**Estado inicial:**
```typescript
reduce_applied: true
combine_applied: true
expand_applied: true
```

**Opción A: Usar /apply con enabled: false**
```typescript
POST /filters/apply

{
  "reduce": {"enabled": false},
  "combine": {"enabled": false},
  "expand": {"enabled": false}
}
```

**Opción B: Usar /revert (más simple)**
```typescript
DELETE /v1/locations/{location_id}/airlines/WN/trips/filters/revert
```

**Resultado (ambas opciones):**
```typescript
// Trips limpios
reduce_applied: false
combine_applied: false
expand_applied: false
pick_up_time: "10:00"  // Restaurado a original
original_pick_up_time: null
```

---

## 4. Preview de Filtros

### 4.1 ¿Qué es Preview?

Preview simula cómo quedarían los trips SIN persistir cambios en la base de datos.

**Request:**
```typescript
POST /v1/locations/{location_id}/airlines/WN/trips/filters/preview

{
  "reduce": {"enabled": true, "minutes_to_reduce": 20},
  "combine": {"enabled": true, "min_gap_minutes": 10},
  "expand": {"enabled": false}
}
```

**Response:**
```typescript
{
  "location_id": "uuid",
  "airline": "WN",
  "total_trips_evaluated": 500,
  "eligible_trips": 450,
  "changes": [
    {
      "trip_id": "uuid",
      "original_time": "10:00",
      "new_time": "09:40",
      "filter_applied": "reduce",
      "hotel_name": "Hotel A"
    }
    // ... más cambios
  ],
  "exclusions": [
    {
      "trip_id": "uuid",
      "reason": "Already modified",
      "details": "..."
    }
  ],
  "summary": {
    "reduce": 150,
    "combine": 50,
    "expand": 0,
    "excluded": 50
  }
}
```

### 4.2 Preview con Filtros Existentes

**Pregunta:** Si ya tengo REDUCE aplicado, ¿puedo hacer preview de COMBINE?

**Respuesta:** ✅ SÍ. Preview V5 ignora los filtros actuales y muestra cómo quedarían con la nueva configuración.

```typescript
// Situación: Tienes REDUCE aplicado
reduce_applied: true

// Preview de COMBINE
POST /filters/preview
{
  "combine": {"enabled": true, "min_gap_minutes": 10}
}

// ✅ Backend encuentra los trips y muestra preview
// ✅ No revierte nada (es solo simulación)
```

---

## 5. Estado de Filtros: ¿Qué está aplicado?

### 5.1 Leer Estado desde Trips

**Método 1: Desde un Trip individual**
```typescript
GET /v1/locations/{location_id}/airlines/WN/trips/{trip_id}

// Response
{
  "id": "uuid",
  "reduce_applied": true,
  "combine_applied": false,
  "expand_applied": false,
  // ... otros campos
}
```

**Método 2: Desde listado de trips**
```typescript
GET /v1/locations/{location_id}/airlines/WN/trips

// Response
{
  "trips": [
    {
      "id": "uuid",
      "reduce_applied": true,
      "combine_applied": true,
      ...
    }
  ]
}
```

### 5.2 Estado Agregado (Recomendado para UI)

Para mostrar qué filtros están activos en el location+airline:

```typescript
// Opción A: Query manual sobre trips
const trips = await fetchTrips(locationId, airline);

const activeFilters = {
  reduce: trips.some(t => t.reduce_applied),
  combine: trips.some(t => t.combine_applied),
  expand: trips.some(t => t.expand_applied),
};

// Opción B: Endpoint dedicado (si existe en tu API)
GET /v1/locations/{location_id}/airlines/WN/trips/filters/status

// Response (ejemplo)
{
  "reduce_applied": true,
  "combine_applied": false,
  "expand_applied": false,
  "trips_with_filters": 150,
  "total_trips": 500
}
```

---

## 6. UI Components: Ejemplos

### 6.1 Componente: Botones de Filtros

```typescript
import { useState, useEffect } from 'react';

interface FilterState {
  reduce: boolean;
  combine: boolean;
  expand: boolean;
}

function FilterButtons() {
  const [activeFilters, setActiveFilters] = useState<FilterState>({
    reduce: false,
    combine: false,
    expand: false,
  });

  // Cargar estado inicial desde trips
  useEffect(() => {
    async function loadFilterState() {
      const trips = await fetchTrips(locationId, airline);
      setActiveFilters({
        reduce: trips.some(t => t.reduce_applied),
        combine: trips.some(t => t.combine_applied),
        expand: trips.some(t => t.expand_applied),
      });
    }
    loadFilterState();
  }, []);

  // Toggle filter
  const toggleFilter = async (filterType: keyof FilterState) => {
    const newState = !activeFilters[filterType];

    // Aplicar cambio
    await applyFilter({
      [filterType]: { enabled: newState, /* config... */ },
    });

    // Actualizar UI
    setActiveFilters(prev => ({
      ...prev,
      [filterType]: newState,
    }));
  };

  return (
    <div>
      <button
        className={activeFilters.reduce ? 'active' : 'inactive'}
        onClick={() => toggleFilter('reduce')}
      >
        REDUCE {activeFilters.reduce && '✓'}
      </button>

      <button
        className={activeFilters.combine ? 'active' : 'inactive'}
        onClick={() => toggleFilter('combine')}
      >
        COMBINE {activeFilters.combine && '✓'}
      </button>

      <button
        className={activeFilters.expand ? 'active' : 'inactive'}
        onClick={() => toggleFilter('expand')}
      >
        EXPAND {activeFilters.expand && '✓'}
      </button>
    </div>
  );
}
```

### 6.2 Componente: Badge de Filtros Activos

```typescript
function FilterBadges({ trip }: { trip: Trip }) {
  return (
    <div className="filter-badges">
      {trip.reduce_applied && (
        <span className="badge badge-reduce">REDUCE</span>
      )}
      {trip.combine_applied && (
        <span className="badge badge-combine">COMBINE</span>
      )}
      {trip.expand_applied && (
        <span className="badge badge-expand">EXPAND</span>
      )}
    </div>
  );
}

// Uso
<TripCard>
  <h3>{trip.hotel_name}</h3>
  <p>Pickup: {trip.pick_up_time}</p>
  <FilterBadges trip={trip} />
</TripCard>
```

### 6.3 Componente: Preview Modal

```typescript
function PreviewModal({ filterConfig }: { filterConfig: FilterRequest }) {
  const [preview, setPreview] = useState<FilterPreviewResult | null>(null);

  useEffect(() => {
    async function loadPreview() {
      const result = await fetch('/filters/preview', {
        method: 'POST',
        body: JSON.stringify(filterConfig),
      }).then(r => r.json());

      setPreview(result);
    }
    loadPreview();
  }, [filterConfig]);

  if (!preview) return <Spinner />;

  return (
    <div className="modal">
      <h2>Preview: {preview.changes.length} cambios</h2>

      <div className="summary">
        <p>REDUCE: {preview.summary.reduce} trips</p>
        <p>COMBINE: {preview.summary.combine} trips</p>
        <p>EXPAND: {preview.summary.expand} trips</p>
        <p>Excluded: {preview.summary.excluded} trips</p>
      </div>

      <table>
        <thead>
          <tr>
            <th>Hotel</th>
            <th>Original</th>
            <th>New</th>
            <th>Filter</th>
          </tr>
        </thead>
        <tbody>
          {preview.changes.map(change => (
            <tr key={change.trip_id}>
              <td>{change.hotel_name}</td>
              <td>{change.original_time}</td>
              <td>{change.new_time}</td>
              <td>{change.filter_applied}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <button onClick={() => applyFilters(filterConfig)}>
        Apply Changes
      </button>
    </div>
  );
}
```

---

## 7. API Completo

### 7.1 Endpoints Disponibles

| Endpoint | Method | Descripción |
|----------|--------|-------------|
| `/filters/preview` | POST | Simular filtros (no persiste) |
| `/filters/apply` | POST | Aplicar filtros (persiste) |
| `/filters/revert` | DELETE | Revertir TODO |
| `/filters/revert-partial` | DELETE | Revertir un tipo específico |

### 7.2 Preview

**Request:**
```typescript
POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/preview
Content-Type: application/json

{
  "reduce": {"enabled": true, "minutes_to_reduce": 20},
  "combine": {"enabled": true, "min_gap_minutes": 10, "max_gap_minutes": 20},
  "expand": {"enabled": false},
  "time_format": "12h"
}
```

**Response 200:**
```typescript
{
  "location_id": "uuid",
  "airline": "WN",
  "total_trips_evaluated": 500,
  "eligible_trips": 450,
  "changes": [...],  // TripChange[]
  "exclusions": [...],  // FilterExclusion[]
  "summary": {
    "reduce": 150,
    "combine": 50,
    "expand": 0,
    "excluded": 50
  }
}
```

### 7.3 Apply

**Request:**
```typescript
POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/apply
Content-Type: application/json

{
  "reduce": {"enabled": true, "minutes_to_reduce": 20},
  "combine": {"enabled": true, "min_gap_minutes": 10, "max_gap_minutes": 20},
  "expand": {"enabled": false}
}
```

**Response 200:**
```typescript
{
  "batch_id": "uuid",
  "location_id": "uuid",
  "airline": "WN",
  "changes_applied": 200,
  "exclusions": [...],
  "log": [
    {
      "trip_id": "uuid",
      "action": "modified",
      "filter": "reduce",
      "original_time": "10:00",
      "new_time": "09:40",
      "hotel": "Hotel A",
      "airline": "WN"
    }
  ],
  "summary": {
    "reduce": 150,
    "combine": 50,
    "expand": 0,
    "excluded": 50
  }
}
```

**Response 500 (Error):**
```typescript
{
  "detail": "Error applying filters: ..."
}
```

### 7.4 Revert (Completo)

**Request:**
```typescript
DELETE /v1/locations/{location_id}/airlines/{airline}/trips/filters/revert
```

**Response 200:**
```typescript
{
  "location_id": "uuid",
  "airline": "WN",
  "reverted_count": 200,
  "batch_ids_reverted": ["uuid1", "uuid2"],
  "log": [...]
}
```

### 7.5 Revert Partial (Un filtro específico)

**Request:**
```typescript
DELETE /v1/locations/{location_id}/airlines/{airline}/trips/filters/revert-partial?filter_type=reduce
```

**Query Parameters:**
- `filter_type`: 'reduce' | 'combine' | 'expand'

**Response 200:**
```typescript
{
  "location_id": "uuid",
  "airline": "WN",
  "filter_type": "reduce",
  "reverted_count": 150,
  "reapplied_count": 50,
  "log": [...]
}
```

**Nota:** Este endpoint revierte TODO y re-aplica solo los filtros que NO son del tipo especificado.

---

## 8. Diferencias V4 vs V5

| Aspecto | V4 | V5 |
|---------|----|----|
| **enabled: false** | No toca el filtro | ❌ Desactiva explícitamente |
| **Desactivar filtro individual** | Requiere /revert-partial | ✅ Puedes usar /apply directamente |
| **UX** | Menos intuitivo | ✅ Más intuitivo |
| **Complejidad** | Más simple (solo marca TRUE) | ⚠️ Más complejo (maneja TRUE/FALSE) |
| **Backwards compatible** | N/A | ✅ Sí (si omites campo, no lo toca) |

---

## 9. Migration Guide: V4 → V5

### 9.1 ¿Necesitas cambiar tu frontend?

**NO**, si actualmente:
- Solo usas `enabled: true` para activar filtros
- Usas `/revert-partial` para desactivar filtros individuales

**SÍ**, si quieres:
- Usar `enabled: false` para desactivar filtros en /apply
- Simplificar tu lógica eliminando llamadas a /revert-partial

### 9.2 Cambios Recomendados

**Antes (V4):**
```typescript
// Desactivar REDUCE
await fetch('/filters/revert-partial?filter_type=reduce', {
  method: 'DELETE',
});
```

**Después (V5):**
```typescript
// Opción A: Usar apply con enabled: false (más simple)
await fetch('/filters/apply', {
  method: 'POST',
  body: JSON.stringify({
    reduce: { enabled: false },
    combine: { enabled: true, min_gap_minutes: 10 },
  }),
});

// Opción B: Seguir usando /revert-partial (funciona igual)
await fetch('/filters/revert-partial?filter_type=reduce', {
  method: 'DELETE',
});
```

### 9.3 Testing Checklist

- [ ] Aplicar REDUCE → Verificar `reduce_applied: true`
- [ ] Aplicar COMBINE → Verificar `combine_applied: true`
- [ ] Desactivar REDUCE con `enabled: false` → Verificar `reduce_applied: false`
- [ ] Aplicar REDUCE + COMBINE juntos → Verificar ambos TRUE
- [ ] Revertir TODO con /revert → Verificar todos FALSE
- [ ] Preview con filtros existentes → Verificar que funciona
- [ ] UI muestra badges correctos para filtros activos

---

## 10. Casos Edge y Errores Comunes

### 10.1 Error: "No eligible trips found"

**Causa:** No hay trips que cumplan los criterios:
- `trip_type = 'outbound'`
- `status = 'scheduled'`
- `location_id` y `airline` coinciden
- `pick_up_date` en rango (si especificaste)

**Solución:**
- Verificar que el `location_id` y `airline` son correctos
- Revisar el rango de fechas
- Asegurarte de que hay trips outbound scheduled

### 10.2 Error 500: "Multiple commits"

**Causa:** Este error era común en V3 (auto-revert). En V4/V5 NO debería ocurrir.

**Solución:**
- Verificar que estás usando la versión correcta del backend
- Revisar logs del backend

### 10.3 Comportamiento: "enabled: false no hace nada"

**Causa:** Estás usando V4 (no V5).

**Solución:**
- Verificar versión del backend (debe ser V5)
- Alternativamente, usar `/revert-partial`

### 10.4 Comportamiento: "Omití reduce y se desactivó"

**Causa:** Tu request tiene explícitamente `reduce: null` o `reduce: {enabled: false}`.

**Solución:**
- Para NO tocar un filtro, NO lo incluyas en el request
- `{combine: {enabled: true}}` ← reduce no se toca
- `{reduce: {enabled: false}, combine: {enabled: true}}` ← reduce se desactiva

---

## 11. FAQ

### 11.1 ¿Cuál es la diferencia entre omitir un filtro y enabled: false?

**Omitir (no especificar):**
```typescript
{
  combine: {enabled: true}
  // reduce NO especificado
}
// → reduce mantiene su estado actual (no se toca)
```

**Enabled: false:**
```typescript
{
  reduce: {enabled: false},
  combine: {enabled: true}
}
// → reduce se desactiva explícitamente (marca FALSE)
```

### 11.2 ¿Puedo tener múltiples filtros activos simultáneamente?

**SÍ.** Ese es el punto de V4/V5. Puedes tener:
- `reduce_applied: true`
- `combine_applied: true`
- `expand_applied: true`

Todos al mismo tiempo en el mismo trip.

### 11.3 ¿En qué orden se aplican los filtros?

**Orden de aplicación (backend):**
1. REDUCE (Priority 0)
2. COMBINE (Priority 1)
3. EXPAND (Priority 1)

Esto significa que REDUCE siempre se aplica primero, y luego COMBINE/EXPAND operan sobre el resultado.

### 11.4 ¿Qué pasa si aplico COMBINE sin REDUCE?

**Funciona perfectamente.** Los filtros son independientes. Puedes aplicar:
- Solo REDUCE
- Solo COMBINE
- Solo EXPAND
- Cualquier combinación

### 11.5 ¿Cómo revertir TODO de una vez?

**Opción A: /revert (más simple)**
```typescript
DELETE /v1/locations/{location_id}/airlines/WN/trips/filters/revert
```

**Opción B: /apply con todo en false**
```typescript
POST /filters/apply
{
  "reduce": {"enabled": false},
  "combine": {"enabled": false},
  "expand": {"enabled": false}
}
```

Ambas opciones producen el mismo resultado.

### 11.6 ¿filter_applied sigue existiendo?

**SÍ**, pero está DEPRECATED. Se mantiene para backwards compatibility.

**Recomendación:** Usa `reduce_applied`, `combine_applied`, `expand_applied` en lugar de `filter_applied`.

### 11.7 ¿Puedo aplicar filtros a fechas específicas?

**SÍ.** Usa `pick_up_date_from` y `pick_up_date_to`:

```typescript
{
  "reduce": {"enabled": true, "minutes_to_reduce": 20},
  "pick_up_date_from": "2026-01-25",
  "pick_up_date_to": "2026-01-31"
}
```

Solo los trips en ese rango de fechas serán afectados.

---

## 12. Resumen: Cómo Usar V5

### 12.1 Workflow Típico

1. **Preview primero** (opcional pero recomendado):
```typescript
const preview = await fetch('/filters/preview', {
  method: 'POST',
  body: JSON.stringify(filterConfig),
}).then(r => r.json());

// Mostrar preview al usuario
showPreviewModal(preview);
```

2. **Aplicar si usuario confirma:**
```typescript
if (userConfirms) {
  const result = await fetch('/filters/apply', {
    method: 'POST',
    body: JSON.stringify(filterConfig),
  }).then(r => r.json());

  // Actualizar UI
  refreshTrips();
}
```

3. **Mostrar estado de filtros activos:**
```typescript
const trips = await fetchTrips();
const activeFilters = {
  reduce: trips.some(t => t.reduce_applied),
  combine: trips.some(t => t.combine_applied),
  expand: trips.some(t => t.expand_applied),
};

// Renderizar UI con filtros activos
renderFilterButtons(activeFilters);
```

### 12.2 Reglas de Oro

1. ✅ **Siempre hacer preview antes de apply** (UX)
2. ✅ **Usar `enabled: true/false` explícitamente** (claridad)
3. ✅ **No especificar un filtro si no quieres tocarlo** (mantener estado)
4. ✅ **Leer `reduce_applied`, `combine_applied`, `expand_applied`** (no `filter_applied`)
5. ✅ **Mostrar filtros activos en la UI** (transparencia)

---

## 13. Soporte y Contacto

**Backend Team**
**Última actualización:** 2026-01-20

**Archivos de referencia:**
- `/home/backend/GT360/docs/GROUND_FILTERS_V4_INDEPENDENT.md` - Documentación técnica backend
- `/home/backend/GT360/docs/GROUND_FILTERS_COMPLETE_V3.md` - Documentación completa V3
- `/home/backend/GT360/features/trips/routes/trips_router.py` - Endpoints
- `/home/backend/GT360/features/trips/services/trip_filter_service.py` - Lógica de negocio

---

**¡Feliz desarrollo! 🚀**
