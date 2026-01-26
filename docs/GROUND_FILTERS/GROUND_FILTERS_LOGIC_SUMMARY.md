# Ground Filters V2 - Resumen Completo de Lógica

## Arquitectura de Filtros

### Concepto de Stack (Pila)

Cada combinación `(location_id, airline, pick_up_date)` tiene su propio **stack de filtros**.

```
Stack del día 2026-01-25:
┌─────────────────────────────────────┐
│ Step 3: Expand    (step_order=3)    │ ← Último aplicado
├─────────────────────────────────────┤
│ Step 2: Combine   (step_order=2)    │
├─────────────────────────────────────┤
│ Step 1: Reduce    (step_order=1)    │ ← Primero aplicado
└─────────────────────────────────────┘
```

---

## Los 3 Tipos de Filtros

### 1. REDUCE

**Propósito:** Restar minutos fijos al pickup_time.

**Lógica:**
```
pickup_time = 08:30
minutes_to_reduce = 10
→ nuevo pickup_time = 08:20
```

**Trabaja sobre:** `trip.original_pick_up_time` (si existe) o `trip.pick_up_time`

**Importante:**
- Reduce SIEMPRE usa el tiempo **original** como base
- Esto evita "drift" (deriva) si se aplica múltiples veces

```python
# Línea 422 en step_filter_service.py
base_time = trip.original_pick_up_time or trip.pick_up_time
```

---

### 2. COMBINE

**Propósito:** Unir pares de trips al punto medio.

**Lógica:**
```
Trip A: 08:20  ┐
               ├→ gap = 10 min → midpoint = 08:25
Trip B: 08:30  ┘

Resultado: Ambos trips ahora tienen pickup_time = 08:25
```

**Condiciones para combinar:**
1. Gap entre trips está en rango `[min_gap, max_gap]`
2. `pickup_location` idéntico
3. `drop_off_location` idéntico
4. Ningún trip fue modificado por Combine/Expand en este step (Rule A)

**Trabaja sobre:** `_get_effective_time()` que busca:
1. Primero: ¿Hay un cambio pendiente en `self.changes`? → usa ese
2. Si no: `trip.original_pick_up_time` o `trip.pick_up_time`

```python
# Línea 951-959 en step_filter_service.py
def _get_effective_time(self, trip: Trip) -> time:
    # Check if we have a pending change
    for change in reversed(self.changes):
        if change.trip_id == trip.id:
            return change.new_time
    # Use original if exists, otherwise current
    return trip.original_pick_up_time or trip.pick_up_time
```

**IMPORTANTE:** Si Reduce ya se aplicó en el mismo día (antes de este step), Combine VE los tiempos reducidos porque ya están persistidos en `trip.pick_up_time`.

---

### 3. EXPAND

**Propósito:** Separar pares de trips demasiado juntos.

**Estrategia de 3 intentos:**
```
Gap actual = 3 min (muy junto)
min_gap = 5, max_gap = 15, max_shift = 10

Intento 1 (Both): A retrocede 10, B avanza 10 → Gap = 23
Intento 2 (Only A): A retrocede 10, B queda → Gap = 13 ✅
Intento 3 (Only B): A queda, B avanza 10 → Gap = 13 ✅
```

**Rule B (No-Collision):** Expand valida que el nuevo gap NO caiga en el rango de Combine activos.

**Trabaja sobre:** `_get_effective_time()` (igual que Combine)

---

## Interacción Entre Filtros

### Escenario: Reduce → Combine (mismo día)

```
Estado Inicial:
Trip A: pick_up_time = 08:30
Trip B: pick_up_time = 08:45
Gap = 15 min

PASO 1: Apply Reduce (minutes_to_reduce = 10)
─────────────────────────────────────────────
Trip A: 08:30 → 08:20 (guardado en DB)
Trip B: 08:45 → 08:35 (guardado en DB)

PASO 2: Apply Combine (min_gap=5, max_gap=15)
─────────────────────────────────────────────
Trip A: pick_up_time = 08:20 (leído de DB)
Trip B: pick_up_time = 08:35 (leído de DB)
Gap = 15 min ✅ (está en rango)

Midpoint = 08:27:30 → 08:28 (redondeado)
Trip A: 08:20 → 08:28
Trip B: 08:35 → 08:28

RESULTADO FINAL:
Trip A: pick_up_time = 08:28, original_pick_up_time = 08:30
Trip B: pick_up_time = 08:28, original_pick_up_time = 08:45
```

### Escenario: Reduce → Combine → Expand (mismo día)

```
PASO 1: Apply Reduce (minutes_to_reduce = 10)
─────────────────────────────────────────────
Trips modificados, guardados en DB

PASO 2: Apply Combine (min_gap=5, max_gap=15)
─────────────────────────────────────────────
Combine lee los tiempos YA REDUCIDOS de la DB
Une pares según gap reducido

PASO 3: Apply Expand (min_gap=5, max_gap=15, max_shift=10)
─────────────────────────────────────────────────────────
Expand lee los tiempos YA COMBINADOS de la DB
Separa pares que quedaron demasiado juntos
Rule B: Valida que no cree gaps en rango de Combine
```

---

## El Bug: `skip_days_with_stack`

### Ubicación

`step_filter_service.py` líneas 1396-1409:

```python
async def apply_bulk(...):
    for pick_up_date in dates:
        # Check if we should skip days with existing stack
        if config.skip_days_with_stack:  # ← DEFAULT = True
            has_stack = await self._day_has_active_stack(
                location_id, airline, pick_up_date
            )
            if has_stack:  # ← Verifica CUALQUIER step activo
                by_date.append(DayResult(
                    skipped=True,
                    skip_reason="Day already has active filter stack"
                ))
                continue  # ← SALTA EL DÍA
```

### `_day_has_active_stack` (líneas 1221-1237)

```python
async def _day_has_active_stack(self, ...) -> bool:
    query = (
        Select(FilterStep.id)
        .Where(FilterStep.location_id == location_id)
        .Where(FilterStep.airline == airline)
        .Where(FilterStep.pick_up_date == pick_up_date)
        .Where(FilterStep.is_active == True)
        # ← NO filtra por filter_type
        .Limit(1)
    )
    result = await self.session.exec(query).first()
    return result is not None  # True si existe CUALQUIER step
```

### El Problema

| Acción | Qué pasa | Esperado |
|--------|----------|----------|
| Apply Reduce | ✅ Funciona | ✅ |
| Apply Combine (después de Reduce) | ❌ SKIPPED "Day already has active filter stack" | ✅ Debería aplicar |
| Apply Expand (después de Reduce+Combine) | ❌ SKIPPED | ✅ Debería aplicar |

### La Lógica Deseada

```
skip_days_with_stack = True debería significar:
- Saltar si YA EXISTE un step del MISMO filter_type

NO debería significar:
- Saltar si existe CUALQUIER step
```

---

## Fix Propuesto

### Opción A: Modificar `_day_has_active_stack`

```python
async def _day_has_active_stack(
    self,
    location_id: UUID,
    airline: str,
    pick_up_date: date,
    filter_type: str | None = None,  # ← AGREGAR parámetro
) -> bool:
    query = (
        Select(FilterStep.id)
        .Where(FilterStep.location_id == location_id)
        .Where(FilterStep.airline == airline)
        .Where(FilterStep.pick_up_date == pick_up_date)
        .Where(FilterStep.is_active == True)
    )

    # Si se especifica filter_type, solo verificar ese tipo
    if filter_type:
        query = query.Where(FilterStep.filter_type == filter_type)

    query = query.Limit(1)
    result = await self.session.exec(query).first()
    return result is not None
```

### Actualizar llamada en `apply_bulk`

```python
if config.skip_days_with_stack:
    has_stack = await self._day_has_active_stack(
        location_id, airline, pick_up_date,
        filter_type=config.filter_type  # ← PASAR el tipo
    )
```

### Resultado

| Acción | Antes | Después |
|--------|-------|---------|
| Reduce (ningún step existe) | ✅ | ✅ |
| Reduce (Reduce ya existe) | ❌ Skip | ❌ Skip (correcto) |
| Combine (solo Reduce existe) | ❌ Skip (BUG) | ✅ Aplica |
| Combine (Combine ya existe) | - | ❌ Skip (correcto) |
| Expand (Reduce+Combine existen) | ❌ Skip (BUG) | ✅ Aplica |
| Expand (Expand ya existe) | - | ❌ Skip (correcto) |

---

## Flujo Completo Correcto

```
1. Usuario activa Reduce con ventana 05:00-10:00, minutes_to_reduce=10
   → POST /bulk/apply {filter_type: "reduce", ...}
   → Backend crea FilterStep(filter_type="reduce") para cada día
   → Trips en ventana tienen pick_up_time reducido

2. Usuario activa Combine con ventana 05:00-10:00, min_gap=5, max_gap=15
   → POST /bulk/apply {filter_type: "combine", ...}
   → Backend verifica: ¿Existe step de tipo "combine"? → NO
   → Backend crea FilterStep(filter_type="combine") para cada día
   → Combine trabaja sobre los tiempos YA REDUCIDOS

3. Usuario activa Expand con ventana 05:00-10:00
   → POST /bulk/apply {filter_type: "expand", ...}
   → Backend verifica: ¿Existe step de tipo "expand"? → NO
   → Backend crea FilterStep(filter_type="expand") para cada día
   → Expand trabaja sobre los tiempos YA REDUCIDOS+COMBINADOS

4. GET /stack devuelve:
   steps: [
     {filter_type: "reduce", step_order: 1},
     {filter_type: "combine", step_order: 2},
     {filter_type: "expand", step_order: 3}
   ]
```

---

## Resumen

| Aspecto | Estado |
|---------|--------|
| Reduce trabaja sobre original | ✅ Correcto (evita drift) |
| Combine trabaja sobre tiempo actual | ✅ Correcto (acumula) |
| Expand trabaja sobre tiempo actual | ✅ Correcto (acumula) |
| Múltiples tipos en mismo día | ✅ Permitido |
| Mismo tipo duplicado en día | ❌ Bloqueado |

## Fixes Aplicados (2026-01-25)

1. **`_day_has_active_stack`** - Ahora filtra por `filter_type` para permitir stacking de diferentes tipos
2. **`_get_next_step_order`** - Fix para RowResult extraction
3. **`_get_effective_time`** - Ahora usa `pick_up_time` (actual) para que filtros se acumulen
