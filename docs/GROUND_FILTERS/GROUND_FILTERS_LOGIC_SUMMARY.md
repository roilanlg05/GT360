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
# step_filter_service.py
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
5. **NUEVO:** Ningún trip tiene `expand_applied=true` (Regla de Prioridad)

**Trabaja sobre:** `_get_effective_time()` que busca:
1. Primero: ¿Hay un cambio pendiente en `self.changes`? → usa ese
2. Si no: `trip.original_pick_up_time` o `trip.pick_up_time`

```python
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

**Condiciones para expandir:**
1. Gap entre trips está en rango `[min_gap, max_gap]`
2. Ningún trip fue modificado por Combine/Expand en este step (Rule A)
3. **NUEVO:** Ningún trip tiene `combine_applied=true` (Regla de Prioridad)

---

## Reglas de Anticolisión

### Rule A: "No Double-Modification in Single Step"

**Scope:** Dentro del MISMO step

**¿Qué hace?** Un trip modificado por Combine o Expand en UN step NO puede ser modificado otra vez en ese mismo step.

**Implementación:**
```python
self.modified_by_combine_expand: set[UUID] = set()  # Tracking

# En Combine/Expand:
if trip_a.id in self.modified_by_combine_expand:
    continue  # Skip
```

**Ejemplo:**
```
Combine Step:
- Iteración 1: Combina Trip A y Trip B → marca A y B
- Iteración 2: Intenta Trip B y Trip C → SKIP (B ya está marcado)
```

**Importante:** Este set se **limpia al inicio de cada operación nueva** (apply_step, preview_step, etc.).

---

### Regla de Prioridad Entre Combine y Expand (NUEVO 2026-01-28)

**Scope:** Entre DIFERENTES steps

#### Concepto

El primer filtro (Combine o Expand) que modifique un trip tiene prioridad absoluta.
El segundo filtro NO puede modificar ese trip.

#### Diseño

- **Tipo**: Bloqueo Total (si cualquier trip del par está bloqueado, skip el par completo)
- **Dirección**: Bidireccional (el primero en aplicarse por step_order gana)
- **Reduce**: NO participa en prioridad (es "base", se aplica siempre)
- **Alcance**: Global (no por ventana)

#### Implementación

```python
# En _apply_combine()
if trip_a.expand_applied or trip_b.expand_applied:
    logger.info("[PRIORITY_RULE] Combine skipping pair: Expand has priority")
    continue

# En _apply_expand()
if trip_a.combine_applied or trip_b.combine_applied:
    logger.info("[PRIORITY_RULE] Expand skipping pair: Combine has priority")
    continue
```

#### Ejemplos

**Ejemplo 1: Combine Primero**
```
Step 1: Apply Combine (min_gap=5, max_gap=15)
  - Modifica Trip A + Trip B → midpoint 08:15
  - A.combine_applied = True
  - B.combine_applied = True

Step 2: Apply Expand (min_gap=5, max_gap=15, max_shift=10)
  - Intenta par (A, C): SKIP (A tiene combine_applied=True)
  - Intenta par (B, D): SKIP (B tiene combine_applied=True)
  - Solo puede modificar trips sin combine_applied=True
```

**Ejemplo 2: Expand Primero**
```
Step 1: Apply Expand (max_shift=10)
  - Modifica Trip X + Trip Y
  - X.expand_applied = True
  - Y.expand_applied = True

Step 2: Apply Combine (min_gap=5, max_gap=15)
  - Intenta par (X, Z): SKIP (X tiene expand_applied=True)
  - Solo puede modificar trips sin expand_applied=True
```

#### Justificación

Esta regla reemplaza la antigua "Rule B: No-Collision Rule" que validaba gaps contra Combine activos. La nueva regla es más simple, predecible y performante:

- **Antes**: O(n × m × k) donde n=trips, m=combine steps, k=windows
- **Después**: O(1) por par (solo check de flags booleanos)

---

## Compatibilidad Entre Filtros

| Combinación | Permitido | Notas |
|-------------|-----------|-------|
| Reduce + Combine | ✅ SÍ | Combine usa tiempos ya reducidos |
| Reduce + Expand | ✅ SÍ | Expand usa tiempos ya reducidos |
| Combine + Expand (mismo día) | ⚠️ CON PRIORIDAD | El primero en aplicarse tiene prioridad absoluta |
| Reduce + Reduce | ❌ NO | Solo 1 Reduce por día |
| Combine + Combine | ❌ NO | Solo 1 Combine por día |
| Expand + Expand | ❌ NO | Solo 1 Expand por día |

---

## Performance de Regla de Prioridad

### Comparación con Rule B Antigua

| Métrica | Rule B (Antigua) | Regla de Prioridad (Nueva) |
|---------|------------------|---------------------------|
| Complejidad | O(n × m × k) | O(1) |
| Query a DB | Sí (active_combines) | No |
| Checks por par | ~10-50 | 2 (solo flags) |
| Claridad de logs | Baja ("collision") | Alta ("priority") |

### Impacto

- Reduce latencia de Expand en ~5-10ms por aplicación
- Simplifica debugging (mensajes más claros)
- Reduce carga en DB (sin query de active_combines)

---

## Cascada de Filtros

### Flujo Completo de Ejemplo

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESTADO INICIAL:
Trip A: pick_up_time=08:30
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1: Apply Reduce (minutes_to_reduce=10)
  Base: original_pick_up_time (NULL) → usa pick_up_time (08:30)
  Cálculo: 08:30 - 10 min = 08:20

  DB guardada:
    original_pick_up_time: 08:30  ← Guardado por primera vez
    pick_up_time: 08:20           ← Modificado
    reduce_applied: true
    combine_applied: false
    expand_applied: false

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 2: Apply Combine (min_gap=5, max_gap=15)
  Lee de DB: Trip A (08:20), Trip B (08:35)
  Gap: 15 minutos ✅ (cae en [5,15])
  Midpoint: (08:20 + 08:35) / 2 = 08:27.5 → 08:28

  DB guardada:
    original_pick_up_time: 08:30  ← NO CAMBIA (immutable)
    pick_up_time: 08:28           ← Modificado
    reduce_applied: true          ← Mantenido
    combine_applied: true         ← Activado
    expand_applied: false

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 3: Apply Expand (max_shift=10, min_gap=5, max_gap=15)
  Lee de DB: Trip A (08:28), Trip B (08:28)

  Check Prioridad: ¿A o B tienen combine_applied=true?
  → SÍ (ambos) → SKIP este par (Combine tiene prioridad)

  Resultado: Expand NO modifica A ni B
```

---

## Flags de Trip

Cada trip tiene estos campos para tracking de filtros:

```python
# En Trip model
original_pick_up_time: Optional[time] = None  # Tiempo ANTES de filtros
reduce_applied: bool = False                  # Flag: Reduce activo
combine_applied: bool = False                 # Flag: Combine activo
expand_applied: bool = False                  # Flag: Expand activo
filtered_at: Optional[datetime] = None        # Timestamp del último filtro
current_step_id: Optional[UUID] = None        # ID del último step
```

### ¿Cómo Se Usan?

1. **Frontend**: Lee estos flags para mostrar qué filtros están activos en cada trip
2. **Backend**: Usa estos flags para la Regla de Prioridad

```python
# Frontend puede hacer:
if trip.reduce_applied:
    mostrar_badge("Reduce")
if trip.combine_applied:
    mostrar_badge("Combine")
if trip.expand_applied:
    mostrar_badge("Expand")
```

---

## Revert

Cuando se revierte un step:

1. El step se marca como `is_active=False`
2. Se resetean TODOS los trips del día a `original_pick_up_time`
3. Se **re-aplican todos los steps activos restantes** en orden
4. Los flags se actualizan según los nuevos filtros aplicados

**Importante:** La Regla de Prioridad se re-evalúa en el revert. Si se revierte Combine, Expand puede ahora modificar los trips que antes estaban bloqueados.

---

## Orden de Validaciones

El orden de checks en `_apply_combine()` y `_apply_expand()`:

```
1. Rule A (modified_by_combine_expand)     ← Intra-step
   ↓
2. Regla de Prioridad (expand_applied/combine_applied)  ← Inter-step
   ↓
3. Location Match (pickup/dropoff)         ← Business logic
   ↓
4. Gap Range (min_gap, max_gap)            ← Business logic
   ↓
5. Apply Filter
```

---

## Frontend: Información Disponible

### Response de GET /trips

```json
{
  "id": "trip-123",
  "pick_up_time": "08:28",          // ACTUAL (modificado)
  "original_pick_up_time": "08:30", // ORIGINAL
  "reduce_applied": true,
  "combine_applied": true,
  "expand_applied": false,
  "filtered_at": "2026-01-25T10:15:30Z",
  "current_step_id": "step-uuid-2"
}
```

### ¿Necesita El Frontend Implementar Lógica de Anticolisión?

**NO.** El backend ya lo hace. El frontend solo necesita:

```typescript
// Mostrar qué filtros están aplicados
const activeFilters = [
    trip.reduce_applied && "Reduce",
    trip.combine_applied && "Combine",
    trip.expand_applied && "Expand"
].filter(Boolean);
```

---

## Resumen Ejecutivo

### Cambios 2026-01-28

1. ✅ **Single Commit Pattern**: Elimina race condition, mejora performance de 15s a <2s
2. ✅ **Conteo Independiente**: `trips_modified` ahora cuenta solo trips únicos por filtro
3. ✅ **Regla de Prioridad**: Reemplaza Rule B antigua, más simple y performante

### Reglas Actuales

- **Rule A**: Intra-step (no doble modificación en el mismo step)
- **Regla de Prioridad**: Inter-step (el primero que modifica gana)
- **Location Match**: Business logic (Combine solo con mismo origen/destino)
- **Gap Range**: Business logic (validación de gaps min/max)

---

**Última actualización:** 2026-01-28
**Versión:** Ground Filters V2.1 con Regla de Prioridad
