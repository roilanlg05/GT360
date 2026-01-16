# Backend: Manejo de Duplicación de Trips

## 📋 Resumen

El backend implementa una **constraint de unicidad** en la tabla `trips` que previene la inserción de trips duplicados. Cuando se intenta subir un archivo Excel con trips que ya existen en la base de datos, el backend devuelve un error HTTP 422 con información detallada sobre el trip duplicado.

---

## 🔒 Constraint de Unicidad

**Ubicación:** [`shared/db/schemas/trips/trips.py:25-30`](../shared/db/schemas/trips/trips.py)

```python
@table("trips", schema="trips", unique_together=[
    "location_id", "pick_up_date",
    "pick_up_time", "airline",
    "flight_number", "pick_up_location",
    "drop_off_location"
])
class Trip(PSQLModel):
    # ...
```

### Campos que conforman la Unique Key

Un trip se considera **duplicado** si ya existe otro trip con **TODOS** estos valores idénticos:

| Campo | Tipo | Ejemplo |
|-------|------|---------|
| `location_id` | UUID | `337c5b6f-6910-49da-a786-591e27a0188a` |
| `pick_up_date` | Date | `2025-06-01` |
| `pick_up_time` | Time | `12:30:00` |
| `airline` | String | `WN` (Southwest Airlines) |
| `flight_number` | String | `3209` |
| `pick_up_location` | String | `SDF` |
| `drop_off_location` | String | `Hyatt Regency Louisville` |

### ¿Por qué este constraint?

Este constraint previene:
- ✅ Subir el mismo archivo Excel múltiples veces
- ✅ Duplicación accidental de trips
- ✅ Conflictos en la programación de drivers
- ✅ Inconsistencias en reportes y estadísticas

---

## ⚠️ Formato del Error del Backend

### HTTP Response

Cuando ocurre un error de duplicación, el backend responde con:

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "detail": "We couldn't validate the schedule: Key (location_id, pick_up_date, pick_up_time, airline, flight_number, pick_up_location, drop_off_location)=(337c5b6f-6910-49da-a786-591e27a0188a, 2025-06-01, 12:30:00, WN, 3209, SDF, Hyatt Regency Louisville) already exists."
}
```

### Ubicación del código

**Archivo:** [`features/trips/routes/trips_router.py:288-302`](../features/trips/routes/trips_router.py)

```python
except Exception as e:
    # Rollback en caso de error
    try:
        await session.rollback()
    except Exception:
        pass

    msg = str(e)
    print(e)
    if "DETAIL:" in msg:
        msg = msg.split("DETAIL:", 1)[1].strip()
    raise HTTPException(
        status_code=422,
        detail=f"We couldn't validate the schedule: {msg}"
    )
```

### Anatomía del Mensaje de Error

```
We couldn't validate the schedule: Key (location_id, pick_up_date, pick_up_time, airline, flight_number, pick_up_location, drop_off_location)=(337c5b6f-6910-49da-a786-591e27a0188a, 2025-06-01, 12:30:00, WN, 3209, SDF, Hyatt Regency Louisville) already exists.
```

**Partes del mensaje:**

1. **Prefijo fijo:** `"We couldn't validate the schedule: "`
2. **Detalle de PostgreSQL:** `"Key (...) already exists."`
3. **Valores del trip duplicado:** Entre paréntesis después del `=`

---

## 🎯 Guía para el Desarrollador Frontend

### 1. Detectar el Error de Duplicación

```typescript
// src/utils/trips-error-parser.ts

interface DuplicateTripError {
  isDuplicate: boolean;
  originalMessage: string;
  month: number;        // 0-11 (formato JavaScript)
  year: number;
  date: string;         // ISO format: "2025-06-01"
  airline: string;      // "WN"
  flightNumber: string; // "3209"
  pickUpLocation: string;
  dropOffLocation: string;
  pickUpTime: string;   // "12:30:00"
}

export function parseDuplicateTripError(errorMessage: string): DuplicateTripError | null {
  // Verificar si es un error de duplicación
  if (!errorMessage.includes("already exists") || !errorMessage.includes("Key (")) {
    return null;
  }

  try {
    // Extraer los valores del error usando regex
    const valuesRegex = /\(([^)]+)\)=\(([^)]+)\) already exists/;
    const match = errorMessage.match(valuesRegex);

    if (!match) return null;

    const keys = match[1].split(', ').map(k => k.trim());
    const values = match[2].split(', ').map(v => v.trim());

    // Crear un objeto con los valores extraídos
    const errorData: Record<string, string> = {};
    keys.forEach((key, index) => {
      errorData[key] = values[index];
    });

    // Parsear la fecha
    const pickUpDate = new Date(errorData.pick_up_date);
    const month = pickUpDate.getMonth(); // 0-11
    const year = pickUpDate.getFullYear();

    return {
      isDuplicate: true,
      originalMessage: errorMessage,
      month,
      year,
      date: errorData.pick_up_date,
      airline: errorData.airline,
      flightNumber: errorData.flight_number,
      pickUpLocation: errorData.pick_up_location,
      dropOffLocation: errorData.drop_off_location,
      pickUpTime: errorData.pick_up_time,
    };
  } catch (e) {
    console.error('[parseDuplicateTripError] Failed to parse error:', e);
    return null;
  }
}
```

### 2. Formatear Mensaje para el Usuario

```typescript
// src/utils/trips-error-formatter.ts

import { parseDuplicateTripError } from './trips-error-parser';

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

const MONTH_NAMES_ES = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
];

export function formatDuplicateTripMessage(
  errorMessage: string,
  locale: 'en' | 'es' = 'en'
): string {
  const parsed = parseDuplicateTripError(errorMessage);

  if (!parsed) {
    // Si no es un error de duplicación reconocido, devolver mensaje genérico
    return locale === 'en'
      ? 'Unable to upload trips. Please check your file and try again.'
      : 'No se pudieron cargar los viajes. Por favor revise el archivo e intente nuevamente.';
  }

  const monthNames = locale === 'en' ? MONTH_NAMES : MONTH_NAMES_ES;
  const monthName = monthNames[parsed.month];

  if (locale === 'en') {
    return `Duplicate trip detected in ${monthName} ${parsed.year}. ` +
           `Flight ${parsed.airline} ${parsed.flightNumber} on ${parsed.date} at ${parsed.pickUpTime} ` +
           `(${parsed.pickUpLocation} → ${parsed.dropOffLocation}) already exists. ` +
           `Please review your file and remove duplicates before uploading.`;
  } else {
    return `Trip duplicado detectado en ${monthName} ${parsed.year}. ` +
           `El vuelo ${parsed.airline} ${parsed.flightNumber} del ${parsed.date} a las ${parsed.pickUpTime} ` +
           `(${parsed.pickUpLocation} → ${parsed.dropOffLocation}) ya existe. ` +
           `Por favor revise el archivo y elimine los duplicados antes de cargar.`;
  }
}
```

### 3. Implementar en el Componente

```typescript
// src/components/trips/update-trips-button.tsx

import { toast } from '@/hooks/use-toast';
import { formatDuplicateTripMessage } from '@/utils/trips-error-formatter';

async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
  const file = event.target.files?.[0];
  if (!file) return;

  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('location_id', locationId);

    const response = await fetch(`${API_URL}/v1/trips/upload-trips`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`
      },
      body: formData
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const errorMessage = errorData.detail || 'Unknown error occurred';

      // Formatear mensaje de error profesional
      const userMessage = formatDuplicateTripMessage(errorMessage, 'en');

      // Mostrar notificación de error
      toast({
        title: "Upload Failed",
        description: userMessage,
        variant: "destructive",
        duration: 8000, // 8 segundos para dar tiempo a leer
      });

      return;
    }

    const data = await response.json();

    // Éxito
    toast({
      title: "Upload Successful",
      description: `${data.uploaded_rows} trips uploaded successfully`,
      variant: "default",
    });

  } catch (error) {
    toast({
      title: "Upload Failed",
      description: "An unexpected error occurred. Please try again.",
      variant: "destructive",
    });
  }
}
```

---

## 📱 Ejemplos de Notificaciones de Usuario

### ❌ Error de Duplicación

```
Title: "Upload Failed"
Description: "Duplicate trip detected in June 2025. Flight WN 3209 on 2025-06-01
at 12:30:00 (SDF → Hyatt Regency Louisville) already exists. Please review your
file and remove duplicates before uploading."
Variant: destructive
Duration: 8000ms
```

### ✅ Éxito

```
Title: "Upload Successful"
Description: "1,247 trips uploaded successfully"
Variant: default
Duration: 5000ms
```

---

## 🎨 UI/UX Recomendaciones

### 1. **Mensaje Claro y Específico**
- ✅ Mencionar el mes y año del trip duplicado
- ✅ Incluir detalles del vuelo (aerolínea, número, fecha, hora)
- ✅ Mostrar origen y destino del trip

### 2. **Acción Sugerida**
- 💡 Sugerir al usuario que revise el archivo Excel
- 💡 Indicar que debe eliminar duplicados antes de reintentar
- 💡 Opcionalmente, ofrecer un botón "View Existing Trips" que filtre por ese mes

### 3. **Duración de la Notificación**
- ⏱️ Errores de duplicación: **8-10 segundos** (mensaje largo, requiere lectura)
- ⏱️ Errores genéricos: **5 segundos**
- ⏱️ Éxitos: **3-5 segundos**

### 4. **Logging**
```typescript
// Registrar el error completo para debugging
console.error('[TripsUpload] Duplicate trip error:', {
  month: parsed.month,
  year: parsed.year,
  airline: parsed.airline,
  flightNumber: parsed.flightNumber,
  date: parsed.date,
  time: parsed.pickUpTime,
  originalError: errorMessage
});
```

---

## 🧪 Casos de Prueba

### Test 1: Subir archivo con trip duplicado

**Setup:**
1. Subir archivo Excel con 100 trips para Junio 2025
2. Subir el mismo archivo nuevamente

**Resultado Esperado:**
- Status: `422 Unprocessable Entity`
- Mensaje: Incluye mes, año, y detalles del primer trip duplicado encontrado
- No se insertó ningún trip (transacción rollback completa)

### Test 2: Archivo parcialmente duplicado

**Setup:**
1. Subir archivo con 100 trips
2. Subir nuevo archivo con 50 trips nuevos + 50 trips del archivo anterior

**Resultado Esperado:**
- Status: `422 Unprocessable Entity`
- Mensaje: Detalles del primer duplicado encontrado
- **Ningún trip se inserta** (batch completo falla, no hay inserción parcial)

### Test 3: Misma fecha pero diferente hora

**Setup:**
- Trip 1: `2025-06-01 12:30:00`
- Trip 2: `2025-06-01 14:45:00` (mismo día, diferente hora)

**Resultado Esperado:**
- ✅ Ambos trips se insertan correctamente (no son duplicados)

---

## 🔄 Comportamiento de Transacciones

### ⚠️ Importante: Transacción "Todo o Nada"

El backend usa transacciones de PostgreSQL, lo que significa:

```python
# En caso de error:
await session.rollback()  # TODOS los trips del batch se descartan
```

**Implicaciones:**

- ✅ Si el archivo tiene **1000 trips** y el trip #500 es duplicado
- ❌ **NINGÚN trip se inserta** (rollback completo)
- 💡 El usuario debe corregir el archivo y volver a subir **todos los trips**

**Mensaje recomendado para el frontend:**

```
"No trips were uploaded due to duplicate entries. Please remove all duplicates
from your file and upload again."
```

---

## 📊 Estadísticas de Errores (Opcional)

Si el backend detecta múltiples duplicados (en el futuro), podría devolver:

```json
{
  "detail": "Multiple duplicate trips found",
  "duplicates": [
    {
      "date": "2025-06-01",
      "month": 5,
      "year": 2025,
      "airline": "WN",
      "flight_number": "3209",
      "count": 3
    },
    {
      "date": "2025-06-15",
      "month": 5,
      "year": 2025,
      "airline": "AA",
      "flight_number": "1234",
      "count": 1
    }
  ]
}
```

**Nota:** Esta funcionalidad **NO está implementada** actualmente. El backend solo reporta el **primer duplicado** encontrado.

---

## 🛠️ Debugging Tips

### Ver el constraint en PostgreSQL

```sql
-- Ver la definición del constraint
SELECT conname, contype, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'trips.trips'::regclass
AND contype = 'u';  -- 'u' = UNIQUE constraint
```

### Buscar trips duplicados manualmente

```sql
-- Encontrar grupos de trips duplicados
SELECT
  location_id,
  pick_up_date,
  pick_up_time,
  airline,
  flight_number,
  pick_up_location,
  drop_off_location,
  COUNT(*) as duplicate_count
FROM trips.trips
GROUP BY
  location_id,
  pick_up_date,
  pick_up_time,
  airline,
  flight_number,
  pick_up_location,
  drop_off_location
HAVING COUNT(*) > 1;
```

---

## 📚 Referencias

- **Modelo Trip:** [`shared/db/schemas/trips/trips.py`](../shared/db/schemas/trips/trips.py)
- **Router Upload:** [`features/trips/routes/trips_router.py`](../features/trips/routes/trips_router.py)
- **PostgreSQL UNIQUE Constraints:** https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-UNIQUE-CONSTRAINTS

---

## 🔄 Historial de Cambios

| Fecha | Versión | Cambios |
|-------|---------|---------|
| 2026-01-15 | 1.0 | Documentación inicial del manejo de duplicados |

---

**Última actualización:** 2026-01-15
**Autor:** Backend Team (Claude Sonnet 4.5)
