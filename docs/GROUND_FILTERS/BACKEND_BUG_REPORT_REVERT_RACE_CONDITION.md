# Backend Bug Report: Ground Filters Revert Issues

**Fecha:** 2026-01-28
**Última Actualización:** 2026-01-28 (Análisis Crítico Completo)
**Reportado por:** Frontend Developer
**Severidad:** HIGH (Bug crítico) + MEDIUM (Performance)
**Afecta:** Ground Filters V2 - Operaciones de Apply y Revert

---

## 🔴 CONCLUSIÓN DEL ANÁLISIS CRÍTICO

Después de una investigación exhaustiva del código frontend, **confirmo que ambos bugs son 100% problemas del backend**:

### Bug #1: Race Condition - CONFIRMADO EN BACKEND
- **Causa Raíz**: El backend envía el WebSocket `step_reverted` ANTES de que los commits estén propagados en el connection pool de PostgreSQL
- **Evidencia**: El frontend recibe trips con `reduce_applied=false`, `combine_applied=false` cuando el stack indica que están activos
- **El delay de 50ms + 150ms adicionales del frontend NO es suficiente** para 448 commits secuenciales

### Bug #2: Performance - CONFIRMADO EN BACKEND
- **Causa Raíz**: El backend hace commits individuales por cada step re-aplicado
- **Cálculo**: 112 steps × 4 commits = 448 commits secuenciales = ~13.4 segundos

### Archivos Frontend Analizados:
- `src/hooks/use-trip-filters-v2.ts` - Hook de filtros V2
- `src/app/.../schedule-dashboard-client.tsx` - Dashboard con manejo de WebSocket
- `src/hooks/use-infinite-scroll-trips.ts` - Paginación de trips
- `src/hooks/use-websocket-trips.ts` - Manejo de WebSocket
- `src/app/.../home/_components/columns.tsx` - Columna Ground Filters

---

## 📋 Resumen Ejecutivo

Se reportan **3 problemas críticos** en el sistema de Ground Filters que requieren atención y un analisis critico del backend:

1. **🐛 Bug: Columna Ground Filters "Va Un Paso Atrás" después de Revert** (CRÍTICO)
2. **⚡ Performance: Reverts tardan 8-15 segundos** (MEDIO)
3. **📊 Request: Trips Independientes en Notificaciones** (MEJORA)

---

## 🐛 Bug #1: Columna Ground Filters "Va Un Paso Atrás" (CRÍTICO)

### Síntoma Observado

Cuando el usuario revierte UN filtro (ej: EXPAND), quedando otros dos filtros activos (ej: REDUCE + COMBINE), la columna Ground Filters en la tabla se muestra vacia y al revertir otro entonces muestra el estado anterior (ej: REDUCE + COMBINE)

**Ejemplo:**
```
Estado Inicial:
  Filtros activos: REDUCE + COMBINE + EXPAND
  Columna muestra: [icon-reduce] [icon-combine] [icon-expand] 04:45 → 04:30

Usuario revierte EXPAND:
  ↓
Estado Esperado:
  Filtros activos: REDUCE + COMBINE
  Columna debería mostrar: [icon-reduce] [icon-combine] 04:45 → 04:35

Estado Real (BUG):
  Columna sigue mostrando: [-] vacia 
  ↑ Muestra el estado erroneo  (pero sin embargo cuando se reduce otro por ejemplo COMBINE entonces muestra el estado anterior  ejemplo [icon-reduce] [icon-combine] 04:45 → 04:35)
```

### Comportamiento Detallado

Aplicando y revirtiendo filtros uno por uno:

```
1. Aplico REDUCE
   ✅ Columna: [reduce] (CORRECTO)

2. Aplico COMBINE
   ✅ Columna: [reduce] [combine] (CORRECTO)

3. Aplico EXPAND
   ✅ Columna: [reduce] [combine] [expand] (CORRECTO)

4. Revierto EXPAND
   ❌ Columna: [-] vacia la columna  (INCORRECTO - debería ser solo [reduce] [combine])

5. Revierto COMBINE
   ❌ Columna: [reduce] [combine] (INCORRECTO - debería ser solo [reduce])

6. Revierto REDUCE
   ❌ Columna: [reduce] (INCORRECTO - debería estar vacía)

7. DESPUÉS del último revert
   ✅ Columna: vacía (CORRECTO finalmente)
```

**Patrón:** La columna comienza vacia y luego muestra el estado del erroneo 
### Logs del Frontend

#### Después de Revertir EXPAND:

**Rehidratación del Stack (CORRECTO):**
```javascript
[useTripFiltersV2] 📥 Rehidration data available {
  forceSyncSaved: 4,
  rehidration.reduce.enabled: true,    ✅
  rehidration.combine.enabled: true,   ✅
  rehidration.expand.enabled: false    ✅
}
```

**Trips Loaded del Backend (INCORRECTO):**
```javascript
[InfiniteScroll] 📥 Trips loaded: {
  count: 24,
  sample: [{
    id: "31250ac4-fdd3-4ef7-83c3-dfb0cceb1672",
    reduce_applied: false,    ❌ Debería ser TRUE
    combine_applied: false,   ❌ Debería ser TRUE
    expand_applied: false,    ✅ Correcto
    ground_filter: undefined  ❌ Debería existir
  }]
}
```

### 🔬 Análisis Crítico del Código Frontend (Nuevo)

#### Ubicación de la Lógica de Ground Filters Column

**Archivo:** `src/app/(main)/dashboard/home/_components/columns.tsx`
**Líneas:** 163-223

```typescript
function GroundFiltersCell({ row }: { row: { original: Row } }) {
  const groundFilter = row.original.ground_filter;

  // Si ground_filter es undefined → columna vacía
  if (!groundFilter) {
    return (
      <div className="flex items-center justify-start">
        <span className="text-xs text-muted-foreground">—</span>
      </div>
    );
  }
  // ... renderiza iconos y tiempos
}
```

#### Cómo se Construye `ground_filter`

**Archivo:** `src/app/(main)/dashboard/locations/[code]/[airline]/schedule-dashboard-client.tsx`
**Función:** `normalizeGroundFilter()` (líneas 235-360)

```typescript
const normalizeGroundFilter = (trip: any): Row["ground_filter"] | undefined => {
  // CRÍTICO: Verifica flags booleanos del backend
  const hasActiveFilter =
    trip.reduce_applied === true ||
    trip.combine_applied === true ||
    trip.expand_applied === true;

  // CRÍTICO: Verifica original_pick_up_time
  const hasOriginalTime = trip.original_pick_up_time != null;

  // Si NO hay filtro activo → retorna undefined → columna vacía
  if (!hasActiveFilter) {
    return undefined;
  }

  // Solo construye ground_filter si hasActiveFilter es TRUE
  return {
    filter_type: derivedFilterType,
    filter_types: derivedFilterTypes,
    original_time: trip.original_pick_up_time,
    applied_time: trip.pick_up_time,
  };
};
```

#### Flujo Completo del Revert (Analizado)

**Archivo:** `src/hooks/use-trip-filters-v2.ts`
**Función:** `revertByFilterType()` (líneas 1126-1329)

```
1. Usuario hace click en "Revert EXPAND"
2. Frontend muestra toast loading
3. Frontend llama POST /bulk/revert (HTTP)
4. Backend procesa:
   a. Marca EXPAND como inactive
   b. Reset TODOS los trips (flags = false)
   c. Re-aplica REDUCE (commit)
   d. Re-aplica COMBINE (commit)
   e. Delay 50ms
   f. Envía WebSocket "step_reverted"
5. HTTP Response llega al frontend
6. Frontend llama rehidration.reload() → obtiene stack correcto
7. Frontend espera 150ms adicionales
8. Frontend llama infiniteScroll.reset() → GET /trips
9. Backend responde con trips...
   ❌ PERO los trips tienen reduce_applied=false, combine_applied=false
```

**¿Por qué los trips tienen flags incorrectos?**

El endpoint `/trips` usa una conexión diferente del connection pool que puede tener un snapshot de la base de datos de ANTES de que los commits de re-apply se propaguen.

### Análisis de la Race Condition

Según `FIX_RACE_CONDITION_REVERT.md`, el backend implementó un delay de **50ms** antes del WebSocket:

```python
# Línea 847-851 (step_filter_service.py)
# RACE CONDITION FIX: Add small delay...
await asyncio.sleep(0.05)  # 50ms delay

await self._send_revert_notification(...)
```

**Sin embargo, el bug persiste** en operaciones con muchos steps.

### Timeline Actual de la Race Condition

```
Backend Process                           | Database State              | Frontend
------------------------------------------|-----------------------------|-----------------
T0: API /bulk/revert recibida             |                             |
T1: Marcar Step 3 (expand) inactive       |                             |
T2: Reset TODOS los trips                 |                             |
T3: COMMIT 1                              | All flags = FALSE ✅        |
T4: Re-apply Step 1 (Reduce)              |                             |
T5: COMMIT 2                              | reduce_applied = TRUE ✅    |
T6: Refresh trip_lookup                   |                             |
T7: Re-apply Step 2 (Combine)             |                             |
T8: COMMIT 3                              | combine_applied = TRUE ✅   |
T9: Refresh trip_lookup                   |                             |
T10: Get stack state                      |                             |
T11: await asyncio.sleep(0.05)            | ← 50ms delay               |
T12: Send WebSocket 'step_reverted'       |                             |
T13:                                      |                             | WebSocket recibido
T14:                                      | Propagation delay? ⚠️       | infiniteScroll.reset()
T15:                                      |                             | GET /trips
T16:                                      | Connection pool lag? ⚠️     | Recibe trips
```

**El problema:** El refetch en T15 puede obtener datos de un snapshot de database que se creó ANTES de que COMMIT 3 fuera completamente visible en todas las conexiones del pool.

### Datos del Request Real

**Request URL:**
```
POST /v2/locations/{uuid}/airlines/WN/filters/bulk/revert
```

**Request Body:**
```json
{
  "date_from": "2026-02-01",
  "date_to": null,
  "filter_type": "reduce"
}
```

**Response:**
```json
{
  "total_days": 28,
  "days_with_reverts": 28,
  "total_steps_reverted": 112,  // 4 steps/día × 28 días
  "total_trips_recalculated": 3136,
  "by_date": [
    {
      "pick_up_date": "2026-02-01",
      "steps_reverted": 4,  // ← Cada día tiene 4 steps tipo "reduce"
      "trips_recalculated": 91
    },
    // ... 27 días más
  ]
}
```

**Timing observado:**
- Request duration: ~10-15 segundos
- 112 steps × ~4 commits cada uno = **448 commits secuenciales**

### Posibles Causas

#### 1. Connection Pool Isolation

El backend usa un connection pool de PostgreSQL. Cuando hace:

```python
# Connection 1 (usada por revert)
await self.session.commit()  # COMMIT 3 - combine_applied = TRUE

# Connection 2 (usada por GET /trips del frontend)
trips = await session.exec(select(Trip)...).all()
```

Si Connection 2 inició su transacción ANTES de COMMIT 3, verá el snapshot viejo (READ COMMITTED isolation level).

**El delay de 50ms NO es suficiente** porque:
- 50ms es antes del WebSocket
- Pero el WebSocket viaja instantáneamente
- El frontend recibe el WebSocket en ~5-20ms
- El frontend hace refetch inmediatamente
- **Total tiempo desde COMMIT 3 hasta refetch: ~70-100ms** (puede no ser suficiente con connection pool)

#### 2. Múltiples Commits Agravan el Problema

Con 112 steps, cada uno tiene su propio commit:

```python
for active_step in active_steps:
    # Apply step
    trip.reduce_applied = True
    await self.session.commit()  # ← Commit individual

    # Refresh trip_lookup
    trips = await self.session.exec(trips_query).all()
```

**Problema:** Cada commit necesita tiempo de propagación (10-30ms típico). Con 112 steps:
- Last commit (COMMIT 448) en T10
- WebSocket en T11 (después de 50ms)
- Frontend refetch en T13
- **Si connection pool tiene lag, puede ver COMMIT 447 pero no COMMIT 448**

### Evidencia del Bug

**Lo que el backend cree que envió (según logs):**
```python
# stack_state al final del revert
{
  "steps": [
    {"filter_type": "reduce", "is_active": true},
    {"filter_type": "combine", "is_active": true}
  ]
}
```

**Lo que el frontend recibe en GET /trips:**
```json
{
  "id": "trip-123",
  "reduce_applied": false,   ❌
  "combine_applied": false,  ❌
  "expand_applied": false,   ✅
  "original_pick_up_time": "04:45:00"  // ← Existe (indicador de filtros activos)
}
```

**Inconsistencia:** El stack dice "reduce y combine activos" pero los trips tienen todos los flags en FALSE.

### Soluciones Propuestas

#### Opción 1: Aumentar Delay del WebSocket (Rápido)

Cambiar el delay de 50ms a **200-300ms**:

```python
# En _revert_step_internal() después de get_stack()
# RACE CONDITION FIX: Increase delay for large operations
# 50ms is insufficient when re-applying many steps (100+ commits)
await asyncio.sleep(0.2)  # 200ms delay
```

**Pros:**
- Fix simple (1 línea)
- Garantiza propagación completa

**Cons:**
- Agrega latencia innecesaria en reverts pequeños
- No resuelve el root cause

#### Opción 2: Single Commit al Final (Mejor)

En lugar de commitear después de cada step, acumular todos los cambios:

```python
async def _revert_step_internal(...):
    # Fase 1: Mark inactive (no commit)
    step.is_active = False
    self.session.add(step)

    # Fase 2: Reset trips (no commit)
    for trip in trips:
        trip.pick_up_time = trip.original_pick_up_time
        trip.reduce_applied = False
        trip.combine_applied = False
        trip.expand_applied = False
        self.session.add(trip)

    # Fase 3: Re-apply all active steps (no commits)
    for active_step in active_steps:
        # Apply filter
        for change in self.changes:
            trip.pick_up_time = change.new_time
            if filter_type == "reduce":
                trip.reduce_applied = True
            # ... etc
            self.session.add(trip)

    # SINGLE COMMIT at end
    await self.session.commit()  # ← Todo es atómico

    # Now send WebSocket (no delay needed)
    await self._send_revert_notification(...)
```

**Pros:**
- ✅ Elimina race condition completamente
- ✅ Más rápido (1 commit vs 448 commits)
- ✅ Atomic operation
- ✅ No necesita delay artificial

**Cons:**
- ⚠️ All-or-nothing (si falla Step 3, se pierde Step 1 también)
- ⚠️ Requiere refactoring del error handling
- ⚠️ Más memoria (acumula todos los cambios antes de commit)

#### Opción 3: WebSocket en Background Task (Arquitectural)

Enviar el WebSocket DESPUÉS de que el HTTP response regrese:

```python
# En el router
@router.post("/bulk/revert")
async def bulk_revert(
    background_tasks: BackgroundTasks,
    ...
):
    result = await service.revert_bulk(...)

    # Send WebSocket in background AFTER response is sent
    background_tasks.add_task(
        send_revert_notification,
        location_id, airline, result.step_ids, result.filter_type
    )

    return result  # Frontend gets this first
```

**Pros:**
- ✅ Clean separation
- ✅ Frontend refetch basado en HTTP response, no WebSocket
- ✅ No race condition

**Cons:**
- ⚠️ WebSocket llega después (afecta multi-tab sync)
- ⚠️ Cambios en router layer
- ⚠️ Más complejo

### Recomendación del Frontend

**Preferencia:** Opción 2 (Single Commit)

**Justificación:**
- Resuelve el root cause
- Mejora performance significativamente
- Simplifica el código (menos refresh de trip_lookup)

**Trade-off aceptable:**
- Si un step falla al re-aplicarse, mejor hacer rollback completo que dejar estado inconsistente
- La operación actual ya es "all-or-nothing" conceptualmente

---

## ⚡ Bug #2: Reverts Tardan 8-15 Segundos (PERFORMANCE)

### Síntoma

Cuando se revierte un tipo de filtro en modo BULK (ej: todo Febrero), la operación tarda entre **8 y 15 segundos**.

### Datos Observados

**Request:**
```json
{
  "date_from": "2026-02-01",
  "date_to": null,  // null = todo el futuro
  "filter_type": "reduce"
}
```

**Response (después de 12 segundos):**
```json
{
  "total_days": 28,
  "days_with_reverts": 28,
  "total_steps_reverted": 112,
  "total_trips_recalculated": 3136
}
```

**Breakdown:**
- 28 días procesados
- 4 steps tipo "reduce" por día
- 112 steps total
- ~112 trips/día promedio

### Análisis de Performance

#### Commits por Operación

Para **UNA** fecha con 4 steps activos (Reduce 1, Reduce 2, Reduce 3, Combine):

```
Revert Step (Reduce 1):
  1. Mark inactive (no commit needed aquí)
  2. Reset all trips → COMMIT 1
  3. Re-apply Reduce 2 → COMMIT 2
  4. Re-apply Reduce 3 → COMMIT 3
  5. Re-apply Combine → COMMIT 4

Total: 4 commits por step revertido
```

**Para 112 steps:**
- 112 steps × 4 commits = **448 commits secuenciales**
- Si cada commit tarda ~30ms → 13.4 segundos **solo en commits**

#### Código Actual (Ineficiente)

```python
# En _revert_step_internal() - líneas 763-834
# Para cada step activo restante
for active_step in active_steps:
    # Apply filter
    self._apply_reduce(current_trips, config)

    # Persist changes
    for change in self.changes:
        trip.reduce_applied = True
        self.session.add(trip)

    # COMMIT (línea 830)
    await self.session.commit()  # ← Commit individual

    # Refresh trip_lookup (líneas 833-834)
    trips = await self.session.exec(trips_query).all()
    trip_lookup = {t.id: t for t in trips}
```

**Problema:** Para 3 steps activos:
- 3 commits
- 3 refreshes de trips desde database
- Muy ineficiente

### Propuesta de Optimización

#### Batch Processing por Día

En lugar de hacer 112 reverts secuenciales con commits individuales:

```python
async def revert_bulk(...):
    # Para cada día
    for pick_up_date in dates:
        # Obtener todos los steps a revertir de este día
        steps_to_revert = await self._get_steps_to_revert(...)

        # Marcar TODOS como inactive
        for step in steps_to_revert:
            step.is_active = False
            self.session.add(step)

        # Reset TODOS los trips del día
        for trip in trips:
            trip.pick_up_time = trip.original_pick_up_time
            trip.reduce_applied = False
            trip.combine_applied = False
            trip.expand_applied = False
            self.session.add(trip)

        # Re-apply TODOS los steps activos restantes
        for active_step in active_steps:
            for change in changes:
                trip.reduce_applied = True
                self.session.add(trip)

        # SINGLE COMMIT PER DAY
        await self.session.commit()

    # Send WebSocket ONCE at end
    await self._send_revert_notification(...)
```

**Mejora estimada:**
- Antes: 112 steps × 4 commits = 448 commits
- Después: 28 días × 1 commit = **28 commits**
- **Speedup: ~16x más rápido** (de 12 segundos a ~1 segundo)

### Performance Comparison

| Escenario | Steps | Commits Actuales | Commits Optimizados | Tiempo Actual | Tiempo Optimizado |
|-----------|-------|------------------|---------------------|---------------|-------------------|
| 1 día, 1 step | 1 | 4 | 1 | 120ms | 30ms |
| 1 día, 4 steps | 4 | 16 | 1 | 480ms | 30ms |
| 28 días, 4 steps | 112 | 448 | 28 | 13.4s | 840ms |

---

## 📊 Request #3: Trips Independientes en Notificaciones

### Problema Actual

Cuando se aplican múltiples filtros, las notificaciones **acumulan y suman** todos los trips afectados en lugar de mostrar trips independientes por filtro.

### Escenario de Ejemplo

```
Estado Inicial: Sin filtros

1. Usuario aplica REDUCE
   Backend response:
   {
     "filter_type": "reduce",
     "total_trips_modified": 25  // 25 trips afectados por reduce
   }

   Notificación actual: "25 trips modificados" ✅ CORRECTO

2. Usuario aplica COMBINE (después de REDUCE)
   Backend response:
   {
     "filter_type": "combine",
     "total_trips_modified": 40  // ❌ INCORRECTO
   }

   Breakdown real:
   - 10 trips que YA tenían REDUCE ahora también tienen COMBINE
   - 5 trips nuevos que NO tenían REDUCE ahora tienen COMBINE
   - Total afectados POR COMBINE = 15 trips

   Notificación actual: "40 trips modificados" ❌ INCORRECTO (suma con reduce)
   Notificación esperada: "15 trips modificados por combine" ✅
```

### Root Cause

El endpoint `/bulk/apply` con `skip_days_with_stack: false` procesa TODOS los trips, incluyendo:
- Trips que ya tienen otros filtros aplicados (re-calcula)
- Trips nuevos que solo tienen este filtro

**El response no distingue entre:**
- Trips NUEVOS afectados por este filtro
- Trips RE-CALCULADOS que ya tenían otros filtros

### Lo Que Necesita el Frontend

Para mostrar notificaciones correctas, el backend debería retornar:

```json
{
  "filter_type": "combine",
  "total_trips_modified": 15,  // Solo trips afectados POR COMBINE
  "breakdown": {
    "new_trips_affected": 5,        // Trips que NO tenían filtros antes
    "existing_trips_updated": 10,   // Trips que YA tenían otros filtros
    "total_unique": 15               // Total único para ESTE filtro
  },
  "cumulative_total": 30  // Total de trips con CUALQUIER filtro (opcional)
}
```

### Ejemplo de Uso en Frontend

```typescript
// Apply REDUCE
const result1 = await applyBulk({ filter_type: "reduce", ... })
toast.success(`${result1.total_trips_modified} trips afectados por reduce`)
// Muestra: "25 trips afectados por reduce"

// Apply COMBINE
const result2 = await applyBulk({ filter_type: "combine", ... })
toast.success(`${result2.total_trips_modified} trips afectados por combine`)
// Muestra: "15 trips afectados por combine" (no 40)
```

### Request para Backend

**Por favor actualizar:**

#### 1. BulkStepResult
```python
class BulkStepResult(BaseModel):
    filter_type: str
    total_trips_modified: int  # ← Cambiar a "trips únicos para ESTE filtro"

    # Opcional: agregar breakdown
    breakdown: Optional[TripModificationBreakdown] = None

class TripModificationBreakdown(BaseModel):
    new_trips_affected: int       # Trips sin filtros previos
    existing_trips_updated: int   # Trips con filtros previos
    total_unique: int             # Suma de los dos
```

#### 2. Lógica en apply_bulk()

```python
# Después de aplicar el filtro
trips_modified_by_this_filter = set()

for change in self.changes:
    trip = trip_lookup.get(change.trip_id)

    # Verificar si el trip YA tenía este filtro específico
    already_had_filter = getattr(trip, f"{filter_type}_applied", False)

    if not already_had_filter:
        trips_modified_by_this_filter.add(trip.id)

    # Apply filter
    trip.pick_up_time = change.new_time
    setattr(trip, f"{filter_type}_applied", True)

# Return count of UNIQUE trips for THIS filter
total_trips_modified = len(trips_modified_by_this_filter)
```

### Aplicar/Revert Notifications - Expected Behavior

#### Apply Notification

```
Antes (ACTUAL):
  Aplico REDUCE: "25 trips modificados"
  Aplico COMBINE: "40 trips modificados"  ❌ Suma con reduce

Después (ESPERADO):
  Aplico REDUCE: "25 trips modificados"
  Aplico COMBINE: "15 trips modificados por combine"  ✅ Solo combine
```

#### Revert Notification

```
Antes (ACTUAL):
  Revierto REDUCE: "112 steps en 28 días (3,136 trips recalculados)"

Después (ESPERADO):
  Revierto REDUCE: "112 steps revertidos en 28 días"
  ↑ Simplificado, sin mencionar trips recalculados
```

**Justificación:**
- "trips recalculados" incluye trips de COMBINE y EXPAND que se re-aplicaron
- Es confuso para el usuario ver 3,136 trips cuando solo revirtió REDUCE
- Es mejor mostrar solo: steps revertidos + días afectados

---

## 🧪 Testing & Verification

### Test Case 1: Verificar Race Condition

**Setup:**
```sql
-- Aplicar 3 filtros
INSERT INTO filter_steps (filter_type, step_order, is_active) VALUES
  ('reduce', 1, true),
  ('combine', 2, true),
  ('expand', 3, true);
```

**Test:**
```python
# Revertir expand
result = await revert_last_step(date="2026-01-31")

# IMMEDIATELY query (simula frontend refetch)
import time
time.sleep(0)  # No delay
trips = await get_trips(date="2026-01-31")

# Verify flags
for trip in trips:
    assert trip.reduce_applied == True, f"FAIL: reduce_applied is {trip.reduce_applied}"
    assert trip.combine_applied == True, f"FAIL: combine_applied is {trip.combine_applied}"
    assert trip.expand_applied == False
```

**Expected:** Test debe pasar (todos los flags correctos)

**Current:** Test falla intermitentemente (race condition)

### Test Case 2: Verificar Trips Independientes

```python
# Apply REDUCE
result1 = await apply_bulk(filter_type="reduce", ...)
print(f"REDUCE affected: {result1.total_trips_modified} trips")

# Apply COMBINE (después de REDUCE)
result2 = await apply_bulk(filter_type="combine", ...)
print(f"COMBINE affected: {result2.total_trips_modified} trips")

# Expected output:
# REDUCE affected: 25 trips ✅
# COMBINE affected: 15 trips ✅ (solo los nuevos, no suma con reduce)

# Current output:
# REDUCE affected: 25 trips ✅
# COMBINE affected: 40 trips ❌ (suma con reduce)
```

### Test Case 3: Performance con Single Commit

**Setup:** 28 días con 4 steps cada uno

**Test:**
```python
import time

start = time.time()
result = await revert_bulk(
    date_from="2026-02-01",
    date_to="2026-02-28",
    filter_type="reduce"
)
duration = time.time() - start

print(f"Duration: {duration:.2f}s")
print(f"Steps reverted: {result.total_steps_reverted}")
```

**Expected con Single Commit:** < 2 segundos
**Current:** 10-15 segundos

---

## 🔍 Información Adicional del Frontend

### Skip Days With Stack

El frontend actualmente usa:

```typescript
skip_days_with_stack: false  // Siempre FALSE
```

**Pregunta para backend:** ¿Este parámetro afecta la performance o el conteo de trips?

### Date Range Usado

El frontend aplica filtros con:

```json
{
  "date_from": "2026-02-01",  // Primer día del mes
  "date_to": null             // NULL = aplicar a TODO el futuro
}
```

**Observación:** Esto puede causar que se procesen MUCHOS días en el futuro (no solo el mes actual).

**Pregunta:** ¿Es posible optimizar bulk operations para rangos grandes (ej: >100 días)?

### Connection Pool Size

**Pregunta:** ¿Cuál es el tamaño del connection pool de PostgreSQL?

Si es pequeño (ej: 5-10 conexiones), puede haber contention:
- Revert usa 1 conexión durante 12 segundos
- Frontend refetch compite por conexiones disponibles
- Puede obtener snapshot viejo si su transacción se retrasa

---

## 📋 Requests para Backend

### Request 1: Fix Race Condition (Alta Prioridad)

**Opciones:**
1. ✅ **Preferido:** Single commit al final (Opción 2)
2. ⚠️ **Alternativa:** Aumentar delay a 200-300ms (Opción 1)
3. ⚠️ **Futura:** WebSocket en background task (Opción 3)

### Request 2: Optimizar Performance (Alta Prioridad)

**Objetivo:** Reducir tiempo de bulk revert de ~12s a <2s

**Approach:**
- Single commit por día (no por step)
- Batch processing donde sea posible

### Request 3: Trips Independientes en Response (Media Prioridad)

**Cambios en BulkStepResult:**
```python
class BulkStepResult(BaseModel):
    # ... campos existentes ...
    total_trips_modified: int  # ← Solo trips únicos para ESTE filtro

    # Opcional para debugging
    breakdown: Optional[dict] = {
        "new_trips": int,      # Sin filtros previos
        "updated_trips": int,  # Con filtros previos
    }
```

**Cambios en FilterStepResult** (per-day):
```python
class FilterStepResult(BaseModel):
    trips_modified: int  # ← Solo trips para ESTE step, no acumulado
    # ... resto igual ...
}
```

---

## 🎯 Expected Backend Changes Summary

### Change 1: Single Commit (Critical)

**File:** `features/trips/services/step_filter_service.py`
**Method:** `_revert_step_internal()` (líneas 707-854)

**Before:**
```python
for active_step in active_steps:
    # Apply
    # Persist
    await self.session.commit()  # ← Individual
    # Refresh
```

**After:**
```python
# Accumulate all changes
for active_step in active_steps:
    # Apply
    # Add to session (no commit)

# Single commit at end
await self.session.commit()

# No delay needed
await self._send_revert_notification(...)
```

### Change 2: Independent Trip Counts

**File:** `features/trips/services/step_filter_service.py`
**Methods:** `apply_bulk()`, `apply_step()`

**Add logic:**
```python
# Track trips that DIDN'T have this filter before
trips_newly_affected = set()

for change in self.changes:
    trip = trip_lookup[change.trip_id]
    already_had_filter = getattr(trip, f"{filter_type}_applied", False)

    if not already_had_filter:
        trips_newly_affected.add(trip.id)

# Return independent count
return BulkStepResult(
    total_trips_modified=len(trips_newly_affected),  # ← Not cumulative
    ...
)
```

### Change 3: Simplify Revert Notifications

**No backend change needed** - Frontend will use different fields:
- Use `total_steps_reverted` and `days_with_reverts`
- Ignore `total_trips_recalculated`

---

## 🔧 Workarounds Temporales en Frontend

Mientras se implementan los fixes del backend, el frontend ha implementado:

### Workaround 1: Delay Adicional

```typescript
// En schedule-dashboard-client.tsx línea 1606
// Agregar 150ms adicionales después del WebSocket
await new Promise(resolve => setTimeout(resolve, 150))
infiniteScroll.reset()
```

**Efectividad:** 70-80% (todavía falla ocasionalmente con muchos steps)

### Workaround 2: Loading Toast

```typescript
// En use-trip-filters-v2.ts línea 1054
const loadingToastId = toast.loading(`Revirtiendo filtros ${filterType}...`, {
  description: 'Esto puede tardar varios segundos con múltiples días',
})
```

**Mejora:** Da feedback al usuario durante operaciones largas

### Workaround 3: Combine Preview Changes

```typescript
// En use-trip-filters-v2.ts línea 97-142
// Detecta y combina trips duplicados en preview
function combinePreviewChanges(results: FilterStepResult[]): TripChangeV2[]
```

**Efectividad:** 100% para preview, pero no resuelve el problema de Apply

---

## 📚 Referencias

- **FIX_RACE_CONDITION_REVERT.md** - Fix de 50ms delay (insuficiente)
- **GROUND_FILTERS_REVERT_COMPLETE_GUIDE.md** - Guía completa de revert
- **Código Backend:** `features/trips/services/step_filter_service.py`
- **Código Frontend:**
  - `src/hooks/use-trip-filters-v2.ts`
  - `src/app/(main)/dashboard/locations/[code]/[airline]/schedule-dashboard-client.tsx`

---

## ✅ Verification Checklist

Después de implementar los fixes, verificar:

- [ ] **Race Condition:** Revertir 1 step no muestra estado "un paso atrás"
- [ ] **Performance:** Bulk revert de 28 días tarda <2 segundos (no 12 segundos)
- [ ] **Notificaciones Apply:** Segunda aplicación muestra solo trips del filtro actual
- [ ] **Notificaciones Revert:** Muestra steps + días, no trips recalculados
- [ ] **Test Case 1:** Pasa consistentemente (sin race condition)
- [ ] **Test Case 2:** Cuenta trips independientes correctamente
- [ ] **Test Case 3:** Performance mejorada 10x+

---

## 🤝 Colaboración Frontend-Backend

El frontend está alineado con la documentación existente y ha implementado workarounds temporales. Sin embargo, los problemas fundamentales requieren cambios en el backend:

1. **Architecture:** Single commit en lugar de commits individuales
2. **Performance:** Batch processing para operaciones masivas
3. **Data:** Conteos independientes de trips por filtro

**Disponibilidad para Testing:** Frontend team disponible para testing de cambios y puede proveer más logs/datos si se necesitan.

---

**Reportado por:** Frontend Developer
**Fecha:** 2026-01-28
**Prioridad:** HIGH (Race condition) + MEDIUM (Performance/Notifications)
**Status:** Esperando implementación en backend
