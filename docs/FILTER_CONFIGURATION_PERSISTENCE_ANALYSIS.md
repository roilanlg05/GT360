# 📊 Análisis: Persistencia de Configuración de Ground Filters

## 🎯 Pregunta del Usuario

¿Existe algo que permita al frontend mostrar la configuración guardada de filtros por:
- **Aerolínea** (airline)
- **Tipo de filtro** (reduce, combine, expand)
- **Organization ID** (visible para todos los roles: manager, drivers, crew)
- **Multi-dispositivo** (persistente entre sesiones y dispositivos)

¿Se construye solo en frontend o backend + frontend?

---

## ✅ LO QUE YA EXISTE EN EL BACKEND

### 1. **Modelo FilterBatch** (Base de Datos)

**Ubicación**: `shared/db/schemas/trips/filter_batches.py`

```python
class FilterBatch(PSQLModel):
    id: uuid                      # ID único del batch
    location_id: uuid             # → Links to organization via Location
    airline: str                  # "WN", "AA", etc.
    config: jsonb                 # Configuración COMPLETA guardada como JSON
    filters_applied: jsonb        # ["reduce", "combine", "expand"]
    trips_affected: int           # Número de trips modificados
    created_at: timestamptz       # Timestamp de aplicación
    revert_history: jsonb         # Historial de partial reverts
```

**Estructura del campo `config` (JSON completo)**:
```json
{
  "pick_up_date_from": "2026-01-15",
  "pick_up_date_to": "2026-01-31",
  "rounding_mode": "multiple_of_5",
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 20,
    "hotel_names": ["Marriott", "Hilton"],
    "time_range": { "start": "05:00:00", "end": "10:00:00" }
  },
  "combine": {
    "enabled": true,
    "min_gap": 10,
    "max_gap": 20,
    "hotel_names": null,
    "time_range": null
  },
  "expand": {
    "enabled": false
  }
}
```

### 2. **Trip Tracking** (Ya implementado)

**Ubicación**: `shared/db/schemas/trips/trips.py`

```python
class Trip:
    # ... campos normales ...

    # Tracking de filtros:
    original_pick_up_time: time   # Tiempo original (antes de filtros)
    filter_applied: str           # "reduce", "combine", "expand", "reduce+combine"
    filter_batch_id: uuid         # Referencia al FilterBatch
    filtered_at: timestamptz      # Timestamp de aplicación
```

### 3. **Relación Organization → Location → FilterBatch**

```
Organization (id)
    ↓ (has many)
Location (id, organization_id)
    ↓ (has many)
FilterBatch (id, location_id, airline)
```

**Esto significa:**
- ✅ Los filtros están asociados a una organización (indirectamente)
- ✅ Todos los usuarios de la misma organización pueden ver la misma configuración
- ✅ Es persistente en base de datos (no solo en frontend)

### 4. **Endpoints Existentes** (Solo escritura)

```
POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/preview
  → Simula cambios (no guarda nada)

POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/apply
  → Aplica filtros Y crea FilterBatch (✅ GUARDA CONFIG)

POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/revert
  → Revierte filtros (opcionalmente por batch_id)

POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/revert-partial
  → Revierte un filtro específico (reduce, combine, o expand)
```

---

## ❌ LO QUE FALTA (GAPs Críticos)

### **Problema Principal**: No hay endpoints GET para leer configuración

El sistema **guarda** la configuración pero **no expone** forma de leerla.

### GAPs identificados:

1. ❌ **No hay endpoint para obtener la configuración ACTUAL/ACTIVA**
   ```
   GET /v1/locations/{location_id}/airlines/{airline}/trips/filters/current
   → Debería retornar la configuración del último batch activo
   ```

2. ❌ **No hay endpoint para listar batches históricos**
   ```
   GET /v1/locations/{location_id}/airlines/{airline}/trips/filters/history
   → Lista todos los batches aplicados (con paginación)
   ```

3. ❌ **No hay endpoint para obtener un batch específico**
   ```
   GET /v1/locations/{location_id}/airlines/{airline}/trips/filters/batches/{batch_id}
   → Retorna config completa de un batch específico
   ```

4. ❌ **No hay endpoint para listar todas las configuraciones por organization**
   ```
   GET /v1/organizations/{org_id}/filters/summary
   → Lista todas las locations/airlines con filtros activos
   ```

---

## 🎯 RESPUESTA: Backend + Frontend

### **Es BACKEND + FRONTEND** por estas razones:

#### ✅ **Backend es NECESARIO porque:**

1. **Multi-dispositivo**:
   - Un manager aplica filtros desde laptop
   - Otro manager abre desde tablet → debe ver la misma config
   - **Imposible con solo frontend state**

2. **Multi-rol**:
   - Managers configuran filtros
   - Drivers necesitan ver qué filtros están activos
   - Crew members (QR scan) necesitan saber tiempos modificados
   - **Solo backend puede centralizar esta info**

3. **Persistencia**:
   - Sesión termina, config debe permanecer
   - Browser cache se limpia, config debe estar
   - **Base de datos es source of truth**

4. **Sincronización**:
   - Múltiples users editan simultáneamente
   - WebSocket puede notificar cambios
   - **Backend coordina estado global**

#### 🔨 **Frontend es NECESARIO porque:**

1. **UI Layer**: Display de la configuración
2. **Interaction**: Editar/modificar settings
3. **Cache Local**: Performance (cache de última config)
4. **Optimistic Updates**: UX responsivo

---

## 💡 SOLUCIÓN PROPUESTA

### Arquitectura Recomendada:

```
┌─────────────────────────────────────────────────┐
│ Frontend (React)                                │
│                                                 │
│  • UI para mostrar config actual                │
│  • Botones para editar/revertir                 │
│  • Cache de última config (localStorage)        │
│  • WebSocket listener para updates real-time    │
└────────────────┬────────────────────────────────┘
                 │
                 ↓ HTTP GET/POST
┌─────────────────────────────────────────────────┐
│ Backend API (Python/FastAPI)                    │
│                                                 │
│  NEW ENDPOINTS:                                 │
│  • GET /filters/current → Config activa         │
│  • GET /filters/history → Historial batches    │
│  • GET /filters/summary → Resumen por org      │
│                                                 │
│  EXISTING:                                      │
│  • POST /filters/apply → Guarda FilterBatch ✅  │
│  • POST /filters/revert → Revierte filtros ✅   │
└────────────────┬────────────────────────────────┘
                 │
                 ↓ SQL Queries
┌─────────────────────────────────────────────────┐
│ PostgreSQL Database                             │
│                                                 │
│  • FilterBatch table (ya existe) ✅             │
│  • Trip table con filter tracking ✅            │
└─────────────────────────────────────────────────┘
```

### Flujo Completo:

```
1. MANAGER APLICA FILTROS:
   Frontend → POST /filters/apply
   Backend → Crea FilterBatch
   Backend → Actualiza trips con filter_batch_id
   Backend → Publica WebSocket event

2. OTRO DISPOSITIVO/USUARIO ABRE APP:
   Frontend → GET /filters/current
   Backend → Query FilterBatch más reciente por location+airline
   Backend → Retorna config completa
   Frontend → Muestra config en UI

3. DRIVER ABRE APP:
   Frontend → GET /filters/current
   Backend → Retorna config (mismo endpoint)
   Frontend → Muestra badge "Filtros Activos: Reduce 20min"
```

---

## 🚀 ENDPOINTS NECESARIOS (Propuesta Detallada)

### 1. **GET Current Configuration** (CRÍTICO)

```http
GET /v1/locations/{location_id}/airlines/{airline}/trips/filters/current
```

**Response**:
```json
{
  "has_active_filters": true,
  "batch_id": "uuid",
  "applied_at": "2026-01-18T20:00:00Z",
  "filters_active": ["reduce", "combine"],
  "config": {
    "reduce": { "enabled": true, "minutes_to_reduce": 20 },
    "combine": { "enabled": true, "min_gap": 10, "max_gap": 20 },
    "expand": { "enabled": false }
  },
  "trips_affected": 543,
  "can_revert": true
}
```

**SQL Query**:
```python
# Obtener el batch más reciente con trips aún filtrados
latest_batch = await session.exec(
    Select(FilterBatch)
    .Where(
        (FilterBatch.location_id == location_id) &
        (FilterBatch.airline == airline)
    )
    .OrderBy(FilterBatch.created_at.Desc())
    .Limit(1)
).first()

# Verificar si aún hay trips con ese batch_id
trips_count = await session.exec(
    Select(Count(Trip.id))
    .Where(Trip.filter_batch_id == latest_batch.id)
).first()
```

### 2. **GET Filter History**

```http
GET /v1/locations/{location_id}/airlines/{airline}/trips/filters/history?skip=0&limit=10
```

**Response**:
```json
{
  "data": [
    {
      "batch_id": "uuid",
      "applied_at": "2026-01-18T20:00:00Z",
      "filters_applied": ["reduce", "combine"],
      "trips_affected": 543,
      "is_active": true,
      "reverted_filters": []
    },
    {
      "batch_id": "uuid-2",
      "applied_at": "2026-01-17T15:30:00Z",
      "filters_applied": ["reduce"],
      "trips_affected": 320,
      "is_active": false,
      "reverted_filters": ["reduce"]
    }
  ],
  "total": 25,
  "skip": 0,
  "limit": 10
}
```

### 3. **GET Organization Summary**

```http
GET /v1/organizations/{org_id}/filters/summary
```

**Response**:
```json
{
  "organization_id": "uuid",
  "locations": [
    {
      "location_id": "uuid",
      "location_name": "SDF",
      "airlines": [
        {
          "airline": "WN",
          "has_active_filters": true,
          "last_applied": "2026-01-18T20:00:00Z",
          "filters_active": ["reduce", "combine"],
          "trips_affected": 543
        },
        {
          "airline": "AA",
          "has_active_filters": false,
          "last_applied": null,
          "filters_active": [],
          "trips_affected": 0
        }
      ]
    }
  ]
}
```

### 4. **GET Specific Batch**

```http
GET /v1/locations/{location_id}/airlines/{airline}/trips/filters/batches/{batch_id}
```

**Response**:
```json
{
  "batch_id": "uuid",
  "location_id": "uuid",
  "airline": "WN",
  "applied_at": "2026-01-18T20:00:00Z",
  "config": {
    "pick_up_date_from": "2026-01-15",
    "pick_up_date_to": "2026-01-31",
    "reduce": { ... },
    "combine": { ... },
    "expand": { ... }
  },
  "filters_applied": ["reduce", "combine"],
  "trips_affected": 543,
  "revert_history": {
    "expand": {
      "reverted_at": "2026-01-18T21:00:00Z",
      "trips_affected": 120
    }
  }
}
```

---

## 📊 COMPARACIÓN: Solo Frontend vs Backend + Frontend

| Aspecto | Solo Frontend | Backend + Frontend ✅ |
|---------|---------------|----------------------|
| **Multi-dispositivo** | ❌ No sincroniza | ✅ Centralizado |
| **Multi-usuario** | ❌ Estado local | ✅ Compartido |
| **Persistencia** | ❌ Se pierde con cache | ✅ Database permanente |
| **Visibilidad roles** | ❌ Solo manager | ✅ Manager + Driver + Crew |
| **Source of truth** | ❌ Cada dispositivo | ✅ Backend único |
| **WebSocket updates** | ❌ No posible | ✅ Real-time sync |
| **Historial** | ❌ No disponible | ✅ Auditable |
| **Performance** | ✅ Sin latencia | ⚠️ Requiere HTTP calls |

**Ganador**: Backend + Frontend (con cache local para performance)

---

## 🎨 UI/UX PROPUESTA

### Vista para Manager:

```
┌─────────────────────────────────────────────────────┐
│ Ground Filters - Southwest Airlines (WN)           │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Status: 🟢 FILTROS ACTIVOS                        │
│  Aplicados: 18 Ene 2026, 20:00                     │
│  Trips afectados: 543                              │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │ ✅ Reduce: -20 minutos                       │   │
│  │    Hoteles: Marriott, Hilton                │   │
│  │    Horario: 05:00 - 10:00                   │   │
│  │                                              │   │
│  │ ✅ Combine: Gap 10-20 min                    │   │
│  │    Hoteles: Todos                           │   │
│  │                                              │   │
│  │ ❌ Expand: Inactivo                          │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  [Editar Configuración]  [Revertir Todo]          │
│  [Ver Historial (25)]                              │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Vista para Driver/Crew:

```
┌─────────────────────────────────────────────────────┐
│ Trips - Southwest Airlines (WN)                    │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ⚠️  NOTA: Tiempos modificados con filtros          │
│      • Reduce: -20 minutos                         │
│      • Combine: Viajes combinados en pares         │
│                                                     │
│  Ver detalles de configuración →                   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## ✅ CONCLUSIÓN Y RECOMENDACIONES

### **Respuesta Final**: BACKEND + FRONTEND

### **Por qué Backend:**
1. ✅ **Ya existe infraestructura** (FilterBatch, Trip tracking)
2. ✅ **Multi-dispositivo** es requirement crítico
3. ✅ **Multi-rol** (manager, driver, crew) necesitan ver mismo estado
4. ✅ **Source of truth** debe ser centralizado
5. ✅ **Auditoría** y historial son necesarios

### **Lo que falta construir:**
1. 🔨 **4 nuevos endpoints GET** (current, history, summary, batch detail)
2. 🔨 **Frontend UI** para mostrar configuración
3. 🔨 **Cache local** opcional para performance
4. 🔨 **WebSocket events** para sync real-time (opcional)

### **Esfuerzo estimado:**
- Backend (endpoints GET): 2-3 horas
- Frontend (UI components): 3-4 horas
- Testing: 1-2 horas
- **Total: 6-9 horas**

### **Prioridad de implementación:**
1. ⭐⭐⭐ **GET /filters/current** (CRÍTICO - lo más usado)
2. ⭐⭐ **GET /filters/history** (importante para managers)
3. ⭐ **GET /filters/summary** (nice-to-have para overview)
4. ⭐ **GET /filters/batches/{id}** (edge case)

---

## 📝 PRÓXIMOS PASOS

¿Quieres que implemente los endpoints GET faltantes?

Opción A: **Solo el endpoint crítico** (`GET /filters/current`)
Opción B: **Los 4 endpoints completos** (current + history + summary + detail)
Opción C: **Endpoints + Frontend UI completo**

**Recomendación**: Empezar con Opción A para desbloquear el frontend rápidamente.

---
---

# ✅ IMPLEMENTACIÓN COMPLETADA

## 🎯 Fecha de Implementación
**2026-01-18**

## 📦 Lo que se implementó

Se implementaron **2 endpoints GET** para managers, permitiendo visualizar la configuración de filtros desde cualquier dispositivo:

1. ✅ **GET /filters/current** - Ver configuración activa
2. ✅ **GET /filters/history** - Ver historial de batches aplicados

---

## 🔧 ENDPOINTS IMPLEMENTADOS (MANAGER ONLY)

### 1. GET Current Filter Configuration

```http
GET /v1/locations/{location_id}/airlines/{airline}/trips/filters/current
```

**Descripción**: Retorna la configuración activa de filtros para una location y airline específica.

**Autenticación**: Solo rol `manager`

**Response Model**: `FilterCurrentResponse`

```typescript
interface FilterCurrentResponse {
  has_active_filters: boolean;
  batch_id: string | null;           // UUID del batch activo
  applied_at: string | null;         // ISO 8601 timestamp
  filters_active: string[];          // ["reduce", "combine", "expand"]
  config: FilterConfig | null;       // Configuración completa
  trips_affected: number;            // Número de trips con filtros aplicados
  summary: FilterSummary | null;     // Desglose exacto por tipo de filtro
}

interface FilterSummary {
  reduced: number;   // Trips afectados por reduce
  combined: number;  // Trips afectados por combine
  expanded: number;  // Trips afectados por expand
}

interface FilterConfig {
  pick_up_date_from?: string;        // "YYYY-MM-DD"
  pick_up_date_to?: string;          // "YYYY-MM-DD"
  rounding_mode?: "multiple_of_5" | "odd_minutes";
  reduce?: {
    enabled: boolean;
    minutes_to_reduce: number;
    hotel_names: string[] | null;
    time_range: { start: string; end: string } | null;
  };
  combine?: {
    enabled: boolean;
    min_gap: number;
    max_gap: number;
    hotel_names: string[] | null;
    time_range: { start: string; end: string } | null;
  };
  expand?: {
    enabled: boolean;
    min_gap: number;
    max_gap: number;
    max_shift: number;
    hotel_names: string[] | null;
    time_range: { start: string; end: string } | null;
  };
}
```

**Response Examples**:

**Caso 1: Filtros Activos**
```json
{
  "has_active_filters": true,
  "batch_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "applied_at": "2026-01-18T20:00:00Z",
  "filters_active": ["reduce", "combine"],
  "config": {
    "pick_up_date_from": "2026-01-15",
    "pick_up_date_to": "2026-01-31",
    "rounding_mode": "multiple_of_5",
    "reduce": {
      "enabled": true,
      "minutes_to_reduce": 20,
      "hotel_names": ["Marriott", "Hilton"],
      "time_range": {
        "start": "05:00:00",
        "end": "10:00:00"
      }
    },
    "combine": {
      "enabled": true,
      "min_gap": 10,
      "max_gap": 20,
      "hotel_names": null,
      "time_range": null
    },
    "expand": {
      "enabled": false
    }
  },
  "trips_affected": 543,
  "summary": {
    "reduced": 320,
    "combined": 223,
    "expanded": 0
  }
}
```

**Caso 2: Sin Filtros Activos**
```json
{
  "has_active_filters": false,
  "batch_id": null,
  "applied_at": null,
  "filters_active": [],
  "config": null,
  "trips_affected": 0,
  "summary": null
}
```

**Status Codes**:
- `200 OK` - Respuesta exitosa (con o sin filtros activos)
- `400 Bad Request` - location_id o airline inválidos
- `403 Forbidden` - Usuario no es manager
- `404 Not Found` - Location no encontrada

---

### 2. GET Filter History

```http
GET /v1/locations/{location_id}/airlines/{airline}/trips/filters/history?skip=0&limit=10
```

**Descripción**: Retorna historial paginado de aplicaciones de filtros.

**Autenticación**: Solo rol `manager`

**Query Parameters**:
- `skip` (optional, default: 0) - Número de registros a saltar
- `limit` (optional, default: 10, max: 100) - Máximo de registros a retornar

**Response Model**: `FilterHistoryResponse`

```typescript
interface FilterHistoryResponse {
  data: FilterHistoryItem[];
  total: number;                     // Total de batches en historial
  skip: number;                      // Skip usado en la petición
  limit: number;                     // Limit usado en la petición
}

interface FilterHistoryItem {
  batch_id: string;                  // UUID del batch
  applied_at: string;                // ISO 8601 timestamp
  filters_applied: string[];         // ["reduce", "combine", "expand"]
  trips_affected: number;            // Trips afectados en aplicación original
  is_active: boolean;                // true si trips aún referencian este batch
  reverted_filters: string[];        // Filtros que fueron parcialmente revertidos
}
```

**Response Example**:

```json
{
  "data": [
    {
      "batch_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "applied_at": "2026-01-18T20:00:00Z",
      "filters_applied": ["reduce", "combine"],
      "trips_affected": 543,
      "is_active": true,
      "reverted_filters": []
    },
    {
      "batch_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
      "applied_at": "2026-01-17T15:30:00Z",
      "filters_applied": ["reduce", "combine", "expand"],
      "trips_affected": 320,
      "is_active": false,
      "reverted_filters": ["expand"]
    },
    {
      "batch_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
      "applied_at": "2026-01-16T10:00:00Z",
      "filters_applied": ["reduce"],
      "trips_affected": 150,
      "is_active": false,
      "reverted_filters": []
    }
  ],
  "total": 25,
  "skip": 0,
  "limit": 10
}
```

**Status Codes**:
- `200 OK` - Respuesta exitosa (puede ser array vacío si no hay historial)
- `400 Bad Request` - location_id o airline inválidos
- `403 Forbidden` - Usuario no es manager
- `404 Not Found` - Location no encontrada

---

## 🎨 GUÍA DE IMPLEMENTACIÓN FRONTEND

### Arquitectura Recomendada

```
Frontend (React/Vue/etc)
    ↓
  State Management (Redux/Zustand/Context)
    ↓
  API Service Layer
    ↓
  Backend API (GET /filters/current, GET /filters/history)
    ↓
  PostgreSQL (FilterBatch table)
```

### Flujos de Usuario (Manager)

#### Flujo 1: Ver Configuración Activa

```typescript
// 1. Manager abre página de Ground Filters
const { data, isLoading, error } = useQuery({
  queryKey: ['filterConfig', locationId, airline],
  queryFn: () => getFilterConfig(locationId, airline),
});

// 2. Mostrar estado según respuesta
if (data.has_active_filters) {
  // Renderizar configuración activa con:
  // - Badge "Filtros Activos"
  // - Fecha de aplicación
  // - Detalles de cada filtro (reduce, combine, expand)
  // - Número de trips afectados
  // - Botones: "Editar", "Revertir Todo", "Ver Historial"
} else {
  // Renderizar estado vacío:
  // - Mensaje "Sin filtros activos"
  // - Botón "Configurar Filtros"
  // - Opcionalmente mostrar historial (si existe)
}
```

#### Flujo 2: Ver Historial

```typescript
// 1. Manager hace click en "Ver Historial"
const { data, isLoading, fetchNextPage, hasNextPage } = useInfiniteQuery({
  queryKey: ['filterHistory', locationId, airline],
  queryFn: ({ pageParam = 0 }) =>
    getFilterHistory(locationId, airline, pageParam, 10),
  getNextPageParam: (lastPage, pages) => {
    const currentCount = pages.length * 10;
    return currentCount < lastPage.total ? currentCount : undefined;
  },
});

// 2. Renderizar lista con infinite scroll
// Para cada batch mostrar:
// - Fecha de aplicación
// - Filtros aplicados (badges: "Reduce", "Combine", "Expand")
// - Estado: "Activo" (verde) o "Revertido" (gris)
// - Si fue revertido parcialmente, mostrar qué filtros fueron revertidos
// - Trips afectados
// - Botón "Ver Detalles" (opcional, para mostrar config completa)
```

### API Service Layer (Ejemplo TypeScript)

```typescript
// services/filterConfigService.ts

import axios from 'axios';

const BASE_URL = process.env.REACT_APP_API_URL;

export interface FilterCurrentResponse {
  has_active_filters: boolean;
  batch_id: string | null;
  applied_at: string | null;
  filters_active: string[];
  config: FilterConfig | null;
  trips_affected: number;
  summary: FilterSummary | null;
}

export interface FilterSummary {
  reduced: number;
  combined: number;
  expanded: number;
}

export interface FilterHistoryResponse {
  data: FilterHistoryItem[];
  total: number;
  skip: number;
  limit: number;
}

export interface FilterHistoryItem {
  batch_id: string;
  applied_at: string;
  filters_applied: string[];
  trips_affected: number;
  is_active: boolean;
  reverted_filters: string[];
}

/**
 * Obtiene la configuración activa de filtros para una location y airline.
 *
 * @param locationId - UUID de la location
 * @param airline - Código de aerolínea (ej: "WN", "AA")
 * @returns Promise con la configuración actual
 * @throws Error si el usuario no es manager o la location no existe
 */
export async function getFilterConfig(
  locationId: string,
  airline: string
): Promise<FilterCurrentResponse> {
  const response = await axios.get<FilterCurrentResponse>(
    `${BASE_URL}/v1/locations/${locationId}/airlines/${airline}/trips/filters/current`,
    {
      headers: {
        Authorization: `Bearer ${getAuthToken()}`,
      },
    }
  );
  return response.data;
}

/**
 * Obtiene el historial de aplicaciones de filtros.
 *
 * @param locationId - UUID de la location
 * @param airline - Código de aerolínea
 * @param skip - Número de registros a saltar (paginación)
 * @param limit - Máximo de registros a retornar (1-100)
 * @returns Promise con el historial paginado
 */
export async function getFilterHistory(
  locationId: string,
  airline: string,
  skip: number = 0,
  limit: number = 10
): Promise<FilterHistoryResponse> {
  const response = await axios.get<FilterHistoryResponse>(
    `${BASE_URL}/v1/locations/${locationId}/airlines/${airline}/trips/filters/history`,
    {
      params: { skip, limit },
      headers: {
        Authorization: `Bearer ${getAuthToken()}`,
      },
    }
  );
  return response.data;
}

function getAuthToken(): string {
  // Implementar según tu sistema de autenticación
  return localStorage.getItem('auth_token') || '';
}
```

### Componente de Ejemplo (React)

```tsx
// components/FilterConfigPanel.tsx

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { getFilterConfig } from '../services/filterConfigService';

interface Props {
  locationId: string;
  airline: string;
}

export function FilterConfigPanel({ locationId, airline }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['filterConfig', locationId, airline],
    queryFn: () => getFilterConfig(locationId, airline),
    refetchOnWindowFocus: true,  // Refetch al volver a la ventana
    refetchInterval: 60000,       // Refetch cada 60 segundos (opcional)
  });

  if (isLoading) {
    return <div>Cargando configuración...</div>;
  }

  if (error) {
    return <div>Error: {error.message}</div>;
  }

  if (!data.has_active_filters) {
    return (
      <div className="no-filters-state">
        <h3>Sin filtros activos</h3>
        <p>No hay filtros aplicados actualmente para {airline}</p>
        <button onClick={() => navigateToConfigurePage()}>
          Configurar Filtros
        </button>
      </div>
    );
  }

  return (
    <div className="filter-config-panel">
      <div className="header">
        <h2>Ground Filters - {airline}</h2>
        <span className="badge active">FILTROS ACTIVOS</span>
      </div>

      <div className="metadata">
        <p>Aplicados: {formatDate(data.applied_at!)}</p>
        <p>Trips afectados: {data.trips_affected}</p>
        <p>Batch ID: {data.batch_id}</p>
      </div>

      <div className="filters-list">
        {data.filters_active.includes('reduce') && data.config?.reduce && (
          <FilterCard
            type="reduce"
            title="Reduce"
            config={data.config.reduce}
          />
        )}
        {data.filters_active.includes('combine') && data.config?.combine && (
          <FilterCard
            type="combine"
            title="Combine"
            config={data.config.combine}
          />
        )}
        {data.filters_active.includes('expand') && data.config?.expand && (
          <FilterCard
            type="expand"
            title="Expand"
            config={data.config.expand}
          />
        )}
      </div>

      <div className="actions">
        <button onClick={() => openEditModal(data.config!)}>
          Editar Configuración
        </button>
        <button onClick={() => revertAllFilters(data.batch_id!)}>
          Revertir Todo
        </button>
        <button onClick={() => openHistoryModal()}>
          Ver Historial
        </button>
      </div>
    </div>
  );
}
```

---

## ⚠️ CASOS DE USO Y ESTADOS POSIBLES

### Estado 1: Sin Filtros Nunca Aplicados
```json
{
  "has_active_filters": false,
  "batch_id": null,
  "applied_at": null,
  "filters_active": [],
  "config": null,
  "trips_affected": 0
}
```

**Frontend debe mostrar**:
- Mensaje: "Sin filtros configurados"
- Botón: "Configurar Filtros"
- Historial: Vacío o no mostrar sección

---

### Estado 2: Filtros Activos
```json
{
  "has_active_filters": true,
  "batch_id": "uuid",
  "applied_at": "2026-01-18T20:00:00Z",
  "filters_active": ["reduce", "combine"],
  "config": { ... },
  "trips_affected": 543
}
```

**Frontend debe mostrar**:
- Badge verde: "FILTROS ACTIVOS"
- Detalles completos de configuración
- Botones: "Editar", "Revertir", "Ver Historial"

---

### Estado 3: Filtros Fueron Revertidos
```json
{
  "has_active_filters": false,
  "batch_id": null,
  "applied_at": null,
  "filters_active": [],
  "config": null,
  "trips_affected": 0
}
```

**Pero el historial muestra batches previos**:
```json
{
  "data": [
    {
      "batch_id": "uuid",
      "applied_at": "2026-01-17T10:00:00Z",
      "filters_applied": ["reduce"],
      "trips_affected": 200,
      "is_active": false,
      "reverted_filters": []
    }
  ],
  "total": 1
}
```

**Frontend debe mostrar**:
- Mensaje: "Sin filtros activos actualmente"
- Submensaje: "Última aplicación: 17 Ene 2026 (revertida)"
- Botón: "Ver Historial Completo"
- Botón: "Configurar Nuevos Filtros"

---

### Estado 4: Revert Parcial
```json
// GET /current
{
  "has_active_filters": true,
  "filters_active": ["reduce"],  // Solo reduce
  "config": { ... }
}

// GET /history
{
  "data": [
    {
      "batch_id": "uuid",
      "filters_applied": ["reduce", "combine", "expand"],
      "is_active": true,
      "reverted_filters": ["combine", "expand"]  // Estos fueron revertidos
    }
  ]
}
```

**Frontend debe mostrar**:
- Badge: "FILTROS ACTIVOS (Modificados)"
- Indicar que algunos filtros del batch original fueron revertidos
- Mostrar solo los filtros activos actualmente
- En historial, mostrar badges de "Revertido" para combine y expand

---

## 🔄 SINCRONIZACIÓN MULTI-DISPOSITIVO

### Problema:
Manager A aplica filtros desde laptop → Manager B abre desde tablet

### Solución:
Frontend debe implementar polling o WebSocket para mantener sincronización.

**Opción 1: Polling (Simple)**
```typescript
useQuery({
  queryKey: ['filterConfig', locationId, airline],
  queryFn: () => getFilterConfig(locationId, airline),
  refetchInterval: 30000,  // Poll cada 30 segundos
});
```

**Opción 2: WebSocket (Recomendado)**
```typescript
// Subscribe a cambios de filtros
const socket = useWebSocket();

useEffect(() => {
  socket.on('filter:applied', (data) => {
    if (data.locationId === locationId && data.airline === airline) {
      // Invalidar cache y refetch
      queryClient.invalidateQueries(['filterConfig', locationId, airline]);

      // Mostrar notificación
      toast.info(`Filtros actualizados por ${data.userName}`);
    }
  });

  socket.on('filter:reverted', (data) => {
    if (data.locationId === locationId && data.airline === airline) {
      queryClient.invalidateQueries(['filterConfig', locationId, airline]);
      toast.info('Filtros revertidos');
    }
  });

  return () => {
    socket.off('filter:applied');
    socket.off('filter:reverted');
  };
}, [locationId, airline]);
```

---

## 🧪 TESTING RECOMENDADO

### Unit Tests (Frontend)

```typescript
describe('FilterConfigService', () => {
  it('should fetch current config successfully', async () => {
    // Mock API response
    mockAxios.get.mockResolvedValueOnce({
      data: {
        has_active_filters: true,
        batch_id: 'test-uuid',
        filters_active: ['reduce'],
        trips_affected: 100,
      },
    });

    const result = await getFilterConfig('location-1', 'WN');

    expect(result.has_active_filters).toBe(true);
    expect(result.filters_active).toContain('reduce');
  });

  it('should handle no active filters', async () => {
    mockAxios.get.mockResolvedValueOnce({
      data: {
        has_active_filters: false,
        batch_id: null,
        filters_active: [],
        trips_affected: 0,
      },
    });

    const result = await getFilterConfig('location-1', 'AA');

    expect(result.has_active_filters).toBe(false);
    expect(result.batch_id).toBeNull();
  });
});
```

### Integration Tests (Backend + Frontend)

```typescript
describe('Filter Configuration Integration', () => {
  it('should show active config after applying filters', async () => {
    // 1. Apply filters
    await applyFilters(locationId, airline, {
      reduce: { enabled: true, minutes_to_reduce: 20 },
    });

    // 2. Get current config
    const config = await getFilterConfig(locationId, airline);

    // 3. Verify
    expect(config.has_active_filters).toBe(true);
    expect(config.filters_active).toContain('reduce');
    expect(config.config?.reduce?.minutes_to_reduce).toBe(20);
  });

  it('should show no active config after reverting', async () => {
    // 1. Apply filters
    const applyResult = await applyFilters(locationId, airline, {...});

    // 2. Revert filters
    await revertFilters(locationId, airline, applyResult.batch_id);

    // 3. Get current config
    const config = await getFilterConfig(locationId, airline);

    // 4. Verify
    expect(config.has_active_filters).toBe(false);
  });
});
```

---

## 📝 CHECKLIST DE IMPLEMENTACIÓN FRONTEND

### Fase 1: Setup Básico
- [ ] Crear types/interfaces para FilterCurrentResponse y FilterHistoryResponse
- [ ] Implementar servicio API (getFilterConfig, getFilterHistory)
- [ ] Configurar React Query o SWR para caching

### Fase 2: UI Components
- [ ] Componente FilterConfigPanel (mostrar config activa)
- [ ] Componente FilterHistoryList (mostrar historial con paginación)
- [ ] Estados vacíos (sin filtros, sin historial)
- [ ] Loading states y error handling

### Fase 3: Integración
- [ ] Conectar con flujo de "Apply Filters" (invalidar cache después de aplicar)
- [ ] Conectar con flujo de "Revert Filters" (invalidar cache después de revertir)
- [ ] Implementar polling o WebSocket para sincronización multi-dispositivo

### Fase 4: UX Enhancements
- [ ] Notificaciones cuando otros managers modifican filtros
- [ ] Confirmación antes de revertir filtros
- [ ] Mostrar timestamp relativo ("hace 2 horas", "ayer")
- [ ] Badges visuales para estado (activo/revertido)

### Fase 5: Testing
- [ ] Unit tests para servicios API
- [ ] Component tests para FilterConfigPanel
- [ ] Integration tests para flujo completo
- [ ] E2E tests para multi-dispositivo

---

## 🚀 DEPLOYMENT STATUS

### Backend
- ✅ Modelos creados en `features/trips/models/filter_models.py`
- ✅ Endpoints implementados en `features/trips/routes/trips_router.py`
- ✅ Deployado en Docker (imagen: `gt360:latest`)
- ✅ Verificado en OpenAPI: `http://localhost:8000/docs`

### Endpoints Disponibles
```
GET /v1/locations/{location_id}/airlines/{airline}/trips/filters/current
GET /v1/locations/{location_id}/airlines/{airline}/trips/filters/history
```

### Frontend
- ⏳ Pendiente de implementación

---

## 🎯 PRÓXIMOS PASOS RECOMENDADOS

1. **Implementar servicios API en frontend** (1-2 horas)
   - Crear tipos TypeScript
   - Implementar funciones de fetch
   - Configurar React Query

2. **Crear componente FilterConfigPanel** (2-3 horas)
   - UI para mostrar configuración activa
   - Estados: activo, inactivo, loading, error
   - Botones de acción (editar, revertir, historial)

3. **Crear componente FilterHistoryModal** (2-3 horas)
   - Lista paginada de batches
   - Infinite scroll o paginación tradicional
   - Mostrar estado de cada batch (activo/revertido)

4. **Implementar sincronización** (1-2 horas)
   - Polling cada 30-60 segundos, o
   - WebSocket events para cambios en tiempo real

5. **Testing** (2-3 horas)
   - Unit tests para servicios
   - Component tests
   - Integration tests

**Total estimado**: 8-13 horas de desarrollo frontend

---

## 📞 CONTACTO Y SOPORTE

Si tienes preguntas sobre la implementación o necesitas ajustes, contacta al equipo de backend.

**Endpoints de documentación**:
- OpenAPI Docs: `http://localhost:8000/docs`
- Redoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
