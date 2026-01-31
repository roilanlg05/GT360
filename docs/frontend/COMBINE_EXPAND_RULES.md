# Reglas de Prioridad entre Combine y Expand

## Resumen Ejecutivo

**Regla Principal**: El PRIMER filtro aplicado SIEMPRE GANA cuando hay conflicto entre Combine y Expand.

- ✅ **Si aplicas Combine primero (step_order=1), luego Expand (step_order=2)** → Combine se mantiene, Expand se salta
- ✅ **Si aplicas Expand primero (step_order=1), luego Combine (step_order=2)** → Expand se mantiene, Combine se salta

---

## Implementación en el Código

### 1. Cuando Combine encuentra trips con Expand ya aplicado

**Archivo**: `/features/trips/services/step_filter_service.py:550-567`

```python
# En el método _apply_combine()

# PRIORITY RULE: Expand has absolute priority
if trip_a.expand_applied or trip_b.expand_applied:
    logger.info(
        f"[PRIORITY_RULE] Combine skipping pair "
        f"({trip_a.id}, {trip_b.id}): "
        f"Expand already claimed these trips "
        f"(expand_applied: {trip_a.expand_applied}, {trip_b.expand_applied})"
    )
    self._record_exclusion(
        f"combine({trip_a.id}, {trip_b.id})",
        [trip_a.id, trip_b.id],
        "Skipped: Expand has priority (applied in earlier step)",
        0,
        0,
        trips=[trip_a, trip_b],
    )
    i += 1
    continue  # SALTA el par, NO aplica Combine
```

**Comportamiento**: Si cualquier trip del par tiene `expand_applied=true`, Combine SALTA ese par completamente.

### 2. Cuando Expand encuentra trips con Combine ya aplicado

**Archivo**: `/features/trips/services/step_filter_service.py:633-637`

```python
# En el método _apply_expand()

# PRIORITY RULE: Filter out trips blocked by Combine
available_trips = [
    t for t in sorted_trips
    if not t.combine_applied  # FILTRA trips que ya tienen Combine
]

if len(available_trips) < 2:
    continue  # No hay suficientes trips disponibles, salta esta ventana
```

**Comportamiento**: Expand FILTRA completamente todos los trips que tienen `combine_applied=true` antes de identificar cadenas.

---

## Regla de Mutua Exclusión

**Principio**: Un trip NO puede tener `combine_applied=true` Y `expand_applied=true` al mismo tiempo.

### Por qué?

1. **Ambos modifican posicionamiento de trips**: No pueden coexistir sin conflicto
2. **Combine trabaja en PARES**: Mueve dos trips a su punto medio
3. **Expand trabaja en CADENAS**: Esparce cadenas de 2-6 trips usando patrones de acordeón

Si permitiéramos ambos, habría conflictos sobre cuál modificación aplicar.

---

## Escenarios Detallados

### Escenario 1: Combine Primero, Luego Expand

**Pasos**:
1. Usuario aplica filtro Combine (step_order=1)
   - Trips A y B forman un par válido (gap 15 min, mismo hotel)
   - Combine mueve ambos a su punto medio
   - `trip_a.combine_applied = true`, `trip_b.combine_applied = true`

2. Usuario aplica filtro Expand (step_order=2)
   - Expand busca cadenas de trips disponibles
   - **FILTRA** trips donde `combine_applied=true`
   - Trip A y Trip B son EXCLUIDOS de la búsqueda de cadenas
   - Expand NO puede modificar estos trips

**Resultado**:
- ✅ Combine permanece aplicado a Trip A y Trip B
- ❌ Expand NO se aplica a Trip A y Trip B
- ✅ Expand SÍ puede aplicarse a otros trips que NO tengan `combine_applied=true`

**Flags finales**:
```json
{
  "trip_a": {
    "combine_applied": true,
    "expand_applied": false
  },
  "trip_b": {
    "combine_applied": true,
    "expand_applied": false
  }
}
```

### Escenario 2: Expand Primero, Luego Combine

**Pasos**:
1. Usuario aplica filtro Expand (step_order=1)
   - Trips A, B, C forman una cadena válida (gaps pequeños, mismo hotel)
   - Expand aplica patrón [-10, 0, +10]
   - `trip_a.expand_applied = true`, `trip_b.expand_applied = true`, `trip_c.expand_applied = true`

2. Usuario aplica filtro Combine (step_order=2)
   - Combine busca pares de trips consecutivos
   - Encuentra Trip A y Trip B como candidatos
   - **VERIFICA** si alguno tiene `expand_applied=true`
   - Ambos tienen `expand_applied=true`
   - Combine SALTA este par (lo registra como exclusión)

**Resultado**:
- ✅ Expand permanece aplicado a Trip A, B, C
- ❌ Combine NO se aplica a Trip A y Trip B
- ✅ Combine SÍ puede aplicarse a otros pares que NO tengan `expand_applied=true`

**Flags finales**:
```json
{
  "trip_a": {
    "combine_applied": false,
    "expand_applied": true
  },
  "trip_b": {
    "combine_applied": false,
    "expand_applied": true
  },
  "trip_c": {
    "combine_applied": false,
    "expand_applied": true
  }
}
```

### Escenario 3: Filtros en trips diferentes (sin conflicto)

**Pasos**:
1. Usuario aplica filtro Combine (step_order=1)
   - Trips A y B forman un par → Combine aplicado
   - `trip_a.combine_applied = true`, `trip_b.combine_applied = true`

2. Usuario aplica filtro Expand (step_order=2)
   - Trips D, E, F forman una cadena (diferentes de A y B)
   - Expand puede aplicarse porque D, E, F NO tienen `combine_applied=true`
   - `trip_d.expand_applied = true`, etc.

**Resultado**:
- ✅ Combine aplicado a Trip A y B
- ✅ Expand aplicado a Trip D, E, F
- Ambos filtros coexisten sin conflicto (en trips diferentes)

**Flags finales**:
```json
{
  "trip_a": { "combine_applied": true, "expand_applied": false },
  "trip_b": { "combine_applied": true, "expand_applied": false },
  "trip_d": { "combine_applied": false, "expand_applied": true },
  "trip_e": { "combine_applied": false, "expand_applied": true },
  "trip_f": { "combine_applied": false, "expand_applied": true }
}
```

---

## Regla A: Modificación Única por Combine/Expand

**Archivo**: `/features/trips/services/step_filter_service.py:545-548`

```python
# Rule A check (dentro del mismo step)
if (trip_a.id in self.modified_by_combine_expand or
    trip_b.id in self.modified_by_combine_expand):
    i += 1
    continue
```

**Propósito**: Dentro del MISMO step, un trip solo puede ser modificado UNA VEZ por Combine.

**Ejemplo**:
- Trips: A (04:00), B (04:15), C (04:30)
- Gap A-B = 15 min (válido)
- Gap B-C = 15 min (válido)
- Combine procesa A-B primero → mueve a 04:07
- Combine NO puede procesar B-C después porque B ya fue modificado en este step

Esta regla es INDEPENDIENTE de la regla de prioridad entre Combine y Expand.

---

## Comportamiento Durante Revert

Cuando reviertes un step:

**Archivo**: `/features/trips/services/step_filter_service.py:812-822`

```python
# Reset all trips to original
for trip in trips:
    if trip.original_pick_up_time:
        trip.pick_up_time = trip.original_pick_up_time
        trip.reduce_applied = False
        trip.combine_applied = False   # ← Se resetea
        trip.expand_applied = False     # ← Se resetea
        trip.current_step_id = None
        trip.filtered_at = None
```

Luego se **re-aplican** todos los steps activos restantes en orden:

```python
# Re-apply remaining steps in order
for active_step in active_steps:
    if config.filter_type == "reduce":
        self._apply_reduce(current_trips, config)
    elif config.filter_type == "combine":
        self._apply_combine(current_trips, config)
    elif config.filter_type == "expand":
        await self._apply_expand(current_trips, config)
```

Esto garantiza que las reglas de prioridad se respeten correctamente después del revert.

---

## Aclaración sobre el Comentario "Expand has absolute priority"

**Comentario en el código** (línea 550):
```python
# PRIORITY RULE: Expand has absolute priority
```

**Este comentario es ENGAÑOSO**. La regla real es:

- **Si Expand fue aplicado PRIMERO** (tiene `expand_applied=true`), Combine lo respeta
- **Si Combine fue aplicado PRIMERO** (tiene `combine_applied=true`), Expand lo respeta

**NO es que Expand tenga "prioridad absoluta"**. Es mutua exclusión donde **el primero gana**.

El comentario debería decir:
```python
# PRIORITY RULE: If Expand was already applied to this trip, respect it and skip
```

---

## Resumen de Reglas

| Situación | Comportamiento | Resultado |
|-----------|---------------|-----------|
| **Combine aplicado primero** | Expand ve `combine_applied=true` → FILTRA esos trips | Combine GANA |
| **Expand aplicado primero** | Combine ve `expand_applied=true` → SALTA el par | Expand GANA |
| **Trips diferentes** | No hay conflicto | Ambos coexisten |
| **Dentro del mismo step** | Rule A: un trip solo se modifica 1 vez | Primera modificación GANA |

---

## Para el Frontend

**Combinaciones válidas en un mismo trip**:
1. ✅ `reduce_applied=true, combine_applied=true, expand_applied=false`
2. ✅ `reduce_applied=true, combine_applied=false, expand_applied=true`
3. ❌ `combine_applied=true, expand_applied=true` ← **IMPOSIBLE**

**Cómo verificar si hay conflicto**:
```typescript
// ❌ Estado inválido (error de integridad de datos)
if (trip.combine_applied && trip.expand_applied) {
  console.error('Invalid state: Combine and Expand cannot both be true!');
  // Reportar error al backend
}
```

**Orden de iconos**: Siempre usar `step_order` del stack state para mostrar en orden cronológico.

---

## Pregunta del Usuario

> "si yo aplico Combine y luego Expand en las reglas solo se debería quedar Combine cuando choquen"

**✅ CORRECTO**: Eso es exactamente lo que pasa en el código actual.

Si aplicas:
1. Step 1: Combine
2. Step 2: Expand

Y hay trips que forman un par válido para Combine Y también forman parte de una cadena para Expand:

- Combine los modifica primero → `combine_applied=true`
- Expand los ve y los FILTRA (línea 634-637)
- Expand NO los modifica
- **Resultado**: Solo Combine permanece aplicado

> "el comportamiento que veo es que se dejan de aplicar los dos"

**Posible causa**: Si estás viendo que AMBOS se dejan de aplicar, podría ser:
1. Los trips no cumplen los criterios para ninguno de los dos filtros
2. Hay un revert intermedio que resetea todo
3. Los trips no tienen la misma combinación de pickup/dropoff location requerida

**Para investigar**: Revisar los logs y ver las exclusiones registradas.

---

**Última actualización**: 2026-01-31
