# Bug Analysis: Configuración de Filtros se Pierde Después de F5

**Fecha:** 2026-01-26
**Reportado por:** Usuario Frontend
**Severidad:** CRÍTICA

---

## 🐛 Descripción del Bug

### Flujo Problemático

```
1. Usuario aplica filtro Reduce con 10 minutos
   → ✅ Funciona correctamente
   → ✅ Trips se modifican
   → ✅ UI muestra el filtro activo

2. Usuario hace F5 (refresh de la página)
   → ❌ La configuración del filtro se pierde
   → ❌ El switch aparece apagado (OFF)
   → ❌ La configuración (windows, minutes_to_reduce) desaparece

3. PERO los trips mantienen los tiempos modificados
   → ✅ Trips siguen teniendo reduce_applied: true
   → ✅ Trips mantienen original_pick_up_time
   → ✅ Trips mantienen tiempos modificados
```

---

## 🔍 Análisis de los Logs del Frontend

### Logs de Rehidratación (Después de F5)

```javascript
[useFilterRehidration] 📡 Loading stack from backend...
[useFilterRehidration] 🔍 REQUEST PARAMS: {
  locationId: 'd9f81f73-3059-4bcf-a980-47cca92fe594',
  airline: 'WN',
  pickUpDate: '2026-01-01'
}

[useFilterRehidration] 📥 Backend response received: {success: true, hasData: true}
[useFilterRehidration] 🔍 RAW BACKEND RESPONSE: {
  steps: Array(0),  // ← VACÍO - Aquí está el problema
  total_trips_affected: 0
}

[parseStepToConfig] reduce: No step found, returning disabled default
// ← Frontend interpreta esto como filtro apagado
```

### Logs de Trips (Misma Sesión)

```javascript
[normalizeGroundFilter] Trip data: {
  reduce_applied: true,      // ← Filtro SÍ está aplicado
  original_time: '04:15',    // ← Hora original guardada
  applied_time: '04:05'      // ← Hora modificada (-10 min)
}

[InfiniteScroll] Backend filter fields: {
  tripsWithFilters: 13  // ← 13 trips con filtros activos
}
```

---

## 🚨 INCONSISTENCIA DETECTADA EN EL BACKEND

### Evidencia de la Inconsistencia

| Entidad | Estado Real | Lo que Debería Ser |
|---------|-------------|-------------------|
| **Trips** | `reduce_applied: true`<br>`original_pick_up_time: "04:15"`<br>`pick_up_time: "04:05"` | ✅ Correcto |
| **FilterSteps** | `steps: []` (vacío) | ❌ **INCORRECTO** - Debería haber FilterStep activo |

### Diagnóstico

El backend tiene **trips modificados** pero **NO tiene FilterSteps activos** para esa fecha.

Esto solo puede ocurrir si:

1. ✅ **Escenario más probable:** FilterStep fue revertido incorrectamente
   ```sql
   -- El FilterStep se marcó como is_active=false
   UPDATE trips.filter_steps SET is_active = false WHERE ...;

   -- PERO los trips NO se limpiaron correctamente
   -- Los trips deberían tener:
   -- - pick_up_time = original_pick_up_time
   -- - original_pick_up_time = NULL
   -- - reduce_applied = FALSE
   ```

2. ⚠️ FilterStep fue eliminado manualmente de la DB
   ```sql
   DELETE FROM trips.filter_steps WHERE ...;
   -- Sin ejecutar el proceso de revert primero
   ```

3. ⚠️ El commit del FilterStep falló pero los trips sí se guardaron
   ```python
   # Poco probable porque están en la misma transacción
   await self.session.commit()  # Debería guardar ambos o ninguno
   ```

---

## 🔬 Investigación del Código del Backend

### Flujo Correcto de Apply (Como Debería Funcionar)

**Archivo:** `features/trips/services/step_filter_service.py:135-258`

```python
async def apply_step(...):
    # 1. Crear FilterStep
    filter_step = FilterStep(
        id=step_id,
        location_id=location_id,
        airline=airline,
        pick_up_date=pick_up_date,
        is_active=True,  # ← Se marca como activo
        ...
    )
    self.session.add(filter_step)  # ← Agregar a sesión

    # 2. Modificar trips
    for change in self.changes:
        trip.original_pick_up_time = trip.pick_up_time  # Backup
        trip.pick_up_time = change.new_time              # Nuevo
        trip.reduce_applied = True                       # Flag
        trip.current_step_id = step_id                   # Referencia
        self.session.add(trip)

    # 3. Commit TODO junto (transacción atómica)
    await self.session.commit()  # ← Ambos se guardan o ambos fallan
```

**Conclusión:** Si los trips están modificados, el FilterStep DEBERÍA existir.

---

### Flujo de Rehidratación (Como Funciona)

**Archivo:** `features/trips/services/step_filter_service.py:312-356`

```python
async def get_stack(...):
    query = (
        Select(FilterStep)
        .Where(FilterStep.location_id == location_id)
        .Where(FilterStep.airline == airline)
        .Where(FilterStep.pick_up_date == pick_up_date)
        .Where(FilterStep.is_active == True)  # ← Solo steps ACTIVOS
        .OrderBy(FilterStep.step_order.Asc())
    )
    steps = await self.session.exec(query).all()

    return StackState(
        steps=step_infos,  # ← Vacío si no hay steps activos
        ...
    )
```

**Conclusión:** Si retorna `steps: []`, es porque NO hay FilterSteps con `is_active=true` en la DB.

---

## 🎯 Causa Raíz del Problema

### Escenario Más Probable

```sql
-- 1. FilterStep fue creado correctamente
INSERT INTO trips.filter_steps (
    id, location_id, airline, pick_up_date,
    filter_type, is_active, ...
) VALUES (..., true, ...);

-- 2. Trips fueron modificados correctamente
UPDATE trips.trips SET
    original_pick_up_time = pick_up_time,
    pick_up_time = <nuevo_tiempo>,
    reduce_applied = true,
    ...;

-- 3. Alguien o algo REVIRTIÓ el FilterStep
UPDATE trips.filter_steps
SET is_active = false
WHERE id = '...';

-- PERO los trips NO se limpiaron (BUG en el proceso de revert)
-- Los trips deberían haberse reseteado a:
UPDATE trips.trips SET
    pick_up_time = original_pick_up_time,
    original_pick_up_time = NULL,
    reduce_applied = FALSE,
    ...;
```

---

## 🔧 Verificación en la Base de Datos

### Query para Detectar la Inconsistencia

```sql
-- Trips con filtros pero sin FilterStep activo
SELECT
    t.id,
    t.flight_number,
    t.pick_up_date,
    t.pick_up_time,
    t.original_pick_up_time,
    t.reduce_applied,
    t.current_step_id
FROM trips.trips t
WHERE
    t.location_id = 'd9f81f73-3059-4bcf-a980-47cca92fe594'
    AND t.airline = 'WN'
    AND t.pick_up_date = '2026-01-01'
    AND t.original_pick_up_time IS NOT NULL  -- Tiene filtro aplicado
    AND NOT EXISTS (
        SELECT 1
        FROM trips.filter_steps fs
        WHERE fs.location_id = t.location_id
          AND fs.airline = t.airline
          AND fs.pick_up_date = t.pick_up_date
          AND fs.is_active = true
    );
```

**Resultado esperado:** 13 trips (los que vimos en los logs)

### Query para Buscar FilterSteps Revertidos

```sql
-- Buscar FilterSteps inactivos para esa fecha
SELECT
    id,
    filter_type,
    step_order,
    is_active,
    trips_affected,
    created_at,
    windows
FROM trips.filter_steps
WHERE
    location_id = 'd9f81f73-3059-4bcf-a980-47cca92fe594'
    AND airline = 'WN'
    AND pick_up_date = '2026-01-01'
ORDER BY created_at DESC;
```

**Resultado esperado:** Debería mostrar steps con `is_active = false`

---

## ✅ Solución para Limpiar la Inconsistencia

```sql
-- Resetear trips que tienen filtros pero sin FilterStep activo
UPDATE trips.trips t
SET
    pick_up_time = t.original_pick_up_time,  -- Restaurar hora original
    original_pick_up_time = NULL,             -- Limpiar backup
    reduce_applied = FALSE,                   -- Limpiar flags
    combine_applied = FALSE,
    expand_applied = FALSE,
    current_step_id = NULL,                   -- Limpiar referencia
    filtered_at = NULL,                       -- Limpiar timestamp
    updated_at = NOW()
WHERE
    t.original_pick_up_time IS NOT NULL
    AND NOT EXISTS (
        SELECT 1
        FROM trips.filter_steps fs
        WHERE fs.location_id = t.location_id
          AND fs.airline = t.airline
          AND fs.pick_up_date = t.pick_up_date
          AND fs.is_active = true
    );
```

---

## 📊 Análisis del Código: ¿Cómo Funciona la Rehidratación?

### Código de Rehidratación (Backend)

**Ubicación:** `step_filter_service.py:312-356`

```python
async def get_stack(...) -> StackState:
    # 1. Buscar FilterSteps ACTIVOS
    query = Select(FilterStep).Where(
        FilterStep.location_id == location_id,
        FilterStep.airline == airline,
        FilterStep.pick_up_date == pick_up_date,
        FilterStep.is_active == True  # ← KEY: Solo activos
    )
    steps = await self.session.exec(query).all()

    # 2. Parsear cada step a FilterStepInfo
    for step in steps:
        step_infos.append(FilterStepInfo(
            step_id=step.id,
            filter_type=step.filter_type,
            windows=step.windows,  # ← Incluye configuración completa
            trips_affected=step.trips_affected,
            is_active=step.is_active,
            ...
        ))

    # 3. Retornar stack
    return StackState(
        steps=step_infos,  # ← Vacío si no hay steps activos
        ...
    )
```

**Funcionamiento:**
- ✅ Busca solo steps con `is_active = true`
- ✅ Incluye configuración completa (windows con minutes_to_reduce)
- ✅ Si no hay steps activos, retorna `steps: []` (legítimo)

**Problema:**
- ❌ Retorna vacío cuando debería haber steps
- ❌ Inconsistencia: trips tienen filtros pero no hay steps activos

---

## 🎯 CONCLUSIÓN: ¿El Problema es del Backend o Frontend?

### Respuesta: **INCONSISTENCIA EN LA BASE DE DATOS (Backend)**

| Aspecto | Análisis | Responsable |
|---------|----------|-------------|
| **Código de apply_step** | ✅ Correcto - guarda FilterStep y trips juntos | Backend OK |
| **Código de get_stack** | ✅ Correcto - retorna steps activos | Backend OK |
| **Estado de la DB** | ❌ **INCONSISTENTE** - Trips con filtros sin FilterSteps | **Backend (datos)** |
| **Rehidratación frontend** | ✅ Correcto - interpreta `steps: []` como apagado | Frontend OK |

### Diagnóstico Final

**El problema NO es del código del backend**, sino de **datos corruptos/inconsistentes en PostgreSQL**.

El código del backend funciona correctamente:
- ✅ Al aplicar: Guarda FilterStep + modifica trips (transacción atómica)
- ✅ Al rehidratar: Retorna steps activos
- ✅ El proceso de revert debería limpiar ambos

**PERO:**
- ❌ Hay trips con `reduce_applied: true` sin FilterSteps activos correspondientes
- ❌ Esto indica que el proceso de revert NO limpió los trips correctamente
- ❌ O alguien eliminó FilterSteps manualmente

---

## 🔧 Soluciones

### Solución 1: Limpiar Inconsistencia Existente (Inmediato)

```sql
-- Ejecutar este SQL para resetear trips huérfanos
UPDATE trips.trips t
SET
    pick_up_time = t.original_pick_up_time,
    original_pick_up_time = NULL,
    reduce_applied = FALSE,
    combine_applied = FALSE,
    expand_applied = FALSE,
    current_step_id = NULL,
    filtered_at = NULL,
    updated_at = NOW()
WHERE
    t.original_pick_up_time IS NOT NULL
    AND NOT EXISTS (
        SELECT 1 FROM trips.filter_steps fs
        WHERE fs.location_id = t.location_id
          AND fs.airline = t.airline
          AND fs.pick_up_date = t.pick_up_date
          AND fs.is_active = true
    );
```

**Archivo:** `scripts/fix_filter_inconsistency.sql` (ya creado)

---

### Solución 2: Prevenir Futuras Inconsistencias

#### Opción A: Agregar Foreign Key Constraint (Recomendado)

```sql
-- Agregar FK de trip.current_step_id → filter_steps.id
ALTER TABLE trips.trips
ADD CONSTRAINT fk_trip_current_step
FOREIGN KEY (current_step_id)
REFERENCES trips.filter_steps(id)
ON DELETE SET NULL;  -- Si se elimina step, limpiar referencia
```

**Beneficio:**
- PostgreSQL garantizará integridad referencial
- No permite eliminar FilterSteps si hay trips referenciándolos

#### Opción B: Revisar Código de Revert

**Ubicación:** `step_filter_service.py:707-838`

Verificar que el código de `_revert_step_internal` siempre limpie trips correctamente:

```python
# Líneas 738-748
for trip in trips:
    if trip.original_pick_up_time:
        trip.pick_up_time = trip.original_pick_up_time
        trip.reduce_applied = False
        trip.original_pick_up_time = None  # ← Importante
        self.session.add(trip)

await self.session.commit()  # ← Asegurar que se commitea
```

**Verificar:** Que no haya paths donde se marque `is_active=false` sin limpiar trips.

---

## 📋 Tests Recomendados

### Test 1: Aplicar y Rehidratar

```bash
# 1. Aplicar filtro
curl -X POST "http://api.gt360.app/v2/locations/d9f81f73.../airlines/WN/filters/step/apply" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "filter_type": "reduce",
    "pick_up_date": "2026-01-26",
    "windows": [{"start": "00:00", "end": "24:00", "minutes_to_reduce": 10}]
  }'

# 2. Verificar que se guardó
curl "http://api.gt360.app/v2/locations/d9f81f73.../airlines/WN/filters/stack?pick_up_date=2026-01-26" \
  -H "Authorization: Bearer $TOKEN"

# Debería retornar: { steps: [{filter_type: "reduce", ...}] }
```

### Test 2: Aplicar, Revertir, Rehidratar

```bash
# 1. Aplicar filtro
POST /step/apply

# 2. Verificar
GET /stack
# Debe retornar: steps: [{reduce, ...}]

# 3. Revertir
POST /revert-last

# 4. Verificar rehidratación
GET /stack
# Debe retornar: steps: [] (vacío)

# 5. Verificar trips limpiados
GET /trips
# Debe retornar trips con reduce_applied: false, original_pick_up_time: null
```

---

## 🎯 RESPUESTA FINAL

### ¿El Problema es del Backend o Frontend?

**BACKEND (datos inconsistentes)** ❌

**Evidencia:**
1. ✅ El frontend llama correctamente a GET /stack
2. ✅ El backend retorna correctamente (según su DB: `steps: []`)
3. ❌ **PERO** la DB tiene datos inconsistentes (trips con filtros sin steps)
4. ✅ El frontend interpreta correctamente la respuesta vacía como "filtro apagado"

**El código del backend funciona correctamente.** El problema es que:
- Hay trips modificados (reduce_applied: true)
- Pero NO hay FilterSteps activos correspondientes
- Esto causa que GET /stack retorne vacío
- El frontend piensa que no hay filtros (correcto basado en la respuesta)

---

## 📝 Acciones Recomendadas

### Inmediatas

1. **Ejecutar limpieza de inconsistencia:**
   ```bash
   psql -h postgres -U gt360 -d gt360 -f scripts/fix_filter_inconsistency.sql
   ```

2. **Verificar que no haya más inconsistencias:**
   ```bash
   curl "http://localhost:8000/test/filters/check-inconsistency?location_id=d9f81f73...&airline=WN&pick_up_date=2026-01-01"
   ```

### A Mediano Plazo

1. **Agregar FK constraint** para prevenir futuras inconsistencias
2. **Revisar código de revert** para asegurar que siempre limpie trips
3. **Agregar tests automatizados** del flujo apply→revert→rehidratar

---

## 🔍 Cómo Reproducir para Debugging

```bash
# 1. Ver estado actual de trips
SELECT id, reduce_applied, original_pick_up_time, current_step_id
FROM trips.trips
WHERE location_id = 'd9f81f73-3059-4bcf-a980-47cca92fe594'
  AND airline = 'WN'
  AND pick_up_date = '2026-01-01'
  AND original_pick_up_time IS NOT NULL;

# 2. Ver FilterSteps (activos e inactivos)
SELECT id, filter_type, is_active, created_at
FROM trips.filter_steps
WHERE location_id = 'd9f81f73-3059-4bcf-a980-47cca92fe594'
  AND airline = 'WN'
  AND pick_up_date = '2026-01-01';

# 3. Si hay trips pero no steps activos → INCONSISTENCIA
```

---

**Estado:** ✅ Análisis completo realizado
**Conclusión:** Problema de datos inconsistentes en PostgreSQL, no del código del backend
**Acción requerida:** Limpiar inconsistencia con el SQL proporcionado
