# Ground Filters - Complete Workflow Documentation

**Fecha:** 2026-01-17
**Versión:** 1.0
**Autor:** Backend Team
**Estado:** Implementado y en Producción

---

## 📋 Tabla de Contenidos

1. [Visión General](#1-visión-general)
2. [Arquitectura del Sistema](#2-arquitectura-del-sistema)
3. [Modelos de Datos](#3-modelos-de-datos)
4. [Flujo Completo Paso a Paso](#4-flujo-completo-paso-a-paso)
5. [Lógica de Filtros Detallada](#5-lógica-de-filtros-detallada)
6. [Reglas y Restricciones](#6-reglas-y-restricciones)
7. [Persistencia y Base de Datos](#7-persistencia-y-base-de-datos)
8. [Endpoints API](#8-endpoints-api)
9. [Ejemplos Concretos](#9-ejemplos-concretos)
10. [Consideraciones Técnicas](#10-consideraciones-técnicas)
11. [Diagramas de Flujo](#11-diagramas-de-flujo)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Visión General

### 1.1 Propósito

Los **Ground Filters** permiten ajustar automáticamente los tiempos de pickup (`pick_up_time`) de trips outbound para optimizar la logística de transporte terrestre en aeropuertos.

### 1.2 Tipos de Filtros

| Filtro | Objetivo | Scope |
|--------|----------|-------|
| **Reduce** | Reducir tiempos de anticipación (lead time) | Global - Todos los trips del rango de fechas |
- Prioridad 0 ,esta por encima de combine y expand. 
- Siempre resta tiempo del pick up time origuinal , Ejemplo cuando esta off es resta 0 pero si primero estan activos combine y expand y luego reduce entra en esena restando del tiempo origuinal y luego se aplican otraves combine y expand sobre ese tiempo,
ejemplo reduce esta en off  combane tomo dos pickup time origuinal 2:00 y 2:30 = 2:15  pero luego reduce se confuigura a -20 entoces el algoritmo seria 1:40 y 2:10 = 1:55 , aplicar cada parte nesesaria segun frontend o backend , reduce se debe dejar fuera de la regla anticoliciones pq no genera nada de coliciones 
| **Combine** | Combinar trips cercanos en un solo pickup | Por Día - Solo trips del mismo `pick_up_date` | Prioridad 1
- Cuando combine es aplicado los trips no se fucionan o pierden sus propiedades unicas sino que simplemente toman otro pick up time .
| **Expand** | Separar trips muy juntos | Por Día - Solo trips del mismo `pick_up_date` | Prioridad 1 
- 

### 1.3 Criterios de Elegibilidad

**Solo se procesan trips que cumplan TODOS estos criterios:**

```python
✅ trip_type = 'outbound'
✅ status = 'scheduled'
✅ location_id = {location_id del request}
✅ airline = {airline del request}
✅ pick_up_date >= pick_up_date_from (si se especifica)
✅ pick_up_date <= pick_up_date_to (si se especifica)
```

**Trips excluidos:**
- ❌ trip_type = 'inbound' o 'flight'
- ❌ status = 'completed', 'cancelled', 'en_route', etc.
- ❌ Otras airlines
- ❌ Fuera del rango de fechas

---

## 2. Arquitectura del Sistema

### 2.1 Capas de la Aplicación

```
┌─────────────────────────────────────────────────────┐
│                   FRONTEND                          │
│  (React + TypeScript + use-trip-filters.ts)        │
└─────────────────────────────────────────────────────┘
                        ↓ HTTP/REST
┌─────────────────────────────────────────────────────┐
│                API LAYER (FastAPI)                  │
│  - trips_router.py                                  │
│  - Endpoints: /preview, /apply, /revert            │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│              SERVICE LAYER                          │
│  - TripFilterService (trip_filter_service.py)      │
│  - Lógica de negocio                                │
│  - Validaciones                                     │
│  - Aplicación de reglas                             │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│              DATA MODELS                            │
│  - filter_models.py (Pydantic)                      │
│  - FilterRequest, FilterPreviewResult, etc.         │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│            DATABASE LAYER (PostgreSQL)              │
│  - Table: trips.trips                               │
│  - Columns: pick_up_time, original_pick_up_time,   │
│             filter_applied, filter_batch_id, etc.   │
└─────────────────────────────────────────────────────┘
```

### 2.2 Archivos Principales

```
backend/
├── features/trips/
│   ├── routes/
│   │   └── trips_router.py           # Endpoints API
│   ├── services/
│   │   └── trip_filter_service.py    # Lógica de filtros
│   ├── models/
│   │   └── filter_models.py          # Modelos Pydantic
│   └── utils/
│       └── ...
├── shared/db/schemas/trips/
│   └── trips.py                       # Modelo SQLAlchemy
└── docs/
    ├── GROUND_FILTERS_COMPLETE_WORKFLOW.md  # Este documento
    └── FRONTEND_FILTERS_IMPLEMENTATION_FOR_BACKEND.md
```

---

## 3. Modelos de Datos

### 3.1 FilterRequest (Request Body)

**Archivo:** `features/trips/models/filter_models.py`

```python
class FilterRequest(BaseModel):
    """Request model para aplicar filtros."""

    # ✅ Filtrado por fecha (NUEVO - 2026-01-17)
    pick_up_date_from: Optional[str] = None  # "YYYY-MM-DD"
    pick_up_date_to: Optional[str] = None    # "YYYY-MM-DD"

    # Configuraciones de filtros
    reduce: Optional[ReduceFilterConfig] = None
    combine: Optional[CombineFilterConfig] = None
    expand: Optional[ExpandFilterConfig] = None
```

**Ejemplo JSON:**
```json
{
  "pick_up_date_from": "2025-10-01",
  "pick_up_date_to": "2025-10-31",
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 30,
    "hotel_names": ["Hilton Downtown", "Marriott Airport"],
    "time_range": {
      "start": "05:00",
      "end": "10:00"
    }
  },
  "combine": {
    "enabled": false
  },
  "expand": {
    "enabled": false
  }
}
```

### 3.2 Configuración de Reduce

```python
class ReduceFilterConfig(BaseModel):
    """Configuración para Lead Time Reduction."""
    enabled: bool = False
    minutes_to_reduce: int = Field(default=0, ge=0, le=120)
    hotel_names: Optional[list[str]] = None  # None = TODOS
    time_range: Optional[TimeRange] = None   # None = TODOS
```

**Parámetros:**
- `minutes_to_reduce`: Minutos a restar (0-120)
- `hotel_names`: Lista de hoteles a filtrar. Si es `null`, aplica a TODOS.
- `time_range`: Rango de horas (ej: "05:00" - "10:00"). Si es `null`, aplica a TODAS las horas.

### 3.3 Configuración de Combine

```python
class CombineFilterConfig(BaseModel):
    """Configuración para Combine (contract) filter."""
    enabled: bool = False
    min_gap: int = Field(ge=1, le=60)   # ej: 15 min
    max_gap: int = Field(ge=1, le=120)  # ej: 20 min
    hotel_names: Optional[list[str]] = None all be default
    time_range: Optional[TimeRange] = None
```

**Lógica:** M {Crear una nueva logica que mantenga las mismas reglas anti-colicion pero con multiplo de 5 para los tres filtros ejemplo los pickup time terminan en 10:15 , 1:25 y esta logica por defecto estara activada en setting y luego esta la opcion de hora impar ej 2:11 , 5:27 ect... }
- Encuentra pares de trips con gap entre `min_gap` y `max_gap` minutos
- Los mueve a su punto medio
- Solo aplica a trips del **mismo día** (`pick_up_date`)

### 3.4 Configuración de Expand

```python
class ExpandFilterConfig(BaseModel):
    """Configuración para Expand filter."""
    enabled: bool = False
    min_gap: int = Field(ge=1, le=60)    # ej: 21 min
    max_gap: int = Field(ge=1, le=120)   # ej: 30 min
    max_shift: int = Field(ge=1, le=30)  # max minutos de desplazamiento
    hotel_names: Optional[list[str]] = None
    time_range: Optional[TimeRange] = None
```

**Lógica:**
- Encuentra pares de trips con gap entre `min_gap` y `max_gap` minutos
- Distribuye: 1/3 hacia atrás (trip anterior), 2/3 hacia adelante (trip posterior)
- Solo aplica a trips del **mismo día** (`pick_up_date`)
- Respeta **No-Collision Rule** (ver sección 6.2)

### 3.5 TimeRange

```python
class TimeRange(BaseModel):
    """Rango de tiempo para filtrar trips por ventana horaria."""
    start: time  # ej: "05:00:00"
    end: time    # ej: "10:00:00"
```

**Soporte para cruces de medianoche:**
- Si `start > end` (ej: "22:00" - "02:00"), se interpreta como cruce de medianoche
- Lógica: `t >= start OR t <= end`

### 3.6 TripChange (Response)

```python
class TripChange(BaseModel):
    """Representa una modificación propuesta o aplicada."""
    trip_id: UUID
    original_time: time         # ej: "08:30:00"
    new_time: time              # ej: "08:00:00"
    filter_applied: str         # "reduce", "combine", "expand"
    hotel_name: str
    pick_up_date: Optional[str]
    airline: Optional[str]
```

### 3.7 FilterPreviewResult (Response)

```python
class FilterPreviewResult(BaseModel):
    """Resultado de simulación (preview) sin aplicar cambios."""
    location_id: UUID
    airline: str
    changes: list[TripChange]              # Cambios propuestos
    exclusions: list[FilterExclusion]      # Operaciones excluidas
    summary: dict                          # {"reduce": 10, "combine": 5, ...}
    total_trips_evaluated: int
    eligible_trips: int
```

### 3.8 FilterApplyResult (Response)

```python
class FilterApplyResult(BaseModel):
    """Resultado de aplicar filtros (persistido a DB)."""
    batch_id: UUID                         # Para revertir después
    location_id: UUID
    airline: str
    changes_applied: int
    exclusions: list[FilterExclusion]
    log: list[dict]                        # Log detallado
    summary: dict
```

### 3.9 FilterRevertResult (Response)

```python
class FilterRevertResult(BaseModel):
    """Resultado de revertir filtros."""
    trips_reverted: int
    batch_ids_reverted: list[UUID]
```

### 3.10 Columnas DB Agregadas al Schema Trip

**Tabla:** `trips.trips`

```sql
-- Columnas agregadas para filtros
original_pick_up_time  TIME              NULL,  -- Tiempo original antes del filtro
filter_applied         TEXT              NULL,  -- "reduce", "combine", "expand"
filter_batch_id        UUID              NULL,  -- ID del batch para revertir
filtered_at            TIMESTAMPTZ       NULL,  -- Cuándo se aplicó
```

---

## 4. Flujo Completo Paso a Paso

### 4.1 Fase 1: Preview (Simulación)

**Usuario:** Quiere ver los cambios **antes** de aplicarlos.

```
┌─────────────────────────────────────────────────────────┐
│ 1. Usuario configura filtros en UI                      │
│    - Selecciona mes/año: Octubre 2025                   │
│    - Configura Reduce: 30 minutos, 05:00-10:00         │
│    - Click "Preview"                                     │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 2. Frontend construye request                           │
│    - Calcula: pick_up_date_from = "2025-10-01"         │
│    - Calcula: pick_up_date_to = "2025-10-31"           │
│    - Construye FilterRequest con reduce config          │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 3. POST /filters/preview                                │
│    URL: /v1/locations/{id}/airlines/WN/trips/           │
│         filters/preview                                  │
│    Body: { pick_up_date_from, pick_up_date_to, reduce } │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 4. Backend: TripFilterService.preview()                │
│    a) Parse date_from y date_to                         │
│    b) Get eligible trips con SQL query                  │
│       - trip_type = 'outbound'                          │
│       - status = 'scheduled'                            │
│       - airline = 'WN'                                  │
│       - pick_up_date BETWEEN date_from AND date_to      │
│    c) _filter_by_options() - Filtrar por hotel/time    │
│    d) _apply_reduce() - Simular reduce                  │
│    e) _apply_combine() - Simular combine (si enabled)   │
│    f) _apply_expand() - Simular expand (si enabled)     │
│    g) Build summary: {"reduce": 342, "combine": 0}     │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 5. Backend retorna FilterPreviewResult                  │
│    {                                                     │
│      "location_id": "uuid...",                          │
│      "airline": "WN",                                   │
│      "changes": [                                        │
│        {                                                 │
│          "trip_id": "uuid-1",                           │
│          "original_time": "08:30:00",                   │
│          "new_time": "08:00:00",                        │
│          "filter_applied": "reduce",                    │
│          "hotel_name": "Hilton Downtown"                │
│        },                                                │
│        ...342 más                                        │
│      ],                                                  │
│      "summary": {"reduce": 342, "combine": 0},         │
│      "total_trips_evaluated": 688,                      │
│      "eligible_trips": 342                              │
│    }                                                     │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 6. Frontend muestra modal de preview                    │
│    - Tabla con cambios propuestos                       │
│    - Summary: "342 trips will be modified"             │
│    - Botones: "Cancel" / "Apply Changes"                │
└─────────────────────────────────────────────────────────┘
```

**⚠️ Importante:** En esta fase NO se modifica la base de datos. Es solo simulación.

---

### 4.2 Fase 2: Apply (Aplicar y Persistir)

**Usuario:** Confirma que quiere aplicar los cambios.

```
┌─────────────────────────────────────────────────────────┐
│ 1. Usuario hace click en "Apply Changes"               │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 2. POST /filters/apply                                  │
│    URL: /v1/locations/{id}/airlines/WN/trips/           │
│         filters/apply                                    │
│    Body: { MISMO que en preview }                       │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 3. Backend: TripFilterService.apply()                  │
│    a) Generate batch_id = uuid4()                       │
│    b) Get eligible trips (igual que preview)            │
│    c) Apply filters (igual que preview)                 │
│    d) ✅ PERSISTIR A DB:                               │
│       for each change:                                  │
│         - Save original_pick_up_time (si es la 1ra vez) │
│         - Update pick_up_time = new_time                │
│         - Set filter_applied = "reduce"                 │
│         - Set filter_batch_id = batch_id                │
│         - Set filtered_at = now()                       │
│         - session.add(trip)  # ✅ CRÍTICO               │
│       session.commit()                                  │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 4. Backend retorna FilterApplyResult                    │
│    {                                                     │
│      "batch_id": "90f7b8a8-1234-5678-...",             │
│      "location_id": "uuid...",                          │
│      "airline": "WN",                                   │
│      "changes_applied": 342,                            │
│      "summary": {"reduce": 342, "combine": 0},         │
│      "log": [...]                                        │
│    }                                                     │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 5. Frontend guarda batch_id en localStorage            │
│    - localStorage.setItem("last_batch_id", batch_id)   │
│    - Para poder revertir después                        │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 6. Frontend muestra toast                               │
│    ✅ "342 trips modified successfully"                │
│    Batch ID: 90f7b8a8...                                │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 7. Frontend refresca la tabla de trips                 │
│    - Llama onTripsUpdated()                             │
│    - GET /trips?airline=WN&date_from=2025-10-01&...   │
│    - Tabla ahora muestra pick_up_time MODIFICADOS      │
└─────────────────────────────────────────────────────────┘
```

**✅ Resultado:** Los cambios están ahora en la base de datos y visibles en la tabla.

---

### 4.3 Fase 3: Revert (Deshacer Cambios)

**Usuario:** Se arrepiente y quiere revertir los cambios.

```
┌─────────────────────────────────────────────────────────┐
│ 1. Usuario hace click en "Revert Changes"              │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 2. Frontend obtiene batch_id del localStorage          │
│    - batch_id = localStorage.getItem("last_batch_id")  │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 3. POST /filters/revert?batch_id={batch_id}           │
│    URL: /v1/locations/{id}/airlines/WN/trips/           │
│         filters/revert?batch_id=90f7b8a8...            │
│    Body: (vacío)                                        │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 4. Backend: TripFilterService.revert()                 │
│    a) Query trips con:                                  │
│       - location_id = {id}                              │
│       - airline = 'WN'                                  │
│       - filter_applied IS NOT NULL                      │
│       - original_pick_up_time IS NOT NULL               │
│       - filter_batch_id = {batch_id} (si se especificó) │
│    b) ✅ REVERTIR EN DB:                               │
│       for each trip:                                    │
│         - pick_up_time = original_pick_up_time          │
│         - original_pick_up_time = NULL                  │
│         - filter_applied = NULL                         │
│         - filter_batch_id = NULL                        │
│         - filtered_at = NULL                            │
│         - session.add(trip)  # ✅ CRÍTICO               │
│       session.commit()                                  │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 5. Backend retorna FilterRevertResult                   │
│    {                                                     │
│      "trips_reverted": 342,                             │
│      "batch_ids_reverted": ["90f7b8a8-..."]            │
│    }                                                     │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 6. Frontend limpia localStorage                         │
│    - localStorage.removeItem("last_batch_id")          │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 7. Frontend muestra toast                               │
│    ✅ "342 trips reverted successfully"                │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 8. Frontend refresca la tabla de trips                 │
│    - GET /trips?airline=WN&date_from=2025-10-01&...   │
│    - Tabla ahora muestra pick_up_time ORIGINALES       │
└─────────────────────────────────────────────────────────┘
```

**✅ Resultado:** Los trips vuelven a sus tiempos originales.

---

## 5. Lógica de Filtros Detallada

### 5.1 Reduce Filter (Lead Time Reduction)

**Objetivo:** Reducir el tiempo de anticipación entre el pickup y la hora del vuelo.

**Algoritmo:**

```python
def _apply_reduce(trips: list[Trip], config: ReduceFilterConfig):
    """
    Aplica Reduce a TODOS los trips elegibles.
    NO agrupa por día.
    """
    for trip in trips:
        # Rule A: Skip if already modified
        if trip.id in modified_trip_ids:
            continue

        # 1. Get original time
        original_time = trip.pick_up_time  # ej: 08:30:00

        # 2. Subtract minutes
        new_time = subtract_minutes(original_time, config.minutes_to_reduce)
        # Ejemplo: 08:30:00 - 30 min = 08:00:00

        # 3. Round to 5 minutes
        new_time = round_to_5_minutes(new_time)
        # Ejemplo: 08:02:00 → 08:00:00

        # 4. Record change
        record_change(trip, original_time, new_time, "reduce")

        # 5. Mark as modified (Rule A)
        modified_trip_ids.add(trip.id)
```

**Características:**
- ✅ Aplica a **todos** los trips del rango de fechas (no agrupa por día) para reduce no importa esto solo combine y expand 
- ✅ Respeta `hotel_names` (si se especifica)
- ✅ Respeta `time_range` (si se especifica)
- ✅ Redondea a múltiplos de 5 minutos - esto ya no sera asi depende de la nueva seleccion en setting 
- ✅ No puede reducir por debajo de 00:00:00 (se cicla a 23:55:00)

**Ejemplo:**

```
Trips ANTES del filtro:
- Trip 1: 08:30:00 (Hotel A)
- Trip 2: 09:15:00 (Hotel B)
- Trip 3: 10:00:00 (Hotel A)

Config: minutes_to_reduce = 30, hotel_names = null

Trips DESPUÉS del filtro:
- Trip 1: 08:00:00 ✅ (08:30 - 30 = 08:00)
- Trip 2: 08:45:00 ✅ (09:15 - 30 = 08:45)
- Trip 3: 09:30:00 ✅ (10:00 - 30 = 09:30)

Todos los trips fueron modificados (342 cambios)
```

---

### 5.2 Combine Filter (Contract)

**Objetivo:** Combinar dos trips cercanos moviéndolos a su punto medio, reduciendo el número de viajes.no los fuciona cada trips conserva sus propiedades solo cambia el pick up time


**Algoritmo:**

```python
def _apply_combine(trips: list[Trip], config: CombineFilterConfig):
    """
    Aplica Combine solo a pares de trips del MISMO día.
    Agrupa por pick_up_date.
    """
    # 1. Group trips by pick_up_date
    trips_by_date = defaultdict(list)
    for trip in trips:
        if trip.pick_up_date:
            trips_by_date[trip.pick_up_date].append(trip)

    # 2. Process each date separately
    for pick_up_date, day_trips in trips_by_date.items():
        # 3. Sort by pickup time
        sorted_trips = sorted(day_trips, key=lambda t: time_to_minutes(t.pick_up_time))

        # 4. Iterate through pairs
        i = 0
        while i < len(sorted_trips) - 1:
            trip_a = sorted_trips[i]
            trip_b = sorted_trips[i + 1]

            # Rule A: Skip if either already modified
            if trip_a.id in modified_trip_ids or trip_b.id in modified_trip_ids:
                i += 1
                continue

            # 5. Calculate gap
            gap = minutes_between(trip_a.pick_up_time, trip_b.pick_up_time)

            # 6. Check if gap is in range
            if config.min_gap <= gap <= config.max_gap:
                # 7. Calculate midpoint
                midpoint = calculate_midpoint(trip_a.pick_up_time, trip_b.pick_up_time)
                midpoint = round_to_5_minutes(midpoint)

                # 8. Record changes for BOTH trips
                record_change(trip_a, trip_a.pick_up_time, midpoint, "combine")
                record_change(trip_b, trip_b.pick_up_time, midpoint, "combine")

                # 9. Mark both as modified (Rule A)
                modified_trip_ids.add(trip_a.id)
                modified_trip_ids.add(trip_b.id)

                # 10. Skip both trips
                i += 2
            else:
                i += 1
```

**Características:**
- ✅ **Solo procesa trips del mismo día** (`pick_up_date`)
- ✅ Encuentra pares con gap en rango `[min_gap, max_gap]`
- ✅ Mueve ambos trips al punto medio
- ✅ Respeta Rule A (no modifica trips ya modificados)
- ✅ Redondea a múltiplos de 5 minutos

**Ejemplo:**

```
Día: 2025-10-05

Trips ANTES del filtro:
- Trip 1: 08:00:00
- Trip 2: 08:18:00  <- gap = 18 min
- Trip 3: 09:00:00

Config: min_gap = 15, max_gap = 20

Trips DESPUÉS del filtro:
- Trip 1: 08:10:00 ✅ (midpoint de 08:00 y 08:18)
- Trip 2: 08:10:00 ✅ (midpoint de 08:00 y 08:18)
- Trip 3: 09:00:00 (no modificado, gap = 42 min > max_gap)

2 trips fueron combinados en un solo pickup a las 08:10
```

---

### 5.3 Expand Filter (Separate)

**Objetivo:** Separar dos trips muy juntos para evitar congestión.

**Algoritmo:**

```python
def _apply_expand(trips: list[Trip], config: ExpandFilterConfig, combine_config: Optional[CombineFilterConfig]):
    """
    Aplica Expand solo a pares de trips del MISMO día.
    Respeta No-Collision Rule.
    """
    # 1. Group trips by pick_up_date
    trips_by_date = defaultdict(list)
    for trip in trips:
        if trip.pick_up_date:
            trips_by_date[trip.pick_up_date].append(trip)

    # 2. Process each date separately
    for pick_up_date, day_trips in trips_by_date.items():
        # 3. Sort by pickup time
        sorted_trips = sorted(day_trips, key=lambda t: time_to_minutes(t.pick_up_time))

        # 4. Iterate through pairs
        for i in range(len(sorted_trips) - 1):
            trip_a = sorted_trips[i]
            trip_b = sorted_trips[i + 1]

            # Rule A: Skip if either already modified
            if trip_a.id in modified_trip_ids or trip_b.id in modified_trip_ids:
                continue

            # 5. Calculate gap
            gap = minutes_between(trip_a.pick_up_time, trip_b.pick_up_time)

            # 6. Check if gap is in range
            if config.min_gap <= gap <= config.max_gap:
                # 7. Simulate expansion (1/3 backwards, 2/3 forwards)
                shift_a = config.max_shift // 3     # ej: 15 // 3 = 5 min
                shift_b = config.max_shift - shift_a # ej: 15 - 5 = 10 min

                new_time_a = subtract_minutes(trip_a.pick_up_time, shift_a)
                new_time_b = add_minutes(trip_b.pick_up_time, shift_b)

                new_time_a = round_to_5_minutes(new_time_a)
                new_time_b = round_to_5_minutes(new_time_b)

                # 8. No-Collision Rule (Rule B)
                if combine_config and combine_config.enabled:
                    collision = False

                    # Check gap with previous neighbor (i-1)
                    if i > 0:
                        prev_trip = sorted_trips[i - 1]
                        prev_time = get_effective_time(prev_trip)
                        gap_with_prev = minutes_between(prev_time, new_time_a)

                        if combine_config.min_gap <= gap_with_prev <= combine_config.max_gap:
                            record_exclusion("Collision with prev trip", gap_with_prev)
                            collision = True

                    # Check gap with next neighbor (i+2)
                    if not collision and i + 2 < len(sorted_trips):
                        next_trip = sorted_trips[i + 2]
                        next_time = get_effective_time(next_trip)
                        gap_with_next = minutes_between(new_time_b, next_time)

                        if combine_config.min_gap <= gap_with_next <= combine_config.max_gap:
                            record_exclusion("Collision with next trip", gap_with_next)
                            collision = True

                    if collision:
                        continue  # Skip this pair

                # 9. Apply expansion
                record_change(trip_a, trip_a.pick_up_time, new_time_a, "expand")
                record_change(trip_b, trip_b.pick_up_time, new_time_b, "expand")

                # 10. Mark both as modified (Rule A)
                modified_trip_ids.add(trip_a.id)
                modified_trip_ids.add(trip_b.id)
```

**Características:**
- ✅ **Solo procesa trips del mismo día** (`pick_up_date`)
- ✅ Encuentra pares con gap en rango `[min_gap, max_gap]`
- ✅ Distribución asimétrica: 1/3 atrás, 2/3 adelante
- ✅ Respeta Rule A y Rule B (No-Collision)
- ✅ Redondea a múltiplos de 5 minutos

**Ejemplo:**

```
Día: 2025-10-05

Trips ANTES del filtro:
- Trip 1: 08:00:00
- Trip 2: 08:25:00  <- gap = 25 min
- Trip 3: 09:00:00

Config: min_gap = 21, max_gap = 30, max_shift = 15

Trips DESPUÉS del filtro:
- Trip 1: 08:00:00 (no modificado)
- Trip 2: 08:20:00 ✅ (08:25 - 5 min)
- Trip 3: 08:35:00 ✅ (08:25 + 10 min)

Gap resultante: 08:20 → 08:35 = 15 min (fuera del rango de combine)
```

---

## 6. Reglas y Restricciones

### 6.1 Rule A: No Repeated Modifications

**Descripción:** Un trip modificado NO puede ser modificado nuevamente en la misma corrida.

**Implementación:**

```python
class TripFilterService:
    def __init__(self):
        self.modified_trip_ids: set[UUID] = set()

    def _apply_reduce(trips, config):
        for trip in trips:
            if trip.id in self.modified_trip_ids:
                continue  # Skip
            # ... apply reduce ...
            self.modified_trip_ids.add(trip.id)
```

**Ejemplo:**

```
Orden de ejecución: Reduce → Combine → Expand

1. Reduce modifica Trip 1: 08:30 → 08:00
   modified_trip_ids = {Trip 1}

2. Combine intenta modificar Trip 1 + Trip 2
   ❌ SKIP porque Trip 1 ya está en modified_trip_ids

3. Expand también skip Trip 1

Resultado: Trip 1 solo fue modificado por Reduce
```

---

### 6.2 Rule B: No-Collision Rule (Expand Only)

**Descripción:** Expand no debe crear gaps que caigan en el rango de Combine.

**Propósito:** Evitar que Expand cree situaciones donde Combine querría intervenir, causando conflictos.

**Implementación:**

```python
def _apply_expand(trips, expand_config, combine_config):
    # ... calcular new_time_a y new_time_b ...

    if combine_config and combine_config.enabled:
        # Check gap with previous trip
        gap_with_prev = minutes_between(prev_time, new_time_a)
        if combine_config.min_gap <= gap_with_prev <= combine_config.max_gap:
            # ❌ COLLISION: Skip this expansion
            record_exclusion("Would create combine-eligible gap with prev trip")
            continue

        # Check gap with next trip
        gap_with_next = minutes_between(new_time_b, next_time)
        if combine_config.min_gap <= gap_with_next <= combine_config.max_gap:
            # ❌ COLLISION: Skip this expansion
            record_exclusion("Would create combine-eligible gap with next trip")
            continue

    # ✅ Safe to expand
    apply_expansion()
```

**Ejemplo:**

```
Configuración:
- Combine: min_gap = 15, max_gap = 20
- Expand: min_gap = 21, max_gap = 30, max_shift = 15

Trips del día:
- Trip A: 07:45:00
- Trip B: 08:00:00
- Trip C: 08:25:00  <- candidato para expand
- Trip D: 08:50:00

Intentamos expandir Trip C y Trip D:
- new_time_c = 08:25 - 5 = 08:20
- new_time_d = 08:50 + 10 = 09:00

Verificamos colisión con Trip B:
- gap(Trip B → Trip C) = gap(08:00 → 08:20) = 20 min
- ❌ 20 min está en rango [15, 20] de Combine
- EXCLUSIÓN: "Collision with previous trip"

Resultado: Expansion NO se aplica para evitar conflicto
```

---

### 6.3 Redondeo a 5 Minutos

**Descripción:** Todos los tiempos resultantes se redondean al múltiplo de 5 más cercano.

**Implementación:**

```python
def round_to_5_minutes(t: time) -> time:
    total_minutes = t.hour * 60 + t.minute
    rounded = round(total_minutes / 5) * 5
    rounded = rounded % (24 * 60)  # Handle overflow
    return time(hour=rounded // 60, minute=rounded % 60, tzinfo=t.tzinfo)
```

**Ejemplos:**

```
08:32:00 → 08:30:00
08:33:00 → 08:35:00
08:37:30 → 08:40:00
23:58:00 → 00:00:00  (overflow)
```

---

### 6.4 Filtrado por Hotel y Time Range

**Descripción:** Los filtros pueden opcionalmente restringirse a:
- Hoteles específicos (`hotel_names`)
- Ventana horaria (`time_range`)

**Implementación:**

```python
def _filter_by_options(trips: list[Trip], config):
    result = trips

    # Filter by hotel names
    if config.hotel_names:
        hotel_set = set(h.lower() for h in config.hotel_names)
        result = [
            t for t in result
            if t.pick_up_location and t.pick_up_location.lower() in hotel_set
        ]

    # Filter by time range
    if config.time_range:
        result = [
            t for t in result
            if is_time_in_range(t.pick_up_time, config.time_range)
        ]

    return result

def is_time_in_range(t: time, time_range: TimeRange) -> bool:
    start = time_range.start
    end = time_range.end

    if start <= end:
        # Normal range: 05:00 - 10:00
        return start <= t <= end
    else:
        # Midnight crossing: 22:00 - 02:00
        return t >= start or t <= end
```

**Ejemplo:**

```
Configuración:
- hotel_names: ["Hilton Downtown", "Marriott Airport"]
- time_range: {"start": "05:00", "end": "10:00"}

Trips antes del filtrado:
1. 04:30 - Hilton Downtown     ❌ (fuera de time_range)
2. 08:00 - Hilton Downtown     ✅
3. 09:15 - Marriott Airport    ✅
4. 11:00 - Hilton Downtown     ❌ (fuera de time_range)
5. 08:30 - Holiday Inn         ❌ (hotel no en lista)

Solo los trips 2 y 3 serán procesados por el filtro
```

---

## 7. Persistencia y Base de Datos

### 7.1 Columnas Agregadas

**Tabla:** `trips.trips`

```sql
CREATE TABLE trips.trips (
    -- Columnas existentes
    id UUID PRIMARY KEY,
    location_id UUID NOT NULL,
    pick_up_date DATE NOT NULL,
    pick_up_time TIME WITH TIME ZONE NOT NULL,
    airline VARCHAR(10),
    trip_type VARCHAR(20),
    status VARCHAR(20),
    -- ... otras columnas ...

    -- ✅ Columnas agregadas para filtros (2026-01-17)
    original_pick_up_time TIME WITH TIME ZONE,  -- Backup del tiempo original
    filter_applied TEXT,                         -- "reduce", "combine", "expand"
    filter_batch_id UUID,                        -- Para revertir en batch
    filtered_at TIMESTAMP WITH TIME ZONE,        -- Timestamp de aplicación

    -- Índices
    INDEX idx_trips_filter_batch (filter_batch_id),
    INDEX idx_trips_filter_applied (filter_applied)
);
```

### 7.2 Query para Apply

**Paso 1: Get Eligible Trips**

```sql
SELECT *
FROM trips.trips
WHERE location_id = $1
  AND airline = $2
  AND trip_type = 'outbound'
  AND status = 'scheduled'
  AND pick_up_date >= $3  -- date_from
  AND pick_up_date <= $4  -- date_to
ORDER BY pick_up_date, pick_up_time;
```

**Paso 2: Update Trips (por cada change)**

```python
# En el servicio:
for change in self.changes:
    trip = trip_lookup.get(change.trip_id)
    if trip:
        # Save original if first time
        if trip.original_pick_up_time is None:
            trip.original_pick_up_time = trip.pick_up_time

        # Apply new time
        trip.pick_up_time = change.new_time
        trip.filter_applied = change.filter_applied
        trip.filter_batch_id = batch_id
        trip.filtered_at = datetime.utcnow()
        trip.updated_at = datetime.utcnow()

        # ✅ CRÍTICO: Add to session
        self.session.add(trip)

# Commit all changes
await self.session.commit()
```

**SQL generado por SQLAlchemy:**

```sql
UPDATE trips.trips
SET pick_up_time = $1,
    original_pick_up_time = $2,
    filter_applied = $3,
    filter_batch_id = $4,
    filtered_at = $5,
    updated_at = $6
WHERE id = $7;
```

### 7.3 Query para Revert

```sql
SELECT *
FROM trips.trips
WHERE location_id = $1
  AND airline = $2
  AND filter_applied IS NOT NULL
  AND original_pick_up_time IS NOT NULL
  AND filter_batch_id = $3  -- Optional: specific batch
```

**Update para revertir:**

```sql
UPDATE trips.trips
SET pick_up_time = original_pick_up_time,
    original_pick_up_time = NULL,
    filter_applied = NULL,
    filter_batch_id = NULL,
    filtered_at = NULL,
    updated_at = NOW()
WHERE id IN (...);
```

### 7.4 Transacciones

**Importante:** Todas las operaciones de apply y revert se ejecutan en una transacción.

```python
async def apply(...):
    try:
        # 1. Get trips
        trips = await self._get_eligible_trips(...)

        # 2. Apply filters (in memory)
        self._apply_reduce(...)
        self._apply_combine(...)
        self._apply_expand(...)

        # 3. Persist to DB
        for change in self.changes:
            # ... modificaciones ...
            self.session.add(trip)

        # ✅ Commit transaction
        await self.session.commit()

        return FilterApplyResult(...)

    except Exception as e:
        # ❌ Rollback on error
        await self.session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
```

**Ventajas:**
- ✅ Si algo falla, NO se persiste nada (atomicidad)
- ✅ No hay "estado intermedio" visible en la DB
- ✅ Rollback automático en caso de error

---

## 8. Endpoints API

### 8.1 POST /filters/preview

**URL:** `POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/preview`

**Path Parameters:**
- `location_id` (UUID): ID de la location
- `airline` (string): Código de aerolínea (ej: "WN", "AA")

**Request Body:**

```json
{
  "pick_up_date_from": "2025-10-01",
  "pick_up_date_to": "2025-10-31",
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 30,
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

**Response 200:**

```json
{
  "location_id": "dec0c23e-b1d5-4c44-adb4-18b9d4183cc9",
  "airline": "WN",
  "changes": [
    {
      "trip_id": "90759ad7-db9b-437a-98db-5322a6bf25c7",
      "original_time": "08:30:00",
      "new_time": "08:00:00",
      "filter_applied": "reduce",
      "hotel_name": "Hilton Downtown",
      "pick_up_date": "2025-10-05",
      "airline": "WN"
    }
    // ... más cambios
  ],
  "exclusions": [],
  "summary": {
    "reduce": 342,
    "combine": 0,
    "expand": 0,
    "excluded": 0
  },
  "total_trips_evaluated": 688,
  "eligible_trips": 342
}
```

**Errors:**
- `400 Bad Request`: ID de location inválido, configuración inválida
- `404 Not Found`: Location no encontrada
- `401 Unauthorized`: Token inválido

---

### 8.2 POST /filters/apply

**URL:** `POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/apply`

**Path Parameters:** (igual que preview)

**Request Body:** (MISMO que preview)

**Response 200:**

```json
{
  "batch_id": "90f7b8a8-1234-5678-9abc-def012345678",
  "location_id": "dec0c23e-b1d5-4c44-adb4-18b9d4183cc9",
  "airline": "WN",
  "changes_applied": 342,
  "exclusions": [],
  "log": [
    {
      "trip_id": "90759ad7-...",
      "action": "modified",
      "filter": "reduce",
      "original_time": "08:30:00",
      "new_time": "08:00:00",
      "hotel": "Hilton Downtown",
      "airline": "WN"
    }
    // ... más logs
  ],
  "summary": {
    "reduce": 342,
    "combine": 0,
    "expand": 0,
    "excluded": 0
  }
}
```

**Importante:**
- ✅ `batch_id` se debe guardar para poder revertir después
- ✅ Los cambios están ahora en la base de datos
- ✅ Los tiempos originales se guardaron en `original_pick_up_time`

**Errors:**
- `400 Bad Request`: Configuración inválida
- `404 Not Found`: Location no encontrada
- `401 Unauthorized`: Token inválido
- `500 Internal Server Error`: Error en DB commit

---

### 8.3 POST /filters/revert

**URL:** `POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/revert?batch_id={batch_id}`

**Path Parameters:**
- `location_id` (UUID): ID de la location
- `airline` (string): Código de aerolínea

**Query Parameters:**
- `batch_id` (UUID, opcional): ID del batch a revertir
  - Si se proporciona: Solo revierte trips de ese batch
  - Si NO se proporciona: Revierte TODOS los batches de la location+airline

**Request Body:** (vacío)

**Response 200:**

```json
{
  "trips_reverted": 342,
  "batch_ids_reverted": [
    "90f7b8a8-1234-5678-9abc-def012345678"
  ]
}
```

**Errors:**
- `400 Bad Request`: batch_id inválido
- `404 Not Found`: Location no encontrada
- `401 Unauthorized`: Token inválido

---

## 9. Ejemplos Concretos

### 9.1 Caso de Uso Real: Southwest Airlines en San Diego

**Contexto:**
- Location: San Diego (SDF)
- Airline: Southwest (WN)
- Mes: Octubre 2025
- Total trips outbound/scheduled: 688
- Problema: Tiempos de pickup muy anticipados (90+ minutos antes del vuelo)

**Objetivo:** Reducir lead time a 60 minutos para trips entre 05:00 y 10:00

**Configuración:**

```json
{
  "pick_up_date_from": "2025-10-01",
  "pick_up_date_to": "2025-10-31",
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 30,
    "hotel_names": null,
    "time_range": {
      "start": "05:00",
      "end": "10:00"
    }
  }
}
```

**Resultado:**

```
Total trips evaluados: 688
Trips elegibles (05:00-10:00): 342
Trips modificados: 342

Ejemplos:
- Trip 1: 05:30:00 → 05:00:00 ✅
- Trip 2: 06:15:00 → 05:45:00 ✅
- Trip 3: 08:30:00 → 08:00:00 ✅
- Trip 4: 11:00:00 → 11:00:00 (sin cambio, fuera de time_range)

Batch ID: 90f7b8a8-1234-5678-9abc-def012345678
```

**Impacto:**
- ✅ Reducción promedio de lead time: 90 min → 60 min
- ✅ Menos tiempo de espera para pasajeros
- ✅ Optimización de recursos de transporte
- ✅ Reversible con un click si se detectan problemas

---

### 9.2 Caso Complejo: Combine + Expand con Colisión

**Contexto:**
- Día: 2025-10-05
- Varios trips muy espaciados que podrían optimizarse

**Trips del día (ANTES):**

```
07:00:00 - Trip A
08:00:00 - Trip B
08:18:00 - Trip C  <- gap con B = 18 min (combine-eligible)
08:25:00 - Trip D  <- gap con C = 7 min (muy juntos)
09:00:00 - Trip E
```

**Configuración:**

```json
{
  "pick_up_date_from": "2025-10-05",
  "pick_up_date_to": "2025-10-05",
  "combine": {
    "enabled": true,
    "min_gap": 15,
    "max_gap": 20
  },
  "expand": {
    "enabled": true,
    "min_gap": 5,
    "max_gap": 10,
    "max_shift": 15
  }
}
```

**Proceso paso a paso:**

```
1️⃣ COMBINE ejecuta primero:
   - Analiza Trip B + Trip C: gap = 18 min ✅ (en rango [15,20])
   - Midpoint = (08:00 + 08:18) / 2 = 08:09
   - ✅ Trip B: 08:00 → 08:09
   - ✅ Trip C: 08:18 → 08:09
   - modified_trip_ids = {B, C}

2️⃣ EXPAND ejecuta después:
   - Analiza Trip C + Trip D:
     ❌ SKIP porque Trip C ya está en modified_trip_ids (Rule A)

   - Analiza Trip D + Trip E: gap = 35 min
     ❌ SKIP porque gap > max_gap (10)

3️⃣ RESULTADO FINAL:
   07:00:00 - Trip A (sin cambio)
   08:09:00 - Trip B ✅ (combinado)
   08:09:00 - Trip C ✅ (combinado)
   08:25:00 - Trip D (sin cambio, protegido por Rule A)
   09:00:00 - Trip E (sin cambio)

Summary:
- combine: 2
- expand: 0
- excluded: 0
```

**Observaciones:**
- ✅ Combine se ejecutó correctamente
- ✅ Expand no pudo procesar Trip C+D porque Trip C ya fue modificado (Rule A)
- ✅ No hubo colisiones porque Expand no se aplicó

---

### 9.3 Caso con No-Collision Rule

**Trips del día (ANTES):**

```
08:00:00 - Trip A
08:10:00 - Trip B
08:35:00 - Trip C  <- candidato para expand con D
09:05:00 - Trip D
```

**Configuración:**

```json
{
  "combine": {
    "enabled": true,
    "min_gap": 15,
    "max_gap": 20
  },
  "expand": {
    "enabled": true,
    "min_gap": 20,
    "max_gap": 40,
    "max_shift": 15
  }
}
```

**Análisis:**

```
EXPAND intenta procesar Trip C + Trip D:
- Gap actual: 30 min ✅ (en rango [20, 40])
- Expansion propuesta:
  - shift_a = 15 / 3 = 5 min
  - shift_b = 15 - 5 = 10 min
  - new_time_c = 08:35 - 5 = 08:30
  - new_time_d = 09:05 + 10 = 09:15

NO-COLLISION CHECK:
- Gap con Trip B: 08:10 → 08:30 = 20 min
- ❌ 20 min está en rango de Combine [15, 20]
- EXCLUSIÓN: "Collision with previous trip (20 min)"

RESULTADO:
- Expansion NO se aplica
- Trips C y D quedan sin modificar
- Se evita crear un gap que Combine querría procesar
```

---

## 10. Consideraciones Técnicas

### 10.1 Performance

**Queries Optimizadas:**

```sql
-- Índices recomendados:
CREATE INDEX idx_trips_outbound_scheduled
  ON trips.trips(location_id, airline, trip_type, status)
  WHERE trip_type = 'outbound' AND status = 'scheduled';

CREATE INDEX idx_trips_date_range
  ON trips.trips(pick_up_date);

CREATE INDEX idx_trips_filter_batch
  ON trips.trips(filter_batch_id)
  WHERE filter_batch_id IS NOT NULL;
```

**Estimación de tiempo:**
- 100 trips: < 100ms
- 500 trips: < 500ms
- 1000 trips: ~ 1 segundo
- 5000 trips: ~ 5 segundos

**Optimizaciones aplicadas:**
- ✅ Single query para get trips (no N+1)
- ✅ In-memory processing (no queries intermedias)
- ✅ Bulk update con session.add() + commit
- ✅ Índices en columnas de filtrado

---

### 10.2 Timezone Handling

**Importante:** Los `pick_up_time` se guardan con timezone en la base de datos.

```python
# En el trip model:
pick_up_time = Column(TIME(timezone=True))

# Al aplicar filtros:
new_time = time(hour=8, minute=0, tzinfo=trip.pick_up_time.tzinfo)
# Preserva el timezone original del trip
```

**Ejemplo:**

```
Trip en San Diego (PST/PDT):
- original_pick_up_time: 08:30:00-07:00
- new_time: 08:00:00-07:00

El timezone se preserva en todas las operaciones
```

---

### 10.3 Concurrency

**Problema:** ¿Qué pasa si dos usuarios aplican filtros al mismo tiempo?

**Solución:** Transacciones SQL + Optimistic Locking

```python
# PostgreSQL garantiza isolation por transacción:
async with session.begin():
    trips = await session.exec(...)  # Locks rows
    # ... modificaciones ...
    await session.commit()  # Release locks
```

**Escenario:**

```
Usuario A: Aplica filtro a las 10:00:00
Usuario B: Aplica filtro a las 10:00:01

PostgreSQL serializa las transacciones:
1. Usuario A lee trips (locks)
2. Usuario A modifica trips
3. Usuario A commit (release locks)
4. Usuario B lee trips (locks)
5. Usuario B modifica trips (con datos ya actualizados por A)
6. Usuario B commit
```

**Resultado:**
- ✅ No hay race conditions
- ✅ No se pierden datos
- ⚠️ El segundo usuario verá los cambios del primero

---

### 10.4 Logging

**Niveles de logging:**

```python
# INFO: Operaciones normales
logger.info(f"[FILTER] Eligible trips found: {total}")
logger.info(f"[FILTER] Changes applied: {len(self.changes)}")

# WARNING: Situaciones inusuales pero no errores
logger.warning(f"[FILTER] No eligible trips found for {airline}")

# ERROR: Errores que impiden la operación
logger.error(f"[FILTER] Failed to commit: {e}")
```

**Logs importantes:**

```python
# Al inicio de preview/apply
logger.info(f"[FILTER] Eligible trips found: {total_evaluated} for location={location_id}, airline={airline}")
logger.info(f"[FILTER] Config: reduce={config.reduce}, combine={config.combine}, expand={config.expand}")

# Después de aplicar cada filtro
logger.info(f"[FILTER] Reduce: {reduce_count} changes")
logger.info(f"[FILTER] Combine: {combine_count} changes")
logger.info(f"[FILTER] Expand: {expand_count} changes")

# Al finalizar
logger.info(f"[FILTER] Total changes applied: {len(self.changes)}, batch_id={batch_id}")
```

---

### 10.5 Error Handling

**Errores comunes y manejo:**

```python
# 1. Location no encontrada
if not location:
    raise HTTPException(status_code=404, detail="Location no encontrada")

# 2. Formato de fecha inválido
try:
    date_from = date.fromisoformat(config.pick_up_date_from)
except ValueError:
    raise HTTPException(status_code=400, detail="Formato de fecha inválido")

# 3. Error en commit
try:
    await self.session.commit()
except Exception as e:
    await self.session.rollback()
    logger.error(f"[FILTER] Commit failed: {e}")
    raise HTTPException(status_code=500, detail="Error al guardar cambios")

# 4. No hay trips elegibles
if not trips:
    # NO es un error, retornar resultado vacío
    return FilterApplyResult(
        batch_id=batch_id,
        changes_applied=0,
        summary={"reduce": 0, "combine": 0, "expand": 0}
    )
```

---

## 11. Diagramas de Flujo

### 11.1 Flujo de Apply Completo

```
START
  │
  ├─> Parse date_from y date_to
  │
  ├─> GET eligible trips de DB
  │     - trip_type = 'outbound'
  │     - status = 'scheduled'
  │     - location_id, airline
  │     - pick_up_date en rango
  │
  ├─> ¿Hay trips elegibles?
  │     NO ─> Return empty result
  │     YES ─> Continue
  │
  ├─> Build trip_lookup dictionary
  │
  ├─> ¿Reduce enabled?
  │     YES ─> _apply_reduce()
  │            - Filter by hotel/time_range
  │            - For each trip: subtract minutes
  │            - Round to 5 min
  │            - Record change
  │            - Add to modified_trip_ids
  │
  ├─> ¿Combine enabled?
  │     YES ─> _apply_combine()
  │            - Group by pick_up_date
  │            - For each date:
  │              - Sort by time
  │              - Find pairs with gap in [min, max]
  │              - Skip if already modified (Rule A)
  │              - Move to midpoint
  │              - Record changes
  │              - Add to modified_trip_ids
  │
  ├─> ¿Expand enabled?
  │     YES ─> _apply_expand()
  │            - Group by pick_up_date
  │            - For each date:
  │              - Sort by time
  │              - Find pairs with gap in [min, max]
  │              - Skip if already modified (Rule A)
  │              - Simulate expansion (1/3, 2/3)
  │              - Check No-Collision Rule (Rule B)
  │              - If collision: exclude, continue
  │              - Else: Record changes
  │              - Add to modified_trip_ids
  │
  ├─> PERSIST to DB:
  │     For each change:
  │       - Get trip from trip_lookup
  │       - Save original_pick_up_time (if first time)
  │       - Update pick_up_time = new_time
  │       - Set filter_applied, filter_batch_id, filtered_at
  │       - session.add(trip)  # ✅ CRÍTICO
  │     session.commit()
  │
  ├─> Build summary
  │
  └─> Return FilterApplyResult
        - batch_id
        - changes_applied
        - summary
        - log
END
```

---

### 11.2 Flujo de Combine (Detalle)

```
_apply_combine(trips, config)
  │
  ├─> Group trips by pick_up_date
  │     trips_by_date = {
  │       "2025-10-01": [trip1, trip2, ...],
  │       "2025-10-02": [trip5, trip6, ...],
  │       ...
  │     }
  │
  ├─> For each (date, day_trips):
  │     │
  │     ├─> Sort day_trips by pick_up_time
  │     │
  │     ├─> i = 0
  │     │
  │     ├─> While i < len(day_trips) - 1:
  │     │     │
  │     │     ├─> trip_a = day_trips[i]
  │     │     ├─> trip_b = day_trips[i+1]
  │     │     │
  │     │     ├─> ¿trip_a o trip_b ya modificado?
  │     │     │     YES ─> i += 1, continue
  │     │     │
  │     │     ├─> gap = minutes_between(trip_a, trip_b)
  │     │     │
  │     │     ├─> ¿min_gap <= gap <= max_gap?
  │     │     │     NO ─> i += 1, continue
  │     │     │     YES ─> Continue
  │     │     │
  │     │     ├─> midpoint = (time_a + time_b) / 2
  │     │     ├─> midpoint = round_to_5(midpoint)
  │     │     │
  │     │     ├─> record_change(trip_a, original, midpoint, "combine")
  │     │     ├─> record_change(trip_b, original, midpoint, "combine")
  │     │     │
  │     │     ├─> modified_trip_ids.add(trip_a.id)
  │     │     ├─> modified_trip_ids.add(trip_b.id)
  │     │     │
  │     │     └─> i += 2  # Skip both trips
  │     │
  │     └─> Next date
  │
  └─> Return
```

---

## 12. Troubleshooting

### 12.1 Problema: Filtros no se reflejan en la tabla

**Síntomas:**
- Backend responde `200 OK` con `changes_applied: 342`
- Pero la tabla del frontend no muestra cambios
- `revert` devuelve `trips_reverted: 0`

**Causa:** Faltaba `session.add(trip)` antes del commit

**Solución:** ✅ Ya corregido en versión 1.0 (2026-01-17)

**Verificación:**

```sql
-- Verificar que trips tienen filtros aplicados:
SELECT COUNT(*)
FROM trips.trips
WHERE filter_applied IS NOT NULL;

-- Resultado esperado: > 0 después de apply
```

---

### 12.2 Problema: Combine/Expand modifican trips de días diferentes

**Síntomas:**
- Combine junta un trip del día 5 con un trip del día 6
- Lógica de negocio incorrecta

**Causa:** No agrupaba por `pick_up_date`

**Solución:** ✅ Ya corregido en versión 1.0

```python
# Ahora agrupa por fecha:
trips_by_date = defaultdict(list)
for trip in trips:
    if trip.pick_up_date:
        trips_by_date[trip.pick_up_date].append(trip)

# Procesa cada fecha por separado
for pick_up_date, day_trips in trips_by_date.items():
    # ... lógica de combine/expand ...
```

---

### 12.3 Problema: Backend modifica trips de todos los meses

**Síntomas:**
- Usuario aplica filtro a octubre
- Backend modifica trips de enero, febrero, etc.

**Causa:** Backend no recibía `pick_up_date_from` y `pick_up_date_to`

**Solución:** ✅ Ya corregido en versión 1.0

```python
# Ahora filtra por fecha:
if date_from:
    query = query.Where(Trip.pick_up_date >= date_from)
if date_to:
    query = query.Where(Trip.pick_up_date <= date_to)
```

**Frontend debe enviar:**

```json
{
  "pick_up_date_from": "2025-10-01",
  "pick_up_date_to": "2025-10-31",
  "reduce": { ... }
}
```

---

### 12.4 Problema: Timezone incorrecto en resultados

**Síntomas:**
- Tiempos aparecen con timezone incorrecto
- Conversiones erróneas UTC vs local

**Causa:** No preservar `tzinfo` al crear nuevos times

**Solución:**

```python
# ✅ Correcto:
new_time = time(hour=8, minute=0, tzinfo=trip.pick_up_time.tzinfo)

# ❌ Incorrecto:
new_time = time(hour=8, minute=0)  # No timezone
```

---

### 12.5 Problema: Performance lento con muchos trips

**Síntomas:**
- Requests tardan > 5 segundos con 5000+ trips

**Soluciones:**

```sql
-- 1. Verificar índices existen:
SELECT indexname, tablename
FROM pg_indexes
WHERE tablename = 'trips'
  AND schemaname = 'trips';

-- 2. Crear índices si faltan:
CREATE INDEX IF NOT EXISTS idx_trips_outbound_scheduled
  ON trips.trips(location_id, airline, trip_type, status)
  WHERE trip_type = 'outbound' AND status = 'scheduled';

-- 3. Analizar plan de query:
EXPLAIN ANALYZE
SELECT * FROM trips.trips
WHERE location_id = 'uuid'
  AND airline = 'WN'
  AND trip_type = 'outbound'
  AND status = 'scheduled'
  AND pick_up_date BETWEEN '2025-10-01' AND '2025-10-31';
```

---

## 13. Changelog

### Versión 1.0 (2026-01-17)

**Agregado:**
- ✅ Campos `pick_up_date_from` y `pick_up_date_to` en `FilterRequest`
- ✅ Filtrado por rango de fechas en `_get_eligible_trips()`
- ✅ Agrupación por `pick_up_date` en Combine y Expand
- ✅ `session.add(trip)` en `apply()` y `revert()`
- ✅ Columnas DB: `original_pick_up_time`, `filter_applied`, `filter_batch_id`, `filtered_at`

**Corregido:**
- ✅ Filtros ahora persisten correctamente en DB
- ✅ Revert funciona correctamente
- ✅ Combine/Expand solo operan en trips del mismo día
- ✅ Backend filtra por mes correctamente

**Deprecated:**
- ❌ Campo `target_date` (nunca fue implementado en backend)

---

## 14. Referencias

**Archivos de código:**
- [features/trips/routes/trips_router.py](../features/trips/routes/trips_router.py)
- [features/trips/services/trip_filter_service.py](../features/trips/services/trip_filter_service.py)
- [features/trips/models/filter_models.py](../features/trips/models/filter_models.py)

**Documentación relacionada:**
- [FRONTEND_FILTERS_IMPLEMENTATION_FOR_BACKEND.md](FRONTEND_FILTERS_IMPLEMENTATION_FOR_BACKEND.md)
- [BACKEND_ARCHITECTURE_AND_WORKFLOW.md](BACKEND_ARCHITECTURE_AND_WORKFLOW.md)

---

**Fin del documento**
**Última actualización:** 2026-01-17
**Autor:** Backend Team GT360
