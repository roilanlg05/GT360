# Cambios Críticos en Expand - Notificación para Frontend

**Fecha:** 2026-01-29
**Severidad:** HIGH
**Requiere:** Actualización de expectativas del frontend

---

## RESUMEN EJECUTIVO

El sistema de Expand cambió **RADICALMENTE** de procesamiento por pares a procesamiento por cadenas. Esto afecta:

1. ✅ Número de trips modificados (puede ser menor)
2. ✅ Patrón de modificaciones (predecible, no adaptativo)
3. ✅ Exclusiones (cadenas completas, no pares individuales)
4. ✅ Preview (puede mostrar resultados diferentes)

---

## CAMBIO #1: De Pares a Cadenas

### ANTES (Sistema Viejo)

```
Enfoque: Procesamiento PAR por PAR

Lógica:
1. Iterar sobre trips secuencialmente
2. Para cada par (A, B) con gap problemático:
   - Intentar 3 estrategias: both, only_a, only_b
   - Marcar A y B como "usados"
   - Continuar con siguiente par

Ejemplo:
  Trips: A, B, C, D, E (gaps de 25 min)

  Iteración 1: Par (A, B) → Expande both
  Iteración 2: Par (B, C) → SKIP (B ya usado)
  Iteración 3: Par (C, D) → Expande both
  Iteración 4: Par (D, E) → SKIP (D ya usado)

  Resultado: Solo A, B, D expandidos
            C, E quedan sin expandir ❌
```

### AHORA (Sistema Nuevo)

```
Enfoque: Procesamiento por CADENAS

Lógica:
1. Identificar cadenas de trips con gaps pequeños
   Umbral = max_gap

2. Para cada cadena, aplicar patrón FIJO según tamaño:
   - 2 trips: [-max, +max]
   - 3 trips: [-max, 0, +max]
   - 4 trips: [-max, 0, 0, +max]
   - 5 trips: [-max, 0, 0, 0, +max]
   - 6 trips: [-max, 0, 0, 0, 0, +max]
   - 7+ trips: EXCLUIR

Ejemplo:
  Trips: A, B, C, D, E (gaps de 25 min, max_gap=35)

  Umbral = 35
  Todos gaps (25) <= 34 → UNA cadena de 5 trips

  Patrón: [-10, 0, 0, 0, +10]

  Resultado: A: -10, B: 0, C: 0, D: 0, E: +10
            Solo A y E expandidos ✅
            B, C, D quedan sin cambio
```

---

## CAMBIO #2: Agrupación por Location

### NUEVO Requisito

**Expand ahora agrupa trips por `(pickup_location, drop_off_location)` ANTES de identificar cadenas.**

Esto significa:

```
Trips del día:
  A: Marriott → Airport
  B: Marriott → Airport (gap 25)
  C: Hilton → Airport (gap 25)
  D: Hilton → Airport (gap 25)

ANTES (viejo):
  Cadena única: [A, B, C, D]
  Procesaba todos juntos

AHORA (nuevo):
  Grupo 1 (Marriott → Airport): [A, B]
    → Cadena de 2 → Patrón [-10, +10]

  Grupo 2 (Hilton → Airport): [C, D]
    → Cadena de 2 → Patrón [-10, +10]
```

**IMPACTO:** Más trips procesados (grupos más pequeños).

---

## CAMBIO #3: Umbral de Cadena

### Fórmula Actual

```
Umbral = max_gap
```

**Ejemplo:**
- Gap range: 20-35 min
- Umbral = 35 min

**Regla:**
```
Si gap <= 34 min → Misma cadena
Si gap >= 35 min → Cadenas diferentes
```

### Impacto en Frontend

**El frontend NO necesita saber el umbral**, pero SÍ necesita entender:

- Expand ahora puede NO modificar trips si forman cadena muy larga (7+)
- Expand solo modifica bordes de cadenas grandes (4-6 trips)

---

## CAMBIO #4: Patrones Fijos (No Adaptativos)

### ANTES (Sistema Viejo)

```
Para cada par, intentaba 3 estrategias y elegía la mejor:
1. Both: A retrocede max, B avanza max
2. Only A: Solo A retrocede
3. Only B: Solo B avanza

La estrategia variaba según neighbors y gaps.
```

### AHORA (Sistema Nuevo)

```
Patrón FIJO según tamaño de cadena:

Cadena de 2: SIEMPRE [-max, +max]
Cadena de 3: SIEMPRE [-max, 0, +max]
Cadena de 4: SIEMPRE [-max, 0, 0, +max]
...
```

**IMPACTO:** Más predecible pero menos adaptativo.

---

## IMPACTO EN PREVIEW

### Response Structure (Sin Cambios)

```json
{
  "trips_modified": 10,
  "changes": [
    {
      "trip_id": "uuid",
      "original_time": "04:30",
      "new_time": "04:20",
      "filter_applied": "expand",
      ...
    }
  ],
  "exclusions": [
    {
      "operation": "expand_chain(5 trips)",
      "trip_ids": [...],
      "reason": "Chain of 5 trips would leave intermediate gaps (max 3 allowed)",
      ...
    }
  ]
}
```

### Cambios Observables

#### 1. Trips Modificados Puede Ser Menor

**ANTES:**
```
5 trips con gaps de 25 min
Expandía 2-3 trips (pares independientes)
```

**AHORA:**
```
5 trips forman cadena de 5
Patrón: [-10, 0, 0, 0, +10]
Solo 2 trips modificados (bordes)
```

**Frontend verá:** `trips_modified = 2` (antes podía ser 3-4)

#### 2. Exclusiones Diferentes

**ANTES:**
```json
{
  "operation": "expand(trip_a, trip_b)",
  "reason": "All 3 expand attempts failed"
}
```

**AHORA:**
```json
{
  "operation": "expand_chain(7 trips)",
  "reason": "Chain of 7 trips would leave intermediate gaps (max 6 allowed)"
}
```

**Frontend puede mostrar:** "7 trips excluded" en lugar de "1 pair excluded"

#### 3. Patrones en Preview

**Ejemplo visible:**

```
Preview para cadena de 5 trips:

Trip 1: 04:30 → 04:20 ✅ (cambió)
Trip 2: 04:55 → 04:55 (sin cambio)
Trip 3: 05:20 → 05:20 (sin cambio)
Trip 4: 05:45 → 05:45 (sin cambio)
Trip 5: 06:10 → 06:20 ✅ (cambió)
```

**Antes:** Podría haber mostrado cambios en trips 1, 2, 4, 5 (pares alternados).

**Ahora:** Solo muestra cambios en bordes (1 y 5).

---

## COMPORTAMIENTOS "EXTRAÑOS" QUE PUEDE NOTAR EL FRONTEND

### 1. Menos Trips Modificados de lo Esperado

**Escenario:**
```
Frontend configura: Gap 20-35, Shift 10
Frontend ve en preview: "2 trips modified"
Frontend espera: "5 trips modified" (porque hay 5 trips en rango)
```

**Explicación:**
- Los 5 trips forman una cadena
- Solo bordes se modifican (2 trips)
- Los del medio (3 trips) quedan sin cambio

**¿Es bug?** NO. Es comportamiento esperado del nuevo sistema.

### 2. Trips del Medio Sin Ícono Naranja

**Escenario:**
```
Tabla muestra:
  Trip 1: [azul] [naranja] 04:30 → 03:55
  Trip 2: [azul]           04:55 → 04:30
  Trip 3: [azul]           05:20 → 04:55
  Trip 4: [azul]           05:45 → 05:25
  Trip 5: [azul] [naranja] 06:10 → 06:05
```

**Frontend pregunta:** ¿Por qué trips 2, 3, 4 NO tienen Expand?

**Explicación:**
- Cadena de 5: [1, 2, 3, 4, 5]
- Patrón: [-10, 0, 0, 0, +10]
- Solo 1 y 5 cambiaron → solo ellos tienen `expand_applied=true`

**¿Es bug?** NO. Es correcto.

### 3. Cadenas Grandes Completamente Excluidas

**Escenario:**
```
Frontend ve en exclusiones:
  "expand_chain(7 trips) excluded: Chain too long (max 6 allowed)"

Preview muestra: 0 trips modified
```

**Frontend puede pensar:** "Expand no funciona"

**Explicación:**
- 7 trips forman una cadena
- Cadenas de 7+ se excluyen
- NINGÚN trip se modifica

**¿Es bug?** NO. Es limitación del algoritmo (evita gaps intermedios).

---

## LO QUE EL FRONTEND DEBE SABER

### 1. Nueva Lógica de Cadenas

```
Expand YA NO procesa pares independientes.

Ahora:
1. Agrupa por location
2. Identifica cadenas (gaps <= max_gap)
3. Aplica patrón fijo
4. Solo modifica bordes en cadenas grandes
```

### 2. Trips del Medio Pueden Quedar Sin Cambio

```
Esto es ESPERADO en cadenas de 4-6 trips.

Cadena de 5: [-10, 0, 0, 0, +10]
             ↑             ↑
          cambia      cambia
                ↑ ↑ ↑
             sin cambio
```

### 3. Umbral de Cadena = max_gap

```
Si gap entre trips <= (max_gap - 1):
  → Están en la misma cadena

Ejemplo: max_gap=35
  Gap de 34 min → misma cadena
  Gap de 35 min → cadenas diferentes
```

### 4. Máximo 6 Trips por Cadena

```
Cadenas de 7+ trips NO se procesan (se excluyen completas).

Razón: Evitar gaps intermedios problemáticos.
```

---

## CAMBIOS EN EL RESPONSE

### Preview y Apply (StepResult)

**Campos que cambiaron:**

```typescript
// ANTES
{
  "trips_modified": 15,  // Conteo de todos los cambios
  "exclusions": [
    {
      "operation": "expand(trip_a, trip_b)",  // Por par
      "reason": "All 3 attempts failed"
    }
  ]
}

// AHORA
{
  "trips_modified": 10,  // Solo trips NUEVOS para este filtro
  "summary": {
    "modified": 10,
    "total_changes": 15,  // NUEVO campo (para debugging)
    "excluded": 5
  },
  "exclusions": [
    {
      "operation": "expand_chain(4 trips)",  // Por cadena
      "reason": "Chain of 4 trips would leave intermediate gaps (max 3 allowed)"
      // NOTA: Este mensaje cambió después a "max 6 allowed"
    }
  ]
}
```

**Campos NUEVOS:**
- `summary.total_changes` - Total de cambios (puede diferir de `trips_modified`)

**Campos MODIFICADOS:**
- `trips_modified` - Ahora es conteo INDEPENDIENTE (solo trips nuevos)
- `exclusions[].operation` - Ahora puede ser "expand_chain(N trips)" en lugar de "expand(a, b)"

---

## DOCUMENTACIÓN PARA FRONTEND

### Guía Creada

[FRONTEND_CLASSIFICATION_GUIDE.md](FRONTEND_CLASSIFICATION_GUIDE.md)

**Contenido:**
- Cómo clasificar trips según flags
- Escenarios posibles por trip
- Regla de prioridad entre Combine y Expand
- Código TypeScript de ejemplo

### Lo Que NO Cambió

```
✅ Flags en Trip (reduce_applied, combine_applied, expand_applied)
✅ Campos en TripResponse (original_pick_up_time, pick_up_time)
✅ Estructura de TripChange en preview
✅ Endpoints (mismo path, mismo método)
```

### Lo Que SÍ Cambió

```
⚠️ Comportamiento de Expand (pares → cadenas)
⚠️ Conteo de trips_modified (independiente)
⚠️ Formato de exclusiones (cadenas, no pares)
⚠️ Número de trips expandidos (puede ser menor)
```

---

## COMPORTAMIENTO EXTRAÑO: Análisis

### Síntoma 1: "Expand no modifica nada"

**Posible causa:**
```
Cadena de 7+ trips se excluye completamente.

Solución frontend:
- Mostrar mensaje en exclusiones
- Sugerir al usuario ajustar configuración
```

### Síntoma 2: "Solo algunos trips tienen ícono naranja"

**Posible causa:**
```
Cadena de 4-6 trips solo expande bordes.
Trips del medio NO tienen expand_applied.

Esto es CORRECTO.
```

### Síntoma 3: "Preview muestra menos cambios que antes"

**Posible causa:**
```
trips_modified ahora cuenta solo trips NUEVOS.

Si Reduce ya modificó 20 trips, y luego Expand modifica
10 de esos trips, trips_modified = 0 (no nuevos).

Usar summary.total_changes para ver todos los cambios.
```

### Síntoma 4: "Configuración de Expand se comporta diferente"

**Posible causa:**
```
El Gap Range ya NO determina qué pares expandir.
Ahora determina el UMBRAL de cadenas.

Config: Gap 20-35
ANTES: Expandía pares con gap 20-35
AHORA: Forma cadenas con gap <= 35

Impacto: Puede agrupar trips que antes eran independientes.
```

---

## RECOMENDACIONES PARA FRONTEND

### 1. Actualizar Mensajes de Usuario

```typescript
// ANTES
toast.success(`${result.trips_modified} trips expandidos`);

// AHORA (más claro)
if (result.trips_modified === 0 && result.summary.total_changes > 0) {
  toast.success(`${result.summary.total_changes} trips ajustados (ya tenían filtros)`);
} else {
  toast.success(`${result.trips_modified} trips expandidos`);
}
```

### 2. Mostrar Exclusiones de Cadenas

```typescript
// Si hay exclusiones de tipo "expand_chain"
const chainExclusions = result.exclusions.filter(e =>
  e.operation.startsWith("expand_chain")
);

if (chainExclusions.length > 0) {
  const totalExcluded = chainExclusions.reduce((sum, e) =>
    sum + e.trip_ids.length, 0
  );

  toast.warning(
    `${totalExcluded} trips excluded (chains too long)`,
    { description: "Adjust Gap Range or Max Shift to reduce chain size" }
  );
}
```

### 3. Explicar Trips Sin Expand en Medio de Cadena

```typescript
// En la columna Ground Filters
// Si un trip NO tiene expand_applied pero sus neighbors sí:

function isMiddleOfChain(trip: Trip, allTrips: Trip[]): boolean {
  const idx = allTrips.findIndex(t => t.id === trip.id);

  const prevHasExpand = idx > 0 && allTrips[idx-1].expand_applied;
  const nextHasExpand = idx < allTrips.length-1 && allTrips[idx+1].expand_applied;

  return prevHasExpand && nextHasExpand && !trip.expand_applied;
}

// Si es middle of chain, mostrar tooltip
<Tooltip>
  <TooltipTrigger>
    <Badge>Middle of chain</Badge>
  </TooltipTrigger>
  <TooltipContent>
    This trip is in the middle of an expand chain.
    Only edge trips are modified.
  </TooltipContent>
</Tooltip>
```

### 4. Validar Configuración

```typescript
// Ayudar al usuario a configurar Expand correctamente

function validateExpandConfig(minGap: number, maxGap: number, maxShift: number) {
  const threshold = maxGap;

  // Advertir si umbral muy grande (cadenas largas)
  if (threshold > 60) {
    return {
      valid: true,
      warning: "Large threshold may create long chains (7+ trips) that get excluded"
    };
  }

  // Advertir si umbral muy pequeño (cadenas de 1 trip)
  if (threshold < minGap + 5) {
    return {
      valid: true,
      warning: "Small threshold may prevent chain formation"
    };
  }

  return { valid: true };
}
```

---

## COMPARACIÓN: ANTES vs AHORA

| Aspecto | ANTES (Pares) | AHORA (Cadenas) |
|---------|---------------|-----------------|
| **Procesamiento** | Par por par secuencial | Cadena completa |
| **Trips modificados** | Variable (3-5 de 5) | Predecible (2 de 5) |
| **Estrategias** | 3 intentos adaptativos | Patrón fijo |
| **Exclusión** | Por par individual | Por cadena completa |
| **Agrupación** | NO (todos juntos) | SÍ (por location) |
| **Umbral** | N/A | max_gap |
| **Máximo trips** | Ilimitado | 6 por cadena |

---

## CAMBIOS QUE EL FRONTEND DEBE HACER

### ❌ NO Requiere Cambios

- ✅ Lectura de flags (reduce_applied, combine_applied, expand_applied)
- ✅ Formato de tiempos (original → actual)
- ✅ Estructura de TripResponse
- ✅ Endpoints (mismos paths)

### ⚠️ Recomendado Actualizar

1. **Mensajes de notificación** (explicar conteo independiente)
2. **Manejo de exclusiones** (cadenas vs pares)
3. **Tooltips explicativos** (trips del medio sin expand)
4. **Validación de configuración** (advertir umbrales grandes)

---

## RESUMEN PARA FRONTEND DEVELOPER

### ¿Qué cambió en el backend?

1. **Expand ahora usa sistema de cadenas** (no pares)
2. **Solo modifica bordes** en cadenas de 4-6 trips
3. **Excluye cadenas de 7+ trips** completamente
4. **Agrupa por location** antes de procesar
5. **Umbral de cadena** = max_gap

### ¿Qué debe hacer el frontend?

**MÍNIMO (funcional):**
- Nada. El sistema sigue funcionando.

**RECOMENDADO (UX mejorada):**
- Explicar por qué algunos trips NO tienen expand
- Mostrar advertencias si cadenas son muy largas
- Usar `summary.total_changes` para conteos totales

### ¿Es backward compatible?

**SÍ**, pero con comportamiento diferente:
- Mismos campos en response
- Mismos flags en trips
- Diferentes resultados de expansión

---

## DEBUGGING

Si el frontend ve comportamiento extraño:

### Check 1: ¿Cadenas muy largas?

```
Si exclusions contiene "expand_chain(7 trips)" o más:
  → La cadena es demasiado larga
  → Sugerir reducir Gap Range o aumentar Max Shift
```

### Check 2: ¿Trips del medio sin expand?

```
Si trips en el medio de una secuencia NO tienen expand_applied:
  → Están en cadena de 4-6 trips
  → Solo bordes se modifican
  → Es comportamiento esperado
```

### Check 3: ¿Conteo bajo de trips_modified?

```
Si trips_modified parece bajo:
  → Verificar summary.total_changes
  → Puede ser que trips ya tenían el filtro
```

---

**Fecha de cambios:** 2026-01-29
**Version:** Ground Filters V2.2 (con Expand por cadenas)
**Deploy:** Activo en backend
