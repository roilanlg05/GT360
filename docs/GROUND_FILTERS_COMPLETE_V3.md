# Ground Filters - Documentación Completa V3

**Fecha:** 2026-01-20
**Versión:** 3.0
**Autor:** Backend Team
**Estado:** ✅ Implementado y Deployed con Auto-Revert

---

## 📋 Tabla de Contenidos

1. [Visión General](#1-visión-general)
2. [Cambios en V3: Auto-Revert](#2-cambios-en-v3-auto-revert)
3. [Arquitectura del Sistema](#3-arquitectura-del-sistema)
4. [Tipos de Filtros](#4-tipos-de-filtros)
5. [Criterios de Elegibilidad](#5-criterios-de-elegibilidad)
6. [Reglas de Negocio](#6-reglas-de-negocio)
7. [Flujo Completo Paso a Paso](#7-flujo-completo-paso-a-paso)
8. [Endpoints API](#8-endpoints-api)
9. [Modelos de Datos](#9-modelos-de-datos)
10. [Lógica Interna del Servicio](#10-lógica-interna-del-servicio)
11. [Casos de Uso Completos](#11-casos-de-uso-completos)
12. [Ejemplos Request/Response](#12-ejemplos-requestresponse)
13. [Frontend Integration](#13-frontend-integration)
14. [Troubleshooting](#14-troubleshooting)
15. [Diagramas de Flujo](#15-diagramas-de-flujo)

---

## 1. Visión General

### 1.1 ¿Qué son los Ground Filters?

Los **Ground Filters** son un sistema de optimización automática de tiempos de pickup para **transporte terrestre** de trips tipo **OUTBOUND** (Hotel → Airport).

**⚠️ IMPORTANTE:**
- **"Ground Filters"** = Filtros para optimizar el **transporte terrestre** al aeropuerto
- **"Ground Filters"** ≠ Filtros para trips tipo `ground` (Hotel → Hotel)

### 1.2 Objetivo

Optimizar la logística de transporte terrestre ajustando automáticamente los `pick_up_time` de trips outbound para:
- **Reducir** tiempos de anticipación excesivos
- **Combinar** trips cercanos en un solo pickup
- **Separar** trips demasiado juntos para evitar congestión

### 1.3 Alcance

**Aplica SOLO a trips con:**
- ✅ `trip_type = 'outbound'` (Hotel → Airport)
- ✅ `status = 'scheduled'` (No completados, no cancelados)
- ✅ `filter_applied = NULL` **O** con filtros previos (se revierten automáticamente en V3)

**NO aplica a:**
- ❌ `trip_type = 'inbound'` (Airport → Hotel)
- ❌ `trip_type = 'ground'` (Hotel → Hotel)
- ❌ Status completed, cancelled, en_route

---

## 2. Cambios en V3: Auto-Revert

### 2.1 Problema Resuelto en V3

**Problema en V2:**
```
1. Usuario aplica filtro REDUCE → filter_applied = 'reduce'
2. Usuario intenta aplicar COMBINE:
   - ❌ Preview devuelve 0 trips (busca filter_applied == NULL)
   - ❌ Apply también falla
   - Usuario debe revertir manualmente primero
```

**Solución en V3 (2026-01-20):**
```
1. Usuario aplica filtro REDUCE → filter_applied = 'reduce'
2. Usuario intenta aplicar COMBINE:
   - ✅ Preview funciona (ignora filter_applied)
   - ✅ Apply hace auto-revert + aplica nuevos filtros
   - Usuario NO necesita llamar /revert manualmente

Cambios implementados:
- /preview: Removido filtro "filter_applied == NULL" (trip_filter_service.py:525)
- /apply: Auto-revert cuando detecta filter_applied != NULL (trips_router.py:1441-1494)
```

### 2.2 Flujo de Auto-Revert

```
POST /filters/apply con {combine: enabled}
          ↓
[1] Backend verifica: ¿Hay trips con filter_applied != NULL?
          ↓
     SÍ → [2] Auto-Revert
          ↓
          - Restaura todos los trips a original_pick_up_time
          - Limpia filter_applied, filter_batch_id
          - Registra en log
          ↓
[3] Aplica nuevos filtros
          ↓
[4] Retorna resultado con log de auto-revert
```

### 2.3 Ventajas del Auto-Revert

✅ **Transparente:** Usuario no necesita llamar `/revert` manualmente
✅ **Flexible:** Permite aplicar filtros uno por uno o todos juntos
✅ **Seguro:** Mantiene historial de batches
✅ **Informativo:** Log incluye información de qué se revirtió

---

## 3. Arquitectura del Sistema

### 3.1 Capas de la Aplicación

```
┌─────────────────────────────────────────────────────────┐
│                   FRONTEND                              │
│  (React + TypeScript + React Query)                    │
└─────────────────────────────────────────────────────────┘
                        ↓ HTTP/REST
┌─────────────────────────────────────────────────────────┐
│                API LAYER (FastAPI)                      │
│  - trips_router.py                                      │
│  - Endpoints: /preview, /apply, /revert, /eligibility  │
│  - AUTO-REVERT logic (V3)                               │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│              SERVICE LAYER                              │
│  - TripFilterService (trip_filter_service.py)          │
│  - Lógica de negocio                                    │
│  - Validaciones y reglas                                │
│  - Aplicación de filtros                                │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│              DATA MODELS                                │
│  - filter_models.py (Pydantic)                          │
│  - FilterRequest, FilterPreviewResult, etc.             │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│            DATABASE LAYER (PostgreSQL)                  │
│  - trips.trips (pick_up_time, original_pick_up_time)   │
│  - trips.filter_batches (historial)                     │
│  - trips.filter_previews (cross-device sync)           │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Base de Datos

#### Tabla `trips.trips`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `location_id` | UUID | Foreign key a locations |
| `airline` | VARCHAR(10) | Código de aerolínea |
| `trip_type` | VARCHAR(10) | 'inbound', 'outbound', 'ground' |
| `status` | VARCHAR(20) | 'scheduled', 'completed', etc. |
| `pick_up_time` | TIME | **Tiempo actual** (puede estar modificado por filtros) |
| `original_pick_up_time` | TIME | **Tiempo original** (backup para revert) |
| `pick_up_date` | DATE | Fecha del pickup |
| `filter_applied` | VARCHAR(10) | 'reduce', 'combine', 'expand', NULL |
| `filter_batch_id` | UUID | ID del batch que modificó este trip |
| `filtered_at` | TIMESTAMPTZ | Cuándo se aplicó el filtro |

#### Tabla `trips.filter_batches`

Guarda el historial de aplicaciones de filtros:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | UUID | Primary key (batch ID) |
| `location_id` | UUID | Location afectada |
| `airline` | VARCHAR(10) | Airline afectada |
| `config` | JSONB | Configuración de filtros aplicada |
| `filters_applied` | VARCHAR[] | ['reduce', 'combine', 'expand'] |
| `trips_affected` | INTEGER | Cantidad de trips modificados |
| `created_at` | TIMESTAMPTZ | Cuándo se aplicó |
| `reverted_at` | TIMESTAMPTZ | NULL o cuándo se revirtió |

#### Tabla `trips.filter_previews`

Almacena preview results para sincronización cross-device:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `location_id` | UUID | Location |
| `airline` | VARCHAR(10) | Airline |
| `config` | JSONB | FilterRequest |
| `result` | JSONB | FilterPreviewResult |
| `created_at` | TIMESTAMPTZ | Timestamp |

---

## 4. Tipos de Filtros

### 4.1 REDUCE (Priority 0)

**Objetivo:** Reducir el tiempo de anticipación de todos los trips.

**Comportamiento:**
- Resta una cantidad fija de minutos del `original_pick_up_time`
- **SIEMPRE** opera sobre `original_pick_up_time`, NO sobre tiempos ya modificados
- Priority 0: Se ejecuta PRIMERO y NO está sujeto a Rule A

**Ejemplo:**
```
Original:    08:00 AM
Reduce: -20  → 07:40 AM
```

**Configuración:**
```json
{
  "enabled": true,
  "minutes_to_reduce": 20,
  "hotel_names": null,  // Opcional: filtrar por hoteles
  "time_range": null     // Opcional: filtrar por rango de tiempo
}
```

**Casos de exclusión:**
- Tiempo resultante < 00:00 (se excluye el trip)
- Hotel no está en `hotel_names` (si se especifica)
- Tiempo no está en `time_range` (si se especifica)

---

### 4.2 COMBINE (Priority 1)

**Objetivo:** Combinar trips muy cercanos en un solo pickup.

**Comportamiento:**
- Busca pares de trips dentro del rango `[min_gap, max_gap]`
- Mueve ambos trips al punto medio entre ellos
- Sujeto a **Rule A**: Un trip modificado por Combine NO se vuelve a modificar

**Ejemplo:**
```
Trip A: 08:00 AM
Trip B: 08:15 AM
Gap: 15 min (dentro de rango 10-20)

Resultado:
Trip A: 08:07 AM (punto medio)
Trip B: 08:07 AM (punto medio)
```

**Configuración:**
```json
{
  "enabled": true,
  "min_gap": 10,  // Mínimo gap en minutos
  "max_gap": 20,  // Máximo gap en minutos
  "hotel_names": null,
  "time_range": null
}
```

**Casos de exclusión:**
- Trip ya fue modificado por otro filtro Combine/Expand (Rule A)
- Gap no está en rango [min_gap, max_gap]
- Hotel no coincide
- Tiempo no está en rango

---

### 4.3 EXPAND (Priority 1)

**Objetivo:** Separar trips muy juntos para evitar congestión.

**Comportamiento:**
- Busca pares de trips con gap < `min_gap`
- Los separa hasta alcanzar `min_gap` + `max_shift`
- Sujeto a **Rule A** y **Rule B** (No-Collision Rule)

**Ejemplo:**
```
Trip A: 08:00 AM
Trip B: 08:05 AM
Gap: 5 min (menor a min_gap=20)

Configuración: min_gap=20, max_shift=10

Resultado:
Trip A: 07:55 AM (-5 min)
Trip B: 08:15 AM (+10 min)
Nuevo gap: 20 min
```

**Configuración:**
```json
{
  "enabled": true,
  "min_gap": 20,     // Gap mínimo deseado
  "max_gap": 30,     // Gap máximo permitido
  "max_shift": 10,   // Máximo movimiento por trip
  "hotel_names": null,
  "time_range": null
}
```

**Casos de exclusión:**
- Trip ya fue modificado (Rule A)
- Gap resultante caería en rango de Combine (Rule B: No-Collision)
- No se puede alcanzar el `min_gap` con `max_shift`

---

## 5. Criterios de Elegibilidad

### 5.1 Criterios Obligatorios

Un trip es **elegible** para Ground Filters si cumple **TODOS** estos criterios:

```python
✅ trip_type == TripType.OUTBOUND      # Hotel → Airport
✅ status == TripStatus.SCHEDULED      # No completado, no cancelado
✅ location_id == {solicitado}
✅ airline == {solicitado}
✅ pick_up_date en rango [date_from, date_to]  # Si se especifica
```

### 5.2 ¿Qué pasa con trips con filtros ya aplicados? (V3)

**V2 (anterior):**
```python
✅ filter_applied == NULL  # REQUERIDO en /preview y /apply
```

**V3 (actual - Fix 2026-01-20):**
```python
filter_applied puede ser cualquier valor

En /preview:
→ Ignora filter_applied (encuentra todos los trips elegibles)
→ Muestra cómo quedarían los cambios

En /apply:
→ Si filter_applied != NULL, se auto-revierte ANTES de aplicar
→ Luego aplica los nuevos filtros normalmente
```

### 5.3 Query SQL de Elegibilidad (V3)

```sql
-- Trips elegibles para Ground Filters (V3)
SELECT * FROM trips.trips
WHERE location_id = '{location_uuid}'
  AND airline = 'WN'
  AND trip_type = 'outbound'
  AND status = 'scheduled'
  AND pick_up_date >= '2026-01-01'
  AND pick_up_date <= '2026-01-31'
-- ✅ V3: NO filtra por filter_applied (permite preview/apply sobre trips con filtros existentes)
-- ❌ V2: Filtraba por filter_applied == NULL
```

---

## 6. Reglas de Negocio

### 6.1 Rule A: No Re-Modificar (Solo Combine/Expand)

**Definición:**
Un trip modificado por Combine o Expand **NO puede** ser modificado nuevamente por Combine o Expand en la misma ejecución.

**Aplica a:** Combine, Expand
**NO aplica a:** Reduce

**Razón:**
Evitar bucles infinitos y comportamientos impredecibles.

**Ejemplo:**
```
Trip A: 08:00 → 08:07 (modificado por Combine)
Trip B: 08:15 → 08:07 (modificado por Combine)

Expand NO puede mover Trip A ni Trip B porque ya fueron modificados.
```

**Implementación:**
```python
self.modified_by_combine_expand: set[UUID] = set()

# Cuando Combine modifica un trip:
self.modified_by_combine_expand.add(trip_a.id)
self.modified_by_combine_expand.add(trip_b.id)

# Expand verifica:
if trip.id in self.modified_by_combine_expand:
    continue  # Skip
```

---

### 6.2 Rule B: No-Collision Rule (Solo Expand)

**Definición:**
Expand NO debe crear gaps que caigan dentro del rango de Combine.

**Aplica a:** Expand
**NO aplica a:** Reduce, Combine

**Razón:**
Evitar que Expand separe trips de manera que luego Combine los vuelva a juntar.

**Ejemplo:**
```
Configuración:
- Combine: min_gap=10, max_gap=20
- Expand: min_gap=25, max_shift=10

Escenario:
Trip A: 08:00
Trip B: 08:05
Gap actual: 5 min

Expand intenta:
Trip A: 07:55 (-5)
Trip B: 08:15 (+10)
Nuevo gap: 20 min

❌ RECHAZADO porque 20 min cae en rango de Combine [10, 20]
```

**Implementación:**
```python
def _would_collide_with_combine(self, gap_minutes: int, combine_config: CombineFilterConfig) -> bool:
    if not combine_config or not combine_config.enabled:
        return False

    return combine_config.min_gap <= gap_minutes <= combine_config.max_gap
```

---

### 6.3 Priority System

**Priority 0: Reduce**
- Se ejecuta PRIMERO
- Opera sobre `original_pick_up_time`
- NO está sujeto a Rule A

**Priority 1: Combine y Expand**
- Se ejecutan DESPUÉS de Reduce
- Operan sobre tiempos efectivos (después de Reduce)
- SÍ están sujetos a Rule A y Rule B

**Orden de ejecución:**
```
1. REDUCE    (Priority 0)
2. COMBINE   (Priority 1)
3. EXPAND    (Priority 1)
```

---

### 6.4 Rounding Mode

Todos los tiempos resultantes se redondean según el `rounding_mode`:

**multiple_of_5 (default):**
```
07:43 → 07:45
07:47 → 07:45
07:48 → 07:50
```

**odd_minutes:**
```
07:44 → 07:45
07:46 → 07:47
07:48 → 07:49
```

---

## 7. Flujo Completo Paso a Paso

### 7.1 Flujo Preview (Simulación)

```
1. Usuario configura filtros en UI
2. Frontend → POST /filters/preview
3. Backend valida:
   - location_id existe
   - airline válido
   - fechas válidas
4. Backend obtiene trips elegibles (outbound + scheduled)
5. Backend aplica filtros en orden (reduce → combine → expand)
   - Reduce opera sobre original_pick_up_time
   - Combine opera sobre tiempos efectivos
   - Expand opera sobre tiempos efectivos
6. Backend NO persiste cambios
7. Backend retorna:
   - changes: Lista de cambios propuestos
   - exclusions: Trips excluidos con razón
   - summary: Conteo por filtro
8. Frontend muestra preview
9. Backend guarda preview en filter_previews (cross-device sync)
```

---

### 7.2 Flujo Apply (Persistir Cambios) - V3 con Auto-Revert

```
1. Usuario hace clic en "Apply Changes"
2. Frontend → POST /filters/apply
3. Backend valida (igual que preview)

4. ⭐ NUEVO EN V3: Auto-Revert Check
   ├─ Backend verifica: ¿Hay trips con filter_applied != NULL?
   │
   ├─ SÍ → Auto-Revert
   │   ├─ Busca todos los trips con filtros aplicados
   │   ├─ Restaura pick_up_time = original_pick_up_time
   │   ├─ Limpia filter_applied, filter_batch_id, filtered_at
   │   ├─ Registra en log: "auto_revert"
   │   └─ Commitea cambios
   │
   └─ NO → Continúa directamente

5. Backend aplica filtros (igual que preview)
6. Backend persiste cambios:
   - Actualiza pick_up_time
   - Guarda original_pick_up_time (si no existe)
   - Asigna filter_applied, filter_batch_id, filtered_at
7. Backend crea registro en filter_batches
8. Backend limpia preview guardado
9. Backend retorna:
   - batch_id (para revert posterior)
   - changes_applied
   - log (incluye auto-revert si aplicó)
10. Frontend actualiza UI
```

---

### 7.3 Flujo Revert (Deshacer Cambios)

```
1. Usuario hace clic en "Revert Filters"
2. Frontend → POST /filters/revert?batch_id={uuid}
3. Backend busca trips con filter_batch_id == {uuid}
4. Para cada trip:
   - pick_up_time = original_pick_up_time
   - filter_applied = NULL
   - filter_batch_id = NULL
   - filtered_at = NULL
5. Backend actualiza filter_batches.reverted_at
6. Backend retorna trips_reverted
7. Frontend actualiza UI
```

---

### 7.4 Flujo Revert Partial (Revertir UN Filtro)

```
1. Usuario hace clic en "Revert Reduce Only"
2. Frontend → POST /filters/revert-partial?batch_id={uuid}&filter_type=reduce
3. Backend:
   - Busca FilterBatch por batch_id
   - Valida que "reduce" fue aplicado en ese batch
   - Busca trips del batch
   - Revierte todos a original_pick_up_time
   - Reconstruye config SIN reduce
   - Re-aplica combine y expand
4. Backend actualiza filter_batches.revert_history
5. Backend retorna nuevos cambios
6. Frontend actualiza UI
```

---

## 8. Endpoints API

### 8.1 POST `/filters/preview`

**URL:** `/v1/locations/{location_id}/airlines/{airline}/trips/filters/preview`

**Método:** POST

**Headers:**
```
Authorization: Bearer {token}
Content-Type: application/json
```

**Request Body:**
```json
{
  "pick_up_date_from": "2026-01-01",
  "pick_up_date_to": "2026-01-31",
  "rounding_mode": "multiple_of_5",
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 20,
    "hotel_names": null,
    "time_range": null
  },
  "combine": {
    "enabled": true,
    "min_gap": 10,
    "max_gap": 20,
    "hotel_names": null,
    "time_range": null
  },
  "expand": {
    "enabled": false,
    "min_gap": 21,
    "max_gap": 30,
    "max_shift": 10,
    "hotel_names": null,
    "time_range": null
  }
}
```

**Response:**
```json
{
  "location_id": "uuid",
  "airline": "WN",
  "changes": [
    {
      "trip_id": "uuid",
      "original_time": "08:00 AM",
      "new_time": "07:40 AM",
      "filter_applied": "reduce",
      "hotel_name": "Marriott",
      "flight_number": "WN1234",
      "pick_up_date": "2026-01-15"
    }
  ],
  "exclusions": [
    {
      "trip_id": "uuid",
      "reason": "Reduce would result in time < 00:00",
      "filter_type": "reduce",
      "trip_info": {
        "pick_up_time": "00:10 AM",
        "pick_up_location": "Hotel ABC",
        "flight_number": "WN5678"
      }
    }
  ],
  "summary": {
    "reduce": 150,
    "combine": 0,
    "expand": 0,
    "excluded": 5
  },
  "total_trips_evaluated": 500,
  "eligible_trips": 495
}
```

---

### 8.2 POST `/filters/apply` (V3 con Auto-Revert)

**URL:** `/v1/locations/{location_id}/airlines/{airline}/trips/filters/apply`

**Método:** POST

**Request Body:** Igual que `/preview`

**Response:**
```json
{
  "batch_id": "uuid",
  "location_id": "uuid",
  "airline": "WN",
  "changes_applied": 150,
  "exclusions": [...],
  "log": [
    {
      "action": "auto_revert",
      "message": "Automatically reverted 200 trips with existing filters before applying new filters",
      "batches_reverted": ["uuid-aaa", "uuid-bbb"]
    },
    {
      "trip_id": "uuid",
      "action": "modified",
      "filter": "reduce",
      "original_time": "08:00",
      "new_time": "07:40",
      "hotel": "Marriott"
    }
  ],
  "summary": {
    "reduce": 150,
    "combine": 0,
    "expand": 0,
    "excluded": 5
  }
}
```

**⭐ IMPORTANTE EN V3:**
- Si hay trips con `filter_applied != NULL`, se auto-revierten automáticamente
- El log incluye entrada `"auto_revert"` con información de lo que se revirtió
- Usuario NO necesita llamar `/revert` manualmente

---

### 8.3 POST `/filters/revert`

**URL:** `/v1/locations/{location_id}/airlines/{airline}/trips/filters/revert`

**Método:** POST

**Query Params:**
- `batch_id` (opcional): UUID del batch a revertir. Si NULL, revierte todos.

**Response:**
```json
{
  "location_id": "uuid",
  "airline": "WN",
  "trips_reverted": 150,
  "batch_ids_reverted": ["uuid-aaa"],
  "message": "Successfully reverted 150 trips from 1 batch(es)"
}
```

---

### 8.4 POST `/filters/revert-partial`

**URL:** `/v1/locations/{location_id}/airlines/{airline}/trips/filters/revert-partial`

**Método:** POST

**Query Params:**
- `batch_id` (requerido): UUID del batch
- `filter_type` (requerido): "reduce", "combine", o "expand"

**Response:**
```json
{
  "batch_id": "uuid",
  "filter_type_reverted": "reduce",
  "trips_affected": 150,
  "remaining_filters": ["combine"],
  "message": "Successfully reverted 'reduce' and re-applied remaining filters"
}
```

---

### 8.5 GET `/filters/current`

**URL:** `/v1/locations/{location_id}/airlines/{airline}/trips/filters/current`

**Método:** GET

**Response:**
```json
{
  "has_filters": true,
  "batches": [
    {
      "batch_id": "uuid",
      "filters_applied": ["reduce", "combine"],
      "config": {
        "reduce": {"enabled": true, "minutes_to_reduce": 20},
        "combine": {"enabled": true, "min_gap": 10, "max_gap": 20}
      },
      "trips_affected": 150,
      "created_at": "2026-01-20T10:30:00Z"
    }
  ]
}
```

---

### 8.6 GET `/filters/history`

**URL:** `/v1/locations/{location_id}/airlines/{airline}/trips/filters/history`

**Método:** GET

**Response:**
```json
{
  "history": [
    {
      "batch_id": "uuid",
      "filters_applied": ["reduce"],
      "trips_affected": 150,
      "created_at": "2026-01-20T10:30:00Z",
      "reverted_at": "2026-01-20T15:45:00Z"
    }
  ]
}
```

---

### 8.7 GET `/filters/eligibility` (Diagnostic)

**URL:** `/v1/locations/{location_id}/airlines/{airline}/trips/filters/eligibility`

**Método:** GET

**Query Params:**
- `pick_up_date_from` (opcional)
- `pick_up_date_to` (opcional)

**Response:**
```json
{
  "total_trips": 674,
  "eligible_trips": 500,
  "by_trip_type": {
    "outbound": 500,
    "inbound": 174
  },
  "by_status": {
    "scheduled": 674
  },
  "eligible_breakdown": {
    "outbound_scheduled_no_filter": 500,
    "outbound_scheduled_with_filter": 0,
    "outbound_other_status": 0
  },
  "reason": null
}
```

---

### 8.8 GET `/filters/preview/last` (Cross-Device Sync)

**URL:** `/v1/locations/{location_id}/airlines/{airline}/trips/filters/preview/last`

**Método:** GET

**Response:**
```json
{
  "preview_id": "uuid",
  "location_id": "uuid",
  "airline": "WN",
  "config": {...},
  "result": {...},
  "created_at": "2026-01-20T10:30:00Z"
}
```

---

## 9. Modelos de Datos

### 9.1 FilterRequest

```typescript
interface FilterRequest {
  pick_up_date_from?: string;  // YYYY-MM-DD
  pick_up_date_to?: string;    // YYYY-MM-DD
  rounding_mode: "multiple_of_5" | "odd_minutes";
  reduce: ReduceFilterConfig;
  combine: CombineFilterConfig;
  expand: ExpandFilterConfig;
}
```

### 9.2 ReduceFilterConfig

```typescript
interface ReduceFilterConfig {
  enabled: boolean;
  minutes_to_reduce: number;  // Cantidad de minutos a restar
  hotel_names?: string[];     // Opcional: solo estos hoteles
  time_range?: TimeRange;     // Opcional: solo en este rango
}
```

### 9.3 CombineFilterConfig

```typescript
interface CombineFilterConfig {
  enabled: boolean;
  min_gap: number;           // Gap mínimo para combinar
  max_gap: number;           // Gap máximo para combinar
  hotel_names?: string[];
  time_range?: TimeRange;
}
```

### 9.4 ExpandFilterConfig

```typescript
interface ExpandFilterConfig {
  enabled: boolean;
  min_gap: number;           // Gap mínimo deseado
  max_gap: number;           // Gap máximo permitido
  max_shift: number;         // Máximo movimiento por trip
  hotel_names?: string[];
  time_range?: TimeRange;
}
```

### 9.5 TimeRange

```typescript
interface TimeRange {
  start: string;  // HH:MM (24h format)
  end: string;    // HH:MM (24h format)
}
```

### 9.6 TripChange

```typescript
interface TripChange {
  trip_id: string;
  original_time: string;     // Formato según preferencia usuario
  new_time: string;
  filter_applied: "reduce" | "combine" | "expand";
  hotel_name: string;
  flight_number: string;
  pick_up_date: string;
  pick_up_location: string;
  drop_off_location: string;
}
```

### 9.7 FilterExclusion

```typescript
interface FilterExclusion {
  trip_id: string;
  reason: string;
  filter_type: "reduce" | "combine" | "expand";
  trip_info: {
    pick_up_time: string;
    original_pick_up_time?: string;
    pick_up_location: string;
    flight_number: string;
    pick_up_date: string;
  };
}
```

### 9.8 FilterPreviewResult

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
```

### 9.9 FilterApplyResult

```typescript
interface FilterApplyResult {
  batch_id: string;
  location_id: string;
  airline: string;
  changes_applied: number;
  exclusions: FilterExclusion[];
  log: Array<{
    action: string;
    message?: string;
    trip_id?: string;
    filter?: string;
    batches_reverted?: string[];  // ⭐ NUEVO EN V3
  }>;
  summary: {
    reduce: number;
    combine: number;
    expand: number;
    excluded: number;
  };
}
```

---

## 10. Lógica Interna del Servicio

### 10.1 Clase TripFilterService

```python
class TripFilterService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.modified_by_combine_expand: set[UUID] = set()
        self.changes: list[TripChange] = []
        self.exclusions: list[FilterExclusion] = []
        self.log: list[dict] = []
        self.rounding_mode: RoundingMode = RoundingMode.MULTIPLE_OF_5
```

### 10.2 Métodos Principales

#### preview()

```python
async def preview(
    self,
    location_id: UUID,
    airline: str,
    config: FilterRequest,
    time_format: str = "24h",
) -> FilterPreviewResult:
    # 1. Reset state
    self._reset_state()

    # 2. Get eligible trips
    trips = await self._get_eligible_trips(location_id, airline, ...)

    # 3. Apply filters (simulation)
    if config.reduce.enabled:
        self._apply_reduce(trips, config.reduce)
    if config.combine.enabled:
        self._apply_combine(trips, config.combine)
    if config.expand.enabled:
        self._apply_expand(trips, config.expand, config.combine)

    # 4. Build summary
    summary = self._build_summary()

    # 5. Consolidate and format changes
    changes = self._consolidate_changes()
    formatted = self._format_changes(changes, time_format)

    return FilterPreviewResult(...)
```

#### apply()

```python
async def apply(
    self,
    location_id: UUID,
    airline: str,
    config: FilterRequest,
    time_format: str = "24h",
) -> FilterApplyResult:
    # 1. Reset state
    self._reset_state()
    batch_id = uuid4()

    # 2. Get eligible trips
    trips = await self._get_eligible_trips(location_id, airline, ...)

    # 3. Apply filters (same as preview)
    # ...

    # 4. Persist changes to database
    for change in self.changes:
        trip = trip_lookup[change.trip_id]
        if trip.original_pick_up_time is None:
            trip.original_pick_up_time = trip.pick_up_time
        trip.pick_up_time = change.new_time
        trip.filter_applied = change.filter_applied
        trip.filter_batch_id = batch_id
        trip.filtered_at = datetime.utcnow()

    # 5. Create FilterBatch record
    batch = FilterBatch(...)

    # 6. Commit to database
    await self.session.commit()

    return FilterApplyResult(...)
```

#### revert()

```python
async def revert(
    self,
    location_id: UUID,
    airline: str,
    batch_id: Optional[UUID] = None,
) -> FilterRevertResult:
    # 1. Build query
    query = (
        Select(Trip)
        .Where(Trip.location_id == location_id)
        .Where(Trip.airline == airline)
        .Where(Trip.filter_applied != None)
        .Where(Trip.original_pick_up_time != None)
    )

    if batch_id:
        query = query.Where(Trip.filter_batch_id == batch_id)

    # 2. Get trips
    trips = await self.session.exec(query).all()

    # 3. Revert each trip
    for trip in trips:
        trip.pick_up_time = trip.original_pick_up_time
        trip.filter_applied = None
        trip.filter_batch_id = None
        trip.filtered_at = None

    # 4. Update FilterBatch
    # Mark as reverted

    # 5. Commit
    await self.session.commit()

    return FilterRevertResult(...)
```

---

### 10.3 Métodos de Aplicación de Filtros

#### _apply_reduce()

```python
def _apply_reduce(self, trips: list[Trip], config: ReduceFilterConfig):
    for trip in trips:
        # Use original_pick_up_time OR pick_up_time
        original = trip.original_pick_up_time or trip.pick_up_time

        # Subtract minutes
        new_time = self._subtract_minutes(original, config.minutes_to_reduce)

        # Validate
        if new_time < time(0, 0):
            self.exclusions.append(...)
            continue

        # Round
        new_time = self._round_time(new_time)

        # Record change
        self.changes.append(TripChange(...))
```

#### _apply_combine()

```python
def _apply_combine(self, trips: list[Trip], config: CombineFilterConfig):
    # Group by date
    by_date = self._group_by_date(trips)

    for date_trips in by_date.values():
        # Sort by effective time
        sorted_trips = sorted(date_trips, key=lambda t: self._get_effective_time(t))

        i = 0
        while i < len(sorted_trips) - 1:
            trip_a = sorted_trips[i]
            trip_b = sorted_trips[i + 1]

            # Rule A check
            if trip_a.id in self.modified_by_combine_expand:
                i += 1
                continue
            if trip_b.id in self.modified_by_combine_expand:
                i += 1
                continue

            # Calculate gap
            gap = self._calculate_gap(trip_a, trip_b)

            # Check if in range
            if config.min_gap <= gap <= config.max_gap:
                # Calculate midpoint
                midpoint = self._calculate_midpoint(trip_a, trip_b)

                # Round
                midpoint = self._round_time(midpoint)

                # Record changes
                self.changes.append(TripChange(trip_id=trip_a.id, new_time=midpoint, ...))
                self.changes.append(TripChange(trip_id=trip_b.id, new_time=midpoint, ...))

                # Mark as modified (Rule A)
                self.modified_by_combine_expand.add(trip_a.id)
                self.modified_by_combine_expand.add(trip_b.id)

                i += 2  # Skip both trips
            else:
                i += 1
```

#### _apply_expand()

```python
def _apply_expand(
    self,
    trips: list[Trip],
    expand_config: ExpandFilterConfig,
    combine_config: CombineFilterConfig
):
    # Similar structure to combine
    by_date = self._group_by_date(trips)

    for date_trips in by_date.values():
        sorted_trips = sorted(date_trips, key=lambda t: self._get_effective_time(t))

        i = 0
        while i < len(sorted_trips) - 1:
            trip_a = sorted_trips[i]
            trip_b = sorted_trips[i + 1]

            # Rule A check
            if trip_a.id in self.modified_by_combine_expand:
                i += 1
                continue
            if trip_b.id in self.modified_by_combine_expand:
                i += 1
                continue

            gap = self._calculate_gap(trip_a, trip_b)

            # Check if gap < min_gap
            if gap < expand_config.min_gap:
                # Try to expand
                new_gap = expand_config.min_gap
                shift_a = ...
                shift_b = ...

                new_time_a = self._shift_time(trip_a, -shift_a)
                new_time_b = self._shift_time(trip_b, +shift_b)

                # Rule B: No-Collision check
                if self._would_collide_with_combine(new_gap, combine_config):
                    self.exclusions.append(...)
                    i += 1
                    continue

                # Round
                new_time_a = self._round_time(new_time_a)
                new_time_b = self._round_time(new_time_b)

                # Record changes
                self.changes.append(...)
                self.changes.append(...)

                # Mark as modified
                self.modified_by_combine_expand.add(trip_a.id)
                self.modified_by_combine_expand.add(trip_b.id)

                i += 2
            else:
                i += 1
```

---

## 11. Casos de Uso Completos

### 11.1 Caso de Uso 1: Aplicar Reduce Solo

**Escenario:**
Manager quiere reducir 20 minutos a todos los trips outbound.

**Steps:**
```
1. Manager abre Ground Filters drawer
2. Configura:
   - Reduce: enabled, 20 minutes
   - Combine: disabled
   - Expand: disabled
3. Click "Preview Changes"
4. Frontend → POST /filters/preview
5. Backend procesa:
   - Encuentra 500 trips elegibles
   - Aplica reduce a todos
   - 495 modificados, 5 excluidos (tiempo < 00:00)
6. Frontend muestra cambios
7. Manager revisa y click "Apply Changes"
8. Frontend → POST /filters/apply
9. Backend:
   - Verifica si hay filtros aplicados → NO
   - Aplica reduce
   - Persiste cambios
   - Crea batch_id
10. Frontend muestra confirmación
```

---

### 11.2 Caso de Uso 2: Aplicar Reduce, Luego Combine (V3)

**Escenario:**
Manager primero aplica Reduce, luego quiere agregar Combine.

**Steps:**
```
1. Manager aplica Reduce (20 min)
   → Backend: filter_applied = 'reduce'

2. Manager configura Combine (gap 10-20)
3. Click "Preview Changes"
4. Frontend → POST /filters/preview
5. Backend:
   - Encuentra trips con filter_applied = 'reduce'
   - ⚠️ En V2: Devolvería 0 trips
   - ✅ En V3: Encuentra todos (ignora filter_applied en preview)
6. Frontend muestra cambios combinados

7. Manager click "Apply Changes"
8. Frontend → POST /filters/apply
9. Backend V3:
   ⭐ AUTO-REVERT:
   - Detecta filter_applied = 'reduce'
   - Revierte todos a original_pick_up_time
   - Limpia filter_applied
   - Log: "auto_revert: 500 trips"

   - Aplica Reduce + Combine juntos
   - Persiste cambios
   - Nuevo batch_id

10. Frontend muestra:
    - "Previous filters were automatically reverted"
    - Nuevos cambios aplicados
```

---

### 11.3 Caso de Uso 3: Revert Partial

**Escenario:**
Manager aplicó Reduce + Combine, pero quiere quitar solo Reduce.

**Steps:**
```
1. Manager click "Revert Reduce Only"
2. Frontend → POST /filters/revert-partial?batch_id={uuid}&filter_type=reduce
3. Backend:
   - Busca FilterBatch por batch_id
   - Valida que reduce fue aplicado
   - Busca todos los trips del batch
   - Revierte a original_pick_up_time
   - Reconstruye config SIN reduce
   - Re-aplica solo Combine
   - Actualiza FilterBatch
4. Frontend muestra nuevos cambios
```

---

### 11.4 Caso de Uso 4: Cross-Device Preview Sync

**Escenario:**
Manager crea preview en Desktop, lo ve en Mobile.

**Steps:**
```
Device A (Desktop):
1. Manager configura filtros
2. Click "Preview Changes"
3. Backend guarda en filter_previews table
4. Frontend muestra preview

Device B (Mobile):
5. Manager abre mismo location+airline
6. Frontend → GET /filters/preview/last
7. Backend retorna preview guardado de Device A
8. Frontend muestra mismo preview
9. Manager click "Apply Changes" en Mobile
10. Backend aplica y limpia preview
11. Device A refreshea → preview vacío (correcto)
```

---

## 12. Ejemplos Request/Response

### 12.1 Ejemplo Reduce Only

**Request:**
```json
POST /v1/locations/334d0365-070d-470d-b027-c18ec707c057/airlines/WN/trips/filters/preview
{
  "pick_up_date_from": "2026-01-01",
  "pick_up_date_to": "2026-01-31",
  "rounding_mode": "multiple_of_5",
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 20,
    "hotel_names": null,
    "time_range": null
  },
  "combine": {
    "enabled": false
  },
  "expand": {
    "enabled": false
  }
}
```

**Response:**
```json
{
  "location_id": "334d0365-070d-470d-b027-c18ec707c057",
  "airline": "WN",
  "changes": [
    {
      "trip_id": "uuid-1",
      "original_time": "08:00 AM",
      "new_time": "07:40 AM",
      "filter_applied": "reduce",
      "hotel_name": "Marriott Downtown",
      "flight_number": "WN1234",
      "pick_up_date": "2026-01-15",
      "pick_up_location": "Marriott Downtown",
      "drop_off_location": "SDF Airport"
    },
    {
      "trip_id": "uuid-2",
      "original_time": "09:30 AM",
      "new_time": "09:10 AM",
      "filter_applied": "reduce",
      "hotel_name": "Hilton Garden Inn",
      "flight_number": "WN5678",
      "pick_up_date": "2026-01-15",
      "pick_up_location": "Hilton Garden Inn",
      "drop_off_location": "SDF Airport"
    }
  ],
  "exclusions": [
    {
      "trip_id": "uuid-3",
      "reason": "Reduce would result in time < 00:00 (original: 00:10, reduce: 20 min)",
      "filter_type": "reduce",
      "trip_info": {
        "pick_up_time": "00:10 AM",
        "pick_up_location": "Holiday Inn Express",
        "flight_number": "WN9999",
        "pick_up_date": "2026-01-20"
      }
    }
  ],
  "summary": {
    "reduce": 495,
    "combine": 0,
    "expand": 0,
    "excluded": 5
  },
  "total_trips_evaluated": 500,
  "eligible_trips": 500
}
```

---

### 12.2 Ejemplo Combine Only

**Request:**
```json
{
  "reduce": {"enabled": false},
  "combine": {
    "enabled": true,
    "min_gap": 10,
    "max_gap": 20
  },
  "expand": {"enabled": false}
}
```

**Response:**
```json
{
  "changes": [
    {
      "trip_id": "uuid-a",
      "original_time": "08:00 AM",
      "new_time": "08:07 AM",
      "filter_applied": "combine",
      "hotel_name": "Marriott",
      "flight_number": "WN1234"
    },
    {
      "trip_id": "uuid-b",
      "original_time": "08:15 AM",
      "new_time": "08:07 AM",
      "filter_applied": "combine",
      "hotel_name": "Marriott",
      "flight_number": "WN5678"
    }
  ],
  "summary": {
    "reduce": 0,
    "combine": 100,
    "expand": 0,
    "excluded": 0
  }
}
```

---

### 12.3 Ejemplo Apply con Auto-Revert (V3)

**Request:**
```json
POST /v1/locations/{id}/airlines/WN/trips/filters/apply
{
  "reduce": {"enabled": false},
  "combine": {
    "enabled": true,
    "min_gap": 10,
    "max_gap": 20
  },
  "expand": {"enabled": false}
}
```

**Response (cuando había filtros previos):**
```json
{
  "batch_id": "uuid-new",
  "location_id": "uuid",
  "airline": "WN",
  "changes_applied": 100,
  "exclusions": [],
  "log": [
    {
      "action": "auto_revert",
      "message": "Automatically reverted 495 trips with existing filters before applying new filters",
      "batches_reverted": ["uuid-old-batch"]
    },
    {
      "trip_id": "uuid-1",
      "action": "modified",
      "filter": "combine",
      "original_time": "08:00",
      "new_time": "08:07",
      "hotel": "Marriott"
    }
  ],
  "summary": {
    "reduce": 0,
    "combine": 100,
    "expand": 0,
    "excluded": 0
  }
}
```

---

## 13. Frontend Integration

### 13.1 React Query Hooks

```typescript
// hooks/use-filter-preview.ts
export const useFilterPreview = (
  locationId: string,
  airline: string
) => {
  return useMutation({
    mutationFn: async (filters: FilterRequest) => {
      const response = await fetch(
        `/api/v1/locations/${locationId}/airlines/${airline}/trips/filters/preview`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify(filters),
        }
      );

      if (!response.ok) {
        throw new Error('Failed to preview filters');
      }

      return response.json() as Promise<FilterPreviewResult>;
    },
  });
};

// hooks/use-filter-apply.ts
export const useFilterApply = (
  locationId: string,
  airline: string
) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (filters: FilterRequest) => {
      const response = await fetch(
        `/api/v1/locations/${locationId}/airlines/${airline}/trips/filters/apply`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify(filters),
        }
      );

      if (!response.ok) {
        throw new Error('Failed to apply filters');
      }

      return response.json() as Promise<FilterApplyResult>;
    },
    onSuccess: (data) => {
      // Show notification if auto-reverted
      const autoRevertLog = data.log.find(l => l.action === 'auto_revert');
      if (autoRevertLog) {
        toast.info(autoRevertLog.message);
      }

      // Invalidate trips query to refetch
      queryClient.invalidateQueries(['trips', locationId]);
    },
  });
};
```

---

### 13.2 UI Component

```tsx
// components/ground-filters-drawer.tsx
export const GroundFiltersDrawer = () => {
  const { locationId, airline } = useParams();
  const [config, setConfig] = useState<FilterRequest>({
    rounding_mode: 'multiple_of_5',
    reduce: { enabled: false },
    combine: { enabled: false },
    expand: { enabled: false },
  });

  const previewMutation = useFilterPreview(locationId, airline);
  const applyMutation = useFilterApply(locationId, airline);

  const handlePreview = () => {
    previewMutation.mutate(config);
  };

  const handleApply = () => {
    applyMutation.mutate(config);
  };

  return (
    <Drawer>
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle>Ground Filters - {airline}</DrawerTitle>
          <DrawerDescription>
            Optimiza tiempos de pickup para trips OUTBOUND (Hotel → Airport)
          </DrawerDescription>
        </DrawerHeader>

        {/* Eligibility Alert */}
        <FilterEligibilityAlert
          locationId={locationId}
          airline={airline}
        />

        {/* Configuration Forms */}
        <ReduceFilterForm
          config={config.reduce}
          onChange={(reduce) => setConfig({ ...config, reduce })}
        />

        <CombineFilterForm
          config={config.combine}
          onChange={(combine) => setConfig({ ...config, combine })}
        />

        <ExpandFilterForm
          config={config.expand}
          onChange={(expand) => setConfig({ ...config, expand })}
        />

        {/* Preview Results */}
        {previewMutation.data && (
          <PreviewResults data={previewMutation.data} />
        )}

        {/* Actions */}
        <DrawerFooter>
          <Button
            onClick={handlePreview}
            disabled={previewMutation.isPending}
          >
            {previewMutation.isPending ? 'Loading...' : 'Preview Changes'}
          </Button>

          <Button
            onClick={handleApply}
            disabled={!previewMutation.data || applyMutation.isPending}
            variant="default"
          >
            {applyMutation.isPending ? 'Applying...' : 'Apply Changes'}
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
};
```

---

### 13.3 Auto-Revert Notification

```tsx
// components/preview-results.tsx
export const PreviewResults = ({ data }: { data: FilterPreviewResult }) => {
  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Reduce</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{data.summary.reduce}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Combine</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{data.summary.combine}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Expand</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{data.summary.expand}</p>
          </CardContent>
        </Card>
      </div>

      {/* Changes Table */}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Hotel</TableHead>
            <TableHead>Flight</TableHead>
            <TableHead>Original Time</TableHead>
            <TableHead>New Time</TableHead>
            <TableHead>Filter</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.changes.map((change) => (
            <TableRow key={change.trip_id}>
              <TableCell>{change.hotel_name}</TableCell>
              <TableCell>{change.flight_number}</TableCell>
              <TableCell>{change.original_time}</TableCell>
              <TableCell className="font-bold">
                {change.new_time}
              </TableCell>
              <TableCell>
                <Badge variant={getBadgeVariant(change.filter_applied)}>
                  {change.filter_applied}
                </Badge>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {/* Exclusions */}
      {data.exclusions.length > 0 && (
        <Alert variant="warning">
          <AlertTitle>Trips Excluded</AlertTitle>
          <AlertDescription>
            <ul className="list-disc list-inside">
              {data.exclusions.map((excl) => (
                <li key={excl.trip_id}>
                  {excl.trip_info.flight_number}: {excl.reason}
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
};
```

---

## 14. Troubleshooting

### 14.1 Preview Devuelve 0 Trips

**Síntomas:**
- `/trips` devuelve 674 trips
- `/filters/preview` devuelve 0 eligible_trips

**Diagnóstico:**
```bash
GET /filters/eligibility?pick_up_date_from=2026-01-01&pick_up_date_to=2026-01-31
```

**Causas posibles:**

1. **No hay trips OUTBOUND**
```json
{
  "by_trip_type": {
    "inbound": 337,
    "ground": 337,
    "outbound": 0  ← Problema
  }
}
```
**Solución:** Ground Filters solo aplican a trips outbound. Si no hay trips outbound, no hay trips elegibles.

2. **Trips no están SCHEDULED**
```json
{
  "by_status": {
    "completed": 674,
    "scheduled": 0  ← Problema
  }
}
```
**Solución:** Ground Filters solo aplican a trips scheduled. Espera próximos trips o cambia status.

---

### 14.2 Apply Falla con Error 500

**Síntomas:**
- Preview funciona
- Apply devuelve 500 Internal Server Error

**Diagnóstico:**
```bash
docker logs gt360 --tail 50 | grep -i error
```

**Causas posibles:**

1. **Error de permisos en base de datos**
**Solución:** Verificar que el usuario de DB tiene permisos de UPDATE en trips.trips

2. **Constraint violation**
**Solución:** Verificar que no hay conflictos de unique constraints al actualizar

3. **Timeout en transacción**
**Solución:** Reducir cantidad de trips procesados por batch

---

### 14.3 Filters No Se Aplican (V3)

**Síntomas:**
- Apply retorna 200 OK
- Trips NO cambian en base de datos

**Diagnóstico:**
```bash
# Verificar log de apply
{
  "log": [
    {
      "action": "auto_revert",
      "message": "..."
    }
  ]
}

# Verificar trips en DB
SELECT filter_applied, COUNT(*)
FROM trips.trips
WHERE location_id = '{uuid}' AND airline = 'WN'
GROUP BY filter_applied;
```

**Causas posibles:**

1. **Auto-revert está funcionando, pero apply falla silenciosamente**
**Solución:** Verificar que `service.apply()` está commiteando cambios

2. **Trips no cumplen criterios después de auto-revert**
**Solución:** Verificar que trips siguen siendo `trip_type=outbound` y `status=scheduled`

---

### 14.4 CORS Error en Frontend

**Síntomas:**
```
Access to fetch at 'https://api.gt360.app/...' has been blocked by CORS policy
```

**Solución:**
```python
# main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://web.gt360.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 15. Diagramas de Flujo

### 15.1 Flujo Apply V3 con Auto-Revert

```
┌─────────────────────────────────────────────────────────┐
│ POST /filters/apply                                     │
│ {reduce: enabled, combine: enabled}                     │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│ Validar request                                         │
│ - location_id existe?                                   │
│ - airline válido?                                       │
│ - configuración válida?                                 │
└────────────────────┬────────────────────────────────────┘
                     │ ✅ OK
                     ▼
┌─────────────────────────────────────────────────────────┐
│ ⭐ AUTO-REVERT CHECK                                    │
│ Query: SELECT * FROM trips                              │
│ WHERE location_id = {uuid}                              │
│   AND airline = 'WN'                                    │
│   AND trip_type = 'outbound'                            │
│   AND status = 'scheduled'                              │
│   AND filter_applied != NULL                            │
└────────────────────┬────────────────────────────────────┘
                     │
                     ├─ ❌ No trips con filtros
                     │  → Skip auto-revert
                     │
                     └─ ✅ Trips con filtros encontrados
                        ▼
           ┌─────────────────────────────────┐
           │ AUTO-REVERT                     │
           │ Para cada trip:                 │
           │ - pick_up_time = original       │
           │ - filter_applied = NULL         │
           │ - filter_batch_id = NULL        │
           │ - filtered_at = NULL            │
           │ Commit changes                  │
           │ Log: "auto_revert"              │
           └─────────────┬───────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ Get eligible trips                                      │
│ (ahora todos tienen filter_applied = NULL)             │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│ Apply filters in order                                  │
│ 1. REDUCE (Priority 0)                                  │
│ 2. COMBINE (Priority 1)                                 │
│ 3. EXPAND (Priority 1)                                  │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│ Persist changes                                         │
│ - Update pick_up_time                                   │
│ - Set filter_applied                                    │
│ - Set filter_batch_id (NEW)                             │
│ - Set filtered_at                                       │
│ - Create FilterBatch record                             │
│ Commit                                                  │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│ Clear saved preview                                     │
│ DELETE FROM filter_previews                             │
│ WHERE location_id = {uuid} AND airline = 'WN'          │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│ Return FilterApplyResult                                │
│ {                                                       │
│   batch_id: "uuid-new",                                 │
│   changes_applied: 150,                                 │
│   log: [                                                │
│     {action: "auto_revert", message: "..."},            │
│     ...                                                 │
│   ]                                                     │
│ }                                                       │
└─────────────────────────────────────────────────────────┘
```

---

### 15.2 Flujo de Filtros (Reduce → Combine → Expand)

```
START
  │
  ▼
┌─────────────────────────────────────┐
│ Get eligible trips                  │
│ (outbound + scheduled)              │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│ REDUCE (Priority 0)                 │
│ For each trip:                      │
│   original = original_pick_up_time  │
│   new = original - minutes          │
│   new = round(new)                  │
│   record change                     │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│ COMBINE (Priority 1)                │
│ Group trips by date                 │
│ For each date:                      │
│   Sort by effective_time            │
│   For each pair (A, B):             │
│     if gap in [min_gap, max_gap]:   │
│       if NOT modified (Rule A):     │
│         midpoint = (A + B) / 2      │
│         move both to midpoint       │
│         mark as modified            │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│ EXPAND (Priority 1)                 │
│ Group trips by date                 │
│ For each date:                      │
│   Sort by effective_time            │
│   For each pair (A, B):             │
│     if gap < min_gap:               │
│       if NOT modified (Rule A):     │
│         try to expand to min_gap    │
│         check Rule B (no-collision) │
│         if OK:                      │
│           move A earlier            │
│           move B later              │
│           mark as modified          │
└────────────┬────────────────────────┘
             │
             ▼
           END
```

---

## 16. Resumen de Cambios V2 → V3

| Aspecto | V2 | V3 (2026-01-20) |
|---------|----|----|
| **Preview con filtros previos** | ❌ Falla (0 eligible trips) | ✅ Funciona (ignora filter_applied) |
| **Apply con filtros previos** | ❌ Falla (0 eligible trips) | ✅ Auto-revierte y aplica |
| **Filtros secuenciales** | ❌ Requiere revert manual | ✅ Auto-revert transparente |
| **UX** | ❌ Confuso para usuario | ✅ Intuitivo y flexible |
| **API breaking changes** | N/A | ❌ Ninguno (compatible) |
| **Log** | Sin info de revert | ✅ Incluye "auto_revert" |
| **Performance** | N/A | ✅ Igual (una query extra en apply) |

**Archivos modificados en V3:**
- `trips_router.py:1441-1494` - Auto-revert logic en /apply
- `trip_filter_service.py:525` - Removido filtro filter_applied en _get_eligible_trips()

---

## 17. Checklist de Testing

### 17.1 Testing Backend

- [ ] Preview devuelve cambios correctos para Reduce
- [ ] Preview devuelve cambios correctos para Combine
- [ ] Preview devuelve cambios correctos para Expand
- [ ] Preview devuelve cambios correctos para Reduce + Combine + Expand
- [ ] Apply persiste cambios correctamente
- [ ] Apply con filtros previos auto-revierte (V3)
- [ ] Revert restaura tiempos originales
- [ ] Revert Partial funciona correctamente
- [ ] Eligibility endpoint devuelve información correcta
- [ ] Preview sync cross-device funciona
- [ ] Apply limpia preview guardado

### 17.2 Testing Frontend

- [ ] Drawer se abre correctamente
- [ ] Configuración de filtros funciona
- [ ] Preview muestra cambios correctamente
- [ ] Exclusions se muestran con razón
- [ ] Apply aplica cambios y muestra confirmación
- [ ] Auto-revert notifica al usuario (V3)
- [ ] Revert restaura trips
- [ ] Eligibility alert se muestra cuando 0 trips elegibles
- [ ] Cross-device sync funciona
- [ ] Time format (12h/24h) se respeta

### 17.3 Testing E2E

- [ ] Flujo completo: Preview → Apply → Revert
- [ ] Flujo secuencial: Apply Reduce → Apply Combine (V3)
- [ ] Flujo cross-device: Preview en Desktop → Apply en Mobile
- [ ] Flujo con exclusiones: Trips excluidos se muestran correctamente
- [ ] Flujo con auto-revert: Notificación se muestra

---

## 18. Archivos Relevantes

### 18.1 Backend

| Archivo | Descripción |
|---------|-------------|
| `features/trips/routes/trips_router.py` | Endpoints API (Preview, Apply, Revert, etc.) |
| `features/trips/services/trip_filter_service.py` | Lógica de negocio de filtros |
| `features/trips/models/filter_models.py` | Modelos Pydantic (Request/Response) |
| `shared/db/schemas/trips/trips.py` | Schema de Trip |
| `shared/db/schemas/trips/filter_batches.py` | Schema de FilterBatch |
| `shared/db/schemas/trips/filter_previews.py` | Schema de FilterPreview |

### 18.2 Documentación

| Archivo | Descripción |
|---------|-------------|
| `docs/GROUND_FILTERS_COMPLETE_V3.md` | **Este archivo** - Documentación completa V3 |
| `docs/GROUND_FILTERS_COMPLETE_WORKFLOW.md` | V1 (legacy) |
| `docs/GROUND_FILTERS_COMPLETE_WORKFLOW_V2.md` | V2 (legacy) |
| `docs/FILTER_PREVIEW_QUERY_ANALYSIS.md` | Análisis de queries |
| `docs/GROUND_FILTERS_ELIGIBILITY_ENDPOINT.md` | Endpoint de elegibilidad |
| `docs/PREVIEW_PERSISTENCE_IMPLEMENTATION.md` | Cross-device sync |

---

## 19. Próximos Pasos / Roadmap

### 19.1 Mejoras Futuras

- [ ] Soporte para trips tipo `ground` (Hotel → Hotel)
- [ ] Filtros por crew/driver asignado
- [ ] Validación de capacidad de vehículos en Combine
- [ ] Optimización de rutas (no solo tiempos)
- [ ] Machine Learning para sugerir configuraciones óptimas
- [ ] A/B testing de configuraciones
- [ ] Analytics dashboard de efectividad de filtros

### 19.2 Performance Optimizations

- [ ] Cachear trips elegibles
- [ ] Procesamiento en background para grandes volúmenes
- [ ] Batch updates optimizados
- [ ] Indexes adicionales en base de datos

---

**Última actualización:** 2026-01-20
**Versión:** 3.0
**Status:** ✅ Implementado y Deployed
**Auto-Revert:** ✅ Activado
