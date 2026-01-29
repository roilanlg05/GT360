# Guía de Implementación: Notificaciones y Contador de Trips Nuevos

**Fecha:** 2026-01-29
**Versión:** Ground Filters V2.3
**Para:** Frontend Developer
**Deploy:** Activo en backend

---

## Resumen de Cambios

Se implementaron 2 mejoras críticas:

1. ✅ **Fix notificación con 0 trips** (múltiples windows)
2. ✅ **Contador de trips nuevos** ANTES de preview (eligibility mejorado)

---

## Cambio 1: Notificaciones con Doble Conteo

### Problema Resuelto

**ANTES:**
```
Usuario aplica filtro con múltiples windows.
Luego reaplica (cambia config).
Notificación: "0 trips reducidos" ❌ (todos ya tenían el filtro)
```

**AHORA:**
```
Notificación: "50 trips re-aplicados" ✅ (mensaje inteligente)
```

### Campos Nuevos en WebSocket

```typescript
interface StepAppliedEvent {
  type: "step_applied";
  location_id: string;
  airline: string;
  step_id: string;
  filter_type: "reduce" | "combine" | "expand";
  trips_affected: number;  // NUEVOS (sin el filtro antes)
  total_changes: number;   // TOTAL modificados (incluye re-aplicaciones) ← NUEVO
  timestamp: string;
  message: string;  // Mensaje inteligente ← ACTUALIZADO
}
```

### Implementación Frontend

```typescript
// WebSocket handler
websocket.onmessage = (event) => {
  const data = JSON.parse(event.data) as StepAppliedEvent;

  if (data.type === "step_applied") {
    const { filter_type, trips_affected, total_changes } = data;

    // Mostrar notificación inteligente
    if (trips_affected === 0 && total_changes > 0) {
      // Re-aplicación
      toast.info(
        `${total_changes} trips re-aplicados`,
        {
          description: `Filter ${filter_type} updated`,
          icon: getFilterIcon(filter_type)
        }
      );
    } else {
      // Nueva aplicación
      toast.success(
        `${trips_affected} trips ${getFilterLabel(filter_type)}`,
        {
          description: total_changes > trips_affected
            ? `${total_changes} total modificados`
            : undefined,
          icon: getFilterIcon(filter_type)
        }
      );
    }

    // Refetch trips
    await refetchTrips();
  }
};

function getFilterIcon(type: string) {
  switch (type) {
    case "reduce": return "📉";
    case "combine": return "🔗";
    case "expand": return "🔀";
  }
}

function getFilterLabel(type: string) {
  switch (type) {
    case "reduce": return "reducidos";
    case "combine": return "combinados";
    case "expand": return "expandidos";
  }
}
```

### Ejemplo de Uso

```
Primera aplicación:
  WebSocket: { trips_affected: 50, total_changes: 50 }
  Notificación: "50 trips reducidos" ✅

Re-aplicación:
  WebSocket: { trips_affected: 0, total_changes: 50 }
  Notificación: "50 trips re-aplicados" ✅

Aplicación parcial:
  WebSocket: { trips_affected: 20, total_changes: 50 }
  Notificación: "20 trips reducidos (50 total modificados)" ✅
```

---

## Cambio 2: Contador de Trips Nuevos ANTES de Preview

### Endpoint Mejorado

```
GET /v2/locations/{location_id}/airlines/{airline}/filters/eligibility
```

### Query Parameters

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `pick_up_date` | string | ✅ | Fecha en formato YYYY-MM-DD |
| `filter_type` | string | ❌ | Tipo: "reduce", "combine", "expand" ← NUEVO |

### Response (Con filter_type)

```typescript
interface EligibilityResult {
  location_id: string;
  airline: string;
  pick_up_date: string;
  filter_type: string | null;  // ← NUEVO: tipo del filtro consultado
  total_trips: number;
  eligible_trips: number;
  already_filtered: number;  // Con CUALQUIER filtro
  trips_with_filter: number | null;  // ← NUEVO: Con ESTE filtro específico
  trips_new: number | null;          // ← NUEVO: SIN este filtro (nuevos)
  by_hotel: Record<string, number>;
  by_time_range: Record<string, number>;
}
```

### Ejemplo de Request/Response

```typescript
// Request
GET /v2/locations/uuid/airlines/WN/filters/eligibility?pick_up_date=2026-01-28&filter_type=reduce

// Response
{
  "location_id": "uuid",
  "airline": "WN",
  "pick_up_date": "2026-01-28",
  "filter_type": "reduce",       // ← Tipo consultado
  "total_trips": 100,
  "eligible_trips": 100,
  "already_filtered": 30,         // 30 trips con algún filtro
  "trips_with_filter": 20,        // ← 20 trips con reduce_applied=true
  "trips_new": 80,                // ← 80 trips SIN reduce (nuevos)
  "by_hotel": {
    "Marriott": 60,
    "Hilton": 40
  }
}
```

### Implementación Frontend

#### Flujo Completo

```typescript
// 1. Usuario selecciona configuración de filtro
const [filterConfig, setFilterConfig] = useState({
  filter_type: "reduce",
  pick_up_date: "2026-01-28",
  windows: [...]
});

// 2. Verificar eligibility ANTES de mostrar preview
const eligibility = await fetchEligibility(
  locationId,
  airline,
  filterConfig.pick_up_date,
  filterConfig.filter_type  // ← Pasar tipo
);

// 3. Mostrar contador en UI
<Card className="eligibility-info">
  <CardHeader>
    <h3>{getFilterLabel(filterConfig.filter_type)}</h3>
  </CardHeader>
  <CardContent>
    <div className="stats">
      <div className="stat-item">
        <span className="label">Total trips:</span>
        <span className="value">{eligibility.total_trips}</span>
      </div>

      <div className="stat-item">
        <span className="label">Ya con {filterConfig.filter_type}:</span>
        <span className="value">{eligibility.trips_with_filter}</span>
      </div>

      <div className="stat-item highlight">
        <span className="label">Trips nuevos:</span>
        <span className="value">{eligibility.trips_new}</span>  ← IMPORTANTE
      </div>
    </div>
  </CardContent>
</Card>

// 4. Mostrar en botón de preview
<Button onClick={handlePreview} disabled={eligibility.trips_new === 0}>
  Preview Changes
  {eligibility.trips_new > 0 && (
    <Badge variant="blue">{eligibility.trips_new}</Badge>
  )}
</Button>

// 5. Usuario hace preview (confirma el conteo)
const preview = await previewStep(filterConfig);

console.log(
  `Preview confirmó: ${preview.trips_modified} trips nuevos ` +
  `(${preview.summary.total_changes} total)`
);

// 6. Usuario aplica
const result = await applyStep(filterConfig);

// 7. WebSocket notification llega
// (con conteo correcto, sin "0 trips")
```

#### Helper Functions

```typescript
async function fetchEligibility(
  locationId: string,
  airline: string,
  pickUpDate: string,
  filterType?: string
): Promise<EligibilityResult> {
  const url = new URL(`/v2/locations/${locationId}/airlines/${airline}/filters/eligibility`);

  url.searchParams.set("pick_up_date", pickUpDate);

  if (filterType) {
    url.searchParams.set("filter_type", filterType);  // ← Pasar tipo
  }

  const response = await fetch(url.toString());
  return response.json();
}

function getFilterLabel(type: string): string {
  const labels = {
    reduce: "Reduce",
    combine: "Combine",
    expand: "Expand"
  };
  return labels[type] || type;
}
```

---

## Comparación: Antes vs Ahora

### Sin filter_type (Comportamiento Anterior)

```typescript
GET /filters/eligibility?pick_up_date=2026-01-28

Response:
{
  "total_trips": 100,
  "already_filtered": 30  // Con CUALQUIER filtro (no específico)
}

// No se puede saber cuántos tienen Reduce específicamente
```

### Con filter_type (Nuevo)

```typescript
GET /filters/eligibility?pick_up_date=2026-01-28&filter_type=reduce

Response:
{
  "filter_type": "reduce",
  "total_trips": 100,
  "trips_with_filter": 20,  // ← Con reduce_applied=true
  "trips_new": 80            // ← SIN reduce (nuevos)
}

// Ahora SÍ sabemos cuántos son nuevos para Reduce
```

---

## Testing

### Test 1: Notificación con Múltiples Windows

```bash
# Primera aplicación
POST /filters/step
Body: {
  "filter_type": "reduce",
  "windows": [
    { "start": "08:00", "end": "12:00" },
    { "start": "14:00", "end": "18:00" }
  ]
}

WebSocket recibido:
{
  "trips_affected": 50,
  "total_changes": 50,
  "message": "Filter applied: reduce (50 new trips)"
}

# Re-aplicación (cambio config)
POST /filters/step
Body: { ... }

WebSocket recibido:
{
  "trips_affected": 0,     // Ninguno nuevo
  "total_changes": 50,     // Pero 50 modificados
  "message": "Filter re-applied: reduce (50 trips updated)"
}
```

### Test 2: Eligibility por Tipo

```bash
GET /filters/eligibility?pick_up_date=2026-01-28&filter_type=reduce

Response:
{
  "filter_type": "reduce",
  "total_trips": 100,
  "trips_with_filter": 40,
  "trips_new": 60
}

GET /filters/eligibility?pick_up_date=2026-01-28&filter_type=combine

Response:
{
  "filter_type": "combine",
  "total_trips": 100,
  "trips_with_filter": 20,
  "trips_new": 80
}
```

---

## Componente de Ejemplo (React)

```typescript
import { useState, useEffect } from "react";
import { useWebSocket } from "@/hooks/use-websocket";

export function FilterConfigPanel({ locationId, airline, date }: Props) {
  const [filterType, setFilterType] = useState<FilterType>("reduce");
  const [eligibility, setEligibility] = useState<EligibilityResult | null>(null);

  // Cargar eligibility cuando cambia el tipo
  useEffect(() => {
    loadEligibility();
  }, [filterType, date]);

  async function loadEligibility() {
    const result = await fetchEligibility(locationId, airline, date, filterType);
    setEligibility(result);
  }

  // WebSocket notifications
  useWebSocket((event) => {
    if (event.type === "step_applied") {
      const { filter_type, trips_affected, total_changes } = event;

      // Mensaje inteligente
      if (trips_affected === 0 && total_changes > 0) {
        toast.info(`${total_changes} trips re-aplicados (${filter_type})`);
      } else {
        toast.success(`${trips_affected} trips nuevos (${filter_type})`);
      }

      // Recargar eligibility después de apply
      loadEligibility();
    }
  });

  return (
    <div className="filter-config">
      {/* Selector de tipo */}
      <Select value={filterType} onChange={setFilterType}>
        <option value="reduce">Reduce</option>
        <option value="combine">Combine</option>
        <option value="expand">Expand</option>
      </Select>

      {/* Estadísticas */}
      {eligibility && (
        <div className="stats">
          <p>Total trips: {eligibility.total_trips}</p>
          <p>Ya con {filterType}: {eligibility.trips_with_filter}</p>
          <p className="highlight">
            Trips nuevos: {eligibility.trips_new}
          </p>
        </div>
      )}

      {/* Botón de preview con badge */}
      <Button
        onClick={handlePreview}
        disabled={!eligibility || eligibility.trips_new === 0}
      >
        Preview Changes
        {eligibility && eligibility.trips_new > 0 && (
          <Badge>{eligibility.trips_new}</Badge>
        )}
      </Button>
    </div>
  );
}
```

---

## Checklist de Implementación

### Backend ✅ (Ya Implementado)

- [x] Modificar `_send_step_notification()` con `total_changes`
- [x] Actualizar llamada en `apply_step()`
- [x] Mejorar `get_eligibility()` con `filter_type`
- [x] Actualizar modelo `EligibilityResult`
- [x] Actualizar endpoint en router
- [x] Deploy del backend

### Frontend ⏳ (Por Implementar)

- [ ] Actualizar interface `StepAppliedEvent` con `total_changes`
- [ ] Modificar WebSocket handler con mensaje inteligente
- [ ] Agregar `filter_type` a llamadas de eligibility
- [ ] Actualizar interface `EligibilityResult` con campos nuevos
- [ ] Mostrar contador de trips nuevos en UI
- [ ] Agregar badge al botón de preview

---

## Código de Referencia

### Types (TypeScript)

```typescript
// events.ts
export interface StepAppliedEvent {
  type: "step_applied";
  location_id: string;
  airline: string;
  step_id: string;
  filter_type: FilterType;
  trips_affected: number;
  total_changes: number;  // ← NUEVO
  timestamp: string;
  message: string;
}

// filter-models.ts
export interface EligibilityResult {
  location_id: string;
  airline: string;
  pick_up_date: string;
  filter_type: FilterType | null;  // ← NUEVO
  total_trips: number;
  eligible_trips: number;
  already_filtered: number;
  trips_with_filter: number | null;  // ← NUEVO
  trips_new: number | null;          // ← NUEVO
  by_hotel: Record<string, number>;
}
```

### API Calls

```typescript
// api/filters.ts
export async function getEligibility(
  locationId: string,
  airline: string,
  pickUpDate: string,
  filterType?: FilterType
): Promise<EligibilityResult> {
  const params = new URLSearchParams({
    pick_up_date: pickUpDate
  });

  if (filterType) {
    params.set("filter_type", filterType);
  }

  const response = await fetch(
    `/v2/locations/${locationId}/airlines/${airline}/filters/eligibility?${params}`
  );

  return response.json();
}
```

### WebSocket Hook

```typescript
// hooks/use-filter-notifications.ts
export function useFilterNotifications() {
  const { lastMessage } = useWebSocket();

  useEffect(() => {
    if (!lastMessage) return;

    const event = JSON.parse(lastMessage.data);

    if (event.type === "step_applied") {
      handleStepApplied(event);
    } else if (event.type === "step_reverted") {
      handleStepReverted(event);
    }
  }, [lastMessage]);

  function handleStepApplied(event: StepAppliedEvent) {
    const { filter_type, trips_affected, total_changes } = event;

    if (trips_affected === 0 && total_changes > 0) {
      // Re-aplicación
      toast.info(`${total_changes} trips re-aplicados`, {
        description: `Filter ${filter_type} updated`
      });
    } else {
      // Nueva aplicación
      const icon = getFilterIcon(filter_type);
      const label = getFilterLabel(filter_type);

      toast.success(`${trips_affected} trips ${label}`, {
        icon,
        description: total_changes > trips_affected
          ? `${total_changes} total modificados`
          : undefined
      });
    }
  }
}
```

---

## Casos de Uso

### Caso 1: Primera Aplicación

```typescript
// 1. Cargar eligibility
const elig = await getEligibility(loc, airline, date, "reduce");
// { trips_new: 50, trips_with_filter: 0 }

// 2. Mostrar contador
"50 trips nuevos se aplicarán" ✅

// 3. Aplicar
await applyStep({ filter_type: "reduce", ... });

// 4. WebSocket notification
// { trips_affected: 50, total_changes: 50 }
"50 trips reducidos" ✅
```

### Caso 2: Re-aplicación

```typescript
// 1. Cargar eligibility
const elig = await getEligibility(loc, airline, date, "reduce");
// { trips_new: 0, trips_with_filter: 50 }

// 2. Mostrar contador
"0 trips nuevos (50 ya filtrados)" ✅

// 3. Aplicar (cambio config)
await applyStep({ filter_type: "reduce", ... });

// 4. WebSocket notification
// { trips_affected: 0, total_changes: 50 }
"50 trips re-aplicados" ✅
```

### Caso 3: Aplicación Parcial

```typescript
// 1. Cargar eligibility
const elig = await getEligibility(loc, airline, date, "combine");
// { trips_new: 30, trips_with_filter: 20 }

// 2. Mostrar contador
"30 trips nuevos (20 ya combinados)" ✅

// 3. Aplicar
await applyStep({ filter_type: "combine", ... });

// 4. WebSocket notification
// { trips_affected: 30, total_changes: 50 }
"30 trips combinados (50 total)" ✅
```

---

## Backward Compatibility

### ✅ SÍ es compatible

**Campos existentes NO cambiaron:**
- `trips_affected` sigue existiendo
- `total_trips`, `eligible_trips` siguen existiendo

**Campos nuevos son opcionales:**
- `total_changes` en WebSocket (puede ser ignorado)
- `filter_type`, `trips_with_filter`, `trips_new` en eligibility (opcionales)

**Si el frontend NO se actualiza:**
- Sigue funcionando
- Pero verá "0 trips" en re-aplicaciones

---

## Migración Gradual

### Paso 1: Actualizar Types

```typescript
// Agregar campos opcionales
interface StepAppliedEvent {
  // ... campos existentes ...
  total_changes?: number;  // Opcional por ahora
}

interface EligibilityResult {
  // ... campos existentes ...
  filter_type?: string | null;
  trips_with_filter?: number | null;
  trips_new?: number | null;
}
```

### Paso 2: Actualizar WebSocket Handler

```typescript
// Leer total_changes si existe
const totalChanges = event.total_changes || event.trips_affected;
```

### Paso 3: Actualizar Eligibility Calls

```typescript
// Agregar filter_type gradualmente
const elig = await getEligibility(loc, airline, date, "reduce");
```

### Paso 4: Actualizar UI

```typescript
// Mostrar trips_new si existe
{elig.trips_new !== null && (
  <p>Trips nuevos: {elig.trips_new}</p>
)}
```

---

## Resumen Para Frontend Developer

### Lo Que Cambió

1. **WebSocket `step_applied`:**
   - Campo nuevo: `total_changes`
   - Mensaje inteligente (detecta re-aplicaciones)

2. **Endpoint `eligibility`:**
   - Query param nuevo: `filter_type` (opcional)
   - Campos nuevos en response: `filter_type`, `trips_with_filter`, `trips_new`

### Lo Que Debe Hacer

**MÍNIMO (funcional):**
- Agregar campos opcionales a interfaces
- Funciona sin cambios adicionales

**RECOMENDADO (UX mejorado):**
- Usar `total_changes` para mensajes inteligentes
- Llamar eligibility con `filter_type`
- Mostrar contador de trips nuevos
- Agregar badge al botón de preview

---

**Deploy:** 2026-01-29 19:04 UTC
**Breaking Changes:** Ninguno
**Backward Compatible:** Sí
