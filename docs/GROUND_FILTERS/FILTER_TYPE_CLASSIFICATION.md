# Ground Filters: Clasificación por Tipo de Filtro

**Fecha:** 2026-01-29
**Versión:** Ground Filters V2.2
**Para:** Frontend Developer

---

## Resumen Ejecutivo

El backend clasifica y notifica los filtros por tipo ("reduce", "combine", "expand") de forma **automática e independiente**. Cada operación incluye el `filter_type` en el response y en las notificaciones WebSocket.

---

## Tipos de Filtros

```typescript
type FilterType = "reduce" | "combine" | "expand";
```

---

## Clasificación en Apply

### Request (Frontend → Backend)

```typescript
POST /v2/locations/{location_id}/airlines/{airline}/filters/step

Body: {
  "filter_type": "expand",  // ← Frontend especifica el tipo
  "pick_up_date": "2026-01-28",
  "windows": [...]
}
```

### Response (Backend → Frontend)

```typescript
{
  "step_id": "uuid",
  "filter_type": "expand",  // ← Backend confirma el tipo
  "pick_up_date": "2026-01-28",
  "trips_modified": 10,  // Trips NUEVOS para ESTE filtro
  "changes": [...],
  "summary": {
    "modified": 10,
    "total_changes": 15,  // Total (puede incluir trips ya filtrados)
    "excluded": 2
  }
}
```

### Código Backend

```python
# step_filter_service.py línea 249-259
return StepResult(
    step_id=step_id,
    filter_type=config.filter_type,  # ← "reduce" | "combine" | "expand"
    pick_up_date=config.pick_up_date,
    trips_modified=independent_count,  # Solo trips NUEVOS
    changes=self.changes,
    exclusions=self.exclusions,
    summary={
        "modified": independent_count,
        "total_changes": len(self.changes),
        "excluded": len(self.exclusions),
    },
)
```

---

## Notificaciones WebSocket

### Apply Notification

**Cuándo se envía:** Después de aplicar un filtro (línea 272)

**Estructura del evento:**

```json
{
  "type": "step_applied",
  "location_id": "uuid",
  "airline": "WN",
  "step_id": "uuid",
  "filter_type": "reduce",  // ← Tipo de filtro aplicado
  "trips_affected": 25,      // ← Conteo independiente
  "timestamp": "2026-01-28T10:15:30Z",
  "message": "Filter step applied: reduce (25 trips)"
}
```

**Código Backend (líneas 1177-1186):**

```python
event = {
    "type": "step_applied",
    "location_id": str(location_id),
    "airline": airline,
    "step_id": str(step_id),
    "filter_type": filter_type,  # ← "reduce" | "combine" | "expand"
    "trips_affected": trips_affected,
    "timestamp": datetime.utcnow().isoformat(),
    "message": f"Filter step applied: {filter_type} ({trips_affected} trips)"
}
```

### Revert Notification

**Cuándo se envía:** Después de revertir un filtro (línea 864)

**Estructura del evento:**

```json
{
  "type": "step_reverted",
  "location_id": "uuid",
  "airline": "WN",
  "step_id": "uuid",
  "filter_type": "expand",  // ← Tipo de filtro revertido
  "timestamp": "2026-01-28T10:20:00Z",
  "message": "Filter step reverted: expand"
}
```

**Código Backend (líneas 1212-1220):**

```python
event = {
    "type": "step_reverted",
    "location_id": str(location_id),
    "airline": airline,
    "step_id": str(step_id),
    "filter_type": filter_type,  # ← "reduce" | "combine" | "expand"
    "timestamp": datetime.utcnow().isoformat(),
    "message": f"Filter step reverted: {filter_type}"
}
```

---

## Clasificación en el Frontend

### Recepción de Notificaciones

```typescript
// WebSocket handler
websocket.onmessage = (event) => {
  const data = JSON.parse(event.data);

  switch (data.type) {
    case "step_applied":
      handleStepApplied(data);
      break;
    case "step_reverted":
      handleStepReverted(data);
      break;
  }
};

function handleStepApplied(data: StepAppliedEvent) {
  const { filter_type, trips_affected } = data;

  // Clasificar por tipo
  switch (filter_type) {
    case "reduce":
      toast.success(`${trips_affected} trips reducidos`, {
        icon: "📉",
        style: { backgroundColor: "blue" }
      });
      break;

    case "combine":
      toast.success(`${trips_affected} trips combinados`, {
        icon: "🔗",
        style: { backgroundColor: "orange" }
      });
      break;

    case "expand":
      toast.success(`${trips_affected} trips expandidos`, {
        icon: "🔀",
        style: { backgroundColor: "orange" }
      });
      break;
  }

  // Refetch trips
  await refetchTrips();
}
```

---

## Conteo Independiente por Tipo

### Backend Calcula Automáticamente

**Código (líneas 226-234):**

```python
# Antes de aplicar: guardar trips que YA tenían este filtro
filter_flag = f"{config.filter_type}_applied"  # "reduce_applied", etc.
trips_already_with_filter = {
    t.id for t in trips if getattr(t, filter_flag, False)
}

# Después de aplicar: contar solo NUEVOS
trips_newly_modified = {
    change.trip_id for change in self.changes
    if change.trip_id not in trips_already_with_filter
}
independent_count = len(trips_newly_modified)
```

**Esto garantiza:**
- REDUCE solo cuenta trips que NO tenían `reduce_applied=true`
- COMBINE solo cuenta trips que NO tenían `combine_applied=true`
- EXPAND solo cuenta trips que NO tenían `expand_applied=true`

---

## Ejemplo de Clasificación

### Escenario: Aplicar Reduce, luego Combine

```
Step 1: Apply Reduce
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Request:
  POST /filters/step
  { "filter_type": "reduce", ... }

Response:
  {
    "filter_type": "reduce",
    "trips_modified": 25  // 25 trips NO tenían reduce_applied
  }

WebSocket:
  {
    "type": "step_applied",
    "filter_type": "reduce",
    "trips_affected": 25
  }

Frontend muestra:
  📉 "25 trips reducidos"


Step 2: Apply Combine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Request:
  POST /filters/step
  { "filter_type": "combine", ... }

Trips ANTES de Combine:
  - 25 trips tienen reduce_applied=true
  - 0 trips tienen combine_applied=true

Combine modifica 20 trips (10 pares):
  - 15 trips NO tenían combine_applied → NUEVOS
  - 5 trips YA tenían combine_applied → re-aplicados

Response:
  {
    "filter_type": "combine",
    "trips_modified": 15,  // Solo NUEVOS
    "summary": {
      "modified": 15,
      "total_changes": 20  // Total modificados
    }
  }

WebSocket:
  {
    "type": "step_applied",
    "filter_type": "combine",
    "trips_affected": 15  // Solo NUEVOS
  }

Frontend muestra:
  🔗 "15 trips combinados"
```

---

## Clasificación en Preview

### Preview por Tipo

```typescript
POST /v2/locations/{id}/airlines/{airline}/filters/step/preview
Body: {
  "filter_type": "expand",
  "pick_up_date": "2026-01-28",
  "windows": [...]
}

Response:
{
  "step_id": null,
  "filter_type": "expand",  // ← Tipo de filtro
  "trips_modified": 12,
  "changes": [
    {
      "trip_id": "uuid",
      "filter_applied": "expand",  // ← También en cada change
      "original_time": "05:00",
      "new_time": "05:10",
      ...
    }
  ]
}
```

### Frontend Clasifica Changes por Tipo

```typescript
function classifyChangesByType(changes: TripChange[]) {
  return changes.reduce((acc, change) => {
    const type = change.filter_applied;  // "reduce" | "combine" | "expand"

    if (!acc[type]) acc[type] = [];
    acc[type].push(change);

    return acc;
  }, {} as Record<string, TripChange[]>);
}

// Uso:
const byType = classifyChangesByType(preview.changes);

console.log(`Reduce: ${byType.reduce?.length || 0} trips`);
console.log(`Combine: ${byType.combine?.length || 0} trips`);
console.log(`Expand: ${byType.expand?.length || 0} trips`);
```

---

## Estadísticas por Tipo de Filtro

### Endpoint: Stack

```
GET /v2/locations/{id}/airlines/{airline}/filters/stack?pick_up_date=2026-01-28
```

**Response:**

```json
{
  "location_id": "uuid",
  "airline": "WN",
  "pick_up_date": "2026-01-28",
  "steps": [
    {
      "step_id": "uuid-1",
      "step_order": 1,
      "filter_type": "reduce",  // ← Tipo
      "trips_affected": 125,     // ← Conteo para ESTE filtro
      "is_active": true
    },
    {
      "step_id": "uuid-2",
      "step_order": 2,
      "filter_type": "combine",  // ← Tipo
      "trips_affected": 45,       // ← Conteo para ESTE filtro
      "is_active": true
    },
    {
      "step_id": "uuid-3",
      "step_order": 3,
      "filter_type": "expand",  // ← Tipo
      "trips_affected": 30,      // ← Conteo para ESTE filtro
      "is_active": true
    }
  ],
  "total_trips_affected": 170  // Total (puede tener overlap)
}
```

### Frontend Muestra Estadísticas

```typescript
const stack = await getStack(locationId, airline, date);

// Agrupar por tipo
const statsByType = stack.steps.reduce((acc, step) => {
  acc[step.filter_type] = (acc[step.filter_type] || 0) + step.trips_affected;
  return acc;
}, {} as Record<string, number>);

// Mostrar
console.log(`Reduce: ${statsByType.reduce || 0} trips`);
console.log(`Combine: ${statsByType.combine || 0} trips`);
console.log(`Expand: ${statsByType.expand || 0} trips`);
```

---

## Notificaciones Independientes por Tipo

### Implementación Frontend

```typescript
// Mantener contadores por tipo
const filterStats = {
  reduce: 0,
  combine: 0,
  expand: 0
};

// WebSocket handler
websocket.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.type === "step_applied") {
    const { filter_type, trips_affected } = data;

    // Actualizar contador del tipo específico
    filterStats[filter_type] += trips_affected;

    // Mostrar notificación clasificada
    showNotification(filter_type, trips_affected);
  }
};

function showNotification(filterType: FilterType, count: number) {
  const config = {
    reduce: {
      icon: "📉",
      color: "blue",
      message: `${count} trips reducidos`
    },
    combine: {
      icon: "🔗",
      color: "orange",
      message: `${count} trips combinados`
    },
    expand: {
      icon: "🔀",
      color: "orange",
      message: `${count} trips expandidos`
    }
  };

  const cfg = config[filterType];
  toast.success(cfg.message, {
    icon: cfg.icon,
    style: { borderColor: cfg.color }
  });
}
```

---

## Clasificación de Trips en la Tabla

### Backend Provee Flags Individuales

```json
{
  "id": "uuid",
  "reduce_applied": true,   // ← Flag para Reduce
  "combine_applied": true,  // ← Flag para Combine
  "expand_applied": false,  // ← Flag para Expand
  ...
}
```

### Frontend Clasifica por Flags

```typescript
function getActiveFilterTypes(trip: TripResponse): FilterType[] {
  const types: FilterType[] = [];

  if (trip.reduce_applied) types.push("reduce");
  if (trip.combine_applied) types.push("combine");
  if (trip.expand_applied) types.push("expand");

  return types;
}

// Contar trips por tipo de filtro
function countTripsByFilter(trips: TripResponse[]) {
  const counts = {
    reduce: 0,
    combine: 0,
    expand: 0
  };

  trips.forEach(trip => {
    if (trip.reduce_applied) counts.reduce++;
    if (trip.combine_applied) counts.combine++;
    if (trip.expand_applied) counts.expand++;
  });

  return counts;
}

// Uso:
const trips = await fetchTrips();
const stats = countTripsByFilter(trips);

console.log(`Trips con Reduce: ${stats.reduce}`);
console.log(`Trips con Combine: ${stats.combine}`);
console.log(`Trips con Expand: ${stats.expand}`);
```

---

## Clasificación de Changes en Preview

### Backend Incluye filter_applied

```json
{
  "changes": [
    {
      "trip_id": "uuid-1",
      "filter_applied": "reduce",  // ← Tipo del cambio
      "original_time": "08:30",
      "new_time": "08:20"
    },
    {
      "trip_id": "uuid-2",
      "filter_applied": "combine",  // ← Tipo del cambio
      "original_time": "08:20",
      "new_time": "08:25"
    }
  ]
}
```

### Frontend Agrupa por Tipo

```typescript
function groupChangesByType(changes: TripChange[]) {
  return changes.reduce((acc, change) => {
    const type = change.filter_applied;

    if (!acc[type]) {
      acc[type] = {
        type: type,
        count: 0,
        changes: []
      };
    }

    acc[type].count++;
    acc[type].changes.push(change);

    return acc;
  }, {} as Record<string, {
    type: string;
    count: number;
    changes: TripChange[];
  }>);
}

// Renderizar por tipo
const grouped = groupChangesByType(preview.changes);

Object.values(grouped).map(group => (
  <div key={group.type} className="filter-group">
    <h3>{getFilterIcon(group.type)} {group.type}</h3>
    <p>{group.count} cambios</p>
    {group.changes.map(change => (
      <div key={change.trip_id}>
        {change.original_time} → {change.new_time}
      </div>
    ))}
  </div>
))
```

---

## Clasificación Múltiple (Trip con Varios Filtros)

### Un Trip Puede Tener Múltiples Filtros

```json
{
  "id": "uuid",
  "reduce_applied": true,   // ← Tiene Reduce
  "combine_applied": true,  // ← Tiene Combine
  "expand_applied": false   // ← NO tiene Expand
}
```

### Frontend Muestra Todos los Tipos Activos

```typescript
function GroundFiltersCell({ trip }: { trip: TripResponse }) {
  const activeTypes = getActiveFilterTypes(trip);

  // Mostrar badge por cada tipo activo
  return (
    <div className="filter-badges">
      {activeTypes.includes("reduce") && (
        <Badge variant="blue">📉 Reduce</Badge>
      )}
      {activeTypes.includes("combine") && (
        <Badge variant="orange">🔗 Combine</Badge>
      )}
      {activeTypes.includes("expand") && (
        <Badge variant="orange">🔀 Expand</Badge>
      )}

      <span className="time-diff">
        {trip.original_pick_up_time} → {trip.pick_up_time}
      </span>
    </div>
  );
}
```

---

## Resumen: ¿Cómo Clasificar?

### Backend Automáticamente Provee:

| Campo | Dónde | Tipo | Propósito |
|-------|-------|------|----------|
| `filter_type` | StepResult, WebSocket | string | Tipo del filtro aplicado/revertido |
| `filter_applied` | TripChange (preview) | string | Tipo del cambio específico |
| `reduce_applied` | TripResponse | boolean | Flag: ¿Tiene Reduce? |
| `combine_applied` | TripResponse | boolean | Flag: ¿Tiene Combine? |
| `expand_applied` | TripResponse | boolean | Flag: ¿Tiene Expand? |
| `trips_affected` | WebSocket | number | Conteo para ESTE tipo |
| `trips_modified` | StepResult | number | Conteo INDEPENDIENTE |

### Frontend Solo Necesita:

1. **Leer `filter_type`** del response/WebSocket
2. **Mostrar notificación** según el tipo
3. **Agrupar estadísticas** por tipo si se desea
4. **Leer flags booleanos** para mostrar íconos en la tabla

---

## Código Completo de Clasificación

```typescript
// types.ts
export type FilterType = "reduce" | "combine" | "expand";

export interface FilterStats {
  reduce: number;
  combine: number;
  expand: number;
}

// filter-classifier.ts
export class FilterClassifier {
  /**
   * Obtiene tipos de filtros activos en un trip.
   */
  static getActiveTypes(trip: TripResponse): FilterType[] {
    const types: FilterType[] = [];

    if (trip.reduce_applied) types.push("reduce");
    if (trip.combine_applied) types.push("combine");
    if (trip.expand_applied) types.push("expand");

    return types;
  }

  /**
   * Cuenta trips por tipo de filtro.
   */
  static countByType(trips: TripResponse[]): FilterStats {
    return trips.reduce((acc, trip) => {
      if (trip.reduce_applied) acc.reduce++;
      if (trip.combine_applied) acc.combine++;
      if (trip.expand_applied) acc.expand++;
      return acc;
    }, { reduce: 0, combine: 0, expand: 0 });
  }

  /**
   * Agrupa changes por tipo.
   */
  static groupChangesByType(changes: TripChange[]) {
    return changes.reduce((acc, change) => {
      const type = change.filter_applied;
      if (!acc[type]) acc[type] = [];
      acc[type].push(change);
      return acc;
    }, {} as Record<FilterType, TripChange[]>);
  }

  /**
   * Obtiene configuración de UI por tipo.
   */
  static getUIConfig(type: FilterType) {
    const configs = {
      reduce: { icon: "📉", color: "blue", label: "Reduce" },
      combine: { icon: "🔗", color: "orange", label: "Combine" },
      expand: { icon: "🔀", color: "orange", label: "Expand" }
    };

    return configs[type];
  }
}

// Componente de notificaciones
export function FilterNotificationHandler() {
  useWebSocket((event) => {
    if (event.type === "step_applied") {
      const { filter_type, trips_affected } = event;
      const config = FilterClassifier.getUIConfig(filter_type);

      toast.success(
        `${trips_affected} trips ${config.label.toLowerCase()}s`,
        {
          icon: config.icon,
          style: { borderLeftColor: config.color }
        }
      );
    }
  });
}

// Componente de estadísticas
export function FilterStatsPanel({ trips }: { trips: TripResponse[] }) {
  const stats = FilterClassifier.countByType(trips);

  return (
    <div className="filter-stats">
      {(["reduce", "combine", "expand"] as FilterType[]).map(type => {
        const config = FilterClassifier.getUIConfig(type);
        const count = stats[type];

        return (
          <div key={type} className="stat-item">
            <span className="icon">{config.icon}</span>
            <span className="label">{config.label}</span>
            <span className="count">{count}</span>
          </div>
        );
      })}
    </div>
  );
}
```

---

## Respuesta a Tu Pregunta

### "¿Cómo clasificar los tipos de filtros para notificaciones?"

**El backend YA lo hace automáticamente:**

1. ✅ Cada `StepResult` incluye `filter_type`
2. ✅ Cada `WebSocket event` incluye `filter_type`
3. ✅ Cada `TripChange` incluye `filter_applied`
4. ✅ Cada `Trip` incluye flags separados por tipo

**El frontend solo necesita:**

```typescript
// Notificaciones
switch (event.filter_type) {
  case "reduce": mostrarNotificacionReduce(); break;
  case "combine": mostrarNotificacionCombine(); break;
  case "expand": mostrarNotificacionExpand(); break;
}

// Tabla
if (trip.reduce_applied) mostrar_icono_reduce();
if (trip.combine_applied) mostrar_icono_combine();
if (trip.expand_applied) mostrar_icono_expand();
```

---

## NO Requiere Cambios en Frontend

La clasificación por tipo **ya funciona correctamente**. El backend provee toda la información necesaria.

**Lo único que cambió:**
- ✅ `trips_modified` ahora es INDEPENDIENTE (solo nuevos)
- ✅ Expand usa sistema de cadenas (puede modificar menos trips)

**Pero la clasificación por tipo sigue igual.**

---

**Última actualización:** 2026-01-29
**Versión:** Ground Filters V2.2
