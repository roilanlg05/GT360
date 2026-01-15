Roilan Lambert, [01/13/2026 5:16 pm]
# Guía Frontend: Sistema de Filtros de Trips (Outbound/Ground)

## Resumen

El sistema permite ajustar el pickup_time de trips tipo Outbound y Ground mediante tres filtros independientes:

| Filtro | Qué hace |
|--------|----------|
| Reduce | Resta minutos fijos al pickup_time |
| Combine | Junta pares de trips cercanos al punto medio |
| Expand | Separa pares de trips que están muy juntos |

---

## Endpoints Disponibles

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | /v1/locations/{location_id}/trips/filters/preview | Simula cambios sin aplicar |
| POST | /v1/locations/{location_id}/trips/filters/apply | Aplica y guarda cambios |
| POST | /v1/locations/{location_id}/trips/filters/revert | Revierte a valores originales |

---

## 1. Preview (Simulación)

Endpoint: POST /v1/locations/{location_id}/trips/filters/preview

Permite ver los cambios propuestos antes de aplicarlos. Útil para que el manager valide.

### Request Body

interface FilterRequest {
  target_date?: string;  // "YYYY-MM-DD" - opcional, filtra por fecha específica

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

### Response

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

interface TripChange {
  trip_id: string;
  original_time: string;    // "HH:MM:SS"
  new_time: string;         // "HH:MM:SS"
  filter_applied: "reduce" | "combine" | "expand";
  hotel_name: string;
  pick_up_date: string;
}

interface FilterExclusion {
  operation: string;        // "expand(uuid1, uuid2)"
  trip_ids: string[];
  reason: string;
  gap_before: number;
  gap_after: number;
}

### Ejemplo Request

const response = await fetch(`/v1/locations/${locationId}/trips/filters/preview`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({
    target_date: "2025-01-15",
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
});

const preview = await response.json();
console.log(`Se modificarán ${preview.changes.length} trips`);
console.log(`Excluidos: ${preview.exclusions.length}`);

---

## 2. Apply (Aplicar Cambios)

Endpoint: POST /v1/locations/{location_id}/trips/filters/apply

Aplica los filtros y persiste los cambios en la base de datos.

*Protección contra “Apply” repetido (pégalo justo después del párrafo anterior)

Protección ante “Apply” repetido (no acumulación de cambios)
Si el manager ejecuta “Apply” más de una vez con la misma configuración o en el mismo conjunto objetivo, el backend no debe “seguir restando/sumando” minutos acumulativamente sobre un horario ya filtrado. Los filtros deben calcularse de forma estable tomando como referencia el pickup_time original, de manera que repetir “Apply” con los mismos parámetros no genere drift ni duplicación de cambios. Esta regla trabaja junto con la separación “Original vs Filtrado” y con el sistema de batch_id/revert.

### Request Body

Mismo formato que Preview.

### Response

Roilan Lambert, [01/13/2026 5:16 pm]
interface FilterApplyResult {
  batch_id: string;         // UUID para revertir este batch
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

### Ejemplo Request

const response = await fetch(`/v1/locations/${locationId}/trips/filters/apply`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({
    target_date: "2025-01-15",
    combine: {
      enabled: true,
      min_gap: 15,
      max_gap: 20
    }
  })
});

const result = await response.json();
console.log(`Batch ID: ${result.batch_id}`);  // Guardar para revertir
console.log(`Trips modificados: ${result.changes_applied}`);

---

## 3. Revert (Revertir Cambios)

Endpoint: POST /v1/locations/{location_id}/trips/filters/revert

Restaura los pickup_time originales.

### Query Parameters

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| batch_id | string (opcional) | Si se proporciona, solo revierte ese batch. Si es null, revierte TODOS. |

### Response

interface FilterRevertResult {
  trips_reverted: number;
  batch_ids_reverted: string[];
}

### Ejemplos

// Revertir un batch específico
await fetch(`/v1/locations/${locationId}/trips/filters/revert?batch_id=${batchId}`, {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${token}` }
});

// Revertir TODOS los filtros de la location
await fetch(`/v1/locations/${locationId}/trips/filters/revert`, {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${token}` }
});

---

## Cómo Funcionan los Filtros

### Reduce (Reducir Lead Time)

Resta un número fijo de minutos al pickup_time.

Ejemplo: minutes_to_reduce = 10
Trip A: 08:30 → 08:20
Trip B: 09:15 → 09:05

### Combine (Combinar/Contraer)

Si dos trips consecutivos tienen un gap dentro del rango [min_gap, max_gap], ambos se mueven al punto medio.

Ejemplo: min_gap=15, max_gap=20
Trip A: 08:00  ─┐
                ├─► Ambos van a 08:08 (redondeado a 08:10)
Trip B: 08:17  ─┘

Gap original: 17 minutos (está en rango 15-20)
Midpoint: (08:00 + 08:17) / 2 = 08:08 → redondeado a 08:10

*Redondeo a múltiplos de 5 (pégalo en la sección “Redondeo a Múltiplos de 5”)

Regla de redondeo (múltiplos de 5)
El redondeo a múltiplos de 5 se realiza al múltiplo de 5 más cercano. Por ejemplo: 08:03 → 08:05, 08:07 → 08:05, 08:08 → 08:10. Este comportamiento es interno y siempre está habilitado.

### Expand (Expandir/Separar)

Si dos trips tienen un gap en [min_gap, max_gap], se separan:
- El trip más temprano se mueve hacia atrás (1/3 del max_shift)
- El trip más tarde se mueve hacia adelante (2/3 del max_shift)

Ejemplo: min_gap=21, max_gap=30, max_shift=15
Trip A: 08:00 → 07:55 (se mueve 5 min hacia atrás = 15/3)
Trip B: 08:25 → 08:35 (se mueve 10 min hacia adelante = 15-5)

Gap original: 25 minutos
Gap nuevo: 40 minutos

---

## Reglas Importantes

### Regla A: Un trip modificado no se vuelve a modificar

En una misma ejecución, si un trip ya fue modificado por un filtro, NO será tocado por otro filtro.

Ejemplo: Reduce modifica Trip A
         Combine intenta modificar Trip A → IGNORADO

### Regla B: No-Collision Rule (Expand)

Antes de aplicar Expand, el sistema simula el resultado. Si el nuevo gap con un vecino cae dentro del rango de Combine, la operación se cancela y se registra como exclusión.

Ejemplo:
- Combine: 15-20 min
- Expand: 21-30 min

Si Expand(A,B) causaría que B quede a 18 min de C:
→ Operación cancelada (colisionaría con Combine)
→ Se registra en exclusions[]

### Redondeo a Múltiplos de 5

Todos los resultados se redondean automáticamente a múltiplos de 5 minutos.

08:03 → 08:05
08:07 → 08:05
08:08 → 08:10

---

## Filtros Opcionales por Filtro

Cada filtro puede restringirse por:

### 1. Hotel Names (por defecto: ALL)



hotel_names: ["Hilton Downtown", "Marriott"]  // Solo estos hoteles
hotel_names: null  // TODOS los hoteles

### 2. Time Range (por defecto: ALL)

time_range: {
  start: "05:00",
  end: "10:00"
}  // Solo trips en esta ventana

time_range: null  // TODOS los horarios

Roilan Lambert, [01/13/2026 5:16 pm]
Nota: Soporta cruce de medianoche:
time_range: {
  start: "22:00",
  end: "02:00"
}  // Trips de 22:00 a 23:59 y de 00:00 a 02:00

---

## Flujo Recomendado en UI

1. Usuario configura filtros en formulario
        ↓
2. Click "Preview" → POST /filters/preview
        ↓
3. Mostrar tabla con cambios propuestos
   - original_time vs new_time
   - hotel_name
   - filter_applied
        ↓
4. Mostrar exclusiones (si las hay)
   - reason por qué no se aplicó
        ↓
5. Usuario confirma → POST /filters/apply
        ↓
6. Guardar batch_id en estado/localStorage
        ↓
7. Opción "Deshacer" → POST /filters/revert?batch_id=xxx

---

## TypeScript Types (Copiar a Frontend)

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
  target_date?: string;
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
}

export interface FilterExclusion {
  operation: string;
  trip_ids: string[];
  reason: string;
  gap_before: number;
  gap_after: number;
}

export interface FilterPreviewResult {
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

---

## Errores Comunes

| Código | Mensaje | Solución |
|--------|---------|----------|
| 400 | "ID de location inválido" | Verificar UUID format |
| 400 | "Formato de fecha inválido" | Usar YYYY-MM-DD |
| 400 | "max_gap must be >= min_gap" | Corregir valores |
| 404 | "Location no encontrada" | Verificar location_id |

---

## Notas Finales

1. Solo afecta trips Outbound/Ground - Los trips Inbound no son modificados
2. El campo modificado es únicamente `pick_up_time` - No se tocan otros campos
3. Los cambios son reversibles - Siempre se guarda el valor original
4. Preview es gratuito - No modifica nada, usar para validar
5. Batch ID es importante - Guardarlo para poder revertir después