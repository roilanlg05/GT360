# Edit Driver Details Endpoint - Integration Guide

## Overview

Endpoint para editar los detalles de un driver. Soporta dos roles con permisos diferenciados:
- **Manager**: puede cambiar `location_id`, `pay_type`, `pay_frequency`, `rate`, `is_active`, `profile_pic_url` de cualquier driver de su organizacion
- **Driver**: solo puede cambiar `profile_pic_url` (su propia foto de perfil)
- **Nadie** puede cambiar `organization_id`

---

## Endpoint

```
PATCH /v1/drivers/{driver_id}
```

### Autenticacion
- Requiere token JWT valido
- Roles permitidos: `manager`, `driver`

---

## Parametros

### Path Parameters

| Parametro | Tipo | Requerido | Descripcion |
|-----------|------|-----------|-------------|
| `driver_id` | UUID | **Si** | ID del driver a editar |

### Request Body (JSON)

Todos los campos son opcionales. Solo se actualizan los campos enviados (semantica PATCH).

| Campo | Tipo | Requerido | Valores | Descripcion |
|-------|------|-----------|---------|-------------|
| `location_id` | string (UUID) | No | UUID valido | Nueva location asignada al driver |
| `pay_type` | string | No | `day`, `hour`, `trip` | Tipo de pago del driver |
| `pay_frequency` | string | No | `daily`, `weekly`, `biweekly` | Frecuencia de pago del driver |
| `rate` | number (decimal) | No | Cualquier valor positivo | Tarifa de pago segun el pay_type (ej: 25.00 por hora) |
| `is_active` | boolean | No | `true`, `false` | Estado activo/inactivo del driver |
| `profile_pic_url` | string | No | URL valida | URL de la foto de perfil del driver |
| `shift_start_time` | string (HH:MM) | No | Hora valida (ej: `"08:00"`) | Hora de inicio del turno programado |
| `shift_end_time` | string (HH:MM) | No | Hora valida (ej: `"20:00"`) | Hora de fin del turno programado |
| `work_days` | array of strings | No | `["mon","tue","wed","thu","fri","sat","sun"]` | Dias de la semana que trabaja el driver |

#### Ejemplo Request Body (Manager)

```json
{
  "location_id": "660e8400-e29b-41d4-a716-446655440001",
  "pay_type": "hour",
  "pay_frequency": "weekly",
  "rate": 25.00,
  "is_active": true,
  "shift_start_time": "08:00",
  "shift_end_time": "20:00",
  "work_days": ["mon", "tue", "wed", "thu", "fri"]
}
```

#### Ejemplo Request Body (Driver)

```json
{
  "profile_pic_url": "https://storage.example.com/drivers/photo.jpg"
}
```

---

## Reglas de Negocio por Rol

### Manager

| Regla | Descripcion |
|-------|-------------|
| Campos permitidos | `location_id`, `pay_type`, `pay_frequency`, `rate`, `is_active`, `profile_pic_url`, `shift_start_time`, `shift_end_time`, `work_days` |
| Restriccion de organizacion | Solo puede editar drivers de su misma organizacion |
| Validacion de location | El `location_id` debe existir y pertenecer a la misma organizacion del driver |
| Validacion de horario | `shift_start_time` y `shift_end_time` deben ambos estar seteados o ambos ser null |
| Validacion de work_days | Valores deben ser de: `mon`, `tue`, `wed`, `thu`, `fri`, `sat`, `sun` |

### Driver

| Regla | Descripcion |
|-------|-------------|
| Campos permitidos | Solo `profile_pic_url` |
| Restriccion de identidad | Solo puede editarse a si mismo (`driver_id == user_id`) |
| Campos prohibidos | Enviar `location_id`, `pay_type`, `pay_frequency`, `rate` o `is_active` retorna 403 |

---

## Response

### Success Response (200)

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "first_name": "John",
  "last_name": "Doe",
  "email": "john.doe@example.com",
  "phone": "+15028306579",
  "profile_pic": "https://example.com/pic.jpg",
  "is_active": true,
  "pay_type": "hour",
  "pay_frequency": "weekly",
  "rate": 25.00,
  "location_id": "660e8400-e29b-41d4-a716-446655440001",
  "organization_id": "770e8400-e29b-41d4-a716-446655440002",
  "shift_start_time": "08:00",
  "shift_end_time": "20:00",
  "work_days": ["mon", "tue", "wed", "thu", "fri"],
  "created_at": "2026-01-23T10:30:00"
}
```

### Response Fields

| Campo | Tipo | Nullable | Descripcion |
|-------|------|----------|-------------|
| `id` | string (UUID) | No | ID unico del driver |
| `first_name` | string | Si | Nombre del driver |
| `last_name` | string | Si | Apellido del driver |
| `email` | string | No | Email del driver |
| `phone` | string | Si | Telefono del driver |
| `profile_pic` | string | Si | URL de la foto de perfil (de tabla users) |
| `is_active` | boolean | No | Estado activo/inactivo |
| `pay_type` | string | Si | Tipo de pago: `day`, `hour`, `trip` |
| `pay_frequency` | string | Si | Frecuencia de pago: `daily`, `weekly`, `biweekly` |
| `rate` | number | Si | Tarifa de pago segun el pay_type |
| `location_id` | string (UUID) | Si | ID de la location asignada |
| `organization_id` | string (UUID) | Si | ID de la organizacion |
| `shift_start_time` | string (HH:MM) | Si | Hora de inicio del turno programado |
| `shift_end_time` | string (HH:MM) | Si | Hora de fin del turno programado |
| `work_days` | array of strings | Si | Dias de la semana que trabaja (ej: `["mon","tue","wed","thu","fri"]`) |
| `created_at` | string (ISO 8601) | No | Fecha de creacion |

---

## Error Responses

### 400 Bad Request - No fields to update

```json
{
  "detail": "No fields to update"
}
```

### 400 Bad Request - Invalid location

```json
{
  "detail": "Location not found or does not belong to this organization"
}
```

### 400 Bad Request - Invalid location_id format

```json
{
  "detail": "Invalid location_id format"
}
```

### 400 Bad Request - Mismatched shift times

```json
{
  "detail": "shift_start_time and shift_end_time must both be set or both null"
}
```

### 400 Bad Request - Invalid work day

```json
{
  "detail": "Invalid work day 'xyz'. Must be one of: mon, tue, wed, thu, fri, sat, sun"
}
```

### 401 Unauthorized

```json
{
  "detail": "Missing or invalid authentication"
}
```

### 403 Forbidden - Driver editing another driver

```json
{
  "detail": "You can only edit your own profile"
}
```

### 403 Forbidden - Driver sending restricted fields

```json
{
  "detail": "Drivers can only update profile_pic_url"
}
```

### 403 Forbidden - Manager editing driver from another org

```json
{
  "detail": "Driver does not belong to your organization"
}
```

### 404 Not Found

```json
{
  "detail": "Driver not found"
}
```

### 422 Unprocessable Entity - Invalid pay_type

```json
{
  "detail": [
    {
      "type": "enum",
      "loc": ["body", "pay_type"],
      "msg": "Input should be 'day', 'hour' or 'trip'",
      "input": "invalid_value"
    }
  ]
}
```

### 422 Unprocessable Entity - Invalid pay_frequency

```json
{
  "detail": [
    {
      "type": "enum",
      "loc": ["body", "pay_frequency"],
      "msg": "Input should be 'daily', 'weekly' or 'biweekly'",
      "input": "invalid_value"
    }
  ]
}
```

---

## Frontend Implementation

### TypeScript Interfaces

```typescript
interface DriverDetailsUpdate {
  location_id?: string;
  pay_type?: 'day' | 'hour' | 'trip';
  pay_frequency?: 'daily' | 'weekly' | 'biweekly';
  rate?: number;
  is_active?: boolean;
  profile_pic_url?: string;
  shift_start_time?: string;  // "HH:MM" format, e.g. "08:00"
  shift_end_time?: string;    // "HH:MM" format, e.g. "20:00"
  work_days?: ('mon' | 'tue' | 'wed' | 'thu' | 'fri' | 'sat' | 'sun')[];
}

interface DriverResponse {
  id: string;
  first_name: string | null;
  last_name: string | null;
  email: string;
  phone: string | null;
  profile_pic: string | null;
  is_active: boolean;
  pay_type: 'day' | 'hour' | 'trip' | null;
  pay_frequency: 'daily' | 'weekly' | 'biweekly' | null;
  rate: number | null;
  location_id: string | null;
  organization_id: string | null;
  shift_start_time: string | null;  // "HH:MM" or null
  shift_end_time: string | null;    // "HH:MM" or null
  work_days: string[] | null;       // e.g. ["mon","tue","wed","thu","fri"]
  created_at: string;
}
```

### API Service

```typescript
const API_BASE = 'https://api.gt360.app';

async function updateDriverDetails(
  driverId: string,
  data: DriverDetailsUpdate,
  token: string
): Promise<DriverResponse> {
  const response = await fetch(`${API_BASE}/v1/drivers/${driverId}`, {
    method: 'PATCH',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to update driver');
  }

  return response.json();
}
```

### React Hook Example

```typescript
import { useState, useCallback } from 'react';

interface UseUpdateDriverOptions {
  token: string;
  onSuccess?: (driver: DriverResponse) => void;
  onError?: (error: string) => void;
}

function useUpdateDriver({ token, onSuccess, onError }: UseUpdateDriverOptions) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateDriver = useCallback(async (
    driverId: string,
    data: DriverDetailsUpdate
  ) => {
    setLoading(true);
    setError(null);

    try {
      const updatedDriver = await updateDriverDetails(driverId, data, token);
      onSuccess?.(updatedDriver);
      return updatedDriver;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      onError?.(message);
      return null;
    } finally {
      setLoading(false);
    }
  }, [token, onSuccess, onError]);

  return { updateDriver, loading, error };
}
```

---

## Mobile Implementation

### Kotlin (Android)

```kotlin
data class DriverDetailsUpdate(
    val location_id: String? = null,
    val pay_type: String? = null,
    val pay_frequency: String? = null,
    val rate: Double? = null,
    val is_active: Boolean? = null,
    val profile_pic_url: String? = null,
    val shift_start_time: String? = null,  // "HH:MM"
    val shift_end_time: String? = null,    // "HH:MM"
    val work_days: List<String>? = null    // ["mon","tue",...]
)

data class DriverResponse(
    val id: String,
    val first_name: String?,
    val last_name: String?,
    val email: String,
    val phone: String?,
    val profile_pic: String?,
    val is_active: Boolean,
    val pay_type: String?,
    val pay_frequency: String?,
    val rate: Double?,
    val location_id: String?,
    val organization_id: String?,
    val shift_start_time: String?,
    val shift_end_time: String?,
    val work_days: List<String>?,
    val created_at: String
)

suspend fun updateDriverDetails(
    driverId: String,
    data: DriverDetailsUpdate,
    token: String
): Result<DriverResponse> {
    return try {
        val response = httpClient.patch("$BASE_URL/v1/drivers/$driverId") {
            header("Authorization", "Bearer $token")
            contentType(ContentType.Application.Json)
            setBody(data)
        }

        if (response.status == HttpStatusCode.OK) {
            val driver = response.body<DriverResponse>()
            Result.success(driver)
        } else {
            val error = response.body<ErrorResponse>()
            Result.failure(Exception(error.detail))
        }
    } catch (e: Exception) {
        Result.failure(e)
    }
}
```

### Swift (iOS)

```swift
struct DriverDetailsUpdate: Codable {
    var locationId: String?
    var payType: String?
    var payFrequency: String?
    var rate: Double?
    var isActive: Bool?
    var profilePicUrl: String?
    var shiftStartTime: String?
    var shiftEndTime: String?
    var workDays: [String]?

    enum CodingKeys: String, CodingKey {
        case locationId = "location_id"
        case payType = "pay_type"
        case payFrequency = "pay_frequency"
        case rate
        case isActive = "is_active"
        case profilePicUrl = "profile_pic_url"
        case shiftStartTime = "shift_start_time"
        case shiftEndTime = "shift_end_time"
        case workDays = "work_days"
    }
}

struct DriverResponse: Codable {
    let id: String
    let firstName: String?
    let lastName: String?
    let email: String
    let phone: String?
    let profilePic: String?
    let isActive: Bool
    let payType: String?
    let payFrequency: String?
    let rate: Double?
    let locationId: String?
    let organizationId: String?
    let shiftStartTime: String?
    let shiftEndTime: String?
    let workDays: [String]?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, email, phone, rate
        case firstName = "first_name"
        case lastName = "last_name"
        case profilePic = "profile_pic"
        case isActive = "is_active"
        case payType = "pay_type"
        case payFrequency = "pay_frequency"
        case locationId = "location_id"
        case organizationId = "organization_id"
        case shiftStartTime = "shift_start_time"
        case shiftEndTime = "shift_end_time"
        case workDays = "work_days"
        case createdAt = "created_at"
    }
}

func updateDriverDetails(
    driverId: String,
    data: DriverDetailsUpdate
) async throws -> DriverResponse {
    let url = URL(string: "\(baseURL)/v1/drivers/\(driverId)")!
    var request = URLRequest(url: url)
    request.httpMethod = "PATCH"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")

    let encoder = JSONEncoder()
    request.httpBody = try encoder.encode(data)

    let (responseData, response) = try await URLSession.shared.data(for: request)

    guard let httpResponse = response as? HTTPURLResponse,
          httpResponse.statusCode == 200 else {
        let error = try JSONDecoder().decode(ErrorResponse.self, from: responseData)
        throw APIError.serverError(error.detail)
    }

    return try JSONDecoder().decode(DriverResponse.self, from: responseData)
}
```

---

## Usage Examples

### Manager: Update driver location, pay type, frequency and rate

```bash
curl -X PATCH "https://api.gt360.app/v1/drivers/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer {manager_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "location_id": "660e8400-e29b-41d4-a716-446655440001",
    "pay_type": "hour",
    "pay_frequency": "weekly",
    "rate": 25.00
  }'
```

### Manager: Deactivate a driver

```bash
curl -X PATCH "https://api.gt360.app/v1/drivers/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer {manager_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "is_active": false
  }'
```

### Manager: Update profile picture

```bash
curl -X PATCH "https://api.gt360.app/v1/drivers/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer {manager_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "profile_pic_url": "https://storage.example.com/drivers/new-photo.jpg"
  }'
```

### Driver: Update own profile picture

```bash
curl -X PATCH "https://api.gt360.app/v1/drivers/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer {driver_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "profile_pic_url": "https://storage.example.com/drivers/my-photo.jpg"
  }'
```

### Manager: Set driver work schedule

```bash
curl -X PATCH "https://api.gt360.app/v1/drivers/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer {manager_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "shift_start_time": "08:00",
    "shift_end_time": "20:00",
    "work_days": ["mon", "tue", "wed", "thu", "fri"]
  }'
```

### Manager: Set overnight schedule

```bash
curl -X PATCH "https://api.gt360.app/v1/drivers/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer {manager_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "shift_start_time": "21:00",
    "shift_end_time": "03:00",
    "work_days": ["mon", "tue", "wed", "thu", "fri"]
  }'
```

### Manager: Update all editable fields at once

```bash
curl -X PATCH "https://api.gt360.app/v1/drivers/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer {manager_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "location_id": "660e8400-e29b-41d4-a716-446655440001",
    "pay_type": "day",
    "pay_frequency": "biweekly",
    "rate": 150.00,
    "is_active": true,
    "profile_pic_url": "https://storage.example.com/drivers/photo.jpg",
    "shift_start_time": "08:00",
    "shift_end_time": "20:00",
    "work_days": ["mon", "tue", "wed", "thu", "fri"]
  }'
```

---

## Notas Importantes

1. **Semantica PATCH**: Solo los campos enviados se actualizan. Campos omitidos permanecen sin cambios
2. **Validacion de pay_type y pay_frequency**: Ambos campos se validan via Pydantic enum. Valores invalidos retornan 422 automaticamente
3. **rate**: Tarifa de pago del driver segun su `pay_type` (ej: si `pay_type=hour` y `rate=25.00`, el driver gana $25/hora)
4. **Validacion de location_id**: Se verifica que la location exista Y pertenezca a la misma organizacion del driver
5. **organization_id protegido**: No existe en el modelo de request, por lo que es imposible cambiarlo
6. **Driver self-edit only**: Un driver solo puede editar su propio perfil, nunca el de otro driver
7. **Respuesta completa**: El endpoint retorna el driver completo con datos del usuario (nombre, email, etc.) via JOIN con la tabla users
8. **Horario de trabajo**: `shift_start_time` y `shift_end_time` deben setearse juntos o ambos null. Soporta horarios nocturnos (ej: 21:00-03:00)
9. **work_days**: Array de abreviaciones de dias. Se normaliza a lowercase. Usado para info de scheduling, no afecta calculo de earnings
10. **Snapshot en shifts**: Al iniciar un shift, `shift_start_time` y `shift_end_time` se copian al shift para que cambios futuros no afecten earnings historicos

---

**Ultima actualizacion:** 2026-02-17
