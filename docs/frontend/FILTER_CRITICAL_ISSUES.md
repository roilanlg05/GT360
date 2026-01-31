# Análisis Crítico: Problemas y Comportamientos Inesperados entre Combine y Expand

## 🚨 Issues Críticos Detectados

---

## Issue #1: Inconsistencia en Threshold de Gap

### ⚠️ CRÍTICO: Diferente interpretación de `max_gap`

**Problema**:
- **Combine** usa: `min_gap <= gap <= max_gap` (inclusivo)
- **Expand** usa: `gap <= max_gap - 1` (threshold con -1)

**Impacto**: Si configuras ambos filtros con el mismo `max_gap`, tienen comportamientos DIFERENTES para gaps en el límite.

### Ejemplo del Problema:

```typescript
// Configuración
const config = {
  min_gap: 10,
  max_gap: 15,  // ⚠️ MISMO max_gap para ambos
  max_shift: 10
};

// Trips
Trip A: 04:00
Trip B: 04:15  // gap = 15 minutos
```

**Resultado**:
- **Combine**: ✅ `15 <= 15` → **SÍ se aplica** (gap válido)
- **Expand**: ❌ `15 > 14` → **NO forma cadena** (gap demasiado grande)

### Comportamiento Inesperado:

Si aplicas **Combine primero**:
1. Combine ve gap=15 → Válido → Aplica → `combine_applied=true`
2. Expand ve `combine_applied=true` → Filtra estos trips → NO se aplica

Si aplicas **Expand primero**:
1. Expand ve gap=15 → ❌ `15 > (max_gap-1)` → NO forma cadena → NO se aplica
2. Combine ve gap=15 → ✅ Válido → Aplica → `combine_applied=true`

**Resultado**: El orden de aplicación cambia el resultado final!

### Caso Extremo:

```typescript
// 3 trips consecutivos
Trip A: 04:00
Trip B: 04:15  // gap A-B = 15
Trip C: 04:30  // gap B-C = 15

// max_gap = 15

// Expand SOLO:
// - Gap A-B = 15 > 14 → No misma cadena
// - Gap B-C = 15 > 14 → No misma cadena
// - Resultado: Tres cadenas de 1 trip cada una
// - NINGUNO recibe Expand (mínimo 2 trips por cadena)

// Combine SOLO:
// - Gap A-B = 15 ≤ 15 → ✅ Combina A-B
// - Gap B-C = 15 ≤ 15 → ✅ Combina B-C (pero Rule A lo bloquea)
// - Resultado: Solo A-B se combinan
```

### 🔧 Solución Recomendada:

**Opción 1**: Documentar claramente la diferencia
- Expand necesita `max_gap` configurado 1 minuto MÁS alto que Combine
- Ejemplo: Si quieres gap de 15 para ambos → Combine: max_gap=15, Expand: max_gap=16

**Opción 2**: Cambiar el código de Expand
```python
# Actual (problemático):
if gap <= threshold - 1:

# Sugerido (consistente):
if gap <= threshold:
```

**Opción 3**: Crear configuraciones separadas
- `max_gap_combine` y `max_gap_expand` como parámetros distintos

---

## Issue #2: Cadenas Largas Completamente Excluidas

### ⚠️ CRÍTICO: All-or-nothing para cadenas de 7+ trips

**Problema**: Si se forma una cadena de 7+ trips, **TODOS** son excluidos de Expand, incluso si podrías dividir la cadena.

### Ejemplo del Problema:

```typescript
// 8 trips consecutivos con gaps de 10 minutos
Trip A: 04:00
Trip B: 04:10  // gap=10
Trip C: 04:20  // gap=10
Trip D: 04:30  // gap=10
Trip E: 04:40  // gap=10
Trip F: 04:50  // gap=10
Trip G: 05:00  // gap=10
Trip H: 05:10  // gap=10

// max_gap = 15
```

**Comportamiento Actual**:
- Expand identifica cadena: [A, B, C, D, E, F, G, H]
- len(chain) = 8 > 6
- **EXCLUYE TODOS** → Ninguno recibe Expand

**Comportamiento Esperado/Deseable**:
- Dividir en cadenas más pequeñas:
  - Cadena 1: [A, B, C, D, E, F] → Aplica patrón de 6
  - Cadena 2: [G, H] → Aplica patrón de 2
- O al menos aplicar a los primeros 6 trips

### Caso Real:

```
Aeropuerto ocupado en hora pico:
- 15 trips consecutivos cada 8 minutos (04:00 - 06:00)
- max_gap = 15

Resultado Actual: NINGUNO recibe Expand (cadena muy larga)
Resultado Deseable: Dividir en 3 cadenas de 5-6 trips cada una
```

### 🔧 Solución Recomendada:

**Opción 1**: Dividir cadenas largas automáticamente
```python
def _identify_expand_chains_smart(self, trips, max_gap, max_shift):
    # ... identificar cadenas

    smart_chains = []
    for chain in raw_chains:
        if len(chain) <= 6:
            smart_chains.append(chain)
        else:
            # Dividir cadena larga en sub-cadenas de máximo 6
            for i in range(0, len(chain), 6):
                sub_chain = chain[i:i+6]
                if len(sub_chain) >= 2:
                    smart_chains.append(sub_chain)

    return smart_chains
```

**Opción 2**: Configuración adicional
- Agregar `max_chain_length` como parámetro configurable
- Permitir que el usuario decida el máximo (default 6)

**Opción 3**: Aplicar a primeros N trips
- Si cadena > 6, aplicar solo a los primeros 6 trips
- Los demás quedan sin modificar

---

## Issue #3: Rule A crea comportamiento asimétrico

### ⚠️ MEDIO: Combine puede "bloquear" trips adicionales dentro del mismo step

**Problema**: Rule A impide que un trip sea combinado múltiples veces en el MISMO step, pero esto crea asimetría.

### Ejemplo del Problema:

```typescript
// Trips perfectamente espaciados
Trip A: 04:00
Trip B: 04:15  // gap A-B = 15
Trip C: 04:30  // gap B-C = 15
Trip D: 04:45  // gap C-D = 15

// min_gap=10, max_gap=30 (todos los gaps son válidos)
```

**Procesamiento Combine**:
1. Procesa A-B → Combina → Mueve a 04:07.5
2. Marca A y B en `modified_by_combine_expand`
3. Intenta procesar B-C → **Rule A**: B ya fue modificado → SALTA
4. Intenta procesar C-D → Combina → Mueve a 04:37.5

**Resultado**: A-B combinados, C-D combinados, pero B-C NO

**Problema**: El trip B "bloquea" la operación B-C aunque C estaba disponible.

### Comportamiento Esperado:

¿Debería ser:
- **Opción 1**: Solo A-B (primera operación válida, luego todo bloqueado)
- **Opción 2**: A-B y C-D (actual - permite "saltar" y seguir)
- **Opción 3**: Procesar NO consecutivamente (A-C, luego B-D si es válido)

### 🔧 Solución Recomendada:

**Documentar claramente** el comportamiento actual y por qué existe Rule A:
- Propósito: Evitar que un trip se mueva múltiples veces en un paso
- Efecto secundario: Puede dejar gaps "orfanos" entre trips combinados

---

## Issue #4: Case Sensitivity en Location Matching

### ⚠️ MEDIO: Inconsistencia entre hotel filtering y location matching

**Problema**:
- **Hotel filtering**: Case-INSENSITIVE (`hotel_set = set(h.lower() for h in hotel_names)`)
- **Location matching**: Case-SENSITIVE (`trip_a.pick_up_location != trip_b.pick_up_location`)

### Ejemplo del Problema:

```python
# Hotel filtering (case-insensitive)
hotel_names = ["Marriott"]
trip.pick_up_location = "marriott"  # lowercase
# ✅ Pasa el filtro (se convierte a lowercase)

# Location matching (case-sensitive)
trip_a.pick_up_location = "Marriott Riverside"
trip_b.pick_up_location = "marriott riverside"  # lowercase
# ❌ NO coinciden (comparación exacta)
# Combine SALTA el par, Expand NO los agrupa
```

**Comportamiento Inesperado**:
- Trips del mismo hotel PASAN el filtro
- Pero NO se combinan/expanden porque la comparación es case-sensitive

### 🔧 Solución Recomendada:

**Opción 1**: Hacer location matching case-insensitive
```python
if (trip_a.pick_up_location.lower() != trip_b.pick_up_location.lower() or
    trip_a.drop_off_location.lower() != trip_b.drop_off_location.lower()):
    # Skip
```

**Opción 2**: Normalizar datos en DB
- Almacenar locations en formato consistente (title case o lowercase)

---

## Issue #5: Window End Time Exclusivo puede causar confusion

### ⚠️ BAJO: Boundary behavior no intuitivo

**Problema**: `end` time es EXCLUSIVO (`start <= t < end`), lo cual puede ser no intuitivo.

### Ejemplo:

```python
window = { start: "05:00", end: "06:00" }

trip_at_5_59_59 = "05:59:59"  # ✅ Dentro
trip_at_6_00_00 = "06:00:00"  # ❌ Fuera

# Usuario podría esperar que 06:00 esté incluido
```

### 🔧 Solución Recomendada:

**Documentar claramente** que:
- `end` es exclusivo (como rangos de Python)
- Para incluir 06:00, configurar `end: "06:01"`

---

## Issue #6: Gap exacto en límite de threshold

### ⚠️ MEDIO: Comportamiento diferente entre Combine y Expand

**Problema**: Ya cubierto en Issue #1, pero merece énfasis especial.

### Tabla de Comparación:

| Gap (min) | max_gap=15 | Combine | Expand (threshold-1) |
|-----------|------------|---------|---------------------|
| 13 | ≤ 15 | ✅ Válido | ✅ Misma cadena |
| 14 | ≤ 15 | ✅ Válido | ✅ Misma cadena |
| **15** | **= 15** | **✅ Válido** | **❌ Nueva cadena** |
| 16 | > 15 | ❌ Inválido | ❌ Nueva cadena |

**Implicación**: Para gaps EXACTAMENTE en `max_gap`, Combine SÍ aplica pero Expand NO forma cadena.

---

## Issue #7: Falta de validación de configuración inconsistente

### ⚠️ MEDIO: No hay validación cross-filter

**Problema**: Puedes configurar Combine y Expand con parámetros que garantizan conflicto.

### Ejemplo:

```typescript
// Configuración problemática
const step1 = {
  filter_type: "combine",
  windows: [{
    min_gap: 5,
    max_gap: 20  // Combine acepta gaps hasta 20
  }]
};

const step2 = {
  filter_type: "expand",
  windows: [{
    max_gap: 10  // Expand solo forma cadenas con gaps ≤ 9
  }]
};

// Trips con gap=15
// - Combine: ✅ Válido (5 ≤ 15 ≤ 20)
// - Expand: ❌ Inválido (15 > 9)

// Si aplicas Combine primero, Expand NUNCA se aplicará a esos trips
```

### 🔧 Solución Recomendada:

**Validación en backend**:
```python
def validate_filter_compatibility(combine_config, expand_config):
    """Validar que configuraciones sean compatibles."""
    warnings = []

    if combine_config.max_gap != expand_config.max_gap + 1:
        warnings.append(
            f"Combine max_gap ({combine_config.max_gap}) y "
            f"Expand max_gap ({expand_config.max_gap}) tienen "
            f"interpretaciones diferentes. Para consistencia, "
            f"Expand debería ser {combine_config.max_gap - 1}"
        )

    return warnings
```

---

## Issue #8: Trips "Huérfanos" en Location Groups

### ⚠️ BAJO: Un solo trip en location group es excluido

**Problema**: Expand requiere mínimo 2 trips por location group.

### Ejemplo:

```typescript
// Trips
Trip A: { pickup: "Marriott", dropoff: "LAX", time: "04:00" }
Trip B: { pickup: "Marriott", dropoff: "LAX", time: "04:15" }
Trip C: { pickup: "Hilton",   dropoff: "LAX", time: "04:30" }

// Location groups:
// - ("Marriott", "LAX"): [A, B]  ✅ Forma cadena de 2
// - ("Hilton", "LAX"):   [C]     ❌ Solo 1 trip, excluido
```

**Resultado**: Trip C queda sin Expand aunque podría haber beneficio (ej. moverlo +10 min)

### 🔧 Solución Recomendada:

**Opción 1**: Permitir "cadenas de 1" con patrón especial
```python
if chain_length == 1:
    return [0]  # No shift (mantener como está)
```

**Opción 2**: Documentar que Expand solo funciona para grupos

---

## Issue #9: Revert puede causar "loss" temporal de estado

### ⚠️ MEDIO: Durante revert, hay un momento donde flags están incorrectos

**Problema**: Aunque el revert usa "single commit", hay un estado intermedio en memoria.

**Código relevante**:
```python
# Reset all trips to original
for trip in trips:
    trip.pick_up_time = trip.original_pick_up_time
    trip.reduce_applied = False      # ← Todos a false
    trip.combine_applied = False     # ← temporalmente
    trip.expand_applied = False      # ← antes de re-aplicar
```

**Implicación**: Si hay un error durante re-aplicación, los trips quedan en estado reset.

### 🔧 Solución Recomendada:

**Transacción explícita** con rollback en caso de error:
```python
async with self.session.begin_nested():  # Savepoint
    try:
        # Reset y re-aplicar
        await session.commit()
    except Exception as e:
        await session.rollback()  # Volver al estado anterior
        raise
```

---

## Issue #10: No hay forma de "preview revert"

### ⚠️ BAJO: UX issue - no puedes ver qué pasará antes de revertir

**Problema**: Solo existe `revert_step`, no `preview_revert_step`.

**Impacto**: Usuario no puede ver el estado resultante antes de confirmar revert.

### 🔧 Solución Recomendada:

Agregar endpoint `POST /filters/step/{id}/revert/preview`:
```python
async def preview_revert_step(step_id):
    """Muestra qué pasaría si revertieras este step."""
    # Simular revert sin commit
    # Retornar estado resultante
    return {
        "trips_affected": [...],
        "new_stack_state": [...],
        "preview_only": True
    }
```

---

## 📊 Resumen de Severidad

| Issue | Severidad | Impacto | Solución |
|-------|-----------|---------|----------|
| #1: Threshold inconsistente | 🚨 CRÍTICO | Resultados diferentes según orden | Documentar o cambiar código |
| #2: Cadenas largas excluidas | 🚨 CRÍTICO | Muchos trips sin filtro | Dividir cadenas automáticamente |
| #3: Rule A asimétrico | ⚠️ MEDIO | Gaps "orfanos" | Documentar comportamiento |
| #4: Case sensitivity | ⚠️ MEDIO | Trips mismo hotel no agrupan | Normalizar comparación |
| #5: End time exclusivo | ⚠️ BAJO | Confusión en boundary | Documentar claramente |
| #6: Gap exacto en límite | ⚠️ MEDIO | Duplicate de #1 | Ver #1 |
| #7: Falta validación | ⚠️ MEDIO | Configuraciones incompatibles | Agregar validación |
| #8: Trips huérfanos | ⚠️ BAJO | Trips individuales excluidos | Documentar o permitir cadenas de 1 |
| #9: Revert state loss | ⚠️ MEDIO | Error puede dejar inconsistencia | Usar savepoints |
| #10: No preview revert | ⚠️ BAJO | UX issue | Agregar endpoint preview |

---

## 🎯 Recomendaciones Prioritarias

### Prioridad 1 (Crítico):

1. **Resolver Issue #1**: Threshold inconsistente
   - **Acción inmediata**: Documentar claramente la diferencia
   - **Acción a largo plazo**: Cambiar código para consistencia

2. **Resolver Issue #2**: Cadenas largas excluidas
   - **Acción**: Implementar división automática de cadenas

### Prioridad 2 (Medio):

3. **Agregar validación de configuración** (Issue #7)
4. **Normalizar case sensitivity** (Issue #4)
5. **Mejorar manejo de errores en revert** (Issue #9)

### Prioridad 3 (Bajo):

6. **Documentar comportamientos edge case** (Issues #3, #5, #8)
7. **Agregar preview para revert** (Issue #10)

---

## 🔍 Tests Recomendados

Para cada issue, crear tests que verifiquen:

```python
# Test Issue #1: Threshold consistency
def test_gap_at_max_gap_boundary():
    """Verify Combine and Expand behave consistently at max_gap."""
    trips = create_trips_with_gap(15)  # gap = max_gap

    combine_result = apply_combine(trips, max_gap=15)
    expand_result = apply_expand(trips, max_gap=15)

    # Should both apply or both skip
    assert combine_result.applied == expand_result.applied

# Test Issue #2: Long chains
def test_long_chain_handling():
    """Verify chains of 7+ trips are handled gracefully."""
    trips = create_consecutive_trips(10)  # 10 trips

    result = apply_expand(trips, max_gap=15)

    # Should apply to some trips, not exclude all
    assert result.trips_modified > 0
    assert "excluded" not in [ex.reason for ex in result.exclusions]

# Test Issue #4: Case sensitivity
def test_location_case_insensitivity():
    """Verify location matching is case-insensitive."""
    trip_a = Trip(pick_up_location="Marriott")
    trip_b = Trip(pick_up_location="marriott")

    result = apply_combine([trip_a, trip_b])

    assert result.trips_modified == 2  # Should combine
```

---

**Última actualización**: 2026-01-31
**Status**: Issues identificados, pendiente resolución
