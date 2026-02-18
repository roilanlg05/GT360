# Driver Arrival Log Endpoint - Frontend/Mobile Integration Guide

## Overview

Endpoint para loguear cuando el driver llega al pick-up location o al drop-off location. Registra el timestamp usando la hora local de la location del trip (basada en la timezone configurada en la tabla `entities.locations`).

---

## Endpoint

```
POST /v1/trips/{trip_id}/log-arrival
```

### Autenticacion
- Requiere token JWT valido
- Solo usuarios con rol `driver` pueden acceder

---

## Parametros

### Path Parameters

| Parametro | Tipo | Requerido | Descripcion |
|-----------|------|-----------|-------------|
| `trip_id` | UUID | **Si** | ID del trip |

### Request Body

```json
{
  "type": "pick-up",
  "driver_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

| Campo | Tipo | Requerido | Valores | Descripcion |
|-------|------|-----------|---------|-------------|
| `type` | string | **Si** | `"pick-up"`, `"drop-off"` | Tipo de llegada a loguear |
| `driver_id` | UUID | **Si** | - | ID del driver que realiza la accion |

### Valores de `type`

| Valor | Descripcion | Campo actualizado |
|-------|-------------|-------------------|
| `pick-up` | Driver llego al punto de recogida | `arrived_pickup_at` |
| `drop-off` | Driver llego al punto de destino | `arrived_dropoff_at` |

---

## Response

### Success Response (200)

**Pick-up arrival:**
```json
{
  "status": "ok",
  "message": "Arrival at pick-up location logged successfully",
  "trip_id": "550e8400-e29b-41d4-a716-446655440000",
  "arrived_pickup_at": "2026-02-08T14:30:00-05:00",
  "timezone": "America/New_York"
}
```

**Drop-off arrival:**
```json
{
  "status": "ok",
  "message": "Arrival at drop-off location logged successfully",
  "trip_id": "550e8400-e29b-41d4-a716-446655440000",
  "arrived_dropoff_at": "2026-02-08T15:45:00-05:00",
  "timezone": "America/New_York"
}
```

### Response Fields

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `status` | string | Siempre `"ok"` en exito |
| `message` | string | Mensaje descriptivo |
| `trip_id` | string (UUID) | ID del trip actualizado |
| `arrived_pickup_at` | string (ISO 8601) | Timestamp local de llegada al pick-up (solo si type=pick-up) |
| `arrived_dropoff_at` | string (ISO 8601) | Timestamp local de llegada al drop-off (solo si type=drop-off) |
| `timezone` | string (IANA) | Timezone utilizada para calcular la hora local |

---

## Error Responses

### 400 Bad Request
```json
{
  "detail": "type must be 'pick-up' or 'drop-off'"
}
```
```json
{
  "detail": "Invalid trip ID"
}
```
```json
{
  "detail": "Could not determine location timezone"
}
```

### 403 Forbidden
```json
{
  "detail": "The driver is not active"
}
```
```json
{
  "detail": "Driver is not assigned to this trip"
}
```

### 404 Not Found
```json
{
  "detail": "Trip not found"
}
```

### 409 Conflict
```json
{
  "detail": "Arrival at pick-up location already logged"
}
```
```json
{
  "detail": "Arrival at drop-off location already logged"
}
```

---

## Timezone Behavior

El endpoint obtiene la timezone de la location asociada al trip (campo `timezone` en `entities.locations`). La hora se loguea en la hora local de esa location.

**Ejemplo:**
- Location: SDF (Louisville, KY) → timezone: `America/New_York`
- Si el driver llega a las 2:30 PM hora del Este, se registra: `2026-02-08T14:30:00-05:00`

**Ejemplo con otra timezone:**
- Location: LAX (Los Angeles, CA) → timezone: `America/Los_Angeles`
- Si el driver llega a las 11:30 AM hora del Pacifico, se registra: `2026-02-08T11:30:00-08:00`

---

## Database Schema Changes

### Table: `trips.trips`

Nuevos campos agregados:

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `arrived_pickup_at` | TIMESTAMPTZ | Yes | NULL | Timestamp de llegada al pick-up location |
| `arrived_dropoff_at` | TIMESTAMPTZ | Yes | NULL | Timestamp de llegada al drop-off location |

### Table: `trips.trips_history`

Mismos campos replicados para el historial:

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `arrived_pickup_at` | TIMESTAMPTZ | Yes | NULL | Timestamp de llegada al pick-up location |
| `arrived_dropoff_at` | TIMESTAMPTZ | Yes | NULL | Timestamp de llegada al drop-off location |

### Migration SQL

```sql
-- Add arrival timestamp columns to trips table
ALTER TABLE trips.trips
ADD COLUMN IF NOT EXISTS arrived_pickup_at TIMESTAMPTZ DEFAULT NULL,
ADD COLUMN IF NOT EXISTS arrived_dropoff_at TIMESTAMPTZ DEFAULT NULL;

-- Add indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_trips_arrived_pickup_at ON trips.trips(arrived_pickup_at);
CREATE INDEX IF NOT EXISTS idx_trips_arrived_dropoff_at ON trips.trips(arrived_dropoff_at);

-- Add same columns to trips_history table
ALTER TABLE trips.trips_history
ADD COLUMN IF NOT EXISTS arrived_pickup_at TIMESTAMPTZ DEFAULT NULL,
ADD COLUMN IF NOT EXISTS arrived_dropoff_at TIMESTAMPTZ DEFAULT NULL;

-- Add indexes for trips_history
CREATE INDEX IF NOT EXISTS idx_trips_history_arrived_pickup_at ON trips.trips_history(arrived_pickup_at);
CREATE INDEX IF NOT EXISTS idx_trips_history_arrived_dropoff_at ON trips.trips_history(arrived_dropoff_at);
```

---

## Frontend/Mobile Implementation

### TypeScript Interface

```typescript
interface ArrivalLogRequest {
  type: 'pick-up' | 'drop-off';
  driver_id: string;
}

interface ArrivalLogResponse {
  status: string;
  message: string;
  trip_id: string;
  arrived_pickup_at?: string;   // ISO 8601 with timezone offset
  arrived_dropoff_at?: string;  // ISO 8601 with timezone offset
  timezone: string;             // IANA timezone (e.g., "America/New_York")
}
```

### Kotlin (Android)

```kotlin
data class ArrivalLogRequest(
    val type: String,       // "pick-up" or "drop-off"
    val driver_id: String   // UUID
)

data class ArrivalLogResponse(
    val status: String,
    val message: String,
    val trip_id: String,
    val arrived_pickup_at: String?,
    val arrived_dropoff_at: String?,
    val timezone: String
)
```

### Swift (iOS)

```swift
struct ArrivalLogRequest: Codable {
    let type: String        // "pick-up" or "drop-off"
    let driver_id: String   // UUID
}

struct ArrivalLogResponse: Codable {
    let status: String
    let message: String
    let trip_id: String
    let arrived_pickup_at: String?
    let arrived_dropoff_at: String?
    let timezone: String
}
```

### API Call (Kotlin)

```kotlin
suspend fun logDriverArrival(
    tripId: String,
    type: String,  // "pick-up" or "drop-off"
    driverId: String,
    token: String
): Result<ArrivalLogResponse> {
    return try {
        val request = ArrivalLogRequest(
            type = type,
            driver_id = driverId
        )

        val response = httpClient.post("$BASE_URL/v1/trips/$tripId/log-arrival") {
            header("Authorization", "Bearer $token")
            contentType(ContentType.Application.Json)
            setBody(request)
        }

        if (response.status == HttpStatusCode.OK) {
            val body = response.body<ArrivalLogResponse>()
            Result.success(body)
        } else {
            val error = response.body<ErrorResponse>()
            Result.failure(Exception(error.detail))
        }
    } catch (e: Exception) {
        Result.failure(e)
    }
}
```

### API Call (Swift)

```swift
func logDriverArrival(
    tripId: String,
    type: String,   // "pick-up" or "drop-off"
    driverId: String,
    token: String
) async throws -> ArrivalLogResponse {
    let url = URL(string: "\(baseURL)/v1/trips/\(tripId)/log-arrival")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")

    let body = ArrivalLogRequest(type: type, driver_id: driverId)
    request.httpBody = try JSONEncoder().encode(body)

    let (data, response) = try await URLSession.shared.data(for: request)

    guard let httpResponse = response as? HTTPURLResponse,
          httpResponse.statusCode == 200 else {
        throw ArrivalLogError.requestFailed
    }

    return try JSONDecoder().decode(ArrivalLogResponse.self, from: data)
}
```

---

## Usage Examples (cURL)

### Log arrival at pick-up location
```bash
curl -X POST "https://api.gt360.app/v1/trips/{trip_id}/log-arrival" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "pick-up",
    "driver_id": "550e8400-e29b-41d4-a716-446655440000"
  }'
```

### Log arrival at drop-off location
```bash
curl -X POST "https://api.gt360.app/v1/trips/{trip_id}/log-arrival" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "drop-off",
    "driver_id": "550e8400-e29b-41d4-a716-446655440000"
  }'
```

---

## Trip Flow (Updated)

```
SCHEDULED
  ↓
Driver assigned (start trip)  →  started_at
  ↓
Driver arrives at pick-up     →  arrived_pickup_at   ← NEW
  ↓
Pickup confirmed (geofence)   →  picked_up_at
  ↓
Driver arrives at drop-off    →  arrived_dropoff_at  ← NEW
  ↓
Drop-off confirmed (geofence) →  dropped_off_at
  ↓
COMPLETED (moved to history)
```

---

## Notes

1. **One-time log**: Each arrival can only be logged once per trip. Attempting to log again returns 409 Conflict.
2. **Local time**: The timestamp uses the timezone of the location associated with the trip, not the driver's device timezone.
3. **Both fields start as NULL**: They remain NULL until explicitly logged via this endpoint.
4. **No geofence validation**: This endpoint does NOT validate the driver's physical location (unlike pick-up and drop-off endpoints). It simply logs the timestamp.
5. **History sync**: The `arrived_pickup_at` and `arrived_dropoff_at` fields are automatically carried over to `trips_history` when the trip is completed.

---

**Last updated:** 2026-02-08
