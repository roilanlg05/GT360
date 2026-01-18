# Sistema de Formato de Hora - Documentación Completa

## Índice

1. [Resumen Ejecutivo](#resumen-ejecutivo)
2. [Arquitectura del Sistema](#arquitectura-del-sistema)
3. [Componentes](#componentes)
4. [Base de Datos](#base-de-datos)
5. [Flujo de Datos](#flujo-de-datos)
6. [Integración en Endpoints](#integración-en-endpoints)
7. [API Reference](#api-reference)
8. [Guía de Implementación Frontend](#guía-de-implementación-frontend)
9. [Testing](#testing)
10. [FAQ](#faq)

---

## Resumen Ejecutivo

### Problema
Los archivos de trips se suben siempre en formato militar (24h: 16:00, 23:00), pero algunos usuarios prefieren visualizar las horas en formato AM/PM (12h: 04:00 PM, 11:00 PM).

### Solución
Sistema de preferencias por usuario que formatea las horas en el backend antes de enviarlas al frontend. El frontend solo muestra los strings tal como llegan, sin conversión adicional.

### Características Clave
- **Por usuario**: Cada usuario puede elegir su formato preferido
- **Backend-driven**: La conversión ocurre en el servidor
- **Transparente para frontend**: No requiere lógica de conversión en el cliente
- **Default seguro**: Si no hay preferencia, usa formato 24h (militar)
- **Respeta timezone**: Solo cambia el formato visual, no afecta el timezone

---

## Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              FLUJO DE DATOS                              │
└─────────────────────────────────────────────────────────────────────────┘

                    ┌──────────────┐
                    │   Frontend   │
                    │  (Display)   │
                    └──────┬───────┘
                           │ GET /v1/.../trips
                           │ Authorization: Bearer {token}
                           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                              BACKEND (FastAPI)                           │
│                                                                          │
│  ┌─────────────────┐    ┌─────────────────┐    ┌────────────────────┐   │
│  │   Middleware    │───▶│  User Context   │───▶│  Get Time Format   │   │
│  │  (verify_token) │    │ (request.state) │    │  (24h or 12h)      │   │
│  └─────────────────┘    └─────────────────┘    └─────────┬──────────┘   │
│                                                          │              │
│  ┌─────────────────┐    ┌─────────────────┐              │              │
│  │   Trip Model    │───▶│  Serialization  │◀─────────────┘              │
│  │ (pick_up_time:  │    │    Helper       │                             │
│  │   time object)  │    │                 │                             │
│  └─────────────────┘    └────────┬────────┘                             │
│                                  │                                       │
│                                  ▼                                       │
│                         ┌─────────────────┐                             │
│                         │ Time Formatter  │                             │
│                         │ format_time()   │                             │
│                         └────────┬────────┘                             │
│                                  │                                       │
└──────────────────────────────────┼───────────────────────────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │     Response JSON        │
                    │ {"pick_up_time": "16:30"}│  ◀── Usuario 24h
                    │         OR               │
                    │ {"pick_up_time":         │
                    │   "04:30 PM"}            │  ◀── Usuario 12h
                    └──────────────────────────┘
```

---

## Componentes

### 1. Modelo de Base de Datos

**Archivo**: `shared/db/schemas/settings/user_settings.py`

```python
from psqlmodel import Column, PSQLModel, table
from psqlmodel.utils import now
from psqlmodel.orm.types import timestamptz, uuid

class TimeFormat:
    H24 = "24h"
    H12 = "12h"


@table(name="user_settings", schema="settings")
class UserSettings(PSQLModel):
    """
    User preference settings table.
    Stores user-specific preferences like time format display.
    """

    user_id: uuid = Column(
        foreign_key="entities.users.id",
        on_delete="CASCADE",
        primary_key=True
    )

    time_format: str = Column(
        max_len=10,
        default=TimeFormat.H24,
        nullable=False,
        index=True
    )

    created_at: timestamptz = Column(
        default=now,
        nullable=False,
        index=True
    )

    updated_at: timestamptz = Column(
        default=now,
        nullable=False,
        index=True
    )
```

**Exportación**: `shared/db/schemas/settings/__init__.py`
```python
from .user_settings import UserSettings

__all__ = ["UserSettings"]
```

---

### 2. Utilidad de Formateo

**Archivo**: `shared/utils/time_formatter.py`

```python
from datetime import time
from typing import Optional


def format_time(t: Optional[time], format_type: str = "24h") -> Optional[str]:
    """
    Formatea un objeto time según el formato especificado.

    Args:
        t: Objeto time de Python
        format_type: "24h" (militar) o "12h" (AM/PM)

    Returns:
        String formateado o None si t es None

    Examples:
        format_time(time(16, 30), "24h") -> "16:30"
        format_time(time(16, 30), "12h") -> "04:30 PM"
        format_time(time(0, 0), "12h") -> "12:00 AM"
        format_time(time(12, 0), "12h") -> "12:00 PM"
    """
    if t is None:
        return None

    if format_type == "24h":
        # Formato militar: HH:MM (sin segundos)
        return t.strftime("%H:%M")

    elif format_type == "12h":
        # Formato AM/PM: hh:MM AM/PM (sin segundos)
        return t.strftime("%I:%M %p")

    else:
        # Default: formato militar
        return t.strftime("%H:%M")
```

**Formatos de salida**:

| Input | format_type | Output |
|-------|-------------|--------|
| `time(16, 30)` | `"24h"` | `"16:30"` |
| `time(16, 30)` | `"12h"` | `"04:30 PM"` |
| `time(0, 0)` | `"24h"` | `"00:00"` |
| `time(0, 0)` | `"12h"` | `"12:00 AM"` |
| `time(12, 0)` | `"24h"` | `"12:00"` |
| `time(12, 0)` | `"12h"` | `"12:00 PM"` |
| `time(23, 45)` | `"24h"` | `"23:45"` |
| `time(23, 45)` | `"12h"` | `"11:45 PM"` |
| `None` | cualquiera | `None` |

---

### 3. Middleware de Contexto de Usuario

**Archivo**: `shared/middlewares/user_context.py`

```python
from fastapi import Request
from psqlmodel import AsyncSession, Select
from shared.db.schemas import UserSettings
from uuid import UUID
import logging

logger = logging.getLogger(__name__)


async def get_user_time_format(request: Request, session: AsyncSession) -> str:
    """
    Obtiene la preferencia de formato de hora del usuario actual.

    Returns:
        "24h" o "12h" (default: "24h")
    """
    try:
        # El middleware verify_token ya pone user_data en request.state
        user_data = getattr(request.state, "user_data", None)
        if not user_data:
            return "24h"  # Default si no hay usuario autenticado

        user_id = user_data.get("id")
        if not user_id:
            return "24h"

        user_uuid = UUID(user_id)

        # Buscar settings del usuario
        settings = await session.exec(
            Select(UserSettings).Where(UserSettings.user_id == user_uuid)
        ).first()

        if settings and settings.time_format:
            return settings.time_format

        # Default si no tiene settings
        return "24h"

    except Exception as e:
        logger.error(f"Error getting user time format: {e}")
        return "24h"  # Fallback seguro
```

**Comportamiento**:
- Obtiene `user_data` del `request.state` (puesto por `verify_token` middleware)
- Busca el registro de `UserSettings` para ese usuario
- Retorna `"24h"` como fallback en cualquier error o ausencia de datos

---

### 4. Dependency de FastAPI

**Archivo**: `shared/dependencies/user_preferences.py`

```python
from fastapi import Request, Depends
from psqlmodel import AsyncSession
from shared.db.db_config import get_db
from shared.middlewares.user_context import get_user_time_format


async def get_current_time_format(
    request: Request,
    session: AsyncSession = Depends(get_db)
) -> str:
    """
    Dependency para obtener el formato de hora preferido del usuario actual.

    Usage:
        @router.get("/endpoint")
        async def endpoint(time_format: str = Depends(get_current_time_format)):
            # Use time_format for formatting
    """
    return await get_user_time_format(request, session)
```

**Uso en endpoints**:
```python
@router.get("/v1/trips")
async def get_trips(
    time_format: str = Depends(get_current_time_format)
):
    # time_format será "24h" o "12h"
    ...
```

---

### 5. Helper de Serialización

**Archivo**: `shared/utils/serialization.py`

```python
from typing import Any, Dict
from datetime import time
from shared.utils.time_formatter import format_time


def model_dump_with_time_format(
    model: Any,
    time_format: str = "24h",
    mode: str = "json"
) -> Dict[str, Any]:
    """
    Serializa un modelo Pydantic/SQLModel aplicando formato de hora.

    Args:
        model: Modelo a serializar
        time_format: "24h" o "12h"
        mode: Modo de serialización (default: "json")

    Returns:
        Dict con campos de tiempo formateados
    """
    # Serializar el modelo normalmente
    data = model.model_dump(mode=mode)

    # Iterar sobre campos y formatear los de tipo time
    for key, value in data.items():
        # Obtener el campo original del modelo para verificar el tipo
        model_field = getattr(model, key, None)

        # Si es un campo time, aplicar formato
        if isinstance(model_field, time):
            data[key] = format_time(model_field, time_format)

    return data


def serialize_trips_with_format(trips: list, time_format: str = "24h") -> list:
    """
    Helper específico para serializar lista de trips con formato de hora.
    """
    return [
        model_dump_with_time_format(trip, time_format)
        for trip in trips
    ]
```

**Ejemplo de uso**:
```python
# Sin formateo (default)
trip.model_dump(mode="json")
# Output: {"pick_up_time": "16:30:00", ...}

# Con formateo 24h
model_dump_with_time_format(trip, "24h")
# Output: {"pick_up_time": "16:30", ...}

# Con formateo 12h
model_dump_with_time_format(trip, "12h")
# Output: {"pick_up_time": "04:30 PM", ...}
```

---

### 6. Modelos Pydantic para API

**Archivo**: `features/profile/models/profile_models.py`

```python
from pydantic import BaseModel, field_validator


class UserSettingsResponse(BaseModel):
    """User settings response."""
    user_id: str
    time_format: str  # "24h" or "12h"
    created_at: str
    updated_at: str


class UserSettingsUpdate(BaseModel):
    """Fields that can be updated in user settings."""
    time_format: str

    @field_validator("time_format")
    @classmethod
    def validate_time_format(cls, v):
        if v not in ["24h", "12h"]:
            raise ValueError("time_format debe ser '24h' o '12h'")
        return v
```

---

## Base de Datos

### Schema SQL

```sql
-- Crear schema si no existe
CREATE SCHEMA IF NOT EXISTS settings;

-- Tabla de preferencias de usuario
CREATE TABLE IF NOT EXISTS settings.user_settings (
    user_id UUID PRIMARY KEY REFERENCES entities.users(id) ON DELETE CASCADE,
    time_format VARCHAR(10) NOT NULL DEFAULT '24h'
        CHECK (time_format IN ('24h', '12h')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_user_settings_user_id
    ON settings.user_settings(user_id);
CREATE INDEX IF NOT EXISTS idx_user_settings_time_format
    ON settings.user_settings(time_format);
```

### Diagrama ER

```
┌─────────────────────────────┐         ┌─────────────────────────────┐
│      entities.users         │         │   settings.user_settings    │
├─────────────────────────────┤         ├─────────────────────────────┤
│ id: UUID (PK)               │◀────────│ user_id: UUID (PK, FK)      │
│ email: VARCHAR              │  1:1    │ time_format: VARCHAR(10)    │
│ first_name: VARCHAR         │         │ created_at: TIMESTAMPTZ     │
│ last_name: VARCHAR          │         │ updated_at: TIMESTAMPTZ     │
│ ...                         │         │                             │
└─────────────────────────────┘         └─────────────────────────────┘
```

### Relación con Usuario

- **Relación**: One-to-One (1:1)
- **Constraint**: `ON DELETE CASCADE` - Si se elimina el usuario, se eliminan sus settings
- **Creación**: Lazy - Se crea solo cuando el usuario solicita/modifica sus settings

---

## Flujo de Datos

### 1. Usuario Cambia Preferencia

```
Frontend                           Backend                          Database
   │                                  │                                 │
   │ PATCH /v1/profile/settings       │                                 │
   │ {"time_format": "12h"}          │                                 │
   │────────────────────────────────▶│                                 │
   │                                  │                                 │
   │                                  │ SELECT * FROM user_settings    │
   │                                  │ WHERE user_id = $1             │
   │                                  │────────────────────────────────▶│
   │                                  │                                 │
   │                                  │◀────────────────────────────────│
   │                                  │ (settings or null)              │
   │                                  │                                 │
   │                                  │ INSERT/UPDATE user_settings    │
   │                                  │ SET time_format = '12h'        │
   │                                  │────────────────────────────────▶│
   │                                  │                                 │
   │                                  │◀────────────────────────────────│
   │                                  │                                 │
   │ {"user_id": "...",              │                                 │
   │  "time_format": "12h", ...}     │                                 │
   │◀────────────────────────────────│                                 │
   │                                  │                                 │
```

### 2. Usuario Solicita Trips

```
Frontend                           Backend                          Database
   │                                  │                                 │
   │ GET /v1/locations/{id}/trips    │                                 │
   │ Authorization: Bearer {token}    │                                 │
   │────────────────────────────────▶│                                 │
   │                                  │                                 │
   │                                  │──── verify_token ────▶         │
   │                                  │     request.state.user_data    │
   │                                  │                                 │
   │                                  │ SELECT time_format             │
   │                                  │ FROM user_settings             │
   │                                  │ WHERE user_id = $1             │
   │                                  │────────────────────────────────▶│
   │                                  │                                 │
   │                                  │◀──── "12h" ─────────────────────│
   │                                  │                                 │
   │                                  │ SELECT * FROM trips WHERE ...  │
   │                                  │────────────────────────────────▶│
   │                                  │                                 │
   │                                  │◀──── trips data ────────────────│
   │                                  │                                 │
   │                                  │──── format_time(               │
   │                                  │       trip.pick_up_time, "12h")│
   │                                  │                                 │
   │ [{"pick_up_time": "04:30 PM",   │                                 │
   │   "hotel_name": "...", ...}]    │                                 │
   │◀────────────────────────────────│                                 │
   │                                  │                                 │
```

---

## Integración en Endpoints

### Endpoints de Trips Modificados

El archivo `features/trips/routes/trips_router.py` fue modificado en los siguientes puntos:

#### Imports agregados (líneas 8-9)
```python
from shared.middlewares.user_context import get_user_time_format
from shared.utils.serialization import model_dump_with_time_format
```

#### 1. POST /v1/trips/upload-trips (línea ~213)
```python
# Obtener preferencia del usuario
time_format = await get_user_time_format(request, session)
trips = [model_dump_with_time_format(t, time_format) for t in trips_objs]
```

#### 2. POST /v1/locations/{location_id}/trips (línea ~373)
```python
time_format = await get_user_time_format(request, session)
trip_json = model_dump_with_time_format(trip, time_format)
```

#### 3. GET /v1/locations/{location_id}/trips (línea ~510)
```python
time_format = await get_user_time_format(request, session)
for row in result:
    trips.append(model_dump_with_time_format(row[0], time_format))
```

#### 4. PATCH /v1/locations/{location_id}/trips/{trip_id} (línea ~679)
```python
time_format = await get_user_time_format(request, session)
trip = model_dump_with_time_format(trip, time_format)
```

#### 5. POST .../filters/preview (línea ~1151)
```python
time_format = await get_user_time_format(request, session)
service = TripFilterService(session)
result = await service.preview(location_uuid, airline, filters, time_format)
```

#### 6. POST .../filters/apply (línea ~1207)
```python
time_format = await get_user_time_format(request, session)
service = TripFilterService(session)
result = await service.apply(location_uuid, airline, filters, time_format)
```

#### 7. PATCH .../trips/{trip_id}/assign (línea ~1466)
```python
time_format = await get_user_time_format(request, session)
return {
    "status": "ok",
    "data": model_dump_with_time_format(trip, time_format),
}
```

#### 8. GET .../trips/search (línea ~1561)
```python
time_format = await get_user_time_format(request, session)
return {
    "status": "ok",
    "data": model_dump_with_time_format(trip, time_format),
}
```

### Servicio de Filtros

El archivo `features/trips/services/trip_filter_service.py` integra el formateo:

#### Import (línea 49)
```python
from shared.utils.time_formatter import format_time
```

#### Método preview() (línea 83-158)
```python
async def preview(
    self,
    location_id: UUID,
    airline: str,
    config: FilterRequest,
    time_format: str = "24h",  # Nuevo parámetro
) -> FilterPreviewResult:
    # ... lógica existente ...

    # Format time fields according to user preference
    formatted_changes = self._format_changes(self.changes, time_format)

    return FilterPreviewResult(
        changes=formatted_changes,  # Cambios formateados
        # ...
    )
```

#### Método apply() (línea 160-277)
```python
async def apply(
    self,
    location_id: UUID,
    airline: str,
    config: FilterRequest,
    time_format: str = "24h",  # Nuevo parámetro
) -> FilterApplyResult:
    # ... lógica existente ...
```

#### Método _format_changes() (línea 830-854)
```python
def _format_changes(self, changes: list[TripChange], time_format: str) -> list[TripChange]:
    """
    Format time fields in TripChange objects according to user preference.
    """
    formatted_changes = []
    for change in changes:
        formatted_change = TripChange(
            trip_id=change.trip_id,
            original_time=format_time(change.original_time, time_format),
            new_time=format_time(change.new_time, time_format),
            filter_applied=change.filter_applied,
            hotel_name=change.hotel_name,
            pick_up_date=change.pick_up_date,
            airline=change.airline,
        )
        formatted_changes.append(formatted_change)
    return formatted_changes
```

---

## API Reference

### GET /v1/profile/settings

Obtiene las preferencias del usuario actual.

**Headers**:
```
Authorization: Bearer {token}
```

**Response** (200 OK):
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "time_format": "24h",
  "created_at": "2026-01-17T10:30:00+00:00",
  "updated_at": "2026-01-17T10:30:00+00:00"
}
```

**Comportamiento**:
- Si el usuario no tiene settings, se crean automáticamente con valores default
- Default `time_format`: `"24h"`

---

### PATCH /v1/profile/settings

Actualiza las preferencias del usuario actual.

**Headers**:
```
Authorization: Bearer {token}
Content-Type: application/json
```

**Request Body**:
```json
{
  "time_format": "12h"
}
```

**Validación**:
- `time_format` debe ser `"24h"` o `"12h"`
- Cualquier otro valor retorna error 422

**Response** (200 OK):
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "time_format": "12h",
  "created_at": "2026-01-17T10:30:00+00:00",
  "updated_at": "2026-01-17T15:45:00+00:00"
}
```

**Errores**:
```json
// 422 Unprocessable Entity
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "time_format"],
      "msg": "Value error, time_format debe ser '24h' o '12h'"
    }
  ]
}
```

---

## Guía de Implementación Frontend

### Principio Fundamental

**El frontend NO necesita hacer conversión de horas.** El backend envía las horas ya formateadas según la preferencia del usuario.

### Interfaces TypeScript

```typescript
// types/trip.ts
interface Trip {
  id: string;
  pick_up_time: string;   // "16:30" o "04:30 PM" (ya formateado)
  pick_up_date: string;
  pick_up_location: string;
  airline: string;
  // ...
}

// types/settings.ts
interface UserSettings {
  user_id: string;
  time_format: "24h" | "12h";
  created_at: string;
  updated_at: string;
}

interface UserSettingsUpdate {
  time_format: "24h" | "12h";
}
```

### Mostrar Datos (Solo Display)

```tsx
// components/TripCard.tsx
interface TripCardProps {
  trip: Trip;
}

export function TripCard({ trip }: TripCardProps) {
  return (
    <div className="trip-card">
      <h3>{trip.pick_up_location}</h3>

      {/* NO convertir, solo mostrar */}
      <p className="time">{trip.pick_up_time}</p>

      <p className="date">{trip.pick_up_date}</p>
    </div>
  );
}
```

### Cambiar Preferencia de Usuario

```typescript
// services/settings.ts
import { api } from './api';

export async function updateTimeFormat(format: "24h" | "12h") {
  const response = await api.patch('/v1/profile/settings', {
    time_format: format
  });
  return response.data;
}

export async function getSettings() {
  const response = await api.get('/v1/profile/settings');
  return response.data;
}
```

```tsx
// components/SettingsPage.tsx
import { useState, useEffect } from 'react';
import { getSettings, updateTimeFormat } from '../services/settings';

export function SettingsPage() {
  const [timeFormat, setTimeFormat] = useState<"24h" | "12h">("24h");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const settings = await getSettings();
      setTimeFormat(settings.time_format);
    } finally {
      setLoading(false);
    }
  };

  const handleChange = async (format: "24h" | "12h") => {
    setLoading(true);
    try {
      await updateTimeFormat(format);
      setTimeFormat(format);
      // Opcional: Refrescar datos que muestran horas
      window.location.reload();
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <Spinner />;

  return (
    <div className="settings-page">
      <h2>Time Format</h2>

      <div className="format-options">
        <label>
          <input
            type="radio"
            name="timeFormat"
            value="24h"
            checked={timeFormat === "24h"}
            onChange={() => handleChange("24h")}
          />
          24 hours (Military) - 16:30
        </label>

        <label>
          <input
            type="radio"
            name="timeFormat"
            value="12h"
            checked={timeFormat === "12h"}
            onChange={() => handleChange("12h")}
          />
          12 hours (AM/PM) - 04:30 PM
        </label>
      </div>
    </div>
  );
}
```

### Comparación de Tiempos (Si Necesario)

Si el frontend necesita comparar horas (ordenar, calcular diferencias), puede usar este helper:

```typescript
// utils/timeUtils.ts

/**
 * Parsea un string de hora a minutos desde medianoche.
 * Soporta ambos formatos: "16:30" y "04:30 PM"
 */
export function parseTimeToMinutes(timeStr: string): number {
  const is12h = /AM|PM/i.test(timeStr);

  if (is12h) {
    // Parsear formato 12h: "04:30 PM"
    const match = timeStr.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/i);
    if (!match) return 0;

    let hours = parseInt(match[1]);
    const minutes = parseInt(match[2]);
    const period = match[3].toUpperCase();

    if (period === 'PM' && hours !== 12) hours += 12;
    if (period === 'AM' && hours === 12) hours = 0;

    return hours * 60 + minutes;
  } else {
    // Parsear formato 24h: "16:30"
    const [hours, minutes] = timeStr.split(':').map(Number);
    return hours * 60 + minutes;
  }
}

/**
 * Calcula la diferencia en minutos entre dos horas.
 */
export function getTimeDifference(time1: string, time2: string): number {
  const minutes1 = parseTimeToMinutes(time1);
  const minutes2 = parseTimeToMinutes(time2);
  return Math.abs(minutes2 - minutes1);
}

/**
 * Compara dos horas para ordenamiento.
 * Retorna: negativo si a < b, positivo si a > b, 0 si iguales
 */
export function compareTime(a: string, b: string): number {
  return parseTimeToMinutes(a) - parseTimeToMinutes(b);
}

// Uso
const trips = [...];
const sorted = trips.sort((a, b) => compareTime(a.pick_up_time, b.pick_up_time));

const diff = getTimeDifference("04:30 PM", "05:00 PM");
console.log(`Diferencia: ${diff} minutos`); // 30 minutos
```

---

## Testing

### Pruebas Manuales con cURL

#### 1. Obtener settings actuales
```bash
curl -X GET "http://localhost:8000/v1/profile/settings" \
  -H "Authorization: Bearer {token}"
```

#### 2. Cambiar a formato 12h
```bash
curl -X PATCH "http://localhost:8000/v1/profile/settings" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{"time_format": "12h"}'
```

#### 3. Verificar trips con formato 12h
```bash
curl -X GET "http://localhost:8000/v1/locations/{location_id}/trips" \
  -H "Authorization: Bearer {token}"

# Esperado: {"pick_up_time": "04:30 PM", ...}
```

#### 4. Cambiar a formato 24h
```bash
curl -X PATCH "http://localhost:8000/v1/profile/settings" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{"time_format": "24h"}'
```

#### 5. Verificar trips con formato 24h
```bash
curl -X GET "http://localhost:8000/v1/locations/{location_id}/trips" \
  -H "Authorization: Bearer {token}"

# Esperado: {"pick_up_time": "16:30", ...}
```

### Verificación de Base de Datos

```bash
# Conectar a PostgreSQL
docker exec -it postgres psql -U gt360 -d gt360

# Ver tabla de settings
SELECT * FROM settings.user_settings;

# Ver settings de un usuario específico
SELECT * FROM settings.user_settings
WHERE user_id = '550e8400-e29b-41d4-a716-446655440000';
```

---

## FAQ

### ¿El frontend necesita enviar el formato en cada request?

**NO.** El backend detecta automáticamente la preferencia del usuario desde el token de autenticación.

### ¿Qué pasa si el usuario no tiene settings?

Se usa `"24h"` como default. Cuando el usuario accede a GET /v1/profile/settings, se crean automáticamente los settings con valores default.

### ¿El formato afecta el timezone?

**NO.** El formato de hora (24h vs 12h) solo afecta la visualización. Las horas siguen respetando el timezone de la location.

### ¿Los archivos Excel deben cambiar?

**NO.** Los archivos Excel SIEMPRE se suben en formato militar (24h). El sistema solo cambia la visualización en las respuestas de la API.

### ¿Qué pasa si hay un error al obtener la preferencia?

El sistema usa `"24h"` como fallback seguro en cualquier caso de error.

### ¿Los endpoints de filtros también formatean las horas?

**SÍ.** Los endpoints `/preview` y `/apply` formatean los campos `original_time` y `new_time` según la preferencia del usuario.

### ¿Cómo afecta a los logs del endpoint /apply?

Los logs internos almacenan las horas sin formato (como strings de los objetos time). Solo la respuesta al cliente se formatea.

### ¿Puedo forzar un formato específico en un request?

**NO.** El formato siempre se basa en la preferencia del usuario almacenada en la base de datos. No hay override por request.

---

## Estructura de Archivos

```
GT360/
├── shared/
│   ├── db/
│   │   └── schemas/
│   │       ├── __init__.py          # Export de UserSettings
│   │       └── settings/
│   │           ├── __init__.py      # Export local
│   │           └── user_settings.py # Modelo PSQLModel
│   │
│   ├── utils/
│   │   ├── time_formatter.py        # Función format_time()
│   │   └── serialization.py         # Helper model_dump_with_time_format()
│   │
│   ├── middlewares/
│   │   └── user_context.py          # Función get_user_time_format()
│   │
│   └── dependencies/
│       └── user_preferences.py      # Dependency get_current_time_format()
│
├── features/
│   ├── profile/
│   │   ├── models/
│   │   │   └── profile_models.py    # UserSettingsResponse, UserSettingsUpdate
│   │   └── routes/
│   │       └── profile_router.py    # Endpoints GET/PATCH /v1/profile/settings
│   │
│   └── trips/
│       ├── routes/
│       │   └── trips_router.py      # Integración de formateo
│       └── services/
│           └── trip_filter_service.py # Formateo en preview/apply
│
└── docs/
    ├── FRONTEND_GROUND_FILTERS_TIME_FORMAT_UPDATE.md
    ├── FRONTEND_TIME_FORMAT_IMPLEMENTATION_GUIDE.md
    └── TIME_FORMAT_SYSTEM_COMPLETE.md  # Este archivo
```

---

**Fecha de Creación**: 2026-01-17
**Última Actualización**: 2026-01-18
**Versión**: 1.0.0
