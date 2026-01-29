# Algoritmo de Optimización para Expand - Máxima Expansión

**Fecha:** 2026-01-28
**Propuesto por:** Usuario
**Estado:** Diseño

---

## Concepto

### Problema Actual

El Expand procesa pares secuencialmente (A-B, B-C, C-D) y marca trips como "usados", dejando gaps intermedios sin expandir.

### Solución Propuesta

**Algoritmo de Optimización Global:**
1. Tomar TODOS los trips del día que cumplan la configuración
2. Generar múltiples **configuraciones de shifts** posibles
3. Calcular la **expansión total** de cada configuración
4. Elegir la configuración con **máxima expansión**
5. Aplicar esa configuración

---

## Algoritmo Detallado

### Input

```python
trips = [A, B, C, D]  # Ordenados por pick_up_time
tiempos = [04:55, 05:20, 05:45, 06:10]
max_shift = 10  # ±10 minutos por trip
min_gap = 20    # Gap mínimo deseado
max_gap = 35    # Gap máximo deseado
```

### Paso 1: Generar Configuraciones de Shifts

Cada trip puede tener shift de: `[-max_shift, 0, +max_shift]`

**Configuraciones posibles:**

```
Config 1: [-10,  0, +10, +10]  # A retrocede, C y D avanzan
Config 2: [  0, +10, +10, +10]  # Todos avanzan excepto A
Config 3: [-10, -10,  0, +10]  # A y B retroceden, D avanza
Config 4: [-10,  0,  0, +10]   # Solo A retrocede, D avanza
...
Total: 3^n configuraciones (donde n = número de trips)
```

### Paso 2: Calcular Expansión Total

Para cada configuración, calcular:

```python
def calcular_expansion_total(tiempos, shifts, min_gap, max_gap):
    """
    Calcula cuántos minutos de expansión se logran con esta config.

    Expansión = Suma de gaps que SALEN del rango [min_gap, max_gap]
    """
    nuevos_tiempos = [t + s for t, s in zip(tiempos, shifts)]

    expansion_total = 0
    gaps_problematicos = 0

    for i in range(len(nuevos_tiempos) - 1):
        gap_original = tiempos[i+1] - tiempos[i]
        gap_nuevo = nuevos_tiempos[i+1] - nuevos_tiempos[i]

        # Si el gap original estaba en rango problemático
        if min_gap <= gap_original <= max_gap:
            # Y ahora está fuera del rango
            if gap_nuevo > max_gap:
                expansion_total += (gap_nuevo - max_gap)
            elif gap_nuevo < min_gap:
                # Esto no es expansión, es compresión
                # NO queremos esto
                return -999999  # Penalizar

        # Validar que no crea gaps problemáticos nuevos
        if min_gap <= gap_nuevo <= max_gap:
            gaps_problematicos += 1

    # Penalizar si crea gaps problemáticos
    if gaps_problematicos > 0:
        return -999999

    return expansion_total
```

### Paso 3: Seleccionar Mejor Configuración

```python
mejor_config = None
mejor_expansion = -1

for config in generar_configuraciones(len(trips), max_shift):
    expansion = calcular_expansion_total(tiempos, config, min_gap, max_gap)

    if expansion > mejor_expansion:
        mejor_expansion = expansion
        mejor_config = config

# Aplicar mejor configuración
for i, shift in enumerate(mejor_config):
    if shift != 0:
        trips[i].pick_up_time = tiempos[i] + shift
```

---

## Ejemplo Concreto

### Configuración

```
Trips: A(04:55), B(05:20), C(05:45), D(06:10)
Gaps originales: [25, 25, 25] (todos en rango problemático [20,35])
max_shift = 10
```

### Configuraciones Candidatas

#### Config 1: [-10, 0, +10, +10]

```
A: 04:55 - 10 = 04:45
B: 05:20 + 0  = 05:20
C: 05:45 + 10 = 05:55
D: 06:10 + 10 = 06:20

Gaps nuevos: [35, 35, 25]
  Gap A-B: 35 (fuera de [20,35] ✅)
  Gap B-C: 35 (fuera de [20,35] ✅)
  Gap C-D: 25 (dentro de [20,35] ❌)

Expansión total: 10 + 10 = 20 minutos
Gaps problemáticos: 1 (C-D)
Score: -999999 (penalizado)
```

#### Config 2: [-10, 0, 0, +10]

```
A: 04:55 - 10 = 04:45
B: 05:20 + 0  = 05:20
C: 05:45 + 0  = 05:45
D: 06:10 + 10 = 06:20

Gaps nuevos: [35, 25, 35]
  Gap A-B: 35 (fuera ✅)
  Gap B-C: 25 (dentro ❌)
  Gap C-D: 35 (fuera ✅)

Expansión total: 10 + 10 = 20 minutos
Gaps problemáticos: 1 (B-C)
Score: -999999 (penalizado)
```

#### Config 3: [-10, -5, +5, +10]

```
A: 04:55 - 10 = 04:45
B: 05:20 - 5  = 05:15
C: 05:45 + 5  = 05:50
D: 06:10 + 10 = 06:20

Gaps nuevos: [30, 35, 30]
  Gap A-B: 30 (fuera ✅)
  Gap B-C: 35 (fuera ✅)
  Gap C-D: 30 (fuera ✅)

Expansión total: 5 + 10 + 5 = 20 minutos
Gaps problemáticos: 0 ✅
Score: 20 ✅ (MEJOR!)
```

### Resultado

Selecciona **Config 3** porque:
- Expansión total: 20 minutos
- No deja gaps problemáticos
- Todos los gaps salen del rango [20,35]

---

## Implementación Propuesta

### Pseudocódigo

```python
def _apply_expand_optimized(self, trips, config):
    """
    Expand con optimización global: busca la configuración que maximiza expansión.
    """
    for window in config.windows:
        filtered_trips = self._filter_by_hotel(trips, window.hotel_names)
        sorted_trips = sorted(filtered_trips, key=lambda t: t.pick_up_time)

        # Skip trips bloqueados por Combine
        available_trips = [
            t for t in sorted_trips
            if not t.combine_applied  # Regla de Prioridad
        ]

        if len(available_trips) < 2:
            continue

        # Optimización global
        best_config = self._find_optimal_expand_config(
            available_trips,
            max_shift=window.max_shift,
            min_gap=window.min_gap,
            max_gap=window.max_gap
        )

        # Aplicar mejor configuración
        for trip, shift in best_config:
            if shift != 0:
                old_time = trip.pick_up_time
                new_time = self._add_minutes(old_time, shift)
                self._record_change(trip, old_time, new_time, "expand")


def _find_optimal_expand_config(self, trips, max_shift, min_gap, max_gap):
    """
    Busca la configuración de shifts que maximiza expansión.

    Returns: List[(trip, shift)]
    """
    n = len(trips)
    tiempos_base = [self._time_to_minutes(t.pick_up_time) for t in trips]

    # Posibles shifts por trip
    shift_options = [-max_shift, 0, +max_shift]

    mejor_config = None
    mejor_score = -999999

    # Generar todas las combinaciones (3^n)
    for shifts in itertools.product(shift_options, repeat=n):
        # Calcular tiempos nuevos
        nuevos_tiempos = [t + s for t, s in zip(tiempos_base, shifts)]

        # Validar que tiempos estén dentro del día
        if not all(0 <= t < 24*60 for t in nuevos_tiempos):
            continue

        # Calcular score
        score = self._score_expand_config(
            tiempos_base, nuevos_tiempos, shifts, min_gap, max_gap
        )

        if score > mejor_score:
            mejor_score = score
            mejor_config = shifts

    # Convertir a lista de (trip, shift)
    return [(trips[i], mejor_config[i]) for i in range(n)]


def _score_expand_config(self, tiempos_base, nuevos_tiempos, shifts, min_gap, max_gap):
    """
    Calcula score de una configuración.

    Score = Suma de expansión lograda - Penalizaciones
    """
    expansion_total = 0
    gaps_problematicos_nuevos = 0
    movimiento_total = sum(abs(s) for s in shifts)

    for i in range(len(nuevos_tiempos) - 1):
        gap_original = tiempos_base[i+1] - tiempos_base[i]
        gap_nuevo = nuevos_tiempos[i+1] - nuevos_tiempos[i]

        # Si gap original era problemático
        if min_gap <= gap_original <= max_gap:
            if gap_nuevo > max_gap:
                # Expansión lograda
                expansion_total += (gap_nuevo - max_gap)
            elif gap_nuevo < min_gap:
                # Se comprimió (no queremos)
                return -999999
            else:
                # Sigue en rango problemático
                gaps_problematicos_nuevos += 1

        # Si gap nuevo es problemático (creado)
        elif min_gap <= gap_nuevo <= max_gap:
            gaps_problematicos_nuevos += 1

    # Penalizar gaps problemáticos
    if gaps_problematicos_nuevos > 0:
        return -999999

    # Score = expansión total - movimiento (preferir menos movimiento)
    return expansion_total * 1000 - movimiento_total
```

---

## Optimización con Búsqueda Limitada

Si `3^n` es demasiado (ej: 10 trips = 59,049 combinaciones):

### Enfoque Greedy Mejorado

```python
def _find_optimal_expand_greedy(self, trips, max_shift, min_gap, max_gap):
    """
    Algoritmo greedy: expande iterativamente buscando mejora local.
    """
    n = len(trips)
    tiempos = [self._time_to_minutes(t.pick_up_time) for t in trips]
    shifts = [0] * n  # Inicializar sin shifts

    mejorando = True
    iteraciones = 0

    while mejorando and iteraciones < 10:
        mejorando = False
        iteraciones += 1

        # Para cada trip, probar shifts
        for i in range(n):
            mejor_shift_local = shifts[i]
            mejor_score_local = self._score_expand_config(
                tiempos, [t + s for t, s in zip(tiempos, shifts)],
                shifts, min_gap, max_gap
            )

            # Probar -max_shift, 0, +max_shift
            for shift_candidato in [-max_shift, 0, +max_shift]:
                shifts_test = shifts.copy()
                shifts_test[i] = shift_candidato

                nuevos_tiempos = [t + s for t, s in zip(tiempos, shifts_test)]
                score = self._score_expand_config(
                    tiempos, nuevos_tiempos, shifts_test, min_gap, max_gap
                )

                if score > mejor_score_local:
                    mejor_score_local = score
                    mejor_shift_local = shift_candidato
                    mejorando = True

            shifts[i] = mejor_shift_local

    return [(trips[i], shifts[i]) for i in range(n)]
```

**Complejidad**: O(n × k × iteraciones) donde k=3 (opciones de shift)

---

## Tu Propuesta Específica

### Entiendo Tu Algoritmo Así:

```
Trips: A, B, C, D
max_shift = 10

Estrategias a probar:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Máxima expansión extremos:
   A: -10, B: 0, C: +10, D: +10

2. Máxima expansión todos:
   A: -10, B: -10, C: +10, D: +10

3. Expansión gradual:
   A: -10, B: -5, C: +5, D: +10

4. Solo mitad:
   A: -5, B: 0, C: +5, D: +5

... etc
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Para cada estrategia:
  1. Calcular gaps resultantes
  2. Validar que NO crea choques (gaps < min_gap)
  3. Calcular % de expansión lograda
  4. Seleccionar la estrategia con mayor %
```

### Métrica: Porcentaje de Expansión

```python
def calcular_porcentaje_expansion(tiempos_base, nuevos_tiempos, min_gap, max_gap):
    """
    % Expansión = (minutos expandidos / minutos máximos posibles) × 100
    """
    # Minutos de expansión lograda
    expansion_lograda = 0
    for i in range(len(nuevos_tiempos) - 1):
        gap_original = tiempos_base[i+1] - tiempos_base[i]
        gap_nuevo = nuevos_tiempos[i+1] - nuevos_tiempos[i]

        if min_gap <= gap_original <= max_gap:
            # Cuánto se expandió
            if gap_nuevo > max_gap:
                expansion_lograda += (gap_nuevo - max_gap)

    # Máxima expansión teórica
    # Si todos los gaps se pudieran expandir al infinito
    expansion_maxima = 0
    for i in range(len(tiempos_base) - 1):
        gap_original = tiempos_base[i+1] - tiempos_base[i]
        if min_gap <= gap_original <= max_gap:
            # Máximo posible = (shift_i+1 máximo) + (shift_i máximo)
            expansion_maxima += (max_shift * 2)

    if expansion_maxima == 0:
        return 0

    return (expansion_lograda / expansion_maxima) * 100
```

---

## Ejemplo Completo

### Input

```
Trips: A, B, C, D
Tiempos: [04:55, 05:20, 05:45, 06:10]
Gaps originales: [25, 25, 25] (todos problemáticos)
max_shift = 10
min_gap = 20
max_gap = 35
```

### Estrategias a Probar

#### Estrategia 1: Máxima extremos

```
Shifts: [-10, 0, +10, +10]

Nuevos tiempos: [04:45, 05:20, 05:55, 06:20]
Gaps nuevos: [35, 35, 25]

Gaps fuera de rango: 2 (A-B, B-C)
Gaps problemáticos: 1 (C-D = 25)

Score: -999999 (penalizado por gap problemático)
```

#### Estrategia 2: Expansión balanceada

```
Shifts: [-10, -5, +5, +10]

Nuevos tiempos: [04:45, 05:15, 05:50, 06:20]
Gaps nuevos: [30, 35, 30]

Gaps fuera de rango: 3 (todos!)
Gaps problemáticos: 0 ✅

Expansión lograda:
  A-B: 25 → 30 = +5
  B-C: 25 → 35 = +10
  C-D: 25 → 30 = +5
  Total: 20 minutos

Expansión máxima teórica: 3 gaps × 20 min = 60 min
% Expansión: (20 / 60) × 100 = 33%

Score: 20,000 - 30 = 19,970 ✅
```

#### Estrategia 3: Máxima todos

```
Shifts: [-10, -10, +10, +10]

Nuevos tiempos: [04:45, 05:10, 05:55, 06:20]
Gaps nuevos: [25, 45, 25]

Gaps problemáticos: 2 (A-B, C-D)

Score: -999999 (penalizado)
```

### Resultado

**Estrategia 2 gana** con score 19,970 (33% de expansión sin gaps problemáticos).

---

## Algoritmo Optimizado: Beam Search

Para evitar probar 3^n combinaciones, usar **Beam Search**:

```python
def _expand_beam_search(self, trips, max_shift, min_gap, max_gap, beam_width=5):
    """
    Beam search: mantén solo las mejores K configuraciones en cada paso.
    """
    n = len(trips)
    tiempos_base = [self._time_to_minutes(t.pick_up_time) for t in trips]

    # Estado inicial: sin shifts
    beam = [([0] * n, 0)]  # (shifts, score)

    for trip_idx in range(n):
        nuevos_candidatos = []

        for config_actual, _ in beam:
            # Probar 3 opciones para este trip
            for shift in [-max_shift, 0, +max_shift]:
                nueva_config = config_actual.copy()
                nueva_config[trip_idx] = shift

                # Calcular score
                nuevos_tiempos = [t + s for t, s in zip(tiempos_base, nueva_config)]
                score = self._score_expand_config(
                    tiempos_base, nuevos_tiempos, nueva_config, min_gap, max_gap
                )

                nuevos_candidatos.append((nueva_config, score))

        # Mantener solo los mejores beam_width
        nuevos_candidatos.sort(key=lambda x: x[1], reverse=True)
        beam = nuevos_candidatos[:beam_width]

    # Retornar mejor configuración final
    mejor_config, mejor_score = beam[0]
    return [(trips[i], mejor_config[i]) for i in range(n)]
```

**Complejidad**: O(n × beam_width × 3) = O(n) con beam_width constante

---

## Comparación de Enfoques

| Enfoque | Complejidad | Garantía Óptimo | Implementación |
|---------|-------------|-----------------|----------------|
| Búsqueda Exhaustiva | O(3^n) | ✅ Sí | Simple pero lento |
| Greedy Iterativo | O(n × k × iter) | ❌ No | Moderado |
| Beam Search | O(n × beam × k) | ⚠️ Casi óptimo | Moderado |
| Tu código viejo | O(n^2) | ❌ No | Simple |

---

## Pregunta para Ti

Entiendo tu propuesta. Quieres un algoritmo que:

1. ✅ Pruebe diferentes combinaciones de shifts
2. ✅ Calcule la expansión total de cada combinación
3. ✅ Elija la que maximice expansión SIN dejar gaps problemáticos
4. ✅ Se aplique solo a Expand (no afecta Reduce ni Combine)

**Mis preguntas:**

### 1. ¿Cuántos trips típicamente hay por día?
- Si son <10 trips: Búsqueda exhaustiva es viable (3^10 = 59,049)
- Si son >10 trips: Necesitamos Beam Search o Greedy

### 2. ¿Qué define "choque"?
- ¿Gap < min_gap? (ej: gap < 20)
- ¿Gap dentro del rango [min_gap, max_gap]? (ej: 20-35)

### 3. ¿Cómo mides "expansión máxima"?
- ¿Suma de minutos expandidos?
- ¿Porcentaje de expansión lograda?
- ¿Número de gaps que salieron del rango problemático?

### 4. ¿Validación de neighbors?
Como en tu código viejo, ¿debemos validar que NO se creen gaps problemáticos con trips fuera de la secuencia?

---

**¿Quieres que implemente esto? ¿Con qué enfoque?**

- **A)** Búsqueda Exhaustiva (simple, garantiza óptimo, lento si >10 trips)
- **B)** Beam Search (balance complejidad/calidad, rápido)
- **C)** Greedy Iterativo (muy rápido, puede no ser óptimo)