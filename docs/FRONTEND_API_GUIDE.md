# Frontend API Guide - Trips & Locations

**Version:** 1.0
**Fecha:** 2026-01-04

Guia completa para implementar las funcionalidades de Trips y Locations en el frontend.

---

## Tabla de Contenidos

1. [Endpoints Disponibles](#1-endpoints-disponibles)
2. [Add Trip](#2-add-trip)
3. [Edit Trip](#3-edit-trip)
4. [Delete Trip](#4-delete-trip)
5. [Delete Location](#5-delete-location)
6. [Get Trips](#6-get-trips)
7. [WebSocket Integration](#7-websocket-integration)
8. [Manejo de Errores](#8-manejo-de-errores)
9. [TypeScript Interfaces](#9-typescript-interfaces)
10. [Ejemplos de Implementacion](#10-ejemplos-de-implementacion)

---

## 1. Endpoints Disponibles

| Accion | Metodo | Ruta | Status OK | Rol |
|--------|--------|------|-----------|-----|
| Add Trip | POST | `/v1/locations/{location_id}/trips` | 200 | manager |
| Edit Trip | PATCH | `/v1/locations/{location_id}/trips/{trip_id}` | 200 | manager |
| Delete Trip | DELETE | `/v1/locations/{location_id}/trips/{trip_id}` | 204 | manager |
| Delete All Trips | DELETE | `/v1/locations/{location_id}/trips` | 204 | manager |
| Delete Location | DELETE | `/v1/locations/{location_id}` | 200 | manager |
| Get Trips | GET | `/v1/locations/{location_id}/trips` | 200 | manager |
| Get Locations | GET | `/v1/locations` | 200 | manager |
| WebSocket | WS | `/ws/trips?location_id=X&token=Y` | - | manager |

---

## 2. Add Trip

### Endpoint
```
POST /v1/locations/{location_id}/trips
Authorization: Bearer <JWT_TOKEN>
Content-Type: application/json
```

### Request Body
```json
{
  "pick_up_date": "2024-01-15",
  "pick_up_time": "08:00:00",
  "pick_up_location": "Hotel Central",
  "drop_off_location": "JFK Airport",
  "assigned_driver": "550e8400-e29b-41d4-a716-446655440000",
  "airline": "United Airlines",
  "flight_number": "UA123",
  "riders": {
    "adults": 2,
    "children": 1,
    "luggage": 3
  }
}
```

### Campos

| Campo | Tipo | Requerido | Descripcion |
|-------|------|-----------|-------------|
| `pick_up_date` | `string` (ISO date) | Si | Fecha de recogida YYYY-MM-DD |
| `pick_up_time` | `string` (ISO time) | Si | Hora de recogida HH:MM:SS |
| `pick_up_location` | `string` | Si | Direccion de recogida |
| `drop_off_location` | `string` | Si | Direccion de destino |
| `airline` | `string` | Si | Aerolinea |
| `flight_number` | `string` | Si | Numero de vuelo |
| `riders` | `object` | Si | Objeto con cantidades |
| `assigned_driver` | `UUID` | No | ID del conductor asignado |

### Respuesta Exitosa (200)
```json
{
  "data": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "location_id": "550e8400-e29b-41d4-a716-446655440000",
    "pick_up_date": "2024-01-15",
    "pick_up_time": "08:00:00",
    "pick_up_location": "Hotel Central",
    "drop_off_location": "JFK Airport",
    "airline": "United Airlines",
    "flight_number": "UA123",
    "riders": {"adults": 2, "children": 1, "luggage": 3},
    "assigned_driver": null,
    "started_at": null,
    "picked_up_at": null,
    "dropped_off_at": null,
    "created_at": "2024-01-15T09:30:45.123456+00:00",
    "updated_at": "2024-01-15T09:30:45.123456+00:00"
  }
}
```

### Errores
| Codigo | Causa | Mensaje |
|--------|-------|---------|
| 400 | UUID location_id invalido | `"ID de location invalido"` |
| 400 | Trip duplicado | `"We couldn't validate the schedule: DETAIL: ..."` |
| 401 | Token invalido/ausente | `"Missing or invalid authentication"` |
| 403 | Usuario no es manager | `"Not Authorized: We couldn't validate the role"` |
| 404 | Location no existe | `"Location no encontrada"` |

### WebSocket Event
```json
{
  "type": "trip_event",
  "event_type": "insert",
  "location_id": "uuid",
  "trip_id": "uuid",
  "trip": { /* objeto trip completo */ }
}
```

---

## 3. Edit Trip

### Endpoint
```
PATCH /v1/locations/{location_id}/trips/{trip_id}
Authorization: Bearer <JWT_TOKEN>
Content-Type: application/json
```

### Request Body (todos los campos son opcionales)
```json
{
  "pick_up_date": "2024-01-16",
  "pick_up_time": "10:00:00",
  "pick_up_location": "Hotel Marriott",
  "drop_off_location": "Airport JFK",
  "airline": "UA",
  "flight_number": "AA456",
  "riders": {"adults": 3, "children": 0}
}
```

> **Nota**: Solo enviar los campos que se desean modificar (PATCH parcial)

### Respuesta Exitosa (200)
```json
{
  "status": "ok",
  "trip": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "location_id": "550e8400-e29b-41d4-a716-446655440000",
    "pick_up_date": "2024-01-16",
    "pick_up_time": "10:00:00",
    "pick_up_location": "Hotel Marriott",
    "drop_off_location": "Airport JFK",
    "airline": "UA",
    "flight_number": "AA456",
    "riders": {"adults": 3, "children": 0},
    "assigned_driver": null,
    "started_at": null,
    "picked_up_at": null,
    "dropped_off_at": null,
    "created_at": "2024-01-15T09:30:45.123456+00:00",
    "updated_at": "2024-01-16T14:30:00.000000+00:00"
  }
}
```

### Errores
| Codigo | Causa | Mensaje |
|--------|-------|---------|
| 400 | UUID invalido | `"ID de location invalido"` o `"ID de trip invalido"` |
| 400 | Violacion constraint unico | `"We couldn't validate the schedule: DETAIL: ..."` |
| 401 | Token invalido/ausente | `"Invalid token"` |
| 403 | Usuario no es manager | `"Not Authorized: We couldn't validate the role"` |
| 404 | Trip no existe | `"Trip not found"` |

### WebSocket Event
```json
{
  "type": "trip_event",
  "event_type": "update",
  "location_id": "uuid",
  "trip_id": "uuid",
  "trip": { /* objeto trip actualizado */ }
}
```

---

## 4. Delete Trip

### Endpoint
```
DELETE /v1/locations/{location_id}/trips/{trip_id}
Authorization: Bearer <JWT_TOKEN>
```

### Respuesta Exitosa
```
HTTP 204 No Content
(Sin body)
```

### Errores
| Codigo | Causa | Mensaje |
|--------|-------|---------|
| 400 | UUID trip_id invalido | `"ID de trip invalido"` |
| 400 | UUID location_id invalido | `"ID de location invalido"` |
| 401 | Token invalido/ausente | `"Missing or invalid authentication"` |
| 403 | Usuario no es manager | `"Not Authorized: We couldn't validate the role"` |
| 404 | Trip no existe | `"Trip no encontrado"` |

### WebSocket Event
```json
{
  "type": "trip_event",
  "event_type": "delete",
  "location_id": "uuid",
  "trip_id": "uuid"
}
```
> **Nota**: En eventos `delete`, NO se incluye el objeto `trip`, solo `location_id` y `trip_id`

---

## 5. Delete Location

### Endpoint
```
DELETE /v1/locations/{location_id}
Authorization: Bearer <JWT_TOKEN>
```

### Respuesta Exitosa (200)
```json
{
  "data": "Location {location_id} deleted successfully"
}
```

### Errores
| Codigo | Causa | Mensaje |
|--------|-------|---------|
| 400 | UUID invalido | `"ID de location invalido"` |
| 401 | Token invalido/ausente | `"not authorized"` |
| 403 | Usuario no es manager | `"Not Authorized: We couldn't validate the role"` |
| 404 | Location no existe | `"Location no encontrada"` |

### Efectos Cascada (CASCADE DELETE)

Cuando se elimina una Location, **automaticamente se eliminan**:

| Entidad | Efecto |
|---------|--------|
| **Trips** | Se eliminan TODOS los trips de la location |
| **Hotels** | Se eliminan todos los hotels asociados |
| **Drivers** | Su `location_id` se setea a `NULL` |

### WebSocket
> **IMPORTANTE**: La eliminacion de Location **NO genera eventos WebSocket** para los trips eliminados. El frontend debe manejar esto de forma especial.

---

## 6. Get Trips

### Endpoint
```
GET /v1/locations/{location_id}/trips
Authorization: Bearer <JWT_TOKEN>
```

### Query Parameters
| Parametro | Tipo | Descripcion |
|-----------|------|-------------|
| `skip` | `int` | Offset para paginacion (default: 0) |
| `limit` | `int` | Limite de resultados (default: 20, max: 50) |
| `pick_up_date` | `string` | Filtrar por fecha exacta |
| `pick_up_date_from` | `string` | Filtrar desde fecha |
| `pick_up_date_to` | `string` | Filtrar hasta fecha |
| `pick_up_time` | `string` | Filtrar por hora exacta |
| `pick_up_location` | `string` | Buscar por ubicacion (LIKE) |
| `drop_off_location` | `string` | Buscar por destino (LIKE) |
| `airline` | `string` | Buscar por aerolinea (LIKE) |
| `flight_number` | `string` | Filtrar por numero de vuelo |

### Respuesta Exitosa (200)
```json
{
  "data": [
    {
      "id": "uuid",
      "location_id": "uuid",
      "pick_up_date": "2024-01-15",
      "pick_up_time": "08:00:00",
      "pick_up_location": "Hotel Central",
      "drop_off_location": "JFK Airport",
      "airline": "United Airlines",
      "flight_number": "UA123",
      "riders": {"adults": 2, "children": 1},
      "assigned_driver": null,
      "started_at": null,
      "picked_up_at": null,
      "dropped_off_at": null,
      "created_at": "2024-01-15T09:30:45+00:00",
      "updated_at": "2024-01-15T09:30:45+00:00"
    }
  ],
  "skip": 0,
  "limit": 20,
  "total": 100
}
```

### Respuesta Sin Trips (200)
```json
{
  "data": [],
  "skip": 0,
  "limit": 20,
  "total": 0
}
```

### Errores
| Codigo | Causa | Mensaje |
|--------|-------|---------|
| 400 | UUID invalido | `"ID de location invalido"` |
| 401 | Token invalido | `"Missing or invalid authentication"` |
| 403 | Sin permisos | `"Not Authorized: We couldn't validate the role"` |
| 404 | Location no existe | `"Location no encontrada"` |

---

## 7. WebSocket Integration

### Conexion
```
wss://api.gt360.app/ws/trips?location_id={LOCATION_ID}&token={JWT_TOKEN}
```

### Mensaje Inicial (Snapshot)
Al conectarse, el cliente recibe automaticamente todos los trips activos:
```json
{
  "type": "snapshot",
  "location_id": "uuid",
  "trips": [
    { /* trip 1 */ },
    { /* trip 2 */ }
  ]
}
```

### Eventos en Tiempo Real

#### Insert
```json
{
  "type": "trip_event",
  "event_type": "insert",
  "location_id": "uuid",
  "trip_id": "uuid",
  "trip": { /* objeto trip completo */ }
}
```

#### Update
```json
{
  "type": "trip_event",
  "event_type": "update",
  "location_id": "uuid",
  "trip_id": "uuid",
  "trip": { /* objeto trip actualizado */ }
}
```

#### Delete
```json
{
  "type": "trip_event",
  "event_type": "delete",
  "location_id": "uuid",
  "trip_id": "uuid"
}
```

---

## 8. Manejo de Errores

### Tabla de Errores HTTP

| Codigo | Endpoint | Causa | Accion Frontend |
|--------|----------|-------|-----------------|
| 400 | Todos | UUID invalido | Mostrar "ID invalido" |
| 401 | Todos | Token expirado/invalido | Redirigir a login |
| 403 | Todos | Sin permisos (no es manager) | Mostrar "Sin autorizacion" |
| 404 | GET/DELETE | Recurso no existe | Mostrar "No encontrado" |
| 500 | Todos | Error interno servidor | Mostrar "Error del servidor" |

### Errores por AdBlocker (Ignorar)

Los siguientes errores son causados por bloqueadores de anuncios y **NO afectan la funcionalidad**:

```
ERR_BLOCKED_BY_CLIENT:
- static.cloudflareinsights.com/beacon.min.js (Analytics Cloudflare)
- events.mapbox.com/events/v2 (Telemetria Mapbox)
```

---

## 9. TypeScript Interfaces

```typescript
// Trip Interface
interface Trip {
  id: string;                    // UUID
  location_id: string;           // UUID
  pick_up_date: string;          // "YYYY-MM-DD"
  pick_up_time: string;          // "HH:MM:SS"
  pick_up_location: string;
  drop_off_location: string;
  airline: string;
  flight_number: string;
  riders: Record<string, number>; // { adults: 2, children: 1, ... }
  assigned_driver: string | null; // UUID o null
  started_at: string | null;      // ISO timestamp o null
  picked_up_at: string | null;    // ISO timestamp o null
  dropped_off_at: string | null;  // ISO timestamp o null
  created_at: string;             // ISO timestamp
  updated_at: string;             // ISO timestamp
}

// Create Trip Request
interface CreateTripRequest {
  pick_up_date: string;
  pick_up_time: string;
  pick_up_location: string;
  drop_off_location: string;
  airline: string;
  flight_number: string;
  riders: Record<string, number>;
  assigned_driver?: string;
}

// Update Trip Request (all fields optional)
interface UpdateTripRequest {
  pick_up_date?: string;
  pick_up_time?: string;
  pick_up_location?: string;
  drop_off_location?: string;
  airline?: string;
  flight_number?: string;
  riders?: Record<string, number>;
}

// Get Trips Response
interface GetTripsResponse {
  data: Trip[];
  skip: number;
  limit: number;
  total: number;
}

// WebSocket Events
interface WebSocketSnapshot {
  type: "snapshot";
  location_id: string;
  trips: Trip[];
}

interface WebSocketTripEvent {
  type: "trip_event";
  event_type: "insert" | "update" | "delete";
  location_id: string;
  trip_id: string;
  trip?: Trip; // Solo presente en insert y update
}

type WebSocketMessage = WebSocketSnapshot | WebSocketTripEvent;
```

---

## 10. Ejemplos de Implementacion

### Delete Location con Manejo de Errores

```typescript
async function deleteLocation(locationId: string): Promise<void> {
  try {
    const response = await fetch(`${API_URL}/v1/locations/${locationId}`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      switch (response.status) {
        case 400:
          throw new Error('ID de location invalido');
        case 401:
          window.location.href = '/login';
          return;
        case 403:
          throw new Error('No tienes permisos para eliminar esta location');
        case 404:
          throw new Error('La location no existe');
        case 500:
          throw new Error('Error del servidor. Intenta de nuevo.');
        default:
          throw new Error('Error desconocido');
      }
    }

    // Exito - actualizar UI
    removeLocationFromUI(locationId);

  } catch (error) {
    console.error('Error eliminando location:', error);
    showErrorToast(error.message);
  }
}
```

### WebSocket Connection

```typescript
function connectWebSocket(locationId: string, token: string) {
  const ws = new WebSocket(
    `wss://api.gt360.app/ws/trips?location_id=${locationId}&token=${token}`
  );

  ws.onmessage = (event) => {
    const data: WebSocketMessage = JSON.parse(event.data);

    switch (data.type) {
      case 'snapshot':
        // Carga inicial de todos los trips
        setTrips(data.trips);
        break;

      case 'trip_event':
        switch (data.event_type) {
          case 'insert':
            addTrip(data.trip!);
            break;
          case 'update':
            updateTrip(data.trip!);
            break;
          case 'delete':
            // Nota: solo viene trip_id, no el objeto trip
            removeTrip(data.trip_id);
            break;
        }
        break;
    }
  };

  ws.onerror = (error) => {
    console.error('WebSocket error:', error);
    setTimeout(() => connectWebSocket(locationId, token), 5000);
  };

  ws.onclose = () => {
    showNotification('Conexion perdida. Recargando...');
    setTimeout(() => window.location.reload(), 2000);
  };

  return ws;
}
```

### Flujo Recomendado

```
1. Conectar WebSocket: ws/trips?location_id=X&token=Y
2. Recibir snapshot inicial con todos los trips
3. Renderizar lista de trips
4. Escuchar eventos trip_event para actualizaciones en tiempo real

Para operaciones CRUD:
- POST/PATCH/DELETE -> Esperar respuesta HTTP
- La UI se actualizara automaticamente via WebSocket
- No es necesario refrescar manualmente despues de cada operacion
```

---

## Consideraciones Importantes

### Constraint de Unicidad
No pueden existir dos trips con la misma combinacion de:
- `location_id` + `pick_up_date` + `pick_up_time` + `airline` + `flight_number` + `pick_up_location` + `drop_off_location`

### TTL de Redis (Cache)
- Los trips se cachean en Redis con TTL de **5 minutos**
- El snapshot inicial solo muestra trips con actividad reciente en cache

### Latencia de Eventos WebSocket
- ~50-200ms desde el commit en BD hasta recibir evento en WebSocket
- Los eventos se agrupan en batches cada 0.2 segundos maximo

### Delete Location NO genera WebSocket
- Los clientes conectados NO reciben notificacion de trips eliminados
- Deben manejar la perdida de conexion o refrescar manualmente
