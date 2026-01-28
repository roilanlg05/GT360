# Ground Filters V2 - Documentacion Completa

**Fecha de Actualizacion:** 2026-01-26
**Version:** 2.0 (Unica version activa)
**Última actualización:** WebSocket fix + Guía completa de Revert + Auto-aplicación documentada

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
10. [Auto-Aplicación de Filtros a Nuevos Trips](#auto-aplicación-de-filtros-a-nuevos-trips)
11. [Guía Completa de Revert para Frontend](#guía-completa-de-revert-para-frontend)
12. [Modelos de Datos](#modelos-de-datos)
13. [Sistema de WebSocket Completo](#sistema-de-websocket-completo)
14. [Ejemplos de Uso](#ejemplos-de-uso)
15. [Flujo de Trabajo Recomendado](#flujo-de-trabajo-recomendado)

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

Revierte el ultimo step activo (pop del stack) de un día específico.

**Query Parameters:**
- `pick_up_date`: Fecha del día (YYYY-MM-DD, requerido)

**Proceso del Backend (3 Pasos):**

```
PASO 1: Marca el último FilterStep como is_active=false
  → SELECT * FROM filter_steps
    WHERE is_active=true
    ORDER BY step_order DESC LIMIT 1
  → UPDATE filter_steps SET is_active=false WHERE id=step_id

PASO 2: Resetea TODOS los trips del día a original_pick_up_time
  → trip.pick_up_time = trip.original_pick_up_time
  → trip.reduce_applied = false
  → trip.combine_applied = false
  → trip.expand_applied = false
  → trip.current_step_id = null

PASO 3: Re-aplica steps restantes activos (si existen)
  → Si quedaron steps activos en el stack (step_order < revertido)
  → Los re-aplica en orden
  → Si NO quedan steps activos
  → Limpia original_pick_up_time = null
```

**Request (sin body):**

```bash
POST /v2/locations/{loc}/airlines/WN/filters/revert-last?pick_up_date=2026-01-25
```

**Response (StepRevertResult):**

```json
{
  "step_id": "uuid-del-step-revertido",
  "filter_type": "reduce",
  "trips_recalculated": 25,
  "remaining_steps": 0,
  "stack_state": {
    "location_id": "uuid",
    "airline": "WN",
    "pick_up_date": "2026-01-25",
    "steps": [],
    "total_trips_affected": 0
  }
}
```

**Campos Clave:**

| Campo | Descripción |
|-------|-------------|
| `step_id` | UUID del step que fue revertido |
| `filter_type` | Tipo de filtro revertido ("reduce", "combine", "expand") |
| `trips_recalculated` | Número de trips que fueron recalculados |
| `remaining_steps` | Cuántos steps siguen activos después del revert |
| `stack_state` | Estado actualizado del stack después del revert |

**IMPORTANTE para el Frontend:**

```javascript
// Después de revert exitoso:
const response = await POST('/revert-last?pick_up_date=2026-01-25');

// Backend YA hizo:
// ✅ Marcó step como is_active=false
// ✅ Reseteo trips a tiempos originales
// ✅ Re-aplicó steps restantes (si los hay)
// ✅ Publicó evento WebSocket step_reverted

// Frontend DEBE:
// 1. Actualizar estado local con stack_state del response
// 2. Refetch trips (para ver tiempos originales)
// 3. Limpiar savedState (porque stack cambió)
// 4. Escuchar evento WebSocket para multi-tab sync
```

**Errores Posibles:**

```json
// Si no hay steps activos para ese día
{
  "detail": "No active steps found for location=..., airline=WN, date=2026-01-25"
}
```

### 5. Revert Specific Step

**POST** `/step/{step_id}/revert`

Revierte un step específico por su ID (permite revertir steps del medio del stack).

**Path Parameters:**
- `step_id`: UUID del step a revertir (requerido)

**Proceso del Backend:**

```
MISMO proceso que revert-last (3 pasos):
1. Marca step como is_active=false
2. Resetea todos los trips del día a original
3. Re-aplica steps restantes activos en orden
```

**Diferencia con revert-last:**
- `revert-last`: Revierte el step con mayor `step_order` (último aplicado)
- `revert-step`: Revierte un step específico por ID (puede ser cualquiera)

**Request (sin body):**

```bash
POST /v2/locations/{loc}/airlines/WN/filters/step/abc-123-uuid/revert
```

**Response:** Igual que `revert-last` (StepRevertResult)

**Caso de Uso:**

```
Stack actual:
  Step 1 (order=1): Reduce -10min
  Step 2 (order=2): Combine 5-15min
  Step 3 (order=3): Expand 10min

Revertir Step 2 (Combine):
  → Marca Step 2 como is_active=false
  → Resetea trips a original
  → Re-aplica Step 1 (Reduce) ✅
  → Re-aplica Step 3 (Expand) ✅

Resultado:
  Step 1: Reduce (activo)
  Step 3: Expand (activo)
```

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
  "total_days": 29,
  "days_with_reverts": 29,
  "days_skipped": 0,
  "total_steps_reverted": 29,
  "total_trips_recalculated": 900,
  "by_date": [
    {
      "pick_up_date": "2026-01-26",
      "steps_reverted": 1,
      "step_ids": ["uuid-del-step-revertido"],
      "trips_recalculated": 31,
      "skipped": false,
      "skip_reason": null
    },
    {
      "pick_up_date": "2026-01-30",
      "steps_reverted": 1,
      "step_ids": ["uuid-del-step-revertido"],
      "trips_recalculated": 29,
      "skipped": false,
      "skip_reason": null
    }
    // ... otros 27 días
  ]
}
```

**Campos Clave para el Frontend:**

| Campo | Ejemplo | Descripción | Usar en Toast |
|-------|---------|-------------|---------------|
| `total_steps_reverted` | 29 | Número de FilterSteps (días) revertidos | ⚠️ Secundario |
| `total_trips_recalculated` | 900 | **Número de trips recalculados** | ✅ **PRINCIPAL** |
| `days_with_reverts` | 29 | Días procesados exitosamente | ✅ Útil para contexto |
| `filter_type` | "reduce" | Tipo de filtro revertido | ✅ Útil para mensaje |

**Toast Recomendado:**

```javascript
// ✅ CORRECTO - Prioriza trips, incluye contexto
toast.success(
  `Filtro ${response.filter_type} revertido: ` +
  `${response.total_trips_recalculated.toLocaleString()} trips ` +
  `en ${response.days_with_reverts} días`
);
// → "Filtro reduce revertido: 900 trips en 29 días" ✅

// ❌ INCORRECTO - Solo muestra steps
toast.success(`Reverted ${response.total_steps_reverted} steps`);
// → "Reverted 29 steps" ❌ (confuso para el usuario)
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
- Producción: `wss://api.gt360.app/ws/trips` (seguro, recomendado)
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
  ? 'wss://api.gt360.app'
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
      : 'api.gt360.app';
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

## Auto-Aplicación de Filtros a Nuevos Trips

El sistema de Ground Filters V2 incluye funcionalidad de **auto-aplicación automática** de filtros a trips recién importados mediante el sistema de **Filter Presets**.

### Concepto

Cuando se configura un **Preset** para una `location + airline`, el backend automáticamente aplicará esos filtros a **nuevos días** cuando se importen trips, sin intervención manual del usuario.

```
Preset = "Stack Template"
  ↓
Se guarda en filter_presets (tabla PostgreSQL)
  ↓
Al importar trips nuevos → Backend detecta nuevo día
  ↓
Si hay preset configurado → Clona template y aplica filtros
  ↓
Trips YA vienen filtrados automáticamente
```

---

### Cómo Funciona

#### Paso 1: Configurar Preset (Una Vez)

El manager configura un "template de stack" para una location+airline:

```bash
POST /v2/locations/{location_id}/airlines/WN/filters/preset
{
  "stack_template": [
    {
      "filter_type": "reduce",
      "windows": [
        {
          "start": "00:00",
          "end": "24:00",
          "enabled": true,
          "minutes_to_reduce": 10
        }
      ]
    },
    {
      "filter_type": "combine",
      "windows": [
        {
          "start": "04:00",
          "end": "10:00",
          "enabled": true,
          "min_gap": 5,
          "max_gap": 15
        }
      ]
    }
  ]
}
```

**Resultado:**
- Se guarda en `trips.filter_presets`
- Persiste para siempre (hasta que se elimine o actualice)
- Aplica a TODOS los días futuros que se importen

#### Paso 2: Importar Trips

Cuando el usuario importa trips (botón "Update" o cualquier ingesta):

```javascript
// Frontend hace import
const result = await importTrips(excelFile);

// Backend (automático):
// 1. Inserta trips en DB
// 2. Detecta fechas únicas importadas
// 3. Filtra SOLO fechas nuevas (que no existían antes)
// 4. Para cada fecha nueva:
//    - Busca si hay preset para location+airline
//    - Si existe: Clona stack_template y aplica filtros
//    - Si no existe: No hace nada
```

**Ubicación en el código:** `features/trips/routes/trips_router.py:316-367`

```python
# Después de insertar trips exitosamente
if trips_to_create and airline:
    from features.trips.services.filter_preset_service import FilterPresetService

    # Get unique dates from imported trips
    unique_dates_imported = {t.pick_up_date for t in trips_to_create}

    # CRITICAL: Filter to ONLY new dates (not pre-existing)
    new_dates = [
        d for d in unique_dates_imported
        if not await day_has_trips_in_db(location.id, airline, d)
    ]

    # Auto-apply preset ONLY to new dates
    preset_service = FilterPresetService(session)
    auto_apply_result = await preset_service.auto_apply_preset(
        location_id=location.id,
        airline=airline,
        pick_up_dates=new_dates
    )
```

---

### Reglas de Auto-Aplicación

| Condición | ¿Aplica Filtros? | Razón |
|-----------|------------------|-------|
| **Hay preset configurado** + **Día nuevo sin stack** | ✅ SÍ | Aplica template automáticamente |
| **Hay preset configurado** + **Día ya tiene stack manual** | ❌ NO | Respeta configuración existente |
| **NO hay preset configurado** + **Día nuevo** | ❌ NO | Sin template que clonar |
| **Día pre-existente** (re-import) | ❌ NO | Solo aplica a días completamente nuevos |

**Filosofía:** El preset es un "default inteligente" que no sobreescribe configuración manual existente.

---

### Estructura del Preset

#### Modelo de Datos

**Tabla:** `trips.filter_presets`

```sql
CREATE TABLE trips.filter_presets (
    id UUID PRIMARY KEY,
    location_id UUID REFERENCES entities.locations(id) ON DELETE CASCADE,
    airline VARCHAR(10),
    stack_template JSONB,  -- Array de FilterPresetTemplate
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    created_by UUID REFERENCES entities.users(id) ON DELETE SET NULL,
    UNIQUE (location_id, airline)  -- Un preset por location+airline
);
```

#### Stack Template

```json
{
  "stack_template": [
    {
      "filter_type": "reduce",
      "windows": [
        {
          "start": "00:00",
          "end": "12:00",
          "enabled": true,
          "minutes_to_reduce": 15
        },
        {
          "start": "12:00",
          "end": "24:00",
          "enabled": true,
          "minutes_to_reduce": 10
        }
      ]
    },
    {
      "filter_type": "combine",
      "windows": [
        {
          "start": "04:00",
          "end": "10:00",
          "enabled": true,
          "min_gap": 5,
          "max_gap": 20
        }
      ]
    }
  ]
}
```

**Cada template contiene:**
- `filter_type`: "reduce", "combine", "expand"
- `windows`: Array de ventanas con configuración completa

---

### Flujo Completo (Ejemplo)

#### Escenario: Manager configura preset y luego importa trips

**1. Configurar Preset (Una vez)**

```bash
POST /v2/locations/abc-123/airlines/WN/filters/preset
{
  "stack_template": [
    {
      "filter_type": "reduce",
      "windows": [{
        "start": "00:00",
        "end": "24:00",
        "enabled": true,
        "minutes_to_reduce": 10
      }]
    }
  ]
}

# Response:
{
  "id": "preset-uuid-1",
  "location_id": "abc-123",
  "airline": "WN",
  "stack_template": [...],
  "created_at": "2026-01-26T10:00:00Z"
}
```

**2. Importar Trips (Repetido cada vez)**

```javascript
// Frontend: Usuario presiona "Update"
const result = await importTrips(excelFile);

// Backend (automático, transparente):
// - Detecta fechas nuevas: [2026-02-15, 2026-02-16, 2026-02-17]
// - Busca preset para location+airline
// - Encuentra: Reduce -10min
// - Aplica a las 3 fechas
// - Crea 3 FilterSteps (uno por fecha)
// - Modifica trips automáticamente

// Response:
{
  "trips_imported": 150,
  "auto_preset_applied": {
    "applied": true,
    "days_processed": 3,
    "trips_affected": 150,
    "message": "Filtros aplicados automáticamente desde preset"
  }
}
```

**3. Verificar (Rehidratación)**

```bash
GET /v2/locations/abc-123/airlines/WN/filters/stack?pick_up_date=2026-02-15

# Response:
{
  "steps": [
    {
      "step_id": "auto-step-uuid",
      "filter_type": "reduce",
      "windows": [{"minutes_to_reduce": 10, ...}],
      "trips_affected": 50
    }
  ]
}
```

**Resultado:** Los filtros YA están aplicados sin intervención manual. ✅

---

### Ventajas del Sistema

| Ventaja | Descripción |
|---------|-------------|
| **Set and Forget** | Configurar una vez, aplicar para siempre |
| **Consistencia** | Todos los días futuros usan la misma configuración |
| **Automatización** | No requiere aplicar filtros manualmente después de cada import |
| **Flexibilidad** | Si un día específico necesita config diferente, se puede modificar manualmente (preset no sobreescribe) |
| **Transparencia** | El manager ve los FilterSteps aplicados en GET /stack |

---

### Casos de Uso

#### Caso 1: Configuración Estándar para una Aerolínea

```
Problema:
- Southwest (WN) siempre necesita Reduce -10min para trips matutinos
- Se importan trips diariamente

Solución:
1. Configurar preset una vez:
   - Reduce -10min para 04:00-10:00

2. Cada import diario:
   - Backend detecta nuevo día (ej: mañana)
   - Aplica preset automáticamente
   - Manager no hace nada
```

#### Caso 2: Día Excepcional con Config Manual

```
Día Normal (2026-02-15):
- Import → Auto-aplica preset → Reduce -10min

Día con Evento Especial (2026-02-16):
- Import → Auto-aplica preset → Reduce -10min
- Manager manualmente: Revierte reduce, aplica combine diferente
- Preset NO sobreescribe (respeta configuración manual)

Día Normal (2026-02-17):
- Import → Auto-aplica preset → Reduce -10min (preset vuelve)
```

---

### Limitaciones y Consideraciones

#### 1. Solo Aplica a Días Nuevos

```python
# CRITICAL: Solo a fechas completamente nuevas
new_dates = [
    d for d in unique_dates_imported
    if not await day_has_trips_in_db(location.id, airline, d)
]
```

**Por qué:** Si el día ya existe, podría tener configuración manual que no debe sobreescribirse.

#### 2. No Sobreescribe Stack Existente

```python
if existing_step:
    days_skipped.append(pick_up_date)
    logger.debug(f"[AUTO_PRESET] Skipping {pick_up_date} (already has stack)")
    continue
```

**Por qué:** Respetar trabajo manual del manager.

#### 3. Manejo de Errores

```python
try:
    result = await step_filter_service.apply_step(...)
except Exception as e:
    logger.error(f"[AUTO_PRESET] Error applying {template.filter_type}: {e}")
    # Continue with next template (no bloquea todo el import)
```

**Por qué:** Un error en auto-apply NO debe bloquear el import de trips.

---

### API Response con Auto-Apply

Cuando se importan trips, la respuesta incluye información de auto-apply:

```json
{
  "trips_imported": 150,
  "trips_created": 145,
  "trips_updated": 5,
  "auto_preset_result": {
    "applied": true,
    "reason": null,
    "days_processed": 3,
    "days_skipped": 0,
    "trips_affected": 150,
    "stack_cloned_from_preset": true
  }
}
```

**Campos:**
- `applied`: true si se aplicó preset
- `days_processed`: Días que recibieron filtros
- `days_skipped`: Días que ya tenían stack (no se tocaron)
- `trips_affected`: Total de trips modificados por auto-apply

---

### Endpoints de Presets

Ver sección "API Endpoints - Filter Presets" para detalles completos.

**Resumen:**
- `POST /preset` - Crear/actualizar preset
- `GET /preset` - Obtener preset actual
- `DELETE /preset` - Eliminar preset
- `POST /preset/test?pick_up_date=X` - Simular auto-apply para un día específico

---

### Troubleshooting

#### Problema: "Importé trips pero no se aplicaron filtros"

**Verificar:**

1. **¿Existe preset configurado?**
   ```bash
   GET /v2/locations/{loc}/airlines/WN/filters/preset
   # Si retorna 404 → No hay preset configurado
   ```

2. **¿El día es realmente nuevo?**
   ```python
   # Si el día ya tenía trips, auto-apply no ejecuta
   # Solo aplica a fechas completamente nuevas
   ```

3. **¿El día ya tiene stack manual?**
   ```bash
   GET /v2/locations/{loc}/airlines/WN/filters/stack?pick_up_date=2026-02-15
   # Si retorna steps → Ya tiene config, preset no sobreescribe
   ```

4. **Ver logs del backend:**
   ```python
   logger.info("[AUTO_PRESET] Preset found for location=...")
   logger.debug("[AUTO_PRESET] Cloning preset to 2026-02-15")
   logger.debug("[AUTO_PRESET] Applied reduce to 2026-02-15: 50 trips modified")
   ```

---

### Flujo Técnico Detallado

```
┌────────────────────────────────────────────────────────┐
│  1. Frontend: Importar trips vía POST /trips/import    │
└────────────────────────────────────────────────────────┘
                          |
                          v
┌────────────────────────────────────────────────────────┐
│  2. Backend: Insertar trips en PostgreSQL              │
│     - Validar y parsear Excel                          │
│     - Crear registros en trips.trips                   │
└────────────────────────────────────────────────────────┘
                          |
                          v
┌────────────────────────────────────────────────────────┐
│  3. Backend: Detectar fechas únicas importadas         │
│     unique_dates = {t.pick_up_date for t in trips}     │
└────────────────────────────────────────────────────────┘
                          |
                          v
┌────────────────────────────────────────────────────────┐
│  4. Backend: Filtrar SOLO fechas completamente nuevas  │
│     new_dates = [d for d if not exists_in_db(d)]       │
└────────────────────────────────────────────────────────┘
                          |
                          v
┌────────────────────────────────────────────────────────┐
│  5. Backend: Buscar preset para location+airline       │
│     preset = filter_presets.get(location, airline)     │
└────────────────────────────────────────────────────────┘
                          |
          ┌───────────────┴───────────────┐
          |                               |
      Preset NO existe               Preset existe
          |                               |
          v                               v
┌──────────────────┐        ┌──────────────────────────────┐
│  6a. Skip        │        │  6b. Para cada fecha nueva:  │
│  No auto-apply   │        │  - Clonar stack_template     │
└──────────────────┘        │  - Aplicar cada step en orden│
                            │  - Crear FilterSteps en DB    │
                            │  - Modificar trips            │
                            └──────────────────────────────┘
                                          |
                                          v
                            ┌──────────────────────────────┐
                            │  7. Retornar resultado       │
                            │  {                            │
                            │    trips_imported: 150,      │
                            │    auto_preset: {applied:true}│
                            │  }                            │
                            └──────────────────────────────┘
```

---

### Ejemplo Completo

#### Setup Inicial

```bash
# 1. Crear preset para ONT Airport, Southwest
POST /v2/locations/ont-uuid/airlines/WN/filters/preset
{
  "stack_template": [
    {
      "filter_type": "reduce",
      "windows": [{
        "start": "04:00",
        "end": "08:00",
        "enabled": true,
        "minutes_to_reduce": 15
      }]
    }
  ]
}

# Response: Preset creado ✅
```

#### Import Día 1 (2026-02-10)

```javascript
// Frontend: Import trips
const result = await importTrips('southwest_2026-02-10.xlsx');

// Backend detecta:
// - Fecha nueva: 2026-02-10 (no existía antes)
// - Hay preset configurado
// - Aplica reduce -15min automáticamente

// Response:
{
  "trips_imported": 50,
  "auto_preset_result": {
    "applied": true,
    "days_processed": 1,
    "trips_affected": 50
  }
}

// Verificar:
GET /stack?pick_up_date=2026-02-10
// Retorna: [{filter_type: "reduce", windows: [...]}] ✅
```

#### Import Día 2 (2026-02-11)

```javascript
// Mismo proceso automático
const result = await importTrips('southwest_2026-02-11.xlsx');

// Backend:
// - Detecta fecha nueva: 2026-02-11
// - Aplica preset automáticamente
// - Trips YA vienen filtrados

// Manager NO necesita hacer nada ✅
```

#### Manager Modifica Día Específico

```javascript
// Manager decide que 2026-02-12 necesita config especial
// 1. Importa trips (auto-apply funciona normal)
await importTrips('southwest_2026-02-12.xlsx');

// 2. Manualmente revierte y aplica config diferente
await revertFilter('reduce', '2026-02-12');
await applyFilter('combine', '2026-02-12', {min_gap: 10, max_gap: 30});

// 3. Días futuros siguen usando preset normal
await importTrips('southwest_2026-02-13.xlsx');
// → Auto-aplica preset (reduce -15min) ✅
```

---

### Casos Especiales

#### 1. Re-import del Mismo Día

```javascript
// Import inicial
await importTrips('feb15.xlsx');  // ← Auto-aplica preset

// Re-import (corrección de datos)
await importTrips('feb15_corregido.xlsx');  // ← NO auto-aplica (día ya existe)

// Resultado:
// - Trips se actualizan
// - FilterSteps se mantienen
// - Filtros NO se vuelven a aplicar
```

**Por qué:** El día ya existe, no es "nuevo". El preset solo aplica a días completamente nuevos.

#### 2. Import Bulk de Múltiples Días

```javascript
// Import archivo con 30 días
await importTrips('enero_completo.xlsx');

// Backend:
// - Detecta 30 fechas únicas
// - Identifica cuáles son nuevas (ej: 25 son nuevas, 5 pre-existentes)
// - Aplica preset a las 25 nuevas
// - Skip las 5 pre-existentes

// Response:
{
  "trips_imported": 750,
  "auto_preset_result": {
    "applied": true,
    "days_processed": 25,
    "days_skipped": 5,
    "trips_affected": 625
  }
}
```

#### 3. Actualizar Preset

```bash
# Cambiar config del preset
PUT /v2/locations/ont-uuid/airlines/WN/filters/preset
{
  "stack_template": [
    {
      "filter_type": "reduce",
      "windows": [{
        "minutes_to_reduce": 20  # ← Cambio de 15 a 20
      }]
    }
  ]
}

# Días futuros usarán nueva config
# Días pasados mantienen config anterior (no se re-aplica retroactivamente)
```

---

### Consideraciones de Performance

#### Para Imports Grandes (1000+ trips)

**Problema potencial:**
- Aplicar filtros a miles de trips puede causar timeouts
- Transacciones largas bloquean la tabla

**Solución implementada:**
```python
# El auto-apply usa apply_step() que es eficiente
# Cada día se procesa en su propia transacción
# Si un día falla, no bloquea los demás
```

**Recomendación:**
- Imports <500 trips: Auto-apply inline ✅
- Imports >500 trips: Considerar background task (futuro)

#### Cache de Presets

```python
# El preset se busca UNA vez por import
preset = await service.get_preset(location_id, airline)

# Se reutiliza para todas las fechas
for pick_up_date in new_dates:
    # Usa el mismo preset
```

---

### Monitoreo y Logs

#### Logs del Backend

```python
logger.info("[AUTO_PRESET] Preset found for location=abc-123, airline=WN")
logger.info("[AUTO_PRESET] Processing 3 dates")
logger.debug("[AUTO_PRESET] Cloning preset to 2026-02-15")
logger.debug("[AUTO_PRESET] Applied reduce to 2026-02-15: 50 trips modified")
logger.info("[AUTO_PRESET] Completed. Processed 3 days, affected 150 trips")
```

#### Logs de Debugging

```python
logger.debug("[AUTO_PRESET] Skipping 2026-02-10 (already has stack)")
logger.error("[AUTO_PRESET] Error applying combine to 2026-02-12: {error}")
```

---

### Testing

#### Test Endpoint

```bash
# Simular auto-apply para UN día específico (dry-run)
POST /v2/locations/{loc}/airlines/WN/filters/preset/test?pick_up_date=2026-02-15

# Retorna:
{
  "applied": true,
  "days_processed": 1,
  "trips_affected": 50,
  "stack_cloned_from_preset": true
}
```

**Uso:** Verificar que el preset funcionará antes de hacer import real.

---

### Resumen

| Característica | Comportamiento |
|----------------|----------------|
| **Trigger** | Después de importar trips (POST /trips/import) |
| **Condición** | Existe preset + Día nuevo sin stack |
| **Qué hace** | Clona stack_template y aplica filtros automáticamente |
| **Qué NO hace** | Sobreescribir config manual existente |
| **Performance** | Eficiente para imports normales (<500 trips) |
| **Transparencia** | FilterSteps visibles en GET /stack |
| **Rollback** | Manager puede revertir como cualquier filtro manual |

**Beneficio Principal:** "Set and forget" - Configurar una vez, aplicar para siempre. ✨

---

## Guía Completa de Revert para Frontend

Esta sección documenta a profundidad cómo funciona el proceso de revert en el backend y cómo debe implementarlo el frontend correctamente.

### Proceso de Revert - 3 Pasos Automáticos

Cuando el frontend llama a cualquier endpoint de revert, el backend ejecuta automáticamente este proceso:

```
┌─────────────────────────────────────────────────────────────┐
│ PASO 1: Marcar FilterStep como Inactivo                      │
├─────────────────────────────────────────────────────────────┤
│ UPDATE trips.filter_steps                                    │
│ SET is_active = false                                        │
│ WHERE id = 'step-uuid'                                       │
│                                                              │
│ El FilterStep NO se elimina, se mantiene para historial     │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ PASO 2: Resetear TODOS los Trips del Día a Original          │
├─────────────────────────────────────────────────────────────┤
│ Para CADA trip del día:                                      │
│   trip.pick_up_time = trip.original_pick_up_time            │
│   trip.reduce_applied = false                               │
│   trip.combine_applied = false                              │
│   trip.expand_applied = false                               │
│   trip.current_step_id = null                               │
│   trip.filtered_at = null                                   │
│                                                              │
│ NOTA: original_pick_up_time aún NO se limpia (ver Paso 3)  │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ PASO 3: Re-aplicar Steps Restantes (Si Existen)              │
├─────────────────────────────────────────────────────────────┤
│ Caso A: Quedan steps activos (ej: revertiste el del medio)  │
│   → Re-aplica TODOS los steps activos en orden             │
│   → Recalcula tiempos desde original_pick_up_time          │
│   → Mantiene original_pick_up_time (porque aún hay filtros)│
│                                                              │
│ Caso B: NO quedan steps activos (stack vacío)               │
│   → Limpia original_pick_up_time = null                     │
│   → Trips quedan completamente sin filtros                  │
└─────────────────────────────────────────────────────────────┘
```

**Código real del backend:** [step_filter_service.py:707-838](features/trips/services/step_filter_service.py:707)

---

### Dos Formas de Revertir

#### Opción 1: Revert Last (Más Común)

```javascript
// Usuario apaga switch de un filtro
// Frontend debe llamar:

const response = await axios.post(
  `/v2/locations/${locationId}/airlines/${airline}/filters/revert-last`,
  null,  // Sin body
  { params: { pick_up_date: pickUpDate } }
);

// Response:
{
  "step_id": "uuid-del-step-revertido",
  "filter_type": "reduce",
  "trips_recalculated": 25,
  "remaining_steps": 0,  // 0 = stack vacío, >0 = quedan steps
  "stack_state": {
    "steps": [],  // Vacío si remaining_steps = 0
    "total_trips_affected": 0
  }
}
```

**Cuándo usar:**
- Usuario apaga switch de un filtro (ej: Reduce OFF)
- Quieres revertir el último filtro aplicado
- Es el caso más común (90% de los casos)

#### Opción 2: Revert by Step ID (Avanzado)

```javascript
// Revertir un step específico del stack
// (ej: revertir Combine pero mantener Reduce y Expand)

const response = await axios.post(
  `/v2/locations/${locationId}/airlines/${airline}/filters/step/${stepId}/revert`
);

// Response: Igual que revert-last
```

**Cuándo usar:**
- Tienes UI avanzada que muestra lista de steps
- Usuario quiere remover un step específico del medio del stack
- Caso avanzado (10% de los casos)

---

### Qué Hace el Backend Automáticamente

Cuando llamas a cualquier endpoint de revert, el backend **YA hace TODO esto automáticamente:**

| Acción | Estado | Detalles |
|--------|--------|----------|
| **Marcar step como inactivo** | ✅ Automático | `is_active = false` en DB |
| **Resetear trips a tiempos originales** | ✅ Automático | `pick_up_time = original_pick_up_time` |
| **Limpiar flags de filtros** | ✅ Automático | `reduce_applied = false`, etc. |
| **Re-aplicar steps restantes** | ✅ Automático | Si quedan otros steps activos |
| **Limpiar original_pick_up_time** | ✅ Automático | Solo si stack queda vacío |
| **Publicar evento WebSocket** | ✅ Automático | `step_reverted` a Redis |
| **Actualizar current_step_id** | ✅ Automático | `null` o step más reciente |

**El frontend NO necesita:**
- ❌ Modificar trips manualmente
- ❌ Calcular tiempos originales
- ❌ Limpiar flags manualmente
- ❌ Manejar steps restantes

**El backend lo hace TODO.**

---

### Qué DEBE Hacer el Frontend

Después de llamar al endpoint de revert:

```javascript
async function handleRevert(filterType, pickUpDate) {
  try {
    setIsReverting(true);

    // 1. Llamar endpoint de revert
    const response = await axios.post(
      `/v2/locations/${locationId}/airlines/${airline}/filters/revert-last`,
      null,
      { params: { pick_up_date: pickUpDate } }
    );

    // 2. CRÍTICO: Actualizar estado local con stack_state del response
    //    NO usar valores del estado local, usar lo que retorna el backend
    updateStateFromStackState(response.stack_state);

    // 3. CRÍTICO: Limpiar savedState
    //    Si remaining_steps = 0, limpiar todo
    //    Si remaining_steps > 0, actualizar con nuevos steps
    if (response.remaining_steps === 0) {
      setSavedReduce(null);
      setSavedCombine(null);
      setSavedExpand(null);
    } else {
      // Actualizar savedState con stack_state.steps
      updateSavedStateFromSteps(response.stack_state.steps);
    }

    // 4. CRÍTICO: Refetch trips para ver tiempos originales
    //    El backend NO envía trips_batch en revert
    await queryClient.invalidateQueries(['trips', locationId, airline, pickUpDate]);

    // 5. Mostrar notificación
    toast.success(`Filtro ${response.filter_type} revertido`);

  } catch (error) {
    if (error.response?.status === 400) {
      // No hay steps activos para revertir
      toast.error('No hay filtros activos para revertir');
    } else {
      toast.error('Error al revertir filtro');
    }
  } finally {
    setIsReverting(false);
  }
}
```

---

### Casos de Revert

#### Caso 1: Revert Último Filtro (Stack Vacío Después)

**Estado Inicial:**
```javascript
Stack: [
  { step_order: 1, filter_type: "reduce", trips_affected: 25 }
]

Trips:
  - Trip A: pick_up_time="08:15", original_pick_up_time="08:30", reduce_applied=true
  - Trip B: pick_up_time="09:45", original_pick_up_time="10:00", reduce_applied=true
```

**Usuario apaga Reduce switch:**

```javascript
await POST('/revert-last?pick_up_date=2026-01-25');
```

**Response:**
```json
{
  "step_id": "reduce-step-uuid",
  "filter_type": "reduce",
  "trips_recalculated": 25,
  "remaining_steps": 0,  // ← Stack quedó vacío
  "stack_state": {
    "steps": [],  // ← Vacío
    "total_trips_affected": 0
  }
}
```

**Estado Final:**
```javascript
Stack: []  // Vacío

Trips:
  - Trip A: pick_up_time="08:30", original_pick_up_time=null, reduce_applied=false
  - Trip B: pick_up_time="10:00", original_pick_up_time=null, reduce_applied=false
            ↑ Restaurado          ↑ Limpiado               ↑ Limpiado
```

**Frontend debe:**
```javascript
// Limpiar TODO el estado
setSavedReduce(null);
setState({ reduce: { enabled: false, windows: [] } });
```

---

#### Caso 2: Revert Filtro del Medio (Stack NO Vacío)

**Estado Inicial:**
```javascript
Stack: [
  { step_order: 1, filter_type: "reduce", trips_affected: 25 },
  { step_order: 2, filter_type: "combine", trips_affected: 10 },
  { step_order: 3, filter_type: "expand", trips_affected: 5 }
]

Trips:
  - Trip A: pick_up_time="08:00", original="08:30"
            (reduce -15min, combine a 08:00, expand +5min)
```

**Usuario revierte Combine (step_order=2):**

```javascript
await POST(`/step/combine-step-uuid/revert`);
```

**Proceso del Backend:**
```
1. Marca Combine como is_active=false ✅
2. Resetea trips a original (08:30) ✅
3. Re-aplica steps restantes:
   - Re-aplica Reduce: 08:30 → 08:15 ✅
   - Re-aplica Expand: 08:15 → 08:20 ✅
```

**Response:**
```json
{
  "step_id": "combine-step-uuid",
  "filter_type": "combine",
  "trips_recalculated": 25,
  "remaining_steps": 2,  // ← Quedan 2 steps activos
  "stack_state": {
    "steps": [
      { "filter_type": "reduce", ... },  // Re-aplicado
      { "filter_type": "expand", ... }   // Re-aplicado
    ],
    "total_trips_affected": 30
  }
}
```

**Estado Final:**
```javascript
Stack: [
  { step_order: 1, filter_type: "reduce" },  // Activo
  { step_order: 3, filter_type: "expand" }   // Activo
]

Trips:
  - Trip A: pick_up_time="08:20", original="08:30"
            (reduce -15min, expand +5min, sin combine)
```

**Frontend debe:**
```javascript
// Actualizar estado con el nuevo stack
updateStateFromStackState(response.stack_state);

// savedState debe reflejar el nuevo stack (reduce + expand, sin combine)
setSavedReduce(response.stack_state.steps.find(s => s.filter_type === 'reduce'));
setSavedCombine(null);  // Ya no está en el stack
setSavedExpand(response.stack_state.steps.find(s => s.filter_type === 'expand'));
```

---

### Flujo Correcto de Revert en el Frontend

```javascript
// ============================================
// IMPLEMENTACIÓN COMPLETA DE REVERT
// ============================================

async function handleFilterSwitch(filterType, enabled, pickUpDate) {
  if (enabled) {
    // Usuario ENCIENDE filtro
    // → Esto es solo cambio de UI local
    // → NO llama al backend hasta que haga Apply
    setState(prev => ({
      ...prev,
      [filterType]: { ...prev[filterType], enabled: true }
    }));

  } else {
    // Usuario APAGA filtro
    // → Debe REVERTIR en el backend inmediatamente

    try {
      setIsReverting(true);

      // PASO 1: Llamar backend para revertir
      const response = await axios.post(
        `/v2/locations/${locationId}/airlines/${airline}/filters/revert-last`,
        null,
        { params: { pick_up_date: pickUpDate } }
      );

      // PASO 2: Procesar respuesta
      console.log('[Revert] Backend response:', {
        filter_type: response.filter_type,
        trips_recalculated: response.trips_recalculated,
        remaining_steps: response.remaining_steps
      });

      // PASO 3: Actualizar estado local con stack_state
      const { stack_state } = response;

      // Parse steps del backend
      const reduceStep = stack_state.steps.find(s => s.filter_type === 'reduce');
      const combineStep = stack_state.steps.find(s => s.filter_type === 'combine');
      const expandStep = stack_state.steps.find(s => s.filter_type === 'expand');

      // PASO 4: CRÍTICO - Actualizar AMBOS state y savedState
      const newState = {
        reduce: reduceStep
          ? parseStepToConfig(reduceStep)
          : { enabled: false, windows: [] },
        combine: combineStep
          ? parseStepToConfig(combineStep)
          : { enabled: false, windows: [] },
        expand: expandStep
          ? parseStepToConfig(expandStep)
          : { enabled: false, windows: [] }
      };

      setState(newState);
      setSavedReduce(newState.reduce);
      setSavedCombine(newState.combine);
      setSavedExpand(newState.expand);

      // PASO 5: CRÍTICO - Refetch trips para ver tiempos originales
      // El backend NO envía trips_batch en revert
      await queryClient.invalidateQueries(['trips', locationId, airline, pickUpDate]);

      // PASO 6: Mostrar feedback
      if (response.remaining_steps === 0) {
        toast.success('Filtros revertidos - Trips con horarios originales');
      } else {
        toast.info(`Filtro ${response.filter_type} revertido - ${response.remaining_steps} filtros activos`);
      }

    } catch (error) {
      console.error('[Revert] Error:', error);

      if (error.response?.status === 400 && error.response?.data?.detail?.includes('No active steps')) {
        // No hay steps activos para revertir
        toast.warning('No hay filtros activos para revertir');

        // Limpiar estado local
        setState(prev => ({
          ...prev,
          [filterType]: { enabled: false, windows: [] }
        }));

      } else {
        toast.error('Error al revertir filtro');

        // Revertir el switch a ON (porque el revert falló)
        setState(prev => ({
          ...prev,
          [filterType]: { ...prev[filterType], enabled: true }
        }));
      }

    } finally {
      setIsReverting(false);
    }
  }
}
```

---

### WebSocket Event Handler para Revert

Cuando otro usuario (o otra tab) revierte un filtro, recibirás el evento `step_reverted`:

```javascript
// Handler en el WebSocket provider
function handleStepReverted(event: FilterStepRevertedEvent) {
  console.log('[WebSocket] Filter reverted:', event.filter_type);

  // CRÍTICO: Solo procesar si es de la misma airline y fecha actual
  if (event.airline !== currentAirline) return;

  // 1. Reload stack from backend
  await tripFilters.reloadStackFromBackend(pickUpDate);

  // 2. Refetch trips
  await queryClient.invalidateQueries(['trips', locationId, airline, pickUpDate]);

  // 3. Show notification
  toast.info(`Filtro ${event.filter_type} revertido por otro usuario`);
}
```

---

### Mensajes de Notificación Correctos

#### Para Bulk Revert (Múltiples Días)

```javascript
// ✅ CORRECTO - Mostrar trips Y días
const { total_trips_recalculated, days_with_reverts, filter_type } = response.data;

toast.success(
  `Filtro ${filter_type} revertido: ` +
  `${total_trips_recalculated.toLocaleString()} trips ` +
  `en ${days_with_reverts} días`
);

// Ejemplo: "Filtro reduce revertido: 900 trips en 29 días" ✅
```

```javascript
// ❌ INCORRECTO - Solo mostrar steps
toast.success(`Reverted ${response.total_steps_reverted} steps`);
// → "Reverted 29 steps" ❌
// Problema: El usuario no sabe cuántos trips fueron afectados
```

#### Para Single-Day Revert

```javascript
// ✅ CORRECTO
const { trips_recalculated, filter_type } = response.data;

toast.success(
  `Filtro ${filter_type} revertido: ${trips_recalculated} trips restaurados`
);

// Ejemplo: "Filtro reduce revertido: 31 trips restaurados" ✅
```

**Regla General:** Siempre priorizar el **número de trips** sobre el número de steps/días.

---

### Errores Comunes y Soluciones

#### Error 1: "No active steps found"

**Causa:** No hay filtros activos para ese día.

**Solución en el Frontend:**
```javascript
try {
  await revertLast(pickUpDate);
} catch (error) {
  if (error.response?.data?.detail?.includes('No active steps')) {
    // El día no tiene filtros activos
    console.log('No hay filtros para revertir');

    // Asegurar que el estado local también esté limpio
    setSavedReduce(null);
    setState({ reduce: { enabled: false, windows: [] } });
  }
}
```

#### Error 2: Switch se revierte pero trips no cambian

**Causa:** Frontend no hace refetch de trips después del revert.

**Solución:**
```javascript
// SIEMPRE refetch trips después de revert
await queryClient.invalidateQueries(['trips', locationId, airline, pickUpDate]);

// O refetch explícito
await refetchTrips();
```

#### Error 3: isDirty se vuelve true después de revert

**Causa:** savedState no se actualizó con stack_state del backend.

**Solución:**
```javascript
// Después de revert, actualizar savedState
const { stack_state } = response;

// Parse y actualizar
setSavedReduce(parseFromStack(stack_state, 'reduce'));
setSavedCombine(parseFromStack(stack_state, 'combine'));
setSavedExpand(parseFromStack(stack_state, 'expand'));

// Ahora isDirty = false (state === savedState)
```

---

### Checklist de Implementación Frontend

Para implementar revert correctamente, el frontend DEBE:

- [ ] **1. Llamar endpoint correcto**
  ```javascript
  POST /revert-last?pick_up_date=${pickUpDate}
  ```

- [ ] **2. Manejar response correctamente**
  ```javascript
  const { stack_state, remaining_steps, filter_type } = response;
  ```

- [ ] **3. Actualizar state CON stack_state del backend**
  ```javascript
  // NO usar estado local, usar stack_state del response
  updateStateFromBackend(stack_state);
  ```

- [ ] **4. Actualizar savedState CON stack_state**
  ```javascript
  // CRÍTICO para que isDirty funcione
  setSavedState(parseStackState(stack_state));
  ```

- [ ] **5. Refetch trips**
  ```javascript
  // SIEMPRE refetch para ver tiempos originales
  await queryClient.invalidateQueries(['trips']);
  ```

- [ ] **6. Manejar error "No active steps"**
  ```javascript
  catch (error) {
    if (error.detail.includes('No active steps')) {
      // Limpiar estado local
    }
  }
  ```

- [ ] **7. Escuchar evento WebSocket**
  ```javascript
  case 'step_reverted':
    await reloadStackFromBackend();
    await refetchTrips();
  ```

---

### Ejemplo Completo de Implementación

```typescript
// ============================================
// Hook: use-trip-filters-v2.ts
// ============================================

interface RevertOptions {
  filterType: 'reduce' | 'combine' | 'expand';
  pickUpDate: string;
  stepId?: string;  // Opcional, para revert específico
}

async function revertFilter({ filterType, pickUpDate, stepId }: RevertOptions) {
  try {
    setIsReverting(true);
    console.log(`[Revert] Starting revert for ${filterType} on ${pickUpDate}`);

    // 1. Determinar endpoint a usar
    const endpoint = stepId
      ? `/v2/locations/${locationId}/airlines/${airline}/filters/step/${stepId}/revert`
      : `/v2/locations/${locationId}/airlines/${airline}/filters/revert-last`;

    const params = stepId ? {} : { pick_up_date: pickUpDate };

    // 2. Llamar backend
    const response = await axios.post<StepRevertResult>(endpoint, null, { params });

    console.log('[Revert] Backend response:', {
      step_id: response.data.step_id,
      filter_type: response.data.filter_type,
      trips_recalculated: response.data.trips_recalculated,
      remaining_steps: response.data.remaining_steps
    });

    // 3. Extraer stack_state actualizado
    const { stack_state, remaining_steps } = response.data;

    // 4. Parse steps del backend
    const parseStackToState = (stack: StackState) => {
      const reduceStep = stack.steps.find(s => s.filter_type === 'reduce');
      const combineStep = stack.steps.find(s => s.filter_type === 'combine');
      const expandStep = stack.steps.find(s => s.filter_type === 'expand');

      return {
        reduce: reduceStep
          ? {
              enabled: true,
              windows: reduceStep.windows.map(w => ({
                start: w.start,
                end: w.end,
                enabled: w.enabled ?? true,
                minutes_to_reduce: w.minutes_to_reduce
              }))
            }
          : { enabled: false, windows: [] },

        combine: combineStep
          ? {
              enabled: true,
              windows: combineStep.windows.map(w => ({
                start: w.start,
                end: w.end,
                enabled: w.enabled ?? true,
                min_gap: w.min_gap,
                max_gap: w.max_gap
              }))
            }
          : { enabled: false, windows: [] },

        expand: expandStep
          ? {
              enabled: true,
              windows: expandStep.windows.map(w => ({
                start: w.start,
                end: w.end,
                enabled: w.enabled ?? true,
                min_gap: w.min_gap,
                max_gap: w.max_gap,
                max_shift: w.max_shift
              }))
            }
          : { enabled: false, windows: [] }
      };
    };

    // 5. Actualizar AMBOS state y savedState con stack_state del backend
    const newState = parseStackToState(stack_state);

    setState(newState);
    setSavedReduce(newState.reduce);
    setSavedCombine(newState.combine);
    setSavedExpand(newState.expand);

    console.log('[Revert] State updated from backend:', {
      reduce_enabled: newState.reduce.enabled,
      combine_enabled: newState.combine.enabled,
      expand_enabled: newState.expand.enabled
    });

    // 6. Refetch trips para ver tiempos actualizados
    console.log('[Revert] Refetching trips...');
    await queryClient.invalidateQueries(['trips', locationId, airline, pickUpDate]);

    // 7. Feedback al usuario
    if (remaining_steps === 0) {
      toast.success('Todos los filtros revertidos - Horarios originales restaurados');
    } else {
      toast.success(`Filtro ${response.data.filter_type} revertido - ${remaining_steps} filtros activos`);
    }

    // 8. Retornar éxito
    return {
      success: true,
      remaining_steps,
      filter_type: response.data.filter_type
    };

  } catch (error: any) {
    console.error('[Revert] Error:', error);

    // Manejar errores específicos
    if (error.response?.status === 400) {
      const detail = error.response.data?.detail || '';

      if (detail.includes('No active steps')) {
        toast.warning('No hay filtros activos para revertir');

        // Asegurar que estado local esté limpio
        setState(prev => ({
          ...prev,
          [filterType]: { enabled: false, windows: [] }
        }));

        return { success: false, reason: 'no_active_steps' };

      } else if (detail.includes('already reverted')) {
        toast.warning('Este filtro ya fue revertido');
        return { success: false, reason: 'already_reverted' };
      }
    }

    // Error genérico
    toast.error('Error al revertir filtro - Intente nuevamente');

    // Refetch stack para sincronizar con backend
    await rehidration.reload(pickUpDate);

    return { success: false, reason: 'unknown_error' };

  } finally {
    setIsReverting(false);
  }
}

// ============================================
// USO EN COMPONENTE
// ============================================

function FilterReducePanel({ pickUpDate }) {
  const { state, setState, revertFilter, isReverting } = useTripFilters();

  const handleSwitchChange = async (enabled: boolean) => {
    if (!enabled) {
      // Usuario apaga switch → REVERTIR INMEDIATAMENTE
      const result = await revertFilter({
        filterType: 'reduce',
        pickUpDate: pickUpDate
      });

      if (result.success) {
        console.log('✅ Revert successful');
        // El estado ya fue actualizado por revertFilter()
      }
    } else {
      // Usuario enciende switch → Solo cambio local
      setState(prev => ({
        ...prev,
        reduce: { ...prev.reduce, enabled: true }
      }));
    }
  };

  return (
    <Switch
      checked={state.reduce.enabled}
      onCheckedChange={handleSwitchChange}
      disabled={isReverting}
    />
  );
}
```

---

### Consideraciones Críticas

#### 1. **NO Confiar en Estado Local**

```javascript
// ❌ INCORRECTO
await POST('/revert-last');
setState({ reduce: { enabled: false } });  // NO confiar solo en esto

// ✅ CORRECTO
const response = await POST('/revert-last');
const newState = parseStackState(response.stack_state);  // Usar respuesta del backend
setState(newState);
```

**Por qué:** El backend puede tener steps restantes que el frontend no conoce.

#### 2. **Siempre Refetch Trips**

```javascript
// ❌ INCORRECTO
await revert();
// No hacer refetch → Trips siguen mostrando tiempos viejos

// ✅ CORRECTO
await revert();
await queryClient.invalidateQueries(['trips']);
// → Trips muestran tiempos correctos
```

**Por qué:** El backend NO envía trips_batch en revert. El frontend debe hacer GET /trips.

#### 3. **Actualizar savedState Inmediatamente**

```javascript
// ✅ CORRECTO
const { stack_state } = response;
setSavedReduce(parseFromStack(stack_state, 'reduce'));
setSavedCombine(parseFromStack(stack_state, 'combine'));
setSavedExpand(parseFromStack(stack_state, 'expand'));

// Ahora isDirty se calcula correctamente
const isDirty = JSON.stringify(state) !== JSON.stringify(savedState);
```

**Por qué:** Para que el botón Apply se deshabilite correctamente después del revert.

#### 4. **Usar pickUpDate Correcto**

```javascript
// ❌ INCORRECTO
await POST(`/revert-last?pick_up_date=2026-01-01`);
// Si los filtros están en 2026-01-31, NO los encontrará

// ✅ CORRECTO
const currentPickUpDate = getCurrentPickUpDate();  // Del state o prop
await POST(`/revert-last?pick_up_date=${currentPickUpDate}`);
```

**Por qué:** El backend busca FilterSteps por fecha específica.

#### 5. **Manejar remaining_steps**

```javascript
if (response.remaining_steps === 0) {
  // Stack completamente vacío
  setSavedReduce(null);
  setSavedCombine(null);
  setSavedExpand(null);

} else {
  // Quedan steps activos, usar stack_state
  updateFromStackState(response.stack_state);
}
```

**Por qué:** Si quedan steps, el estado debe reflejarlo (no todo debe estar en null/false).

---

### Debugging del Revert

```javascript
// Agregar logs detallados para debugging

console.group('[Revert] Debug Info');

console.log('1. Request:', {
  endpoint: '/revert-last',
  pick_up_date: pickUpDate,
  location_id: locationId,
  airline: airline
});

console.log('2. Response:', {
  step_id: response.step_id,
  filter_type: response.filter_type,
  trips_recalculated: response.trips_recalculated,
  remaining_steps: response.remaining_steps
});

console.log('3. Stack State:', {
  total_steps: response.stack_state.steps.length,
  step_types: response.stack_state.steps.map(s => s.filter_type),
  total_affected: response.stack_state.total_trips_affected
});

console.log('4. Parsed State:', {
  reduce_enabled: newState.reduce.enabled,
  combine_enabled: newState.combine.enabled,
  expand_enabled: newState.expand.enabled
});

console.log('5. Saved State Updated:', {
  savedReduce_enabled: savedReduce?.enabled,
  savedCombine_enabled: savedCombine?.enabled,
  savedExpand_enabled: savedExpand?.enabled
});

console.groupEnd();
```

---

### Resumen de Endpoints de Revert

| Endpoint | Método | Qué Hace | Cuándo Usar |
|----------|--------|----------|-------------|
| `/revert-last?pick_up_date=X` | POST | Revierte último step activo | Usuario apaga switch de filtro |
| `/step/{step_id}/revert` | POST | Revierte step específico | UI avanzada con lista de steps |
| `/bulk/revert` | POST | Revierte filtros en múltiples días | Limpiar filtros de rango de fechas |

**Todos retornan:** `StepRevertResult` con `stack_state` actualizado.

---

### Tabla de Responsabilidades

| Acción | Backend | Frontend |
|--------|---------|----------|
| Marcar step como inactivo | ✅ Automático | ❌ No hacer |
| Resetear trips a original | ✅ Automático | ❌ No hacer |
| Re-aplicar steps restantes | ✅ Automático | ❌ No hacer |
| Publicar WebSocket event | ✅ Automático | ❌ No hacer |
| Actualizar estado local | ❌ No hace | ✅ **DEBE hacer** |
| Refetch trips | ❌ No hace | ✅ **DEBE hacer** |
| Actualizar savedState | ❌ No hace | ✅ **DEBE hacer** |
| Mostrar notificación | ❌ No hace | ✅ **DEBE hacer** |

**Conclusión:** El backend hace todo el trabajo pesado. El frontend solo debe actualizar su estado local y refetch trips.

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
