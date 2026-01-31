# Casos Extremos y Reglas Completas de Filtros Ground

## 🎯 Resumen: Por qué un trip NO recibe un filtro

Existen **7 categorías de condiciones** que pueden hacer que un trip NO sea modificado por Combine o Expand, incluso si parece cumplir los criterios básicos.

---

## Categoría 1: Reglas de Prioridad (Mutua Exclusión)

### 1.1 Combine bloqueado por Expand

**Condición**: Si un trip ya tiene `expand_applied=true`, Combine lo SALTA.

**Código** ([step_filter_service.py:550-567](../features/trips/services/step_filter_service.py#L550-L567)):
```python
# En _apply_combine()
if trip_a.expand_applied or trip_b.expand_applied:
    logger.info(f"[PRIORITY_RULE] Combine skipping pair")
    self._record_exclusion(...)
    i += 1
    continue  # SALTA el par completamente
```

**Ejemplo**:
```
Step 1: Expand applied → trip_a.expand_applied = true
Step 2: Combine intenta procesar trip_a + trip_b
        → Ve expand_applied=true
        → SALTA el par
        → Combine NO se aplica
```

### 1.2 Expand bloqueado por Combine

**Condición**: Si un trip ya tiene `combine_applied=true`, Expand lo FILTRA completamente.

**Código** ([step_filter_service.py:633-637](../features/trips/services/step_filter_service.py#L633-L637)):
```python
# En _apply_expand()
# PRIORITY RULE: Filter out trips blocked by Combine
available_trips = [
    t for t in sorted_trips
    if not t.combine_applied  # FILTRA trips con Combine
]
```

**Ejemplo**:
```
Step 1: Combine applied → trip_a.combine_applied = true
Step 2: Expand busca cadenas
        → FILTRA trip_a de la lista available_trips
        → trip_a no entra en ninguna cadena
        → Expand NO se aplica a trip_a
```

**Resultado**: El PRIMER filtro aplicado SIEMPRE GANA en trips donde hay conflicto.

---

## Categoría 2: Reglas de Ubicación (Location Matching)

### 2.1 Combine requiere pickup y dropoff idénticos

**Condición**: Ambos trips del par DEBEN tener exactamente el mismo `pick_up_location` Y `drop_off_location`.

**Código** ([step_filter_service.py:570-578](../features/trips/services/step_filter_service.py#L570-L578)):
```python
# PUNTO 9: Combine requiere pickup y dropoff idénticos
if (trip_a.pick_up_location != trip_b.pick_up_location or
    trip_a.drop_off_location != trip_b.drop_off_location):
    logger.debug(f"[STEP_FILTER] Skipping Combine: location mismatch")
    i += 1
    continue  # SALTA el par
```

**Ejemplo**:
```
Trip A: { pickup: "Hotel Marriott", dropoff: "Airport LAX" }
Trip B: { pickup: "Hotel Hilton",   dropoff: "Airport LAX" }
        → pickup diferente
        → Combine SALTA el par A-B
```

### 2.2 Expand agrupa por pickup y dropoff idénticos

**Condición**: Expand SOLO forma cadenas con trips que tienen el mismo `pick_up_location` Y `drop_off_location`.

**Código** ([step_filter_service.py:642-652](../features/trips/services/step_filter_service.py#L642-L652)):
```python
# Group by location (pickup_location, drop_off_location)
location_groups = defaultdict(list)
for trip in available_trips:
    key = (trip.pick_up_location, trip.drop_off_location)
    location_groups[key].append(trip)

# Process each location group independently
for (pickup_loc, dropoff_loc), group_trips in location_groups.items():
    if len(group_trips) < 2:
        continue  # Skip if less than 2 trips in this location group
```

**Ejemplo**:
```
Trip A: { pickup: "Hotel Marriott", dropoff: "Airport LAX", time: "04:00" }
Trip B: { pickup: "Hotel Marriott", dropoff: "Airport LAX", time: "04:15" }
Trip C: { pickup: "Hotel Hilton",   dropoff: "Airport LAX", time: "04:30" }

Location groups:
- ("Hotel Marriott", "Airport LAX"): [A, B]  → Puede formar cadena
- ("Hotel Hilton", "Airport LAX"):   [C]     → Solo 1 trip, EXCLUIDO
```

**Resultado**: Trips con diferentes locations NO pueden formar pares (Combine) ni cadenas (Expand).

---

## Categoría 3: Reglas de Gap (Separación de Tiempos)

### 3.1 Combine: Gap debe estar dentro del rango [min_gap, max_gap]

**Condición**: El gap entre dos trips DEBE estar entre `window.min_gap` y `window.max_gap` (inclusive).

**Código** ([step_filter_service.py:583-596](../features/trips/services/step_filter_service.py#L583-L596)):
```python
gap = self._minutes_between(time_a, time_b)

if window.min_gap <= gap <= window.max_gap:
    # Aplica Combine
    midpoint = self._calculate_midpoint(time_a, time_b)
    self._record_change(trip_a, time_a, midpoint, "combine")
    self._record_change(trip_b, time_b, midpoint, "combine")
else:
    i += 1  # SALTA el par (gap fuera del rango)
```

**Ejemplo**:
```
Configuración: min_gap=10, max_gap=30

Trip A: 04:00
Trip B: 04:05  → gap=5  → ❌ Menor que min_gap → NO se aplica
Trip C: 04:20  → gap=15 → ✅ Dentro del rango → SÍ se aplica
Trip D: 05:00  → gap=40 → ❌ Mayor que max_gap → NO se aplica
```

### 3.2 Expand: Gap debe ser ≤ (max_gap - 1) para formar cadena

**Condición CRÍTICA**: Para que dos trips consecutivos estén en la MISMA cadena, el gap DEBE ser ≤ `max_gap - 1`.

**Código** ([step_filter_service.py:713-728](../features/trips/services/step_filter_service.py#L713-L728)):
```python
threshold = max_gap
chains = []
current_chain = [trips[0]]

for i in range(1, len(trips)):
    prev_time = self._get_effective_time(trips[i-1])
    curr_time = self._get_effective_time(trips[i])
    gap = self._minutes_between(prev_time, curr_time)

    if gap <= threshold - 1:  # ⚠️ NOTA: max_gap - 1
        current_chain.append(trips[i])  # Misma cadena
    else:
        # Gap grande → nueva cadena
        if len(current_chain) >= 2:
            chains.append(current_chain)
        current_chain = [trips[i]]
```

**Ejemplo**:
```
Configuración: max_gap=15

Trip A: 04:00
Trip B: 04:14  → gap=14 → ≤ (15-1)=14 → ✅ Misma cadena
Trip C: 04:29  → gap=15 → > (15-1)=14 → ❌ Nueva cadena

Resultado:
- Cadena 1: [A, B]  → Aplica patrón [-max, +max]
- Cadena 2: [C]     → Solo 1 trip, EXCLUIDO (mínimo 2)
```

**⚠️ DIFERENCIA CRÍTICA**:
- **Combine**: `min_gap <= gap <= max_gap` (rango inclusivo en ambos lados)
- **Expand**: `gap <= max_gap - 1` (threshold con -1)

---

## Categoría 4: Reglas de Tamaño de Cadena (Expand)

### 4.1 Cadena debe tener MÍNIMO 2 trips

**Condición**: Expand SOLO aplica a cadenas de 2 o más trips.

**Código** ([step_filter_service.py:726-732](../features/trips/services/step_filter_service.py#L726-L732)):
```python
# Al finalizar identificación de cadenas
if len(current_chain) >= 2:
    chains.append(current_chain)
# Si current_chain tiene solo 1 trip, se descarta (no se agrega)
```

**Ejemplo**:
```
Trips: A (04:00), B (04:50), C (05:00)
max_gap: 15

Gap A-B = 50 → > (15-1) → Nueva cadena
Gap B-C = 10 → ≤ (15-1) → Misma cadena

Resultado:
- Cadena 1: [A]     → Solo 1 trip → ❌ EXCLUIDO
- Cadena 2: [B, C]  → 2 trips → ✅ Aplica patrón [-max, +max]
```

### 4.2 Cadena debe tener MÁXIMO 6 trips

**Condición**: Cadenas de 7+ trips son EXCLUIDAS automáticamente.

**Código** ([step_filter_service.py:749-752](../features/trips/services/step_filter_service.py#L749-L752)):
```python
def _get_expand_pattern(self, chain_length: int, max_shift: int):
    if chain_length < 2:
        return None
    elif chain_length > 6:
        return None  # ⚠️ Cadenas de 7+ trips son muy largas
```

**Código de exclusión** ([step_filter_service.py:665-679](../features/trips/services/step_filter_service.py#L665-L679)):
```python
pattern = self._get_expand_pattern(len(chain), window.max_shift)

if pattern is None:
    # Chain of 7+ trips → EXCLUDE
    self._record_exclusion(
        f"expand_chain({len(chain)} trips)",
        [t.id for t in chain],
        f"Chain of {len(chain)} trips exceeds maximum allowed (max 6 trips)",
        0, 0,
        trips=chain,
    )
    logger.info(f"[EXPAND_CHAIN] Excluded chain of {len(chain)} trips")
    continue
```

**Ejemplo**:
```
Cadena: [A, B, C, D, E, F, G, H]  (8 trips)
        → len(chain) = 8 > 6
        → pattern = None
        → Cadena completa EXCLUIDA
        → NINGUNO de los 8 trips recibe Expand
```

**Patrones soportados**:
- 2 trips: `[-max, +max]`
- 3 trips: `[-max, 0, +max]`
- 4 trips: `[-max, -max/2, +max/2, +max]`
- 5 trips: `[-max, -max/2, 0, +max/2, +max]`
- 6 trips: `[-max, -max/2, -max/4, +max/4, +max/2, +max]`
- 7+ trips: ❌ **EXCLUIDO**

---

## Categoría 5: Reglas de Ventana de Tiempo (Time Window)

### 5.1 Trip debe estar dentro de la ventana de tiempo

**Condición**: El tiempo del trip (efectivo) DEBE estar en el rango `[window.start, window.end)`.

**Código** ([step_filter_service.py:1059-1063](../features/trips/services/step_filter_service.py#L1059-L1063)):
```python
def _is_time_in_window(self, t: time, window: TimeWindow) -> bool:
    """Check if time is within a specific window."""
    start = self._parse_time_str(window.start)
    end = self._parse_time_str(window.end)
    return start <= t < end  # ⚠️ Nota: end es EXCLUSIVO
```

**Ejemplo**:
```
Window: start="05:00", end="10:00"

Trip A: 04:59  → ❌ < start → Fuera de ventana
Trip B: 05:00  → ✅ >= start → Dentro de ventana
Trip C: 09:59  → ✅ < end → Dentro de ventana
Trip D: 10:00  → ❌ >= end → Fuera de ventana
```

**Aplicación en Combine y Expand**:

```python
# Combine (línea 524-531)
window_trips = [
    t for t in filtered_trips
    if self._is_time_in_window(
        self._get_effective_time(t),
        window
    )
]
# Solo procesa trips dentro de la ventana

# Expand (línea 618-625)
window_trips = [
    t for t in filtered_trips
    if self._is_time_in_window(
        self._get_effective_time(t),
        window
    )
]
# Solo procesa trips dentro de la ventana
```

### 5.2 Ventana debe estar habilitada

**Condición**: `window.enabled` debe ser `true` y tener configuración válida.

**Código Combine** ([step_filter_service.py:517-519](../features/trips/services/step_filter_service.py#L517-L519)):
```python
# Skip window if disabled or no config
if not window.enabled or window.min_gap is None or window.max_gap is None:
    continue  # SALTA esta ventana completamente
```

**Código Expand** ([step_filter_service.py:610-613](../features/trips/services/step_filter_service.py#L610-L613)):
```python
# Skip window if disabled or no config
if (not window.enabled or window.min_gap is None or
    window.max_gap is None or window.max_shift is None):
    continue  # SALTA esta ventana completamente
```

---

## Categoría 6: Reglas de Hotel (Filtrado Opcional)

### 6.1 Trip debe estar en la lista de hoteles (si se especifica)

**Condición**: Si `window.hotel_names` está definido, el trip DEBE tener su `pick_up_location` en esa lista.

**Código** ([step_filter_service.py:1007-1020](../features/trips/services/step_filter_service.py#L1007-L1020)):
```python
def _filter_by_hotel(
    self,
    trips: list[Trip],
    hotel_names: Optional[list[str]],
) -> list[Trip]:
    """Filter trips by hotel names (per-window version)."""
    if not hotel_names:
        return trips  # Sin filtro, todos los trips pasan

    hotel_set = set(h.lower() for h in hotel_names)
    return [
        t for t in trips
        if t.pick_up_location and t.pick_up_location.lower() in hotel_set
    ]
```

**Ejemplo**:
```
Window: hotel_names=["Marriott", "Hilton"]

Trip A: pick_up_location="Marriott Riverside"  → ✅ Pasa filtro
Trip B: pick_up_location="Hilton Garden Inn"   → ✅ Pasa filtro
Trip C: pick_up_location="Mission Inn Hotel"   → ❌ FILTRADO
```

**Nota**: La comparación es case-insensitive y usa `in` (substring match).

---

## Categoría 7: Reglas de Estado Interno (Rule A)

### 7.1 Un trip solo puede ser modificado UNA VEZ dentro del mismo step

**Condición**: Dentro de un MISMO step de Combine, un trip solo puede ser modificado una vez.

**Código** ([step_filter_service.py:544-548](../features/trips/services/step_filter_service.py#L544-L548)):
```python
# Rule A check
if (trip_a.id in self.modified_by_combine_expand or
    trip_b.id in self.modified_by_combine_expand):
    i += 1
    continue  # SALTA este par
```

**Ejemplo**:
```
Trips: A (04:00), B (04:15), C (04:30)
Gap A-B = 15, Gap B-C = 15 (ambos válidos)

Procesamiento:
1. Combine procesa A-B → Mueve a 04:07
   → Marca A y B en modified_by_combine_expand
2. Combine intenta procesar B-C
   → Ve que B está en modified_by_combine_expand
   → SALTA el par B-C (Rule A)

Resultado: Solo A-B se combinan, B-C NO
```

**Razón**: Evitar modificar el mismo trip múltiples veces en un solo paso.

### 7.2 Trips ya procesados en una ventana anterior (Reduce)

**Condición**: En Reduce, si un trip ya fue procesado en una ventana previa, se SALTA en ventanas posteriores.

**Código Reduce** ([step_filter_service.py:474-487](../features/trips/services/step_filter_service.py#L474-L487)):
```python
processed_trips = set()

for window in config.windows:
    # ...
    for trip in filtered_trips:
        # Skip if already processed in a previous window
        if trip.id in processed_trips:
            continue

        # ... apply reduce

        processed_trips.add(trip.id)
```

**Ejemplo**:
```
Window 1: start=00:00, end=06:00, reduce=15
Window 2: start=04:00, end=10:00, reduce=20

Trip A: 05:00
        → Está en Window 1 → Reduce -15 → 04:45
        → Marcado en processed_trips
        → Aunque también está en Window 2, se SALTA
        → Solo se aplica Window 1
```

---

## Categoría 8: Reglas de Tiempo Válido (Reduce)

### 8.1 El tiempo resultante debe estar en [00:00, 24:00)

**Condición**: Reduce NO se aplica si el tiempo resultante saldría del día.

**Código** ([step_filter_service.py:496-503](../features/trips/services/step_filter_service.py#L496-L503)):
```python
try:
    new_time = self._subtract_minutes(base_time, window.minutes_to_reduce)
except ValueError as e:
    # Time would go outside day - skip this trip
    logger.debug(
        f"[STEP_FILTER] Skipping Reduce for trip {trip.id}: {e}"
    )
    continue
```

**Ejemplo**:
```
Trip A: 00:05 (5 minutos después de medianoche)
Reduce: -15 minutos
Resultado: 00:05 - 15 = -00:10 (negativo!)
        → ValueError
        → Reduce NO se aplica a este trip
```

---

## 📊 Tabla Resumen: Condiciones que BLOQUEAN filtros

| # | Condición | Combine | Expand | Reduce |
|---|-----------|---------|--------|--------|
| **1** | Otro filtro ya aplicado | ❌ Si `expand_applied=true` | ❌ Si `combine_applied=true` | ✅ N/A |
| **2** | Locations diferentes | ❌ Requiere match exacto | ❌ Solo agrupa matches | ✅ N/A |
| **3** | Gap fuera de rango | ❌ `gap < min_gap` o `gap > max_gap` | ❌ `gap > max_gap - 1` para cadena | ✅ N/A |
| **4** | Cadena muy corta | ✅ N/A | ❌ Cadena < 2 trips | ✅ N/A |
| **5** | Cadena muy larga | ✅ N/A | ❌ Cadena > 6 trips | ✅ N/A |
| **6** | Fuera de ventana de tiempo | ❌ `time < start` o `time >= end` | ❌ `time < start` or `time >= end` | ❌ `time < start` o `time >= end` |
| **7** | Ventana deshabilitada | ❌ `enabled=false` o config incompleta | ❌ `enabled=false` o config incompleta | ❌ `enabled=false` o config incompleta |
| **8** | Hotel no coincide | ❌ Si `hotel_names` especificado | ❌ Si `hotel_names` especificado | ❌ Si `hotel_names` especificado |
| **9** | Ya modificado en este step | ❌ Rule A | ✅ N/A | ✅ N/A |
| **10** | Ya procesado en ventana previa | ✅ N/A | ✅ N/A | ❌ Skip processed |
| **11** | Tiempo resultante inválido | ✅ N/A | ✅ N/A | ❌ Si < 00:00 |

---

## 🔍 Diagnóstico: ¿Por qué AMBOS se dejan de aplicar?

Si ves que NINGUNO de los dos filtros (Combine ni Expand) se aplica a ciertos trips, verifica:

### Checklist de Diagnóstico:

1. **Locations diferentes** ✓
   - ¿Los trips tienen EXACTAMENTE el mismo `pick_up_location` Y `drop_off_location`?
   - Usa logs: `[STEP_FILTER] Skipping Combine: location mismatch`

2. **Gap fuera de rango** ✓
   - Combine: ¿El gap está entre `[min_gap, max_gap]`?
   - Expand: ¿El gap es ≤ `max_gap - 1`?
   - Ejemplo: Si `max_gap=15`, un gap de 15 es válido para Combine pero NO para Expand

3. **Fuera de ventana de tiempo** ✓
   - ¿Los trips están dentro de `[window.start, window.end)`?
   - Recuerda: `end` es EXCLUSIVO

4. **Cadena muy larga (Expand)** ✓
   - Si hay 7+ trips consecutivos con gaps pequeños, Expand EXCLUYE la cadena completa
   - Usa logs: `[EXPAND_CHAIN] Excluded chain of 8 trips`

5. **Cadena demasiado corta (Expand)** ✓
   - Si solo hay 1 trip en un grupo de location, Expand no puede formar cadena

6. **Hotel filtering** ✓
   - ¿Hay `hotel_names` configurado que esté filtrando estos trips?

7. **Ventana deshabilitada o config incompleta** ✓
   - ¿`window.enabled=true`?
   - ¿Todos los parámetros necesarios están configurados? (min_gap, max_gap, max_shift)

8. **Revert reciente** ✓
   - Si acabas de revertir un step, verifica que los flags se resetearon correctamente

---

## 💡 Casos Extremos Específicos

### Caso 1: Gap = max_gap exacto

```
Configuración:
- Combine: min_gap=10, max_gap=15
- Expand: max_gap=15

Trip A: 04:00
Trip B: 04:15  (gap = 15)

Resultado:
- Combine: ✅ 15 está en [10, 15] → SÍ se aplica
- Expand: ❌ 15 > (15-1)=14 → NO forman cadena
```

### Caso 2: 7 trips consecutivos con gaps pequeños

```
Trips: A, B, C, D, E, F, G (todos con gaps de 10 min)
max_gap: 15

Resultado:
- Cadena: [A, B, C, D, E, F, G] (7 trips)
- len(chain) = 7 > 6
- Expand EXCLUYE la cadena completa
- NINGUNO de los 7 trips recibe Expand
```

### Caso 3: Locations case-sensitive

```
Trip A: pick_up_location="Hotel Marriott"
Trip B: pick_up_location="hotel marriott"  (lowercase)

Resultado:
- Son diferentes strings
- NO forman par para Combine
- NO forman cadena para Expand
```

**Nota**: El filtro de hotel SÍ es case-insensitive, pero la comparación de locations NO lo es.

### Caso 4: End time exclusivo

```
Window: start="05:00", end="06:00"

Trip A: 05:59:59  → ✅ Dentro
Trip B: 06:00:00  → ❌ Fuera (end es exclusivo)
```

---

## 📝 Recomendaciones para el Frontend

1. **Mostrar exclusiones**: El backend retorna `StepResult.exclusions[]` con todas las operaciones que fueron excluidas y sus razones.

2. **Verificar logs**: Los logs contienen información detallada sobre por qué cada operación fue saltada.

3. **Tooltips explicativos**: Cuando un trip NO tiene filtro aplicado, mostrar tooltip explicando por qué:
   - "Gap demasiado grande (20 min > max 15 min)"
   - "Cadena muy larga (8 trips > máximo 6)"
   - "Location diferente a otros trips"

4. **Validación de configuración**: Antes de aplicar, validar que:
   - `min_gap < max_gap` para Combine
   - `max_gap - 1 >= 1` para Expand (mínimo gap de 1 para cadena)

---

**Última actualización**: 2026-01-31
