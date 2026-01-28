# Arquitectura del Estado de Revert en Ground Filters V2

**Para:** Equipo Frontend
**Fecha:** 2026-01-26
**Concepto Clave:** El backend es SIEMPRE la fuente de verdad

---

## 🎯 Concepto Fundamental

### ❌ **INCORRECTO: Pensar que "revert" es un estado separado**

```
❌ NO existe tabla "filter_reverts"
❌ NO existe campo "reverted: boolean"
❌ NO existe cache de "estado revertido"
❌ NO se "guarda" el revert
```

### ✅ **CORRECTO: El revert es simplemente marcar is_active=false**

```
✅ FilterStep.is_active = true  → Filtro APLICADO
✅ FilterStep.is_active = false → Filtro REVERTIDO
✅ Ausencia de FilterStep activo → NO hay filtros
```

---

## 📊 Estados Posibles en el Backend

### Estado 1: Sin Filtros (Nunca Aplicados)

**Base de Datos:**
```sql
-- Tabla filter_steps
SELECT * FROM trips.filter_steps
WHERE location_id = 'xxx' AND airline = 'WN' AND pick_up_date = '2026-01-15';

-- Resultado: (0 rows)  ← NO existe FilterStep
```

**GET /stack Response:**
```json
{
  "steps": [],
  "total_trips_affected": 0
}
```

**Trips:**
```sql
-- Tabla trips
original_pick_up_time: NULL
reduce_applied: false
pick_up_time: "08:30"  (tiempo original)
```

---

### Estado 2: Filtro Aplicado (Activo)

**Base de Datos:**
```sql
-- Tabla filter_steps
id          | abc-123
is_active   | true     ← ACTIVO
filter_type | reduce
pick_up_date| 2026-01-15
windows     | [{"minutes_to_reduce": 10, ...}]
```

**GET /stack Response:**
```json
{
  "steps": [
    {
      "step_id": "abc-123",
      "filter_type": "reduce",
      "windows": [{"minutes_to_reduce": 10}],
      "is_active": true
    }
  ],
  "total_trips_affected": 25
}
```

**Trips:**
```sql
original_pick_up_time: "08:30"  (guardado)
reduce_applied: true
pick_up_time: "08:20"  (modificado -10min)
```

---

### Estado 3: Filtro Revertido (Inactivo)

**Base de Datos:**
```sql
-- Tabla filter_steps
id          | abc-123
is_active   | false    ← INACTIVO (revertido)
filter_type | reduce
pick_up_date| 2026-01-15
windows     | [{"minutes_to_reduce": 10, ...}]  ← Config se mantiene
```

**GET /stack Response:**
```json
{
  "steps": [],  // ← VACÍO (filtra is_active=true)
  "total_trips_affected": 0
}
```

**Trips:**
```sql
original_pick_up_time: NULL     (limpiado)
reduce_applied: false           (limpiado)
pick_up_time: "08:30"           (restaurado a original)
```

---

## 🔑 La Clave: is_active

### Tabla filter_steps

```sql
CREATE TABLE trips.filter_steps (
    id UUID PRIMARY KEY,
    location_id UUID,
    airline VARCHAR(10),
    pick_up_date DATE,
    filter_type VARCHAR(20),
    windows JSONB,
    is_active BOOLEAN DEFAULT true,  ← ESTE CAMPO ES LA CLAVE
    ...
);
```

**is_active = true:** Filtro está APLICADO y ACTIVO
**is_active = false:** Filtro fue REVERTIDO

**GET /stack solo retorna FilterSteps con is_active=true:**

```python
# step_filter_service.py:323-330
query = (
    Select(FilterStep)
    .Where(FilterStep.is_active == True)  # ← Solo activos
    .OrderBy(FilterStep.step_order.Asc())
)
```

---

## ❓ Respondiendo tus Preguntas

### Pregunta 1: "¿Dónde se debería guardar el revert?"

**Respuesta:** El revert NO se "guarda" en ningún lado separado.

El revert es simplemente:
```sql
UPDATE filter_steps
SET is_active = false  -- ← Esto es el "revert"
WHERE id = 'step-uuid';
```

**NO hay:**
- ❌ Tabla de "reverts"
- ❌ Campo "reverted: boolean"
- ❌ Historial de reverts
- ❌ Cache de estado revertido

**Solo hay:**
- ✅ FilterStep marcado como `is_active=false`
- ✅ Ese FilterStep se mantiene en la DB para historial
- ✅ PERO no aparece en `GET /stack` (filtra solo activos)

---

### Pregunta 2: "¿Después de un tiempo se pierde el revert?"

**Respuesta:** NO debería perderse SI usas el backend como fuente de verdad.

#### Flujo Correcto (Backend como Source of Truth):

```
1. Usuario aplica Reduce
   → Backend: Crea FilterStep con is_active=true
   → GET /stack retorna: [{ filter_type: "reduce", ... }]
   → Frontend: savedReduce.enabled = true ✅

2. Usuario revierte Reduce
   → Backend: Marca FilterStep como is_active=false
   → GET /stack retorna: [] (vacío)
   → Frontend: savedReduce.enabled = false ✅

3. Usuario hace F5 (refresca página)
   → Frontend: Llama GET /stack
   → Backend retorna: [] (vacío, porque is_active=false)
   → Frontend: savedReduce.enabled = false ✅
   → Estado se mantiene correcto ✅
```

#### Flujo Incorrecto (Frontend usa cache local):

```
1. Usuario aplica Reduce
   → Frontend: localStorage.setItem('reduce', 'applied')
   → savedReduce.enabled = true

2. Usuario revierte Reduce
   → Frontend: localStorage.setItem('reduce', 'reverted')
   → savedReduce.enabled = false

3. Usuario hace F5
   → Frontend: Lee localStorage ('reverted')
   → PERO también llama GET /stack
   → Backend retorna: [] (no hay steps activos)
   → CONFLICTO: localStorage dice 'reverted', backend dice []
   → Frontend se confunde ❌
```

---

### Pregunta 3: "¿El revert se guarda independiente por cada tipo de filtro?"

**Respuesta:** Cada FilterStep es independiente.

```sql
-- Ejemplo: Location tiene 3 filtros aplicados a un día

SELECT filter_type, is_active FROM filter_steps
WHERE location_id = 'xxx'
  AND airline = 'WN'
  AND pick_up_date = '2026-01-15';

-- Resultado:
filter_type | is_active
------------+----------
reduce      | true      ← Aplicado
combine     | false     ← Revertido
expand      | true      ← Aplicado
```

**GET /stack retorna solo los activos:**
```json
{
  "steps": [
    { "filter_type": "reduce" },   // ← Activo
    { "filter_type": "expand" }    // ← Activo
  ]
  // combine NO aparece (is_active=false)
}
```

**Sí, cada tipo de filtro tiene su propio FilterStep independiente.**

---

## 🎯 Source of Truth Hierarchy

```
┌─────────────────────────────────────────────────────┐
│  1. PostgreSQL (trips.filter_steps)                  │
│     ↓                                                │
│     Campo: is_active (true/false)                   │
│     ↓                                                │
│     VERDAD ABSOLUTA                                 │
└─────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────┐
│  2. GET /stack (API Endpoint)                        │
│     ↓                                                │
│     Retorna: FilterSteps con is_active=true         │
│     ↓                                                │
│     FUENTE DE VERDAD PARA FRONTEND                  │
└─────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────┐
│  3. savedState (Frontend)                            │
│     ↓                                                │
│     Parsea response de GET /stack                   │
│     ↓                                                │
│     CACHÉ LOCAL (debe sincronizar con backend)      │
└─────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────┐
│  4. state (Frontend)                                 │
│     ↓                                                │
│     Copia de savedState + ediciones del usuario     │
│     ↓                                                │
│     ESTADO EDITABLE (puede diferir de backend)      │
└─────────────────────────────────────────────────────┘
```

---

## ✅ Reglas para el Frontend

### Regla 1: SIEMPRE Usar Backend como Source of Truth

```javascript
// ❌ INCORRECTO - No confiar solo en localStorage
const isApplied = localStorage.getItem('reduce_applied') === 'true';

// ✅ CORRECTO - Usar GET /stack del backend
const stack = await GET('/stack?pick_up_date=2026-01-15');
const isApplied = stack.steps.some(s => s.filter_type === 'reduce');
```

### Regla 2: Sincronizar Después de Cada Operación

```javascript
// Después de Apply
await POST('/step/apply', config);
await rehidration.reload();  // ← Sincronizar con backend

// Después de Revert
await POST('/revert-last');
await rehidration.reload();  // ← Sincronizar con backend

// Después de F5
useEffect(() => {
  rehidration.reload();  // ← Cargar desde backend
}, []);
```

### Regla 3: NO Guardar Estado de Revert en localStorage

```javascript
// ❌ INCORRECTO
localStorage.setItem('reduce_reverted', 'true');

// ✅ CORRECTO - No guardar nada
// El backend (GET /stack) es la fuente de verdad
```

---

## 🔄 Ciclo de Vida de un Filtro

```
┌──────────────────────────────────────────────────────────┐
│  1. INICIAL: Sin Filtros                                  │
├──────────────────────────────────────────────────────────┤
│  PostgreSQL:  (no existe FilterStep)                     │
│  GET /stack:  steps: []                                  │
│  Frontend:    savedReduce.enabled = false                │
└──────────────────────────────────────────────────────────┘
                    ↓ Apply Reduce
┌──────────────────────────────────────────────────────────┐
│  2. APLICADO: Filtro Activo                              │
├──────────────────────────────────────────────────────────┤
│  PostgreSQL:  FilterStep { is_active: true }             │
│  GET /stack:  steps: [{ filter_type: "reduce" }]         │
│  Frontend:    savedReduce.enabled = true                 │
└──────────────────────────────────────────────────────────┘
                    ↓ Revert Reduce
┌──────────────────────────────────────────────────────────┐
│  3. REVERTIDO: Filtro Inactivo                           │
├──────────────────────────────────────────────────────────┤
│  PostgreSQL:  FilterStep { is_active: false }            │
│  GET /stack:  steps: [] (no retorna inactivos)           │
│  Frontend:    savedReduce.enabled = false                │
└──────────────────────────────────────────────────────────┘
                    ↓ F5 (Refresh)
┌──────────────────────────────────────────────────────────┐
│  4. DESPUÉS DE F5: Rehidratación                         │
├──────────────────────────────────────────────────────────┤
│  Frontend:    Llama GET /stack                           │
│  Backend:     Retorna: steps: []                         │
│  Frontend:    Parse: savedReduce.enabled = false         │
│  Estado:      ✅ Correcto (revertido se mantiene)        │
└──────────────────────────────────────────────────────────┘
```

**El estado de "revertido" se mantiene automáticamente** porque:
- El FilterStep sigue en la DB con `is_active=false`
- `GET /stack` NO lo retorna
- El frontend parsea `steps: []` como `enabled: false`

---

## 🔍 Dónde se Almacena Cada Estado

### Por Tipo de Filtro

| Filtro | Tabla | Columna Clave | Valor Aplicado | Valor Revertido |
|--------|-------|---------------|----------------|-----------------|
| **Reduce** | filter_steps | is_active | `true` | `false` |
| **Combine** | filter_steps | is_active | `true` | `false` |
| **Expand** | filter_steps | is_active | `true` | `false` |

**SÍ, cada tipo tiene su propio registro de FilterStep independiente.**

### Ejemplo con Múltiples Filtros

```sql
-- Location tiene 3 filtros para el mismo día
SELECT
    filter_type,
    is_active,
    step_order,
    trips_affected
FROM trips.filter_steps
WHERE location_id = 'xxx'
  AND airline = 'WN'
  AND pick_up_date = '2026-01-15'
ORDER BY step_order;

-- Resultado:
filter_type | is_active | step_order | trips_affected
------------+-----------+------------+---------------
reduce      | true      | 1          | 25
combine     | false     | 2          | 10   ← Revertido
expand      | true      | 3          | 5
```

**GET /stack retorna:**
```json
{
  "steps": [
    { "filter_type": "reduce", "step_order": 1 },
    { "filter_type": "expand", "step_order": 3 }
  ]
  // combine NO aparece (is_active=false)
}
```

**Interpretación:**
- ✅ Reduce: Aplicado (appears en GET /stack)
- ❌ Combine: Revertido (NO aparece en GET /stack)
- ✅ Expand: Aplicado (appears en GET /stack)

---

## ⚠️ Por Qué Se "Pierde" el Estado

### Causa 1: Frontend NO Llama GET /stack al Cargar

```javascript
// ❌ PROBLEMA
useEffect(() => {
  // NO llama rehidration.reload()
  // Usa valores por defecto o localStorage
}, []);

// ✅ SOLUCIÓN
useEffect(() => {
  if (locationId && airline && pickUpDate) {
    rehidration.reload();  // ← Sincronizar con backend
  }
}, [locationId, airline, pickUpDate]);
```

### Causa 2: Frontend Usa Fecha Incorrecta

```javascript
// ❌ PROBLEMA
await GET('/stack?pick_up_date=2026-01-01');
// Pero los filtros están en 2026-01-15
// Backend retorna: steps: [] (correcto para esa fecha)
// Frontend interpreta como "revertido" (incorrecto)

// ✅ SOLUCIÓN
const currentDate = getCurrentPickUpDate();  // Fecha correcta
await GET(`/stack?pick_up_date=${currentDate}`);
```

### Causa 3: Frontend Guarda Estado Local que Se Desincroniza

```javascript
// ❌ PROBLEMA
localStorage.setItem('filters_state', JSON.stringify({
  reduce: { enabled: true }
}));

// Luego backend revierte el filtro (otro usuario, otro tab, etc.)
// localStorage sigue diciendo enabled: true
// DESINCRONIZACIÓN ❌

// ✅ SOLUCIÓN
// NO usar localStorage para estado de filtros
// SIEMPRE obtener de GET /stack
```

---

## ✅ Implementación Correcta del Frontend

### Al Cargar la Página (F5, Mount)

```javascript
// Component mount o al abrir drawer
useEffect(() => {
  async function loadFiltersFromBackend() {
    // 1. Llamar GET /stack
    const stack = await axios.get(
      `/v2/locations/${locationId}/airlines/${airline}/filters/stack`,
      { params: { pick_up_date: pickUpDate } }
    );

    // 2. Parse response
    const reduceStep = stack.data.steps.find(s => s.filter_type === 'reduce');
    const combineStep = stack.data.steps.find(s => s.filter_type === 'combine');
    const expandStep = stack.data.steps.find(s => s.filter_type === 'expand');

    // 3. Actualizar savedState (source of truth local)
    setSavedReduce(reduceStep ? parseStep(reduceStep) : { enabled: false, windows: [] });
    setSavedCombine(combineStep ? parseStep(combineStep) : { enabled: false, windows: [] });
    setSavedExpand(expandStep ? parseStep(expandStep) : { enabled: false, windows: [] });

    // 4. Inicializar state editable
    setState({
      reduce: savedReduce,
      combine: savedCombine,
      expand: savedExpand
    });
  }

  loadFiltersFromBackend();
}, [locationId, airline, pickUpDate]);
```

### Después de Apply

```javascript
async function applyChanges() {
  // 1. Apply al backend
  const response = await POST('/step/apply', config);

  // 2. CRÍTICO: Sincronizar con backend inmediatamente
  await rehidration.reload(pickUpDate);

  // 3. savedState se actualiza con GET /stack
  // 4. isDirty se recalcula y se vuelve false ✅
}
```

### Después de Revert

```javascript
async function revertFilter(filterType) {
  // 1. Revert en backend
  const response = await POST('/revert-last');

  // 2. CRÍTICO: Actualizar con response.stack_state
  const { stack_state } = response.data;

  // Parse stack_state y actualizar savedState
  updateSavedStateFromBackend(stack_state);

  // 3. Limpiar appliedSteps
  setAppliedSteps([]);

  // 4. Refetch trips
  await queryClient.invalidateQueries(['trips']);
}
```

---

## 🔒 Garantizar Persistencia del Estado

### Lo Que DEBE Hacer el Frontend

```javascript
// ============================================
// ÚNICA FUENTE DE VERDAD: GET /stack
// ============================================

// 1. Al cargar página
await rehidration.reload();

// 2. Después de Apply
await rehidration.reload();

// 3. Después de Revert
updateFromBackend(response.stack_state);

// 4. Al cambiar fecha
await rehidration.reload(newPickUpDate);

// 5. Al recibir WebSocket event
await rehidration.reload();
```

### Lo Que NO Debe Hacer el Frontend

```javascript
// ❌ NO guardar en localStorage
localStorage.setItem('filters', ...);

// ❌ NO confiar solo en estado local
const isApplied = localState.reduce.enabled;

// ❌ NO usar appliedSteps como source of truth
const isApplied = appliedSteps.includes('reduce');
```

---

## 🗄️ Almacenamiento en PostgreSQL

### Estructura Real de la Tabla

```sql
CREATE TABLE trips.filter_steps (
    -- Identificación
    id UUID PRIMARY KEY,
    location_id UUID,     -- Cada location independiente
    airline VARCHAR(10),  -- Cada airline independiente
    pick_up_date DATE,    -- Cada fecha independiente

    -- Configuración
    filter_type VARCHAR(20),  -- "reduce" | "combine" | "expand"
    windows JSONB,            -- Configuración completa
    step_order INT,           -- Orden en el stack

    -- Estado
    is_active BOOLEAN,        -- true=aplicado, false=revertido

    -- Metadata
    trips_affected INT,
    created_at TIMESTAMPTZ
);

-- Índices importantes
CREATE INDEX ON filter_steps (location_id, airline, pick_up_date, is_active);
```

### Queries Importantes

```sql
-- Ver estado actual de filtros para un día
SELECT
    filter_type,
    is_active,
    step_order,
    trips_affected,
    created_at
FROM trips.filter_steps
WHERE location_id = 'xxx'
  AND airline = 'WN'
  AND pick_up_date = '2026-01-15'
ORDER BY step_order;

-- Ver solo filtros activos (lo que retorna GET /stack)
SELECT * FROM trips.filter_steps
WHERE location_id = 'xxx'
  AND airline = 'WN'
  AND pick_up_date = '2026-01-15'
  AND is_active = true  -- ← Solo activos
ORDER BY step_order;

-- Ver historial completo (incluyendo revertidos)
SELECT * FROM trips.filter_steps
WHERE location_id = 'xxx'
  AND airline = 'WN'
  AND pick_up_date = '2026-01-15'
ORDER BY created_at DESC;  -- Todos (activos e inactivos)
```

---

## 📋 Checklist de Implementación

Para asegurar que el estado de revert se mantenga:

- [ ] **1. GET /stack es la única fuente de verdad**
  ```javascript
  const isApplied = savedState.reduce.enabled;  // ✅
  // NO: appliedSteps.includes('reduce')  ❌
  ```

- [ ] **2. Sincronizar después de cada operación**
  ```javascript
  await apply(); await rehidration.reload();
  await revert(); updateFromBackend(response.stack_state);
  ```

- [ ] **3. NO usar localStorage para filtros**
  ```javascript
  // ❌ NO hacer esto
  localStorage.setItem('filters_state', ...);
  ```

- [ ] **4. Usar pickUpDate correcto**
  ```javascript
  await GET(`/stack?pick_up_date=${currentPickUpDate}`);
  ```

- [ ] **5. Parsear correctamente is_active**
  ```javascript
  // Backend retorna steps solo si is_active=true
  // Si steps: [] → Todos están revertidos
  ```

---

## 🐛 Debugging: "Se Pierde el Revert"

### Paso 1: Verificar Qué Retorna el Backend

```javascript
// En la consola del navegador
const stack = await fetch(
  '/v2/locations/XXX/airlines/WN/filters/stack?pick_up_date=2026-01-15',
  { headers: { Authorization: `Bearer ${token}` } }
).then(r => r.json());

console.log('Backend retorna:', stack);

// Si steps: [] → Backend dice que está revertido ✅
// Si steps: [...] → Backend dice que está aplicado ✅
```

### Paso 2: Verificar Qué Hace el Frontend

```javascript
// Agregar logs en rehidration
console.log('[Rehidration] Backend response:', response);
console.log('[Rehidration] Parsed reduce:', {
  enabled: reduceStep ? true : false,
  hasStep: !!reduceStep
});

// Si backend retorna [] pero frontend muestra enabled=true
// → Problema en el parsing del frontend ❌
```

### Paso 3: Verificar PostgreSQL Directamente

```sql
-- Conectar a PostgreSQL
SELECT
    filter_type,
    is_active,
    created_at
FROM trips.filter_steps
WHERE location_id = 'xxx'
  AND airline = 'WN'
  AND pick_up_date = '2026-01-15';

-- Si is_active=false → Revertido en DB ✅
-- Si is_active=true → Aplicado en DB (no debería "perderse") ✅
```

---

## 💡 Resumen Ejecutivo

### ¿Dónde se guarda el revert?

**Respuesta:** En PostgreSQL, campo `FilterStep.is_active`

```
is_active = true  → Filtro aplicado
is_active = false → Filtro revertido
```

### ¿Es independiente por tipo de filtro?

**Respuesta:** SÍ, cada tipo tiene su propio FilterStep

```
reduce:  FilterStep { filter_type: "reduce", is_active: true }
combine: FilterStep { filter_type: "combine", is_active: false }
expand:  FilterStep { filter_type: "expand", is_active: true }
```

### ¿Por qué se pierde después de un tiempo?

**Respuesta:** NO debería perderse SI el frontend:
1. ✅ Llama `GET /stack` al cargar
2. ✅ Usa `savedState` como source of truth
3. ✅ NO usa localStorage para filtros
4. ✅ Usa pickUpDate correcto

**Si se pierde:**
- ❌ Frontend NO está llamando `GET /stack` correctamente
- ❌ Frontend está usando fecha incorrecta
- ❌ Frontend está confiando en cache local desincronizado

---

## 🎯 Solución Definitiva

```javascript
// ============================================
// PATRÓN CORRECTO - Backend como Source of Truth
// ============================================

// Estado del frontend:
const [savedState, setSavedState] = useState({
  reduce: { enabled: false, windows: [] },
  combine: { enabled: false, windows: [] },
  expand: { enabled: false, windows: [] }
});

// SIEMPRE sincronizar con backend:
async function syncWithBackend(pickUpDate: string) {
  // 1. GET /stack del backend
  const stack = await GET(`/stack?pick_up_date=${pickUpDate}`);

  // 2. Parse steps
  const newState = {
    reduce: parseFilterType(stack.steps, 'reduce'),
    combine: parseFilterType(stack.steps, 'combine'),
    expand: parseFilterType(stack.steps, 'expand')
  };

  // 3. Actualizar savedState
  setSavedState(newState);

  // 4. Retornar estado
  return newState;
}

// Helper
function parseFilterType(steps: FilterStep[], type: string) {
  const step = steps.find(s => s.filter_type === type);

  return step
    ? { enabled: true, windows: step.windows }  // ← Aplicado
    : { enabled: false, windows: [] };           // ← Revertido o nunca aplicado
}

// Usar en:
// - Component mount
// - Después de Apply
// - Después de Revert
// - Al cambiar pickUpDate
// - Al recibir WebSocket events
```

**Con este patrón, el estado de revert NUNCA se pierde.** ✅

---

## 📚 Documentación Relacionada

- [GROUND_FILTERS_V2_COMPLETE_DOCUMENTATION.md](GROUND_FILTERS_V2_COMPLETE_DOCUMENTATION.md) - Sección "Guía Completa de Revert"
- [FRONTEND_REVERT_IMPLEMENTATION_GUIDE.md](FRONTEND_REVERT_IMPLEMENTATION_GUIDE.md) - Código completo de implementación

---

**CONCLUSIÓN:** El backend guarda el estado de revert en `FilterStep.is_active` (PostgreSQL). El frontend debe SIEMPRE usar `GET /stack` como fuente de verdad para saber qué filtros están aplicados o revertidos. NO debe confiar en localStorage ni estado local que pueda desincronizarse.
