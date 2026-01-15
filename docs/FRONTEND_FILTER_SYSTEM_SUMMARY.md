# Sistema de Filtros de Trips - Resumen para Frontend

**Fecha:** 2026-01-14
**Estado:** Implementado y funcionando

---

## 1. Resumen Ejecutivo

El sistema de filtros para trips Outbound/Ground está **completamente implementado** en el backend. Permite ajustar el `pickup_time` de los trips mediante tres filtros independientes.

---

## 2. Endpoints Disponibles

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| POST | `/v1/locations/{location_id}/trips/filters/preview` | Simula cambios sin aplicar |
| POST | `/v1/locations/{location_id}/trips/filters/apply` | Aplica y guarda cambios |
| POST | `/v1/locations/{location_id}/trips/filters/revert` | Revierte a valores originales |

**Autenticacion:** Todos requieren token JWT con rol `manager`.

---

## 3. Filtros Disponibles

### 3.1 Reduce (Reducir Lead Time)
Resta un numero fijo de minutos al `pickup_time`.

```
Ejemplo: minutes_to_reduce = 10
Trip A: 08:30 -> 08:20
Trip B: 09:15 -> 09:05
```

### 3.2 Combine (Combinar/Contraer)
Si dos trips consecutivos tienen un gap dentro del rango `[min_gap, max_gap]`, ambos se mueven al punto medio.

```
Ejemplo: min_gap=15, max_gap=20
Trip A: 08:00 --+
               +--> Ambos van a 08:10 (redondeado)
Trip B: 08:17 --+

Gap original: 17 minutos (esta en rango 15-20)
Midpoint: (08:00 + 08:17) / 2 = 08:08 -> redondeado a 08:10
```

### 3.3 Expand (Expandir/Separar)
Separa pares de trips que estan muy juntos:
- Trip mas temprano: se mueve hacia atras (1/3 del max_shift)
- Trip mas tarde: se mueve hacia adelante (2/3 del max_shift)

```
Ejemplo: min_gap=21, max_gap=30, max_shift=15
Trip A: 08:00 -> 07:55 (se mueve 5 min hacia atras)
Trip B: 08:25 -> 08:35 (se mueve 10 min hacia adelante)

Gap original: 25 minutos
Gap nuevo: 40 minutos
```

---

## 4. Request Body (TypeScript)

```typescript
interface TimeRange {
  start: string;  // "HH:MM" ej: "05:00"
  end: string;    // "HH:MM" ej: "10:00"
}

interface ReduceFilterConfig {
  enabled: boolean;
  minutes_to_reduce: number;      // 0-120 minutos
  hotel_names?: string[] | null;  // null = ALL hoteles
  time_range?: TimeRange | null;  // null = ALL horarios
}

interface CombineFilterConfig {
  enabled: boolean;
  min_gap: number;                // ej: 15 (minutos)
  max_gap: number;                // ej: 20 (minutos)
  hotel_names?: string[] | null;
  time_range?: TimeRange | null;
}

interface ExpandFilterConfig {
  enabled: boolean;
  min_gap: number;                // ej: 21
  max_gap: number;                // ej: 30
  max_shift: number;              // ej: 15 (max minutos a mover)
  hotel_names?: string[] | null;
  time_range?: TimeRange | null;
}

interface FilterRequest {
  target_date?: string;           // "YYYY-MM-DD" opcional
  reduce?: ReduceFilterConfig;
  combine?: CombineFilterConfig;
  expand?: ExpandFilterConfig;
}
```

---

## 5. Responses (TypeScript)

### 5.1 Preview Response

```typescript
interface TripChange {
  trip_id: string;
  original_time: string;    // "HH:MM:SS"
  new_time: string;         // "HH:MM:SS"
  filter_applied: "reduce" | "combine" | "expand";
  hotel_name: string;
  pick_up_date: string | null;
}

interface FilterExclusion {
  operation: string;        // "expand(uuid1, uuid2)"
  trip_ids: string[];
  reason: string;
  gap_before: number;
  gap_after: number;
}

interface FilterPreviewResult {
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
```

### 5.2 Apply Response

```typescript
interface FilterApplyResult {
  batch_id: string;         // UUID - GUARDAR para revertir
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
  reason?: string;
}
```

### 5.3 Revert Response

```typescript
interface FilterRevertResult {
  trips_reverted: number;
  batch_ids_reverted: string[];
}
```

---

## 6. Ejemplos de Uso

### 6.1 Preview (Simulacion)

```typescript
const response = await fetch(
  `${API_URL}/v1/locations/${locationId}/trips/filters/preview`,
  {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({
      target_date: "2025-12-15",
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
console.log(`Se modificaran ${preview.changes.length} trips`);
console.log(`Excluidos: ${preview.exclusions.length}`);
```

### 6.2 Apply (Aplicar Cambios)

```typescript
const response = await fetch(
  `${API_URL}/v1/locations/${locationId}/trips/filters/apply`,
  {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({
      target_date: "2025-12-15",
      combine: {
        enabled: true,
        min_gap: 15,
        max_gap: 20
      }
    })
  }
);

const result = await response.json();
console.log(`Batch ID: ${result.batch_id}`);  // GUARDAR ESTO
console.log(`Trips modificados: ${result.changes_applied}`);

// Guardar batch_id para poder revertir despues
localStorage.setItem('lastFilterBatchId', result.batch_id);
```

### 6.3 Revert (Deshacer)

```typescript
// Revertir un batch especifico
const batchId = localStorage.getItem('lastFilterBatchId');
await fetch(
  `${API_URL}/v1/locations/${locationId}/trips/filters/revert?batch_id=${batchId}`,
  {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` }
  }
);

// Revertir TODOS los filtros de la location
await fetch(
  `${API_URL}/v1/locations/${locationId}/trips/filters/revert`,
  {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` }
  }
);
```

---

## 7. Reglas de Negocio

### Regla A: Un trip modificado no se vuelve a modificar
En una misma ejecucion, si un trip ya fue modificado por un filtro, NO sera tocado por otro filtro.

```
Ejemplo: Reduce modifica Trip A
         Combine intenta modificar Trip A -> IGNORADO
```

### Regla B: No-Collision Rule (Expand)
Antes de aplicar Expand, el sistema simula el resultado. Si el nuevo gap con un vecino cae dentro del rango de Combine, la operacion se cancela y se registra como exclusion.

### Regla C: Redondeo a Multiplos de 5
Todos los resultados se redondean automaticamente a multiplos de 5 minutos.

```
08:03 -> 08:05
08:07 -> 08:05
08:08 -> 08:10
```

### Regla D: Solo Outbound/Ground
Los trips **Inbound** NO son modificados por los filtros. Solo aplica a Outbound y Ground.

### Regla E: Proteccion contra Apply Repetido
Si el manager ejecuta "Apply" mas de una vez, los filtros se calculan tomando como referencia el `original_pick_up_time`, evitando drift acumulativo.

---

## 8. Campos Nuevos en Trip

El modelo Trip ahora incluye estos campos para tracking de filtros:

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `original_pick_up_time` | TIME | Hora original antes del filtro (NULL si nunca filtrado) |
| `filter_applied` | VARCHAR(20) | Filtro aplicado: "reduce", "combine", "expand" |
| `filter_batch_id` | UUID | ID del batch para agrupar/revertir |
| `filtered_at` | TIMESTAMPTZ | Timestamp cuando se aplico el filtro |

Estos campos se envian en el snapshot del WebSocket y en las respuestas de la API.

---

## 9. Flujo Recomendado en UI

```
1. Usuario configura filtros en formulario
        |
        v
2. Click "Preview" -> POST /filters/preview
        |
        v
3. Mostrar tabla con cambios propuestos
   - original_time vs new_time
   - hotel_name
   - filter_applied
        |
        v
4. Mostrar exclusiones (si las hay)
   - reason por que no se aplico
        |
        v
5. Usuario confirma -> POST /filters/apply
        |
        v
6. Guardar batch_id en estado/localStorage
        |
        v
7. Opcion "Deshacer" -> POST /filters/revert?batch_id=xxx
```

---

## 10. Errores Comunes

| Codigo | Mensaje | Solucion |
|--------|---------|----------|
| 400 | "ID de location invalido" | Verificar UUID format |
| 400 | "Formato de fecha invalido" | Usar YYYY-MM-DD |
| 400 | "max_gap must be >= min_gap" | Corregir valores |
| 401 | "Invalid token" | Renovar token JWT |
| 404 | "Location no encontrada" | Verificar location_id |

---

## 11. Cambios Recientes (2026-01-14)

### Fixes aplicados:
1. **Sintaxis psqlmodel corregida** - Cambiado `Trip.select()` a `Select(Trip)` y `.where()` a `.Where()`
2. **Columnas agregadas a DB** - Se ejecuto migracion para agregar las 4 columnas de tracking
3. **Indices creados** - Se agregaron indices para optimizar queries de filtros

### Estado actual:
- Endpoint `/filters/preview` -> Funcionando
- Endpoint `/filters/apply` -> Funcionando
- Endpoint `/filters/revert` -> Funcionando
- WebSocket snapshot incluye campos de filtro -> Funcionando

---

## 12. Notas Importantes

1. **Solo afecta trips Outbound/Ground** - Los trips Inbound no son modificados
2. **El campo modificado es unicamente `pick_up_time`** - No se tocan otros campos
3. **Los cambios son reversibles** - Siempre se guarda el valor original
4. **Preview es gratuito** - No modifica nada, usar para validar
5. **Batch ID es importante** - Guardarlo para poder revertir despues
6. **Time range soporta cruce de medianoche** - ej: 22:00 a 02:00

---

## 13. Contacto

Backend: Claude Code / GT360 Team
