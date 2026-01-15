# Guía Frontend: Sistema de Filtros de Trips (Outbound)

## Resumen

El sistema permite ajustar el `pickup_time` de trips tipo **Outbound** con status **SCHEDULED** mediante tres filtros independientes:

| Filtro | Qué hace |
|--------|----------|
| **Reduce** | Resta minutos fijos al pickup_time |
| **Combine** | Junta pares de trips cercanos al punto medio |
| **Expand** | Separa pares de trips que están muy juntos |

---

## Criterios de Elegibilidad

Los filtros **SOLO** aplican a trips que cumplan **TODOS** estos criterios:

| Criterio | Valor |
|----------|-------|
| `trip_type` | `outbound` |
| `status` | `scheduled` |
| `location_id` | El especificado en la URL |
| `airline` | El especificado en la URL |

---

## Endpoints Disponibles

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/v1/locations/{location_id}/airlines/{airline}/trips/filters/preview` | Simula cambios sin aplicar |
| POST | `/v1/locations/{location_id}/airlines/{airline}/trips/filters/apply` | Aplica y guarda cambios |
| POST | `/v1/locations/{location_id}/airlines/{airline}/trips/filters/revert` | Revierte a valores originales |

---

## 1. Preview (Simulación)

**Endpoint:** `POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/preview`

Permite ver los cambios propuestos **antes de aplicarlos**. Útil para que el manager valide.

### Path Parameters

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `location_id` | UUID | ID de la location |
| `airline` | string | Código de aerolínea (ej: "WN", "AA") |

### Request Body

```typescript
interface FilterRequest {
  reduce?: {
    enabled: boolean;
    minutes_to_reduce: number;      // 0-120 minutos a restar
    hotel_names?: string[] | null;  // null = ALL hoteles
    time_range?: {
      start: string;  // "HH:MM" ej: "05:00"
      end: string;    // "HH:MM" ej: "10:00"
    } | null;
  };

  combine?: {
    enabled: boolean;
    min_gap: number;                // ej: 15 (minutos mínimos entre trips)
    max_gap: number;                // ej: 20 (minutos máximos entre trips)
    hotel_names?: string[] | null;
    time_range?: { start: string; end: string; } | null;
  };

  expand?: {
    enabled: boolean;
    min_gap: number;                // ej: 21
    max_gap: number;                // ej: 30
    max_shift: number;              // ej: 10 (máx minutos a mover cada trip)
    hotel_names?: string[] | null;
    time_range?: { start: string; end: string; } | null;
  };
}
```

### Response

```typescript
interface FilterPreviewResult {
  location_id: string;
  airline: string;
  changes: TripChange[];
  exclusions: FilterExclusion[];
  summary: {
    reduce: number;
    combine: number;
    expand: number;
    excluded: number;
  };
  total_trips_evaluated: number;
  eligible_trips: number;
}

interface TripChange {
  trip_id: string;
  original_time: string;    // "HH:MM:SS"
  new_time: string;         // "HH:MM:SS"
  filter_applied: "reduce" | "combine" | "expand";
  hotel_name: string;
  pick_up_date: string;
  airline: string;
}

interface FilterExclusion {
  operation: string;        // "expand(uuid1, uuid2)"
  trip_ids: string[];
  reason: string;
  gap_before: number;
  gap_after: number;
}
```

### Ejemplo Request

```javascript
const locationId = "550e8400-e29b-41d4-a716-446655440000";
const airline = "WN";

const response = await fetch(
  `/v1/locations/${locationId}/airlines/${airline}/trips/filters/preview`,
  {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({
      reduce: {
        enabled: true,
        minutes_to_reduce: 10,
        hotel_names: null,  // ALL hoteles
        time_range: {
          start: "05:00",
          end: "10:00"
        }
      },
      combine: {
        enabled: true,
        min_gap: 15,
        max_gap: 20,
        hotel_names: ["Hilton Downtown", "Marriott Airport"],
        time_range: null  // ALL horarios
      },
      expand: {
        enabled: false
      }
    })
  }
);

const preview = await response.json();
console.log(`Location: ${preview.location_id}`);
console.log(`Airline: ${preview.airline}`);
console.log(`Se modificarán ${preview.changes.length} trips`);
console.log(`Excluidos: ${preview.exclusions.length}`);
```

---

## 2. Apply (Aplicar Cambios)

**Endpoint:** `POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/apply`

Aplica los filtros y **persiste los cambios** en la base de datos.

### Path Parameters

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `location_id` | UUID | ID de la location |
| `airline` | string | Código de aerolínea (ej: "WN", "AA") |

### Request Body

Mismo formato que Preview.

### Response

```typescript
interface FilterApplyResult {
  batch_id: string;         // UUID para revertir este batch
  location_id: string;
  airline: string;
  changes_applied: number;
  exclusions: FilterExclusion[];
  log: LogEntry[];
  summary: {
    reduce: number;
    combine: number;
    expand: number;
    excluded: number;
  };
}

interface LogEntry {
  trip_id?: string;
  action: "modified" | "exclusion";
  filter?: string;
  original_time?: string;
  new_time?: string;
  hotel?: string;
  airline?: string;
  reason?: string;
}
```

### Ejemplo Request

```javascript
const locationId = "550e8400-e29b-41d4-a716-446655440000";
const airline = "WN";

const response = await fetch(
  `/v1/locations/${locationId}/airlines/${airline}/trips/filters/apply`,
  {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({
      combine: {
        enabled: true,
        min_gap: 15,
        max_gap: 20
      }
    })
  }
);

const result = await response.json();
console.log(`Batch ID: ${result.batch_id}`);  // Guardar para revertir
console.log(`Airline: ${result.airline}`);
console.log(`Trips modificados: ${result.changes_applied}`);
```

---

## 3. Revert (Revertir Cambios)

**Endpoint:** `POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/revert`

Restaura los `pickup_time` originales.

### Path Parameters

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `location_id` | UUID | ID de la location |
| `airline` | string | Código de aerolínea (ej: "WN", "AA") |

### Query Parameters

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `batch_id` | string (opcional) | Si se proporciona, solo revierte ese batch. Si es null, revierte TODOS. |

### Response

```typescript
interface FilterRevertResult {
  trips_reverted: number;
  batch_ids_reverted: string[];
}
```

### Ejemplos

```javascript
const locationId = "550e8400-e29b-41d4-a716-446655440000";
const airline = "WN";

// Revertir un batch específico
await fetch(
  `/v1/locations/${locationId}/airlines/${airline}/trips/filters/revert?batch_id=${batchId}`,
  {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` }
  }
);

// Revertir TODOS los filtros de la location+airline
await fetch(
  `/v1/locations/${locationId}/airlines/${airline}/trips/filters/revert`,
  {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` }
  }
);
```

---

## Cómo Funcionan los Filtros

### Reduce (Reducir Lead Time)

Resta un número fijo de minutos al `pickup_time`.

```
Ejemplo: minutes_to_reduce = 10
Trip A: 08:30 → 08:20
Trip B: 09:15 → 09:05
```

### Combine (Combinar/Contraer)

Si dos trips consecutivos tienen un gap dentro del rango `[min_gap, max_gap]`, ambos se mueven al **punto medio**.

```
Ejemplo: min_gap=15, max_gap=20
Trip A: 08:00  ─┐
                ├─► Ambos van a 08:08 (redondeado a 08:10)
Trip B: 08:17  ─┘

Gap original: 17 minutos (está en rango 15-20)
Midpoint: (08:00 + 08:17) / 2 = 08:08 → redondeado a 08:10
```

### Expand (Expandir/Separar)

Si dos trips tienen un gap en `[min_gap, max_gap]`, se separan:
- El trip **más temprano** se mueve hacia atrás (1/3 del max_shift)
- El trip **más tarde** se mueve hacia adelante (2/3 del max_shift)

```
Ejemplo: min_gap=21, max_gap=30, max_shift=15
Trip A: 08:00 → 07:55 (se mueve 5 min hacia atrás = 15/3)
Trip B: 08:25 → 08:35 (se mueve 10 min hacia adelante = 15-5)

Gap original: 25 minutos
Gap nuevo: 40 minutos
```

---

## Reglas Importantes

### Regla A: Un trip modificado no se vuelve a modificar

En una misma ejecución, si un trip ya fue modificado por un filtro, NO será tocado por otro filtro.

```
Ejemplo: Reduce modifica Trip A
         Combine intenta modificar Trip A → IGNORADO
```

### Regla B: No-Collision Rule (Expand)

Antes de aplicar Expand, el sistema simula el resultado. Si el nuevo gap con un vecino cae dentro del rango de Combine, la operación se **cancela** y se registra como exclusión.

```
Ejemplo:
- Combine: 15-20 min
- Expand: 21-30 min

Si Expand(A,B) causaría que B quede a 18 min de C:
→ Operación cancelada (colisionaría con Combine)
→ Se registra en exclusions[]
```

### Redondeo a Múltiplos de 5

**Todos** los resultados se redondean automáticamente a múltiplos de 5 minutos.

```
08:03 → 08:05
08:07 → 08:05
08:08 → 08:10
```

---

## Filtros Opcionales por Filtro

Cada filtro puede restringirse por:

### 1. Hotel Names (por defecto: ALL)

```javascript
hotel_names: ["Hilton Downtown", "Marriott"]  // Solo estos hoteles
hotel_names: null  // TODOS los hoteles
```

### 2. Time Range (por defecto: ALL)

```javascript
time_range: {
  start: "05:00",
  end: "10:00"
}  // Solo trips en esta ventana

time_range: null  // TODOS los horarios
```

**Nota:** Soporta cruce de medianoche:
```javascript
time_range: {
  start: "22:00",
  end: "02:00"
}  // Trips de 22:00 a 23:59 y de 00:00 a 02:00
```

---

## Flujo Recomendado en UI

```
1. Usuario selecciona Location y Airline
        ↓
2. Usuario configura filtros en formulario
        ↓
3. Click "Preview" → POST /filters/preview
        ↓
4. Mostrar tabla con cambios propuestos
   - original_time vs new_time
   - hotel_name
   - filter_applied
        ↓
5. Mostrar exclusiones (si las hay)
   - reason por qué no se aplicó
        ↓
6. Usuario confirma → POST /filters/apply
        ↓
7. Guardar batch_id en estado/localStorage
        ↓
8. Opción "Deshacer" → POST /filters/revert?batch_id=xxx
```

---

## TypeScript Types (Copiar a Frontend)

```typescript
// Request Types
export interface TimeRange {
  start: string;  // "HH:MM"
  end: string;
}

export interface ReduceFilterConfig {
  enabled: boolean;
  minutes_to_reduce: number;
  hotel_names?: string[] | null;
  time_range?: TimeRange | null;
}

export interface CombineFilterConfig {
  enabled: boolean;
  min_gap: number;
  max_gap: number;
  hotel_names?: string[] | null;
  time_range?: TimeRange | null;
}

export interface ExpandFilterConfig {
  enabled: boolean;
  min_gap: number;
  max_gap: number;
  max_shift: number;
  hotel_names?: string[] | null;
  time_range?: TimeRange | null;
}

export interface FilterRequest {
  reduce?: ReduceFilterConfig;
  combine?: CombineFilterConfig;
  expand?: ExpandFilterConfig;
}

// Response Types
export interface TripChange {
  trip_id: string;
  original_time: string;
  new_time: string;
  filter_applied: 'reduce' | 'combine' | 'expand';
  hotel_name: string;
  pick_up_date: string | null;
  airline: string | null;
}

export interface FilterExclusion {
  operation: string;
  trip_ids: string[];
  reason: string;
  gap_before: number;
  gap_after: number;
}

export interface FilterPreviewResult {
  location_id: string;
  airline: string;
  changes: TripChange[];
  exclusions: FilterExclusion[];
  summary: {
    reduce: number;
    combine: number;
    expand: number;
    excluded: number;
  };
  total_trips_evaluated: number;
  eligible_trips: number;
}

export interface FilterApplyResult {
  batch_id: string;
  location_id: string;
  airline: string;
  changes_applied: number;
  exclusions: FilterExclusion[];
  log: Record<string, unknown>[];
  summary: {
    reduce: number;
    combine: number;
    expand: number;
    excluded: number;
  };
}

export interface FilterRevertResult {
  trips_reverted: number;
  batch_ids_reverted: string[];
}
```

---

## Errores Comunes

| Código | Mensaje | Solución |
|--------|---------|----------|
| 400 | "ID de location inválido" | Verificar UUID format |
| 400 | "Airline inválido" | El código debe tener al menos 2 caracteres |
| 400 | "max_gap must be >= min_gap" | Corregir valores |
| 404 | "Location no encontrada" | Verificar location_id |

---

## Notas Finales

1. **Solo afecta trips Outbound con status SCHEDULED** - Los trips Inbound, Ground, o con otro status no son modificados
2. **Requiere location_id y airline** - Ambos son obligatorios en la URL
3. **El campo modificado es únicamente `pick_up_time`** - No se tocan otros campos
4. **Los cambios son reversibles** - Siempre se guarda el valor original
5. **Preview es gratuito** - No modifica nada, usar para validar
6. **Batch ID es importante** - Guardarlo para poder revertir después
7. **Airline se normaliza** - Se convierte a mayúsculas automáticamente (wn → WN)
