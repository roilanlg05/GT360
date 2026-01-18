# Ground Filters - Complete Workflow Documentation V2

**Fecha:** 2026-01-17
**Versión:** 2.0 - Nueva Implementación con Prioridad de Reduce
**Autor:** Backend Team
**Estado:** ✅ Implementado y en Producción

---

## 📋 Tabla de Contenidos

1. [Visión General](#1-visión-general)
2. [Arquitectura del Sistema](#2-arquitectura-del-sistema)
3. [Modelos de Datos](#3-modelos-de-datos)
4. [Sistema de Prioridades](#4-sistema-de-prioridades)
5. [Lógica de Filtros Detallada](#5-lógica-de-filtros-detallada)
6. [Reglas y Restricciones](#6-reglas-y-restricciones)
7. [Redondeo Configurable](#7-redondeo-configurable)
8. [Persistencia y Base de Datos](#8-persistencia-y-base-de-datos)
9. [Endpoints API](#9-endpoints-api)
10. [Ejemplos Concretos](#10-ejemplos-concretos)
11. [Guía de Implementación Frontend](#11-guía-de-implementación-frontend)
12. [Testing y Verificación](#12-testing-y-verificación)

---

## 1. Visión General

### 1.1 Propósito

Los **Ground Filters** permiten ajustar automáticamente los tiempos de pickup (`pick_up_time`) de trips outbound para optimizar la logística de transporte terrestre en aeropuertos.

### 1.2 Tipos de Filtros

| Filtro | Prioridad | Objetivo | Scope | Agrupación |
|--------|-----------|----------|-------|------------|
| **Reduce** | 0 | Reducir tiempos de anticipación (lead time) | Global | ❌ NO agrupa por día |
| **Combine** | 1 | Combinar trips cercanos en un solo pickup | Por Día | ✅ SÍ agrupa por `pick_up_date` |
| **Expand** | 1 | Separar trips muy juntos | Por Día | ✅ SÍ agrupa por `pick_up_date` |

### 1.3 Características Clave - Nueva Implementación

#### ✅ Reduce (Prioridad 0)
- **Siempre** opera sobre `original_pick_up_time`, NO sobre tiempos modificados
- Cuando Reduce cambia, Combine/Expand **se re-aplican automáticamente** sobre los nuevos tiempos reducidos
- **NO** está sujeto a Rule A (no bloquea que Combine/Expand modifiquen el mismo trip)
- **NO** genera colisiones, por lo que está excluido de reglas anti-colisión
- Aplica a **todos** los trips del rango de fechas sin agrupar por día

**Ejemplo:**
```
Original: Trip A = 02:00, Trip B = 02:30

Paso 1: Reduce OFF, Combine activo
  → Combine: 02:00 y 02:30 → 02:15 (midpoint)

Paso 2: Se activa Reduce -20 minutos
  → Reduce opera sobre ORIGINALES: 02:00-20=01:40, 02:30-20=02:10
  → Combine RE-APLICA sobre REDUCIDOS: 01:40 y 02:10 → 01:55 ✅
```

#### ✅ Combine (Prioridad 1)
- Opera sobre tiempos **efectivos** (con Reduce ya aplicado si existe)
- **NO fusiona** trips, solo cambia su `pick_up_time`
- Cada trip conserva sus propiedades únicas
- Solo aplica a trips del **mismo día** (`pick_up_date`)
- Sujeto a Rule A

#### ✅ Expand (Prioridad 1)
- Opera sobre tiempos **efectivos** (con Reduce ya aplicado si existe)
- Solo aplica a trips del **mismo día** (`pick_up_date`)
- Sujeto a Rule A y Rule B (No-Collision)

### 1.4 Criterios de Elegibilidad

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
```python
❌ trip_type = 'inbound' o 'flight'
❌ status = 'completed', 'cancelled', 'en_route', etc.
❌ Otras airlines
❌ Fuera del rango de fechas
```

---

## 2. Arquitectura del Sistema

### 2.1 Capas de la Aplicación

```
┌─────────────────────────────────────────────────────┐
│                   FRONTEND                          │
│  (React + TypeScript + use-trip-filters.ts)        │
│  - Configuración de filtros                        │
│  - Selección de rounding_mode                      │
│  - Preview y Apply                                  │
└─────────────────────────────────────────────────────┘
                        ↓ HTTP/REST
┌─────────────────────────────────────────────────────┐
│                API LAYER (FastAPI)                  │
│  - trips_router.py                                  │
│  - Endpoints: /preview, /apply, /revert            │
│  - Validación de FilterRequest                     │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│              SERVICE LAYER                          │
│  - TripFilterService (trip_filter_service.py)      │
│  - Sistema de Prioridades (Reduce = 0, C/E = 1)   │
│  - Tracking separado: modified_by_combine_expand   │
│  - _get_effective_time(): Retorna tiempos con     │
│    Reduce aplicado                                  │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│              DATA MODELS                            │
│  - filter_models.py (Pydantic)                      │
│  - RoundingMode enum                                │
│  - FilterRequest con rounding_mode                  │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│            DATABASE LAYER (PostgreSQL)              │
│  - Table: trips.trips                               │
│  - Columns: pick_up_time, original_pick_up_time,   │
│             filter_applied, filter_batch_id, etc.   │
│  - original_pick_up_time NUNCA cambia              │
└─────────────────────────────────────────────────────┘
```

### 2.2 Archivos Principales

```
backend/
├── features/trips/
│   ├── routes/
│   │   └── trips_router.py           # Endpoints API
│   ├── services/
│   │   └── trip_filter_service.py    # ⚡ Lógica actualizada con prioridades
│   ├── models/
│   │   └── filter_models.py          # ⚡ Nuevo: RoundingMode enum
│   └── utils/
│       └── ...
├── shared/db/schemas/trips/
│   └── trips.py                       # Modelo SQLAlchemy
└── docs/
    ├── GROUND_FILTERS_COMPLETE_WORKFLOW_V2.md  # 📄 Este documento
    └── FRONTEND_FILTERS_IMPLEMENTATION_FOR_BACKEND.md
```

---

## 3. Modelos de Datos

### 3.1 RoundingMode (Enum) - ⚡ NUEVO

```python
from enum import Enum

class RoundingMode(str, Enum):
    """Rounding mode for time calculations."""
    MULTIPLE_OF_5 = "multiple_of_5"  # Redondea a múltiplos de 5: 10:15, 1:25 (default)
    ODD_MINUTES = "odd_minutes"      # Sin redondeo: 2:11, 5:27
```

**Uso:**
- `MULTIPLE_OF_5`: Comportamiento actual, compatible backwards
- `ODD_MINUTES`: Para operaciones que requieren precisión exacta

### 3.2 FilterRequest (Request Body) - ⚡ ACTUALIZADO

```python
class FilterRequest(BaseModel):
    """Request model for applying filters."""
    pick_up_date_from: Optional[str] = None  # "YYYY-MM-DD"
    pick_up_date_to: Optional[str] = None    # "YYYY-MM-DD"
    rounding_mode: RoundingMode = RoundingMode.MULTIPLE_OF_5  # ⚡ NUEVO
    reduce: Optional[ReduceFilterConfig] = None
    combine: Optional[CombineFilterConfig] = None
    expand: Optional[ExpandFilterConfig] = None
```

**Ejemplo Request:**
```json
{
  "pick_up_date_from": "2025-10-01",
  "pick_up_date_to": "2025-10-31",
  "rounding_mode": "multiple_of_5",
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 20,
    "hotel_names": null,
    "time_range": null
  },
  "combine": {
    "enabled": true,
    "min_gap": 15,
    "max_gap": 30,
    "hotel_names": null,
    "time_range": null
  }
}
```

### 3.3 ReduceFilterConfig

```python
class ReduceFilterConfig(BaseModel):
    """Configuración para Lead Time Reduction filter."""
    enabled: bool = False
    minutes_to_reduce: int = Field(default=0, ge=0, le=120)
    hotel_names: Optional[list[str]] = None  # None = ALL
    time_range: Optional[TimeRange] = None   # None = ALL
```

**Parámetros:**
- `minutes_to_reduce`: Minutos a restar (0-120)
- `hotel_names`: Lista de hoteles. Si es `null`, aplica a TODOS.
- `time_range`: Rango de horas (ej: "05:00" - "10:00"). Si es `null`, aplica a TODAS.

### 3.4 CombineFilterConfig

```python
class CombineFilterConfig(BaseModel):
    """Configuración para Combine (contract) filter."""
    enabled: bool = False
    min_gap: int = Field(ge=1, le=60)   # ej: 15 min
    max_gap: int = Field(ge=1, le=120)  # ej: 30 min
    hotel_names: Optional[list[str]] = None
    time_range: Optional[TimeRange] = None
```

**Lógica:**
- Encuentra pares de trips con gap entre `min_gap` y `max_gap` minutos
- Los mueve a su punto medio
- Solo aplica a trips del **mismo día** (`pick_up_date`)
- Opera sobre tiempos **efectivos** (con Reduce aplicado si existe)

### 3.5 ExpandFilterConfig

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
- Respeta **No-Collision Rule** (Rule B)
- Opera sobre tiempos **efectivos** (con Reduce aplicado si existe)

### 3.6 TripChange (Response)

```python
class TripChange(BaseModel):
    """Represents a single trip modification."""
    trip_id: UUID
    original_time: time       # Tiempo antes del cambio (puede ser ya reducido)
    new_time: time           # Tiempo después del cambio
    filter_applied: str      # "reduce", "combine", "expand"
    hotel_name: str
    pick_up_date: Optional[str] = None
    airline: Optional[str] = None
```

### 3.7 FilterPreviewResult (Response)

```python
class FilterPreviewResult(BaseModel):
    """Result of filter preview (simulation without applying)."""
    location_id: UUID
    airline: str
    changes: list[TripChange]
    exclusions: list[FilterExclusion]
    summary: dict  # {"reduce": 5, "combine": 10, "expand": 3, "excluded": 2}
    total_trips_evaluated: int
    eligible_trips: int
```

### 3.8 FilterApplyResult (Response)

```python
class FilterApplyResult(BaseModel):
    """Result of applying filters."""
    batch_id: UUID              # ID único para revertir cambios
    location_id: UUID
    airline: str
    changes_applied: int
    exclusions: list[FilterExclusion]
    log: list[dict]
    summary: dict
```

---

## 4. Sistema de Prioridades

### 4.1 Orden de Ejecución

```
┌─────────────────────────────────────┐
│  1. Reduce (Prioridad 0)            │
│     - Opera sobre original_pick_up_time │
│     - NO está sujeto a Rule A       │
│     - NO bloquea Combine/Expand     │
└─────────────────────────────────────┘
            ↓
┌─────────────────────────────────────┐
│  2. Combine (Prioridad 1)           │
│     - Opera sobre tiempos efectivos │
│       (con Reduce aplicado)         │
│     - Sujeto a Rule A               │
└─────────────────────────────────────┘
            ↓
┌─────────────────────────────────────┐
│  3. Expand (Prioridad 1)            │
│     - Opera sobre tiempos efectivos │
│     - Sujeto a Rule A y Rule B      │
└─────────────────────────────────────┘
```

### 4.2 Cómo Funciona la Prioridad de Reduce

#### Escenario 1: Reduce OFF, luego se activa

```
Estado Inicial:
  Trip A: original = 02:00
  Trip B: original = 02:30

Paso 1: Reduce OFF (0 min), Combine activo
  ✅ Combine ve: 02:00 y 02:30 → 02:15 (midpoint)
  DB: Trip A.pick_up_time = 02:15
      Trip B.pick_up_time = 02:15

Paso 2: Usuario activa Reduce = 20 min
  ✅ Reduce opera sobre ORIGINALES:
     02:00 - 20 = 01:40
     02:30 - 20 = 02:10

  ✅ Combine RE-APLICA sobre NUEVOS REDUCIDOS:
     01:40 y 02:10 → 01:55 (midpoint)

  DB: Trip A.pick_up_time = 01:55  ← Combine aplicado sobre reducidos
      Trip B.pick_up_time = 01:55
      Trip A.original_pick_up_time = 02:00  ← NUNCA cambia
      Trip B.original_pick_up_time = 02:30  ← NUNCA cambia
```

#### Escenario 2: Cambio de configuración de Reduce

```
Estado Actual:
  Trip A: original = 08:00, pick_up_time = 07:40 (Reduce -20)
  Trip B: original = 08:30, pick_up_time = 08:10 (Reduce -20)

Usuario cambia Reduce de -20 a -30:
  ✅ Reduce recalcula desde ORIGINALES:
     08:00 - 30 = 07:30
     08:30 - 30 = 08:00

  ✅ Combine RE-APLICA:
     07:30 y 08:00 → 07:45 (midpoint)

  DB: Trip A.pick_up_time = 07:45
      Trip B.pick_up_time = 07:45
      Trip A.original_pick_up_time = 08:00  ← NUNCA cambia
```

### 4.3 Tracking Separado

```python
# En TripFilterService:
self.modified_by_combine_expand: set[UUID] = set()  # ⚡ NUEVO

def _apply_reduce(...):
    # ...
    # ❌ NO agregar a modified_by_combine_expand
    # Reduce NO bloquea Combine/Expand

def _apply_combine(...):
    # ...
    if trip.id in self.modified_by_combine_expand:  # ⚡ Usa el nuevo set
        continue  # Rule A: skip if already modified by Combine/Expand
    # ...
    self.modified_by_combine_expand.add(trip.id)  # ⚡ Agregar al nuevo set

def _apply_expand(...):
    # Similar a combine
```

---

## 5. Lógica de Filtros Detallada

### 5.1 Reduce Filter - ⚡ ACTUALIZADO

**Objetivo:** Reducir tiempos de anticipación (lead time) restando minutos del `original_pick_up_time`.

**Algoritmo:**

```python
def _apply_reduce(trips: list[Trip], config: ReduceFilterConfig):
    """
    Priority 0: Always operates on original_pick_up_time.
    Does NOT block Combine/Expand.
    """
    for trip in trips:
        # ⚡ Usar original_pick_up_time si existe, sino pick_up_time
        base_time = trip.original_pick_up_time if trip.original_pick_up_time else trip.pick_up_time

        # Restar minutos
        new_time = base_time - timedelta(minutes=config.minutes_to_reduce)

        # Redondear según configuración
        new_time = round_time(new_time, rounding_mode)

        # Registrar cambio
        record_change(trip, base_time, new_time, "reduce")

        # ⚡ NO agregar a modified_by_combine_expand
        # Reduce NO bloquea Combine/Expand
```

**Características:**
- ✅ Aplica a **todos** los trips del rango de fechas (no agrupa por día)
- ✅ Respeta `hotel_names` (si se especifica)
- ✅ Respeta `time_range` (si se especifica)
- ✅ Redondea según `rounding_mode` configurado
- ✅ No puede reducir por debajo de 00:00:00 (se cicla a 23:55:00 o 23:59:00)
- ✅ **NO** está sujeto a Rule A
- ✅ **NO** genera colisiones

**Ejemplo:**

```
Trips ANTES de Reduce:
- Trip 1: original = 08:30:00, pick_up_time = 08:30:00
- Trip 2: original = 09:15:00, pick_up_time = 09:15:00

Config: Reduce -30 min

Trips DESPUÉS de Reduce:
- Trip 1: original = 08:30:00, pick_up_time = 08:00:00 ✅
- Trip 2: original = 09:15:00, pick_up_time = 08:45:00 ✅
```

### 5.2 Combine Filter (Contract) - ⚡ ACTUALIZADO

**Objetivo:** Combinar dos trips cercanos moviéndolos a su punto medio. **NO fusiona trips**, solo cambia el `pick_up_time`.

**Algoritmo:**

```python
def _apply_combine(trips: list[Trip], config: CombineFilterConfig):
    """
    Priority 1: Operates AFTER Reduce (uses effective times).
    Subject to Rule A.
    """
    # ⚡ Agrupar por pick_up_date
    trips_by_date = defaultdict(list)
    for trip in trips:
        trips_by_date[trip.pick_up_date].append(trip)

    # Procesar cada día por separado
    for pick_up_date, day_trips in trips_by_date.items():
        # ⚡ Ordenar por tiempo EFECTIVO (con Reduce aplicado)
        sorted_trips = sorted(day_trips, key=lambda t: get_effective_time(t))

        i = 0
        while i < len(sorted_trips) - 1:
            trip_a = sorted_trips[i]
            trip_b = sorted_trips[i + 1]

            # ⚡ Rule A: Skip si ya fue modificado por Combine/Expand
            if trip_a.id in modified_by_combine_expand or trip_b.id in modified_by_combine_expand:
                i += 1
                continue

            # ⚡ Obtener tiempos EFECTIVOS (con Reduce aplicado)
            time_a = get_effective_time(trip_a)
            time_b = get_effective_time(trip_b)

            gap = minutes_between(time_a, time_b)

            if config.min_gap <= gap <= config.max_gap:
                # Calcular punto medio
                midpoint = (time_a + time_b) / 2
                midpoint = round_time(midpoint, rounding_mode)

                # Registrar cambios usando tiempos efectivos como "original"
                record_change(trip_a, time_a, midpoint, "combine")
                record_change(trip_b, time_b, midpoint, "combine")

                # ⚡ Marcar como modificados por Combine
                modified_by_combine_expand.add(trip_a.id)
                modified_by_combine_expand.add(trip_b.id)

                i += 2  # Skip both
            else:
                i += 1
```

**Características:**
- ✅ Solo aplica a trips del **mismo día** (`pick_up_date`)
- ✅ Opera sobre tiempos **efectivos** (con Reduce aplicado)
- ✅ Respeta `hotel_names` y `time_range`
- ✅ Sujeto a Rule A (no modifica trips ya modificados por Combine/Expand)
- ✅ **NO fusiona** trips, solo cambia `pick_up_time`

**Ejemplo:**

```
Día 2025-10-01:
  Trip A: original = 08:00, effective = 07:40 (Reduce -20 aplicado)
  Trip B: original = 08:30, effective = 08:10 (Reduce -20 aplicado)
  Gap: 30 minutos

Config: Combine min_gap=15, max_gap=45

Resultado:
  Midpoint = (07:40 + 08:10) / 2 = 07:55

  Trip A: pick_up_time = 07:55 ✅
  Trip B: pick_up_time = 07:55 ✅
```

### 5.3 Expand Filter - ⚡ ACTUALIZADO

**Objetivo:** Separar dos trips que están muy juntos, respetando No-Collision Rule.

**Algoritmo:**

```python
def _apply_expand(trips: list[Trip], config: ExpandFilterConfig, combine_config):
    """
    Priority 1: Operates AFTER Reduce.
    Subject to Rule A and Rule B (No-Collision).
    """
    # Agrupar por pick_up_date
    trips_by_date = defaultdict(list)
    for trip in trips:
        trips_by_date[trip.pick_up_date].append(trip)

    for pick_up_date, day_trips in trips_by_date.items():
        # ⚡ Ordenar por tiempo EFECTIVO
        sorted_trips = sorted(day_trips, key=lambda t: get_effective_time(t))

        for i in range(len(sorted_trips) - 1):
            trip_a = sorted_trips[i]
            trip_b = sorted_trips[i + 1]

            # ⚡ Rule A
            if trip_a.id in modified_by_combine_expand or trip_b.id in modified_by_combine_expand:
                continue

            # ⚡ Obtener tiempos EFECTIVOS
            time_a = get_effective_time(trip_a)
            time_b = get_effective_time(trip_b)

            gap = minutes_between(time_a, time_b)

            if config.min_gap <= gap <= config.max_gap:
                # Simular expansión (1/3 atrás, 2/3 adelante)
                shift_a = config.max_shift // 3
                shift_b = config.max_shift - shift_a

                new_time_a = time_a - shift_a
                new_time_b = time_b + shift_b

                # ⚡ Rule B: No-Collision Rule
                if combine_config and combine_config.enabled:
                    # Verificar colisión con vecino anterior
                    if i > 0:
                        prev_time = get_effective_time(sorted_trips[i-1])
                        gap_with_prev = minutes_between(prev_time, new_time_a)
                        if combine_config.min_gap <= gap_with_prev <= combine_config.max_gap:
                            record_exclusion("Collision with previous trip")
                            continue

                    # Verificar colisión con vecino siguiente
                    if i + 2 < len(sorted_trips):
                        next_time = get_effective_time(sorted_trips[i+2])
                        gap_with_next = minutes_between(new_time_b, next_time)
                        if combine_config.min_gap <= gap_with_next <= combine_config.max_gap:
                            record_exclusion("Collision with next trip")
                            continue

                # Aplicar expansión
                record_change(trip_a, time_a, new_time_a, "expand")
                record_change(trip_b, time_b, new_time_b, "expand")

                modified_by_combine_expand.add(trip_a.id)
                modified_by_combine_expand.add(trip_b.id)
```

**Características:**
- ✅ Solo aplica a trips del **mismo día**
- ✅ Opera sobre tiempos **efectivos**
- ✅ Distribución: 1/3 atrás, 2/3 adelante
- ✅ Respeta No-Collision Rule (Rule B)

---

## 6. Reglas y Restricciones

### 6.1 Rule A: No Repeated Modifications - ⚡ ACTUALIZADO

**Regla:** Un trip modificado por **Combine o Expand** NO puede ser modificado nuevamente por **Combine o Expand** en la misma ejecución.

**⚡ IMPORTANTE:** Esta regla **NO** aplica a Reduce. Reduce puede modificar trips que luego serán modificados por Combine/Expand.

**Implementación:**
```python
# Tracking separado
self.modified_by_combine_expand: set[UUID] = set()

# En Combine/Expand:
if trip.id in self.modified_by_combine_expand:
    continue  # Skip este trip

# En Reduce:
# NO agregar a modified_by_combine_expand
```

**Ejemplo:**
```
Trips A y B:
1. Reduce modifica ambos: A y B → OK ✅
2. Combine modifica ambos: A y B → OK ✅
3. Expand intenta modificar A → ❌ BLOQUEADO por Rule A
```

### 6.2 Rule B: No-Collision Rule

**Regla:** Expand NO debe crear gaps que caigan en el rango de Combine.

**Verificación:**
```python
# Antes de aplicar Expand, verificar:
gap_with_prev = minutes_between(prev_trip, new_time_a)
gap_with_next = minutes_between(new_time_b, next_trip)

if combine_min <= gap_with_prev <= combine_max:
    # ❌ Colisión detectada, excluir operación
    record_exclusion("Collision with previous trip")
```

---

## 7. Redondeo Configurable - ⚡ NUEVO

### 7.1 Modos de Redondeo

#### Modo 1: MULTIPLE_OF_5 (Default)

```python
rounding_mode: "multiple_of_5"
```

**Comportamiento:**
- Redondea al múltiplo de 5 más cercano
- `08:13` → `08:15`
- `08:17` → `08:15`
- `08:18` → `08:20`

**Ejemplo:**
```
Input: 02:11
Rounded: 02:10

Input: 02:13
Rounded: 02:15
```

#### Modo 2: ODD_MINUTES

```python
rounding_mode: "odd_minutes"
```

**Comportamiento:**
- **NO redondea**, mantiene minutos exactos
- `08:13` → `08:13`
- `08:17` → `08:17`
- `02:11` → `02:11`

**Uso:** Cuando se requiere precisión exacta sin redondeo.

### 7.2 Implementación

```python
def _round_time(self, t: time) -> time:
    """Round time based on configured rounding mode."""
    if self.rounding_mode == RoundingMode.MULTIPLE_OF_5:
        return self._round_to_5_minutes(t)
    elif self.rounding_mode == RoundingMode.ODD_MINUTES:
        return t  # Sin redondeo
    else:
        return self._round_to_5_minutes(t)  # Default
```

### 7.3 Configuración desde Frontend

```typescript
const filterRequest: FilterRequest = {
  rounding_mode: "multiple_of_5",  // o "odd_minutes"
  reduce: { ... },
  combine: { ... },
  expand: { ... }
}
```

---

## 8. Persistencia y Base de Datos

### 8.1 Columnas de la Tabla `trips.trips`

```sql
-- Columnas principales
pick_up_time          TIME           -- Tiempo actual (modificado por filtros)
original_pick_up_time TIME           -- ⚡ Tiempo original (NUNCA cambia después de primer filtro)
filter_applied        VARCHAR(50)    -- "reduce", "combine", "expand"
filter_batch_id       UUID           -- ID del batch para revertir
filtered_at           TIMESTAMP      -- Cuándo se aplicó el filtro
updated_at            TIMESTAMP      -- Última actualización
```

### 8.2 Flujo de Persistencia - ⚡ ACTUALIZADO

```python
async def apply(...):
    # ...aplicar filtros...

    for change in self.changes:
        trip = trip_lookup[change.trip_id]

        # ⚡ Guardar original SOLO la primera vez
        if trip.original_pick_up_time is None:
            trip.original_pick_up_time = trip.pick_up_time

        # Aplicar nuevo tiempo
        trip.pick_up_time = change.new_time
        trip.filter_applied = change.filter_applied  # Último filtro aplicado
        trip.filter_batch_id = batch_id
        trip.filtered_at = now
        trip.updated_at = now

        # ⚡ CRÍTICO: Agregar a sesión
        session.add(trip)

    await session.commit()
```

**⚡ IMPORTANTE:**
- `original_pick_up_time` se guarda **UNA SOLA VEZ**
- `original_pick_up_time` **NUNCA** cambia en aplicaciones posteriores
- `filter_applied` muestra el **último filtro** aplicado (puede ser "combine" aunque Reduce también esté activo)

### 8.3 Revertir Filtros

```python
async def revert(location_id, airline, batch_id):
    trips = get_filtered_trips(location_id, airline, batch_id)

    for trip in trips:
        # Restaurar tiempo original
        trip.pick_up_time = trip.original_pick_up_time
        trip.original_pick_up_time = None
        trip.filter_applied = None
        trip.filter_batch_id = None
        trip.filtered_at = None

        session.add(trip)

    await session.commit()
```

---

## 9. Endpoints API

### 9.1 POST `/v1/locations/{location_id}/airlines/{airline}/trips/filters/preview`

**Descripción:** Simula la aplicación de filtros sin modificar la base de datos.

**Request:**
```json
{
  "pick_up_date_from": "2025-10-01",
  "pick_up_date_to": "2025-10-31",
  "rounding_mode": "multiple_of_5",
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 20,
    "hotel_names": null,
    "time_range": null
  },
  "combine": {
    "enabled": true,
    "min_gap": 15,
    "max_gap": 30,
    "hotel_names": null,
    "time_range": null
  },
  "expand": {
    "enabled": false
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
      "original_time": "08:00:00",
      "new_time": "07:45:00",
      "filter_applied": "combine",
      "hotel_name": "Holiday Inn",
      "pick_up_date": "2025-10-01",
      "airline": "WN"
    }
  ],
  "exclusions": [],
  "summary": {
    "reduce": 150,
    "combine": 75,
    "expand": 0,
    "excluded": 0
  },
  "total_trips_evaluated": 300,
  "eligible_trips": 300
}
```

### 9.2 POST `/v1/locations/{location_id}/airlines/{airline}/trips/filters/apply`

**Descripción:** Aplica los filtros y persiste los cambios en la base de datos.

**Request:** Mismo formato que `/preview`

**Response:**
```json
{
  "batch_id": "uuid",
  "location_id": "uuid",
  "airline": "WN",
  "changes_applied": 225,
  "exclusions": [],
  "log": [...],
  "summary": {
    "reduce": 150,
    "combine": 75,
    "expand": 0,
    "excluded": 0
  }
}
```

### 9.3 POST `/v1/locations/{location_id}/airlines/{airline}/trips/filters/revert`

**Descripción:** Revierte los filtros aplicados.

**Query Params:**
- `batch_id` (opcional): Si se proporciona, solo revierte ese batch. Si no, revierte todos.

**Response:**
```json
{
  "trips_reverted": 225,
  "batch_ids_reverted": ["uuid"]
}
```

---

## 10. Ejemplos Concretos

### 10.1 Ejemplo Completo: Reduce + Combine

**Datos Iniciales:**
```
Día 2025-10-01:
  Trip A: id=1, original=02:00, pick_up_time=02:00
  Trip B: id=2, original=02:30, pick_up_time=02:30
```

**Request:**
```json
{
  "pick_up_date_from": "2025-10-01",
  "pick_up_date_to": "2025-10-01",
  "rounding_mode": "multiple_of_5",
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 20
  },
  "combine": {
    "enabled": true,
    "min_gap": 10,
    "max_gap": 60
  }
}
```

**Ejecución Paso a Paso:**

```
PASO 1: Reduce (Prioridad 0)
  ─────────────────────────────
  Trip A:
    base_time = original_pick_up_time = 02:00
    new_time = 02:00 - 20 = 01:40
    ✅ Cambio registrado: (02:00 → 01:40, filter="reduce")

  Trip B:
    base_time = original_pick_up_time = 02:30
    new_time = 02:30 - 20 = 02:10
    ✅ Cambio registrado: (02:30 → 02:10, filter="reduce")

PASO 2: Combine (Prioridad 1)
  ─────────────────────────────
  Trips del día 2025-10-01:
    Trip A: effective_time = 01:40 (último cambio de Reduce)
    Trip B: effective_time = 02:10 (último cambio de Reduce)

  Gap = 02:10 - 01:40 = 30 minutos
  min_gap (10) <= 30 <= max_gap (60) ✅

  Midpoint = (01:40 + 02:10) / 2 = 01:55

  ✅ Cambio registrado para Trip A: (01:40 → 01:55, filter="combine")
  ✅ Cambio registrado para Trip B: (02:10 → 01:55, filter="combine")

  modified_by_combine_expand.add(1)
  modified_by_combine_expand.add(2)

PASO 3: Persistencia
  ─────────────────────────────
  Trip A:
    original_pick_up_time = 02:00  ← Guardado la primera vez, NUNCA cambia
    pick_up_time = 01:55           ← Resultado final
    filter_applied = "combine"     ← Último filtro aplicado
    filter_batch_id = uuid

  Trip B:
    original_pick_up_time = 02:30  ← NUNCA cambia
    pick_up_time = 01:55
    filter_applied = "combine"
    filter_batch_id = uuid
```

**Resultado Final en DB:**
```sql
SELECT id, original_pick_up_time, pick_up_time, filter_applied
FROM trips.trips
WHERE id IN (1, 2);

-- Resultado:
--  id | original_pick_up_time | pick_up_time | filter_applied
-- ----+-----------------------+--------------+----------------
--   1 | 02:00:00              | 01:55:00     | combine
--   2 | 02:30:00              | 01:55:00     | combine
```

### 10.2 Ejemplo: Cambio de Configuración de Reduce

**Estado Actual (después del ejemplo 10.1):**
```
Trip A: original=02:00, pick_up_time=01:55 (Reduce -20, Combine aplicado)
Trip B: original=02:30, pick_up_time=01:55
```

**Nueva Request (cambiar Reduce a -30):**
```json
{
  "pick_up_date_from": "2025-10-01",
  "pick_up_date_to": "2025-10-01",
  "rounding_mode": "multiple_of_5",
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 30  // ⚡ Cambio de 20 a 30
  },
  "combine": {
    "enabled": true,
    "min_gap": 10,
    "max_gap": 60
  }
}
```

**Ejecución:**

```
PASO 1: Reduce (Prioridad 0)
  ─────────────────────────────
  Trip A:
    base_time = original_pick_up_time = 02:00  ← ⚡ Siempre usa el original
    new_time = 02:00 - 30 = 01:30
    ✅ Cambio: (02:00 → 01:30, filter="reduce")

  Trip B:
    base_time = 02:30  ← Siempre el original
    new_time = 02:30 - 30 = 02:00
    ✅ Cambio: (02:30 → 02:00, filter="reduce")

PASO 2: Combine (Prioridad 1)
  ─────────────────────────────
  Trip A: effective_time = 01:30 (de Reduce)
  Trip B: effective_time = 02:00 (de Reduce)

  Gap = 02:00 - 01:30 = 30 min ✅

  Midpoint = (01:30 + 02:00) / 2 = 01:45

  ✅ Trip A: (01:30 → 01:45, filter="combine")
  ✅ Trip B: (02:00 → 01:45, filter="combine")

RESULTADO FINAL:
  Trip A: original=02:00, pick_up_time=01:45  ← Cambió de 01:55 a 01:45
  Trip B: original=02:30, pick_up_time=01:45  ← Cambió de 01:55 a 01:45
```

### 10.3 Ejemplo: Rounding Modes

**Datos:**
```
Trip A: 02:11
Trip B: 02:27
Gap: 16 minutos
```

**Modo 1: MULTIPLE_OF_5**
```json
{
  "rounding_mode": "multiple_of_5",
  "combine": {
    "enabled": true,
    "min_gap": 10,
    "max_gap": 30
  }
}

Midpoint sin redondeo: (02:11 + 02:27) / 2 = 02:19
Midpoint redondeado: 02:20  ← Redondea al múltiplo de 5 más cercano

Resultado:
  Trip A: 02:20
  Trip B: 02:20
```

**Modo 2: ODD_MINUTES**
```json
{
  "rounding_mode": "odd_minutes",
  "combine": {
    "enabled": true,
    "min_gap": 10,
    "max_gap": 30
  }
}

Midpoint: (02:11 + 02:27) / 2 = 02:19
Sin redondeo: 02:19  ← Mantiene el valor exacto

Resultado:
  Trip A: 02:19
  Trip B: 02:19
```

---

## 11. Guía de Implementación Frontend

### 11.1 Actualizar Modelos TypeScript

```typescript
// ⚡ NUEVO: Enum de rounding mode
export enum RoundingMode {
  MULTIPLE_OF_5 = "multiple_of_5",
  ODD_MINUTES = "odd_minutes"
}

// ⚡ ACTUALIZADO: FilterRequest
export interface FilterRequest {
  pick_up_date_from?: string;       // "YYYY-MM-DD"
  pick_up_date_to?: string;         // "YYYY-MM-DD"
  rounding_mode: RoundingMode;      // ⚡ NUEVO
  reduce?: ReduceFilterConfig;
  combine?: CombineFilterConfig;
  expand?: ExpandFilterConfig;
}
```

### 11.2 Agregar UI para Rounding Mode

```typescript
// Componente de configuración
const FilterSettings = () => {
  const [roundingMode, setRoundingMode] = useState<RoundingMode>(
    RoundingMode.MULTIPLE_OF_5
  );

  return (
    <div>
      <label>Rounding Mode:</label>
      <select
        value={roundingMode}
        onChange={(e) => setRoundingMode(e.target.value as RoundingMode)}
      >
        <option value={RoundingMode.MULTIPLE_OF_5}>
          Multiple of 5 (10:15, 1:25) - Default
        </option>
        <option value={RoundingMode.ODD_MINUTES}>
          Odd Minutes (2:11, 5:27) - Exact
        </option>
      </select>
    </div>
  );
};
```

### 11.3 Construir Request

```typescript
const buildFilterRequest = (): FilterRequest => {
  const request: FilterRequest = {
    pick_up_date_from: selectedDateFrom,  // "2025-10-01"
    pick_up_date_to: selectedDateTo,      // "2025-10-31"
    rounding_mode: roundingMode,          // ⚡ NUEVO
  };

  // Agregar filtros habilitados
  if (reduceEnabled) {
    request.reduce = {
      enabled: true,
      minutes_to_reduce: reduceMinutes,
      hotel_names: selectedHotels.length > 0 ? selectedHotels : null,
      time_range: timeRange || null
    };
  }

  if (combineEnabled) {
    request.combine = {
      enabled: true,
      min_gap: combineMinGap,
      max_gap: combineMaxGap,
      hotel_names: selectedHotels.length > 0 ? selectedHotels : null,
      time_range: timeRange || null
    };
  }

  if (expandEnabled) {
    request.expand = {
      enabled: true,
      min_gap: expandMinGap,
      max_gap: expandMaxGap,
      max_shift: expandMaxShift,
      hotel_names: selectedHotels.length > 0 ? selectedHotels : null,
      time_range: timeRange || null
    };
  }

  return request;
};
```

### 11.4 Llamar API Preview

```typescript
const handlePreview = async () => {
  const request = buildFilterRequest();

  try {
    const response = await fetch(
      `/v1/locations/${locationId}/airlines/${airline}/trips/filters/preview`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request)
      }
    );

    const result: FilterPreviewResult = await response.json();

    console.log('Preview Result:', result);
    console.log('Summary:', result.summary);
    // summary = { reduce: 150, combine: 75, expand: 0, excluded: 0 }

    // Mostrar cambios en la UI
    displayChanges(result.changes);

  } catch (error) {
    console.error('Error in preview:', error);
  }
};
```

### 11.5 Llamar API Apply

```typescript
const handleApply = async () => {
  const request = buildFilterRequest();

  try {
    const response = await fetch(
      `/v1/locations/${locationId}/airlines/${airline}/trips/filters/apply`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request)
      }
    );

    const result: FilterApplyResult = await response.json();

    console.log('Applied filters:', result);
    console.log('Batch ID:', result.batch_id);  // Guardar para revert
    console.log('Changes applied:', result.changes_applied);

    // ⚡ IMPORTANTE: Refrescar la tabla de trips
    await refreshTripsTable();

  } catch (error) {
    console.error('Error in apply:', error);
  }
};
```

### 11.6 Refrescar Tabla de Trips

```typescript
const refreshTripsTable = async () => {
  // Llamar GET /trips con los mismos filtros de fecha
  const response = await fetch(
    `/v1/locations/${locationId}/trips?` +
    `airline=${airline}&` +
    `pick_up_date_from=${dateFrom}&` +
    `pick_up_date_to=${dateTo}&` +
    `skip=0&limit=50`
  );

  const trips = await response.json();

  // Actualizar tabla
  setTripsData(trips);

  // ⚡ Los trips ahora tienen pick_up_time modificado
  // Ejemplo:
  // trip.original_pick_up_time = "02:00:00"
  // trip.pick_up_time = "01:55:00"  ← Modificado por filtros
  // trip.filter_applied = "combine"
};
```

### 11.7 Revertir Filtros

```typescript
const handleRevert = async (batchId?: string) => {
  const url = batchId
    ? `/v1/locations/${locationId}/airlines/${airline}/trips/filters/revert?batch_id=${batchId}`
    : `/v1/locations/${locationId}/airlines/${airline}/trips/filters/revert`;

  try {
    const response = await fetch(url, { method: 'POST' });
    const result: FilterRevertResult = await response.json();

    console.log('Reverted trips:', result.trips_reverted);

    // Refrescar tabla
    await refreshTripsTable();

  } catch (error) {
    console.error('Error in revert:', error);
  }
};
```

### 11.8 Mostrar Indicadores en la Tabla

```typescript
const TripRow = ({ trip }: { trip: Trip }) => {
  const isFiltered = trip.filter_applied !== null;
  const hasOriginal = trip.original_pick_up_time !== null;

  return (
    <tr className={isFiltered ? 'filtered-row' : ''}>
      <td>{trip.id}</td>
      <td>
        {hasOriginal && (
          <span className="original-time" title="Original time">
            {trip.original_pick_up_time} →
          </span>
        )}
        <span className="current-time">
          {trip.pick_up_time}
        </span>
        {isFiltered && (
          <span className="filter-badge" title={`Filter: ${trip.filter_applied}`}>
            {trip.filter_applied}
          </span>
        )}
      </td>
      <td>{trip.hotel_name}</td>
      {/* ... más columnas ... */}
    </tr>
  );
};
```

---

## 12. Testing y Verificación

### 12.1 Test Case 1: Reduce con Prioridad 0

**Setup:**
```sql
INSERT INTO trips.trips (id, original_pick_up_time, pick_up_time, pick_up_date, airline, trip_type, status)
VALUES
  ('trip-a', NULL, '02:00:00', '2025-10-01', 'WN', 'outbound', 'scheduled'),
  ('trip-b', NULL, '02:30:00', '2025-10-01', 'WN', 'outbound', 'scheduled');
```

**Step 1: Apply Combine (Reduce OFF)**
```json
{
  "pick_up_date_from": "2025-10-01",
  "pick_up_date_to": "2025-10-01",
  "reduce": { "enabled": false },
  "combine": { "enabled": true, "min_gap": 10, "max_gap": 60 }
}
```

**Verificación:**
```sql
SELECT id, original_pick_up_time, pick_up_time, filter_applied
FROM trips.trips
WHERE id IN ('trip-a', 'trip-b');

-- Esperado:
--  id     | original_pick_up_time | pick_up_time | filter_applied
-- --------+-----------------------+--------------+----------------
--  trip-a | 02:00:00              | 02:15:00     | combine
--  trip-b | 02:30:00              | 02:15:00     | combine
```

**Step 2: Activate Reduce -20**
```json
{
  "pick_up_date_from": "2025-10-01",
  "pick_up_date_to": "2025-10-01",
  "reduce": { "enabled": true, "minutes_to_reduce": 20 },
  "combine": { "enabled": true, "min_gap": 10, "max_gap": 60 }
}
```

**Verificación:**
```sql
SELECT id, original_pick_up_time, pick_up_time, filter_applied
FROM trips.trips
WHERE id IN ('trip-a', 'trip-b');

-- Esperado:
--  id     | original_pick_up_time | pick_up_time | filter_applied
-- --------+-----------------------+--------------+----------------
--  trip-a | 02:00:00              | 01:55:00     | combine
--  trip-b | 02:30:00              | 01:55:00     | combine
--         ↑ NUNCA cambia         ↑ Cambió      ↑ Último aplicado
```

**⚡ Explicación:**
- `original_pick_up_time` permanece en 02:00 y 02:30 (NUNCA cambia)
- Reduce calcula: 02:00-20=01:40, 02:30-20=02:10
- Combine re-aplica: (01:40+02:10)/2 = 01:55
- `pick_up_time` final = 01:55
- `filter_applied` = "combine" (último filtro aplicado)

### 12.2 Test Case 2: Redondeo Configurable

**Setup:**
```sql
INSERT INTO trips.trips (id, pick_up_time, pick_up_date, airline, trip_type, status)
VALUES
  ('trip-c', '02:11:00', '2025-10-01', 'WN', 'outbound', 'scheduled'),
  ('trip-d', '02:27:00', '2025-10-01', 'WN', 'outbound', 'scheduled');
```

**Test con MULTIPLE_OF_5:**
```json
{
  "rounding_mode": "multiple_of_5",
  "combine": { "enabled": true, "min_gap": 10, "max_gap": 30 }
}
```

**Resultado Esperado:**
```
Midpoint sin redondeo: (02:11 + 02:27) / 2 = 02:19
Midpoint redondeado: 02:20

pick_up_time = 02:20 para ambos trips
```

**Test con ODD_MINUTES:**
```json
{
  "rounding_mode": "odd_minutes",
  "combine": { "enabled": true, "min_gap": 10, "max_gap": 30 }
}
```

**Resultado Esperado:**
```
Midpoint: 02:19 (sin redondeo)

pick_up_time = 02:19 para ambos trips
```

### 12.3 Test Case 3: Rule A (Reduce NO Bloquea Combine)

**Setup:**
```sql
INSERT INTO trips.trips (id, pick_up_time, pick_up_date, airline, trip_type, status)
VALUES
  ('trip-e', '08:00:00', '2025-10-01', 'WN', 'outbound', 'scheduled'),
  ('trip-f', '08:20:00', '2025-10-01', 'WN', 'outbound', 'scheduled');
```

**Request:**
```json
{
  "reduce": { "enabled": true, "minutes_to_reduce": 10 },
  "combine": { "enabled": true, "min_gap": 10, "max_gap": 30 }
}
```

**Verificación:**
```
Reduce aplica:
  Trip E: 08:00 - 10 = 07:50
  Trip F: 08:20 - 10 = 08:10
  Gap = 20 min

Combine NO debe ser bloqueado (Reduce no agrega a modified_by_combine_expand):
  Midpoint = (07:50 + 08:10) / 2 = 08:00
  ✅ Combine se aplica correctamente

Resultado esperado:
  Trip E: pick_up_time = 08:00
  Trip F: pick_up_time = 08:00
```

**SQL:**
```sql
SELECT id, original_pick_up_time, pick_up_time, filter_applied
FROM trips.trips
WHERE id IN ('trip-e', 'trip-f');

-- Esperado:
--  id     | original_pick_up_time | pick_up_time | filter_applied
-- --------+-----------------------+--------------+----------------
--  trip-e | 08:00:00              | 08:00:00     | combine
--  trip-f | 08:20:00              | 08:00:00     | combine
```

### 12.4 Queries de Verificación

**Verificar trips filtrados:**
```sql
SELECT
  id,
  pick_up_date,
  original_pick_up_time,
  pick_up_time,
  filter_applied,
  filter_batch_id,
  filtered_at
FROM trips.trips
WHERE location_id = 'uuid'
  AND airline = 'WN'
  AND filter_applied IS NOT NULL
ORDER BY pick_up_date, pick_up_time;
```

**Verificar que original_pick_up_time no cambió:**
```sql
-- Esta query debe retornar 0 filas
SELECT *
FROM trips.trips
WHERE filter_applied IS NOT NULL
  AND (
    original_pick_up_time IS NULL  -- No se guardó el original
    OR original_pick_up_time = pick_up_time  -- Original igual al actual (error)
  );
```

**Verificar summary:**
```sql
SELECT
  filter_applied,
  COUNT(*) as count
FROM trips.trips
WHERE location_id = 'uuid'
  AND airline = 'WN'
  AND filter_batch_id = 'batch-uuid'
GROUP BY filter_applied;

-- Esperado:
--  filter_applied | count
-- ----------------+-------
--  reduce         |   0    ← Reduce no es el último, Combine sobrescribe
--  combine        |  150
--  expand         |   0
```

---

## 13. Notas Importantes para el Equipo

### 13.1 ⚡ Cambios Críticos Implementados

1. **Reduce Prioridad 0**:
   - ✅ Siempre usa `original_pick_up_time`
   - ✅ NO está sujeto a Rule A
   - ✅ NO agrega a `modified_by_combine_expand`

2. **Tracking Separado**:
   - ✅ Nuevo set: `modified_by_combine_expand`
   - ✅ Solo Combine/Expand agregan a este set
   - ✅ Rule A solo chequea este set

3. **`_get_effective_time()`**:
   - ✅ Retorna el último cambio (con Reduce aplicado)
   - ✅ Combine/Expand usan tiempos efectivos, no `trip.pick_up_time`

4. **Redondeo Configurable**:
   - ✅ Nuevo campo `rounding_mode` en FilterRequest
   - ✅ Método `_round_time()` usa el modo configurado
   - ✅ Default: `MULTIPLE_OF_5` (backwards compatible)

### 13.2 Backwards Compatibility

- ✅ `rounding_mode` tiene default `MULTIPLE_OF_5`
- ✅ Si frontend no envía `rounding_mode`, usa el default
- ✅ Comportamiento anterior se mantiene como default

### 13.3 Consideraciones de Performance

- ⚠️ Reduce procesa TODOS los trips del rango (no agrupa por día)
- ⚠️ Combine/Expand agrupan por día (más eficiente)
- ✅ `_get_effective_time()` itera sobre `self.changes` (lista en memoria, no DB query)

### 13.4 Frontend Checklist

- [ ] Actualizar modelos TypeScript con `RoundingMode` y `rounding_mode`
- [ ] Agregar UI para seleccionar `rounding_mode`
- [ ] Actualizar `buildFilterRequest()` para incluir `rounding_mode`
- [ ] Refrescar tabla de trips después de `/apply`
- [ ] Mostrar indicador de filtros aplicados en la tabla
- [ ] Implementar botón de revert con `batch_id`
- [ ] Probar end-to-end con datos reales

---

**FIN DE LA DOCUMENTACIÓN**

**Contacto:** Backend Team
**Fecha:** 2026-01-17
**Versión:** 2.0 - Nueva Implementación con Prioridad de Reduce
