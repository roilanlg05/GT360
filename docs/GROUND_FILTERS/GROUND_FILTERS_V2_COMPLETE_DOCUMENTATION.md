# Ground Filters V2 - Documentacion Completa

**Fecha de Actualizacion:** 2026-01-25
**Version:** 2.0 (Unica version activa)

---

## Tabla de Contenidos

1. [Resumen Ejecutivo](#resumen-ejecutivo)
2. [Arquitectura del Sistema](#arquitectura-del-sistema)
3. [Esquema de Base de Datos](#esquema-de-base-de-datos)
4. [Tipos de Filtro](#tipos-de-filtro)
5. [Ventanas de Tiempo](#ventanas-de-tiempo)
6. [Reglas del Sistema](#reglas-del-sistema)
7. [API Endpoints - Step Filters (Per-Day)](#api-endpoints---step-filters-per-day)
8. [API Endpoints - Bulk Filters (Multi-Day)](#api-endpoints---bulk-filters-multi-day)
9. [API Endpoints - Filter Presets](#api-endpoints---filter-presets)
10. [Modelos de Datos](#modelos-de-datos)
11. [Notificaciones WebSocket](#notificaciones-websocket)
12. [Ejemplos de Uso](#ejemplos-de-uso)
13. [Flujo de Trabajo Recomendado](#flujo-de-trabajo-recomendado)

---

## Resumen Ejecutivo

Ground Filters V2 es un sistema de optimizacion de horarios de pickup para trips de transporte terrestre. Permite a los managers ajustar automaticamente los horarios de recogida mediante tres tipos de filtros:

| Filtro | Funcion | Caso de Uso |
|--------|---------|-------------|
| **Reduce** | Resta minutos fijos al pickup time | Anticipar recogidas para margen de seguridad |
| **Combine** | Unifica pares de trips al punto medio | Reducir numero de viajes separados |
| **Expand** | Separa pares de trips | Evitar congestion en mismo horario |

### Caracteristicas Principales

- **Stack-Based**: Los filtros se aplican como pasos en una pila (stack), permitiendo revertir en orden
- **Order-Free**: Se pueden aplicar reduce, combine, expand en cualquier secuencia
- **Per-Day o Bulk**: Soporta operaciones por dia individual o multiples dias (rango/futuro)
- **Time Windows**: Cada step puede tener multiples ventanas de tiempo con configuracion independiente
- **Minute Precision**: Sin redondeo a multiplos de 5, precision exacta al minuto
- **Anti-Drift**: El `original_pick_up_time` es inmutable para garantizar reversion correcta

---

## Arquitectura del Sistema

```
                              Frontend
                                  |
                                  v
+------------------------------------------------------------------+
|                         FastAPI Routers                           |
|  +------------------------+    +-------------------------------+  |
|  | step_filter_router     |    | filter_preset_router          |  |
|  | - 6 endpoints per-day  |    | - 5 endpoints                 |  |
|  | - 3 endpoints bulk     |    |                               |  |
|  +------------------------+    +-------------------------------+  |
+------------------------------------------------------------------+
                                  |
                                  v
+------------------------------------------------------------------+
|                          Services                                 |
|  +------------------------+    +-------------------------------+  |
|  | StepFilterService      |    | FilterPresetService           |  |
|  | - preview/apply step   |    | - CRUD presets                |  |
|  | - preview/apply bulk   |    | - auto-apply on import        |  |
|  | - revert              |    |                               |  |
|  +------------------------+    +-------------------------------+  |
+------------------------------------------------------------------+
                                  |
                                  v
+------------------------------------------------------------------+
|                    PostgreSQL (Schema: trips)                     |
|  +----------------+  +----------------+  +---------------------+  |
|  | filter_steps   |  | filter_presets |  | trips (columnas)    |  |
|  | - id           |  | - id           |  | - original_pick_up_ |  |
|  | - location_id  |  | - location_id  |  |   time              |  |
|  | - airline      |  | - airline      |  | - current_step_id   |  |
|  | - pick_up_date |  | - stack_       |  | - reduce_applied    |  |
|  | - step_order   |  |   template     |  | - combine_applied   |  |
|  | - filter_type  |  |                |  | - expand_applied    |  |
|  | - windows      |  |                |  | - filtered_at       |  |
|  +----------------+  +----------------+  +---------------------+  |
+------------------------------------------------------------------+
                                  |
                                  v
+------------------------------------------------------------------+
|                    Redis (Notifications)                          |
|                    Channel: loc:{location_id}                     |
+------------------------------------------------------------------+
```

### Archivos del Sistema

```
features/trips/
├── routes/
│   ├── step_filter_router.py      # Endpoints V2 (per-day + bulk)
│   └── filter_preset_router.py    # Endpoints de presets
├── services/
│   ├── step_filter_service.py     # Logica de filtros V2
│   └── filter_preset_service.py   # Logica de presets/auto-apply
└── models/
    └── filter_models.py           # Pydantic models

shared/db/schemas/trips/
├── filter_steps.py                # Tabla filter_steps
├── filter_presets.py              # Tabla filter_presets
└── trips.py                       # Columnas de filtro en trips
```

---

## Esquema de Base de Datos

### Tabla: `trips.filter_steps`

Almacena cada paso de filtro aplicado en el stack.

| Columna | Tipo | Descripcion |
|---------|------|-------------|
| `id` | UUID | PK, auto-generado |
| `location_id` | UUID | FK a locations, CASCADE on delete |
| `airline` | VARCHAR(10) | Codigo de aerolinea (ej: "WN", "AA") |
| `pick_up_date` | DATE | Fecha objetivo del filtro |
| `step_order` | INT | Orden en el stack (1, 2, 3...) |
| `filter_type` | VARCHAR(20) | "reduce", "combine", "expand" |
| `config` | JSONB | Metadata del filtro |
| `windows` | JSONB | Array de ventanas de tiempo |
| `trips_affected` | INT | Numero de trips modificados |
| `created_at` | TIMESTAMPTZ | Fecha de creacion |
| `is_active` | BOOL | False si fue revertido |

**Unique Constraint:** `(location_id, airline, pick_up_date, step_order)`

### Tabla: `trips.filter_presets`

Templates de filtros para auto-aplicar en importaciones.

| Columna | Tipo | Descripcion |
|---------|------|-------------|
| `id` | UUID | PK, auto-generado |
| `location_id` | UUID | FK a locations, CASCADE on delete |
| `airline` | VARCHAR(10) | Codigo de aerolinea |
| `stack_template` | JSONB | Array de templates de steps |
| `created_at` | TIMESTAMPTZ | Fecha de creacion |
| `updated_at` | TIMESTAMPTZ | Ultima actualizacion |
| `created_by` | UUID | FK a users (nullable) |

### Columnas en `trips.trips` para Filtros

| Columna | Tipo | Descripcion |
|---------|------|-------------|
| `original_pick_up_time` | TIME | Hora original (inmutable, para revert) |
| `current_step_id` | UUID | FK al ultimo step que modifico el trip |
| `reduce_applied` | BOOL | True si Reduce fue aplicado |
| `combine_applied` | BOOL | True si Combine fue aplicado |
| `expand_applied` | BOOL | True si Expand fue aplicado |
| `filtered_at` | TIMESTAMPTZ | Cuando se aplico el ultimo filtro |

---

## Tipos de Filtro

### Comportamiento de Acumulacion (Stack)

Los filtros se **acumulan** en orden de aplicacion. Cada filtro trabaja sobre el `pick_up_time` **actual** (ya modificado por filtros anteriores), no sobre el original.

```
Ejemplo: Reduce -> Combine

Trip A: original = 08:30, Trip B: original = 08:40

PASO 1: Apply Reduce (minutes_to_reduce = 10)
  Trip A: 08:30 -> 08:20
  Trip B: 08:40 -> 08:30

PASO 2: Apply Combine (min_gap=5, max_gap=15)
  Usa tiempos YA REDUCIDOS:
  Trip A: 08:20 \
                 > Midpoint = 08:25
  Trip B: 08:30 /

RESULTADO FINAL:
  Trip A: 08:25 (Reduce + Combine aplicados)
  Trip B: 08:25 (Reduce + Combine aplicados)
```

**Nota:** El `original_pick_up_time` permanece inmutable para permitir reversion completa.

### Combinaciones Validas

| Combo | Descripcion |
|-------|-------------|
| Reduce -> Combine | Reduce primero, Combine trabaja sobre tiempos reducidos |
| Combine -> Reduce | Combine primero, Reduce trabaja sobre tiempos combinados |
| Reduce -> Expand | Reduce primero, Expand trabaja sobre tiempos reducidos |
| Expand -> Reduce | Expand primero, Reduce trabaja sobre tiempos expandidos |

**Importante:** Combine y Expand **no se combinan entre si** (Rule A impide doble modificacion).

---

### 1. Reduce

**Proposito:** Restar minutos fijos al pickup time.

**Base Time:** Usa `original_pick_up_time` (inmutable) para evitar drift al re-aplicar.

**Parametros por Ventana:**
- `minutes_to_reduce`: 1-120 minutos

**Ejemplo:**
```
Antes: Trip A pickup 08:30
Config: minutes_to_reduce = 15
Despues: Trip A pickup 08:15
```

### 2. Combine

**Proposito:** Unificar pares de trips cercanos al punto medio.

**Base Time:** Usa `pick_up_time` actual (ya modificado por filtros anteriores).

**Requisitos:**
- Mismo `pick_up_location` (hotel)
- Mismo `drop_off_location` (aeropuerto)
- Gap entre trips en rango `[min_gap, max_gap]`

**Parametros por Ventana:**
- `min_gap`: 1-60 minutos
- `max_gap`: 1-120 minutos

**Ejemplo (sin Reduce previo):**
```
Antes:
  Trip A: 08:00, Marriott -> LAX
  Trip B: 08:10, Marriott -> LAX
Config: min_gap=5, max_gap=15
Despues:
  Trip A: 08:05, Marriott -> LAX
  Trip B: 08:05, Marriott -> LAX
```

**Ejemplo (con Reduce previo):**
```
Despues de Reduce (-10 min):
  Trip A: 07:50, Marriott -> LAX
  Trip B: 08:00, Marriott -> LAX
Config: min_gap=5, max_gap=15
Despues de Combine:
  Trip A: 07:55, Marriott -> LAX (midpoint de 07:50 y 08:00)
  Trip B: 07:55, Marriott -> LAX
```

### 3. Expand

**Proposito:** Separar pares de trips para evitar congestion.

**Base Time:** Usa `pick_up_time` actual (ya modificado por filtros anteriores).

**Estrategia Smart con 3 Intentos:**
1. **Both**: A retrocede, B avanza
2. **Only A**: Solo A retrocede
3. **Only B**: Solo B avanza

**Parametros por Ventana:**
- `min_gap`: 1-60 minutos
- `max_gap`: 1-120 minutos
- `max_shift`: 1-20 minutos

---

## Ventanas de Tiempo

Cada step puede tener multiples ventanas de tiempo con configuracion independiente.

### Modelo TimeWindow

```python
class TimeWindow(BaseModel):
    start: str = "00:00"       # Formato HH:MM
    end: str = "24:00"         # Formato HH:MM (24:00 = fin del dia)
    enabled: bool = True       # Si esta activa

    # Config especifica (segun tipo de filtro)
    minutes_to_reduce: int | None = None   # Para Reduce (1-120)
    min_gap: int | None = None             # Para Combine/Expand (1-60)
    max_gap: int | None = None             # Para Combine/Expand (1-120)
    max_shift: int | None = None           # Solo para Expand (1-20)
    hotel_names: list[str] | None = None   # Filtrar por hoteles especificos
```

### Reglas de Ventanas

1. **No Overlap:** Las ventanas no pueden superponerse
2. **No Midnight Crossing:** `start` debe ser menor que `end`
3. **Al menos una activa:** Debe haber minimo una ventana con `enabled=true`
4. **Default:** Si no se especifican ventanas, se usa `00:00-24:00`

---

## Reglas del Sistema

### Rule A: No Doble Modificacion en Combine/Expand

Un trip modificado por Combine o Expand **no puede ser modificado nuevamente** en el mismo step.

### Rule B: No-Collision (Expand vs Combine Activo)

Al aplicar Expand, el nuevo gap resultante **no debe caer dentro del rango de un Combine activo**.

### Anti-Drift: Original Time Inmutable

`original_pick_up_time` se guarda la primera vez que se modifica un trip y **nunca se sobrescribe**.

### No Wrap-Around

V2 **no permite** que los tiempos crucen la medianoche.

---

## API Endpoints - Step Filters (Per-Day)

Base URL: `/v2/locations/{location_id}/airlines/{airline}/filters/`

### 1. Preview Step (Per-Day)

**POST** `/step/preview`

Simula un filtro para UN dia sin aplicar cambios.

**Request Body:**
```json
{
  "filter_type": "reduce",
  "pick_up_date": "2026-01-25",
  "windows": [
    {
      "start": "05:00",
      "end": "12:00",
      "enabled": true,
      "minutes_to_reduce": 15
    }
  ]
}
```

**Response (StepResult):**
```json
{
  "step_id": null,
  "filter_type": "reduce",
  "pick_up_date": "2026-01-25",
  "trips_modified": 25,
  "changes": [...],
  "exclusions": [],
  "summary": {"modified": 25, "excluded": 0}
}
```

### 2. Apply Step (Per-Day)

**POST** `/step/apply`

Aplica un filtro a UN dia y lo guarda en el stack.

**Request/Response:** Igual que Preview, pero `step_id` no es null.

### 3. Get Stack

**GET** `/stack?pick_up_date=2026-01-25`

Obtiene el estado actual del stack para un dia.

**Response (StackState):**
```json
{
  "location_id": "uuid",
  "airline": "WN",
  "pick_up_date": "2026-01-25",
  "steps": [
    {
      "step_id": "uuid",
      "step_order": 1,
      "filter_type": "reduce",
      "windows_count": 2,
      "windows": [...],
      "trips_affected": 25,
      "created_at": "2026-01-24T10:30:00Z",
      "is_active": true,
      "config": {}
    }
  ],
  "total_trips_affected": 25
}
```

### 4. Revert Last Step

**POST** `/revert-last?pick_up_date=2026-01-25`

Revierte el ultimo step activo (pop del stack).

### 5. Revert Specific Step

**POST** `/step/{step_id}/revert`

Revierte un step especifico por ID.

### 6. Get Eligibility (Per-Day)

**GET** `/eligibility?pick_up_date=2026-01-25`

Verifica cuantos trips son elegibles para filtrado en UN dia.

---

## API Endpoints - Bulk Filters (Multi-Day)

Base URL: `/v2/locations/{location_id}/airlines/{airline}/filters/bulk/`

### 1. Preview Bulk

**POST** `/bulk/preview`

Simula un filtro para MULTIPLES dias o todos los trips futuros.

**Request Body (BulkFilterConfig):**
```json
{
  "filter_type": "reduce",
  "date_from": "2026-01-25",
  "date_to": null,
  "windows": [
    {
      "start": "00:00",
      "end": "24:00",
      "enabled": true,
      "minutes_to_reduce": 15
    }
  ],
  "skip_days_with_stack": true
}
```

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `filter_type` | string | "reduce", "combine", "expand" |
| `date_from` | string | Fecha inicio (YYYY-MM-DD) |
| `date_to` | string? | Fecha fin (null = todos los futuros) |
| `windows` | array | Configuracion de ventanas |
| `skip_days_with_stack` | bool | Si omitir dias con filtros existentes |

**Response (BulkStepResult):**
```json
{
  "filter_type": "reduce",
  "date_from": "2026-01-25",
  "date_to": null,
  "total_days": 15,
  "days_processed": 12,
  "days_skipped": 3,
  "total_trips_modified": 450,
  "total_exclusions": 5,
  "by_date": [
    {
      "pick_up_date": "2026-01-25",
      "trips_modified": 30,
      "exclusions_count": 0,
      "step_id": null,
      "skipped": false,
      "skip_reason": null
    },
    {
      "pick_up_date": "2026-01-26",
      "trips_modified": 0,
      "exclusions_count": 0,
      "step_id": null,
      "skipped": true,
      "skip_reason": "Day already has active filter stack"
    }
  ],
  "all_changes": [...],
  "all_exclusions": [...]
}
```

### 2. Apply Bulk

**POST** `/bulk/apply`

Aplica un filtro a MULTIPLES dias, creando un step por dia.

**Request:** Igual que Preview Bulk

**Response:** Igual que Preview Bulk, pero `step_id` en cada `DayResult` contiene el UUID del step creado.

### 3. Get Bulk Eligibility

**GET** `/bulk/eligibility?date_from=2026-01-25&date_to=2026-02-28`

Verifica cuantos trips son elegibles en un rango de fechas.

**Query Parameters:**
- `date_from`: Fecha inicio (requerido)
- `date_to`: Fecha fin (opcional, null = todos los futuros)

**Response (BulkEligibilityResult):**
```json
{
  "location_id": "uuid",
  "airline": "WN",
  "date_from": "2026-01-25",
  "date_to": "2026-02-28",
  "total_days": 35,
  "total_trips": 1050,
  "total_eligible": 1050,
  "by_date": [
    {
      "pick_up_date": "2026-01-25",
      "eligible_trips": 30,
      "already_filtered": 0,
      "by_hotel": {"Marriott": 15, "Hilton": 15}
    }
  ]
}
```

### 4. Revert Bulk

**POST** `/bulk/revert`

Revierte filtros de un tipo específico (o todos) a través de múltiples días.

**Request (BulkRevertConfig):**
```json
{
  "date_from": "2026-01-25",
  "date_to": "2026-02-28",
  "filter_type": "reduce"
}
```

**Parámetros:**
- `date_from`: Fecha inicio (requerido, formato YYYY-MM-DD)
- `date_to`: Fecha fin (opcional, null = todos los días futuros)
- `filter_type`: Tipo de filtro a revertir (opcional, null = todos los tipos)

**Response (BulkRevertResult):**
```json
{
  "date_from": "2026-01-25",
  "date_to": "2026-02-28",
  "filter_type": "reduce",
  "total_days": 2,
  "days_with_reverts": 2,
  "days_skipped": 0,
  "total_steps_reverted": 2,
  "total_trips_recalculated": 31,
  "by_date": [
    {
      "pick_up_date": "2026-01-26",
      "steps_reverted": 1,
      "step_ids": ["uuid-del-step-revertido"],
      "trips_recalculated": 16,
      "skipped": false,
      "skip_reason": null
    },
    {
      "pick_up_date": "2026-01-30",
      "steps_reverted": 1,
      "step_ids": ["uuid-del-step-revertido"],
      "trips_recalculated": 15,
      "skipped": false,
      "skip_reason": null
    }
  ]
}
```

**Casos de Uso:**
1. **Revertir un tipo de filtro en todo el futuro:**
   ```json
   {"date_from": "2026-01-25", "date_to": null, "filter_type": "reduce"}
   ```

2. **Revertir TODOS los filtros en un rango:**
   ```json
   {"date_from": "2026-01-25", "date_to": "2026-02-28", "filter_type": null}
   ```

3. **Flujo: Modificar ventana de tiempo:**
   - Revert bulk del filter_type
   - Re-apply bulk con nueva configuración de windows

---

## API Endpoints - Filter Presets

Base URL: `/v2/locations/{location_id}/airlines/{airline}/filters/`

### 1. Create/Update Preset

**POST** `/preset`

### 2. Get Preset

**GET** `/preset`

### 3. Update Preset

**PUT** `/preset`

### 4. Delete Preset

**DELETE** `/preset`

### 5. Test Preset

**POST** `/preset/test?pick_up_date=2026-01-25`

---

## Modelos de Datos

### FilterStepConfig (Per-Day Request)

```python
class FilterStepConfig(BaseModel):
    filter_type: str           # "reduce" | "combine" | "expand"
    pick_up_date: str          # "YYYY-MM-DD"
    windows: list[TimeWindow]  # Default: [TimeWindow()] = dia completo
```

### BulkFilterConfig (Multi-Day Request)

```python
class BulkFilterConfig(BaseModel):
    filter_type: str                    # "reduce" | "combine" | "expand"
    date_from: str                      # "YYYY-MM-DD"
    date_to: str | None = None          # "YYYY-MM-DD" o null = todos los futuros
    windows: list[TimeWindow]
    skip_days_with_stack: bool = True   # Omitir dias con filtros existentes
```

### StepResult (Per-Day Response)

```python
class StepResult(BaseModel):
    step_id: UUID | None       # None para preview
    filter_type: str
    pick_up_date: str
    trips_modified: int
    changes: list[TripChange]
    exclusions: list[FilterExclusion]
    summary: dict
```

### BulkStepResult (Multi-Day Response)

```python
class BulkStepResult(BaseModel):
    filter_type: str
    date_from: str
    date_to: str | None

    # Summary
    total_days: int
    days_processed: int
    days_skipped: int
    total_trips_modified: int
    total_exclusions: int

    # Per-day details
    by_date: list[DayResult]

    # All changes (can be large)
    all_changes: list[TripChange]
    all_exclusions: list[FilterExclusion]
```

### DayResult

```python
class DayResult(BaseModel):
    pick_up_date: str
    trips_modified: int
    exclusions_count: int
    step_id: UUID | None       # None para preview, UUID para apply
    skipped: bool = False
    skip_reason: str | None = None
```

### BulkRevertConfig (Bulk Revert Request)

```python
class BulkRevertConfig(BaseModel):
    date_from: str                      # "YYYY-MM-DD" (requerido)
    date_to: str | None = None          # "YYYY-MM-DD" o null = todos los futuros
    filter_type: str | None = None      # "reduce" | "combine" | "expand" o null = todos
```

### BulkRevertResult (Bulk Revert Response)

```python
class BulkRevertResult(BaseModel):
    date_from: str
    date_to: str | None
    filter_type: str | None

    # Summary
    total_days: int
    days_with_reverts: int
    days_skipped: int
    total_steps_reverted: int
    total_trips_recalculated: int

    # Per-day details
    by_date: list[DayRevertResult]
```

### DayRevertResult

```python
class DayRevertResult(BaseModel):
    pick_up_date: str
    steps_reverted: int
    step_ids: list[UUID]
    trips_recalculated: int
    skipped: bool = False
    skip_reason: str | None = None
```

---

## Notificaciones WebSocket

Cuando se aplica o revierte un step, se envia una notificacion via Redis PubSub.

### Canal

```
loc:{location_id}
```

### Evento: Step Applied

```json
{
  "type": "step_applied",
  "location_id": "uuid",
  "airline": "WN",
  "step_id": "uuid",
  "filter_type": "reduce",
  "trips_affected": 25,
  "timestamp": "2026-01-24T10:30:00Z",
  "message": "Filter step applied: reduce (25 trips)"
}
```

### Evento: Step Reverted

```json
{
  "type": "step_reverted",
  "location_id": "uuid",
  "airline": "WN",
  "step_id": "uuid",
  "filter_type": "reduce",
  "timestamp": "2026-01-24T11:00:00Z",
  "message": "Filter step reverted: reduce"
}
```

**Nota:** En operaciones bulk, se envia UNA notificacion por cada dia procesado.

---

## Sistema de WebSocket Completo

### Arquitectura General del WebSocket

El sistema de WebSocket para ground filters permite actualizaciones en tiempo real de:
1. **Trips** (creación, actualización, eliminación)
2. **Filter steps** (aplicación y reversión de filtros)
3. **Estado de la conexión** (validación de token mediante ping/pong)

```
Frontend WebSocket Client
        |
        | ws://api/ws/trips?location_id={loc}&token={jwt}
        v
+----------------------------------------------------------+
|  FastAPI WebSocket Endpoint (/ws/trips)                 |
|  - Autenticación con JWT                                 |
|  - Validación de permisos por location                   |
+----------------------------------------------------------+
        |
        v
+----------------------------------------------------------+
|  WSManager (features/trips/utils/ws_manager.py)          |
|  - Gestiona rooms por location_id                        |
|  - Mantiene listeners Redis por location                 |
|  - Enruta eventos a clientes conectados                  |
+----------------------------------------------------------+
        |
        v
+----------------------------------------------------------+
|  Redis PubSub                                            |
|  - Canal: loc:{location_id}                              |
|  - Escucha eventos de trips y filtros                    |
+----------------------------------------------------------+
        ^
        |
+----------------------------------------------------------+
|  Publicadores de Eventos                                 |
|  - trip_webhooks.py (batch imports)                      |
|  - step_filter_service.py (apply/revert filters)         |
+----------------------------------------------------------+
```

### Archivos del Sistema WebSocket

```
features/trips/
├── websockets/
│   └── trip_websockets.py        # Endpoint WebSocket principal
├── utils/
│   └── ws_manager.py              # Gestor de conexiones y rooms
└── webhooks/
    └── trip_webhooks.py           # Webhook para batch imports

features/trips/services/
└── step_filter_service.py         # Publica eventos de filtros

shared/redis/
├── redis_client.py                # Cliente Redis singleton
└── redis_safe.py                  # Wrapper para calls seguros a Redis
```

---

### UN SOLO WebSocket para Todo

**IMPORTANTE:** El sistema usa **UN SOLO WebSocket** (`/ws/trips`) que maneja:

| Tipo de Evento | Fuente | Cuándo se Envía |
|----------------|--------|-----------------|
| `snapshot` | WebSocket al conectar | Al abrir conexión inicial |
| `trips_batch` | trip_webhooks.py | Solo en importaciones externas vía webhook |
| `step_applied` | step_filter_service.py | Al aplicar filtros (POST /step/apply) |
| `step_reverted` | step_filter_service.py | Al revertir filtros (POST /revert-last) |
| `location_deleted` | location_service.py | Al eliminar location |

**Nota Crítica:**
- `trips_batch` solo se envía en **importaciones** (webhook externo)
- Al aplicar/revertir filtros, **NO** se envía `trips_batch`
- El frontend debe hacer **refetch manual** de trips después de recibir eventos de filtros

---

### Conexión al WebSocket

#### Endpoint

```
/ws/trips
```

**URL Completa según entorno:**
- Producción: `wss://api.gt360.com/ws/trips` (seguro, recomendado)
- Desarrollo local: `ws://localhost:8000/ws/trips`

**Nota:** Usar `wss://` (WebSocket Secure) en producción para encriptación TLS.

#### Query Parameters

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `location_id` | UUID | ID de la location a monitorear (requerido) |
| `token` | string | JWT de autenticación (requerido) |

#### Flujo de Conexión

```
1. Cliente abre WebSocket con location_id y token
2. Backend valida token (decode_token)
3. Backend verifica permisos user_can_access_location
4. Si OK, acepta conexión y registra en room
5. Backend crea listener Redis para loc:{location_id}
6. Backend envía snapshot inicial de todos los trips
```

#### Ejemplo de Conexión (JavaScript)

```javascript
// 1. Obtener token JWT de autenticación
const token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...";
const locationId = "123e4567-e89b-12d3-a456-426614174000";

// 2. Conectar WebSocket
// Usar wss:// en producción, ws:// solo en desarrollo
const apiUrl = process.env.NODE_ENV === 'production'
  ? 'wss://api.gt360.com'
  : 'ws://localhost:8000';

const ws = new WebSocket(
  `${apiUrl}/ws/trips?location_id=${locationId}&token=${token}`
);

// 3. Handlers
ws.onopen = () => {
  console.log("WebSocket conectado");
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  handleWebSocketMessage(message);
};

ws.onerror = (error) => {
  console.error("WebSocket error:", error);
};

ws.onclose = (event) => {
  console.log("WebSocket cerrado:", event.code, event.reason);
  // Implementar reconexión automática
  setTimeout(reconnect, 3000);
};
```

---

### Tipos de Mensajes

El WebSocket maneja varios tipos de mensajes bidireccionales:

#### 1. Snapshot (Backend → Frontend)

**Descripción:** Enviado al conectar, contiene todos los trips actuales de la location.

**Estructura:**

```json
{
  "type": "snapshot",
  "location_id": "123e4567-e89b-12d3-a456-426614174000",
  "location_info": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "name": "SDF",
    "timezone": "America/New_York"
  },
  "trips": [
    {
      "id": "trip-uuid-1",
      "location_id": "123e4567-e89b-12d3-a456-426614174000",
      "airline": "WN",
      "flight_number": "1234",
      "pick_up_date": "2026-01-25",
      "pick_up_time": "08:30:00",
      "original_pick_up_time": null,
      "pick_up_location": "Marriott Downtown",
      "drop_off_location": "Airport Terminal 1",
      "trip_type": "outbound",
      "status": "scheduled",
      "reduce_applied": false,
      "combine_applied": false,
      "expand_applied": false,
      "current_step_id": null,
      "filtered_at": null
    }
  ]
}
```

**Campos Clave:**

- `location_info`: Metadata de la location (timezone para ordenar trips en Timeline)
- `trips`: Array de todos los trips activos (obtenidos de Redis o PostgreSQL)

**Cuándo se envía:**
- Inmediatamente después de establecer la conexión WebSocket
- Incluye TODOS los trips de la location
- Si Redis está vacío, se obtiene de PostgreSQL (fallback automático)

---

#### 2. Trips Batch (Backend → Frontend)

**Descripción:** Batch de eventos de trips (insert/update/delete) publicado por webhooks.

**Estructura:**

```json
{
  "type": "trips_batch",
  "location_id": "123e4567-e89b-12d3-a456-426614174000",
  "events": [
    {
      "location_id": "123e4567-e89b-12d3-a456-426614174000",
      "trip_id": "trip-uuid-1",
      "event_type": "insert",
      "trip": {
        "id": "trip-uuid-1",
        "airline": "WN",
        "flight_number": "5678",
        "pick_up_date": "2026-01-26",
        "pick_up_time": "09:15:00",
        "original_pick_up_time": null,
        "pick_up_location": "Hilton Garden Inn",
        "drop_off_location": "Airport Terminal 2",
        "trip_type": "outbound",
        "status": "scheduled"
      }
    },
    {
      "location_id": "123e4567-e89b-12d3-a456-426614174000",
      "trip_id": "trip-uuid-2",
      "event_type": "update",
      "trip": {
        "id": "trip-uuid-2",
        "pick_up_time": "08:15:00",
        "original_pick_up_time": "08:30:00",
        "reduce_applied": true,
        "filtered_at": "2026-01-25T14:30:00Z"
      }
    },
    {
      "location_id": "123e4567-e89b-12d3-a456-426614174000",
      "trip_id": "trip-uuid-3",
      "event_type": "delete",
      "trip": {
        "id": "trip-uuid-3",
        "airline": "AA",
        "flight_number": "9999"
      }
    }
  ]
}
```

**Tipos de Eventos (event_type):**

| event_type | Descripción | Acción Frontend |
|------------|-------------|-----------------|
| `insert` | Nuevo trip creado | Agregar a lista de trips |
| `update` | Trip modificado (ej: filtro aplicado) | Actualizar trip existente |
| `delete` | Trip eliminado | Remover de lista |
| `db_update` | Actualización genérica de DB | Actualizar trip existente |

**Cuándo se envía:**
- ✅ Cuando el sistema de importación procesa trips vía webhook (trip_webhooks.py)
- ❌ **NO se envía** cuando se aplica o revierte un filtro
- Formato batch para reducir overhead de mensajes

**IMPORTANTE:** Al aplicar/revertir filtros, el backend solo envía `step_applied`/`step_reverted`.
El frontend debe hacer refetch manual de trips para actualizar la UI.

**Procesamiento Frontend:**

```javascript
function handleWebSocketMessage(message) {
  switch (message.type) {
    case "snapshot":
      // Reemplazar trips completos
      setTrips(message.trips);
      setLocationInfo(message.location_info);
      break;

    case "trips_batch":
      // Procesar cada evento del batch
      message.events.forEach(event => {
        switch (event.event_type) {
          case "insert":
            addTrip(event.trip);
            break;
          case "update":
          case "db_update":
            updateTrip(event.trip_id, event.trip);
            break;
          case "delete":
            removeTrip(event.trip_id);
            break;
        }
      });
      break;

    // ... otros tipos
  }
}
```

---

#### 3. Step Applied (Backend → Frontend)

**Descripción:** Notificación de que un filtro fue aplicado exitosamente.

**Estructura:**

```json
{
  "type": "step_applied",
  "location_id": "123e4567-e89b-12d3-a456-426614174000",
  "airline": "WN",
  "step_id": "step-uuid-1",
  "filter_type": "reduce",
  "trips_affected": 25,
  "timestamp": "2026-01-25T14:30:00Z",
  "message": "Filter step applied: reduce (25 trips)"
}
```

**Campos:**

| Campo | Descripción |
|-------|-------------|
| `step_id` | UUID del step creado en filter_steps |
| `filter_type` | "reduce", "combine", "expand" |
| `trips_affected` | Número de trips modificados |
| `timestamp` | ISO 8601 timestamp (UTC) |
| `message` | Mensaje descriptivo para UI |

**Cuándo se envía:**
- Después de `POST /step/apply` exitoso
- En bulk operations, UNA notificación por cada día procesado
- Después de aplicar preset automático en import

**Acción Frontend Recomendada:**
```javascript
case "step_applied":
  // 1. Mostrar toast/notification
  showNotification(`Filtro ${message.filter_type} aplicado a ${message.trips_affected} trips`);

  // 2. Actualizar stack state para el día
  await fetchStackState(message.airline, pickUpDate);

  // 3. IMPORTANTE: Refetch trips manualmente
  // El backend NO envía trips_batch automáticamente al aplicar filtros
  await queryClient.invalidateQueries(['trips', locationId, airline, pickUpDate]);
  break;
```

---

#### 4. Step Reverted (Backend → Frontend)

**Descripción:** Notificación de que un filtro fue revertido.

**Estructura:**

```json
{
  "type": "step_reverted",
  "location_id": "123e4567-e89b-12d3-a456-426614174000",
  "airline": "WN",
  "step_id": "step-uuid-1",
  "filter_type": "reduce",
  "timestamp": "2026-01-25T15:00:00Z",
  "message": "Filter step reverted: reduce"
}
```

**Cuándo se envía:**
- Después de `POST /revert-last` exitoso
- Después de `POST /step/{step_id}/revert` exitoso
- En bulk revert, UNA notificación por cada step revertido

**Acción Frontend Recomendada:**
```javascript
case "step_reverted":
  // 1. Mostrar notification
  showNotification(`Filtro ${message.filter_type} revertido`);

  // 2. Actualizar stack state
  await fetchStackState(message.airline, pickUpDate);

  // 3. IMPORTANTE: Refetch trips manualmente para ver tiempos originales
  // El backend NO envía trips_batch automáticamente al revertir filtros
  await queryClient.invalidateQueries(['trips', locationId, airline, pickUpDate]);
  break;
```

---

#### 5. Ping/Pong (Frontend ↔ Backend)

**Descripción:** Mecanismo de keep-alive y validación de token activo.

**Ping (Frontend → Backend):**

```json
{
  "action": "ping",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Pong (Backend → Frontend):**

```json
{
  "type": "pong"
}
```

**Error de Token Inválido/Expirado:**

```json
{
  "type": "error",
  "code": 401,
  "detail": "Invalid or expired token"
}
```

**Implementación Recomendada:**

```javascript
// Enviar ping cada 30 segundos
const pingInterval = setInterval(() => {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      action: "ping",
      token: currentToken
    }));
  }
}, 30000);

// Manejar respuesta
function handleWebSocketMessage(message) {
  switch (message.type) {
    case "pong":
      console.log("Connection alive");
      break;

    case "error":
      if (message.code === 401) {
        console.error("Token expired, reconnecting...");
        ws.close();
        refreshTokenAndReconnect();
      }
      break;
  }
}
```

---

#### 6. Subscribe/Unsubscribe (Frontend → Backend)

**Descripción:** Acciones opcionales del cliente (la conexión ya está suscrita automáticamente).

**Subscribe (Frontend → Backend):**

```json
{
  "action": "subscribe"
}
```

**Respuesta:**

```json
{
  "type": "subscribed",
  "location_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

**Unsubscribe (Frontend → Backend):**

```json
{
  "action": "unsubscribe"
}
```

**Respuesta:**

```json
{
  "type": "unsubscribed",
  "location_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

**Nota:** En la implementación actual, la conexión WebSocket ya está suscrita automáticamente al conectar. Estos comandos son opcionales y pueden usarse para logging o UI feedback.

---

### Estrategia de Caché (Redis + PostgreSQL)

El sistema implementa una estrategia híbrida de caché:

#### Snapshot Flow

```
┌─────────────────────────────────────────────────┐
│  send_snapshot(location_id)                      │
└─────────────────────────────────────────────────┘
                    |
                    v
┌─────────────────────────────────────────────────┐
│  Get location_info from PostgreSQL               │
│  - timezone, airport code                        │
└─────────────────────────────────────────────────┘
                    |
                    v
┌─────────────────────────────────────────────────┐
│  Try Redis: SMEMBERS loc:{location_id}:trips     │
└─────────────────────────────────────────────────┘
                    |
        ┌───────────┴───────────┐
        |                       |
    Redis HIT              Redis MISS
        |                       |
        v                       v
┌──────────────┐       ┌──────────────┐
│ MGET trips   │       │ Query DB     │
│ from Redis   │       │ (PostgreSQL) │
└──────────────┘       └──────────────┘
        |                       |
        |                       v
        |              ┌──────────────┐
        |              │ Re-populate  │
        |              │ Redis cache  │
        |              └──────────────┘
        |                       |
        └───────────┬───────────┘
                    v
        ┌─────────────────────┐
        │ Send snapshot to WS  │
        └─────────────────────┘
```

#### TTL de Caché

```python
TRIP_TTL_SECONDS = 300  # 5 minutos
```

- Redis keys: `trip:{trip_id}` → JSON del trip
- Redis sets: `loc:{location_id}:trips` → Set de trip_ids
- Ambos expiran en 5 minutos si no se actualizan
- Auto-refresh al recibir webhooks o al aplicar filtros

#### Self-Healing Cache

Si Redis está vacío pero PostgreSQL tiene datos, el sistema:
1. Lee trips de PostgreSQL
2. Repopula Redis automáticamente
3. Continúa funcionando normalmente

---

### Manejo de Errores y Códigos de Cierre

#### Códigos de Cierre WebSocket

| Código | Razón | Descripción |
|--------|-------|-------------|
| 1000 | Normal closure | Cierre normal por cliente |
| 1008 | Policy violation | Token inválido o sin permisos |
| 1011 | Internal error | Error inesperado en servidor |

#### Errores de Autenticación

```python
# Token inválido en conexión inicial
await ws.close(code=1008)  # Policy violation

# Token expirado en ping
await ws.send_json({
  "type": "error",
  "code": 401,
  "detail": "Invalid or expired token"
})
await ws.close(code=1008)
```

#### Errores de Permisos

```python
# Usuario sin acceso a location
if not await user_can_access_location(session, org_id, location_id):
    await ws.close(code=1008)
    return
```

---

### Ejemplo Completo de Implementación Frontend

```javascript
class GroundFiltersWebSocket {
  constructor(locationId, token) {
    this.locationId = locationId;
    this.token = token;
    this.ws = null;
    this.reconnectDelay = 3000;
    this.maxReconnectDelay = 30000;
    this.pingInterval = null;
    this.isIntentionallyClosed = false;
  }

  connect() {
    // Construir URL según entorno
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname === 'localhost'
      ? 'localhost:8000'
      : 'api.gt360.com';
    const url = `${protocol}//${host}/ws/trips?location_id=${this.locationId}&token=${this.token}`;

    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      console.log('[WebSocket] Connected');
      this.reconnectDelay = 3000; // Reset delay
      this.startPing();
    };

    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      this.handleMessage(message);
    };

    this.ws.onerror = (error) => {
      console.error('[WebSocket] Error:', error);
    };

    this.ws.onclose = (event) => {
      console.log('[WebSocket] Closed:', event.code, event.reason);
      this.stopPing();

      if (!this.isIntentionallyClosed) {
        this.reconnect();
      }
    };
  }

  handleMessage(message) {
    console.log('[WebSocket] Message:', message.type);

    switch (message.type) {
      case 'snapshot':
        this.onSnapshot(message.trips, message.location_info);
        break;

      case 'trips_batch':
        this.onTripsBatch(message.events);
        break;

      case 'step_applied':
        this.onStepApplied(message);
        break;

      case 'step_reverted':
        this.onStepReverted(message);
        break;

      case 'pong':
        console.log('[WebSocket] Pong received');
        break;

      case 'error':
        this.onError(message);
        break;

      default:
        console.warn('[WebSocket] Unknown message type:', message.type);
    }
  }

  onSnapshot(trips, locationInfo) {
    console.log(`[WebSocket] Snapshot: ${trips.length} trips`);
    // Actualizar estado global de trips
    store.dispatch(setTrips(trips));
    store.dispatch(setLocationInfo(locationInfo));
  }

  onTripsBatch(events) {
    console.log(`[WebSocket] Batch: ${events.length} events`);

    events.forEach(event => {
      switch (event.event_type) {
        case 'insert':
          store.dispatch(addTrip(event.trip));
          break;
        case 'update':
        case 'db_update':
          store.dispatch(updateTrip({
            id: event.trip_id,
            changes: event.trip
          }));
          break;
        case 'delete':
          store.dispatch(removeTrip(event.trip_id));
          break;
      }
    });
  }

  onStepApplied(message) {
    console.log(`[WebSocket] Filter applied: ${message.filter_type}`);

    // Mostrar notificación
    showToast({
      type: 'success',
      message: `Filtro ${message.filter_type} aplicado a ${message.trips_affected} trips`
    });

    // Actualizar stack state
    store.dispatch(fetchStackState({
      locationId: this.locationId,
      airline: message.airline,
      pickUpDate: getCurrentPickUpDate()
    }));
  }

  onStepReverted(message) {
    console.log(`[WebSocket] Filter reverted: ${message.filter_type}`);

    showToast({
      type: 'info',
      message: `Filtro ${message.filter_type} revertido`
    });

    store.dispatch(fetchStackState({
      locationId: this.locationId,
      airline: message.airline,
      pickUpDate: getCurrentPickUpDate()
    }));
  }

  onError(message) {
    console.error('[WebSocket] Error:', message);

    if (message.code === 401) {
      // Token expirado, refrescar y reconectar
      this.disconnect();
      refreshToken().then(newToken => {
        this.token = newToken;
        this.connect();
      });
    }
  }

  startPing() {
    this.pingInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({
          action: 'ping',
          token: this.token
        }));
      }
    }, 30000); // Cada 30 segundos
  }

  stopPing() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  reconnect() {
    console.log(`[WebSocket] Reconnecting in ${this.reconnectDelay}ms...`);

    setTimeout(() => {
      this.connect();
    }, this.reconnectDelay);

    // Exponential backoff
    this.reconnectDelay = Math.min(
      this.reconnectDelay * 2,
      this.maxReconnectDelay
    );
  }

  disconnect() {
    this.isIntentionallyClosed = true;
    this.stopPing();
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
    }
  }
}

// Uso
const wsClient = new GroundFiltersWebSocket(locationId, token);
wsClient.connect();

// Cleanup al desmontar componente
onUnmount(() => {
  wsClient.disconnect();
});
```

---

### Flujo Completo de Eventos (Apply Filter)

```
┌──────────────────────────────────────────────────────────────┐
│  1. Frontend: POST /step/apply (o /bulk/apply)                │
└──────────────────────────────────────────────────────────────┘
                          |
                          v
┌──────────────────────────────────────────────────────────────┐
│  2. Backend: StepFilterService.apply_step()                   │
│     - Modifica trips en PostgreSQL                            │
│     - Crea FilterStep record                                  │
│     - Actualiza original_pick_up_time, filter flags           │
└──────────────────────────────────────────────────────────────┘
                          |
                          v
┌──────────────────────────────────────────────────────────────┐
│  3. Backend: Publish Redis (loc:{location_id})                │
│     - Evento: "step_applied" notification                     │
│     - NO publica trips_batch (refetch manual necesario)       │
└──────────────────────────────────────────────────────────────┘
                          |
                          v
┌──────────────────────────────────────────────────────────────┐
│  4. WSManager: _location_listener() recibe evento             │
│     - Decode JSON del pubsub                                  │
│     - Reenvía a todos los clientes WebSocket en la room       │
└──────────────────────────────────────────────────────────────┘
                          |
                          v
┌──────────────────────────────────────────────────────────────┐
│  5. Frontend: Recibe vía WebSocket                            │
│     - {"type":"step_applied", "filter_type":"reduce", ...}    │
└──────────────────────────────────────────────────────────────┘
                          |
                          v
┌──────────────────────────────────────────────────────────────┐
│  6. Frontend: Handle step_applied                             │
│     - Reload stack: GET /stack                                │
│     - Refetch trips: GET /trips (manual)                      │
│     - Actualizar savedState → isDirty = false                 │
│     - Mostrar notificación                                    │
└──────────────────────────────────────────────────────────────┘
```

**NOTA IMPORTANTE:** El backend NO publica `trips_batch` cuando se aplican o revierten filtros.
El frontend DEBE hacer refetch manual de trips vía `GET /trips` o `invalidateQueries`
para actualizar la columna Ground con los tiempos modificados.

---

### Optimización: Batch vs Individual Events

El sistema envía eventos en **batch** para reducir overhead:

```python
# WSManager.SEND_WS_BATCH = True (por defecto)

# UN solo mensaje WebSocket con múltiples eventos:
{
  "type": "trips_batch",
  "location_id": "123...",
  "events": [
    {"event_type": "update", "trip_id": "...", "trip": {...}},
    {"event_type": "update", "trip_id": "...", "trip": {...}},
    {"event_type": "update", "trip_id": "...", "trip": {...}}
    // ... 25 trips modificados en un solo mensaje
  ]
}
```

**Ventaja:**
- Menos mensajes WebSocket (1 en vez de 25)
- Menos overhead de parsing JSON
- Mejor performance en filtros bulk

**Alternativa (SEND_WS_BATCH = False):**
```python
# Múltiples mensajes individuales (deshabilitado por defecto)
{"type": "trip_event", "event_type": "update", "trip_id": "...", ...}
{"type": "trip_event", "event_type": "update", "trip_id": "...", ...}
// ... 25 mensajes separados
```

---

### Gestión de Rooms y Cleanup

#### Rooms por Location

```python
# WSManager mantiene:
rooms: Dict[str, Set[WebSocket]] = {}
# Ejemplo:
# {
#   "loc-uuid-1": {ws1, ws2, ws3},  # 3 clientes viendo misma location
#   "loc-uuid-2": {ws4}              # 1 cliente en otra location
# }
```

#### Listener Redis por Room

```python
location_listener_tasks: Dict[str, asyncio.Task] = {}
# Ejemplo:
# {
#   "loc-uuid-1": <asyncio.Task running _location_listener>,
#   "loc-uuid-2": <asyncio.Task running _location_listener>
# }
```

#### Auto-Cleanup

```
┌───────────────────────────────────────┐
│  Cliente WebSocket se desconecta      │
└───────────────────────────────────────┘
              |
              v
┌───────────────────────────────────────┐
│  WSManager.disconnect(ws)              │
│  - Remueve ws de room                  │
│  - Si room queda vacía:                │
│    * Remueve room del dict             │
│    * Cancela listener Redis task       │
└───────────────────────────────────────┘
```

**Beneficio:**
- No hay listeners Redis huérfanos
- Recursos liberados automáticamente
- Escalable a miles de locations

---

### Seguridad y Validación

#### 1. Autenticación en Conexión

```python
# Validar JWT
try:
    claims = decode_token(token)
except Exception:
    await ws.close(code=1008)  # Policy violation
    return
```

#### 2. Autorización por Location

```python
# Verificar que user tenga acceso a location
org_id = metadata.get("organization_id")
if not await user_can_access_location(session, org_id, location_id):
    await ws.close(code=1008)
    return
```

#### 3. Validación en Ping/Pong

```python
# Re-validar token en cada ping
if action == "ping":
    ping_token = msg.get("token")
    try:
        decode_token(ping_token)
        await ws.send_json({"type": "pong"})
    except Exception:
        await ws.send_json({
            "type": "error",
            "code": 401,
            "detail": "Invalid or expired token"
        })
        await ws.close(code=1008)
```

**Beneficio:**
- Detecta tokens expirados antes de 1 hora
- Permite al frontend refrescar token proactivamente

---

### Troubleshooting y Debugging

#### Logs del Backend

```python
# features/trips/websockets/trip_websockets.py
logger.info(f"[SNAPSHOT] Redis has data, using cache...")
logger.info(f"[SNAPSHOT] Redis empty, falling back to PostgreSQL...")

# features/trips/services/step_filter_service.py
logger.info(f"[STEP_FILTER] Applied step {step_id}: {len(changes)} trips modified")
logger.info(f"[STEP_FILTER] Notification sent: step={step_id}, filter={filter_type}")
```

#### Monitorear Redis PubSub

```bash
# Escuchar todos los eventos de una location
redis-cli
> SUBSCRIBE loc:123e4567-e89b-12d3-a456-426614174000

# Ver todas las subscriptions activas
> PUBSUB CHANNELS loc:*
```

#### Verificar Caché Redis

```bash
# Ver trips en caché
redis-cli
> SMEMBERS loc:123e4567-e89b-12d3-a456-426614174000:trips
> GET trip:trip-uuid-1

# Ver TTL
> TTL loc:123e4567-e89b-12d3-a456-426614174000:trips
> TTL trip:trip-uuid-1
```

#### Logs del Frontend

```javascript
// Habilitar logs detallados
const DEBUG = true;

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  if (DEBUG) {
    console.log('[WebSocket]', message.type, message);
  }
  handleMessage(message);
};
```

---

### Best Practices

#### 1. Reconexión Automática con Exponential Backoff

```javascript
reconnectDelay = 3000;     // Inicio: 3 segundos
maxReconnectDelay = 30000; // Máximo: 30 segundos

reconnect() {
  setTimeout(() => {
    this.connect();
  }, this.reconnectDelay);

  this.reconnectDelay = Math.min(
    this.reconnectDelay * 2,
    this.maxReconnectDelay
  );
}
```

#### 2. Mantener Token Actualizado

```javascript
// Refrescar token ANTES de que expire
const tokenExpiresIn = 3600000; // 1 hora
const refreshBefore = 300000;   // 5 minutos antes

setTimeout(async () => {
  const newToken = await refreshToken();
  this.token = newToken;
  // El próximo ping usará el nuevo token
}, tokenExpiresIn - refreshBefore);
```

#### 3. Cleanup en Unmount

```javascript
// React
useEffect(() => {
  const ws = new GroundFiltersWebSocket(locationId, token);
  ws.connect();

  return () => {
    ws.disconnect();
  };
}, [locationId, token]);
```

#### 4. Deduplicación de Eventos

```javascript
// Evitar procesar el mismo evento dos veces
const processedEventIds = new Set();

onTripsBatch(events) {
  events.forEach(event => {
    if (event.event_id && processedEventIds.has(event.event_id)) {
      return; // Skip duplicado
    }

    if (event.event_id) {
      processedEventIds.add(event.event_id);
    }

    // Procesar evento...
  });
}
```

---

## Ejemplos de Uso

### Ejemplo 1: Preview Bulk - Todos los Trips Futuros

```bash
curl -X POST "http://api/v2/locations/{loc}/airlines/WN/filters/bulk/preview" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "filter_type": "reduce",
    "date_from": "2026-01-25",
    "date_to": null,
    "windows": [
      {
        "start": "00:00",
        "end": "24:00",
        "enabled": true,
        "minutes_to_reduce": 15
      }
    ],
    "skip_days_with_stack": true
  }'
```

### Ejemplo 2: Apply Bulk - Rango de Fechas

```bash
curl -X POST "http://api/v2/locations/{loc}/airlines/WN/filters/bulk/apply" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "filter_type": "combine",
    "date_from": "2026-01-25",
    "date_to": "2026-02-28",
    "windows": [
      {
        "start": "05:00",
        "end": "12:00",
        "enabled": true,
        "min_gap": 5,
        "max_gap": 15
      }
    ],
    "skip_days_with_stack": false
  }'
```

### Ejemplo 3: Apply Single Day

```bash
curl -X POST "http://api/v2/locations/{loc}/airlines/WN/filters/step/apply" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "filter_type": "reduce",
    "pick_up_date": "2026-01-25",
    "windows": [
      {
        "start": "00:00",
        "end": "24:00",
        "enabled": true,
        "minutes_to_reduce": 15
      }
    ]
  }'
```

### Ejemplo 4: Check Bulk Eligibility

```bash
curl "http://api/v2/locations/{loc}/airlines/WN/filters/bulk/eligibility?date_from=2026-01-25" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Flujo de Trabajo Recomendado

### Para Preview/Apply Masivo (Todos los Futuros)

```
1. GET /bulk/eligibility?date_from=2026-01-25
   -> Ver cuantos trips en cuantos dias

2. POST /bulk/preview
   {
     "filter_type": "reduce",
     "date_from": "2026-01-25",
     "date_to": null,
     "windows": [...],
     "skip_days_with_stack": true
   }
   -> Ver cambios propuestos por dia

3. Si OK, POST /bulk/apply
   -> Aplica a todos los dias
   -> Retorna step_id por cada dia
```

### Para Operacion Diaria (Un Dia)

```
1. GET /eligibility?pick_up_date=2026-01-25

2. POST /step/preview
   -> Revisar changes y exclusions

3. POST /step/apply

4. GET /stack?pick_up_date=2026-01-25

5. Si necesario: POST /revert-last?pick_up_date=2026-01-25
```

### Orden Recomendado de Filtros

1. **Reduce** primero (ajusta tiempos base)
2. **Combine** segundo (agrupa trips cercanos)
3. **Expand** ultimo (separa si hay congestion)

---

## Resumen de Endpoints

### Step Filters (Per-Day)

| Operacion | Endpoint | Metodo |
|-----------|----------|--------|
| Preview day | `/step/preview` | POST |
| Apply day | `/step/apply` | POST |
| Get stack | `/stack?pick_up_date=X` | GET |
| Revert last | `/revert-last?pick_up_date=X` | POST |
| Revert specific | `/step/{step_id}/revert` | POST |
| Eligibility day | `/eligibility?pick_up_date=X` | GET |

### Bulk Filters (Multi-Day)

| Operacion | Endpoint | Metodo |
|-----------|----------|--------|
| Preview bulk | `/bulk/preview` | POST |
| Apply bulk | `/bulk/apply` | POST |
| Eligibility bulk | `/bulk/eligibility?date_from=X&date_to=Y` | GET |

### Filter Presets

| Operacion | Endpoint | Metodo |
|-----------|----------|--------|
| Create/Update | `/preset` | POST |
| Get | `/preset` | GET |
| Update | `/preset` | PUT |
| Delete | `/preset` | DELETE |
| Test | `/preset/test?pick_up_date=X` | POST |

---

## Errores Comunes

| Error | Causa | Solucion |
|-------|-------|----------|
| `"Windows overlap"` | Ventanas se superponen | Ajustar rangos de tiempo |
| `"Window crosses midnight"` | start >= end | Corregir orden de tiempos |
| `"At least one window must be enabled"` | Todas deshabilitadas | Habilitar al menos una |
| `"No active steps found"` | Intentar revert sin steps | Verificar stack antes |
| `"No eligible trips"` | Sin trips outbound/scheduled | Verificar datos de trips |

---

**Ultima actualizacion:** 2026-01-26 (Sistema WebSocket documentado + BUG fix aplicado en ws_manager.py)
