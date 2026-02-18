# Ground Filters V2 - Guía de Preview para Frontend

> **Propósito**: Documentación técnica para el frontend sobre cómo funciona el sistema de preview de filtros y cómo combinar correctamente los resultados.

---

## ✅ FIX APLICADO (2026-02-03)

### Cambios en el Backend

El backend ahora **excluye automáticamente** los trips que ya tienen un filtro aplicado y genera exclusiones con los tiempos correctos.

### Comportamiento Actual del Preview

| Escenario | `changes` | `exclusions` |
|-----------|-----------|--------------|
| Preview Reduce (trip sin reduce) | ✅ Incluido | - |
| Preview Reduce (trip con `reduce_applied=true`) | ❌ No incluido | ✅ "Already has Reduce applied" |
| Preview Combine (trip sin combine) | ✅ Incluido | - |
| Preview Combine (trip con `combine_applied=true`) | ❌ No incluido | ✅ "Already has Combine applied" |
| Preview Combine (trip con `expand_applied=true`) | ❌ No incluido | ✅ "Skipped: Expand has priority" |
| Preview Expand (trip sin expand) | ✅ Incluido | - |
| Preview Expand (trip con `expand_applied=true`) | ❌ No incluido | ✅ "Already has Expand applied" |
| Preview Expand (trip con `combine_applied=true`) | ❌ No incluido | ✅ "Skipped: Combine has priority" |

### Ejemplo de Respuesta - Preview Combine (ya aplicado)

```json
{
  "step_id": null,
  "filter_type": "combine",
  "changes": [],
  "exclusions": [
    {
      "operation": "combine(trip-uuid)",
      "trip_ids": ["trip-uuid"],
      "reason": "Already has Combine applied",
      "trips_info": [{
        "trip_id": "trip-uuid",
        "pick_up_time": "08:37",
        "original_pick_up_time": "08:45",
        "hotel_name": "Hotel A",
        "airline": "WN",
        "flight_number": "1234"
      }]
    }
  ]
}
```

### Tiempos en las Exclusiones

- `pick_up_time`: Tiempo **actual** del trip (después del filtro aplicado)
- `original_pick_up_time`: Tiempo **original** (antes de cualquier filtro)

---

## 1. Arquitectura del Sistema de Filtros

### 1.1 Concepto: Order-Free (Sin Orden Fijo)

El sistema V2 es **order-free**, lo que significa:

- Los filtros (reduce, combine, expand) se pueden aplicar en **CUALQUIER orden**
- NO existe un orden fijo como "reduce siempre va primero"
- La prioridad la define el **orden cronológico de aplicación** (`step_order`)

```
Ejemplo válido 1: Reduce → Combine → Expand
Ejemplo válido 2: Expand → Reduce → Combine
Ejemplo válido 3: Combine → Expand → Reduce
```

### 1.2 Priority Rule: "El Primero que Llega, Gana"

Cuando un trip es modificado por Combine o Expand, el otro filtro **NO puede tocarlo**:

```
Escenario A: Usuario aplica Combine primero
  - Trip A modificado por Combine (combine_applied=true)
  - Luego intenta aplicar Expand
  - Expand NO puede modificar Trip A (Combine tiene prioridad)
  - Expand genera exclusión: "Skipped: Combine has priority"

Escenario B: Usuario aplica Expand primero
  - Trip A modificado por Expand (expand_applied=true)
  - Luego intenta aplicar Combine
  - Combine NO puede modificar Trip A (Expand tiene prioridad)
  - Combine genera exclusión: "Skipped: Expand has priority"
```

**Ambos filtros generan exclusiones simétricas** con la información del trip:
- `pick_up_time`: Tiempo actual (después del filtro que tiene prioridad)
- `original_pick_up_time`: Tiempo original (antes de cualquier filtro)

### 1.3 Reglas de Exclusión Completas

El backend genera exclusiones en los siguientes casos:

#### A. Re-aplicación del mismo filtro

Si un trip ya tiene un filtro aplicado y se hace preview del mismo filtro:

| Filtro | Flag verificado | Razón de exclusión |
|--------|-----------------|-------------------|
| Reduce | `reduce_applied=true` | "Already has Reduce applied" |
| Combine | `combine_applied=true` | "Already has Combine applied" |
| Expand | `expand_applied=true` | "Already has Expand applied" |

#### B. Priority Rule (Anticolisión entre Combine y Expand)

Combine y Expand son **mutuamente excluyentes**:

| Preview | Si el trip tiene | Razón de exclusión |
|---------|-----------------|-------------------|
| Combine | `expand_applied=true` | "Skipped: Expand has priority" |
| Expand | `combine_applied=true` | "Skipped: Combine has priority" |

#### C. Cadenas largas en Expand

Si una cadena de trips tiene más de 6 elementos:

| Situación | Razón de exclusión |
|-----------|-------------------|
| Cadena de 7+ trips | "Chain of X trips exceeds maximum allowed (max 6 trips)" |

### 1.4 Stack de Filtros (Per-Day)

Cada día tiene su propio stack de filtros:

```
Stack del 2026-01-25:
┌─────────────────────────────────────┐
│ step_order: 3 │ expand  │ 5 trips  │  ← Último aplicado
├─────────────────────────────────────┤
│ step_order: 2 │ combine │ 10 trips │
├─────────────────────────────────────┤
│ step_order: 1 │ reduce  │ 25 trips │  ← Primero aplicado
└─────────────────────────────────────┘
```

---

## 2. Endpoints de Preview

### 2.1 Preview Individual

```http
POST /v2/locations/{location_id}/airlines/{airline}/filters/step/preview

Body:
{
  "filter_type": "expand",
  "pick_up_date": "2026-01-25",
  "windows": [
    {
      "start": "05:00",
      "end": "12:00",
      "enabled": true,
      "min_gap": 5,
      "max_gap": 15,
      "max_shift": 10
    }
  ]
}
```

### 2.2 Preview Bulk (Multi-Day)

```http
POST /v2/locations/{location_id}/airlines/{airline}/filters/bulk/preview

Body:
{
  "filter_type": "combine",
  "date_from": "2026-01-25",
  "date_to": "2026-01-31",
  "windows": [...]
}
```

---

## 3. Estructura de Respuesta del Preview

### 3.1 StepResult

```typescript
interface StepResult {
  step_id: string | null;      // null en preview, UUID en apply
  filter_type: string;         // "reduce" | "combine" | "expand"
  pick_up_date: string;
  trips_modified: number;      // Solo trips NUEVOS para este filtro
  changes: TripChange[];       // Lista de cambios
  exclusions: FilterExclusion[]; // Trips excluidos por reglas
  summary: {
    modified: number;
    total_changes: number;
    excluded: number;
  };
}
```

### 3.2 TripChange (CRÍTICO - Entender esto)

```typescript
interface TripChange {
  trip_id: string;
  original_time: string;    // ⚠️ Tiempo de ENTRADA a este filtro
  new_time: string;         // Tiempo de SALIDA de este filtro
  filter_applied: string;   // "reduce" | "combine" | "expand"
  hotel_name: string;
  pick_up_date: string | null;
  airline: string | null;
  flight_number: string | null;
}
```

### 3.3 ⚠️ IMPORTANTE: Qué significa `original_time`

El campo `original_time` en `TripChange` **NO es el tiempo original del trip**.

Es el **tiempo de entrada a ese filtro específico**:

```
Trip original: 08:00

Preview de Combine:
  original_time: 08:00  ← Input a Combine (tiempo original del trip)
  new_time: 08:10       ← Output de Combine

Preview de Expand (después de Combine):
  original_time: 08:10  ← Input a Expand (output de Combine)
  new_time: 08:50       ← Output de Expand
```

---

## 4. El Bug del Preview Combinado

### 4.1 Escenario del Bug

```
Estado inicial: Trip A a las 08:00

1. Usuario aplica Combine:
   Backend responde: { original_time: "08:00", new_time: "08:10" }
   Preview muestra: 08:00 → 08:10 ✅

2. Usuario agrega Expand al preview:
   Frontend hace 2 llamadas:
   - Preview Combine: { original_time: "08:00", new_time: "08:10" }
   - Preview Expand:  { original_time: "08:10", new_time: "08:50" }

3. Frontend combina mal los resultados:
   ❌ Muestra: 08:10 → 08:50 (perdió el tiempo original 08:00)
   ✅ Debería: 08:00 → 08:50
```

### 4.2 Diagrama del Flujo de Datos

```
┌─────────────────────────────────────────────────────────────────┐
│                         BACKEND                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Trip en BD:                                                     │
│  ┌──────────────────────────────────────────┐                   │
│  │ id: "trip-a"                              │                   │
│  │ pick_up_time: 08:10        (actual)       │                   │
│  │ original_pick_up_time: 08:00 (inmutable)  │                   │
│  │ combine_applied: true                     │                   │
│  │ expand_applied: false                     │                   │
│  └──────────────────────────────────────────┘                   │
│                                                                  │
│  Preview Expand:                                                 │
│  - Lee pick_up_time actual (08:10)                              │
│  - Aplica shift (+40 min)                                       │
│  - Retorna: { original_time: 08:10, new_time: 08:50 }           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Tiene 2 respuestas de preview:                                  │
│                                                                  │
│  Combine: { trip_id: "a", original: 08:00, new: 08:10 }         │
│  Expand:  { trip_id: "a", original: 08:10, new: 08:50 }         │
│                                                                  │
│  ❌ BUG: Toma original_time del último (Expand) = 08:10         │
│  ✅ FIX: Debe tomar original_time del primero (Combine) = 08:00 │
│                                                                  │
│  Resultado correcto: 08:00 → 08:50                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Solución: combinePreviewChanges()

### 5.1 Lógica Correcta

```typescript
/**
 * Combina los resultados de múltiples previews en una vista unificada.
 *
 * REGLAS:
 * 1. original_time = del PRIMER filtro en el orden de aplicación
 * 2. new_time = del ÚLTIMO filtro en el orden de aplicación
 * 3. El orden lo define el usuario (orden en que agregó los filtros)
 */
function combinePreviewChanges(
  results: FilterStepResult[],
  filterOrder: string[]  // Orden en que el usuario activó los filtros
): TripChangeV2[] {

  // Paso 1: Agrupar cambios por trip_id
  const byTrip = new Map<string, TripChangeV2[]>();

  for (const result of results) {
    for (const change of result.changes) {
      const existing = byTrip.get(change.trip_id) || [];
      existing.push({
        ...change,
        _filterIndex: filterOrder.indexOf(change.filter_applied)
      });
      byTrip.set(change.trip_id, existing);
    }
  }

  // Paso 2: Combinar cambios de cada trip
  const combined: TripChangeV2[] = [];

  for (const [tripId, changes] of byTrip) {
    // Si solo hay un cambio, usarlo directamente
    if (changes.length === 1) {
      combined.push(changes[0]);
      continue;
    }

    // Ordenar por el orden de aplicación de filtros
    const sorted = [...changes].sort((a, b) => a._filterIndex - b._filterIndex);

    const first = sorted[0];                    // Primer filtro aplicado
    const last = sorted[sorted.length - 1];     // Último filtro aplicado

    // Combinar: original del primero, new del último
    combined.push({
      trip_id: first.trip_id,
      pick_up_date: first.pick_up_date,
      hotel_name: first.hotel_name,
      airline: first.airline,
      flight_number: first.flight_number,
      original_time: first.original_time,       // ✅ Del PRIMER filtro
      new_time: last.new_time,                  // ✅ Del ÚLTIMO filtro
      filter_applied: sorted.map(c => c.filter_applied).join('+'),
    });
  }

  return combined;
}
```

### 5.2 Obtener el Orden de Filtros

El `filterOrder` debe reflejar el orden en que el usuario aplicó/activó los filtros:

```typescript
// Opción A: Desde el stack existente + filtros nuevos
async function getFilterOrder(locationId: string, airline: string, date: string): Promise<string[]> {
  // 1. Obtener stack actual (filtros ya aplicados)
  const stack = await api.get(`/v2/.../filters/stack?pick_up_date=${date}`);

  // 2. Extraer orden de filtros del stack
  const appliedOrder = stack.steps
    .sort((a, b) => a.step_order - b.step_order)
    .map(step => step.filter_type);

  // 3. Agregar filtros en preview que no están en el stack
  const previewFilters = getActivePreviewFilters(); // ['expand'] por ejemplo

  return [...appliedOrder, ...previewFilters.filter(f => !appliedOrder.includes(f))];
}

// Opción B: Mantener el orden en el estado del componente
const [filterOrder, setFilterOrder] = useState<string[]>([]);

const handleAddFilter = (filterType: string) => {
  if (!filterOrder.includes(filterType)) {
    setFilterOrder([...filterOrder, filterType]);
  }
};
```

### 5.3 Ejemplo Completo

```typescript
// Estado del componente
const [activeFilters, setActiveFilters] = useState<string[]>(['combine']); // Usuario activó combine
const [previewResults, setPreviewResults] = useState<Map<string, FilterStepResult>>(new Map());

// Cuando el usuario agrega un filtro
const handleToggleFilter = async (filterType: string) => {
  // Actualizar orden
  if (!activeFilters.includes(filterType)) {
    setActiveFilters([...activeFilters, filterType]);
  }

  // Hacer preview
  const result = await api.post('/v2/.../filters/step/preview', {
    filter_type: filterType,
    pick_up_date: selectedDate,
    windows: getWindowsConfig(filterType),
  });

  setPreviewResults(new Map(previewResults).set(filterType, result));
};

// Obtener cambios combinados para mostrar
const getCombinedChanges = (): TripChangeV2[] => {
  const results = Array.from(previewResults.values());
  return combinePreviewChanges(results, activeFilters);
};
```

---

## 6. Casos Especiales

### 6.1 Trip con Solo un Filtro

Si un trip solo fue afectado por un filtro, no hay nada que combinar:

```typescript
// Expand sin Combine previo
changes = [
  { trip_id: "a", original_time: "08:00", new_time: "08:40", filter: "expand" }
]

// Resultado: se usa directamente
combined = [
  { trip_id: "a", original_time: "08:00", new_time: "08:40", filter: "expand" }
]
```

### 6.2 Trip Bloqueado por Priority Rule

Si un trip tiene `combine_applied=true`, Expand NO lo puede modificar:

```typescript
// Trip A ya tiene Combine aplicado
// Preview de Expand NO incluirá Trip A en sus changes
// Solo incluirá Trip A en exclusions con razón "Combine has priority"

combineResult = {
  changes: [{ trip_id: "a", original: "08:00", new: "08:10" }],
  exclusions: []
}

expandResult = {
  changes: [],  // ← Trip A NO aparece aquí
  exclusions: [{
    trip_ids: ["a"],
    reason: "Skipped: Combine has priority"
  }]
}
```

### 6.3 Reduce + Combine + Expand

```typescript
// Orden: reduce → combine → expand
filterOrder = ['reduce', 'combine', 'expand'];

// Previews:
reduceResult  = { changes: [{ trip_id: "a", original: "08:30", new: "08:15" }] }
combineResult = { changes: [{ trip_id: "a", original: "08:15", new: "08:20" }] }
expandResult  = { changes: [{ trip_id: "a", original: "08:20", new: "08:50" }] }

// Combinado:
combined = [{
  trip_id: "a",
  original_time: "08:30",  // Del primero (reduce)
  new_time: "08:50",       // Del último (expand)
  filter_applied: "reduce+combine+expand"
}]
```

---

## 7. Validaciones Recomendadas

### 7.1 Verificar Consistencia de Tiempos

```typescript
function validatePreviewChain(changes: TripChangeV2[]): boolean {
  // Para cada trip con múltiples cambios, verificar que formen una cadena
  // El new_time de un filtro debe ser el original_time del siguiente

  for (let i = 0; i < changes.length - 1; i++) {
    const current = changes[i];
    const next = changes[i + 1];

    if (current.new_time !== next.original_time) {
      console.warn(`Gap en cadena de filtros para trip ${current.trip_id}`);
      return false;
    }
  }

  return true;
}
```

### 7.2 Manejar Filtros Faltantes

```typescript
function combinePreviewChanges(
  results: FilterStepResult[],
  filterOrder: string[]
): TripChangeV2[] {
  // ...

  for (const [tripId, changes] of byTrip) {
    // Verificar que todos los cambios tienen un orden válido
    const unknownFilters = changes.filter(c => !filterOrder.includes(c.filter_applied));

    if (unknownFilters.length > 0) {
      console.warn(`Filtros desconocidos para trip ${tripId}:`, unknownFilters);
      // Agregarlos al final del orden
      unknownFilters.forEach(c => filterOrder.push(c.filter_applied));
    }

    // ... resto de la lógica
  }
}
```

---

## 8. Testing del Fix

### 8.1 Caso de Prueba: Combine + Expand

```typescript
describe('combinePreviewChanges', () => {
  it('should use original_time from first filter and new_time from last', () => {
    const results = [
      {
        filter_type: 'combine',
        changes: [{ trip_id: 'a', original_time: '08:00', new_time: '08:10', filter_applied: 'combine' }]
      },
      {
        filter_type: 'expand',
        changes: [{ trip_id: 'a', original_time: '08:10', new_time: '08:50', filter_applied: 'expand' }]
      }
    ];

    const filterOrder = ['combine', 'expand'];
    const combined = combinePreviewChanges(results, filterOrder);

    expect(combined).toHaveLength(1);
    expect(combined[0].original_time).toBe('08:00');  // Del primero
    expect(combined[0].new_time).toBe('08:50');       // Del último
    expect(combined[0].filter_applied).toBe('combine+expand');
  });
});
```

### 8.2 Caso de Prueba: Orden Inverso

```typescript
it('should respect user-defined filter order (expand first)', () => {
  const results = [
    {
      filter_type: 'expand',
      changes: [{ trip_id: 'b', original_time: '09:00', new_time: '09:40', filter_applied: 'expand' }]
    },
    {
      filter_type: 'combine',
      changes: [{ trip_id: 'b', original_time: '09:40', new_time: '09:45', filter_applied: 'combine' }]
    }
  ];

  // Usuario aplicó expand primero, luego combine
  const filterOrder = ['expand', 'combine'];
  const combined = combinePreviewChanges(results, filterOrder);

  expect(combined[0].original_time).toBe('09:00');  // Del primero (expand)
  expect(combined[0].new_time).toBe('09:45');       // Del último (combine)
  expect(combined[0].filter_applied).toBe('expand+combine');
});
```

---

## 9. Resumen

| Concepto | Valor |
|----------|-------|
| **¿Quién calcula el preview?** | Backend |
| **¿Quién combina los previews?** | Frontend |
| **¿Qué es `original_time`?** | Tiempo de ENTRADA a ese filtro específico |
| **¿Hay orden fijo de filtros?** | NO, es order-free |
| **¿Qué define la prioridad?** | El orden en que el usuario aplicó los filtros |
| **¿Dónde está el bug?** | `combinePreviewChanges()` usa mal `original_time` |
| **¿Cuál es el fix?** | Usar `original_time` del PRIMER filtro, `new_time` del ÚLTIMO |

---

## 10. Contacto

Si tienes dudas sobre el comportamiento del backend, los endpoints disponibles son:

- `GET /v2/.../filters/stack` - Ver stack actual
- `GET /v2/.../filters/eligibility` - Ver trips elegibles
- `POST /v2/.../filters/step/preview` - Preview de un filtro
- `POST /v2/.../filters/step/apply` - Aplicar un filtro

Documentación completa del backend: `GROUND_FILTERS_V2_COMPLETE_DOCUMENTATION.md`
