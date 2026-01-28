# Frontend: Guía de Clasificación con Nueva Regla de Prioridad

**Fecha:** 2026-01-28
**Versión:** Ground Filters V2.1
**Para:** Frontend Developer

---

## Resumen Ejecutivo

Con la **nueva Regla de Prioridad entre Combine y Expand**, los escenarios posibles de filtros **POR TRIP** han cambiado.

### ⚠️ CAMBIO CRÍTICO

**ANTES (Rule B antigua):**
Un trip podía tener los 3 filtros activos simultáneamente:
```
Trip X: reduce_applied=true, combine_applied=true, expand_applied=true
```

**AHORA (Regla de Prioridad nueva):**
Un trip puede tener **MÁXIMO 2 filtros activos**:
- Reduce + Combine
- Reduce + Expand
- Solo Reduce
- Solo Combine
- Solo Expand

**NO ES POSIBLE:** Reduce + Combine + Expand en el mismo trip (debido a prioridad).

---

## Escenarios Posibles por Trip

### Escenarios Válidos

| Flags del Trip | Escenario | Ícono a Mostrar | Color | Tiempo a Mostrar |
|----------------|-----------|----------------|-------|------------------|
| `reduce_applied=true`<br>`combine_applied=false`<br>`expand_applied=false` | Solo Reduce | 📉 Reduce | Azul | Original → Reducido |
| `reduce_applied=false`<br>`combine_applied=true`<br>`expand_applied=false` | Solo Combine | 🔗 Combine | Naranja | Original → Combinado |
| `reduce_applied=false`<br>`combine_applied=false`<br>`expand_applied=true` | Solo Expand | 🔀 Expand | Naranja | Original → Expandido |
| `reduce_applied=true`<br>`combine_applied=true`<br>`expand_applied=false` | Reduce + Combine | 📉 🔗 | Azul + Naranja | Original → Reducido+Combinado |
| `reduce_applied=true`<br>`combine_applied=false`<br>`expand_applied=true` | Reduce + Expand | 📉 🔀 | Azul + Naranja | Original → Reducido+Expandido |
| `reduce_applied=false`<br>`combine_applied=false`<br>`expand_applied=false` | Sin filtros | — | Gris | Solo actual |

### Escenarios IMPOSIBLES (Con Nueva Regla)

| Flags del Trip | ¿Por Qué Es Imposible? |
|----------------|------------------------|
| `reduce=true, combine=true, expand=true` | Combine y Expand compiten. Solo uno puede modificar el trip. |
| `reduce=false, combine=true, expand=true` | Combine y Expand son mutuamente excluyentes por prioridad. |

---

## Cómo Funciona la Regla de Prioridad

### Regla Bidireccional

```
El primer filtro (Combine o Expand) que modifique un trip gana.
El segundo NO puede tocarlo.

Orden determinado por: step_order (menor = primero)
```

### Ejemplo 1: Combine Bloquea Expand

```
Timeline del Día 2026-02-01:

Step 1 (step_order=1): Apply Reduce
  → Trip A: 08:45 → 08:35 (reduce 10 min)
  → A.reduce_applied = True

Step 2 (step_order=2): Apply Combine (min_gap=5, max_gap=15)
  → Par (A, B): 08:35 y 08:40 → midpoint 08:37
  → A.reduce_applied = True
  → A.combine_applied = True ✅
  → B.reduce_applied = True
  → B.combine_applied = True ✅

Step 3 (step_order=3): Apply Expand (max_shift=10)
  → Intenta par (A, C):
    Check: A.combine_applied == True? ✅ SÍ
    Result: SKIP (Combine tiene prioridad)
  → Intenta par (B, D):
    Check: B.combine_applied == True? ✅ SÍ
    Result: SKIP (Combine tiene prioridad)
  → Solo puede modificar trips SIN combine_applied

Estado Final del Trip A:
  reduce_applied: true
  combine_applied: true
  expand_applied: false     ← NO SE APLICÓ por prioridad

Íconos a mostrar: 📉 (Reduce) + 🔗 (Combine)
Tiempo: 08:45 → 08:37
```

### Ejemplo 2: Expand Bloquea Combine

```
Timeline del Día 2026-02-02:

Step 1 (step_order=1): Apply Reduce
  → Trip X: 09:00 → 08:50
  → X.reduce_applied = True

Step 2 (step_order=2): Apply Expand (max_shift=10)
  → Par (X, Y): 08:50 y 08:55 → expand a 08:40 y 09:05
  → X.reduce_applied = True
  → X.expand_applied = True ✅
  → Y.reduce_applied = True
  → Y.expand_applied = True ✅

Step 3 (step_order=3): Apply Combine
  → Intenta par (X, Z):
    Check: X.expand_applied == True? ✅ SÍ
    Result: SKIP (Expand tiene prioridad)
  → Solo puede modificar trips SIN expand_applied

Estado Final del Trip X:
  reduce_applied: true
  combine_applied: false    ← NO SE APLICÓ por prioridad
  expand_applied: true

Íconos a mostrar: 📉 (Reduce) + 🔀 (Expand)
Tiempo: 09:00 → 08:40
```

---

## Clasificación en el PREVIEW

### Response del Backend (POST /preview)

```json
{
  "trips_modified": 448,
  "changes": [
    {
      "trip_id": "uuid-1",
      "original_time": "08:45",
      "new_time": "08:35",
      "filter_applied": "reduce",
      "hotel_name": "Marriott",
      "pick_up_date": "2026-02-01"
    },
    {
      "trip_id": "uuid-2",
      "original_time": "04:55",
      "new_time": "04:40",
      "filter_applied": "combine",
      "hotel_name": "Marriott",
      "pick_up_date": "2026-02-01"
    }
  ]
}
```

### Lógica de Clasificación en Frontend

```typescript
interface PreviewChange {
  trip_id: string;
  original_time: string;
  new_time: string;
  filter_applied: "reduce" | "combine" | "expand";
  hotel_name: string;
  pick_up_date: string;
}

// PASO 1: Agrupar por fecha
const byDate = changes.reduce((acc, change) => {
  const date = change.pick_up_date;
  if (!acc[date]) acc[date] = [];
  acc[date].push(change);
  return acc;
}, {} as Record<string, PreviewChange[]>);

// PASO 2: Para cada fecha, agrupar por hotel (opcional)
const byHotel = (changes: PreviewChange[]) => {
  return changes.reduce((acc, change) => {
    const hotel = change.hotel_name;
    if (!acc[hotel]) acc[hotel] = [];
    acc[hotel].push(change);
    return acc;
  }, {} as Record<string, PreviewChange[]>);
};

// PASO 3: Determinar ícono/color según filter_applied
function getFilterIcon(filterType: string) {
  switch (filterType) {
    case "reduce":
      return <ReduceIcon color="blue" />;      // Azul
    case "combine":
      return <CombineIcon color="orange" />;   // Naranja
    case "expand":
      return <ExpandIcon color="orange" />;    // Naranja
  }
}

// PASO 4: Renderizar
Object.entries(byDate).map(([date, dateChanges]) => (
  <div key={date} className="date-group">
    <h3>{formatDate(date)}</h3>  {/* "Sun, Feb 1" */}
    <p>{dateChanges.length} changes</p>

    {Object.entries(byHotel(dateChanges)).map(([hotel, hotelChanges]) => (
      <div key={hotel} className="hotel-group">
        <p>{hotel}</p>
        {hotelChanges.map(change => (
          <div key={change.trip_id} className="change-row">
            {getFilterIcon(change.filter_applied)}
            <span>{change.original_time} → {change.new_time}</span>
          </div>
        ))}
      </div>
    ))}
  </div>
))
```

**IMPORTANTE:** El backend retorna `filter_applied` (string), NO flags booleanos en el preview.

---

## Clasificación en la COLUMNA "Ground Filters"

### Response del Backend (GET /trips)

```json
{
  "id": "uuid",
  "pick_up_time": "04:40",
  "original_pick_up_time": "04:45",
  "reduce_applied": true,
  "combine_applied": true,
  "expand_applied": false
}
```

### Lógica de Clasificación en Frontend

```typescript
interface GroundFilterDisplay {
  icons: string[];       // ["reduce", "combine"]
  originalTime: string;  // "04:45"
  finalTime: string;     // "04:40"
  hasFilters: boolean;
}

function classifyTrip(trip: TripResponse): GroundFilterDisplay {
  // Si no tiene filtros, retornar vacío
  if (!trip.original_pick_up_time) {
    return {
      icons: [],
      originalTime: "",
      finalTime: "",
      hasFilters: false
    };
  }

  // Construir array de íconos según flags
  const icons: string[] = [];

  // IMPORTANTE: El orden de los íconos debe reflejar el orden de aplicación
  // Reduce siempre es primero (si está presente)
  if (trip.reduce_applied) {
    icons.push("reduce");
  }

  // Combine o Expand (solo UNO puede estar activo debido a prioridad)
  if (trip.combine_applied) {
    icons.push("combine");
  } else if (trip.expand_applied) {
    icons.push("expand");
  }

  return {
    icons,
    originalTime: trip.original_pick_up_time,
    finalTime: trip.pick_up_time,
    hasFilters: true
  };
}

// Renderizar
function GroundFiltersCell({ trip }: { trip: TripResponse }) {
  const display = classifyTrip(trip);

  if (!display.hasFilters) {
    return <span className="text-muted">—</span>;
  }

  return (
    <div className="ground-filters-cell">
      {/* Íconos */}
      <div className="filter-icons">
        {display.icons.includes("reduce") && (
          <ReduceIcon color="blue" />
        )}
        {display.icons.includes("combine") && (
          <CombineIcon color="orange" />
        )}
        {display.icons.includes("expand") && (
          <ExpandIcon color="orange" />
        )}
      </div>

      {/* Tiempos */}
      <span className="time-diff">
        {display.originalTime} → {display.finalTime}
      </span>
    </div>
  );
}
```

---

## Escenarios Posibles por Día/Trip

### ✅ Escenarios Válidos

Basándome en la nueva regla de prioridad, estos son los **ÚNICOS** escenarios posibles:

```
POR DÍA (stack):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Solo Reduce
2. Solo Combine
3. Solo Expand
4. Reduce + Combine   (en ese orden o invertido)
5. Reduce + Expand    (en ese orden o invertido)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

POR TRIP (flags):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. reduce=true,  combine=false, expand=false
2. reduce=false, combine=true,  expand=false
3. reduce=false, combine=false, expand=true
4. reduce=true,  combine=true,  expand=false
5. reduce=true,  combine=false, expand=true
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### ❌ Escenario IMPOSIBLE

```
reduce=false, combine=true, expand=true
reduce=true,  combine=true, expand=true

¿Por qué? Combine y Expand compiten por prioridad.
Solo UNO de los dos puede modificar un trip específico.
```

---

## Tabla de Clasificación Completa

### Para la Columna "Ground Filters"

Use esta tabla para determinar qué mostrar:

| `reduce_applied` | `combine_applied` | `expand_applied` | Íconos a Mostrar | Color | Tiempos |
|------------------|-------------------|------------------|------------------|-------|---------|
| `false` | `false` | `false` | — | Gris | Solo `pick_up_time` |
| `true` | `false` | `false` | 📉 | Azul | `original → pick_up` |
| `false` | `true` | `false` | 🔗 | Naranja | `original → pick_up` |
| `false` | `false` | `true` | 🔀 | Naranja | `original → pick_up` |
| `true` | `true` | `false` | 📉 🔗 | Azul + Naranja | `original → pick_up` |
| `true` | `false` | `true` | 📉 🔀 | Azul + Naranja | `original → pick_up` |

### Para el Preview

```typescript
// En el preview, usa change.filter_applied (string)
function getPreviewIcon(filterType: string) {
  switch (filterType) {
    case "reduce":  return <ReduceIcon color="blue" />;
    case "combine": return <CombineIcon color="orange" />;
    case "expand":  return <ExpandIcon color="orange" />;
  }
}
```

---

## Explicación de la Nueva Regla para Frontend

### Concepto Clave

```
Reduce es "BASE" (se aplica siempre, no compite)
Combine y Expand COMPITEN (solo uno gana por trip)
```

### Flujo de Aplicación

```
Escenario A: Reduce → Combine → Expand

Step 1: Reduce
  Trip A: 08:45 → 08:35
  Flags: reduce=true

Step 2: Combine
  Par (A, B): 08:35 y 08:40 → 08:37
  Flags: reduce=true, combine=true

Step 3: Expand
  Intenta par (A, C):
  → Check: A.combine_applied? ✅ SÍ
  → SKIP (Combine tiene prioridad)

  Resultado: A NO se expande
  Flags finales: reduce=true, combine=true, expand=false

  ✅ Frontend muestra: [Reduce] [Combine] 08:45 → 08:37
```

```
Escenario B: Reduce → Expand → Combine

Step 1: Reduce
  Trip X: 09:00 → 08:50
  Flags: reduce=true

Step 2: Expand
  Par (X, Y): 08:50 y 08:55 → 08:40 y 09:05
  Flags: reduce=true, expand=true

Step 3: Combine
  Intenta par (X, Z):
  → Check: X.expand_applied? ✅ SÍ
  → SKIP (Expand tiene prioridad)

  Resultado: X NO se combina
  Flags finales: reduce=true, combine=false, expand=true

  ✅ Frontend muestra: [Reduce] [Expand] 09:00 → 08:40
```

---

## Clasificación Detallada por Escenario

### Escenario 1: Solo Reduce

**Backend retorna:**
```json
{
  "reduce_applied": true,
  "combine_applied": false,
  "expand_applied": false,
  "original_pick_up_time": "08:45",
  "pick_up_time": "08:35"
}
```

**Frontend debe mostrar:**
```
Ícono: 📉 (azul)
Tiempo: 08:45 → 08:35
```

---

### Escenario 2: Solo Combine

**Backend retorna:**
```json
{
  "reduce_applied": false,
  "combine_applied": true,
  "expand_applied": false,
  "original_pick_up_time": "05:05",
  "pick_up_time": "05:00"
}
```

**Frontend debe mostrar:**
```
Ícono: 🔗 (naranja)
Tiempo: 05:05 → 05:00
```

---

### Escenario 3: Solo Expand

**Backend retorna:**
```json
{
  "reduce_applied": false,
  "combine_applied": false,
  "expand_applied": true,
  "original_pick_up_time": "06:05",
  "pick_up_time": "05:45"
}
```

**Frontend debe mostrar:**
```
Ícono: 🔀 (naranja)
Tiempo: 06:05 → 05:45
```

---

### Escenario 4: Reduce + Combine

**Backend retorna:**
```json
{
  "reduce_applied": true,
  "combine_applied": true,
  "expand_applied": false,
  "original_pick_up_time": "04:45",
  "pick_up_time": "04:40"
}
```

**Frontend debe mostrar:**
```
Íconos: 📉 (azul) + 🔗 (naranja)
Tiempo: 04:45 → 04:40
```

**Orden:** Reduce primero (azul), luego Combine (naranja)

---

### Escenario 5: Reduce + Expand

**Backend retorna:**
```json
{
  "reduce_applied": true,
  "combine_applied": false,
  "expand_applied": true,
  "original_pick_up_time": "06:05",
  "pick_up_time": "05:45"
}
```

**Frontend debe mostrar:**
```
Íconos: 📉 (azul) + 🔀 (naranja)
Tiempo: 06:05 → 05:45
```

**Orden:** Reduce primero (azul), luego Expand (naranja)

---

## Código Completo para el Frontend

### Componente: GroundFiltersCell

```typescript
import { Badge } from "@/components/ui/badge";

interface TripResponse {
  id: string;
  pick_up_time: string;
  original_pick_up_time: string | null;
  reduce_applied: boolean;
  combine_applied: boolean;
  expand_applied: boolean;
}

function GroundFiltersCell({ trip }: { trip: TripResponse }) {
  // Si no hay filtros aplicados, mostrar "—"
  if (!trip.original_pick_up_time) {
    return (
      <div className="flex items-center justify-start">
        <span className="text-xs text-muted-foreground">—</span>
      </div>
    );
  }

  // Construir array de badges según flags
  const badges = [];

  // Reduce siempre primero (si está presente)
  if (trip.reduce_applied) {
    badges.push(
      <Badge key="reduce" variant="blue" className="mr-1">
        📉 Reduce
      </Badge>
    );
  }

  // Combine o Expand (solo UNO puede estar activo)
  if (trip.combine_applied) {
    badges.push(
      <Badge key="combine" variant="orange" className="mr-1">
        🔗 Combine
      </Badge>
    );
  } else if (trip.expand_applied) {
    badges.push(
      <Badge key="expand" variant="orange" className="mr-1">
        🔀 Expand
      </Badge>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      {/* Badges de filtros */}
      <div className="flex items-center">
        {badges}
      </div>

      {/* Tiempos */}
      <span className="text-xs text-muted-foreground">
        {trip.original_pick_up_time} → {trip.pick_up_time}
      </span>
    </div>
  );
}

export default GroundFiltersCell;
```

---

## Validación de Clasificación

### Regla de Validación

```typescript
// Esta función valida que los flags sean consistentes
function validateTripFlags(trip: TripResponse): {
  valid: boolean;
  reason?: string;
} {
  // REGLA 1: Si original_pick_up_time existe, al menos UN flag debe ser true
  if (trip.original_pick_up_time &&
      !trip.reduce_applied &&
      !trip.combine_applied &&
      !trip.expand_applied) {
    return {
      valid: false,
      reason: "Trip tiene original_pick_up_time pero sin filtros activos"
    };
  }

  // REGLA 2: Combine y Expand NO pueden estar ambos en true
  if (trip.combine_applied && trip.expand_applied) {
    return {
      valid: false,
      reason: "INCONSISTENCIA: Combine y Expand no pueden coexistir (Regla de Prioridad)"
    };
  }

  // REGLA 3: Si NO hay original_pick_up_time, ningún flag debe ser true
  if (!trip.original_pick_up_time &&
      (trip.reduce_applied || trip.combine_applied || trip.expand_applied)) {
    return {
      valid: false,
      reason: "Flags activos sin original_pick_up_time"
    };
  }

  return { valid: true };
}
```

---

## Respuesta a Tu Pregunta

### "¿Solo se producen escenarios {Reduce y Combine} o {Reduce y Expand}?"

**Respuesta: SÍ, CORRECTO** (para un trip específico).

Con la nueva regla de prioridad:

```
POR TRIP, los escenarios son:

✅ {Reduce solo}
✅ {Combine solo}
✅ {Expand solo}
✅ {Reduce + Combine}
✅ {Reduce + Expand}

❌ {Reduce + Combine + Expand} ← IMPOSIBLE
❌ {Combine + Expand} ← IMPOSIBLE (sin Reduce)
```

**Pero a nivel de STACK del día:**

Puedes tener los 3 steps en el stack:
```
Step 1: Reduce
Step 2: Combine
Step 3: Expand
```

**Sin embargo, los TRIPS individuales solo tendrán:**
- Algunos: `reduce=true, combine=true, expand=false` (Combine los tocó primero)
- Otros: `reduce=true, combine=false, expand=true` (Expand los tocó, Combine no pudo)

---

## Cómo Clasificar Correctamente

### Lógica de Clasificación (Pseudocódigo)

```typescript
// Para cada trip:
1. ¿Tiene original_pick_up_time?
   NO → Mostrar "—" (sin filtros)
   SÍ → Continuar

2. Leer flags y construir array de íconos:
   icons = []

   if (reduce_applied) {
     icons.push({ type: "reduce", color: "blue" })
   }

   if (combine_applied) {
     icons.push({ type: "combine", color: "orange" })
   } else if (expand_applied) {
     icons.push({ type: "expand", color: "orange" })
   }

   // NOTA: combine_applied y expand_applied nunca son true simultáneamente

3. Mostrar íconos + tiempos:
   {icons.map(icon => <Icon {...icon} />)}
   {original_pick_up_time} → {pick_up_time}
```

---

## Ejemplo Visual de Clasificación

Basándome en las imágenes que compartiste:

### Imagen 1: Tabla de Trips

```
Row 1: 04:45 → 04:40
  Flags: reduce=true, combine=true, expand=false
  Mostrar: [📉 azul] [🔗 naranja] 04:45 → 04:40

Row 2: 04:55 → 04:40
  Flags: reduce=true, combine=true, expand=false
  Mostrar: [📉 azul] [🔗 naranja] 04:55 → 04:40

Row 3: 05:05 → 05:00
  Flags: reduce=true, combine=true, expand=false
  Mostrar: [📉 azul] [🔗 naranja] 05:05 → 05:00

Row 4: 05:15 → 05:00
  Flags: reduce=true, combine=true, expand=false
  Mostrar: [📉 azul] [🔗 naranja] 05:15 → 05:00

Row 5: 05:45 → 05:35
  Flags: reduce=true, combine=false, expand=false
  Mostrar: [📉 azul] 05:45 → 05:35

Row 6: 06:05 → 05:45
  Flags: reduce=true, combine=false, expand=true
  Mostrar: [📉 azul] [🔀 naranja] 06:05 → 05:45

Row 7: 06:35 → 06:35
  Flags: reduce=true, combine=false, expand=true
  Mostrar: [📉 azul] [🔀 naranja] 06:35 → 06:35

Row 8: 07:45 → 07:35
  Flags: reduce=true, combine=false, expand=false
  Mostrar: [📉 azul] 07:45 → 07:35

Row 9: 09:15 → 09:05
  Flags: reduce=true, combine=false, expand=false
  Mostrar: [📉 azul] 09:15 → 09:05

Row 10: Sin original_pick_up_time
  Flags: reduce=false, combine=false, expand=false
  Mostrar: —
```

### Imagen 2: Preview Changes

```
Sun, Feb 1 (13 changes)

WN 3034 Marriott: 04:45 → 04:35
  filter_applied: "reduce"
  Mostrar: [📉 azul] 04:45 → 04:35

WN 4667 Marriott: 04:55 → 04:40
  filter_applied: "combine"
  Mostrar: [🔗 naranja] 04:55 → 04:40

WN 2220 Mission Inn: 05:05 → 04:55
  filter_applied: "reduce"
  Mostrar: [📉 azul] 05:05 → 04:55
```

---

## Código TypeScript Completo

```typescript
// types.ts
export interface TripResponse {
  id: string;
  pick_up_time: string;
  original_pick_up_time: string | null;
  reduce_applied: boolean;
  combine_applied: boolean;
  expand_applied: boolean;
  // ... otros campos
}

export interface PreviewChange {
  trip_id: string;
  original_time: string;
  new_time: string;
  filter_applied: "reduce" | "combine" | "expand";
  hotel_name: string;
  pick_up_date: string;
}

// ground-filters-classifier.ts
export class GroundFiltersClassifier {
  /**
   * Determina qué íconos mostrar para un trip según flags.
   *
   * Regla de Prioridad:
   * - Combine y Expand son mutuamente excluyentes (solo UNO puede estar activo)
   * - Reduce es compatible con ambos
   */
  static getIcons(trip: TripResponse): string[] {
    const icons: string[] = [];

    // Reduce siempre primero (si está presente)
    if (trip.reduce_applied) {
      icons.push("reduce");
    }

    // Combine o Expand (solo uno puede estar activo)
    if (trip.combine_applied) {
      icons.push("combine");
    } else if (trip.expand_applied) {
      icons.push("expand");
    }

    return icons;
  }

  /**
   * Determina el color principal de la celda.
   */
  static getPrimaryColor(trip: TripResponse): string {
    // Si tiene Combine o Expand, priorizar naranja
    if (trip.combine_applied || trip.expand_applied) {
      return "orange";
    }
    // Si solo tiene Reduce, usar azul
    if (trip.reduce_applied) {
      return "blue";
    }
    // Sin filtros
    return "gray";
  }

  /**
   * Valida que los flags sean consistentes.
   */
  static validate(trip: TripResponse): { valid: boolean; reason?: string } {
    // Combine y Expand no pueden coexistir
    if (trip.combine_applied && trip.expand_applied) {
      return {
        valid: false,
        reason: "BACKEND ERROR: Combine y Expand no pueden coexistir (Regla de Prioridad)"
      };
    }

    // Si hay original_pick_up_time, debe haber al menos un flag
    if (trip.original_pick_up_time &&
        !trip.reduce_applied &&
        !trip.combine_applied &&
        !trip.expand_applied) {
      return {
        valid: false,
        reason: "Inconsistencia: original_pick_up_time sin flags"
      };
    }

    return { valid: true };
  }
}

// Componente React
export function GroundFiltersCell({ trip }: { trip: TripResponse }) {
  // Validar consistencia (opcional, para debugging)
  const validation = GroundFiltersClassifier.validate(trip);
  if (!validation.valid) {
    console.error(`[GroundFilters] Trip ${trip.id}: ${validation.reason}`);
  }

  // Si no hay filtros
  if (!trip.original_pick_up_time) {
    return <span className="text-muted">—</span>;
  }

  // Obtener íconos
  const icons = GroundFiltersClassifier.getIcons(trip);

  return (
    <div className="ground-filters-cell">
      <div className="filter-badges">
        {icons.map(icon => {
          switch (icon) {
            case "reduce":
              return <Badge key="reduce" variant="blue">📉</Badge>;
            case "combine":
              return <Badge key="combine" variant="orange">🔗</Badge>;
            case "expand":
              return <Badge key="expand" variant="orange">🔀</Badge>;
          }
        })}
      </div>

      <span className="time-display">
        {trip.original_pick_up_time} → {trip.pick_up_time}
      </span>
    </div>
  );
}
```

---

## Testing de Clasificación

### Test 1: Validar Flags Mutuamente Excluyentes

```typescript
// Este test debe FALLAR si hay inconsistencia
test("Combine y Expand no coexisten", () => {
  const trips = await fetchTrips();

  trips.forEach(trip => {
    if (trip.combine_applied && trip.expand_applied) {
      throw new Error(
        `BACKEND ERROR: Trip ${trip.id} tiene combine=true y expand=true ` +
        `(viola Regla de Prioridad)`
      );
    }
  });
});
```

### Test 2: Validar Clasificación Visual

```typescript
test("Clasificación muestra íconos correctos", () => {
  const scenarios = [
    {
      trip: { reduce: true, combine: false, expand: false },
      expected: ["reduce"]
    },
    {
      trip: { reduce: true, combine: true, expand: false },
      expected: ["reduce", "combine"]
    },
    {
      trip: { reduce: true, combine: false, expand: true },
      expected: ["reduce", "expand"]
    },
    {
      trip: { reduce: false, combine: true, expand: false },
      expected: ["combine"]
    }
  ];

  scenarios.forEach(scenario => {
    const icons = GroundFiltersClassifier.getIcons(scenario.trip);
    expect(icons).toEqual(scenario.expected);
  });
});
```

---

## Resumen Final

### ¿Quién Hace Qué?

| Responsabilidad | Backend | Frontend |
|-----------------|---------|----------|
| **Calcular tiempos** | ✅ SÍ | ❌ NO |
| **Aplicar regla de prioridad** | ✅ SÍ | ❌ NO |
| **Retornar flags** | ✅ SÍ | ❌ NO |
| **Agrupar por fecha/hotel** | ❌ NO | ✅ SÍ |
| **Mapear flags → íconos** | ❌ NO | ✅ SÍ |
| **Formatear tiempos para display** | ❌ NO | ✅ SÍ |
| **Validar inconsistencias** | ✅ SÍ (evita) | ⚠️ OPCIONAL (detecta) |

### Escenarios Posibles (Confirmado)

```
✅ {Reduce solo}
✅ {Combine solo}
✅ {Expand solo}
✅ {Reduce + Combine}
✅ {Reduce + Expand}

❌ {Reduce + Combine + Expand} ← IMPOSIBLE con nueva regla
```

---

**Última actualización:** 2026-01-28
**Versión:** Ground Filters V2.1 con Regla de Prioridad
**Deploy:** Activo en backend
