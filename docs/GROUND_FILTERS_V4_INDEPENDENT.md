# Ground Filters V4: Independent Filter Fields

**Fecha:** 2026-01-20
**Status:** ✅ DEPLOYED
**Cambio Principal:** Filtros independientes sin auto-revert

---

## Resumen del Cambio

### Problema en V3

El auto-revert causaba errores 500 cuando se aplicaban filtros secuencialmente debido a múltiples commits en la misma transacción:

```
1. Usuario aplica REDUCE
2. Usuario aplica COMBINE
   → Auto-revert hace commit()
   → Apply hace commit()
   → Error 500: Múltiples commits / transacción inconsistente
```

### Solución en V4

**Cambio de modelo de datos:**
- **ANTES (V3):** Un solo campo `filter_applied` (solo un filtro activo a la vez)
- **DESPUÉS (V4):** Tres campos booleanos independientes

```python
# V3 (antes):
filter_applied: str  # 'reduce', 'combine', o 'expand'

# V4 (ahora):
reduce_applied: bool = False
combine_applied: bool = False
expand_applied: bool = False
```

---

## Cambios Implementados

### 1. Migración de Base de Datos

**Archivo:** `migrations/add_independent_filter_fields.sql`

```sql
-- Agregar 3 columnas booleanas
ALTER TABLE trips.trips
ADD COLUMN reduce_applied BOOLEAN DEFAULT FALSE,
ADD COLUMN combine_applied BOOLEAN DEFAULT FALSE,
ADD COLUMN expand_applied BOOLEAN DEFAULT FALSE;

-- Migrar datos existentes
UPDATE trips.trips SET reduce_applied = TRUE WHERE filter_applied = 'reduce';
UPDATE trips.trips SET combine_applied = TRUE WHERE filter_applied = 'combine';
UPDATE trips.trips SET expand_applied = TRUE WHERE filter_applied = 'expand';

-- Crear índices
CREATE INDEX idx_trips_reduce_applied ON trips.trips(reduce_applied) WHERE reduce_applied = TRUE;
CREATE INDEX idx_trips_combine_applied ON trips.trips(combine_applied) WHERE combine_applied = TRUE;
CREATE INDEX idx_trips_expand_applied ON trips.trips(expand_applied) WHERE expand_applied = TRUE;
```

**Resultados:**
- ✅ 594 trips migrados con `reduce_applied = TRUE`
- ✅ 2 trips migrados con `combine_applied = TRUE`
- ✅ 80 trips migrados con `expand_applied = TRUE`

---

### 2. Schema de Trip Actualizado

**Archivo:** `shared/db/schemas/trips/trips.py`

```python
class Trip(PSQLModel):
    # ... campos existentes ...

    # DEPRECATED: Mantener para compatibilidad
    filter_applied: str = Column(max_len=20, default=None, nullable=True, index=True)

    # === V4: Independent filter tracking ===
    reduce_applied: bool = Column(default=False, nullable=False, index=True)
    combine_applied: bool = Column(default=False, nullable=False, index=True)
    expand_applied: bool = Column(default=False, nullable=False, index=True)
```

---

### 3. Servicio Actualizado

**Archivo:** `features/trips/services/trip_filter_service.py`

#### apply() - Marca filtros independientes

```python
# Determinar qué filtros están habilitados en este batch
filters_enabled = {
    'reduce': config.reduce and config.reduce.enabled,
    'combine': config.combine and config.combine.enabled,
    'expand': config.expand and config.expand.enabled
}

# Marcar campos booleanos según filtros habilitados
for change in self.changes:
    trip = trip_lookup.get(change.trip_id)
    if trip:
        # V4: Set independent filter flags
        if filters_enabled['reduce']:
            trip.reduce_applied = True
        if filters_enabled['combine']:
            trip.combine_applied = True
        if filters_enabled['expand']:
            trip.expand_applied = True

        # Mantener filter_applied para compatibilidad
        trip.filter_applied = change.filter_applied
```

#### revert() - Limpia filtros independientes

```python
for trip in trips:
    if trip.original_pick_up_time:
        trip.pick_up_time = trip.original_pick_up_time
        trip.original_pick_up_time = None
        trip.filter_applied = None

        # V4: Clear independent filter flags
        trip.reduce_applied = False
        trip.combine_applied = False
        trip.expand_applied = False
```

---

### 4. Endpoint Apply Simplificado

**Archivo:** `features/trips/routes/trips_router.py`

**ANTES (V3):**
```python
# Auto-revert check
existing_filtered_trips = await session.exec(...)
if existing_filtered_trips:
    service_revert = TripFilterService(session)
    revert_result = await service_revert.revert(...)
    # ... logging ...

# Apply filters
service = TripFilterService(session)
result = await service.apply(...)
```

**DESPUÉS (V4):**
```python
# V4: Independent filters - no auto-revert needed
service = TripFilterService(session)
result = await service.apply(location_uuid, airline, filters, time_format)
```

---

## Comportamiento Nuevo

### Aplicación Secuencial (El Problema Resuelto)

**Caso 1: Aplicar REDUCE, luego COMBINE**

```
Estado inicial:
- No hay filtros aplicados

Usuario aplica REDUCE:
→ Backend marca: reduce_applied = TRUE
→ pick_up_time modificado
→ ✅ Success 200

Usuario aplica COMBINE (sin revertir):
→ Backend marca: combine_applied = TRUE
→ pick_up_time modificado (opera sobre tiempo con reduce)
→ ✅ Success 200 (NO hay auto-revert, NO hay error 500)

Estado final:
- reduce_applied = TRUE
- combine_applied = TRUE
- pick_up_time refleja AMBOS filtros
```

**Caso 2: Aplicar REDUCE + COMBINE juntos**

```
Usuario aplica REDUCE + COMBINE en un solo request:
→ Backend marca: reduce_applied = TRUE, combine_applied = TRUE
→ pick_up_time modificado con ambos filtros
→ ✅ Success 200

Estado final:
- reduce_applied = TRUE
- combine_applied = TRUE
```

---

### Revert Independiente

**Caso 3: Revertir solo REDUCE**

```
Estado inicial:
- reduce_applied = TRUE
- combine_applied = TRUE

Usuario usa /revert-partial?filter_type=reduce:
→ Backend revierte TODO
→ Re-aplica solo COMBINE
→ Estado final:
  - reduce_applied = FALSE
  - combine_applied = TRUE
```

**Caso 4: Revert completo**

```
Usuario usa /revert:
→ Backend revierte TODO
→ Estado final:
  - reduce_applied = FALSE
  - combine_applied = FALSE
  - expand_applied = FALSE
  - pick_up_time = original_pick_up_time
```

---

## Ventajas de V4

| Aspecto | V3 (Auto-Revert) | V4 (Independent) |
|---------|------------------|------------------|
| **Filtros secuenciales** | ❌ Error 500 | ✅ Funciona |
| **Complejidad** | ❌ Auto-revert complicado | ✅ Simple y directo |
| **Transacciones** | ❌ Múltiples commits | ✅ Un solo commit |
| **Independencia** | ❌ Solo un filtro activo | ✅ Todos independientes |
| **Debugging** | ❌ Difícil rastrear estado | ✅ Claro (3 campos booleanos) |
| **Performance** | ⚠️ Auto-revert extra | ✅ Sin overhead |

---

## Backwards Compatibility

- ✅ `filter_applied` se mantiene para compatibilidad
- ✅ Frontend NO necesita cambios inmediatos
- ✅ Queries antiguas siguen funcionando
- ⚠️ `filter_applied` será deprecado en V5

---

## Testing

### Test 1: Aplicar REDUCE

```bash
POST /filters/apply
{
  "reduce": {"enabled": true, "minutes_to_reduce": 20},
  "combine": {"enabled": false},
  "expand": {"enabled": false}
}

# Esperado:
# ✅ 200 OK
# ✅ trips con reduce_applied = TRUE
# ✅ pick_up_time modificado
```

### Test 2: Aplicar COMBINE sin revertir REDUCE

```bash
POST /filters/apply
{
  "reduce": {"enabled": false},
  "combine": {"enabled": true, "min_gap": 10, "max_gap": 20},
  "expand": {"enabled": false}
}

# Esperado:
# ✅ 200 OK (NO 500)
# ✅ trips con reduce_applied = TRUE, combine_applied = TRUE
# ✅ pick_up_time refleja ambos filtros
```

### Test 3: Aplicar REDUCE + COMBINE juntos

```bash
POST /filters/apply
{
  "reduce": {"enabled": true, "minutes_to_reduce": 20},
  "combine": {"enabled": true, "min_gap": 10, "max_gap": 20},
  "expand": {"enabled": false}
}

# Esperado:
# ✅ 200 OK
# ✅ trips con reduce_applied = TRUE, combine_applied = TRUE
```

### Verificar en DB

```sql
-- Ver estado de filtros aplicados
SELECT
    id,
    pick_up_time,
    original_pick_up_time,
    reduce_applied,
    combine_applied,
    expand_applied,
    filter_applied  -- deprecated pero funcional
FROM trips.trips
WHERE location_id = '{uuid}' AND airline = 'WN'
AND (reduce_applied OR combine_applied OR expand_applied);
```

---

## Archivos Modificados

| Archivo | Cambio |
|---------|--------|
| `migrations/add_independent_filter_fields.sql` | ✅ Migración DB |
| `shared/db/schemas/trips/trips.py:120-138` | ✅ 3 campos booleanos |
| `features/trips/services/trip_filter_service.py:223-258` | ✅ Marca filtros independientes |
| `features/trips/services/trip_filter_service.py:345-348` | ✅ Limpia filtros en revert |
| `features/trips/routes/trips_router.py:1441-1448` | ✅ Removido auto-revert |

---

## Status Final

| Componente | Status |
|------------|--------|
| Migración DB | ✅ Ejecutada (594 + 2 + 80 trips) |
| Schema actualizado | ✅ Deployed |
| Servicio actualizado | ✅ Deployed |
| Endpoint actualizado | ✅ Deployed |
| Docker container | ✅ Reiniciado |
| Server status | ✅ Running (http://0.0.0.0:8000) |

---

## Actualización V5 (2026-01-20)

### Mejora en V5: enabled: false desactiva activamente

**Problema en V4:**
- `enabled: false` no hacía nada (solo no tocaba el filtro)
- Para desactivar un filtro individual, había que usar `/revert-partial`

**Solución en V5:**
```python
# V5: enabled: false marca FALSE explícitamente
if filters_state['reduce'] is True:
    trip.reduce_applied = True
elif filters_state['reduce'] is False:
    trip.reduce_applied = False  # ← Nuevo en V5
```

**Comportamiento V5:**

| Request | Comportamiento |
|---------|----------------|
| `{reduce: {enabled: true}}` | Aplica REDUCE y marca TRUE |
| `{reduce: {enabled: false}}` | NO aplica REDUCE y marca FALSE (desactiva) |
| `{combine: {enabled: true}}` (reduce omitido) | No toca REDUCE (mantiene estado) |

**Ejemplo V5:**
```json
// Estado inicial
reduce_applied: true
combine_applied: true

// Request: Desactivar REDUCE, mantener COMBINE
{
  "reduce": {"enabled": false},
  "combine": {"enabled": true, "min_gap_minutes": 10}
}

// Resultado
reduce_applied: false  ← Desactivado
combine_applied: true  ← Mantiene
```

**Archivo modificado:**
- `features/trips/services/trip_filter_service.py:223-297` - Lógica V5

**Documentación Frontend:**
- 📄 `docs/GROUND_FILTERS_FRONTEND_GUIDE_V5.md` - Guía completa para frontend
- 📄 `docs/RESPUESTA_FRONTEND_V5.md` - Respuesta a pregunta específica

---

## Próximos Pasos (Opcional)

1. **Frontend:** Actualizar UI para mostrar múltiples filtros activos
2. **Frontend:** Usar `enabled: false` en lugar de `/revert-partial` (V5)
3. **API:** Agregar endpoint GET `/filters/status` que muestre qué filtros están activos
4. **V6:** Deprecar completamente `filter_applied` (remover columna)

---

**Resumen V4:** El problema de error 500 está resuelto. Los filtros ahora son completamente independientes y pueden aplicarse secuencialmente sin errores.

**Resumen V5:** Ahora puedes desactivar filtros individuales con `enabled: false` sin usar `/revert-partial`.

**Última actualización:** 2026-01-20 (V5 deployed)
