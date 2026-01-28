# Ground Filters V2 - Guía Completa de Revert

**Fecha:** 2026-01-28
**Versión:** 2.0 (Post-fix)
**Archivo:** `features/trips/services/step_filter_service.py`

---

## 📋 Tabla de Contenidos

1. [Resumen Ejecutivo](#resumen-ejecutivo)
2. [Conceptos Fundamentales](#conceptos-fundamentales)
3. [Revert Last Step](#revert-last-step)
4. [Revert Specific Step](#revert-specific-step)
5. [Bulk Revert](#bulk-revert)
6. [Proceso Interno Detallado](#proceso-interno-detallado)
7. [WebSocket Notifications](#websocket-notifications)
8. [Ejemplos de Uso](#ejemplos-de-uso)
9. [Edge Cases y Comportamientos Especiales](#edge-cases-y-comportamientos-especiales)
10. [Troubleshooting](#troubleshooting)

---

## Resumen Ejecutivo

El sistema de **Revert** en Ground Filters V2 permite deshacer filtros aplicados de forma controlada y segura. Soporta tres operaciones:

| Operación | Endpoint | Descripción |
|-----------|----------|-------------|
| **Revert Last** | `POST /revert-last` | Revierte el último step del stack (LIFO) |
| **Revert Step** | `POST /step/{id}/revert` | Revierte un step específico por ID |
| **Bulk Revert** | `POST /bulk/revert` | Revierte múltiples steps en un rango de fechas |

### Características Clave

- ✅ **Stack-Based:** Trabaja como una pila (stack) de cambios
- ✅ **Non-Destructive:** Siempre re-aplica steps restantes
- ✅ **Anti-Drift:** Usa `original_pick_up_time` inmutable para reset completo
- ✅ **Atomic:** Cada revert es una transacción completa
- ✅ **Real-time:** Notifica vía WebSocket para multi-tab sync

---

## Conceptos Fundamentales

### El Stack de Filtros

Los filtros se aplican como **pasos** (steps) en un stack:

```
Stack para 2026-01-31 (ejemplo):
  ┌──────────────────────────────────┐
  │ Step 3: Combine (5-15 gap)       │ ← Último aplicado (top of stack)
  ├──────────────────────────────────┤
  │ Step 2: Reduce (10 min)          │
  ├──────────────────────────────────┤
  │ Step 1: Reduce (15 min)          │ ← Primero aplicado (bottom of stack)
  └──────────────────────────────────┘
```

Cada step tiene:
- `step_order`: Posición en el stack (1, 2, 3...)
- `is_active`: Si está activo (true) o revertido (false)
- `filter_type`: Tipo de filtro ("reduce", "combine", "expand")
- `windows`: Configuración de ventanas de tiempo

### Estados de un Step

```python
# Estado ACTIVO
is_active = True   # Step está aplicado
trips afectados tienen:
  - pick_up_time modificado
  - original_pick_up_time guardado
  - reduce_applied/combine_applied/expand_applied = True
  - current_step_id apunta a este step

# Estado REVERTIDO
is_active = False  # Step fue revertido
El step permanece en la tabla pero no afecta trips
```

### Original Pick Up Time (Anti-Drift)

```python
# Primera vez que se modifica un trip
trip.original_pick_up_time = trip.pick_up_time  # Guardado para siempre
trip.pick_up_time = new_time  # Modificado

# Después de múltiples filtros
trip.original_pick_up_time = 08:00  # NUNCA cambia
trip.pick_up_time = 07:35  # Cambia con cada filtro

# Después de revert completo (sin steps activos)
trip.original_pick_up_time = NULL  # Se limpia
trip.pick_up_time = 08:00  # Vuelve a original
```

**Regla de Oro:** `original_pick_up_time` es INMUTABLE excepto:
- Se establece la primera vez que se modifica un trip
- Se limpia (NULL) cuando NO quedan steps activos

---

## Revert Last Step

### Descripción

Revierte el **último step activo** (el de mayor `step_order`). Funciona como `pop()` en una pila.

### Endpoint

```
POST /v2/locations/{location_id}/airlines/{airline}/filters/revert-last
Query Parameters:
  - pick_up_date: "YYYY-MM-DD" (requerido)
```

### Request

```bash
POST /v2/locations/abc-123/airlines/WN/filters/revert-last?pick_up_date=2026-01-31
```

No requiere body (vacío).

### Response

```json
{
  "step_id": "uuid-del-step-revertido",
  "filter_type": "combine",
  "trips_recalculated": 25,
  "remaining_steps": 2,
  "stack_state": {
    "location_id": "abc-123",
    "airline": "WN",
    "pick_up_date": "2026-01-31",
    "steps": [
      {
        "step_id": "uuid-step-1",
        "step_order": 1,
        "filter_type": "reduce",
        "is_active": true,
        "trips_affected": 30
      },
      {
        "step_id": "uuid-step-2",
        "step_order": 2,
        "filter_type": "reduce",
        "is_active": true,
        "trips_affected": 30
      }
    ],
    "total_trips_affected": 30
  }
}
```

### Campos de Respuesta

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `step_id` | UUID | ID del step que fue revertido |
| `filter_type` | string | Tipo de filtro revertido ("reduce", "combine", "expand") |
| `trips_recalculated` | int | Número de trips recalculados |
| `remaining_steps` | int | Cuántos steps quedan activos después del revert |
| `stack_state` | StackState | Estado completo del stack después del revert |

### Ejemplo de Uso

**Escenario:** Tienes 3 steps aplicados, quieres revertir el último

```
Stack Inicial:
  Step 1: Reduce -15min (active)
  Step 2: Reduce -10min (active)
  Step 3: Combine 5-15gap (active)  ← Este se revertirá

Acción:
  POST /revert-last?pick_up_date=2026-01-31

Resultado:
  Step 1: Reduce -15min (active) ✅
  Step 2: Reduce -10min (active) ✅
  Step 3: Combine (INACTIVE) ❌

Trips después:
  - Tiempos: Reducidos por Steps 1 y 2
  - reduce_applied: TRUE
  - combine_applied: FALSE
  - original_pick_up_time: Mantiene valor original
```

---

## Revert Specific Step

### Descripción

Revierte un **step específico por ID**, sin importar su posición en el stack. Útil para revertir steps del medio sin afectar los de arriba.

### Endpoint

```
POST /v2/locations/{location_id}/airlines/{airline}/filters/step/{step_id}/revert
Path Parameters:
  - step_id: UUID del step a revertir (requerido)
```

### Request

```bash
POST /v2/locations/abc-123/airlines/WN/filters/step/uuid-step-2/revert
```

No requiere body (vacío).

### Response

Mismo formato que `revert_last_step`:

```json
{
  "step_id": "uuid-step-2",
  "filter_type": "reduce",
  "trips_recalculated": 30,
  "remaining_steps": 2,
  "stack_state": {...}
}
```

### Ejemplo de Uso

**Escenario:** Tienes 3 steps, quieres revertir el del medio

```
Stack Inicial:
  Step 1: Reduce -15min (active)
  Step 2: Combine 5-15gap (active)  ← Revertir este
  Step 3: Expand 10min (active)

Acción:
  POST /step/uuid-step-2/revert

Proceso:
  1. Marca Step 2 como inactive
  2. Resetea TODOS los trips a original
  3. Re-aplica Step 1 (Reduce) ✅
  4. Re-aplica Step 3 (Expand) ✅

Resultado:
  Step 1: Reduce (active) ✅
  Step 2: Combine (INACTIVE) ❌
  Step 3: Expand (active) ✅

Trips después:
  - Tiempos: Afectados por Reduce + Expand
  - reduce_applied: TRUE
  - combine_applied: FALSE
  - expand_applied: TRUE
```

**Ventaja:** Puedes remover un step del medio sin afectar los de arriba.

---

## Bulk Revert

### Descripción

Revierte filtros a través de **múltiples fechas** en una sola operación. Útil para deshacer filtros aplicados masivamente.

### Endpoint

```
POST /v2/locations/{location_id}/airlines/{airline}/filters/bulk/revert
```

### Request

```json
{
  "date_from": "2026-01-31",
  "date_to": "2026-02-28",
  "filter_type": "reduce"
}
```

| Campo | Tipo | Descripción | Requerido |
|-------|------|-------------|-----------|
| `date_from` | string | Fecha inicio (YYYY-MM-DD) | ✅ Sí |
| `date_to` | string? | Fecha fin (null = todos los futuros) | ❌ Opcional |
| `filter_type` | string? | Tipo de filtro ("reduce", "combine", "expand", null = todos) | ❌ Opcional |

### Response

```json
{
  "date_from": "2026-01-31",
  "date_to": "2026-02-28",
  "filter_type": "reduce",
  "total_days": 29,
  "days_with_reverts": 29,
  "days_skipped": 0,
  "total_steps_reverted": 29,
  "total_trips_recalculated": 870,
  "by_date": [
    {
      "pick_up_date": "2026-01-31",
      "steps_reverted": 1,
      "step_ids": ["uuid-step-1"],
      "trips_recalculated": 30,
      "skipped": false
    },
    {
      "pick_up_date": "2026-02-01",
      "steps_reverted": 1,
      "step_ids": ["uuid-step-2"],
      "trips_recalculated": 30,
      "skipped": false
    }
    // ... otros 27 días
  ]
}
```

### Campos de Respuesta

| Campo | Descripción |
|-------|-------------|
| `total_days` | Total de días en el rango |
| `days_with_reverts` | Días donde se revirtió al menos un step |
| `days_skipped` | Días sin steps activos (nada que revertir) |
| `total_steps_reverted` | Total de steps revertidos en todos los días |
| `total_trips_recalculated` | Total de trips recalculados |
| `by_date` | Array con detalles por cada día |

### Casos de Uso

#### Caso 1: Revertir un tipo de filtro en todo el futuro

```json
{
  "date_from": "2026-01-31",
  "date_to": null,
  "filter_type": "reduce"
}
```

Resultado: Revierte TODOS los steps de tipo "reduce" desde 2026-01-31 en adelante.

#### Caso 2: Revertir TODOS los filtros en un rango

```json
{
  "date_from": "2026-01-31",
  "date_to": "2026-02-28",
  "filter_type": null
}
```

Resultado: Revierte TODOS los steps (reduce, combine, expand) en ese rango.

#### Caso 3: Modificar una ventana de tiempo

```
Flujo:
1. Revert bulk del filter_type específico
2. Re-apply bulk con nueva configuración de windows
```

---

## Proceso Interno Detallado

### Método Core: `_revert_step_internal()`

Este método es el **corazón** de todas las operaciones de revert. Es llamado por:
- `revert_last_step()`
- `revert_step()`
- `revert_bulk()` (para cada día)

### Flujo Completo (3 Fases)

```
┌─────────────────────────────────────────────────────────────┐
│ FASE 1: MARCAR STEP COMO INACTIVO                          │
└─────────────────────────────────────────────────────────────┘
    ↓
    step.is_active = False
    self.session.add(step)
    ↓

┌─────────────────────────────────────────────────────────────┐
│ FASE 2: RESET COMPLETO DE TRIPS                            │
└─────────────────────────────────────────────────────────────┘
    ↓
    Query: Todos los trips con original_pick_up_time != NULL
    ↓
    Para cada trip:
      trip.pick_up_time = trip.original_pick_up_time  ← Reset
      trip.reduce_applied = False                     ← Reset
      trip.combine_applied = False                    ← Reset
      trip.expand_applied = False                     ← Reset
      trip.current_step_id = None                     ← Reset
      trip.filtered_at = None                         ← Reset
    ↓
    await self.session.commit()  ← COMMIT RESET
    ↓

┌─────────────────────────────────────────────────────────────┐
│ FASE 3: RE-APLICAR STEPS ACTIVOS RESTANTES                │
└─────────────────────────────────────────────────────────────┘
    ↓
    Query: Obtener todos los steps con is_active = True
    OrderBy: step_order ASC (del primero al último)
    ↓
    Para cada active_step:
      ↓
      self._reset_state()  ← Limpiar self.changes y tracking
      ↓
      Aplicar filtro según tipo:
        - _apply_reduce(trips, config)
        - _apply_combine(trips, config)
        - _apply_expand(trips, config)
      ↓
      Persistir cambios:
        Para cada change en self.changes:
          trip.pick_up_time = change.new_time
          trip.current_step_id = active_step.id
          trip.filtered_at = NOW()

          if filter_type == "reduce":
              trip.reduce_applied = True
          elif filter_type == "combine":
              trip.combine_applied = True
          elif filter_type == "expand":
              trip.expand_applied = True
      ↓
      await self.session.commit()  ← COMMIT CADA STEP
      ↓
      Refresh trip_lookup:
        trips = await query(trips_query).all()
        trip_lookup = {t.id: t for t in trips}
    ↓

┌─────────────────────────────────────────────────────────────┐
│ FASE 4: CLEANUP Y NOTIFICACIÓN                             │
└─────────────────────────────────────────────────────────────┘
    ↓
    Si NO quedan steps activos:
      trip.original_pick_up_time = NULL  ← Limpieza
      await self.session.commit()
    ↓
    stack_state = await self.get_stack(...)  ← Estado final
    ↓
    await self._send_revert_notification(...)  ← WebSocket
    ↓
    return StepRevertResult(...)
```

---

## Revert Last Step

### Código Fuente

```python
async def revert_last_step(
    self,
    location_id: UUID,
    airline: str,
    pick_up_date_str: str,
) -> StepRevertResult:
    """Revert the last active step (pop from stack)."""
    pick_up_date = date.fromisoformat(pick_up_date_str)

    # 1. Buscar último step activo (mayor step_order)
    query = (
        Select(FilterStep)
        .Where(FilterStep.location_id == location_id)
        .Where(FilterStep.airline == airline)
        .Where(FilterStep.pick_up_date == pick_up_date)
        .Where(FilterStep.is_active == True)
        .OrderBy(FilterStep.step_order.Desc())  # ← Descendente
        .Limit(1)
    )
    last_step = await self.session.exec(query).first()

    if not last_step:
        raise ValueError("No active steps found")

    # 2. Delegar a método interno
    return await self._revert_step_internal(
        last_step, location_id, airline, pick_up_date
    )
```

### Comportamiento

```
Stack Antes:
  Step 1 (order=1): Reduce -15min (active)
  Step 2 (order=2): Reduce -10min (active)
  Step 3 (order=3): Combine 5-15gap (active)  ← Último

Acción: revert_last_step()

Proceso:
  1. Encuentra Step 3 (mayor step_order)
  2. Step 3.is_active = False
  3. Resetea todos los trips a original
  4. Re-aplica Steps 1 y 2

Stack Después:
  Step 1 (order=1): Reduce -15min (active) ✅
  Step 2 (order=2): Reduce -10min (active) ✅
  Step 3 (order=3): Combine (INACTIVE) ❌

Trips después:
  - pick_up_time: Reducido por Steps 1 y 2
  - reduce_applied: TRUE
  - combine_applied: FALSE
  - original_pick_up_time: Mantiene valor
```

### Casos Especiales

#### Caso 1: Solo hay un step activo

```
Stack:
  Step 1: Reduce (active)

Acción: revert_last_step()

Resultado:
  Step 1: Reduce (INACTIVE)
  Stack vacío
  Trips: Vuelven a tiempos originales
  original_pick_up_time: Se limpia (NULL)
```

#### Caso 2: No hay steps activos

```
Stack: (vacío)

Acción: revert_last_step()

Error: ValueError("No active steps found")
```

---

## Revert Specific Step

### Descripción

Permite revertir cualquier step del stack por su ID, no solo el último. Útil para:
- Remover un step del medio
- Revertir por ID específico desde el UI
- Operaciones programáticas donde conoces el step_id

### Código Fuente

```python
async def revert_step(
    self,
    step_id: UUID,
) -> StepRevertResult:
    """Revert a specific step by ID."""
    # 1. Buscar step por ID
    query = Select(FilterStep).Where(FilterStep.id == step_id)
    step = await self.session.exec(query).first()

    if not step:
        raise ValueError(f"Step {step_id} not found")

    if not step.is_active:
        raise ValueError(f"Step {step_id} is already reverted")

    # 2. Delegar a método interno
    return await self._revert_step_internal(
        step, step.location_id, step.airline, step.pick_up_date
    )
```

### Diferencia con revert_last_step

| Aspecto | revert_last_step | revert_step |
|---------|------------------|-------------|
| **Parámetro** | pick_up_date | step_id |
| **Busca por** | step_order DESC | step.id |
| **Puede revertir** | Solo el último | Cualquiera |
| **Proceso interno** | ✅ Mismo (_revert_step_internal) | ✅ Mismo |

### Ejemplo de Uso

**Escenario:** Revertir Step 2 del medio del stack

```
Stack Inicial:
  Step 1 (order=1): Reduce -15min (active)
  Step 2 (order=2): Combine 5-15gap (active)  ← Revertir este
  Step 3 (order=3): Expand 10min (active)

Acción:
  POST /step/uuid-step-2/revert

Proceso:
  1. Marca Step 2 como inactive
  2. Resetea todos los trips a original
  3. Re-aplica Step 1 (Reduce) ✅
  4. Re-aplica Step 3 (Expand) ✅

Stack Después:
  Step 1 (order=1): Reduce -15min (active) ✅
  Step 2 (order=2): Combine (INACTIVE) ❌
  Step 3 (order=3): Expand 10min (active) ✅

Trips después:
  - Afectados por Reduce (-15min)
  - Afectados por Expand (separación)
  - NO afectados por Combine
  - reduce_applied: TRUE
  - combine_applied: FALSE
  - expand_applied: TRUE
```

---

## Bulk Revert

### Descripción

Revierte filtros en **múltiples días** de una sola vez. Puede revertir:
- Un tipo específico de filtro (ej: solo "reduce")
- Todos los tipos de filtros
- En un rango de fechas
- Desde una fecha hasta el futuro

### Código Fuente (Simplificado)

```python
async def revert_bulk(
    self,
    location_id: UUID,
    airline: str,
    config: BulkRevertConfig,
) -> BulkRevertResult:
    """Revert filter steps across multiple days."""
    date_from = date.fromisoformat(config.date_from)
    date_to = date.fromisoformat(config.date_to) if config.date_to else None

    # 1. Obtener todas las fechas con steps activos en el rango
    dates = await self._get_dates_with_active_steps(
        location_id, airline, date_from, date_to, config.filter_type
    )

    # 2. Para cada fecha
    for pick_up_date in dates:
        # Obtener steps a revertir (filtra por filter_type si se especifica)
        steps_to_revert = await self._get_steps_to_revert(
            location_id, airline, pick_up_date, config.filter_type
        )

        # Revertir cada step
        for step in steps_to_revert:
            result = await self._revert_step_internal(
                step, location_id, airline, pick_up_date
            )

    # 3. Retornar resumen
    return BulkRevertResult(...)
```

### Proceso de Bulk Revert

```
Input: date_from=2026-01-31, date_to=2026-02-05, filter_type="reduce"

Paso 1: Encontrar fechas con steps activos
  → Fechas encontradas: [2026-01-31, 2026-02-01, 2026-02-03, 2026-02-05]

Paso 2: Para cada fecha
  2026-01-31:
    → Encuentra steps tipo "reduce": [Step 1, Step 2]
    → Revierte Step 1 (_revert_step_internal)
    → Revierte Step 2 (_revert_step_internal)
    → Trips recalculados: 30

  2026-02-01:
    → Encuentra steps tipo "reduce": [Step 1]
    → Revierte Step 1 (_revert_step_internal)
    → Trips recalculados: 25

  ... (continúa para todas las fechas)

Paso 3: Retornar resumen
  total_steps_reverted: 5
  total_trips_recalculated: 120
  days_with_reverts: 4
```

### Ejemplos de Uso

#### Ejemplo 1: Revertir Reduce en todo el futuro

```json
POST /bulk/revert
{
  "date_from": "2026-01-31",
  "date_to": null,
  "filter_type": "reduce"
}
```

Resultado: Revierte TODOS los filtros Reduce desde 2026-01-31 hacia el futuro.

#### Ejemplo 2: Revertir TODO en un mes específico

```json
POST /bulk/revert
{
  "date_from": "2026-02-01",
  "date_to": "2026-02-28",
  "filter_type": null
}
```

Resultado: Revierte TODOS los filtros (reduce, combine, expand) en febrero 2026.

#### Ejemplo 3: Limpiar Combine de una semana

```json
POST /bulk/revert
{
  "date_from": "2026-02-01",
  "date_to": "2026-02-07",
  "filter_type": "combine"
}
```

Resultado: Revierte solo filtros Combine en esa semana, deja Reduce y Expand intactos.

---

## Proceso Interno Detallado

### Fase 1: Marcar Step como Inactivo

```python
# Código (línea 735-736)
step.is_active = False
self.session.add(step)
```

**Base de datos:**
```sql
UPDATE trips.filter_steps
SET is_active = false
WHERE id = 'step-uuid';
```

**Importante:** El step NO se elimina, solo se marca como inactivo.

---

### Fase 2: Reset Completo de Trips

```python
# Código (líneas 738-761)
# Query: Todos los trips filtrados del día
trips_query = (
    Select(Trip)
    .Where(Trip.location_id == location_id)
    .Where(Trip.airline == airline)
    .Where(Trip.pick_up_date == pick_up_date)
    .Where(Trip.original_pick_up_time != None)  # ← Solo filtrados
)
trips = await self.session.exec(trips_query).all()

# Reset cada trip a estado original
for trip in trips:
    if trip.original_pick_up_time:
        trip.pick_up_time = trip.original_pick_up_time
        trip.reduce_applied = False
        trip.combine_applied = False
        trip.expand_applied = False
        trip.current_step_id = None
        trip.filtered_at = None
        self.session.add(trip)

# COMMIT el reset
await self.session.commit()
```

**Base de datos:**
```sql
-- Para TODOS los trips del día que tienen filtros
UPDATE trips.trips
SET
    pick_up_time = original_pick_up_time,
    reduce_applied = false,
    combine_applied = false,
    expand_applied = false,
    current_step_id = NULL,
    filtered_at = NULL
WHERE location_id = 'xxx'
  AND airline = 'WN'
  AND pick_up_date = '2026-01-31'
  AND original_pick_up_time IS NOT NULL;
```

**Nota Crítica:** TODOS los trips del día se resetean, no solo los afectados por el step revertido. Esto garantiza consistencia al re-aplicar.

---

### Fase 3: Re-Aplicar Steps Activos Restantes

```python
# Código (líneas 763-834)
# 1. Obtener steps activos restantes
active_steps_query = (
    Select(FilterStep)
    .Where(FilterStep.location_id == location_id)
    .Where(FilterStep.airline == airline)
    .Where(FilterStep.pick_up_date == pick_up_date)
    .Where(FilterStep.is_active == True)
    .OrderBy(FilterStep.step_order.Asc())  # ← Orden ascendente
)
active_steps = await self.session.exec(active_steps_query).all()

# 2. Si quedan steps activos
if active_steps:
    trips = await self.session.exec(trips_query).all()
    trip_lookup = {t.id: t for t in trips}

    # 3. Re-aplicar cada step en orden
    for active_step in active_steps:
        # Limpiar estado interno
        self._reset_state()  # ← Importante

        # Reconstruir config del step
        config = FilterStepConfig(
            filter_type=active_step.filter_type,
            pick_up_date=str(pick_up_date),
            windows=[TimeWindow(**w) for w in active_step.windows],
        )

        # Obtener trips elegibles
        current_trips = await self._get_eligible_trips(
            location_id, airline, pick_up_date
        )

        # Aplicar filtro según tipo
        if config.filter_type == "reduce":
            self._apply_reduce(current_trips, config)
        elif config.filter_type == "combine":
            self._apply_combine(current_trips, config)
        elif config.filter_type == "expand":
            await self._apply_expand(current_trips, config)

        # Persistir cambios
        now = datetime.utcnow()
        for change in self.changes:
            trip = trip_lookup.get(change.trip_id)
            if not trip:
                trip_q = Select(Trip).Where(Trip.id == change.trip_id)
                trip = await self.session.exec(trip_q).first()

            if trip:
                if trip.original_pick_up_time is None:
                    trip.original_pick_up_time = trip.pick_up_time

                trip.pick_up_time = change.new_time
                trip.current_step_id = active_step.id
                trip.filtered_at = now

                # Establecer flag según tipo
                if config.filter_type == "reduce":
                    trip.reduce_applied = True
                elif config.filter_type == "combine":
                    trip.combine_applied = True
                elif config.filter_type == "expand":
                    trip.expand_applied = True

                self.session.add(trip)
                trips_recalculated += 1

        # COMMIT después de cada step (FIX aplicado)
        await self.session.commit()

        # REFRESH trip_lookup para próximo step (FIX aplicado)
        trips = await self.session.exec(trips_query).all()
        trip_lookup = {t.id: t for t in trips}

else:
    # NO quedan steps activos → Limpiar original_pick_up_time
    for trip in trips:
        trip.original_pick_up_time = None
        self.session.add(trip)
    await self.session.commit()
```

**Puntos Clave:**

1. **self._reset_state():** Limpia `self.changes`, `self.modified_by_combine_expand`, etc.
2. **Commit dentro del loop:** (FIX APLICADO) Cada step se commitea antes de aplicar el siguiente
3. **Refresh trip_lookup:** (FIX APLICADO) Se refresca después de cada commit
4. **Orden ascendente:** Steps se re-aplican en el orden original (1, 2, 3...)

---

### Fase 4: Cleanup y Notificación

```python
# Código (líneas 836-854)
# Si NO quedan steps activos
else:
    for trip in trips:
        trip.original_pick_up_time = None  # ← Cleanup
        self.session.add(trip)
        trips_recalculated += 1
    await self.session.commit()

# Obtener estado final del stack
stack_state = await self.get_stack(location_id, airline, str(pick_up_date))

# Enviar notificación WebSocket
await self._send_revert_notification(location_id, airline, step_id, filter_type)

# Retornar resultado
return StepRevertResult(
    step_id=step_id,
    filter_type=filter_type,
    trips_recalculated=trips_recalculated,
    remaining_steps=len(active_steps),
    stack_state=stack_state,
)
```

---

## WebSocket Notifications

### Evento: step_reverted

Cuando se revierte un step, se publica un evento en Redis:

```python
# Código (líneas 1184-1213)
async def _send_revert_notification(
    self,
    location_id: UUID,
    airline: str,
    step_id: UUID,
    filter_type: str,
):
    """Send notification when a step is reverted."""
    event = {
        "type": "step_reverted",
        "location_id": str(location_id),
        "airline": airline,
        "step_id": str(step_id),
        "filter_type": filter_type,
        "timestamp": datetime.utcnow().isoformat(),
        "message": f"Filter step reverted: {filter_type}"
    }

    channel = f"loc:{location_id}"
    await redis_client.publish(channel, json.dumps(event))
```

### Canal Redis

```
Channel: loc:{location_id}

Ejemplo: loc:abc-123-def-456
```

### Payload del Evento

```json
{
  "type": "step_reverted",
  "location_id": "abc-123-def-456",
  "airline": "WN",
  "step_id": "uuid-del-step-revertido",
  "filter_type": "combine",
  "timestamp": "2026-01-28T02:15:00.123456",
  "message": "Filter step reverted: combine"
}
```

### Frontend - Manejo del Evento

El frontend debe:

```typescript
websocket.on('step_reverted', async (event) => {
    // 1. Refetch stack para ver estado actualizado
    const stack = await api.getStack(locationId, airline, date);
    setActiveFilters(stack.steps);

    // 2. Refetch trips para ver tiempos y flags actualizados
    await refetchTrips();

    // 3. Mostrar notificación al usuario
    toast.success(`Filter ${event.filter_type} reverted`);

    // 4. Limpiar cualquier estado local guardado
    clearSavedFilterState();
});
```

**Importante:**
- ❌ NO asumir que todos los filtros se revirtieron
- ✅ Usar `stack.steps` del server como source of truth
- ✅ Siempre refetch trips después del evento

---

## Ejemplos de Uso

### Ejemplo 1: Revertir Último Step Simple

**Situación:**
```
Stack:
  Step 1: Reduce -10min (30 trips affected)

Usuario: "Undo this filter"
```

**Código:**
```bash
POST /v2/locations/abc/airlines/WN/filters/revert-last?pick_up_date=2026-01-31
```

**Response:**
```json
{
  "step_id": "step-1-uuid",
  "filter_type": "reduce",
  "trips_recalculated": 30,
  "remaining_steps": 0,
  "stack_state": {
    "steps": [],
    "total_trips_affected": 0
  }
}
```

**Estado Final:**
- Stack vacío
- 30 trips vuelven a tiempos originales
- `original_pick_up_time` limpiado (NULL)
- `reduce_applied = FALSE`

---

### Ejemplo 2: Revertir Step del Medio

**Situación:**
```
Stack:
  Step 1: Reduce -15min (active)
  Step 2: Combine 5-15gap (active) ← Queremos revertir este
  Step 3: Expand 10min (active)

Trips actualmente:
  - Reducidos 15 min
  - Combinados (pares al midpoint)
  - Expandidos 10 min
```

**Código:**
```bash
POST /v2/locations/abc/airlines/WN/filters/step/step-2-uuid/revert
```

**Proceso Detallado:**

```
Fase 1: Marcar Step 2 como inactive
  Step 2.is_active = False

Fase 2: Reset TODOS los trips
  Trip A: 08:00 (original) → reset a 08:00
  Trip B: 08:10 (original) → reset a 08:10
  All flags = False

Fase 3: Re-aplicar Steps 1 y 3

  Re-aplicar Step 1 (Reduce -15min):
    Trip A: 08:00 → 07:45
    Trip B: 08:10 → 07:55
    reduce_applied = True
    COMMIT

  Re-aplicar Step 3 (Expand 10min):
    Trip A: 07:45 → 07:35 (retrocede 10 min)
    Trip B: 07:55 → 08:05 (avanza 10 min)
    expand_applied = True
    COMMIT

Fase 4: Resultado Final
  Trip A:
    pick_up_time = 07:35
    reduce_applied = TRUE
    combine_applied = FALSE ← No re-aplicado
    expand_applied = TRUE

  Trip B:
    pick_up_time = 08:05
    reduce_applied = TRUE
    combine_applied = FALSE ← No re-aplicado
    expand_applied = TRUE
```

**Response:**
```json
{
  "step_id": "step-2-uuid",
  "filter_type": "combine",
  "trips_recalculated": 30,
  "remaining_steps": 2,
  "stack_state": {
    "steps": [
      {"step_order": 1, "filter_type": "reduce", "is_active": true},
      {"step_order": 3, "filter_type": "expand", "is_active": true}
    ]
  }
}
```

---

### Ejemplo 3: Bulk Revert - Limpiar Febrero

**Situación:**
```
Febrero tiene 28 días
Cada día tiene:
  - Step 1: Reduce -10min
  - Step 2: Combine 5-15gap

Usuario: "Remove all filters from February"
```

**Código:**
```bash
POST /v2/locations/abc/airlines/WN/filters/bulk/revert
{
  "date_from": "2026-02-01",
  "date_to": "2026-02-28",
  "filter_type": null
}
```

**Proceso:**
```
Para cada día (2026-02-01 hasta 2026-02-28):
  1. Encuentra steps activos: [Step 1, Step 2]
  2. Revierte Step 1 (Reduce):
     - Marca Step 1 inactive
     - Reset trips
     - Re-aplica Step 2 (Combine)
  3. Revierte Step 2 (Combine):
     - Marca Step 2 inactive
     - Reset trips
     - NO hay steps restantes
     - Limpia original_pick_up_time

Total:
  - 28 días procesados
  - 56 steps revertidos (2 por día)
  - ~800 trips recalculados
```

**Response:**
```json
{
  "date_from": "2026-02-01",
  "date_to": "2026-02-28",
  "filter_type": null,
  "total_days": 28,
  "days_with_reverts": 28,
  "days_skipped": 0,
  "total_steps_reverted": 56,
  "total_trips_recalculated": 840,
  "by_date": [
    {
      "pick_up_date": "2026-02-01",
      "steps_reverted": 2,
      "step_ids": ["step-1-uuid", "step-2-uuid"],
      "trips_recalculated": 30
    },
    // ... 27 días más
  ]
}
```

---

### Ejemplo 4: Modificar Configuración de Ventanas

**Situación:**
```
Tienes Reduce aplicado con windows incorrectas:
  Window: 00:00-24:00, reduce 10min

Quieres cambiar a:
  Window 1: 05:00-12:00, reduce 15min
  Window 2: 12:00-18:00, reduce 5min
```

**Proceso:**
```bash
# Paso 1: Revertir el Reduce existente
POST /bulk/revert
{
  "date_from": "2026-01-31",
  "date_to": null,
  "filter_type": "reduce"
}

# Paso 2: Re-aplicar con nueva configuración
POST /bulk/apply
{
  "filter_type": "reduce",
  "date_from": "2026-01-31",
  "date_to": null,
  "windows": [
    {"start": "05:00", "end": "12:00", "minutes_to_reduce": 15},
    {"start": "12:00", "end": "18:00", "minutes_to_reduce": 5}
  ],
  "skip_days_with_stack": false  # ← Importante
}
```

**Resultado:**
- Configuración antigua removida
- Nueva configuración aplicada
- Trips recalculados con nuevas windows

---

## Edge Cases y Comportamientos Especiales

### Edge Case 1: Revertir el Único Step

```
Stack:
  Step 1: Reduce (active)

Acción: revert_last_step()

Resultado:
  - Step 1.is_active = False
  - remaining_steps = 0
  - Trips resetean a original
  - original_pick_up_time = NULL (limpiado)

stack_state.steps = []  ← Stack vacío
```

### Edge Case 2: Revertir Step Inexistente

```python
POST /step/uuid-no-existe/revert

Error: ValueError("Step uuid-no-existe not found")
Response: 404 Not Found
```

### Edge Case 3: Revertir Step Ya Revertido

```python
POST /step/uuid-step-inactive/revert

Error: ValueError("Step uuid-step-inactive is already reverted")
Response: 400 Bad Request
```

### Edge Case 4: No Hay Steps Activos

```python
POST /revert-last?pick_up_date=2026-01-31

Error: ValueError("No active steps found for location=..., airline=WN, date=2026-01-31")
Response: 400 Bad Request
```

### Edge Case 5: Bulk Revert Sin Matches

```json
POST /bulk/revert
{
  "date_from": "2026-01-31",
  "date_to": "2026-02-28",
  "filter_type": "expand"
}

// Si no hay steps tipo "expand" en ese rango
Response:
{
  "total_days": 0,
  "days_with_reverts": 0,
  "total_steps_reverted": 0,
  "total_trips_recalculated": 0,
  "by_date": []
}
```

### Edge Case 6: Revert con Múltiples Steps del Mismo Tipo

```
Stack:
  Step 1: Reduce -15min (active)
  Step 2: Reduce -10min (active)  ← Revertir este
  Step 3: Combine (active)

Acción: POST /step/step-2-uuid/revert

Proceso:
  1. Step 2.is_active = False
  2. Reset trips
  3. Re-aplica Step 1 (Reduce -15min)
  4. Re-aplica Step 3 (Combine)

Resultado Final:
  Trip afectado por Reduce (-15 solo) y Combine
  reduce_applied = TRUE (de Step 1)
  combine_applied = TRUE (de Step 3)
```

---

## Comportamientos Importantes

### 1. Reset Completo Siempre

**Principio:** Cuando se revierte UN step, se resetean TODOS los trips del día y se re-aplican todos los steps activos.

**Por qué:** Garantiza consistencia. Los filtros pueden interactuar entre sí (Reduce afecta gaps para Combine).

**Ejemplo:**
```
Initial:
  Step 1: Reduce -20min (gap entre A y B = 10min)
  Step 2: Combine 5-15gap (combina A y B)

Si solo quitáramos Step 1 sin re-aplicar:
  Gap entre A y B = 30min (demasiado grande)
  Combine ya no aplicaría
  → Estado inconsistente

Solución: Reset + Re-apply:
  1. Reset a original (gap = 30min)
  2. Re-apply Combine (no aplica porque gap > 15)
  → Estado consistente
```

### 2. Order Preservation

Los steps se re-aplican en **orden ascendente** (step_order), no en el orden en que fueron creados.

**Ejemplo:**
```
Stack:
  Step 1 (order=1): Reduce
  Step 3 (order=3): Expand  ← Step 2 fue revertido antes

Revert Step 3:
  Re-aplica: Solo Step 1 (orden 1)
  NO crea un nuevo Step 2
```

### 3. Atomic Transactions

Cada revert es una transacción atómica:
- Si falla en cualquier punto → Rollback completo
- Todo se commitea o nada se commitea
- No hay estados parciales

### 4. Idempotencia

Revertir el mismo step dos veces:
```
Primera vez: Success (step.is_active = False)
Segunda vez: Error ("Step already reverted")
```

No hay efectos secundarios de intentar revertir múltiples veces.

---

## Troubleshooting

### Problema: Flags No se Establecen Después de Revert

**Síntoma:**
```sql
-- Después de revertir Step 3, Steps 1 y 2 siguen activos
-- Pero trips tienen reduce_applied = FALSE
SELECT reduce_applied FROM trips.trips WHERE ...
```

**Causa:** Bug en versión antigua (pre-fix 2026-01-28)

**Solución:** Actualizar a versión 2.0.1 o superior (FIX aplicado el 2026-01-28)

**Fix aplicado:**
- Commit movido dentro del loop (línea 830)
- Trip_lookup refrescado después de cada commit (líneas 833-834)

---

### Problema: Frontend Muestra Todos los Filtros Revertidos

**Síntoma:**
Después de revertir UN step, frontend muestra que TODOS los filtros desaparecieron.

**Diagnóstico:**
```bash
# Verificar en base de datos
docker exec postgres psql -U gt360 -d gt360 -c "
SELECT step_order, filter_type, is_active
FROM trips.filter_steps
WHERE location_id = 'xxx'
  AND pick_up_date = '2026-01-31'
ORDER BY step_order;
"

# Si backend muestra steps activos pero frontend no:
# → Bug del FRONTEND
```

**Causa (Frontend):**
- Frontend no usa `stack_state` del response
- Frontend no refetchea trips
- Frontend limpia todo el estado local

**Solución (Frontend):**
```typescript
const handleRevert = async (stepId) => {
    const response = await api.revertStep(stepId);

    // Usar stack_state del response
    setFilters(response.stack_state.steps);

    // Refetch trips
    await refetchTrips();
};
```

---

### Problema: Trips con Tiempos Modificados Pero Sin Flags

**Síntoma:**
```sql
-- Trips tienen tiempos modificados y current_step_id
-- Pero reduce_applied = FALSE
SELECT
    pick_up_time,
    original_pick_up_time,
    reduce_applied,
    current_step_id
FROM trips.trips
WHERE original_pick_up_time != pick_up_time
  AND reduce_applied = false;
```

**Causa:** Bug en versión pre-fix (antes 2026-01-28)

**Migración (si necesitas corregir datos históricos):**
```sql
-- Corregir flags basándose en current_step_id
UPDATE trips.trips t
SET reduce_applied = true
FROM trips.filter_steps fs
WHERE t.current_step_id = fs.id
  AND fs.filter_type = 'reduce'
  AND fs.is_active = true
  AND t.reduce_applied = false;

-- Repetir para combine
UPDATE trips.trips t
SET combine_applied = true
FROM trips.filter_steps fs
WHERE t.current_step_id = fs.id
  AND fs.filter_type = 'combine'
  AND fs.is_active = true
  AND t.combine_applied = false;

-- Repetir para expand
UPDATE trips.trips t
SET expand_applied = true
FROM trips.filter_steps fs
WHERE t.current_step_id = fs.id
  AND fs.filter_type = 'expand'
  AND fs.is_active = true
  AND t.expand_applied = false;
```

---

### Problema: Error "No active steps found"

**Síntoma:**
```
POST /revert-last?pick_up_date=2026-01-31
Error: "No active steps found for location=..., airline=WN, date=2026-01-31"
```

**Causa:** No hay steps activos para ese día

**Verificación:**
```sql
SELECT step_order, filter_type, is_active
FROM trips.filter_steps
WHERE location_id = 'xxx'
  AND airline = 'WN'
  AND pick_up_date = '2026-01-31';
```

**Posibilidades:**
1. Nunca se aplicaron filtros ese día
2. Todos los filtros ya fueron revertidos (is_active = false)
3. Fecha incorrecta

---

### Problema: Bulk Revert No Revierte Nada

**Síntoma:**
```json
POST /bulk/revert
{
  "date_from": "2026-01-31",
  "filter_type": "combine"
}

Response:
{
  "total_steps_reverted": 0,
  "days_with_reverts": 0
}
```

**Causa:** No hay steps del tipo especificado en ese rango

**Verificación:**
```sql
SELECT
    pick_up_date,
    COUNT(*) as total_steps,
    COUNT(CASE WHEN filter_type = 'combine' THEN 1 END) as combine_steps
FROM trips.filter_steps
WHERE location_id = 'xxx'
  AND airline = 'WN'
  AND pick_up_date >= '2026-01-31'
  AND is_active = true
GROUP BY pick_up_date;
```

---

## Best Practices

### 1. Siempre Verificar Stack State Después de Revert

```typescript
const response = await api.revertStep(stepId);

// Usar el stack_state del response
console.log('Remaining steps:', response.stack_state.steps);
console.log('Total affected:', response.stack_state.total_trips_affected);
```

### 2. Refetch Trips Después de Revert

```typescript
await api.revertStep(stepId);
await refetchTrips();  // ← Obligatorio para ver estado actualizado
```

### 3. Usar Bulk Revert para Operaciones Masivas

```typescript
// ❌ Ineficiente
for (const date of dates) {
    await api.revertLast(date);
}

// ✅ Eficiente
await api.bulkRevert({
    date_from: dates[0],
    date_to: dates[dates.length - 1],
    filter_type: "reduce"
});
```

### 4. Manejar Errores Apropiadamente

```typescript
try {
    const result = await api.revertStep(stepId);
    toast.success(`Reverted ${result.filter_type} filter`);
} catch (error) {
    if (error.message.includes("already reverted")) {
        toast.info("Filter was already reverted");
    } else if (error.message.includes("not found")) {
        toast.error("Filter step not found");
    } else {
        toast.error("Error reverting filter");
    }
}
```

### 5. Escuchar WebSocket Events

```typescript
websocket.on('step_reverted', async (event) => {
    // Multi-tab sync
    if (event.location_id === currentLocation) {
        await refetchStack();
        await refetchTrips();
    }
});
```

---

## Verificación de Estado

### Query: Verificar Stack de un Día

```sql
SELECT
    step_order,
    filter_type,
    is_active,
    trips_affected,
    created_at,
    id
FROM trips.filter_steps
WHERE location_id = 'your-location-uuid'
  AND airline = 'WN'
  AND pick_up_date = '2026-01-31'
ORDER BY step_order ASC;
```

**Interpretación:**
- `is_active = true` → Step activo, afectando trips
- `is_active = false` → Step revertido, no afecta trips
- Gaps en step_order (1, 3, 5) → Steps 2 y 4 fueron revertidos

### Query: Verificar Estado de Trips

```sql
SELECT
    id,
    flight_number,
    pick_up_time::text as current,
    original_pick_up_time::text as original,
    reduce_applied,
    combine_applied,
    expand_applied,
    current_step_id
FROM trips.trips
WHERE location_id = 'your-location-uuid'
  AND airline = 'WN'
  AND pick_up_date = '2026-01-31'
  AND original_pick_up_time IS NOT NULL
ORDER BY pick_up_time
LIMIT 20;
```

**Interpretación:**
- `original != current` → Trip modificado
- Flags indican qué tipos de filtros están activos
- `current_step_id` indica el último step que modificó el trip

### Query: Trips con Flags Incorrectos (Post-Revert)

```sql
-- Encuentra trips con flags incorrectos
SELECT
    t.id,
    t.flight_number,
    t.reduce_applied,
    t.combine_applied,
    t.expand_applied,
    fs.filter_type as should_be
FROM trips.trips t
INNER JOIN trips.filter_steps fs ON t.current_step_id = fs.id
WHERE t.location_id = 'xxx'
  AND t.pick_up_date = '2026-01-31'
  AND fs.is_active = true
  AND (
    (fs.filter_type = 'reduce' AND t.reduce_applied = false)
    OR (fs.filter_type = 'combine' AND t.combine_applied = false)
    OR (fs.filter_type = 'expand' AND t.expand_applied = false)
  );
```

Si devuelve filas → Hay inconsistencia (bug pre-fix)

---

## Diagrama de Flujo Completo

### Revert Last Step - Diagrama Visual

```
┌─────────────────────────────────────────────────────────────┐
│ 1. RECIBIR REQUEST                                          │
│    POST /revert-last?pick_up_date=2026-01-31               │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. BUSCAR ÚLTIMO STEP ACTIVO                                │
│    SELECT * FROM filter_steps                               │
│    WHERE is_active = true                                   │
│    ORDER BY step_order DESC LIMIT 1                         │
└─────────────────────────────────────────────────────────────┘
                         ↓
                    ¿Encontrado?
                    /          \
                  NO            SÍ
                  ↓              ↓
        ┌──────────────┐  ┌──────────────────────────┐
        │ Error 400    │  │ 3. MARCAR COMO INACTIVE  │
        │ "No active   │  │    step.is_active = False│
        │  steps"      │  │    session.add(step)     │
        └──────────────┘  └──────────────────────────┘
                                      ↓
                          ┌──────────────────────────────────┐
                          │ 4. OBTENER TRIPS FILTRADOS       │
                          │    WHERE original_pick_up_time   │
                          │      IS NOT NULL                 │
                          └──────────────────────────────────┘
                                      ↓
                          ┌──────────────────────────────────┐
                          │ 5. RESET TODOS LOS TRIPS         │
                          │    pick_up_time = original       │
                          │    reduce_applied = False        │
                          │    combine_applied = False       │
                          │    expand_applied = False        │
                          │    current_step_id = NULL        │
                          └──────────────────────────────────┘
                                      ↓
                          ┌──────────────────────────────────┐
                          │ 6. COMMIT RESET                  │
                          │    await session.commit()        │
                          └──────────────────────────────────┘
                                      ↓
                          ┌──────────────────────────────────┐
                          │ 7. OBTENER STEPS ACTIVOS         │
                          │    WHERE is_active = true        │
                          │    ORDER BY step_order ASC       │
                          └──────────────────────────────────┘
                                      ↓
                              ¿Hay steps activos?
                              /              \
                          NO                  SÍ
                          ↓                    ↓
            ┌────────────────────┐   ┌──────────────────────────┐
            │ 8a. CLEANUP        │   │ 8b. RE-APLICAR STEPS     │
            │ original_pick_up_  │   │ Para cada active_step:   │
            │   time = NULL      │   │   - Apply filter         │
            │                    │   │   - Set flags            │
            │                    │   │   - COMMIT               │
            │                    │   │   - REFRESH trip_lookup  │
            └────────────────────┘   └──────────────────────────┘
                          ↓                    ↓
                          └────────┬───────────┘
                                   ↓
                          ┌──────────────────────────────────┐
                          │ 9. GET STACK STATE               │
                          │    Current state after revert    │
                          └──────────────────────────────────┘
                                      ↓
                          ┌──────────────────────────────────┐
                          │ 10. SEND WEBSOCKET EVENT         │
                          │     type: "step_reverted"        │
                          │     channel: loc:{location_id}   │
                          └──────────────────────────────────┘
                                      ↓
                          ┌──────────────────────────────────┐
                          │ 11. RETURN RESULT                │
                          │     StepRevertResult             │
                          └──────────────────────────────────┘
```

---

## API Reference Completa

### 1. Revert Last Step

```
POST /v2/locations/{location_id}/airlines/{airline}/filters/revert-last

Query Parameters:
  pick_up_date: string (YYYY-MM-DD, required)

Request Body: (vacío)

Response: StepRevertResult
  - step_id: UUID
  - filter_type: string
  - trips_recalculated: int
  - remaining_steps: int
  - stack_state: StackState

Errors:
  400 - Invalid location_id/date format
  400 - No active steps found
  500 - Internal server error
```

### 2. Revert Specific Step

```
POST /v2/locations/{location_id}/airlines/{airline}/filters/step/{step_id}/revert

Path Parameters:
  step_id: UUID (required)

Request Body: (vacío)

Response: StepRevertResult
  (mismo formato que revert_last)

Errors:
  400 - Invalid step_id format
  400 - Step not found
  400 - Step already reverted
  500 - Internal server error
```

### 3. Bulk Revert

```
POST /v2/locations/{location_id}/airlines/{airline}/filters/bulk/revert

Request Body: BulkRevertConfig
  {
    "date_from": "YYYY-MM-DD",
    "date_to": "YYYY-MM-DD" | null,
    "filter_type": "reduce" | "combine" | "expand" | null
  }

Response: BulkRevertResult
  - date_from: string
  - date_to: string?
  - filter_type: string?
  - total_days: int
  - days_with_reverts: int
  - days_skipped: int
  - total_steps_reverted: int
  - total_trips_recalculated: int
  - by_date: DayRevertResult[]

Errors:
  400 - Invalid date format
  500 - Internal server error
```

---

## Performance Considerations

### Revert Last/Specific Step

- **Time Complexity:** O(n * m)
  - n = número de trips filtrados en el día
  - m = número de steps activos restantes

- **Database Queries:**
  1. SELECT last/specific step (1 query)
  2. SELECT trips with filters (1 query)
  3. UPDATE trips reset (1 query, n rows)
  4. COMMIT
  5. SELECT active steps (1 query)
  6. For each active step:
     - SELECT trips (1 query)
     - UPDATE trips (1 query, n rows)
     - COMMIT

**Total:** ~2 + (2 * m) queries

### Bulk Revert

- **Time Complexity:** O(d * n * m)
  - d = número de días en el rango
  - n = trips por día
  - m = steps por día

- **Database Queries:** d * queries_per_day

**Recomendación:** Para rangos grandes, ejecutar en horarios de bajo tráfico.

---

## Testing Guide

### Test 1: Revert Last Simple

```python
# Setup
apply_step(Reduce, -10min)

# Test
result = revert_last_step(date="2026-01-31")

# Verify
assert result.remaining_steps == 0
assert result.stack_state.steps == []
assert all(trip.original_pick_up_time is None for trip in trips)
```

### Test 2: Revert Middle Step

```python
# Setup
apply_step(Reduce, -15min)  # Step 1
apply_step(Combine, 5-15gap)  # Step 2
apply_step(Expand, 10min)  # Step 3

# Test
result = revert_step(step_id=step_2_id)

# Verify
assert result.remaining_steps == 2
assert len(result.stack_state.steps) == 2
assert result.stack_state.steps[0].filter_type == "reduce"
assert result.stack_state.steps[1].filter_type == "expand"

# Verify trips
trips = get_trips(date="2026-01-31")
assert all(t.reduce_applied for t in trips if t.filtered)
assert all(not t.combine_applied for t in trips)
assert all(t.expand_applied for t in trips if t.filtered)
```

### Test 3: Bulk Revert

```python
# Setup
for date in range(jan_31, feb_28):
    apply_step(Reduce, date=date)

# Test
result = bulk_revert(
    date_from="2026-01-31",
    date_to="2026-02-28",
    filter_type="reduce"
)

# Verify
assert result.days_with_reverts == 29
assert result.total_steps_reverted == 29
assert result.total_trips_recalculated > 0
```

---

## Changelog

### 2026-01-28: Critical Fix

**Issue:** Filter flags not set after revert
**Fix:**
- Moved `commit()` inside the loop (line 830)
- Added `trip_lookup` refresh after each commit (lines 833-834)

**Impact:** All new revert operations now correctly set filter flags.

**Migration:** Historical data may need manual flag correction (see Troubleshooting).

---

## Related Documentation

- [GROUND_FILTERS_V2_COMPLETE_DOCUMENTATION.md](GROUND_FILTERS/GROUND_FILTERS_V2_COMPLETE_DOCUMENTATION.md)
- [FIX_REVERT_FLAGS_BUG.md](FIX_REVERT_FLAGS_BUG.md)
- [DEPLOY_PROCESS.md](../DEPLOY_PROCESS.md)

---

**Documentado por:** Claude Code
**Última actualización:** 2026-01-28
**Versión:** 2.0.1 (Post-fix)
