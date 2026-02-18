# GT360 - Guia Completa del Rol Driver (Backend)

> Documento exhaustivo de todos los endpoints, modelos, WebSockets, flujos y funcionalidades disponibles para el rol **driver** en el backend GT360.

---

## TABLA DE CONTENIDO

1. [Arquitectura General](#1-arquitectura-general)
2. [Autenticacion](#2-autenticacion)
3. [Estado Online/Offline del Driver](#3-estado-onlineoffline-del-driver)
4. [Trips - Ciclo de Vida Completo](#4-trips---ciclo-de-vida-completo)
5. [Perfil del Driver](#5-perfil-del-driver)
6. [User Settings (Preferencias)](#6-user-settings-preferencias)
7. [WebSockets - Tiempo Real](#7-websockets---tiempo-real)
8. [Soporte / Contacto](#8-soporte--contacto)
9. [Geofencing](#9-geofencing)
10. [Ecosistema GPS / Coordenadas / Ubicacion](#10-ecosistema-gps--coordenadas--ubicacion)
11. [Modelos de Base de Datos](#11-modelos-de-base-de-datos)
12. [Flujos Completos (Diagramas)](#12-flujos-completos-diagramas)
13. [Headers y Autenticacion Requerida](#13-headers-y-autenticacion-requerida)
14. [Codigos de Error](#14-codigos-de-error)

---

## 1. ARQUITECTURA GENERAL

### Stack Tecnologico
- **Framework**: FastAPI (Python)
- **Base de datos**: PostgreSQL con ORM psqlmodel
- **Cache/Pub-Sub**: Redis
- **Auth**: JWT (jose) + Argon2 para passwords
- **WebSockets**: FastAPI WebSocket nativo + Redis Pub/Sub
- **Email**: Brevo (SMTP)
- **Storage**: Local filesystem (`/var/www/gt360/uploads`)

### Roles del Sistema
```
UserRole:
  - admin
  - manager
  - crew
  - driver    <-- ESTE DOCUMENTO
```

### URL Base
- **Produccion**: `https://api.gt360.app`
- **Desarrollo**: `https://dev.gt360.app`

### Dominios de Cookies
- Dominio: `.gt360.app`
- HttpOnly: true
- Secure: true
- SameSite: lax

---

## 2. AUTENTICACION

### 2.1 Registro de Driver

> **NOTA**: Los drivers NO se auto-registran. Un **manager** los registra.

```
POST /v1/auth/register/driver
```

**Body (JSON)**:
```json
{
  "first_name": "John",
  "last_name": "Doe",
  "email": "john@example.com",
  "phone": "+15551234567",
  "organization_id": "uuid-de-la-organizacion",
  "location_id": "uuid-de-la-location"
}
```

**Validaciones**:
- `email`: Debe ser un email valido (EmailStr)
- `phone`: Formato US normalizado a E.164 (+1XXXXXXXXXX). Acepta: `+1 (555) 123-4567`, `555-123-4567`, `5551234567`
- `organization_id`: Debe existir en la DB
- `location_id`: ID de la location asignada al driver
- Se genera una **password temporal aleatoria** (el driver NO elige password)

**Flujo**:
1. Se verifica que el email no exista
2. Se genera password temporal con `secrets.token_urlsafe(12)`
3. Se crea el `User` con `role="driver"`
4. Se crea el `Driver` con `organization_id` y `location_id`
5. Se genera nonce para verificacion de email
6. Se envia email de verificacion

**Response (201)**:
```json
{
  "message": "User registred succefull. Check your email for confirmation!"
}
```

**Errores**:
- `409`: Email ya en uso
- `404`: Organization not found
- `400`: Registration failed (validacion)

---

### 2.2 Verificacion de Email

```
GET /v1/auth/verify-email?token={token}
```

**Publico**: Si (no requiere auth)

El driver recibe un link por email. Al hacer click:
1. Se decodifica el JWT (valido por 24 horas)
2. Se valida que el `purpose` sea `email_verification`
3. Se valida el `nonce` (uso unico)
4. Se marca `email_verified_at = now()`
5. Se invalida el nonce

**Response (200)**: `"Email verified successfully"`

**Errores**:
- `304`: Email ya verificado
- `400`: Token invalido o expirado

---

### 2.3 Sign In (Login)

```
POST /v1/auth/sign-in
```

**Publico**: Si

**Body**:
```json
{
  "email": "john@example.com",
  "password": "MyP@ss123!"
}
```

**Flujo**:
1. Busca usuario por email
2. Verifica password con Argon2 + pepper
3. Valida que el email este verificado
4. Genera JWT access token
5. Genera refresh token (opaco, SHA-256 hasheado en DB)
6. Setea cookies httpOnly

**Response (200)**:
```json
{
  "data": {
    "session": {
      "access_token": "eyJhbG...",
      "expires_at": 1700000000,
      "type": "Bearer"
    },
    "refresh_token": {
      "refresh": "token-opaco-base64...",
      "expires_at": "2026-03-10T00:00:00Z"
    },
    "user_data": {
      "id": "uuid-del-usuario",
      "email": "john@example.com",
      "phone": "+15551234567",
      "role": "driver",
      "organization_id": "uuid-de-la-org",
      "location_id": "uuid-de-la-location",
      "first_name": "John",
      "last_name": "Doe",
      "profile_pic": "https://api.gt360.app/uploads/profiles/user-uuid/image.jpg"
    }
  }
}
```

**IMPORTANTE para el driver**: El `user_data` incluye `organization_id`, `location_id`, `first_name`, `last_name`, y `profile_pic` embebidos en el token JWT. Estos se necesitan para hacer llamadas a otros endpoints y mostrar información del perfil.

**JWT Payload (metadata)**:
```json
{
  "sub": "user-uuid",
  "metadata": {
    "email": "john@example.com",
    "phone": "+15551234567",
    "role": "driver",
    "organization_id": "org-uuid",
    "location_id": "location-uuid",
    "first_name": "John",
    "last_name": "Doe",
    "profile_pic": "https://api.gt360.app/uploads/profiles/user-uuid/image.jpg"
  },
  "iat": 1700000000,
  "exp": 1700003600
}
```

**Duracion del Token**: Configurable via `TOKEN_DURATION` env var (minutos).

---

### 2.4 Refresh Token

```
POST /v1/auth/refresh
```

**Publico**: Si

**Body (JSON)** (o cookie `refresh_token`):
```json
{
  "refresh_token": "token-opaco..."
}
```

Acepta el refresh token en 3 formas:
- Cookie `refresh_token`
- Body campo `refresh_token`
- Body campo `refresh`
- Body campo `token`

**Response**: Mismo formato que sign-in con nuevos tokens.

**Flujo**:
1. Valida el refresh token (no revocado, no expirado)
2. Genera nuevo refresh token
3. Genera nuevo access token con metadata actualizada
4. Setea nuevas cookies

---

### 2.5 Sign Out (Logout)

```
POST /v1/auth/sign-out/
```

**Auth**: Requerida (Bearer token)

**Flujo**:
1. Blacklistea el access token actual en Redis (TTL 300s)
2. Revoca TODOS los refresh tokens del usuario en DB
3. Elimina cookies

**Response (200)**:
```json
{
  "message": "All cookies revoked"
}
```

---

### 2.6 Forgot Password

```
POST /v1/auth/forgot-password
```

**Publico**: Si

**Body**: `email` (EmailStr como query/body)

**Flujo**:
1. Busca usuario por email
2. Genera nonce y token de reset (valido 30 min)
3. Envia email con link de reset

**Response (200)**: Siempre retorna el mismo mensaje (no revela si el email existe):
```json
"If the email exists, you will receive a password reset link"
```

---

### 2.7 Reset Password

```
POST /v1/auth/reset-password?token={reset_token}
```

**Publico**: Si

**Body**:
```json
{
  "new_password": "NewP@ss456!"
}
```

**Validaciones de Password**:
- Minimo 8 caracteres
- Al menos 1 mayuscula
- Al menos 1 minuscula
- Al menos 1 digito
- Al menos 1 caracter especial (!@#$%^&*()_=+[]{};:,.<>?/\\|~`'\"-)

**Flujo**:
1. Decodifica token
2. Valida `purpose = password_reset`
3. Valida nonce (uso unico)
4. Valida nueva password (reglas)
5. Verifica que sea diferente a la actual
6. Hashea nueva password
7. Revoca todos los refresh tokens
8. Invalida nonce

**Response (200)**:
```json
{
  "message": "Password updated. Sign in again."
}
```

---

### 2.8 Change Password (Autenticado)

```
PUT /v1/auth/change-password?user_id={user_id}
```

**Body**:
```json
{
  "current_password": "OldP@ss123!",
  "new_password": "NewP@ss456!"
}
```

**Flujo**: Similar a reset pero requiere password actual.

---

## 3. ESTADO ONLINE/OFFLINE DEL DRIVER

### 3.1 Obtener Estado Actual

```
GET /v1/drivers/me/status
```

**Auth**: Requerida (role: driver)

**Response (200)**:
```json
{
  "id": "driver-uuid",
  "is_active": true
}
```

**Logica**: Consulta la tabla `drivers` usando el `user_id` del token JWT.

---

### 3.2 Cambiar Estado (Online/Offline)

```
PATCH /v1/drivers/me/active
```

**Auth**: Requerida (role: driver)

**Body**:
```json
{
  "is_active": true
}
```

Para `is_active: true` = **Online**
Para `is_active: false` = **Offline**

**Validacion Critica**: Si el driver intenta ponerse **offline** (`is_active: false`) y tiene trips activos con estado `SCHEDULED` o `EN_ROUTE`, se rechaza:

**Error (409)**:
```json
{
  "detail": "Cannot go offline with 2 active trip(s). Complete all trips before going offline."
}
```

**Response (200)**:
```json
{
  "id": "driver-uuid",
  "is_active": false
}
```

### Estados del Driver
| is_active | Significado | UI |
|-----------|-------------|-----|
| `true` | Online - Puede recibir y ejecutar trips | Circulo verde "Online" |
| `false` | Offline - No disponible | Circulo gris "Offline" |

> **NOTA**: No existe un estado "Busy" explicitamente en el backend. El concepto "Busy" de la UI se deriva del driver teniendo trips en estado `EN_ROUTE`.

---

## 4. TRIPS - CICLO DE VIDA COMPLETO

### 4.1 Obtener Trips (Lista paginada)

```
GET /v1/locations/{location_id}/trips
```

**Auth**: Requerida (role: manager, driver, crew)

**Query Parameters**:
| Param | Tipo | Descripcion |
|-------|------|-------------|
| `pick_up_date` | string (ISO date) | Filtro exacto por fecha |
| `pick_up_date_from` | string (ISO date) | Rango: fecha desde |
| `pick_up_date_to` | string (ISO date) | Rango: fecha hasta |
| `pick_up_time` | string (ISO time) | Filtro exacto por hora |
| `pick_up_time_from` | string (ISO time) | Rango: hora desde |
| `pick_up_time_to` | string (ISO time) | Rango: hora hasta |
| `pick_up_location` | string | Busqueda parcial (ILIKE) |
| `drop_off_location` | string | Busqueda parcial (ILIKE) |
| `airline` | string | Busqueda parcial (ILIKE) |
| `flight_number` | string | Match exacto |
| `trip_type` | string | `inbound`, `outbound`, `ground` |
| `assigned_driver` | string (UUID) | Filtrar por driver asignado |
| `status` | string | `scheduled`, `en_route`, `completed`, `canceled` |
| `skip` | int (default 0) | Paginacion: offset |
| `limit` | int (default 100, max 200) | Paginacion: limite |

**Response (200)**:
```json
{
  "data": [
    {
      "id": "trip-uuid",
      "assigned_driver": "driver-uuid | null",
      "location_id": "location-uuid",
      "pick_up_date": "2026-01-15",
      "pick_up_time": "15:45:00-05:00",
      "pick_up_location": "Hilton Downtown",
      "drop_off_location": "JFK",
      "airline": "UA",
      "flight_number": "UA123",
      "trip_type": "outbound",
      "riders": {"pilots": 2, "flight_attendants": 4},
      "started_at": null,
      "picked_up_at": null,
      "dropped_off_at": null,
      "created_at": "2026-01-10T12:00:00Z",
      "updated_at": "2026-01-10T12:00:00Z",
      "status": "scheduled",
      "original_pick_up_time": null,
      "reduce_applied": false,
      "combine_applied": false,
      "expand_applied": false,
      "filtered_at": null,
      "current_step_id": null
    }
  ],
  "skip": 0,
  "limit": 100,
  "total": 42
}
```

**USO PARA DRIVER**: Para obtener solo los trips asignados al driver:
```
GET /v1/locations/{location_id}/trips?assigned_driver={driver_uuid}
```

Para obtener solo trips "Live" (scheduled o en_route):
```
GET /v1/locations/{location_id}/trips?assigned_driver={driver_uuid}&status=scheduled
GET /v1/locations/{location_id}/trips?assigned_driver={driver_uuid}&status=en_route
```

---

### 4.2 Obtener Trips Historicos

```
GET /v1/locations/{location_id}/trips/history
```

**Auth**: Requerida (role: manager, driver, crew)

Mismos query params que `/trips`. Consulta la tabla `trips_history` (trips archivados).

Ordenados por fecha **descendente** (mas recientes primero).

---

### 4.3 Detalle de un Trip

```
GET /v1/locations/{location_id}/trips/{trip_id}/details
```

**Auth**: Requerida (role: manager, driver)

**RESTRICCION DRIVER**: Un driver solo puede ver detalles de trips que le estan asignados. Si intenta acceder a un trip de otro driver:
```json
{
  "detail": "Drivers can only view trips assigned to them"
}
```

**Response (200)**:
```json
{
  "trip": {
    "id": "trip-uuid",
    "assigned_driver": "driver-uuid",
    "location_id": "location-uuid",
    "pick_up_date": "2026-01-15",
    "pick_up_time": "15:45",
    "pick_up_location": "Hilton Downtown",
    "drop_off_location": "JFK",
    "airline": "UA",
    "flight_number": "UA123",
    "trip_type": "outbound",
    "riders": {"pilots": 2, "flight_attendants": 4},
    "status": "scheduled",
    "started_at": null,
    "picked_up_at": null,
    "dropped_off_at": null
  },
  "location": {
    "id": "location-uuid",
    "name": "JFK",
    "timezone": "America/New_York",
    "address": null,
    "point": {"type": "Point", "coordinates": [-73.7781, 40.6413]},
    "radio_zone": 0.5,
    "validation_status": "VALIDATED",
    "provider": "WN"
  },
  "driver": {
    "id": "driver-uuid",
    "first_name": "John",
    "last_name": "Doe",
    "email": "john@example.com",
    "phone": "+15551234567",
    "pay_type": "day",
    "is_active": true,
    "point": {"type": "Point", "coordinates": [-73.9857, 40.7484]}
  },
  "filter_step": null,
  "pickup_hotel": {
    "id": "hotel-uuid",
    "name": "Hilton Downtown",
    "address": "123 Main St",
    "point": {"type": "Point", "coordinates": [-73.98, 40.74]},
    "radio_zone": 0.05,
    "validation_status": "VALIDATED"
  },
  "dropoff_hotel": null
}
```

---

### 4.4 Asignar Driver a Trip / Auto-asignacion

```
PATCH /v1/organizations/{org_id}/locations/{location_id}/trips/{trip_id}/assign
```

**Auth**: Requerida (role: manager, driver)

**Comportamiento segun rol**:

#### Para DRIVER (auto-asignacion + Start):
- No se envia `driver_id` (se ignora si se envia)
- El driver se auto-asigna usando su ID del token
- **AUTOMATICAMENTE** marca `started_at = now()` y `status = "en_route"`
- El driver debe pertenecer a la misma organizacion

**Response para driver**:
```json
{
  "status": "ok",
  "data": { "...trip serializado..." },
  "message": "Trip iniciado correctamente"
}
```

#### Para MANAGER (asignacion):
```
PATCH ...?driver_id={driver_uuid}
```
- Requiere `driver_id` como query param
- Solo asigna el driver, NO marca started_at
- El driver debe pertenecer a la misma organizacion

---

### 4.5 Start Trip (Iniciar Viaje)

```
POST /v1/trips/{trip_id}/start
```

**Auth**: Requerida (role: driver)

**Body**:
```json
{
  "driver_id": "driver-uuid"  // Opcional (se valida vs token)
}
```

**Validaciones**:
1. El trip debe existir
2. El trip no debe estar cancelado
3. El trip no debe estar ya en ruta (started_at != null)
4. El driver debe estar **activo** (`is_active = true`)
5. Si se envia `driver_id`, debe coincidir con el del token (anti-spoofing)
6. Si el trip no tiene driver asignado, se auto-asigna el driver del request
7. Si el trip ya tiene driver, debe ser el mismo que hace el request

**Restricciones de Tiempo por Tipo de Trip**:

| Trip Type | Restriccion |
|-----------|-------------|
| `inbound` | Solo se puede iniciar **hasta 1 hora antes** del pickup time |
| `outbound` | Solo se puede iniciar **hasta 25 minutos antes** del pickup time |
| `ground` | Sin restriccion de tiempo |

**Error de tiempo (400)**:
```json
{
  "detail": "Inbound trips can only be started up to 1 hour before pickup time. Earliest start: 14:45 EST"
}
```

**Response (200)**:
```json
{
  "status": "ok",
  "message": "Trip iniciado exitosamente",
  "trip_id": "trip-uuid",
  "started_at": "2026-01-15T20:45:00+00:00"
}
```

**Cambios en DB**:
- `started_at = now(UTC)`
- `status = "en_route"`

---

### 4.6 Pick Up (Recoger Pasajeros)

```
POST /v1/trips/{trip_id}/pick-up
```

**Auth**: Requerida (role: driver)

**Body**:
```json
{
  "driver_id": "driver-uuid",
  "driver_location": {
    "type": "Point",
    "coordinates": [-73.9857, 40.7484]
  },
  "pickup_location": {
    "type": "Point",
    "coordinates": [-73.9800, 40.7400]
  },
  "radio_zone": 0.05
}
```

**Formato de coordenadas**: GeoJSON Point `[longitude, latitude]`

**Validaciones**:
1. Ambas ubicaciones deben ser GeoJSON Point validos
2. Se calcula la distancia Haversine en millas entre `driver_location` y `pickup_location`
3. La distancia debe ser <= `radio_zone` (en millas)
4. El driver debe estar activo (`is_active = true`)
5. El driver debe estar asignado al trip

**Error: Driver fuera del radio (400)**:
```json
{
  "detail": {
    "error": "driver_outside_radius",
    "message": "El driver esta fuera del radio de pickup",
    "distance_miles": 0.1234,
    "radius_miles": 0.05
  }
}
```

**Response (200)**:
```json
{
  "status": "ok",
  "message": "Pickup registrado exitosamente",
  "trip_id": "trip-uuid",
  "picked_up_at": "2026-01-15T20:50:00+00:00",
  "distance_miles": 0.0234
}
```

**Cambios en DB**:
- `picked_up_at = now(UTC)`
- `status = "en_route"`

---

### 4.7 Drop Off (Dejar Pasajeros)

```
POST /v1/trips/{trip_id}/drop-off
```

**Auth**: Requerida (role: driver)

**Body**:
```json
{
  "driver_id": "driver-uuid",
  "driver_location": {
    "type": "Point",
    "coordinates": [-73.7781, 40.6413]
  },
  "dropoff_location": {
    "type": "Point",
    "coordinates": [-73.7790, 40.6420]
  },
  "radio_zone": 0.1
}
```

**Validaciones**: Identicas al pick-up pero con la ubicacion de destino.

**Response (200)**:
```json
{
  "status": "ok",
  "message": "Drop off registrado exitosamente",
  "trip_id": "trip-uuid",
  "dropped_off_at": "2026-01-15T21:30:00+00:00",
  "distance_miles": 0.0123
}
```

**Cambios en DB**:
- `dropped_off_at = now(UTC)`
- `status = "completed"`

---

### 4.8 Flujo Completo del Trip (Estado por Estado)

```
SCHEDULED  -->  EN_ROUTE  -->  EN_ROUTE (pickup)  -->  COMPLETED (dropoff)
              start_trip       pick_up                  drop_off
                  |                |
                  v                v
              SCHEDULED  <--  SCHEDULED
                        relief
              (trip libre, sin driver)
```

| Paso | Endpoint | Status Resultante | Timestamp Actualizado |
|------|----------|-------------------|----------------------|
| 1. Trip creado | (por manager) | `scheduled` | `created_at` |
| 2. Driver asignado | (por manager o auto) | `scheduled` | `assigned_driver` |
| 3. Start Trip | `POST /v1/trips/{id}/start` | `en_route` | `started_at` |
| 4. Pick Up | `POST /v1/trips/{id}/pick-up` | `en_route` | `picked_up_at` |
| 5. Drop Off | `POST /v1/trips/{id}/drop-off` | `completed` | `dropped_off_at` |
| Alt. Relief | `POST /v1/trips/{id}/relief` | `scheduled` | Reset: assigned_driver, started_at, picked_up_at, arrived_* |

**Nota sobre auto-asignacion**: Si un driver usa `PATCH .../assign`, los pasos 2 y 3 se combinan (se asigna y se inicia automaticamente).

**Nota sobre relief**: En cualquier momento despues del start y antes del drop-off, el driver asignado puede soltar el trip. Ver seccion 4.16.

### Trip Status
```
TripStatus:
  SCHEDULED = "scheduled"   # Programado, esperando
  EN_ROUTE  = "en_route"    # En camino / En progreso
  COMPLETED = "completed"   # Completado
  CANCELED  = "canceled"    # Cancelado
```

### Trip Types
```
TripType:
  INBOUND  = "inbound"    # Aeropuerto -> Hotel (recogida de crew)
  OUTBOUND = "outbound"   # Hotel -> Aeropuerto (llevar crew al vuelo)
  GROUND   = "ground"     # Hotel -> Hotel (transfer terrestre)
```

---

### 4.16 Relief Trip (Soltar Viaje)

```
POST /v1/trips/{trip_id}/relief
```

**Auth**: Requerida (role: driver)

**Body**: No requiere body. El `driver_id` se obtiene del JWT token.

**Proposito**: Permite al driver que tomo un trip soltarlo, devolviendolo a estado `SCHEDULED` sin driver asignado, para que otro driver lo pueda tomar.

**Validaciones**:
1. El trip debe existir
2. El trip debe estar en estado `EN_ROUTE` (ya fue iniciado)
3. El trip NO debe haber completado el drop-off (`dropped_off_at` debe ser null)
4. El driver del token JWT debe ser el **mismo** asignado al trip (anti-spoofing)
5. El driver debe estar activo (`is_active = true`)

**Que se resetea en el trip**:

| Campo | Antes | Despues |
|-------|-------|---------|
| `assigned_driver` | driver-uuid | `null` |
| `status` | `en_route` | `scheduled` |
| `started_at` | timestamp | `null` |
| `picked_up_at` | timestamp o null | `null` |
| `arrived_pickup_at` | timestamp o null | `null` |
| `arrived_dropoff_at` | timestamp o null | `null` |

**Response (200)**:
```json
{
  "status": "ok",
  "message": "Trip released successfully",
  "trip_id": "trip-uuid"
}
```

**Errores**:
- `400`: ID de trip invalido
- `401`: Token invalido o faltante
- `403`: Driver inactivo o no es el driver asignado al trip
- `404`: Trip no encontrado
- `409`: Trip no esta en ruta, o ya completo el drop-off

**WebSocket**: Se publica un evento `trip_relieved` via Redis Pub/Sub a los canales `loc:{location_id}` y `org:{organization_id}`, notificando a todos los clientes conectados que el trip volvio a estar disponible.

**Evento WebSocket**:
```json
{
  "type": "trips_batch",
  "location_id": "location-uuid",
  "events": [{
    "trip_id": "trip-uuid",
    "event_type": "trip_relieved",
    "trip": {
      "id": "trip-uuid",
      "assigned_driver": null,
      "status": "scheduled",
      "started_at": null,
      "picked_up_at": null,
      "arrived_pickup_at": null,
      "arrived_dropoff_at": null
    }
  }]
}
```

**Casos de uso**:
- El trip fue cancelado por el cliente y el driver necesita soltarlo
- El manager quiere reasignar el trip a otro driver
- El driver no puede completar el viaje por cualquier razon

**Restricciones de seguridad**:
- Solo el driver asignado puede hacer relief. Otro driver NO puede interceder.
- Un manager NO puede hacer relief (debe usar el endpoint de edicion para reasignar).

---

### 4.9 Obtener Locations

```
GET /v1/locations
```

**Auth**: Requerida (role: manager, driver)

**Query Params**:
- `location_id` (opcional): Obtener una location especifica

**Response sin filtro (200)**:
```json
{
  "data": [
    {
      "id": "location-uuid",
      "organization_id": "org-uuid",
      "name": "JFK",
      "point": {"type": "Point", "coordinates": [-73.7781, 40.6413]},
      "address": null,
      "radio_zone": 0.5,
      "validation_status": "VALIDATED",
      "provider": "WN",
      "timezone": "America/New_York",
      "created_at": "2026-01-01T00:00:00Z"
    }
  ]
}
```

---

### 4.10 Obtener Hoteles por Location

```
GET /v1/locations/{location_id}/hotels
```

**Auth**: Requerida (role: manager, driver)

**Query Params**:
| Param | Tipo | Descripcion |
|-------|------|-------------|
| `name` | string | Buscar por nombre |
| `exact` | bool (default false) | Match exacto o parcial |
| `skip` | int | Offset |
| `limit` | int (max 100) | Limite |

**Response (200)**:
```json
{
  "data": [
    {
      "id": "hotel-uuid",
      "name": "Hilton Downtown",
      "location_id": "location-uuid",
      "address": "123 Main St",
      "point": {"type": "Point", "coordinates": [-73.98, 40.74]},
      "radio_zone": 0.05,
      "validation_status": "VALIDATED"
    }
  ],
  "skip": 0,
  "limit": 20,
  "total": 5
}
```

---

### 4.11 Obtener Airlines por Location

```
GET /v1/locations/{location_id}/airlines
```

**Auth**: Requerida (role: manager, driver)

**Response (200)**:
```json
{
  "location_id": "location-uuid",
  "location_name": "JFK",
  "airlines": ["AA", "BA", "UA", "WN"],
  "total": 4
}
```

---

### 4.12 Obtener Meses Disponibles

```
GET /v1/locations/{location_id}/months?airline=WN
```

**Auth**: Requerida (role: manager, driver)

**Response (200)**:
```json
{
  "location_id": "location-uuid",
  "location_name": "JFK",
  "airline": "WN",
  "months": [
    {"year": 2026, "month": 0, "count": 1341},
    {"year": 2026, "month": 1, "count": 890}
  ],
  "total_months": 2
}
```

> **NOTA**: `month` usa formato JavaScript (0-11), no SQL (1-12).

---

### 4.13 Obtener Dias Disponibles

```
GET /v1/locations/{location_id}/days?year=2026&month=0&airline=WN
```

**Auth**: Requerida (role: manager, driver)

**Response (200)**:
```json
{
  "location_id": "location-uuid",
  "year": 2026,
  "month": 0,
  "timezone": "America/New_York",
  "current_day": 15,
  "days": [
    {"day": 1, "count": 45, "live_count": 12, "history_count": 33},
    {"day": 2, "count": 38, "live_count": 0, "history_count": 38}
  ]
}
```

**Live vs History**: Un trip es "live" si:
- Status = `en_route` (siempre live)
- Status = `scheduled` Y pickup_time esta en el futuro (en timezone local)

---

### 4.14 Timeline Anchor

```
GET /v1/locations/{location_id}/timeline/anchor?airline=WN
```

**Auth**: Requerida (role: manager, driver)

Retorna informacion para "saltar a ahora" en la timeline.

**Response (200)**:
```json
{
  "timezone": "America/New_York",
  "current_date": "2026-01-15",
  "current_time": "15:30:00",
  "first_live_trip": {
    "id": "trip-uuid",
    "pick_up_date": "2026-01-15",
    "pick_up_time": "15:45:00",
    "cursor": "2026-01-15T15:45:00_trip-uuid"
  },
  "today_summary": {
    "total": 24,
    "live": 8,
    "history": 16,
    "by_status": {
      "scheduled": 6,
      "en_route": 2,
      "completed": 14,
      "canceled": 2
    }
  }
}
```

---

### 4.15 Editar Location (Geofence)

```
PATCH /v1/locations/{location_id}
```

**Auth**: Requerida (role: manager, driver)

**Body**:
```json
{
  "point": {"type": "Point", "coordinates": [-73.7781, 40.6413]},
  "radio_zone": 0.5,
  "address": "123 Airport Rd",
  "validation_status": "VALIDATED"
}
```

---

## 5. PERFIL DEL DRIVER

### 5.1 Obtener Perfil

```
GET /v1/profile
```

**Auth**: Requerida (role: manager, driver, crew)

**Response (200)**:
```json
{
  "id": "user-uuid",
  "first_name": "John",
  "last_name": "Doe",
  "email": "john@example.com",
  "phone": "+15551234567",
  "profile_pic": "https://api.gt360.app/uploads/profiles/uuid.jpg",
  "role": "driver",
  "organization_id": "org-uuid",
  "email_verified_at": "2026-01-01T00:00:00Z",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-05T00:00:00Z"
}
```

---

### 5.2 Actualizar Perfil

```
PATCH /v1/profile
```

**Auth**: Requerida (role: manager, driver, crew)

**Body**:
```json
{
  "profile_pic": "https://api.gt360.app/uploads/profiles/new-uuid.jpg"
}
```

> **NOTA**: Actualmente solo `profile_pic` es actualizable por el usuario. Para cambios de nombre, email o telefono, se debe contactar soporte.

**Response**: Retorna el perfil actualizado.

**WebSocket**: Se publica actualizacion via Redis Pub/Sub al canal `profile:{user_id}`.

---

### 5.3 Eliminar Cuenta

```
DELETE /v1/profile
```

**Auth**: Requerida (role: manager, driver, crew)

**Body**:
```json
{
  "password": "MyP@ss123!"
}
```

**Flujo**:
1. Verifica password
2. Elimina registro de `drivers` (por FK)
3. Elimina registro de `users`
4. Irreversible

**Response (200)**:
```json
{
  "status": "ok",
  "message": "Cuenta eliminada correctamente"
}
```

---

## 6. USER SETTINGS (PREFERENCIAS)

### 6.1 Obtener Settings

```
GET /v1/profile/settings
```

**Auth**: Requerida (role: manager, driver, crew)

**Response (200)**:
```json
{
  "user_id": "user-uuid",
  "time_format": "24h",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

> Si no existen settings, se crean automaticamente con `time_format: "24h"`.

---

### 6.2 Actualizar Settings

```
PATCH /v1/profile/settings
```

**Auth**: Requerida (role: manager, driver, crew)

**Body**:
```json
{
  "time_format": "12h"
}
```

**Valores validos**: `"24h"` o `"12h"`

---

## 7. WEBSOCKETS - TIEMPO REAL

### 7.1 WebSocket de Trips

```
WS /ws/trips?location_id={location_uuid}&token={jwt_token}
```

**Auth**: JWT token como query param

**Flujo de conexion**:
1. Se valida el JWT token
2. Se verifica que el usuario tenga acceso a la location (via organization)
3. Se conecta al "room" de la location
4. Se inicia listener de Redis Pub/Sub en canal `loc:{location_id}`
5. Se envia **snapshot** inicial con todos los trips

**Mensaje snapshot (del servidor)**:
```json
{
  "type": "snapshot",
  "location_id": "location-uuid",
  "location_info": {
    "id": "location-uuid",
    "name": "JFK",
    "timezone": "America/New_York"
  },
  "trips": [
    {"id": "trip-uuid", "...todos los campos..."}
  ]
}
```

**Mensajes de eventos en tiempo real**:
```json
{
  "type": "trips_batch",
  "location_id": "location-uuid",
  "events": [
    {
      "trip_id": "trip-uuid",
      "event_type": "insert|update|delete",
      "location_id": "location-uuid",
      "trip": {"...datos del trip..."}
    }
  ]
}
```

**Evento individual** (si SEND_WS_BATCH = false):
```json
{
  "type": "trip_event",
  "event_type": "insert|update|delete",
  "location_id": "location-uuid",
  "trip_id": "trip-uuid",
  "trip": {"...datos del trip..."}
}
```

**Otros eventos que puede recibir**:
```json
{"type": "step_applied", "location_id": "...", "filter_type": "reduce", "..."}
{"type": "step_reverted", "location_id": "...", "filter_type": "reduce", "..."}
{"type": "location_delete_started", "location_id": "...", "trips_count": 100}
{"type": "location_deleted", "location_id": "...", "trips_deleted": 100}
{"type": "batch_insert", "location_id": "...", "trips_count": 500, "months_affected": [...]}
```

**Mensajes del cliente al servidor**:

Ping (keepalive con validacion de token):
```json
{
  "action": "ping",
  "token": "jwt-token-actualizado"
}
```
Respuesta: `{"type": "pong"}` o cierre si token invalido.

Subscribe:
```json
{"action": "subscribe"}
```
Respuesta: `{"type": "subscribed", "location_id": "..."}`

---

### 7.2 WebSocket de Perfil

```
WS /ws/profile?token={jwt_token}
```

**Auth**: JWT token como query param

**Flujo**:
1. Valida token
2. Envia snapshot del perfil
3. Escucha actualizaciones en canal Redis `profile:{user_id}`

**Snapshot inicial**:
```json
{
  "type": "snapshot",
  "data": {
    "id": "user-uuid",
    "first_name": "John",
    "last_name": "Doe",
    "email": "john@example.com",
    "phone": "+15551234567",
    "profile_pic": "...",
    "role": "driver",
    "email_verified_at": "...",
    "created_at": "...",
    "updated_at": "..."
  }
}
```

**Actualizacion en tiempo real**:
```json
{
  "type": "update",
  "data": {"profile_pic": "nueva-url", "type": "profile_pic_updated"}
}
```

**Mensajes del cliente**:

Ping:
```json
{"action": "ping", "token": "jwt-token"}
```

Refresh (solicitar datos frescos):
```json
{"action": "refresh"}
```

---

### 7.3 Arquitectura del Streaming en Tiempo Real

```
PostgreSQL LISTEN/NOTIFY
       |
       v
  trip_streaming.py (subscriber process)
       |
       v  (batches events, max 100 per batch, flush every 200ms)
       |
       v
  HTTP POST -> /v1/webhooks/trips/batch (HMAC signed)
       |
       v
  trip_webhooks.py (Redis pipeline: SET trip + SADD index + PUBLISH)
       |
       v
  Redis Pub/Sub canal: loc:{location_id}
       |
       v
  ws_manager.py -> WebSocket clients
```

**Pipeline de datos**:
1. Trip se modifica en PostgreSQL (INSERT/UPDATE/DELETE)
2. Trigger de PostgreSQL envia NOTIFY
3. `trip_streaming.py` recibe el evento via Subscribe
4. Se agrupan en batches (max 100 eventos, flush cada 200ms)
5. Se envian via HTTP POST firmado (HMAC SHA-256) al webhook
6. El webhook actualiza Redis cache y publica al Pub/Sub
7. `WSManager` recibe del Pub/Sub y reenvia a todos los WebSocket clientes conectados

---

## 8. SOPORTE / CONTACTO

### 8.1 Enviar Mensaje de Soporte

```
POST /v1/support/contact
```

**Publico**: Si (no requiere auth)

**Body**:
```json
{
  "name": "John Doe",
  "email": "john@example.com",
  "category": "bug",
  "subject": "App crashes on pickup",
  "message": "When I try to pick up passengers, the app crashes..."
}
```

**Categorias disponibles**:
```
SupportCategory:
  BUG = "bug"
  FEATURE = "feature"
  QUESTION = "question"
  OTHER = "other"
```

**Response (200)**:
```json
{
  "success": true,
  "message": "Your message has been sent successfully"
}
```

El email se envia a `admin@gt360.app`.

---

## 9. GEOFENCING

El sistema tiene soporte completo para geofencing de drivers y crew.

### 9.1 Conceptos

- **Geofence**: Zona circular definida por un punto central (lat/lon) y un radio (en millas)
- **Actor**: Driver o Crew que genera eventos
- **Target**: Hotel o Airport donde ocurre el evento
- **Anti-Jitter**: Mecanismo que requiere N lecturas consecutivas dentro/fuera para confirmar entrada/salida

### 9.2 Tipos de Evento
```
EventType:
  ENTER = "ENTER"    # El actor entro al geofence
  DWELL = "DWELL"    # El actor permanece dentro (cada N minutos)
  EXIT  = "EXIT"     # El actor salio del geofence
```

### 9.3 Configuracion de Geofence (por organizacion)
```
Defaults:
  dwell_interval_minutes: 5      # Emitir DWELL cada 5 min
  min_consecutive_readings: 3    # 3 lecturas para confirmar ENTER/EXIT
  cooldown_seconds: 30           # Cooldown entre eventos
```

### 9.4 Radio Zones
- **Airport**: Default 1.0, Max 2.0 millas
- **Location**: Max 1.0 millas
- **Hotel**: Max 0.1 millas

> Ver seccion 10.9 para tabla completa de radio zones.

### 9.5 Validacion de Pick-Up y Drop-Off

El pick-up y drop-off usan la formula **Haversine** para calcular la distancia en millas entre la ubicacion del driver y el punto de pickup/dropoff. El radio lo define el `radio_zone` del hotel/location.

---

## 10. ECOSISTEMA GPS / COORDENADAS / UBICACION

Este sistema es 100% backend-agnostico respecto al proveedor de mapas. El backend **solo almacena, valida y compara coordenadas**. No renderiza mapas, no usa APIs de Mapbox/Google Maps, ni genera rutas. El frontend puede usar cualquier proveedor de mapas (Google Maps, Apple Maps, Mapbox, etc.) - solo necesita enviar y recibir coordenadas en el formato correcto.

### 10.1 Formato de Coordenadas: GeoJSON Point

Casi todas las entidades usan **GeoJSON Point** para almacenar ubicaciones:

```json
{
  "type": "Point",
  "coordinates": [longitude, latitude]
}
```

**IMPORTANTE**: El orden en GeoJSON es `[longitude, latitude]`, NO `[latitude, longitude]`. Esto es estandar GeoJSON (RFC 7946).

Ejemplo real:
```json
{
  "type": "Point",
  "coordinates": [-85.7585, 38.2527]
}
```
Esto representa: longitud -85.7585, latitud 38.2527 (Louisville, KY).

**Excepcion - Airport**: Los aeropuertos almacenan `latitude` y `longitude` como campos separados (float), NO como GeoJSON. Esto es porque los datos de aeropuertos se cargan desde fuentes externas con formato lat/lon separado.

### 10.2 Entidades con Coordenadas

| Entidad | Campo | Formato | Max Radio (millas) | Quien lo establece |
|---------|-------|---------|---------------------|-------------------|
| **Airport** | `latitude` + `longitude` | Campos separados (float) | 2.0 (`radio_zone`) | Carga masiva / admin |
| **Location** | `point` (jsonb) | GeoJSON Point | 1.0 (`radio_zone`) | Manager o Driver via `PATCH /v1/locations/{id}` |
| **Hotel** | `point` (jsonb) | GeoJSON Point | 0.1 (`radio_zone`) | Manager via `POST/PATCH /v1/locations/{id}/hotels` |
| **Driver** | `point` (jsonb) | GeoJSON Point | N/A | **Sin endpoint directo** - solo se envia por request |

### 10.3 Airport: Origen de las Coordenadas de Location

Los aeropuertos son la fuente original de coordenadas. Cada Location (que representa un aeropuerto operacional) se crea a partir de un Airport.

**Schema Airport** (`entities.airports`):
```
id: UUID (PK)
code: string (unique, max 10) -- Ej: "SDF", "LAX", "JFK"
name: string (max 150)
latitude: float             -- Rango: -90 a 90 (CHECK constraint)
longitude: float            -- Rango: -180 a 180 (CHECK constraint)
country_code: string (max 5)
zone_code: string (max 4)
radio_zone: float (default 1.0)  -- Max 2.0 millas (CHECK constraint)
last_modified_at: timestamptz | null
last_modified_by: UUID | null (FK -> entities.users.id)
```

**Flujo**: Cuando se crea una Location a partir de un Airport, las coordenadas `latitude`/`longitude` del airport se convierten a GeoJSON Point para el campo `point` de la Location. El `radio_zone` del airport define el radio inicial de la geofence.

### 10.4 Location: Coordenadas del Aeropuerto Operacional

Cada Location tiene un campo `point` (GeoJSON) que representa la posicion del aeropuerto. Tambien tiene `radio_zone` para geofencing.

**Endpoint para actualizar coordenadas de Location:**

```
PATCH /v1/locations/{location_id}
Auth: manager, driver
```

**Body** (`LocationZoneUpdate`):
```json
{
  "point": {"type": "Point", "coordinates": [-85.7585, 38.2527]},
  "radio_zone": 0.5,
  "address": "600 Terminal Dr, Louisville, KY",
  "validation_status": "VALIDATED"
}
```
Todos los campos son opcionales - solo se actualizan los que se envian.

**Response**:
```json
{
  "status": "ok",
  "location": {
    "id": "uuid...",
    "point": {"type": "Point", "coordinates": [-85.7585, 38.2527]},
    "radio_zone": 0.5,
    "address": "600 Terminal Dr, Louisville, KY",
    "validation_status": "VALIDATED",
    "provider": "google",
    "timezone": "America/New_York",
    ...
  }
}
```

**Campo `provider`**: String (max 15 chars) que indica el proveedor de mapas utilizado para establecer las coordenadas. Es informativo - el backend no lo usa para logica.

**Campo `validation_status`**: Controla si la geofence esta habilitada:
- `"NEEDS_VALIDATION"` (default) - Coordenadas pendientes de verificar
- `"VALIDATED"` - Coordenadas verificadas, geofencing activo
- `"DISABLED"` - Geofencing desactivado para esta location

### 10.5 Hotel: Coordenadas del Punto de Pickup/Dropoff

Los hoteles son los puntos fisicos donde el driver recoge o deja a los pasajeros. Cada hotel tiene su propio `point` y `radio_zone`.

**Crear Hotel** (solo manager):
```
POST /v1/locations/{location_id}/hotels
Auth: manager
Status: 201
```

**Body** (`HotelCreate`):
```json
{
  "name": "Hilton Downtown Louisville",
  "point": {"type": "Point", "coordinates": [-85.7631, 38.2471]},
  "radio_zone": 0.05,
  "address": "501 S 4th St, Louisville, KY",
  "validation_status": "VALIDATED"
}
```
Solo `name` es requerido. Los demas campos son opcionales.

**Editar Hotel** (solo manager):
```
PATCH /v1/locations/{location_id}/hotels/{hotel_id}
Auth: manager
```

**Body** (`HotelPointUpdate`):
```json
{
  "point": {"type": "Point", "coordinates": [-85.7631, 38.2471]},
  "radio_zone": 0.05,
  "address": "501 S 4th St, Louisville, KY",
  "validation_status": "VALIDATED"
}
```
Todos los campos son opcionales.

**Validacion**: Si un hotel ya existe con el mismo `name` + `location_id`, el POST retorna `409 Conflict`.

**`validation_status` en Hotel**: Mismo sistema que Location:
- `"NEEDS_VALIDATION"` (default)
- `"VALIDATED"` - Coordenadas confirmadas
- `"DISABLED"` - Geofencing desactivado para este hotel

### 10.6 Driver: Ubicacion GPS (Sin Endpoint Directo)

El campo `driver.point` (GeoJSON) existe en la base de datos pero **NO hay un endpoint REST dedicado para actualizar la posicion del driver**. La ubicacion del driver se envia como parte de las peticiones de pick-up y drop-off.

**El driver NO hace tracking continuo al backend.** En lugar de enviar su posicion cada X segundos, el driver envia su ubicacion solo cuando realiza una accion:

1. **Pick-up**: El driver envia `driver_location` en el body del POST
2. **Drop-off**: El driver envia `driver_location` en el body del POST

Esto significa que la app del driver debe:
- Obtener las coordenadas GPS del dispositivo localmente
- Enviarlas al backend solo al momento de hacer pick-up o drop-off
- El backend NO rastrea la posicion del driver en tiempo real via REST

### 10.7 Flujo Completo: Como la App Obtiene Coordenadas para Pick-Up

Este es el flujo paso a paso de como la app debe obtener las coordenadas necesarias para ejecutar un pick-up:

```
1. OBTENER LA LISTA DE TRIPS:
   GET /v1/locations/{location_id}/trips
   -> Cada trip tiene: pick_up_location (string, ej: "Hilton Downtown")
   -> Cada trip tiene: drop_off_location (string, ej: "SDF")

2. OBTENER LA LISTA DE HOTELES:
   GET /v1/locations/{location_id}/hotels
   -> Cada hotel tiene: point (GeoJSON), radio_zone, name
   -> Buscar el hotel cuyo name coincida con pick_up_location del trip

3. PARA TRIPS INBOUND (aeropuerto -> hotel):
   - pick_up_location = nombre del aeropuerto (Location)
     -> Usar el point y radio_zone de la Location actual
   - drop_off_location = nombre del hotel
     -> Buscar el hotel por nombre y usar su point/radio_zone

4. PARA TRIPS OUTBOUND (hotel -> aeropuerto):
   - pick_up_location = nombre del hotel
     -> Buscar el hotel por nombre y usar su point/radio_zone
   - drop_off_location = nombre del aeropuerto (Location)
     -> Usar el point y radio_zone de la Location actual

5. AL MOMENTO DEL PICK-UP:
   POST /v1/trips/{trip_id}/pick-up
   {
     "driver_id": "uuid-del-driver",
     "driver_location": {    <-- GPS actual del dispositivo del driver
       "type": "Point",
       "coordinates": [-85.7590, 38.2530]
     },
     "pickup_location": {    <-- Coordenadas del hotel o aeropuerto
       "type": "Point",
       "coordinates": [-85.7631, 38.2471]
     },
     "radio_zone": 0.05      <-- Radio del hotel/location
   }

6. AL MOMENTO DEL DROP-OFF:
   POST /v1/trips/{trip_id}/drop-off
   {
     "driver_id": "uuid-del-driver",
     "driver_location": {    <-- GPS actual del dispositivo del driver
       "type": "Point",
       "coordinates": [-85.7631, 38.2470]
     },
     "dropoff_location": {   <-- Coordenadas del destino
       "type": "Point",
       "coordinates": [-85.7585, 38.2527]
     },
     "radio_zone": 0.5       <-- Radio del destino
   }
```

**NOTA IMPORTANTE**: El `radio_zone` lo envia el frontend basandose en los datos del hotel o location que obtuvo previamente. El backend confía en este valor para la validacion de distancia.

### 10.8 Validacion Haversine: Calculo de Distancia

El backend usa la **formula Haversine** para calcular la distancia en millas entre dos coordenadas:

```python
def haversine_distance_miles(lat1, lon1, lat2, lon2):
    R = 3958.8  # Radio de la Tierra en MILLAS
    # ... calcula distancia esferica ...
    return distancia_en_millas
```

**Parametros**: Earth radius = 3958.8 millas (6371 km).

**Logica de validacion**:
```
distancia = haversine(driver_lat, driver_lon, pickup_lat, pickup_lon)

SI distancia > radio_zone:
   -> Error 400:
   {
     "error": "driver_outside_radius",
     "message": "El driver esta fuera del radio de pickup",
     "distance_miles": 0.1234,   <-- Distancia real
     "radius_miles": 0.05        <-- Radio permitido
   }

SI distancia <= radio_zone:
   -> OK, se registra el pick-up/drop-off
```

La app puede usar `distance_miles` y `radius_miles` del error para mostrar al driver cuanto le falta para estar dentro del radio.

### 10.9 Radio Zones: Limites Completos

| Entidad | Default | Maximo | CHECK Constraint |
|---------|---------|--------|-----------------|
| **Airport** | 1.0 millas | 2.0 millas | `radio_zone IS NULL OR radio_zone <= 2.0` |
| **Location** | null | 1.0 millas | `radio_zone IS NULL OR radio_zone <= 1.0` |
| **Hotel** | null | 0.1 millas | `radio_zone IS NULL OR radio_zone <= 0.1` |

**En la practica**:
- Airport radio_zone se usa como referencia al crear una Location
- Location radio_zone se usa para validar pick-up/drop-off cuando el punto es el aeropuerto
- Hotel radio_zone se usa para validar pick-up/drop-off cuando el punto es un hotel
- Si `radio_zone` es `null`, la validacion no aplica (se permite cualquier distancia)

### 10.10 Obtencion de Coordenadas: Endpoints del Driver

Estos son los endpoints que el driver usa para obtener las coordenadas necesarias:

**1. Obtener Location (con point y radio_zone del aeropuerto):**
```
GET /v1/locations?organization_id={org_id}
GET /v1/locations?location_id={loc_id}
Auth: driver
```
Retorna las locations con sus `point` y `radio_zone`.

**2. Obtener Hoteles (con point y radio_zone de cada hotel):**
```
GET /v1/locations/{location_id}/hotels
Auth: driver
```
Retorna la lista de hoteles con sus coordenadas. El driver busca por `name` para encontrar el hotel correspondiente al `pick_up_location` o `drop_off_location` del trip.

**3. Trip Details (incluye hotel_data con coordenadas):**
```
GET /v1/locations/{location_id}/trips/{trip_id}/details
Auth: driver
```
Retorna el trip con datos expandidos. Si la `pick_up_location` o `drop_off_location` corresponde a un hotel, los datos del hotel (incluyendo `point`) se incluyen en la respuesta.

### 10.11 Resumen para la App del Driver

```
DATOS QUE LA APP NECESITA ALMACENAR LOCALMENTE:
===============================================
1. Location actual del driver (organization_id + location_id del sign-in)
   -> GET /v1/locations?location_id={loc_id}
   -> Guardar: point (coordenadas del aeropuerto) + radio_zone

2. Lista de hoteles de la location
   -> GET /v1/locations/{loc_id}/hotels
   -> Guardar: name, point, radio_zone de cada hotel

3. GPS del dispositivo del driver (permisos del OS)
   -> Solo se necesita al momento de pick-up y drop-off

CUANDO EL DRIVER HACE PICK-UP:
==============================
- Tomar GPS actual del dispositivo -> driver_location
- Buscar coordenadas del punto de pickup:
  - Si es hotel: buscar hotel por nombre en la lista local -> point + radio_zone
  - Si es aeropuerto: usar el point + radio_zone de la Location
- Enviar todo al backend en POST /v1/trips/{id}/pick-up

CUANDO EL DRIVER HACE DROP-OFF:
===============================
- Tomar GPS actual del dispositivo -> driver_location
- Buscar coordenadas del punto de destino:
  - Si es hotel: buscar hotel por nombre -> point + radio_zone
  - Si es aeropuerto: usar el point + radio_zone de la Location
- Enviar todo al backend en POST /v1/trips/{id}/drop-off
```

---

## 11. MODELOS DE BASE DE DATOS

### 11.1 User (entities.users)
```
id: UUID (PK)
first_name: string | null
last_name: string | null
email: string (unique, not null)
password_hash: string (not null)
phone: string | null (unique)
profile_pic: string | null (unique)
role: string (not null) ["admin", "manager", "crew", "driver"]
email_verified_at: timestamptz | null
created_at: timestamptz (default now)
updated_at: timestamptz (default now)
password_reset_nonce: string | null
```

### 11.2 Driver (entities.drivers)
```
id: UUID (PK, FK -> entities.users.id, ON DELETE CASCADE)
is_active: bool (default false)
point: jsonb | null  (GeoJSON Point - ubicacion GPS actual)
location_id: UUID | null (FK -> entities.locations.id)
organization_id: UUID (FK -> entities.organizations.id)
pay_type: string | null ["day", "hour", "trip"]
pay_frequency: string | null ["daily", "weekly", "biweekly"]
rate: decimal | null
profile_pic_url: string | null (unique)
shift_start_time: time | null  (hora de inicio del turno, ej: 08:00)
shift_end_time: time | null    (hora de fin del turno, ej: 20:00)
work_days: jsonb | null        (dias de trabajo, ej: ["mon","tue","wed","thu","fri"])
```

### 11.3 Trip (trips.trips)
```
id: UUID (PK, default gen_uuid)
assigned_driver: UUID | null (FK -> entities.drivers.id)
location_id: UUID (FK -> entities.locations.id, not null)
trip_hash: string (not null)
pick_up_date: date (not null)
pick_up_time: time (not null)
pick_up_location: string (not null)
drop_off_location: string (not null)
airline: string (not null)
flight_number: string (not null)
trip_type: string | null ["inbound", "outbound", "ground"]
riders: jsonb | null  (ej: {"pilots": 2, "flight_attendants": 4})
started_at: timestamptz | null
picked_up_at: timestamptz | null
dropped_off_at: timestamptz | null
created_at: timestamptz (default now)
updated_at: timestamptz (default now)
original_pick_up_time: time | null
reduce_applied: bool (default false)
combine_applied: bool (default false)
expand_applied: bool (default false)
filtered_at: timestamptz | null
current_step_id: UUID | null (FK -> trips.filter_steps.id)
status: string (default "scheduled") ["scheduled", "en_route", "completed", "canceled"]
```

### 11.4 TripHistory (trips.trips_history)
Esquema identico a Trip. Almacena trips archivados.

### 11.5 Location (entities.locations)
```
id: UUID (PK)
organization_id: UUID (FK -> entities.organizations.id)
name: string (nombre del aeropuerto, ej: "JFK")
point: jsonb | null (GeoJSON Point)
address: string | null
radio_zone: float | null (max 1.0 millas)
validation_status: string ["NEEDS_VALIDATION", "VALIDATED", "DISABLED"]
provider: string | null
timezone: string (default "America/New_York", IANA format)
created_at: timestamptz
```

### 11.6 Airport (entities.airports)
```
id: UUID (PK)
code: string (max 10, unique) -- Ej: "SDF", "LAX"
name: string (max 150)
latitude: float              -- CHECK: -90 a 90
longitude: float             -- CHECK: -180 a 180
country_code: string (max 5)
zone_code: string (max 4)
radio_zone: float | null (default 1.0, max 2.0 millas)
last_modified_at: timestamptz | null
last_modified_by: UUID | null (FK -> entities.users.id)
```
**NOTA**: Airport usa lat/lon separados, NO GeoJSON. Ver seccion 10.3.

### 11.7 Hotel (entities.hotels)
```
id: UUID (PK)
name: string (max 250)
location_id: UUID (FK -> entities.locations.id)
address: string | null
point: jsonb | null (GeoJSON Point)
radio_zone: float | null (max 0.1 millas)
validation_status: string ["NEEDS_VALIDATION", "VALIDATED", "DISABLED"]
validated_at: timestamptz | null
validated_by: UUID | null
last_modified_at: timestamptz | null
last_modified_by: UUID | null
created_at: timestamptz
updated_at: timestamptz
```
Unique constraint: `(name, location_id)`

### 11.8 Token (auth.tokens)
```
id: UUID (PK)
user_id: UUID (FK -> entities.users.id)
token_hash: string (SHA-256)
expires_at: timestamptz
revoked: bool (default false)
token_type: string ["refresh"]
```

### 11.9 UserSettings (settings.user_settings)
```
user_id: UUID (PK, FK -> entities.users.id)
time_format: string ["24h", "12h"] (default "24h")
created_at: timestamptz
updated_at: timestamptz
```

### 11.10 Organization (entities.organizations)
```
id: UUID (PK)
manager_id: UUID (FK -> entities.managers.id)
name: string (unique)
address: string | null
website: string | null
status: string ["active"]
plan: string (ej: "freemium", "pro", "enterprise")
```

### 11.11 GeofenceEvent (geofencing.geofence_events)
```
id: UUID (PK)
actor_type: string ["driver", "crew"]
actor_id: UUID (FK -> entities.users.id)
target_type: string ["hotel", "airport"]
target_id: UUID
location_id: UUID (FK -> entities.locations.id)
organization_id: UUID (FK -> entities.organizations.id)
event_type: string ["ENTER", "DWELL", "EXIT"]
reported_lat: float
reported_lon: float
distance_to_center: float (millas)
dwell_minutes: int | null
total_time_inside_seconds: int | null
created_at: timestamptz
```

### 11.12 GeofenceState (geofencing.geofence_states)
```
id: UUID (PK)
actor_type: string
actor_id: UUID
target_type: string
target_id: UUID
is_inside: bool (default false)
consecutive_inside_count: int (default 0)
consecutive_outside_count: int (default 0)
last_enter_at: timestamptz | null
last_exit_at: timestamptz | null
last_dwell_at: timestamptz | null
last_position_at: timestamptz
last_lat: float | null
last_lon: float | null
last_distance: float | null (millas)
```
Unique constraint: `(actor_type, actor_id, target_type, target_id)`

---

## 12. FLUJOS COMPLETOS (DIAGRAMAS)

### 12.1 Login del Driver
```
1. Driver abre app
2. POST /v1/auth/sign-in {email, password}
3. Recibe: access_token + refresh_token + user_data
4. Guarda tokens localmente
5. Extrae de user_data: organization_id, location_id, role
6. Usa access_token en Header: "Authorization: Bearer {token}"
```

### 12.2 Activacion del Driver (ir Online)
```
1. PATCH /v1/drivers/me/active {is_active: true}
2. Si OK: UI cambia a "Online" (verde)
3. Conectar WebSocket: /ws/trips?location_id={loc}&token={jwt}
4. Recibe snapshot de todos los trips
5. Filtra localmente: trips donde assigned_driver == mi_id
```

### 12.3 Flujo Completo de un Trip
```
1. Driver ve trip asignado en lista "Live"
2. Tap en "Start Trip"
   -> POST /v1/trips/{id}/start
   -> Valida: driver activo, tiempo permitido, driver asignado
   -> Status: scheduled -> en_route
   -> UI: Boton cambia a "Navigate"

3. Driver navega al punto de pickup
   -> La app usa GPS para tracking

4. Driver llega al pickup, tap "Pick Up"
   -> POST /v1/trips/{id}/pick-up
   -> Valida: driver dentro del radio (Haversine)
   -> Si fuera del radio: muestra distancia y error
   -> Si OK: picked_up_at = now

5. Driver navega al destino con pasajeros

6. Driver llega al destino, tap "Drop Off"
   -> POST /v1/trips/{id}/drop-off
   -> Valida: driver dentro del radio del destino
   -> Si OK: dropped_off_at = now, status = completed
   -> Trip desaparece de "Live" y va a "History"

ALTERNATIVA - Relief (soltar trip):
   En cualquier momento entre paso 2 y paso 6 (antes del drop-off):
   -> POST /v1/trips/{id}/relief
   -> Valida: driver activo, es el driver asignado, trip en EN_ROUTE
   -> Resetea: assigned_driver=null, status=scheduled, timestamps=null
   -> Trip vuelve a "Live" sin driver asignado
   -> Cualquier otro driver puede tomarlo
```

### 12.4 Desconexion del Driver (ir Offline)
```
1. PATCH /v1/drivers/me/active {is_active: false}
2. Si tiene trips activos: ERROR 409 (debe completarlos primero)
3. Si OK: UI cambia a "Offline" (gris)
4. Desconectar WebSocket
```

### 12.5 Refresh de Token
```
1. Access token expira
2. POST /v1/auth/refresh {refresh_token: "..."}
3. Recibe nuevos: access_token + refresh_token
4. Actualiza tokens localmente
5. Continua operacion normal
```

---

## 13. HEADERS Y AUTENTICACION REQUERIDA

### Header requerido en todas las peticiones autenticadas:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### Rutas publicas (no requieren auth):
```
/v1/auth/register/*
/v1/auth/sign-in
/v1/auth/refresh
/v1/auth/verify-email
/v1/auth/forgot-password
/v1/auth/reset-password
/v1/auth/verify-data
/v1/support/contact
/v1/trips/search/qr
/v1/crew-lookup/config
/v1/crew-lookup/health
/docs
/redoc
/health
/ready
/uploads/*
```

### Content-Type
- `application/json` para todos los endpoints REST
- Archivos: `multipart/form-data` para upload de foto de perfil

---

## 14. CODIGOS DE ERROR

| Codigo | Significado |
|--------|-------------|
| `400` | Bad Request - Parametros invalidos, formato incorrecto, driver fuera de radio |
| `401` | Unauthorized - Token invalido, expirado, faltante, o email no verificado |
| `403` | Forbidden - Rol incorrecto, driver no asignado al trip, driver inactivo |
| `404` | Not Found - Trip, driver, location, o usuario no encontrado |
| `409` | Conflict - Email ya existe, trip ya iniciado, no puede ir offline con trips activos |
| `422` | Unprocessable - Error de validacion del Excel |
| `500` | Internal Server Error |

### Formato de Error estandar:
```json
{
  "detail": "Mensaje descriptivo del error"
}
```

### Formato de Error especial (geofencing):
```json
{
  "detail": {
    "error": "driver_outside_radius",
    "message": "El driver esta fuera del radio de pickup",
    "distance_miles": 0.1234,
    "radius_miles": 0.05
  }
}
```

---

## RESUMEN DE TODOS LOS ENDPOINTS PARA EL DRIVER

### Autenticacion
| Metodo | Endpoint | Auth | Descripcion |
|--------|----------|------|-------------|
| POST | `/v1/auth/sign-in` | No | Login |
| POST | `/v1/auth/sign-out/` | Si | Logout |
| POST | `/v1/auth/refresh` | No | Refresh token |
| POST | `/v1/auth/forgot-password` | No | Solicitar reset de password |
| POST | `/v1/auth/reset-password` | No | Resetear password con token |
| PUT | `/v1/auth/change-password` | Si | Cambiar password (con actual) |
| GET | `/v1/auth/verify-email` | No | Verificar email |

### Estado del Driver
| Metodo | Endpoint | Auth | Descripcion |
|--------|----------|------|-------------|
| GET | `/v1/drivers/me/status` | driver | Obtener is_active |
| PATCH | `/v1/drivers/me/active` | driver | Cambiar online/offline |

### Trips
| Metodo | Endpoint | Auth | Descripcion |
|--------|----------|------|-------------|
| GET | `/v1/locations/{loc}/trips` | driver | Lista paginada de trips |
| GET | `/v1/locations/{loc}/trips/history` | driver | Trips historicos |
| GET | `/v1/locations/{loc}/trips/{trip}/details` | driver | Detalle completo de un trip |
| POST | `/v1/trips/{trip}/start` | driver | Iniciar trip |
| POST | `/v1/trips/{trip}/pick-up` | driver | Pickup (con geovalidacion) |
| POST | `/v1/trips/{trip}/drop-off` | driver | Drop off (con geovalidacion) |
| POST | `/v1/trips/{trip}/relief` | driver | Soltar trip (devolver a scheduled sin driver) |
| PATCH | `/v1/orgs/{org}/locations/{loc}/trips/{trip}/assign` | driver | Auto-asignarse a un trip |

### Locations & Metadata
| Metodo | Endpoint | Auth | Descripcion |
|--------|----------|------|-------------|
| GET | `/v1/locations` | driver | Lista de locations |
| PATCH | `/v1/locations/{loc}` | driver | Editar location (geofence) |
| GET | `/v1/locations/{loc}/hotels` | driver | Lista de hoteles |
| GET | `/v1/locations/{loc}/airlines` | driver | Airlines disponibles |
| GET | `/v1/locations/{loc}/months` | driver | Meses con trips |
| GET | `/v1/locations/{loc}/days` | driver | Dias con conteo live/history |
| GET | `/v1/locations/{loc}/timeline/anchor` | driver | Anchor para "saltar a ahora" |

### Perfil & Settings
| Metodo | Endpoint | Auth | Descripcion |
|--------|----------|------|-------------|
| GET | `/v1/profile` | driver | Obtener perfil |
| PATCH | `/v1/profile` | driver | Actualizar perfil |
| DELETE | `/v1/profile` | driver | Eliminar cuenta |
| GET | `/v1/profile/settings` | driver | Obtener preferencias |
| PATCH | `/v1/profile/settings` | driver | Actualizar preferencias |

### Soporte
| Metodo | Endpoint | Auth | Descripcion |
|--------|----------|------|-------------|
| POST | `/v1/support/contact` | No | Enviar mensaje de soporte |

### WebSockets
| Protocolo | Endpoint | Auth | Descripcion |
|-----------|----------|------|-------------|
| WS | `/ws/trips?location_id={loc}&token={jwt}` | JWT | Trips en tiempo real |
| WS | `/ws/profile?token={jwt}` | JWT | Perfil en tiempo real |
