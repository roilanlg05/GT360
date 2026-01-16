# GT360 Backend - Arquitectura y Workflow

## 📋 Resumen Ejecutivo

Este documento describe la arquitectura completa y el flujo de datos del backend GT360, diseñado para gestionar **trips** (viajes de transporte de pasajeros de aerolíneas) y **flight tracking** (seguimiento de vuelos en tiempo real).

**Audiencia:** Desarrolladores externos que necesitan integrar APIs de flight tracking con el sistema GT360.

---

## 🏗️ Stack Tecnológico

### Core Framework
- **FastAPI** (Python 3.14): Framework web asíncrono de alto rendimiento
- **psqlmodel**: ORM personalizado para PostgreSQL con soporte async
- **PostgreSQL 16+**: Base de datos principal con schemas separados
- **Redis**: Cache, pub/sub para WebSockets, y métricas

### Librerías Principales
```python
fastapi==0.115.12
psqlmodel==2.2.0
redis[hiredis]==5.2.4
httpx==0.28.2          # Cliente HTTP asíncrono
pydantic==2.11.4       # Validación de datos
python-jose[cryptography]  # JWT tokens
```

### Infrastructure
- **Docker + Docker Compose**: Containerización
- **Uvicorn**: ASGI server (producción)
- **Nginx**: Reverse proxy (no incluido en este repo)

---

## 📁 Estructura del Proyecto

```
/home/backend/GT360/
├── main.py                    # Entry point, FastAPI app
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
│
├── features/                  # Feature-based architecture
│   ├── auth/                  # Autenticación JWT
│   │   ├── routes/
│   │   ├── middlewares/       # VerifyToken middleware
│   │   └── utils/             # decode_token()
│   │
│   ├── trips/                 # Core: Gestión de trips
│   │   ├── routes/
│   │   │   └── trips_router.py
│   │   ├── models/
│   │   │   └── trip_model.py
│   │   ├── services/
│   │   ├── websockets/
│   │   │   ├── trip_websockets.py    # /ws/trips
│   │   │   └── org_websockets.py     # /ws/org
│   │   ├── webhooks/
│   │   └── utils/
│   │
│   └── flights/               # Flight Tracking API
│       ├── routes/
│       │   └── flights_router.py
│       ├── models/
│       │   └── flight_models.py
│       └── services/
│           └── flight_cache.py
│
├── shared/                    # Componentes compartidos
│   ├── db/
│   │   ├── db_config.py       # psqlmodel engine
│   │   └── schemas/           # Modelos de DB
│   │       ├── trips/
│   │       │   └── trips.py   # Trip schema
│   │       ├── entities/
│   │       │   └── locations.py
│   │       └── ...
│   │
│   ├── redis/
│   │   └── redis_client.py
│   │
│   ├── middlewares/
│   │   ├── verify_token.py
│   │   ├── rate_limiter.py
│   │   ├── requests_logger.py
│   │   └── exceptions_handler.py
│   │
│   └── settings.py            # Environment variables
│
├── migrations/                # SQL migrations
│   ├── 001_add_status_column_to_trips.sql
│   └── 002_modify_trigger_batch_mode.sql
│
├── docs/                      # Documentación técnica
│   ├── FLIGHT_TRACKING_API.md
│   ├── BACKEND_DUPLICATE_TRIPS_HANDLING.md
│   └── ...
│
└── services/                  # Background services
    └── streaming/
        └── trip_streaming.py
```

---

## 🗄️ Arquitectura de Base de Datos

### PostgreSQL - Schemas Separados

```sql
-- Schemas principales
CREATE SCHEMA entities;  -- Organizations, Locations, Drivers, Hotels
CREATE SCHEMA trips;     -- Trips, Trips History
CREATE SCHEMA auth;      -- Users, Sessions (Auth0 integration)
```

### Tabla: `trips.trips` (Principal)

**Constraint de Unicidad (7 campos):**
```sql
UNIQUE (
    location_id,
    pick_up_date,
    pick_up_time,
    airline,
    flight_number,
    pick_up_location,
    drop_off_location
)
```

**Campos Principales:**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | UUID | PK, generado automáticamente |
| `location_id` | UUID | FK → `entities.locations.id` |
| `pick_up_date` | Date | Fecha del trip (2025-06-01) |
| `pick_up_time` | Time with timezone | Hora de pickup en timezone local |
| `airline` | String | Código IATA (WN, AA, DL) |
| `flight_number` | String | Número de vuelo (1234) |
| `pick_up_location` | String | Origen (SDF, hotel name) |
| `drop_off_location` | String | Destino (SDF, hotel name) |
| `trip_type` | String | `inbound`, `outbound`, `ground` |
| `riders` | JSONB | Array de pasajeros `[{name, phone}]` |
| `status` | String | `scheduled`, `en_route`, `canceled` |
| `assigned_driver` | UUID | FK → `entities.drivers.id` (nullable) |
| `created_at` | Timestamptz | Timestamp de creación |
| `updated_at` | Timestamptz | Última actualización |

**Triggers PostgreSQL:**
```sql
-- Trigger que envía eventos a Redis cuando se modifica un trip
CREATE TRIGGER trip_changed_trigger
AFTER INSERT OR UPDATE OR DELETE ON trips.trips
FOR EACH ROW
EXECUTE FUNCTION notify_trip_change();
```

### Tabla: `entities.locations`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | UUID | PK |
| `organization_id` | UUID | FK → `entities.organizations.id` |
| `name` | String | Código de aeropuerto (SDF, LAX) |
| `timezone` | String | Timezone IANA (America/New_York) |
| `point` | JSONB | GeoJSON Point `{type, coordinates}` |
| `provider` | String | Proveedor de transporte (api, uber) |

---

## 🔄 Arquitectura de Eventos (Redis Pub/Sub)

### Canales de Redis

```
org:{organization_id}  → Eventos a nivel de organización
loc:{location_id}      → Eventos específicos de una location
```

### Tipos de Eventos WebSocket

#### 1. **Trip Events** (Individuales)

```json
{
  "type": "trip_created",
  "location_id": "uuid",
  "location_name": "SDF",
  "trip": {
    "id": "uuid",
    "pick_up_date": "2025-06-01",
    "pick_up_time": "12:30:00-04:00",
    "airline": "WN",
    "flight_number": "3209",
    "status": "scheduled"
  }
}
```

**Eventos disponibles:**
- `trip_created`
- `trip_updated`
- `trip_deleted`

#### 2. **Batch Insert Event**

```json
{
  "type": "batch_insert",
  "location_id": "uuid",
  "location_name": "SDF",
  "airline": "WN",
  "trips_count": 1247,
  "months_affected": [
    {"year": 2025, "month": 5, "count": 450},
    {"year": 2025, "month": 6, "count": 797}
  ],
  "message": "1247 trips uploaded successfully"
}
```

**Cuándo se emite:** Después de subir un archivo Excel con múltiples trips.

**Propósito:** Evitar enviar 1000+ eventos individuales que saturen el frontend.

#### 3. **Location Events**

```json
{
  "type": "location_deleted",
  "location_id": "uuid",
  "location_name": "SDF",
  "deleted_hotels_count": 12,
  "message": "Location SDF and 12 hotels deleted"
}
```

---

## 🌐 Arquitectura de WebSockets

### 1. **WebSocket Manager Pattern**

```python
# Singleton manager que gestiona todas las conexiones WebSocket
class OrgWebSocketManager:
    def __init__(self):
        self.rooms: Dict[str, List[WebSocket]] = {}
        self.listeners: Dict[str, asyncio.Task] = {}

    async def connect(self, ws: WebSocket, org_id: str, claims: dict):
        # Agregar ws a la sala de la organización
        pass

    async def disconnect(self, ws: WebSocket):
        # Remover ws de todas las salas
        pass

    async def broadcast_to_org(self, org_id: str, message: dict):
        # Enviar mensaje a todos los clientes de una org
        pass

    async def ensure_org_listener(self, org_id: str):
        # Crear listener de Redis para el canal org:{org_id}
        pass
```

### 2. **Endpoints WebSocket**

#### `/ws/org` - Eventos de Organización

**Query Params:**
- `organization_id`: UUID de la organización
- `token`: JWT token

**Eventos recibidos:**
- `batch_insert` (upload masivo de trips)
- `location_deleted`
- `location_created`

**Ejemplo de conexión:**
```javascript
const ws = new WebSocket(
  `wss://api.gt360.app/ws/org?organization_id=${orgId}&token=${jwt}`
);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'batch_insert') {
    console.log(`${data.trips_count} trips uploaded`);
  }
};
```

#### `/ws/trips` - Eventos de Location Específica

**Query Params:**
- `location_id`: UUID de la location
- `token`: JWT token

**Eventos recibidos:**
- `trip_created`
- `trip_updated`
- `trip_deleted`

#### `/v1/ws/flights/{flight_number}/{date_local}` - Flight Tracking

**Query Params:**
- `token`: JWT token

**Características:**
- Polling adaptativo (1-10s según estado del vuelo)
- Cache inteligente con TTL dinámico
- Autenticación JWT con ping/pong

---

## 🔐 Autenticación y Autorización

### JWT Token Structure

```json
{
  "sub": "user_id_uuid",
  "iat": 1768501080,
  "exp": 1768504680,
  "metadata": {
    "email": "user@example.com",
    "phone": "+14028605985",
    "role": "manager",
    "organization_id": "org_uuid"
  }
}
```

### Middleware Stack (Orden de Ejecución)

```python
# 1. CORS (preflight OPTIONS)
app.add_middleware(CORSMiddleware, ...)

# 2. DenyDotfileMiddleware (seguridad)
app.add_middleware(DenyDotfileMiddleware)

# 3. HTTPErrorHandler (manejo de errores 500)
app.add_middleware(HTTPErrorHandler)

# 4. RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

# 5. VerifyToken (autenticación JWT)
app.add_middleware(VerifyToken)

# 6. RequestLoggerMiddleware (logs)
app.add_middleware(RequestLoggerMiddleware)
```

**Rutas Públicas (Sin JWT):**
- `GET /v1/flights/*` (todos los endpoints REST de flights)
- `POST /v1/flights/batch`
- `GET /v1/flights/metrics`
- `GET /v1/flights/rate-limit`

**Rutas Protegidas:**
- Todos los endpoints de `/v1/trips/*`
- Todos los WebSockets

---

## 📊 Workflow Completo: Upload de Trips

### Paso 1: Cliente Sube Excel

```http
POST /v1/trips/upload-trips?airport=SDF&airline=WN&provider=api
Authorization: Bearer JWT_TOKEN
Content-Type: multipart/form-data

file: SDF_June_2025.xlsx
```

### Paso 2: Backend Procesa Archivo

```python
# 1. Validar JWT y extraer organization_id
# 2. Parsear Excel → List[TripImport]
# 3. Validar unicidad de trips contra DB
# 4. Verificar/Crear Location
# 5. Activar batch mode (SET LOCAL app.batch_insert_mode = 'true')
# 6. Insertar trips en chunks de 5000
# 7. Commit transacción
# 8. Publicar evento batch_insert a Redis
```

**Manejo de Duplicados:**
```python
# Si detecta duplicado:
raise HTTPException(
    status_code=422,
    detail="We couldn't validate the schedule: Key (...) already exists."
)
# ROLLBACK completo - NO hay inserción parcial
```

### Paso 3: Publicación a Redis

```python
# Calcular meses afectados
months_affected = [
    {"year": 2025, "month": 5, "count": 450},
    {"year": 2025, "month": 6, "count": 797}
]

# Publicar al canal de la organization
await redis.publish(
    f"org:{organization_id}",
    json.dumps({
        "type": "batch_insert",
        "trips_count": 1247,
        "months_affected": months_affected,
        ...
    })
)
```

### Paso 4: WebSocket Manager Distribuye

```python
# El listener de Redis recibe el evento
async def listen_to_redis(org_id: str):
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"org:{org_id}")

    async for message in pubsub.listen():
        # Broadcast a todos los clientes conectados
        await org_manager.broadcast_to_org(org_id, message)
```

### Paso 5: Frontend Recibe Evento

```javascript
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.type === 'batch_insert') {
    // Actualizar UI
    showToast(`${data.trips_count} trips uploaded`);

    // Refrescar paginador si el mes afectado está visible
    if (isCurrentMonthAffected(data.months_affected)) {
      refetchTrips();
    }
  }
};
```

---

## 🛫 Workflow: Flight Tracking Integration

### Arquitectura Actual

```
Frontend Request
    ↓
FastAPI /v1/flights/{flight}/{date}
    ↓
FlightCache (Redis)
    ↓ (cache miss)
AeroDataBox API
    ↓
Cache + Return to Frontend
```

### Componentes Clave

#### 1. **Flight Cache Service**

```python
class FlightCache:
    """
    Redis cache con TTL dinámico basado en estado del vuelo:
    - Landed/Arrived: 60s cache
    - En route (close): 2-3s cache
    - En route (far): 5-10s cache
    - Scheduled: 15s cache
    """

    async def get_or_fetch(
        self,
        flight_number: str,
        date_local: str
    ) -> FlightSnapshot:
        # 1. Verificar cache de Redis
        # 2. Si cache miss → llamar AeroDataBox API
        # 3. Guardar en cache con TTL apropiado
        # 4. Retornar snapshot
```

#### 2. **Flight Models**

```python
class FlightSnapshot(BaseModel):
    flight_number: str
    date_local: str
    status: str  # Scheduled, Boarding, EnRoute, Landed, Canceled
    eta_utc: datetime
    minutes_to_arrival: int
    duration_seconds: int
    position: Position | None
    legs: List[Leg]
    ws_interval_seconds: int  # Recomendado para WebSocket
    provider_last_updated_utc: datetime
    cached_at_utc: datetime
    cache_ttl_seconds: int
```

#### 3. **Endpoints Disponibles**

| Endpoint | Método | Propósito |
|----------|--------|-----------|
| `/v1/flights/{flight}/{date}` | GET | Snapshot completo |
| `/v1/flights/{flight}/{date}/eta` | GET | Solo ETA (lightweight) |
| `/v1/flights/{flight}/{date}/legs` | GET | Segmentos del vuelo |
| `/v1/flights/batch` | POST | Múltiples vuelos en paralelo |
| `/v1/flights/metrics` | GET | Estadísticas de uso |
| `/v1/flights/rate-limit` | GET | Estado del rate limiter |
| `/v1/ws/flights/{flight}/{date}` | WS | Tracking en tiempo real |

---

## 🔗 Integración Propuesta: Trip ↔ Flight

### Objetivo

Enriquecer los trips con información de flight tracking en tiempo real:

```json
{
  "id": "trip_uuid",
  "pick_up_date": "2025-06-01",
  "airline": "WN",
  "flight_number": "3209",
  "status": "scheduled",

  // ✨ NUEVO: Datos de flight tracking
  "flight_tracking": {
    "flight_status": "EnRoute",
    "eta_utc": "2025-06-01T18:30:00Z",
    "minutes_to_arrival": 45,
    "position": {
      "lat": 38.1234,
      "lon": -85.5678
    },
    "last_updated": "2025-06-01T17:45:00Z"
  }
}
```

### Opciones de Arquitectura

#### **Opción A: Backend Enriquece Trips (Recomendado)**

**Ventajas:**
- ✅ Centralizado - un solo source of truth
- ✅ Frontend recibe datos listos para mostrar
- ✅ Cache compartido entre múltiples clientes
- ✅ Menor carga en el frontend

**Desventajas:**
- ❌ Mayor latencia en endpoint de trips
- ❌ Requiere modificar backend actual

**Implementación:**

```python
# En trips_router.py
@router.get("/v1/locations/{location_id}/trips")
async def get_trips(
    location_id: str,
    include_flight_tracking: bool = Query(False)
):
    trips = await fetch_trips_from_db(location_id)

    if include_flight_tracking:
        # Obtener flight tracking para todos los trips
        flight_requests = [
            {
                "flight_number": f"{trip.airline}{trip.flight_number}",
                "date_local": trip.pick_up_date.isoformat()
            }
            for trip in trips
        ]

        # Llamar endpoint batch de flights
        flight_snapshots = await get_flights_batch(flight_requests)

        # Enriquecer trips
        for trip in trips:
            key = f"{trip.airline}{trip.flight_number}_{trip.pick_up_date}"
            if key in flight_snapshots:
                trip.flight_tracking = flight_snapshots[key]

    return trips
```

#### **Opción B: Frontend Llama Ambos Endpoints**

**Ventajas:**
- ✅ No modifica backend de trips
- ✅ Más flexible para el frontend
- ✅ Menor latencia en endpoint de trips

**Desventajas:**
- ❌ Duplica lógica en frontend
- ❌ Múltiples requests HTTP
- ❌ Mayor complejidad en frontend

**Implementación:**

```typescript
// Frontend
const trips = await fetchTrips(locationId);
const flights = await fetchFlightsBatch(
  trips.map(t => ({
    flight_number: `${t.airline}${t.flight_number}`,
    date_local: t.pick_up_date
  }))
);

// Merge manualmente
const enrichedTrips = trips.map(trip => ({
  ...trip,
  flight_tracking: flights.find(f =>
    f.flight_number === `${trip.airline}${trip.flight_number}`
  )
}));
```

#### **Opción C: Nuevo Endpoint Híbrido**

**Ventajas:**
- ✅ No modifica endpoints existentes
- ✅ Optimizado para este caso de uso
- ✅ Backend maneja la complejidad

**Desventajas:**
- ❌ Código duplicado parcialmente
- ❌ Más endpoints que mantener

**Implementación:**

```python
# Nuevo endpoint
@router.get("/v1/locations/{location_id}/trips-with-flights")
async def get_trips_with_flight_tracking(location_id: str):
    # Combina lógica de trips + flights
    return enriched_trips
```

---

## 📈 Métricas y Monitoring

### Redis Keys para Métricas

```
flights:metrics:{date}:cache_hits       → Counter
flights:metrics:{date}:cache_misses     → Counter
flights:metrics:{date}:api_calls        → Counter
flights:metrics:{date}:api_errors       → Counter
flights:metrics:{date}:rate_limited     → Counter
```

### Endpoint de Métricas

```http
GET /v1/flights/metrics?date=2025-06-01

Response:
{
  "date": "2025-06-01",
  "cache_hits": 1234,
  "cache_misses": 567,
  "api_calls": 567,
  "api_errors": 12,
  "rate_limited": 3,
  "flights_not_found": 8
}
```

---

## 🚀 Consideraciones para el Desarrollador de Flight Tracking

### 1. **Rate Limiting**

La API de AeroDataBox tiene límites estrictos:
- **150 requests/minuto** (plan básico)
- **500 requests/minuto** (plan pro)

**Implementación actual:**
```python
# En flight_cache.py
class FlightCache:
    async def check_rate_limit(self) -> bool:
        current = await redis.get("flights:rate_limit:current")
        if int(current or 0) >= MAX_REQUESTS_PER_MINUTE:
            return False

        await redis.incr("flights:rate_limit:current")
        await redis.expire("flights:rate_limit:current", 60)
        return True
```

**Recomendación:** Usar el endpoint `/v1/flights/batch` para múltiples vuelos en lugar de hacer N requests individuales.

### 2. **Cache Strategy**

**TTL Dinámico basado en estado:**

| Estado del Vuelo | TTL Cache | Razón |
|------------------|-----------|-------|
| Landed/Arrived | 60s | Estado terminal, no cambia |
| En Route (<=15 min) | 2s | Crítico, actualizaciones frecuentes |
| En Route (15-30 min) | 3s | Importante pero no crítico |
| En Route (>30 min) | 5-10s | Menos urgente |
| Scheduled/Boarding | 15s | Cambios poco frecuentes |

**Implementación:**
```python
def calculate_ttl(status: str, minutes_to_arrival: int) -> int:
    if status in ["Landed", "Arrived"]:
        return 60
    elif status == "EnRoute":
        if minutes_to_arrival <= 15:
            return 2
        elif minutes_to_arrival <= 30:
            return 3
        elif minutes_to_arrival <= 60:
            return 5
        else:
            return 10
    else:
        return 15
```

### 3. **WebSocket Adaptive Polling**

El WebSocket ajusta automáticamente el intervalo de polling:

```javascript
// Cliente recibe snapshot
{
  "flight_number": "WN1234",
  "status": "EnRoute",
  "minutes_to_arrival": 12,
  "ws_interval_seconds": 1  // ← Backend recomienda intervalo
}

// Cliente ajusta su polling
setInterval(() => {
  // Fetch update
}, snapshot.ws_interval_seconds * 1000);
```

### 4. **Manejo de Errores**

**Errores comunes:**

| Error | HTTP Code | Causa | Solución |
|-------|-----------|-------|----------|
| Flight not found | 404 | Vuelo no existe en AeroDataBox | Mostrar "No data available" |
| Rate limited | 429 | Excedió límite de requests | Usar cache, esperar 60s |
| API error | 500 | Error en AeroDataBox | Retry con exponential backoff |
| Invalid flight number | 400 | Formato incorrecto | Validar en frontend |

**Modelo de error:**
```json
{
  "flight_number": "WN9999",
  "date_local": "2025-06-01",
  "status": "ERROR",
  "error_code": "NOT_FOUND",
  "error_message": "Flight not found in provider database"
}
```

### 5. **Timezone Handling**

**CRÍTICO:** Los trips usan **timezone local de la location**:

```python
# Trip model
pick_up_time: time  # 12:30:00-04:00 (America/New_York)

# Flight model
eta_utc: datetime  # 2025-06-01T18:30:00+00:00 (UTC)

# Conversión necesaria
import pytz
location_tz = pytz.timezone(location.timezone)  # "America/New_York"
eta_local = eta_utc.astimezone(location_tz)
```

### 6. **Batch Processing**

Para procesar 50 trips con flight tracking:

```python
# ❌ MAL: 50 requests individuales
for trip in trips:
    flight = await get_flight_snapshot(trip.airline + trip.flight_number, trip.pick_up_date)

# ✅ BIEN: 1 request batch
flight_requests = [
    {"flight_number": f"{t.airline}{t.flight_number}", "date_local": t.pick_up_date}
    for t in trips
]
flights = await get_flights_batch({"flights": flight_requests})
```

---

## 🔧 Variables de Entorno Necesarias

```bash
# PostgreSQL
POSTGRES_SERVER=postgres
POSTGRES_USER=gt360
POSTGRES_PASSWORD=********
POSTGRES_DB=gt360

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# JWT Auth (Auth0)
AUTH0_DOMAIN=gt360.us.auth0.com
AUTH0_AUDIENCE=https://api.gt360.app
JWT_SECRET_KEY=********

# AeroDataBox (Flight Tracking)
AERODATABOX_API_KEY=********
AERODATABOX_BASE_URL=https://aerodatabox.p.rapidapi.com

# Rate Limiting
FLIGHT_API_MAX_REQUESTS_PER_MINUTE=150
```

---

## 📚 Endpoints Relevantes - Resumen

### Trips Management

| Endpoint | Método | Propósito | Auth |
|----------|--------|-----------|------|
| `POST /v1/trips/upload-trips` | POST | Upload Excel con trips | JWT |
| `GET /v1/locations/{id}/trips` | GET | Lista de trips (paginado) | JWT |
| `GET /v1/locations/{id}/months` | GET | Meses disponibles | JWT |
| `GET /v1/locations/{id}/airlines` | GET | Aerolíneas disponibles | JWT |
| `DELETE /v1/trips/{id}` | DELETE | Eliminar trip | JWT |
| `PATCH /v1/trips/{id}` | PATCH | Actualizar trip | JWT |

### Flight Tracking

| Endpoint | Método | Propósito | Auth |
|----------|--------|-----------|------|
| `GET /v1/flights/{flight}/{date}` | GET | Snapshot completo | Público |
| `GET /v1/flights/{flight}/{date}/eta` | GET | Solo ETA | Público |
| `POST /v1/flights/batch` | POST | Múltiples vuelos | Público |
| `GET /v1/flights/metrics` | GET | Métricas de uso | Público |
| `WS /v1/ws/flights/{flight}/{date}` | WS | Real-time tracking | JWT |

### WebSockets

| Endpoint | Tipo | Eventos | Auth |
|----------|------|---------|------|
| `/ws/org` | WS | batch_insert, location_deleted | JWT |
| `/ws/trips` | WS | trip_created, trip_updated, trip_deleted | JWT |
| `/v1/ws/flights/{flight}/{date}` | WS | Flight updates (adaptive polling) | JWT |

---

## 🎯 Recomendaciones para la Integración

### 1. **Usa el Endpoint Batch**

Para dashboards que muestran múltiples trips:
```python
# Obtener 50 trips con flight tracking
trips = fetch_trips(location_id, limit=50)
flights = await get_flights_batch([
    {"flight_number": f"{t.airline}{t.flight_number}", "date_local": t.pick_up_date}
    for t in trips
])
```

### 2. **Implementa Circuit Breaker**

Si AeroDataBox falla, no degradar toda la UI:
```python
try:
    flight_data = await get_flight_snapshot(...)
except Exception:
    # Mostrar trip sin flight tracking
    flight_data = None
```

### 3. **Cache Agresivo en Frontend**

Usa el campo `cache_ttl_seconds` del snapshot:
```typescript
const cacheKey = `flight:${flightNumber}:${date}`;
const cached = localStorage.getItem(cacheKey);
if (cached) {
  const parsed = JSON.parse(cached);
  if (Date.now() - parsed.cached_at < parsed.cache_ttl_seconds * 1000) {
    return parsed;  // Use cache
  }
}
```

### 4. **Monitorea las Métricas**

Revisa diariamente `/v1/flights/metrics` para:
- Detectar exceso de API calls
- Optimizar cache hits
- Identificar vuelos problemáticos

### 5. **Maneja Estados de Error Gracefully**

```typescript
if (flight.status === 'ERROR') {
  // No mostrar error rojo, solo "Tracking unavailable"
  return <Badge variant="secondary">No tracking data</Badge>;
}
```

---

## 📝 Documentación Adicional

- **[FLIGHT_TRACKING_API.md](FLIGHT_TRACKING_API.md)** - API de flight tracking (frontend guide)
- **[BACKEND_DUPLICATE_TRIPS_HANDLING.md](BACKEND_DUPLICATE_TRIPS_HANDLING.md)** - Manejo de duplicados
- **[UNIFIED_TRIPS_WEBSOCKET_PIPELINE.md](UNIFIED_TRIPS_WEBSOCKET_PIPELINE.md)** - Sistema de WebSockets

---

## 🐛 Debugging y Troubleshooting

### Ver Logs del Backend

```bash
# Logs en tiempo real
docker logs -f gt360

# Filtrar por flight tracking
docker logs gt360 | grep -i "flight"

# Ver errores recientes
docker logs gt360 --tail 100 | grep -i "error"
```

### Verificar Redis

```bash
# Entrar al contenedor de Redis
docker exec -it redis-service redis-cli

# Ver keys de flights
KEYS flights:*

# Ver cache de un vuelo específico
GET flights:cache:WN1234:2025-06-01

# Ver métricas
KEYS flights:metrics:*
```

### Verificar PostgreSQL

```bash
# Entrar al contenedor de PostgreSQL
docker exec -it postgres psql -U gt360 -d gt360

# Ver trips recientes
SELECT * FROM trips.trips ORDER BY created_at DESC LIMIT 10;

# Contar trips por aerolínea
SELECT airline, COUNT(*) FROM trips.trips GROUP BY airline;

# Ver locations
SELECT id, name, timezone FROM entities.locations;
```

---

## 🚀 Próximos Pasos

1. **Revisar el código existente:**
   - [`features/flights/routes/flights_router.py`](../features/flights/routes/flights_router.py)
   - [`features/flights/services/flight_cache.py`](../features/flights/services/flight_cache.py)

2. **Probar la API:**
   ```bash
   # Test flight snapshot
   curl https://api.gt360.app/v1/flights/WN1234/2026-01-16

   # Test batch
   curl -X POST https://api.gt360.app/v1/flights/batch \
     -H "Content-Type: application/json" \
     -d '{"flights":[{"flight_number":"WN1234","date_local":"2026-01-16"}]}'
   ```

3. **Implementar la integración:**
   - Decidir entre Opción A, B, o C
   - Implementar manejo de errores
   - Agregar tests

4. **Monitorear:**
   - Revisar `/v1/flights/metrics` diariamente
   - Configurar alertas para rate limiting
   - Optimizar cache basado en uso real

---

**Última actualización:** 2026-01-16
**Versión:** 1.0
**Contacto:** Backend Team

**Documentación creada por:** Claude Sonnet 4.5
