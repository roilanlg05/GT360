# Filter Preset Global + Auto-Aplicación - Guía Completa

**Fecha:** 2026-01-24
**Versión:** 1.0
**Estado:** ✅ IMPLEMENTADO Y DEPLOYADO

---

## 📋 Índice

1. [Overview](#overview)
2. [Qué es un Preset](#qué-es-un-preset)
3. [Cómo Funciona](#cómo-funciona)
4. [Endpoints](#endpoints)
5. [Ejemplos Frontend](#ejemplos-frontend)
6. [Lifecycle y Persistencia](#lifecycle-y-persistencia)
7. [Testing](#testing)

---

## Overview

**Filter Preset Global** es un sistema que permite configurar filtros una sola vez y aplicarlos automáticamente a trips futuros al importar archivos.

### Beneficios

- ⚡ **Auto-apply:** Filtros se aplican automáticamente sin intervención manual
- 🔒 **Consistencia:** Mismo filtro para todos los días futuros
- 💾 **Persistencia:** Config guardada en backend (no en localStorage)
- 🎯 **Por Location + Airline:** Preset específico para cada combinación

---

## Qué es un Preset

Un **Preset** es un "stack template" guardado en DB que contiene:

```typescript
interface FilterPreset {
  id: string;
  location_id: string;
  airline: string;
  stack_template: FilterPresetTemplate[];  // Array de steps
  created_at: string;
  updated_at: string;
  created_by?: string;
}

interface FilterPresetTemplate {
  filter_type: "reduce" | "combine" | "expand";
  windows: TimeWindow[];  // Windows completos con config
}
```

**Ejemplo:**
```json
{
  "location_id": "uuid",
  "airline": "WN",
  "stack_template": [
    {
      "filter_type": "reduce",
      "windows": [
        {
          "start": "05:00",
          "end": "10:00",
          "enabled": true,
          "minutes_to_reduce": 10,
          "hotel_names": ["Hotel A"]
        },
        {
          "start": "18:00",
          "end": "22:00",
          "enabled": true,
          "minutes_to_reduce": 20
        }
      ]
    },
    {
      "filter_type": "combine",
      "windows": [
        {
          "start": "00:00",
          "end": "24:00",
          "enabled": true,
          "min_gap": 10,
          "max_gap": 20
        }
      ]
    }
  ]
}
```

---

## Cómo Funciona

### Flujo Completo

```
1. Manager crea preset (POST /preset)
   ↓
2. Preset guardado en trips.filter_presets
   ↓
3. Manager importa trips (POST /upload-trips)
   ↓
4. Backend: ANTES del import, query días existentes
   → Ej: [2026-01-20, 2026-01-21] ya existen
   ↓
5. Backend: Import crea trips
   → Días en import: [2026-01-20, 2026-01-25, 2026-01-26]
   ↓
6. Backend: Detecta días NUEVOS
   → Nuevos = días que NO existían antes
   → Nuevos: [2026-01-25, 2026-01-26]
   → Pre-existentes: [2026-01-20]
   ↓
7. Para cada día NUEVO:
   ¿Hay preset? NO → Sin filtros
                SÍ → Clonar preset → crear stack → aplicar
   ↓
8. Para días PRE-EXISTENTES:
   → Skip (NO aplicar preset aunque no tengan stack)
   ↓
9. Resultado:
   - Días nuevos (25, 26): filtros aplicados automáticamente
   - Días viejos (20): SIN cambios (aunque no tengan stack)
```

### Reglas de Auto-Aplicación

| Condición | Acción |
|-----------|--------|
| **No hay preset** | Trips creados sin filtros (normal) |
| **Día NO es nuevo** | Skip (no aplicar preset, aunque no tenga stack) |
| **Día SÍ es nuevo + no hay preset** | Trips sin filtros |
| **Día SÍ es nuevo + hay preset + no tiene stack** | Clonar preset → crear stack → aplicar filtros |
| **Día SÍ es nuevo + hay preset + tiene stack** | Skip (respetar stack existente) |

**CRÍTICO - Definición de "Día Nuevo":**

Un `pick_up_date` es "nuevo" si **NO existía previamente** en `trips.trips` para esa `location_id + airline`.

Esto se detecta **ANTES** del import:
1. Query días existentes para location+airline
2. Import crea trips nuevos
3. Comparar: días importados vs días existentes
4. **Solo los que NO existían antes** = días nuevos

**IMPORTANTE:**
- Auto-apply SOLO a días que son nuevos en este import
- Días viejos (pre-existentes) NO se tocan, **aunque no tengan stack**
- Auto-apply NUNCA sobrescribe stack existente

---

## Endpoints

**Base URL:** `/v2/locations/{location_id}/airlines/{airline}/filters/preset`

### 1. Crear o Actualizar Preset

```http
POST /v2/locations/{location_id}/airlines/{airline}/filters/preset
```

**Request Body:**
```json
{
  "stack_template": [
    {
      "filter_type": "reduce",
      "windows": [
        {
          "start": "05:00",
          "end": "10:00",
          "enabled": true,
          "minutes_to_reduce": 10
        }
      ]
    },
    {
      "filter_type": "combine",
      "windows": [
        {
          "start": "00:00",
          "end": "24:00",
          "enabled": true,
          "min_gap": 10,
          "max_gap": 20
        }
      ]
    }
  ]
}
```

**Response:**
```json
{
  "id": "uuid",
  "location_id": "uuid",
  "airline": "WN",
  "stack_template": [ /* igual que request */ ],
  "created_at": "2026-01-24T00:00:00Z",
  "updated_at": "2026-01-24T00:00:00Z",
  "created_by": null
}
```

---

### 2. Obtener Preset

```http
GET /v2/locations/{location_id}/airlines/{airline}/filters/preset
```

**Response:**
Igual que POST, o 404 si no existe.

---

### 3. Actualizar Preset

```http
PUT /v2/locations/{location_id}/airlines/{airline}/filters/preset
```

**Request Body:**
```json
{
  "stack_template": [ /* nuevo template */ ]
}
```

**Response:**
Igual que POST.

---

### 4. Eliminar Preset

```http
DELETE /v2/locations/{location_id}/airlines/{airline}/filters/preset
```

**Response:**
```json
{
  "status": "deleted"
}
```

---

### 5. Test Preset (Dry-Run)

```http
POST /v2/locations/{location_id}/airlines/{airline}/filters/preset/test
    ?pick_up_date=2026-01-25
```

**Descripción:**
Preview de cómo el preset se aplicaría a un día específico SIN aplicarlo.

**Response:**
```json
{
  "applied": true,
  "days_processed": 1,
  "days_skipped": 0,
  "trips_affected": 25,
  "stack_cloned_from_preset": true
}
```

---

## Ejemplos Frontend

### Crear Preset

```typescript
const createPreset = async (locationId: string, airline: string) => {
  const preset = {
    stack_template: [
      {
        filter_type: 'reduce',
        windows: [
          {
            start: '05:00',
            end: '10:00',
            enabled: true,
            minutes_to_reduce: 10,
            hotel_names: ['Hotel A', 'Hotel B']
          },
          {
            start: '18:00',
            end: '22:00',
            enabled: true,
            minutes_to_reduce: 20
          }
        ]
      },
      {
        filter_type: 'combine',
        windows: [
          {
            start: '00:00',
            end: '24:00',
            enabled: true,
            min_gap: 10,
            max_gap: 20
          }
        ]
      }
    ]
  };

  const response = await fetch(
    `/v2/locations/${locationId}/airlines/${airline}/filters/preset`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(preset),
    }
  );

  return response.json();
};
```

---

### Obtener Preset

```typescript
const getPreset = async (locationId: string, airline: string) => {
  const response = await fetch(
    `/v2/locations/${locationId}/airlines/${airline}/filters/preset`
  );

  if (response.status === 404) {
    return null; // No preset
  }

  return response.json();
};
```

---

### Upload con Auto-Apply

```typescript
const uploadTrips = async (file: File, airport: string, airline: string) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('airport', airport);
  formData.append('airline', airline);

  const response = await fetch('/v1/trips/upload-trips', {
    method: 'POST',
    body: formData,
  });

  const result = await response.json();

  console.log(`Uploaded ${result.uploaded_rows} trips`);
  // Filtros aplicados automáticamente si existe preset ✅
};
```

---

## Lifecycle y Persistencia

### Tabla en DB

```sql
trips.filter_presets (
    id UUID,
    location_id UUID → FK CASCADE,
    airline VARCHAR(10),
    stack_template JSONB,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    created_by UUID,
    UNIQUE(location_id, airline)
)
```

### FK Cascades

```
entities.locations
    ↓ ON DELETE CASCADE
    ├── trips.trips
    ├── trips.filter_steps
    └── trips.filter_presets  ← Preset borrado al borrar location
```

### Persistencia

| Acción | Preset | Stack | Trips |
|--------|--------|-------|-------|
| **Crear preset** | Guardado | - | - |
| **Import sin preset** | - | - | Creados sin filtros |
| **Import con preset (día nuevo)** | - | Clonado | Filtros aplicados |
| **Import con preset (día con stack)** | - | Sin cambios | Nuevos sin filtros |
| **Borrar trips** | Persiste | Persiste | Borrados |
| **Borrar location** | Borrado (CASCADE) | Borrado (CASCADE) | Borrado (CASCADE) |

---

## Testing

### Test 1: Crear Preset

```bash
curl -X POST http://localhost:8000/v2/locations/{loc}/airlines/WN/filters/preset \
  -H "Content-Type: application/json" \
  -d '{
    "stack_template": [
      {
        "filter_type": "reduce",
        "windows": [
          {
            "start": "05:00",
            "end": "10:00",
            "enabled": true,
            "minutes_to_reduce": 15
          }
        ]
      }
    ]
  }'

# Resultado esperado:
# {
#   "id": "uuid",
#   "location_id": "uuid",
#   "airline": "WN",
#   "stack_template": [...]
# }
```

---

### Test 2: Upload con Auto-Apply

```bash
# 1. Verificar preset existe
curl http://localhost:8000/v2/locations/{loc}/airlines/WN/filters/preset

# 2. Upload trips
curl -X POST http://localhost:8000/v1/trips/upload-trips \
  -F "file=@trips.xlsx" \
  -F "airport=LAX" \
  -F "airline=WN" \
  -F "provider=Southwest"

# 3. Verificar en logs
docker logs gt360 --tail 50 | grep AUTO_PRESET

# Resultado esperado:
# [AUTO_PRESET] ✅ Applied preset to 3 days, affected 150 trips
# [AUTO_PRESET] Skipped 0 days (already have stack)

# 4. Verificar stack fue creado
curl http://localhost:8000/v2/locations/{loc}/airlines/WN/filters/stack?pick_up_date=2026-01-25

# Resultado esperado:
# {
#   "steps": [
#     {
#       "step_id": "uuid",
#       "step_order": 1,
#       "filter_type": "reduce",
#       "windows": [...],
#       "trips_affected": 50
#     }
#   ]
# }
```

---

### Test 3: No Sobrescribir Stack Existente

```bash
# 1. Crear preset
curl -X POST .../filters/preset -d '{...}'

# 2. Aplicar manualmente un step para día X
curl -X POST .../filters/step/apply -d '{
  "filter_type": "expand",
  "pick_up_date": "2026-01-25",
  "windows": [...]
}'

# 3. Upload trips para mismo día X
curl -X POST /v1/trips/upload-trips -F "file=@trips.xlsx" ...

# 4. Verificar logs
docker logs gt360 --tail 50 | grep AUTO_PRESET

# Resultado esperado:
# [AUTO_PRESET] Skipping 2026-01-25 (already has stack)
# [AUTO_PRESET] Not applied: All days already have stack

# 5. Verificar stack NO cambió
curl .../filters/stack?pick_up_date=2026-01-25

# Resultado: Stack sigue teniendo SOLO el Expand manual, NO el preset
```

---

### Test 4: Verificar FK CASCADE

```bash
# 1. Crear preset
curl -X POST .../filters/preset -d '{...}'

# 2. Verificar preset existe
SELECT * FROM trips.filter_presets WHERE location_id = 'uuid';
# 1 row

# 3. Borrar location
DELETE FROM entities.locations WHERE id = 'uuid';

# 4. Verificar preset borrado
SELECT * FROM trips.filter_presets WHERE location_id = 'uuid';
# 0 rows (CASCADE lo borró) ✅
```

---

## Lifecycle y Persistencia

### Persistencia de Preset

| Acción | Resultado |
|--------|-----------|
| **Crear preset** | Guardado en trips.filter_presets |
| **Upload trips** | Preset persiste (no se modifica) |
| **Borrar trips** | Preset persiste |
| **Borrar stack de un día** | Preset persiste |
| **Borrar location** | Preset borrado (FK CASCADE) |

### Auto-Apply Logic

**Ubicación:** `trips_router.py:314-345` (DESPUÉS de `session.commit()`)

**Código:**
```python
# Auto-apply preset if exists
preset_service = FilterPresetService(session)
auto_apply_result = await preset_service.auto_apply_preset(
    location_id=location.id,
    airline=airline,
    pick_up_dates=unique_dates
)
```

**Logging:**
```
[AUTO_PRESET] ✅ Applied preset to 3 days, affected 150 trips
[AUTO_PRESET] Skipped 1 days (already have stack)
```

o

```
[AUTO_PRESET] Not applied: No preset found for this location+airline
```

---

## Casos de Uso

### Caso 1: Setup Inicial

```
1. Manager va a "Filter Settings"
2. Configura preset:
   - Reduce: 05:00-10:00 reduce 10 min
   - Reduce: 18:00-22:00 reduce 20 min
   - Combine: 00:00-24:00 min=10 max=20
3. Guarda preset (POST /preset)
4. De ahora en adelante, TODOS los imports aplicarán este preset automáticamente
```

---

### Caso 2: Import Nuevo con Preset

```
Manager importa archivo Excel con trips para 2026-02-10

Backend:
1. Crea trips en DB
2. Commit
3. Detecta preset para location+airline
4. Clona preset → crea stack para 2026-02-10
5. Aplica Reduce → modifica trips
6. Aplica Combine → modifica trips
7. Notifica via WebSocket

Frontend recibe:
- Trips con pickup_time ya modificado
- No necesita aplicar filtros manualmente
```

---

### Caso 3: Re-Import a Día Pre-Existente

```
Manager importa MÁS trips para 2026-01-25 (día que YA existía en DB)

Backend:
1. Query días existentes ANTES del import
   → 2026-01-25 existe ✓
2. Crea trips nuevos en DB
3. Commit
4. Detecta preset
5. Filtra días: 2026-01-25 NO es nuevo (existía antes)
6. Skip auto-apply (día NO es nuevo)

Resultado:
- Trips antiguos: conservan su estado (con o sin filtros)
- Trips nuevos: SIN filtros (pickup_time = original)
- Manager debe aplicar filtros manualmente si lo desea

IMPORTANTE: Aunque el día 2026-01-25 NO tenga stack, no se auto-aplica
porque el criterio es "día nuevo", no "día sin stack".
```

---

### Caso 3b: Re-Import a Día Existente CON Stack

```
Caso especial: Día existía Y tiene stack

Backend:
1. Día 2026-01-25 NO es nuevo → skip (no entra a auto-apply)
2. (Auto-apply ni siquiera verifica si tiene stack)

Resultado: Igual que Caso 3
```

---

### Caso 4: Modificar Preset

```
Manager modifica preset (ej: cambiar reduce de 10 a 15 min)

Efecto:
- Preset actualizado en DB
- Días futuros usarán nuevo preset
- Días antiguos con stack NO cambian (se respeta histórico)

Si el manager quiere aplicar nuevo preset a días viejos:
- Debe revertir stack del día
- Re-importar trips
- O aplicar manualmente con nuevo config
```

---

## Comparación con Sistema Manual

| Aspecto | Sin Preset | Con Preset |
|---------|------------|------------|
| **Import** | Trips sin filtros | Trips con filtros aplicados |
| **Manager intervención** | Manual (cada día) | Ninguna (automático) |
| **Consistencia** | Variable | 100% consistente |
| **Source of truth** | Frontend (localStorage) | Backend (DB) |
| **Persistencia** | Volatile | Persistent |

---

## Resumen

**Filter Preset Global** permite:

1. ✅ **Configurar una vez, usar siempre**
2. ✅ **Auto-aplicar al importar** (sin intervención manual)
3. ✅ **Persistencia en backend** (no localStorage)
4. ✅ **No sobrescribir configuraciones manuales** (respeta stack existente)
5. ✅ **FK CASCADE** (limpieza automática al borrar location)

**Endpoints disponibles:**
- `POST /preset` - Crear/actualizar
- `GET /preset` - Obtener
- `PUT /preset` - Actualizar (alias)
- `DELETE /preset` - Eliminar
- `POST /preset/test` - Dry-run

**Sistema listo para producción.** ✅

---

**Última actualización:** 2026-01-24 00:17 CET
**Autor:** Claude Code
**Deploy:** sha256:9bc9d9ff3b6f...
