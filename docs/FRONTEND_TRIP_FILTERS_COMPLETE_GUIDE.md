# Sistema de Filtros de Trips Outbound/Ground - Guía Completa Frontend

## 📋 Tabla de Contenidos

1. [Resumen Ejecutivo](#resumen-ejecutivo)
2. [Conceptos Fundamentales](#conceptos-fundamentales)
3. [Los Tres Filtros](#los-tres-filtros)
4. [Arquitectura del Sistema](#arquitectura-del-sistema)
5. [Flujo Completo de Operaciones](#flujo-completo-de-operaciones)
6. [API Endpoints](#api-endpoints)
7. [Modelos de Datos](#modelos-de-datos)
8. [Implementación Frontend](#implementación-frontend)
9. [UI/UX Guidelines](#uiux-guidelines)
10. [Testing y QA](#testing-y-qa)
11. [Troubleshooting](#troubleshooting)
12. [Casos Edge](#casos-edge)

---

## 1. Resumen Ejecutivo

### ¿Qué es este sistema?

El **Sistema de Filtros de Trips** permite a los managers ajustar automáticamente los horarios de pickup (`pick_up_time`) de los trips **Outbound** y **Ground** para optimizar rutas y reducir tiempos de espera.

### Estado Actual

✅ **Backend:** Completamente implementado y funcionando
🟡 **Frontend:** Pendiente de implementación
📅 **Fecha de Backend:** 2026-01-14

### Casos de Uso

1. **Reducir Lead Time:** Restar 10-15 minutos a todos los pickups matutinos
2. **Combinar Trips Cercanos:** Unir trips con 15-20 min de diferencia en un solo pickup
3. **Separar Trips Muy Juntos:** Espaciar trips que están a menos de 10 minutos

### Key Features

- ✅ **Preview Mode:** Simula cambios sin aplicarlos (gratis, sin límite)
- ✅ **Reversible:** Todos los cambios se pueden deshacer (batch o completo)
- ✅ **Inteligente:** Respeta reglas de negocio y evita colisiones
- ✅ **Auditado:** Tracking completo de qué cambió, cuándo y por qué

---

## 2. Conceptos Fundamentales

### 2.1 Tipos de Trips

El sistema **SOLO** afecta trips con estas características:

```python
# Elegibles para filtrado
trip_type = "outbound" OR "ground"
status = "scheduled"
location_id = [location específica]
airline = [aerolínea específica]

# NO elegibles
trip_type = "inbound"  # ❌ NUNCA se filtra
status != "scheduled"   # ❌ En route, canceled, etc.
```

**¿Por qué solo Outbound/Ground?**
- **Outbound:** Hotel → Airport (timing flexible, driver puede salir antes)
- **Ground:** Hotel → Hotel (timing flexible)
- **Inbound:** Airport → Hotel (FIJO por horario del vuelo, NO se puede modificar)

### 2.2 Campo Modificado

**UN SOLO CAMPO SE MODIFICA:**
```typescript
interface Trip {
  id: string;
  pick_up_date: string;        // ✅ NO cambia
  pick_up_time: string;         // ⚠️ ESTE SE MODIFICA
  pick_up_location: string;     // ✅ NO cambia
  drop_off_location: string;    // ✅ NO cambia
  airline: string;              // ✅ NO cambia
  flight_number: string;        // ✅ NO cambia

  // Campos de tracking (nuevos)
  original_pick_up_time: string | null;  // Backup automático
  filter_applied: string | null;         // "reduce" | "combine" | "expand"
  filter_batch_id: string | null;        // UUID para revertir
  filtered_at: string | null;            // Timestamp ISO
}
```

### 2.3 Reglas de Negocio (CRÍTICAS)

#### **Regla A: Modificación Única**
Un trip modificado por un filtro **NO puede ser modificado** por otro filtro en la misma ejecución.

```
Ejemplo:
1. Reduce modifica Trip A de 08:00 → 07:50
2. Combine intenta modificar Trip A → ❌ IGNORADO (ya fue modificado)
```

**Razón:** Evitar cambios acumulativos impredecibles.

#### **Regla B: No-Collision Rule**
Expand debe verificar que NO cree gaps que caigan dentro del rango de Combine.

```
Ejemplo:
- Combine configurado: min_gap=15, max_gap=20
- Expand intenta: Trip A (08:00) ← 5min → 07:55
                  Trip B (08:10) → 10min → 08:20
- Gap resultante con Trip C (08:33): 13 minutos
- ❌ RECHAZADO: 13 minutos cae en rango de Combine (15-20)
```

**Razón:** Evitar que Expand cree situaciones que Combine intentaría corregir.

#### **Regla C: Redondeo a Múltiplos de 5**
TODOS los resultados se redondean automáticamente.

```
08:03 → 08:05  (redondeo hacia arriba)
08:07 → 08:05  (redondeo hacia abajo)
08:08 → 08:10  (redondeo hacia arriba)
08:12 → 08:10  (redondeo hacia abajo)
08:13 → 08:15  (redondeo hacia arriba)
```

**Razón:** Horarios más limpios y fáciles de recordar para drivers.

#### **Regla D: Protección contra Drift**
Si se ejecuta Apply múltiples veces, los cálculos usan `original_pick_up_time` como referencia.

```
Primera ejecución:
- original_pick_up_time: NULL → se guarda 08:00
- pick_up_time: 08:00 → 07:50

Segunda ejecución (mismo filtro):
- original_pick_up_time: 08:00 (NO cambia)
- pick_up_time: 08:00 → 07:50 (mismo resultado)
```

**Razón:** Evitar drift acumulativo (07:50 → 07:40 → 07:30...).

---

## 3. Los Tres Filtros

### 3.1 Filtro: REDUCE (Reducir Lead Time)

#### Concepto
Resta un número fijo de minutos a todos los trips seleccionados.

#### Caso de Uso
"Los drivers siempre llegan 15 minutos antes. Quiero reducir todos los pickups matutinos en 10 minutos."

#### Algoritmo

```typescript
for each trip in selected_trips:
  if trip.id not in modified_trips:
    new_time = trip.pick_up_time - minutes_to_reduce
    new_time = round_to_5_minutes(new_time)
    record_change(trip, new_time, "reduce")
    mark_as_modified(trip.id)
```

#### Configuración

```typescript
interface ReduceFilterConfig {
  enabled: boolean;
  minutes_to_reduce: number;      // 0-120 minutos
  hotel_names?: string[] | null;  // null = ALL hoteles
  time_range?: TimeRange | null;  // null = ALL horarios
}
```

#### Ejemplo Visual

**Input:**
```
Trip A: 08:00 (Hotel Hilton)
Trip B: 09:15 (Hotel Marriott)
Trip C: 10:30 (Hotel Hilton)

Config: minutes_to_reduce = 10, hotel_names = ["Hilton"]
```

**Proceso:**
```
Trip A: 08:00 - 10 min = 07:50 → round → 07:50 ✅
Trip B: 09:15 (Marriott, no filtrado) → sin cambios
Trip C: 10:30 - 10 min = 10:20 → round → 10:20 ✅
```

**Output:**
```
Trip A: 07:50 ✅ (filter_applied = "reduce")
Trip B: 09:15 (sin cambios)
Trip C: 10:20 ✅ (filter_applied = "reduce")
```

#### Edge Cases

**1. Cruce de medianoche:**
```
Trip: 00:10
Reduce: 15 minutos
Result: 23:55 del día anterior ✅ (se maneja automáticamente)
```

**2. Time range con cruce de medianoche:**
```
Config: time_range = {start: "22:00", end: "02:00"}
Trip A: 23:30 → ✅ En rango (22:00-23:59)
Trip B: 01:00 → ✅ En rango (00:00-02:00)
Trip C: 15:00 → ❌ Fuera de rango
```

---

### 3.2 Filtro: COMBINE (Combinar/Contraer)

#### Concepto
Si dos trips consecutivos tienen un gap dentro del rango `[min_gap, max_gap]`, ambos se mueven al punto medio (promedio).

#### Caso de Uso
"Hay trips con 17 minutos de diferencia. Quiero combinarlos en un solo horario para que el driver haga ambos pickups en un viaje."

#### Algoritmo

```typescript
trips_sorted = sort_by_time(selected_trips)
i = 0

while i < trips_sorted.length - 1:
  trip_a = trips_sorted[i]
  trip_b = trips_sorted[i + 1]

  // Skip si alguno ya fue modificado (Regla A)
  if is_modified(trip_a) OR is_modified(trip_b):
    i++
    continue

  gap = minutes_between(trip_a.time, trip_b.time)

  if min_gap <= gap <= max_gap:
    midpoint = (trip_a.time + trip_b.time) / 2
    midpoint = round_to_5_minutes(midpoint)

    record_change(trip_a, midpoint, "combine")
    record_change(trip_b, midpoint, "combine")

    mark_as_modified(trip_a.id)
    mark_as_modified(trip_b.id)

    i += 2  // Skip ambos trips
  else:
    i++
```

#### Configuración

```typescript
interface CombineFilterConfig {
  enabled: boolean;
  min_gap: number;                // ej: 15 (minutos)
  max_gap: number;                // ej: 20 (minutos)
  hotel_names?: string[] | null;
  time_range?: TimeRange | null;
}
```

#### Ejemplo Visual

**Input:**
```
Trip A: 08:00 (Hilton)
Trip B: 08:17 (Marriott)
Trip C: 08:45 (Hilton)

Config: min_gap = 15, max_gap = 20
```

**Proceso:**
```
Comparar Trip A ↔ Trip B:
  Gap = 17 minutos
  17 está en rango [15, 20] ✅
  Midpoint = (08:00 + 08:17) / 2 = 08:08.5 → round → 08:10

  Trip A: 08:00 → 08:10 ✅
  Trip B: 08:17 → 08:10 ✅

Comparar Trip B ↔ Trip C:
  ❌ Trip B ya fue modificado (Regla A) → SKIP
```

**Output:**
```
Trip A: 08:10 ✅ (filter_applied = "combine")
Trip B: 08:10 ✅ (filter_applied = "combine")
Trip C: 08:45 (sin cambios)
```

#### Visualización de Gaps

```
ANTES:
|----Trip A----|(17 min)|----Trip B----|(28 min)|----Trip C----|
     08:00                   08:17                   08:45

DESPUÉS:
|----Trip A & B----|(35 min)|----Trip C----|
      08:10                      08:45
```

#### Edge Cases

**1. Múltiples pares consecutivos:**
```
Trip A: 08:00 }
Trip B: 08:17 } → Ambos a 08:10

Trip C: 08:40 }
Trip D: 08:55 } → Ambos a 08:50 (gap = 15 min)

Trip E: 09:20 → Sin cambios (gap con D = 30 min, fuera de rango)
```

**2. Tres trips muy cerca:**
```
Trip A: 08:00
Trip B: 08:15  (gap con A = 15 min)
Trip C: 08:30  (gap con B = 15 min)

Resultado:
- A y B → combinados a 08:08
- B y C → ❌ B ya modificado, C sin cambios
```

---

### 3.3 Filtro: EXPAND (Expandir/Separar)

#### Concepto
Separa pares de trips que están muy juntos, moviendo el primero hacia atrás y el segundo hacia adelante.

**Distribución de Movimiento:**
- Trip más temprano: ⬅️ **1/3** de `max_shift` (hacia atrás)
- Trip más tarde: ➡️ **2/3** de `max_shift` (hacia adelante)

#### Caso de Uso
"Los trips están a 8 minutos de diferencia, lo cual es muy ajustado. Quiero separarlos para dar más margen al driver."

#### Algoritmo

```typescript
trips_sorted = sort_by_time(selected_trips)

for i in 0 to trips_sorted.length - 2:
  trip_a = trips_sorted[i]
  trip_b = trips_sorted[i + 1]

  // Skip si alguno ya fue modificado (Regla A)
  if is_modified(trip_a) OR is_modified(trip_b):
    continue

  gap = minutes_between(trip_a.time, trip_b.time)

  if min_gap <= gap <= max_gap:
    // Calcular nuevos tiempos
    shift_a = max_shift / 3
    shift_b = max_shift - shift_a

    new_time_a = trip_a.time - shift_a
    new_time_b = trip_b.time + shift_b

    new_time_a = round_to_5_minutes(new_time_a)
    new_time_b = round_to_5_minutes(new_time_b)

    // NO-COLLISION RULE (Regla B)
    if combine_enabled:
      // Verificar gap con vecino anterior
      if i > 0:
        prev_trip = trips_sorted[i - 1]
        prev_time = get_effective_time(prev_trip)
        gap_with_prev = minutes_between(prev_time, new_time_a)

        if combine_min_gap <= gap_with_prev <= combine_max_gap:
          record_exclusion("Collision con prev", gap, gap_with_prev)
          continue  // ❌ RECHAZAR operación

      // Verificar gap con vecino siguiente
      if i + 2 < trips_sorted.length:
        next_trip = trips_sorted[i + 2]
        next_time = get_effective_time(next_trip)
        gap_with_next = minutes_between(new_time_b, next_time)

        if combine_min_gap <= gap_with_next <= combine_max_gap:
          record_exclusion("Collision con next", gap, gap_with_next)
          continue  // ❌ RECHAZAR operación

    // ✅ Sin colisiones, aplicar
    record_change(trip_a, new_time_a, "expand")
    record_change(trip_b, new_time_b, "expand")

    mark_as_modified(trip_a.id)
    mark_as_modified(trip_b.id)
```

#### Configuración

```typescript
interface ExpandFilterConfig {
  enabled: boolean;
  min_gap: number;                // ej: 5
  max_gap: number;                // ej: 10
  max_shift: number;              // ej: 15 (máximo de minutos a mover)
  hotel_names?: string[] | null;
  time_range?: TimeRange | null;
}
```

#### Ejemplo Visual

**Input:**
```
Trip A: 08:00
Trip B: 08:08

Config: min_gap = 5, max_gap = 10, max_shift = 15
```

**Proceso:**
```
Gap = 8 minutos (en rango [5, 10]) ✅

Calcular shifts:
  shift_a = 15 / 3 = 5 minutos
  shift_b = 15 - 5 = 10 minutos

Aplicar:
  new_time_a = 08:00 - 5 = 07:55
  new_time_b = 08:08 + 10 = 08:18

Redondear:
  new_time_a = 07:55 (ya múltiplo de 5)
  new_time_b = 08:20 (08:18 → 08:20)

Nuevo gap = 25 minutos ✅
```

**Output:**
```
Trip A: 07:55 ✅ (filter_applied = "expand", movido 5 min atrás)
Trip B: 08:20 ✅ (filter_applied = "expand", movido 12 min adelante)
```

#### Visualización del Expand

```
ANTES:
|----Trip A----|(8 min)|----Trip B----|
     08:00                08:08

Gap muy pequeño ⚠️

DESPUÉS:
|----Trip A----|<--5 min-->|(25 min)|<--10 min-->|----Trip B----|
     07:55                                            08:20

Gap aumentado a 25 min ✅
```

#### No-Collision Rule Visualizada

**Escenario 1: Colisión con vecino anterior**

```
ANTES:
Trip X: 07:30
Trip A: 08:00  } Gap = 8 min → intentar expandir
Trip B: 08:08  }

INTENTO DE EXPAND:
Trip A: 08:00 → 07:55 (mover 5 min atrás)

VERIFICACIÓN:
Gap(Trip X, new Trip A) = 07:30 ↔ 07:55 = 25 minutos

Si Combine está configurado con [15, 20]:
  25 minutos NO está en rango [15, 20] ✅ SIN COLISIÓN

Si Combine está configurado con [20, 30]:
  25 minutos SÍ está en rango [20, 30] ❌ COLISIÓN
  → Operación RECHAZADA y registrada como exclusión
```

**Escenario 2: Colisión con vecino siguiente**

```
ANTES:
Trip A: 08:00  } Gap = 8 min → intentar expandir
Trip B: 08:08  }
Trip C: 08:25

INTENTO DE EXPAND:
Trip B: 08:08 → 08:20 (mover 12 min adelante)

VERIFICACIÓN:
Gap(new Trip B, Trip C) = 08:20 ↔ 08:25 = 5 minutos

Si Combine está configurado con [15, 20]:
  5 minutos NO está en rango [15, 20] ✅ SIN COLISIÓN

Si Combine está configurado con [5, 10]:
  5 minutos SÍ está en rango [5, 10] ❌ COLISIÓN
  → Operación RECHAZADA y registrada como exclusión
```

#### Edge Cases

**1. Expand sin Combine activo:**
```
Config:
  expand: {enabled: true, min_gap: 5, max_gap: 10, max_shift: 15}
  combine: {enabled: false}

Resultado:
  ✅ No-Collision Rule NO se aplica
  ✅ Todas las operaciones Expand proceden sin verificación
```

**2. Múltiples trips muy juntos:**
```
Trip A: 08:00 }
Trip B: 08:08 } → Expandir a 07:55 y 08:20
Trip C: 08:15 → Sin cambios (Trip B ya modificado)
Trip D: 08:22 → Sin cambios (Trip C no fue modificado, pero no cumple rango)
```

---

## 4. Arquitectura del Sistema

### 4.1 Flujo de Datos Completo

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React)                         │
├─────────────────────────────────────────────────────────────────┤
│  1. Usuario configura filtros en formulario                     │
│  2. Click "Preview" → Llamada API                               │
│  3. Mostrar tabla de cambios propuestos                         │
│  4. Usuario confirma → "Apply"                                  │
│  5. Guardar batch_id en state/localStorage                      │
│  6. Opción "Undo" disponible                                   │
└─────────────────────────────────────────────────────────────────┘
                            ↓ HTTP POST
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│                    BACKEND (FastAPI + psqlmodel)                 │
├─────────────────────────────────────────────────────────────────┤
│  1. Validar JWT token (manager role required)                   │
│  2. Validar configuración de filtros                            │
│  3. Obtener trips elegibles de PostgreSQL                       │
│  4. TripFilterService.preview() o .apply()                      │
│  5. Ejecutar filtros en orden: Reduce → Combine → Expand       │
│  6. Aplicar reglas (A, B, C, D)                                │
│  7. Si Apply: persistir cambios + generar batch_id             │
│  8. Retornar resultado                                          │
└─────────────────────────────────────────────────────────────────┘
                            ↓
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│                       POSTGRESQL DATABASE                         │
├─────────────────────────────────────────────────────────────────┤
│  trips.trips table:                                              │
│    - pick_up_time ← modificado                                  │
│    - original_pick_up_time ← backup (si NULL, se guarda)       │
│    - filter_applied ← "reduce" | "combine" | "expand"          │
│    - filter_batch_id ← UUID (para agrupar y revertir)          │
│    - filtered_at ← timestamp                                    │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Orden de Ejecución de Filtros

**SIEMPRE en este orden:**

```
1. REDUCE   → Modifica trips individuales
     ↓
2. COMBINE  → Combina pares (respeta trips ya modificados por Reduce)
     ↓
3. EXPAND   → Separa pares (respeta trips modificados por Reduce/Combine)
              + verifica No-Collision Rule con Combine
```

**¿Por qué este orden?**

1. **Reduce primero:** Es el más simple, no depende de otros trips
2. **Combine segundo:** Necesita saber qué trips ya fueron modificados por Reduce
3. **Expand último:** Es el más complejo, depende de Combine para No-Collision Rule

### 4.3 Modelo de Trip (Antes y Después)

#### Antes del Filtrado

```json
{
  "id": "uuid-123",
  "pick_up_date": "2025-06-01",
  "pick_up_time": "08:00:00-04:00",
  "pick_up_location": "Hilton Downtown",
  "drop_off_location": "SDF",
  "airline": "WN",
  "flight_number": "3209",
  "trip_type": "outbound",
  "status": "scheduled",

  "original_pick_up_time": null,
  "filter_applied": null,
  "filter_batch_id": null,
  "filtered_at": null
}
```

#### Después del Filtrado

```json
{
  "id": "uuid-123",
  "pick_up_date": "2025-06-01",
  "pick_up_time": "07:50:00-04:00",  // ✅ MODIFICADO
  "pick_up_location": "Hilton Downtown",
  "drop_off_location": "SDF",
  "airline": "WN",
  "flight_number": "3209",
  "trip_type": "outbound",
  "status": "scheduled",

  "original_pick_up_time": "08:00:00-04:00",  // ✅ BACKUP
  "filter_applied": "reduce",                  // ✅ TRACKING
  "filter_batch_id": "uuid-batch-456",         // ✅ PARA REVERTIR
  "filtered_at": "2025-06-01T10:30:00Z"        // ✅ TIMESTAMP
}
```

---

## 5. Flujo Completo de Operaciones

### 5.1 Workflow: Preview

```mermaid
Usuario configura filtros
       ↓
[Click "Preview"]
       ↓
POST /v1/locations/{id}/trips/filters/preview
{
  reduce: {enabled: true, minutes_to_reduce: 10},
  combine: {enabled: true, min_gap: 15, max_gap: 20}
}
       ↓
Backend simula cambios (NO modifica DB)
       ↓
Response:
{
  changes: [
    {trip_id: "A", original: "08:00", new: "07:50", filter: "reduce"},
    {trip_id: "B", original: "08:15", new: "08:10", filter: "combine"},
    {trip_id: "C", original: "08:17", new: "08:10", filter: "combine"}
  ],
  exclusions: [],
  summary: {reduce: 1, combine: 2, expand: 0, excluded: 0}
}
       ↓
Frontend muestra tabla comparativa
       ↓
Usuario revisa y decide aplicar o cancelar
```

### 5.2 Workflow: Apply

```mermaid
Usuario confirma cambios
       ↓
[Click "Apply"]
       ↓
POST /v1/locations/{id}/trips/filters/apply
{
  reduce: {enabled: true, minutes_to_reduce: 10},
  combine: {enabled: true, min_gap: 15, max_gap: 20}
}
       ↓
Backend ejecuta filtros + persiste en DB
       ↓
Response:
{
  batch_id: "uuid-batch-789",  // ← IMPORTANTE: GUARDAR
  changes_applied: 3,
  exclusions: [],
  log: [...],
  summary: {reduce: 1, combine: 2, expand: 0, excluded: 0}
}
       ↓
Frontend guarda batch_id en state/localStorage
       ↓
Frontend muestra notificación de éxito
       ↓
Frontend habilita botón "Undo"
```

### 5.3 Workflow: Revert

```mermaid
Usuario se arrepiente
       ↓
[Click "Undo"]
       ↓
POST /v1/locations/{id}/trips/filters/revert?batch_id=uuid-batch-789
       ↓
Backend restaura original_pick_up_time → pick_up_time
       ↓
Backend limpia campos de tracking
       ↓
Response:
{
  trips_reverted: 3,
  batch_ids_reverted: ["uuid-batch-789"]
}
       ↓
Frontend muestra notificación "Cambios revertidos"
       ↓
Frontend deshabilita botón "Undo"
```

---

## 6. API Endpoints

### Base URL

```
Production: https://api.gt360.app
Development: http://localhost:8000
```

### 6.1 POST /v1/locations/{location_id}/trips/filters/preview

**Propósito:** Simular filtros sin aplicar cambios (NO modifica DB).

**Autenticación:** JWT token con rol `manager`

**Path Parameters:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| location_id | UUID | ID de la location |

**Request Body:**
```typescript
{
  reduce?: ReduceFilterConfig;
  combine?: CombineFilterConfig;
  expand?: ExpandFilterConfig;
}
```

**Response 200:**
```typescript
{
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
```

**Errores:**
| Código | Mensaje | Solución |
|--------|---------|----------|
| 400 | "Invalid location_id format" | Verificar UUID |
| 401 | "Invalid token" | Renovar JWT |
| 403 | "Insufficient permissions" | Requiere rol manager |
| 404 | "Location not found" | Verificar location_id |
| 422 | "max_gap must be >= min_gap" | Corregir config |

**Ejemplo:**
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
      reduce: {
        enabled: true,
        minutes_to_reduce: 10,
        hotel_names: null,
        time_range: {start: "05:00", end: "10:00"}
      }
    })
  }
);

const preview = await response.json();
console.log(`${preview.changes.length} trips will be modified`);
```

---

### 6.2 POST /v1/locations/{location_id}/trips/filters/apply

**Propósito:** Aplicar filtros y persistir cambios en DB.

**Autenticación:** JWT token con rol `manager`

**Path Parameters:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| location_id | UUID | ID de la location |

**Request Body:**
```typescript
{
  reduce?: ReduceFilterConfig;
  combine?: CombineFilterConfig;
  expand?: ExpandFilterConfig;
}
```

**Response 200:**
```typescript
{
  batch_id: string;  // ← CRITICAL: Save this for undo!
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
```

**⚠️ IMPORTANTE:** Guardar `batch_id` inmediatamente:

```typescript
const result = await response.json();
localStorage.setItem(`filterBatch_${locationId}`, result.batch_id);
// O en state management:
dispatch(saveLastBatchId(result.batch_id));
```

**Ejemplo:**
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
      combine: {
        enabled: true,
        min_gap: 15,
        max_gap: 20
      }
    })
  }
);

const result = await response.json();
console.log(`Batch ID: ${result.batch_id}`);
console.log(`Modified: ${result.changes_applied} trips`);

// SAVE for undo
localStorage.setItem('lastBatchId', result.batch_id);
```

---

### 6.3 POST /v1/locations/{location_id}/trips/filters/revert

**Propósito:** Revertir filtros (restaurar tiempos originales).

**Autenticación:** JWT token con rol `manager`

**Path Parameters:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| location_id | UUID | ID de la location |

**Query Parameters:**
| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| batch_id | UUID | No | Si se proporciona, solo revierte ese batch. Si se omite, revierte TODOS los filtros de la location+airline |

**Response 200:**
```typescript
{
  trips_reverted: number;
  batch_ids_reverted: string[];
}
```

**Ejemplos:**

**Revertir un batch específico:**
```typescript
const batchId = localStorage.getItem('lastBatchId');
const response = await fetch(
  `${API_URL}/v1/locations/${locationId}/trips/filters/revert?batch_id=${batchId}`,
  {
    method: 'POST',
    headers: {'Authorization': `Bearer ${token}`}
  }
);

const result = await response.json();
console.log(`Reverted ${result.trips_reverted} trips`);
```

**Revertir TODOS los filtros de la location:**
```typescript
const response = await fetch(
  `${API_URL}/v1/locations/${locationId}/trips/filters/revert`,
  {
    method: 'POST',
    headers: {'Authorization': `Bearer ${token}`}
  }
);

const result = await response.json();
console.log(`Reverted ${result.trips_reverted} trips`);
console.log(`Batches reverted: ${result.batch_ids_reverted.join(', ')}`);
```

---

## 7. Modelos de Datos

### 7.1 TypeScript Interfaces

```typescript
// ============================================================
// Filter Configurations
// ============================================================

interface TimeRange {
  start: string;  // "HH:MM" format, e.g., "05:00"
  end: string;    // "HH:MM" format, e.g., "10:00"
}

interface ReduceFilterConfig {
  enabled: boolean;
  minutes_to_reduce: number;      // 0-120 minutos
  hotel_names?: string[] | null;  // null = ALL hoteles
  time_range?: TimeRange | null;  // null = ALL horarios
}

interface CombineFilterConfig {
  enabled: boolean;
  min_gap: number;                // 1-60 minutos
  max_gap: number;                // 1-120 minutos (must be >= min_gap)
  hotel_names?: string[] | null;
  time_range?: TimeRange | null;
}

interface ExpandFilterConfig {
  enabled: boolean;
  min_gap: number;                // 1-60 minutos
  max_gap: number;                // 1-120 minutos (must be >= min_gap)
  max_shift: number;              // 1-30 minutos (máximo a mover por trip)
  hotel_names?: string[] | null;
  time_range?: TimeRange | null;
}

interface FilterRequest {
  reduce?: ReduceFilterConfig;
  combine?: CombineFilterConfig;
  expand?: ExpandFilterConfig;
}

// ============================================================
// Response Models
// ============================================================

interface TripChange {
  trip_id: string;
  original_time: string;    // "HH:MM:SS" format
  new_time: string;         // "HH:MM:SS" format
  filter_applied: "reduce" | "combine" | "expand";
  hotel_name: string;
  pick_up_date: string | null;
  airline: string | null;
}

interface FilterExclusion {
  operation: string;        // e.g., "expand(uuid1, uuid2)"
  trip_ids: string[];
  reason: string;
  gap_before: number;
  gap_after: number;
}

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

interface FilterApplyResult {
  batch_id: string;
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

interface FilterRevertResult {
  trips_reverted: number;
  batch_ids_reverted: string[];
}

// ============================================================
// Trip Model (Extended)
// ============================================================

interface Trip {
  id: string;
  location_id: string;
  pick_up_date: string;
  pick_up_time: string;
  pick_up_location: string;
  drop_off_location: string;
  airline: string;
  flight_number: string;
  trip_type: "inbound" | "outbound" | "ground";
  status: "scheduled" | "en_route" | "canceled";
  riders: any;

  // Filter tracking fields (new)
  original_pick_up_time: string | null;
  filter_applied: string | null;
  filter_batch_id: string | null;
  filtered_at: string | null;

  created_at: string;
  updated_at: string;
}
```

---

## 8. Implementación Frontend

### 8.1 React Hook: useFilters

```typescript
// hooks/use-filters.ts

import { useState } from 'react';
import { FilterRequest, FilterPreviewResult, FilterApplyResult } from '@/types/filters';

export function useFilters(locationId: string, token: string) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastBatchId, setLastBatchId] = useState<string | null>(null);

  const preview = async (config: FilterRequest): Promise<FilterPreviewResult | null> => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/v1/locations/${locationId}/trips/filters/preview`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify(config)
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Preview failed');
      }

      const result = await response.json();
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      return null;
    } finally {
      setLoading(false);
    }
  };

  const apply = async (config: FilterRequest): Promise<FilterApplyResult | null> => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/v1/locations/${locationId}/trips/filters/apply`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify(config)
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Apply failed');
      }

      const result = await response.json();

      // Save batch_id for undo
      setLastBatchId(result.batch_id);
      localStorage.setItem(`filterBatch_${locationId}`, result.batch_id);

      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      return null;
    } finally {
      setLoading(false);
    }
  };

  const revert = async (batchId?: string): Promise<boolean> => {
    setLoading(true);
    setError(null);

    const targetBatchId = batchId || lastBatchId;
    const url = targetBatchId
      ? `${process.env.NEXT_PUBLIC_API_URL}/v1/locations/${locationId}/trips/filters/revert?batch_id=${targetBatchId}`
      : `${process.env.NEXT_PUBLIC_API_URL}/v1/locations/${locationId}/trips/filters/revert`;

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {'Authorization': `Bearer ${token}`}
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Revert failed');
      }

      // Clear saved batch_id
      setLastBatchId(null);
      localStorage.removeItem(`filterBatch_${locationId}`);

      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      return false;
    } finally {
      setLoading(false);
    }
  };

  return {
    preview,
    apply,
    revert,
    loading,
    error,
    lastBatchId,
    canUndo: !!lastBatchId
  };
}
```

### 8.2 Component: FilterPanel

```typescript
// components/filter-panel.tsx

import React, { useState } from 'react';
import { useFilters } from '@/hooks/use-filters';
import { FilterRequest } from '@/types/filters';

interface FilterPanelProps {
  locationId: string;
  token: string;
  onSuccess?: () => void;
}

export function FilterPanel({ locationId, token, onSuccess }: FilterPanelProps) {
  const { preview, apply, revert, loading, error, canUndo } = useFilters(locationId, token);

  const [config, setConfig] = useState<FilterRequest>({
    reduce: { enabled: false, minutes_to_reduce: 10 },
    combine: { enabled: false, min_gap: 15, max_gap: 20 },
    expand: { enabled: false, min_gap: 5, max_gap: 10, max_shift: 15 }
  });

  const [previewData, setPreviewData] = useState<any>(null);
  const [showPreview, setShowPreview] = useState(false);

  const handlePreview = async () => {
    const result = await preview(config);
    if (result) {
      setPreviewData(result);
      setShowPreview(true);
    }
  };

  const handleApply = async () => {
    const result = await apply(config);
    if (result) {
      setShowPreview(false);
      setPreviewData(null);
      onSuccess?.();
    }
  };

  const handleRevert = async () => {
    const success = await revert();
    if (success) {
      onSuccess?.();
    }
  };

  return (
    <div className="filter-panel">
      {/* Reduce Filter */}
      <div>
        <label>
          <input
            type="checkbox"
            checked={config.reduce?.enabled}
            onChange={(e) => setConfig({
              ...config,
              reduce: { ...config.reduce!, enabled: e.target.checked }
            })}
          />
          Reduce Lead Time
        </label>

        {config.reduce?.enabled && (
          <input
            type="number"
            min="0"
            max="120"
            value={config.reduce.minutes_to_reduce}
            onChange={(e) => setConfig({
              ...config,
              reduce: { ...config.reduce!, minutes_to_reduce: parseInt(e.target.value) }
            })}
          />
        )}
      </div>

      {/* Combine Filter */}
      <div>
        <label>
          <input
            type="checkbox"
            checked={config.combine?.enabled}
            onChange={(e) => setConfig({
              ...config,
              combine: { ...config.combine!, enabled: e.target.checked }
            })}
          />
          Combine Trips
        </label>

        {config.combine?.enabled && (
          <>
            <input
              type="number"
              min="1"
              max="60"
              placeholder="Min gap"
              value={config.combine.min_gap}
              onChange={(e) => setConfig({
                ...config,
                combine: { ...config.combine!, min_gap: parseInt(e.target.value) }
              })}
            />
            <input
              type="number"
              min="1"
              max="120"
              placeholder="Max gap"
              value={config.combine.max_gap}
              onChange={(e) => setConfig({
                ...config,
                combine: { ...config.combine!, max_gap: parseInt(e.target.value) }
              })}
            />
          </>
        )}
      </div>

      {/* Expand Filter */}
      <div>
        <label>
          <input
            type="checkbox"
            checked={config.expand?.enabled}
            onChange={(e) => setConfig({
              ...config,
              expand: { ...config.expand!, enabled: e.target.checked }
            })}
          />
          Expand (Separate Trips)
        </label>

        {config.expand?.enabled && (
          <>
            <input
              type="number"
              min="1"
              max="60"
              placeholder="Min gap"
              value={config.expand.min_gap}
              onChange={(e) => setConfig({
                ...config,
                expand: { ...config.expand!, min_gap: parseInt(e.target.value) }
              })}
            />
            <input
              type="number"
              min="1"
              max="120"
              placeholder="Max gap"
              value={config.expand.max_gap}
              onChange={(e) => setConfig({
                ...config,
                expand: { ...config.expand!, max_gap: parseInt(e.target.value) }
              })}
            />
            <input
              type="number"
              min="1"
              max="30"
              placeholder="Max shift"
              value={config.expand.max_shift}
              onChange={(e) => setConfig({
                ...config,
                expand: { ...config.expand!, max_shift: parseInt(e.target.value) }
              })}
            />
          </>
        )}
      </div>

      {/* Action Buttons */}
      <div className="actions">
        <button onClick={handlePreview} disabled={loading}>
          {loading ? 'Loading...' : 'Preview Changes'}
        </button>

        {canUndo && (
          <button onClick={handleRevert} disabled={loading}>
            Undo Last Filter
          </button>
        )}
      </div>

      {/* Error Display */}
      {error && <div className="error">{error}</div>}

      {/* Preview Modal */}
      {showPreview && previewData && (
        <div className="preview-modal">
          <h3>Preview: {previewData.changes.length} changes</h3>

          <table>
            <thead>
              <tr>
                <th>Hotel</th>
                <th>Original Time</th>
                <th>New Time</th>
                <th>Filter</th>
              </tr>
            </thead>
            <tbody>
              {previewData.changes.map((change: any) => (
                <tr key={change.trip_id}>
                  <td>{change.hotel_name}</td>
                  <td>{change.original_time}</td>
                  <td>{change.new_time}</td>
                  <td>{change.filter_applied}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {previewData.exclusions.length > 0 && (
            <div className="exclusions">
              <h4>Excluded Operations: {previewData.exclusions.length}</h4>
              {previewData.exclusions.map((ex: any, i: number) => (
                <div key={i}>
                  <strong>{ex.operation}</strong>: {ex.reason}
                </div>
              ))}
            </div>
          )}

          <div className="preview-actions">
            <button onClick={handleApply} disabled={loading}>
              Apply Changes
            </button>
            <button onClick={() => setShowPreview(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
```

---

## 9. UI/UX Guidelines

### 9.1 Layout Recomendado

```
┌──────────────────────────────────────────────────────────┐
│                    Trip Filters                          │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ☐ Reduce Lead Time                                     │
│     Minutes to reduce: [10▼]                            │
│                                                          │
│  ☑ Combine Trips                                        │
│     Min gap: [15] minutes   Max gap: [20] minutes       │
│     Hotels: [All Hotels ▼]                              │
│                                                          │
│  ☐ Expand (Separate Trips)                             │
│     Min gap: [5] Max gap: [10] Max shift: [15]         │
│                                                          │
│  [Preview Changes]  [Apply]  [Undo Last Filter]         │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### 9.2 Preview Modal

```
┌──────────────────────────────────────────────────────────┐
│  Preview: 15 trips will be modified                      │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  Summary:                                               │
│  • Reduce: 5 trips                                      │
│  • Combine: 10 trips (5 pairs)                          │
│  • Expand: 0 trips                                      │
│  • Excluded: 2 operations                               │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │ Hotel           | Original | New     | Filter      │ │
│  ├────────────────────────────────────────────────────┤ │
│  │ Hilton Downtown | 08:00    | 07:50   | reduce      │ │
│  │ Marriott        | 08:15    | 08:10   | combine     │ │
│  │ Marriott        | 08:17    | 08:10   | combine     │ │
│  │ ...                                                 │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  ⚠️ Excluded Operations:                                │
│  • expand(A,B): Collision with previous (gap = 18 min)  │
│  • expand(C,D): Collision with next (gap = 22 min)      │
│                                                          │
│  [✓ Apply Changes]  [✗ Cancel]                          │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### 9.3 Estados del Botón "Undo"

```typescript
// Disabled (no hay batch_id guardado)
<button disabled className="btn-undo-disabled">
  Undo Last Filter
</button>

// Enabled (hay batch_id guardado)
<button className="btn-undo-enabled" onClick={handleUndo}>
  ↶ Undo Last Filter
</button>

// Loading (ejecutando revert)
<button disabled className="btn-undo-loading">
  <Spinner /> Reverting...
</button>
```

### 9.4 Notificaciones

**Success (Apply):**
```
✓ Filters applied successfully
15 trips modified (Reduce: 5, Combine: 10)
Batch ID: abc-123 (saved for undo)
```

**Success (Revert):**
```
↶ Filters reverted successfully
15 trips restored to original times
```

**Warning (Exclusions):**
```
⚠️ Filters applied with exclusions
13 trips modified, 2 operations excluded
View excluded operations for details
```

**Error:**
```
✗ Failed to apply filters
Error: max_gap must be >= min_gap
Please correct the configuration and try again
```

### 9.5 Indicadores Visuales en Trip List

Trips con filtros aplicados deben mostrarse diferente:

```typescript
<tr className={trip.filter_applied ? 'trip-filtered' : 'trip-normal'}>
  <td>{trip.pick_up_time}</td>
  {trip.filter_applied && (
    <td>
      <Badge variant="info">{trip.filter_applied}</Badge>
      <Tooltip>
        Original: {trip.original_pick_up_time}
        Modified: {trip.filtered_at}
        Batch: {trip.filter_batch_id}
      </Tooltip>
    </td>
  )}
</tr>
```

**Ejemplo visual:**
```
08:00  [reduce] ℹ️  (hover: "Originally 08:10")
08:15  [combine] ℹ️ (hover: "Originally 08:17")
09:30              (no filter applied)
```

---

## 10. Testing y QA

### 10.1 Test Cases - Reduce

| Test | Config | Input | Expected Output |
|------|--------|-------|-----------------|
| Reduce simple | minutes=10 | 08:00 | 07:50 |
| Reduce con redondeo | minutes=12 | 08:00 | 07:50 (08:00-12=07:48→07:50) |
| Reduce cruzando medianoche | minutes=15 | 00:10 | 23:55 |
| Reduce con time_range | minutes=10, range=[05:00-10:00] | 08:00, 12:00 | 07:50, 12:00 (solo primero) |
| Reduce con hotel filter | minutes=10, hotels=["Hilton"] | Hilton:08:00, Marriott:08:15 | 07:50, 08:15 (solo Hilton) |

### 10.2 Test Cases - Combine

| Test | Config | Input | Expected Output |
|------|--------|-------|-----------------|
| Combine simple | min=15, max=20 | 08:00, 08:17 | 08:10, 08:10 |
| Combine fuera de rango | min=15, max=20 | 08:00, 08:30 | 08:00, 08:30 (sin cambios) |
| Combine múltiples pares | min=15, max=20 | 08:00,08:17; 08:45,08:58 | 08:10,08:10; 08:50,08:50 |
| Combine con Reduce previo | Reduce+Combine | 08:00→07:50, 08:05 | 07:50, 08:05 (A ya modificado) |

### 10.3 Test Cases - Expand

| Test | Config | Input | Expected Output |
|------|--------|-------|-----------------|
| Expand simple | min=5, max=10, shift=15 | 08:00, 08:08 | 07:55, 08:20 |
| Expand sin collision | min=5, max=10, shift=15, Combine=[15-20] | 08:00, 08:08, sin vecinos | 07:55, 08:20 |
| Expand con collision prev | min=5, max=10, shift=15, Combine=[15-20] | 07:30, 08:00, 08:08 | 08:00, 08:08 (rechazado) |
| Expand con collision next | min=5, max=10, shift=15, Combine=[15-20] | 08:00, 08:08, 08:30 | 08:00, 08:08 (rechazado) |

### 10.4 Test Cases - Regla A

| Test | Filters | Input | Expected |
|------|---------|-------|----------|
| Reduce + Combine | Reduce(10) + Combine(15-20) | A:08:00, B:08:10 | A→07:50 (reduce), B sin cambios |
| Combine + Expand | Combine(15-20) + Expand(5-10,shift=15) | A:08:00, B:08:17, C:08:22 | A,B→08:10 (combine), C sin cambios |

### 10.5 Integration Tests

```typescript
describe('Filter System Integration', () => {
  it('should preview without modifying DB', async () => {
    const before = await getTrip(tripId);
    await preview({reduce: {enabled: true, minutes_to_reduce: 10}});
    const after = await getTrip(tripId);

    expect(after.pick_up_time).toBe(before.pick_up_time);
  });

  it('should apply and track changes', async () => {
    const result = await apply({reduce: {enabled: true, minutes_to_reduce: 10}});
    const trip = await getTrip(tripId);

    expect(trip.original_pick_up_time).toBe('08:00:00');
    expect(trip.pick_up_time).toBe('07:50:00');
    expect(trip.filter_applied).toBe('reduce');
    expect(trip.filter_batch_id).toBe(result.batch_id);
  });

  it('should revert to original', async () => {
    await apply({reduce: {enabled: true, minutes_to_reduce: 10}});
    await revert(batchId);
    const trip = await getTrip(tripId);

    expect(trip.pick_up_time).toBe('08:00:00');
    expect(trip.original_pick_up_time).toBeNull();
    expect(trip.filter_applied).toBeNull();
  });
});
```

---

## 11. Troubleshooting

### 11.1 Problemas Comunes

#### "No changes in preview"

**Causas:**
1. No hay trips elegibles (todos son Inbound o no Scheduled)
2. Filtros de hotel/time_range demasiado restrictivos
3. Config de gaps fuera de rango real

**Solución:**
```typescript
// Verificar trips elegibles
console.log('Total evaluated:', previewResult.total_trips_evaluated);
console.log('Eligible:', previewResult.eligible_trips);
console.log('Changes:', previewResult.changes.length);

// Si eligible = 0, verificar trip_type y status en DB
// Si eligible > 0 pero changes = 0, revisar config de filtros
```

#### "max_gap must be >= min_gap"

**Causa:** Validación de backend falló

**Solución:**
```typescript
if (config.combine?.max_gap < config.combine?.min_gap) {
  showError('Max gap must be greater than or equal to min gap');
  return;
}
```

#### "Apply no hace nada"

**Causas:**
1. Backend retornó success pero 0 changes
2. Frontend no está refetchando trips después de Apply

**Solución:**
```typescript
const result = await apply(config);
if (result.changes_applied === 0) {
  showWarning('No changes were applied (check preview first)');
} else {
  // Refetch trips
  await refetchTrips();
  showSuccess(`${result.changes_applied} trips modified`);
}
```

#### "Undo button no aparece"

**Causa:** batch_id no se guardó correctamente

**Solución:**
```typescript
useEffect(() => {
  // Load from localStorage on mount
  const saved = localStorage.getItem(`filterBatch_${locationId}`);
  if (saved) {
    setLastBatchId(saved);
  }
}, [locationId]);
```

### 11.2 Debug Checklist

```
□ Backend logs: docker logs gt360 | grep FILTER
□ Verificar trips elegibles en DB: SELECT count(*) FROM trips.trips WHERE trip_type = 'outbound' AND status = 'scheduled'
□ Verificar JWT token válido y no expirado
□ Verificar rol = 'manager' en token
□ Verificar location_id es UUID válido
□ Verificar configuración de filtros pasa validación
□ Verificar batch_id guardado en localStorage
□ Verificar frontend refetch después de Apply
□ Verificar WebSocket conectado para updates en tiempo real
```

---

## 12. Casos Edge

### 12.1 Trip en Límite de Día

```
Trip: 23:55
Reduce: 10 minutos
Result: 23:45 ✅ (NO cruza medianoche)

Trip: 00:05
Reduce: 10 minutos
Result: 23:55 del día anterior ✅
```

**Backend maneja automáticamente**, frontend debe mostrar correctamente.

### 12.2 Time Range Cruzando Medianoche

```
Config: time_range = {start: "22:00", end: "02:00"}

Trip A: 21:30 → ❌ Fuera de rango
Trip B: 23:00 → ✅ En rango (22:00-23:59)
Trip C: 00:30 → ✅ En rango (00:00-02:00)
Trip D: 03:00 → ❌ Fuera de rango
```

### 12.3 Todos los Trips Ya Filtrados

```
Escenario: Usuario ejecuta Apply dos veces con la misma config

Primera ejecución:
- Trip A: 08:00 → 07:50 ✅ (original_pick_up_time = 08:00)

Segunda ejecución:
- Trip A: 07:50 (pero usa original_pick_up_time = 08:00)
- Trip A: 08:00 → 07:50 ✅ (mismo resultado, NO drift)
```

### 12.4 Expand Rechazado Completamente

```
Config:
  Expand: min=5, max=10, shift=15
  Combine: min=15, max=20

Trips:
  A: 08:00
  B: 08:08 } Gap = 8 min (en rango Expand)
  C: 08:25

Intento Expand A,B:
  new_A = 07:55
  new_B = 08:20
  gap(new_B, C) = 5 min ← ❌ No está en rango Combine [15-20]

Pero... ¿qué pasa si hay un Trip D antes de A?
  D: 07:40
  gap(D, new_A) = 15 min ← ⚠️ SÍ está en rango Combine [15-20]
  → RECHAZADO por colisión

Resultado: A y B quedan sin cambios, registrado en exclusions
```

---

## 📞 Soporte y Contacto

**Backend Team:** GT360 Engineering
**Documentación:** [FRONTEND_FILTER_SYSTEM_SUMMARY.md](FRONTEND_FILTER_SYSTEM_SUMMARY.md)
**API Status:** https://api.gt360.app/health

---

**Última actualización:** 2026-01-16
**Versión:** 2.0
**Autor:** Claude Sonnet 4.5

---

## Apéndice A: Diagramas de Flujo Completos

### A.1 Flujo Preview

```
[Usuario configura filtros]
        ↓
[Click "Preview"]
        ↓
Frontend valida configuración
        ↓
POST /filters/preview
        ↓
Backend: Obtener trips elegibles
        ↓
Backend: Filtrar por hotel_names / time_range
        ↓
Backend: Aplicar Reduce (si enabled)
        ↓
Backend: Aplicar Combine (si enabled, respeta Regla A)
        ↓
Backend: Aplicar Expand (si enabled, respeta Regla A y B)
        ↓
Backend: Generar summary y exclusions
        ↓
Response → Frontend
        ↓
Frontend: Mostrar tabla de cambios
        ↓
Frontend: Mostrar exclusiones (si las hay)
        ↓
[Usuario decide: Apply o Cancel]
```

### A.2 Flujo Apply

```
[Usuario confirma en preview modal]
        ↓
[Click "Apply"]
        ↓
POST /filters/apply
        ↓
Backend: Generar batch_id = uuid4()
        ↓
Backend: Obtener trips elegibles
        ↓
Backend: Ejecutar filtros (igual que preview)
        ↓
Backend: FOR EACH change:
  - Si trip.original_pick_up_time es NULL:
      → trip.original_pick_up_time = trip.pick_up_time (backup)
  - trip.pick_up_time = new_time
  - trip.filter_applied = filter_type
  - trip.filter_batch_id = batch_id
  - trip.filtered_at = NOW()
        ↓
Backend: COMMIT transaction
        ↓
Response → Frontend
        ↓
Frontend: Guardar batch_id en localStorage
        ↓
Frontend: Refetch trips (actualizar UI)
        ↓
Frontend: Habilitar botón "Undo"
        ↓
Frontend: Mostrar notificación de éxito
```

### A.3 Flujo Revert

```
[Usuario click "Undo"]
        ↓
POST /filters/revert?batch_id=xxx
        ↓
Backend: SELECT trips WHERE filter_batch_id = xxx
        ↓
Backend: FOR EACH trip:
  - trip.pick_up_time = trip.original_pick_up_time
  - trip.original_pick_up_time = NULL
  - trip.filter_applied = NULL
  - trip.filter_batch_id = NULL
  - trip.filtered_at = NULL
        ↓
Backend: COMMIT transaction
        ↓
Response → Frontend
        ↓
Frontend: Limpiar batch_id de localStorage
        ↓
Frontend: Refetch trips (actualizar UI)
        ↓
Frontend: Deshabilitar botón "Undo"
        ↓
Frontend: Mostrar notificación "Cambios revertidos"
```

---

**FIN DEL DOCUMENTO**
