# Prototipo: Expand con Optimización Global

**Fecha:** 2026-01-28
**Objetivo:** Maximizar expansión total sin romper lógica existente
**Alcance:** Solo modifica `_apply_expand()`, no afecta Reduce ni Combine

---

## Especificaciones Confirmadas

| Parámetro | Valor |
|-----------|-------|
| **Trips por bloque** | Máximo 6 |
| **Configuraciones a probar** | 3^6 = 729 (exhaustivo) |
| **Restricción location** | pickup_location Y drop_off_location iguales |
| **"Choque"** | Gap muy pequeño (pendiente: ¿cuánto?) |
| **max_shift** | Valor configurado por usuario (ej: 10 min) |

---

## Configuraciones a Probar

```python
# Para cada trip: shift puede ser {-max_shift, 0, +max_shift}

Ejemplos con max_shift=10:

Config 1: [-10,   0, +10, +10, +10, +10]  # Extremos
Config 2: [-10, -10, +10, +10, +10, +10]  # Máxima todos
Config 3: [-10,  -5,  +5, +10, +10, +10]  # Balanceado
Config 4: [ -5,  +5, +10, +10, +10, +10]  # Nueva sugerida
Config 5: [  0,   0,  +5,  +5, +10, +10]  # Gradual
...
Total: 729 configuraciones
```

---

## Pseudocódigo del Algoritmo

```python
def _apply_expand_optimized(self, trips, config):
    """
    Expand con optimización global: maximiza expansión total por bloque.

    NO modifica: Reduce, Combine, ni lógica de ventanas/hoteles.
    SOLO cambia: cómo se calculan los shifts dentro de Expand.
    """
    for window in config.windows:
        # ====== LÓGICA EXISTENTE (NO ROMPER) ======

        # Filtrar por hotel
        filtered_trips = self._filter_by_hotel(trips, window.hotel_names)

        # Filtrar por ventana de tiempo
        window_trips = [
            t for t in filtered_trips
            if self._is_time_in_window(self._get_effective_time(t), window)
        ]

        # Ordenar por tiempo
        sorted_trips = sorted(
            window_trips,
            key=lambda t: self._time_to_minutes(self._get_effective_time(t))
        )

        # Filtrar trips bloqueados por Combine (Regla de Prioridad)
        available_trips = [
            t for t in sorted_trips
            if not t.combine_applied  # ← MANTENER
        ]

        if len(available_trips) < 2:
            continue

        # ====== NUEVA LÓGICA DE OPTIMIZACIÓN ======

        # Agrupar por (pickup_location, drop_off_location)
        location_groups = self._group_by_location(available_trips)

        for (pickup_loc, dropoff_loc), group_trips in location_groups.items():
            # Optimizar este grupo
            best_config = self._find_optimal_expand_config(
                trips=group_trips,
                max_shift=window.max_shift,
                min_gap=window.min_gap,
                max_gap=window.max_gap
            )

            # Aplicar mejor configuración
            for trip, shift in best_config:
                if shift != 0:
                    old_time = self._get_effective_time(trip)
                    new_time = self._add_minutes(old_time, shift)
                    self._record_change(trip, old_time, new_time, "expand")


def _group_by_location(self, trips):
    """
    Agrupa trips por (pickup_location, drop_off_location).

    Similar a Combine: solo expandir trips con mismo origen/destino.
    """
    from collections import defaultdict

    groups = defaultdict(list)
    for trip in trips:
        key = (trip.pick_up_location, trip.drop_off_location)
        groups[key].append(trip)

    return groups


def _find_optimal_expand_config(self, trips, max_shift, min_gap, max_gap):
    """
    Busca la configuración de shifts que maximiza expansión.

    Búsqueda exhaustiva: prueba todas las combinaciones de shifts.
    """
    import itertools

    n = len(trips)
    tiempos_base = [self._time_to_minutes(self._get_effective_time(t)) for t in trips]

    # Opciones de shift: {-max_shift, 0, +max_shift}
    shift_options = [-max_shift, 0, +max_shift]

    mejor_config = None
    mejor_score = -999999

    # Generar todas las combinaciones (3^n)
    for shifts in itertools.product(shift_options, repeat=n):
        # Calcular nuevos tiempos
        nuevos_tiempos = [t + s for t, s in zip(tiempos_base, shifts)]

        # Validar tiempos dentro del día [00:00, 23:59]
        if not all(0 <= t < 1440 for t in nuevos_tiempos):
            continue

        # Calcular score
        score = self._score_expand_config(
            tiempos_base=tiempos_base,
            nuevos_tiempos=nuevos_tiempos,
            shifts=shifts,
            min_gap=min_gap,
            max_gap=max_gap
        )

        if score > mejor_score:
            mejor_score = score
            mejor_config = shifts

    # Si no encontró configuración válida, retornar sin cambios
    if mejor_config is None:
        return [(trip, 0) for trip in trips]

    return [(trips[i], mejor_config[i]) for i in range(n)]


def _score_expand_config(self, tiempos_base, nuevos_tiempos, shifts, min_gap, max_gap):
    """
    Calcula score de una configuración de shifts.

    Score = (expansión lograda × 1000) - (gaps problemáticos × 10000) - movimiento total

    Prioridades:
    1. NO crear gaps problemáticos (penalización alta)
    2. Maximizar expansión (reward)
    3. Minimizar movimiento total (tie-breaker)
    """
    n = len(nuevos_tiempos)

    expansion_total = 0
    gaps_problematicos = 0
    movimiento_total = sum(abs(s) for s in shifts)

    for i in range(n - 1):
        gap_original = tiempos_base[i+1] - tiempos_base[i]
        gap_nuevo = nuevos_tiempos[i+1] - nuevos_tiempos[i]

        # Validar: NO crear "choques" (gaps muy pequeños)
        # PENDIENTE: definir threshold (ej: gap < 10 min)
        if gap_nuevo < 10:  # ← AJUSTAR según tu definición
            return -999999  # Penalizar configuración inválida

        # Si gap original estaba en rango problemático
        if min_gap <= gap_original <= max_gap:
            if gap_nuevo > max_gap:
                # Expansión lograda (gap salió del rango)
                expansion_total += (gap_nuevo - max_gap)
            elif gap_nuevo < min_gap:
                # Compresión (no queremos)
                return -999999
            else:
                # Sigue en rango problemático
                gaps_problematicos += 1

        # Si gap nuevo cae en rango problemático (creado nuevo problema)
        elif min_gap <= gap_nuevo <= max_gap:
            gaps_problematicos += 1

    # Penalización por gaps problemáticos
    penalizacion_gaps = gaps_problematicos * 10000

    # Score final
    score = (expansion_total * 1000) - penalizacion_gaps - movimiento_total

    return score
```

---

## Ejemplo Completo con Tus Datos

### Input (De la foto)

```
Trips (Hyatt Regency Louisville):
  WN 4285: 04:55
  WN 3530: 05:20 (gap 25)
  WN 1910: 06:00 (gap 40)
  WN 1703: 06:35 (gap 35)
  WN 3839: 07:00 (gap 25)

Config: min_gap=20, max_gap=35, max_shift=10
```

### Gaps Problemáticos Iniciales

```
Gap 1 (4285-3530): 25 min ✅ (en [20,35]) → EXPANDIR
Gap 2 (3530-1910): 40 min ❌ (fuera de rango) → DEJAR
Gap 3 (1910-1703): 35 min ✅ (en [20,35]) → EXPANDIR
Gap 4 (1703-3839): 25 min ✅ (en [20,35]) → EXPANDIR
```

### Configuraciones a Probar

#### Config 1: [-10, 0, +10, +10, +10]

```
Nuevos tiempos: [04:45, 05:20, 06:10, 06:45, 07:10]
Gaps nuevos: [35, 50, 35, 25]

Gap 1: 25→35 ✅ (expandió +10)
Gap 2: 40→50 (no era problemático)
Gap 3: 35→35 (sin cambio)
Gap 4: 25→25 ❌ (sigue problemático!)

Score: (10 × 1000) - (1 × 10000) - 40 = -40 ❌
```

#### Config 2: [-10, -5, +5, +10, +10]

```
Nuevos tiempos: [04:45, 05:15, 06:05, 06:45, 07:10]
Gaps nuevos: [30, 50, 40, 25]

Gap 1: 25→30 ✅ (expandió +5)
Gap 2: 40→50 (no problemático)
Gap 3: 35→40 ✅ (expandió +5)
Gap 4: 25→25 ❌ (sigue problemático!)

Score: (10 × 1000) - (1 × 10000) - 40 = -40 ❌
```

#### Config 3: [-10, 0, +10, 0, +10]

```
Nuevos tiempos: [04:45, 05:20, 06:10, 06:35, 07:10]
Gaps nuevos: [35, 50, 25, 35]

Gap 1: 25→35 ✅ (expandió +10)
Gap 2: 40→50 (no problemático)
Gap 3: 35→25 ❌ (COMPRIMIÓ!)

Score: -999999 (penalizado)
```

#### Config 4: [-10, -5, +5, -5, +10]

```
Nuevos tiempos: [04:45, 05:15, 06:05, 06:30, 07:10]
Gaps nuevos: [30, 50, 25, 40]

Gap 1: 25→30 ✅ (+5)
Gap 2: 40→50 (no problemático)
Gap 3: 35→25 ❌ (comprimió)

Score: -999999 (penalizado)
```

#### Config 5: [-10, 0, +5, +5, +10]

```
Nuevos tiempos: [04:45, 05:20, 06:05, 06:40, 07:10]
Gaps nuevos: [35, 45, 35, 30]

Gap 1: 25→35 ✅ (+10)
Gap 2: 40→45 (no problemático)
Gap 3: 35→35 (sin cambio)
Gap 4: 25→30 ✅ (+5)

Gaps problemáticos: 0 ✅

Expansión total: +10 + +5 = 15 min
Movimiento total: 10+5+5+10 = 30

Score: (15 × 1000) - 30 = 14,970 ✅ MEJOR!
```

**Config 5 gana** porque logra expandir 2 de 3 gaps problemáticos sin crear nuevos.

---

## Código Prototipo

```python
# ============================================================================
# NUEVA IMPLEMENTACIÓN DE EXPAND CON OPTIMIZACIÓN GLOBAL
# ============================================================================

async def _apply_expand(self, trips: list[Trip], config: FilterStepConfig):
    """
    Apply Expand filter with GLOBAL OPTIMIZATION.

    Busca la configuración de shifts que maximiza la expansión total
    sin crear gaps problemáticos (choques).

    PRIORITY RULE: If Combine already modified a trip, Expand cannot touch it.
    """
    for window in config.windows:
        # Skip window if disabled or no config
        if (not window.enabled or window.min_gap is None or
            window.max_gap is None or window.max_shift is None):
            continue

        # Filter by hotel names specific to this window
        filtered_trips = self._filter_by_hotel(trips, window.hotel_names)

        # Filter to trips within this window's time range
        window_trips = [
            t for t in filtered_trips
            if self._is_time_in_window(
                self._get_effective_time(t),
                window
            )
        ]

        # Sort by effective pickup time
        sorted_trips = sorted(
            window_trips,
            key=lambda t: self._time_to_minutes(self._get_effective_time(t))
        )

        # Filter out trips blocked by Combine (PRIORITY RULE)
        available_trips = [
            t for t in sorted_trips
            if not t.combine_applied
        ]

        if len(available_trips) < 2:
            continue

        # Group by location (pickup_location, drop_off_location)
        location_groups = self._group_trips_by_location(available_trips)

        # Optimize each location group independently
        for (pickup_loc, dropoff_loc), group_trips in location_groups.items():
            if len(group_trips) < 2:
                continue

            # NUEVA LÓGICA: Optimización global del grupo
            optimal_shifts = self._find_optimal_expand_shifts(
                trips=group_trips,
                max_shift=window.max_shift,
                min_gap=window.min_gap,
                max_gap=window.max_gap
            )

            # Aplicar shifts óptimos
            for trip, shift in optimal_shifts:
                if shift != 0:
                    old_time = self._get_effective_time(trip)
                    new_time = self._add_minutes(old_time, shift)

                    # Record change
                    self._record_change(trip, old_time, new_time, "expand")

                    logger.debug(
                        f"[EXPAND_OPT] Trip {trip.id}: "
                        f"{old_time} → {new_time} (shift {shift:+d})"
                    )


def _group_trips_by_location(self, trips: list[Trip]) -> dict:
    """
    Agrupa trips por (pickup_location, drop_off_location).

    Solo trips con mismo origen Y destino se pueden expandir juntos.
    Similar a la restricción de Combine.
    """
    from collections import defaultdict

    groups = defaultdict(list)
    for trip in trips:
        key = (trip.pick_up_location, trip.drop_off_location)
        groups[key].append(trip)

    return groups


def _find_optimal_expand_shifts(
    self,
    trips: list[Trip],
    max_shift: int,
    min_gap: int,
    max_gap: int
) -> list[tuple[Trip, int]]:
    """
    Encuentra la configuración de shifts que maximiza expansión.

    Búsqueda exhaustiva: prueba todas las combinaciones de
    {-max_shift, 0, +max_shift} por trip.

    Con máximo 6 trips: 3^6 = 729 configuraciones (muy manejable).
    """
    import itertools

    n = len(trips)

    # Extraer tiempos base (en minutos desde 00:00)
    tiempos_base = [
        self._time_to_minutes(self._get_effective_time(t))
        for t in trips
    ]

    # Opciones de shift por trip
    shift_options = [-max_shift, 0, +max_shift]

    mejor_config = None
    mejor_score = -999999

    logger.debug(
        f"[EXPAND_OPT] Optimizing {n} trips with {len(list(itertools.product(shift_options, repeat=n)))} configs"
    )

    # Probar todas las combinaciones
    for shifts in itertools.product(shift_options, repeat=n):
        # Calcular nuevos tiempos
        nuevos_tiempos = [
            tiempos_base[i] + shifts[i]
            for i in range(n)
        ]

        # Validar tiempos dentro del día [00:00, 23:59]
        if not all(0 <= t < 1440 for t in nuevos_tiempos):
            continue

        # Calcular score de esta configuración
        score = self._score_expand_config(
            tiempos_base=tiempos_base,
            nuevos_tiempos=nuevos_tiempos,
            shifts=shifts,
            min_gap=min_gap,
            max_gap=max_gap
        )

        if score > mejor_score:
            mejor_score = score
            mejor_config = shifts

            logger.debug(
                f"[EXPAND_OPT] New best: shifts={shifts}, score={score}"
            )

    # Si no encontró configuración válida, no modificar nada
    if mejor_config is None:
        logger.warning(
            f"[EXPAND_OPT] No valid configuration found for {n} trips"
        )
        return [(trip, 0) for trip in trips]

    logger.info(
        f"[EXPAND_OPT] Optimal config: shifts={mejor_config}, score={mejor_score}"
    )

    return [(trips[i], mejor_config[i]) for i in range(n)]


def _score_expand_config(
    self,
    tiempos_base: list[int],
    nuevos_tiempos: list[int],
    shifts: tuple[int],
    min_gap: int,
    max_gap: int
) -> int:
    """
    Calcula score de una configuración de shifts.

    Criterios (en orden de prioridad):
    1. NO crear gaps problemáticos → penalización -10,000 por gap
    2. NO crear "choques" (gap < 10 min) → penalización -999,999
    3. Maximizar expansión total → reward +1,000 por minuto expandido
    4. Minimizar movimiento → penalización -1 por minuto movido

    Returns: Score (mayor = mejor)
    """
    n = len(nuevos_tiempos)

    expansion_total = 0
    gaps_problematicos_nuevos = 0
    movimiento_total = sum(abs(s) for s in shifts)

    for i in range(n - 1):
        gap_original = tiempos_base[i+1] - tiempos_base[i]
        gap_nuevo = nuevos_tiempos[i+1] - nuevos_tiempos[i]

        # CRITERIO 1: NO crear "choques" (gaps muy pequeños)
        # TODO: Clarificar threshold con usuario
        CHOQUE_THRESHOLD = 10  # minutos
        if gap_nuevo < CHOQUE_THRESHOLD:
            return -999999  # Configuración inválida

        # CRITERIO 2: Medir expansión lograda
        if min_gap <= gap_original <= max_gap:
            # Gap original era problemático
            if gap_nuevo > max_gap:
                # Expandió: gap salió del rango
                expansion_total += (gap_nuevo - max_gap)
            elif gap_nuevo < min_gap:
                # Comprimió (no queremos)
                return -999999
            else:
                # Sigue en rango problemático
                gaps_problematicos_nuevos += 1

        # CRITERIO 3: NO crear nuevos gaps problemáticos
        elif min_gap <= gap_nuevo <= max_gap:
            # Creó un nuevo gap problemático
            gaps_problematicos_nuevos += 1

    # Score final
    score = (
        (expansion_total * 1000) -           # Maximizar expansión
        (gaps_problematicos_nuevos * 10000) - # Evitar gaps problemáticos
        movimiento_total                      # Minimizar movimiento
    )

    return score
```

---

## Integración con Código Existente

### Cambios Mínimos en `_apply_expand()`

**ANTES (líneas 611-667):**
```python
for i in range(len(sorted_trips) - 1):
    trip_a = sorted_trips[i]
    trip_b = sorted_trips[i + 1]

    # Validaciones...

    if window.min_gap <= gap <= window.max_gap:
        result = self._smart_expand(...)  # ← Par por par
        if result:
            self._record_change(...)
```

**DESPUÉS (con optimización):**
```python
# Filter blocked trips
available_trips = [t for t in sorted_trips if not t.combine_applied]

# Group by location
location_groups = self._group_trips_by_location(available_trips)

# Optimize each group
for (pickup, dropoff), group in location_groups.items():
    optimal_shifts = self._find_optimal_expand_shifts(
        trips=group,
        max_shift=window.max_shift,
        min_gap=window.min_gap,
        max_gap=window.max_gap
    )

    # Apply optimal shifts
    for trip, shift in optimal_shifts:
        if shift != 0:
            old_time = self._get_effective_time(trip)
            new_time = self._add_minutes(old_time, shift)
            self._record_change(trip, old_time, new_time, "expand")
```

---

## Métodos Nuevos a Agregar

```python
# 1. _group_trips_by_location() - líneas ~30
# 2. _find_optimal_expand_shifts() - líneas ~60
# 3. _score_expand_config() - líneas ~70
# Total: ~160 líneas nuevas

# Eliminar:
# - _smart_expand() (ya no se usa) - líneas ~90

# Neto: +70 líneas aproximadamente
```

---

## Validaciones que se Mantienen

```python
✅ window.enabled
✅ window.min_gap, max_gap, max_shift configurados
✅ Filter by hotel names
✅ Filter by time window
✅ Ordenar por tiempo
✅ Regla de Prioridad (skip si combine_applied)
✅ Tiempos dentro del día [00:00, 23:59]
❌ Rule A (modificada - permitir reusar trips dentro del mismo bloque)
```

---

## Pregunta Pendiente

**¿Cuál es el threshold para "choque"?**

En el código propuse `gap < 10 minutos`, pero necesito confirmación:

```python
CHOQUE_THRESHOLD = ???  # minutos

if gap_nuevo < CHOQUE_THRESHOLD:
    return -999999  # Configuración inválida
```

**Opciones:**
- `10 minutos` (conservador)
- `5 minutos` (más flexible)
- `min_gap - 10` (relativo a configuración)

---

## ¿Procedo con la Implementación?

Con esta información puedo:

1. ✅ Implementar `_group_trips_by_location()`
2. ✅ Implementar `_find_optimal_expand_shifts()` con búsqueda exhaustiva
3. ✅ Implementar `_score_expand_config()` con criterios claros
4. ✅ Modificar `_apply_expand()` para usar optimización
5. ✅ Eliminar `_smart_expand()` (ya no se necesita)
6. ✅ Mantener toda la lógica de validación existente

**Solo necesito que confirmes el threshold de "choque" y procedo con la implementación.**

¿Qué threshold prefieres? ¿O hay otra definición de "choque"?