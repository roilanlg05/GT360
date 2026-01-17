# Flight Tracking API - Documentación Frontend

## Índice

1. [Introducción](#introducción)
2. [Autenticación](#autenticación)
3. [Endpoints REST](#endpoints-rest)
4. [WebSocket](#websocket)
5. [Modelos de Datos](#modelos-de-datos)
6. [Ejemplos de Código](#ejemplos-de-código)
7. [Mejores Prácticas](#mejores-prácticas)

---

## Introducción

La API de Flight Tracking permite rastrear vuelos en tiempo real utilizando datos de AeroDataBox. Incluye:

- **Cache inteligente**: TTL dinámico basado en el estado del vuelo
- **WebSocket adaptativo**: Intervalo de polling que se ajusta automáticamente
- **Rate limiting**: Protección contra exceso de requests
- **Batch fetching**: Obtener múltiples vuelos en una sola request

### Base URL

```
Production: https://api.gt360.app
Development: http://localhost:8000
```

---

## Autenticación

### Endpoints REST

Los endpoints REST de flights son **públicos** y no requieren autenticación:

```
GET /v1/flights/{flight_number}/{date_local}
GET /v1/flights/{flight_number}/{date_local}/eta
GET /v1/flights/{flight_number}/{date_local}/legs
POST /v1/flights/batch
GET /v1/flights/metrics
GET /v1/flights/rate-limit
```

### WebSocket

El WebSocket **requiere JWT** como query parameter:

```
ws://host/v1/ws/flights/{flight_number}/{date_local}?token=JWT_TOKEN
```

#### Renovación de Token

Para mantener la conexión activa, envía un ping con el nuevo token antes de que expire:

```json
// Cliente envía
{"action": "ping", "token": "nuevo_jwt_token"}

// Servidor responde (éxito)
{"type": "pong"}

// Servidor responde (error)
{"type": "error", "code": 401, "detail": "Invalid or expired token"}
```

---

## Endpoints REST

### 1. Obtener Snapshot Completo

```http
GET /v1/flights/{flight_number}/{date_local}
```

**Parámetros:**

| Parámetro | Tipo | Descripción | Ejemplo |
|-----------|------|-------------|---------|
| flight_number | string | Número de vuelo | WN1234, AA567 |
| date_local | string | Fecha local de salida (YYYY-MM-DD) | 2026-01-16 |

**Response:**

```json
{
  "flight_number": "WN1234",
  "date_local": "2026-01-16",
  "status": "EnRoute",
  "eta_utc": "2026-01-16T18:30:00+00:00",
  "minutes_to_arrival": 45,
  "duration_seconds": 7200,
  "position": {
    "lat": 38.1234,
    "lon": -85.5678,
    "reported_at_utc": "2026-01-16T17:45:00+00:00",
    "ground_speed": 450,
    "altitude": 35000,
    "true_track": 270
  },
  "legs": [
    {
      "seq": 1,
      "origin": "DEN",
      "destination": "SDF",
      "dep_scheduled_utc": "2026-01-16T15:00:00+00:00",
      "dep_actual_utc": "2026-01-16T15:05:00+00:00",
      "arr_scheduled_utc": "2026-01-16T18:30:00+00:00",
      "arr_estimated_utc": "2026-01-16T18:25:00+00:00",
      "eta_utc": "2026-01-16T18:25:00+00:00",
      "duration_seconds": 7200,
      "status": "EnRoute"
    }
  ],
  "provider_last_updated_utc": "2026-01-16T17:45:00+00:00",
  "cached_at_utc": "2026-01-16T17:45:30+00:00",
  "cache_ttl_seconds": 2,
  "ws_interval_seconds": 1.0
}
```

---

### 2. Obtener Solo ETA (Lightweight)

```http
GET /v1/flights/{flight_number}/{date_local}/eta
```

Respuesta más ligera, ideal para dashboards con muchos vuelos.

**Response:**

```json
{
  "flight_number": "WN1234",
  "date_local": "2026-01-16",
  "status": "EnRoute",
  "eta_utc": "2026-01-16T18:30:00+00:00",
  "minutes_to_arrival": 45,
  "provider_last_updated_utc": "2026-01-16T17:45:00+00:00",
  "cached_at_utc": "2026-01-16T17:45:30+00:00",
  "cache_ttl_seconds": 2
}
```

---

### 3. Obtener Legs del Vuelo

```http
GET /v1/flights/{flight_number}/{date_local}/legs
```

**Response:**

```json
[
  {
    "seq": 1,
    "origin": "DEN",
    "destination": "SDF",
    "dep_scheduled_utc": "2026-01-16T15:00:00+00:00",
    "dep_estimated_utc": null,
    "dep_actual_utc": "2026-01-16T15:05:00+00:00",
    "arr_scheduled_utc": "2026-01-16T18:30:00+00:00",
    "arr_estimated_utc": "2026-01-16T18:25:00+00:00",
    "arr_actual_utc": null,
    "eta_utc": "2026-01-16T18:25:00+00:00",
    "duration_seconds": 7200,
    "status": "EnRoute",
    "provider_last_updated_utc": "2026-01-16T17:45:00+00:00"
  }
]
```

---

### 4. Batch - Múltiples Vuelos

```http
POST /v1/flights/batch?max_concurrent=10
```

**Request Body:**

```json
{
  "flights": [
    {"flight_number": "WN1234", "date_local": "2026-01-16"},
    {"flight_number": "AA567", "date_local": "2026-01-16"},
    {"flight_number": "DL890", "date_local": "2026-01-16"}
  ]
}
```

**Query Parameters:**

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| max_concurrent | int | 10 | Máximo requests concurrentes (1-20) |

**Response:**

```json
{
  "flights": [
    { /* FlightSnapshot WN1234 */ },
    { /* FlightSnapshot AA567 */ },
    { /* FlightSnapshot DL890 */ }
  ],
  "total": 3,
  "cached": 2,
  "from_api": 1
}
```

**Límites:**
- Máximo 50 vuelos por request

---

### 5. Métricas de Uso

```http
GET /v1/flights/metrics?date=2026-01-16
```

**Query Parameters:**

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| date | string | hoy | Fecha en formato YYYY-MM-DD |

**Response:**

```json
{
  "date": "2026-01-16",
  "cache_hits": 1523,
  "cache_misses": 45,
  "api_calls": 45,
  "api_errors": 2,
  "rate_limited": 0,
  "flights_not_found": 3
}
```

---

### 6. Estado del Rate Limit

```http
GET /v1/flights/rate-limit
```

**Response:**

```json
{
  "current": 45,
  "limit": 100,
  "remaining": 55
}
```

---

## WebSocket

### Conexión

```javascript
const token = "eyJhbGciOiJIUzI1NiIs...";
const flightNumber = "WN1234";
const dateLocal = "2026-01-16";

const ws = new WebSocket(
  `wss://api.gt360.app/v1/ws/flights/${flightNumber}/${dateLocal}?token=${token}`
);
```

### Mensajes del Servidor

El servidor envía automáticamente snapshots del vuelo. El intervalo se adapta según el estado:

| Estado | Intervalo |
|--------|-----------|
| Landed/Arrived | 10s |
| En route (≤15 min to arrival) | 1s |
| En route (15-30 min) | 2s |
| En route (30-60 min) | 3s |
| En route (>60 min) | 5s |
| Scheduled/Boarding | 5s |
| Not found | 5s |

**Formato del mensaje:**

```json
{
  "flight_number": "WN1234",
  "date_local": "2026-01-16",
  "status": "EnRoute",
  "eta_utc": "2026-01-16T18:30:00+00:00",
  "minutes_to_arrival": 45,
  "position": { ... },
  "legs": [ ... ],
  "ws_interval_seconds": 2.0,
  ...
}
```

### Ping/Pong (Renovación de Token)

```javascript
// Enviar ping con nuevo token antes de que expire
ws.send(JSON.stringify({
  action: "ping",
  token: "nuevo_jwt_token"
}));

// Escuchar respuesta
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.type === "pong") {
    console.log("Token renovado exitosamente");
  } else if (data.type === "error" && data.code === 401) {
    console.error("Token inválido, reconectando...");
    // Reconectar con nuevo token
  } else {
    // Es un FlightSnapshot
    updateFlightUI(data);
  }
};
```

### Códigos de Cierre

| Código | Significado |
|--------|-------------|
| 1008 | Token inválido o expirado |
| 1011 | Error interno del servidor |

---

## Modelos de Datos

### FlightSnapshot

```typescript
interface FlightSnapshot {
  flight_number: string;
  date_local: string;
  status: FlightStatus | null;
  eta_utc: string | null;
  minutes_to_arrival: number | null;
  duration_seconds: number | null;
  position: Position | null;
  legs: Leg[];
  provider_last_updated_utc: string | null;
  cached_at_utc: string;
  cache_ttl_seconds: number;
  ws_interval_seconds: number;
}
```

### Position

```typescript
interface Position {
  lat: number;
  lon: number;
  reported_at_utc: string | null;
  ground_speed?: number;  // knots
  altitude?: number;      // feet
  true_track?: number;    // degrees
}
```

### Leg

```typescript
interface Leg {
  seq: number;
  origin: string | null;
  destination: string | null;
  dep_scheduled_utc: string | null;
  dep_estimated_utc: string | null;
  dep_actual_utc: string | null;
  arr_scheduled_utc: string | null;
  arr_estimated_utc: string | null;
  arr_actual_utc: string | null;
  eta_utc: string | null;
  duration_seconds: number | null;
  status: string | null;
  provider_last_updated_utc: string | null;
}
```

### FlightStatus

```typescript
type FlightStatus =
  // Terminal (vuelo completado)
  | "Landed"
  | "Arrived"
  | "Canceled"
  | "Diverted"
  // En vuelo
  | "EnRoute"
  | "InFlight"
  | "Airborne"
  | "Departed"
  // Pre-vuelo
  | "Scheduled"
  | "Boarding"
  | "GateClosed"
  | "Delayed"
  // Especiales
  | "NOT_FOUND"
  | "RATE_LIMITED"
  | "ERROR"
  | "Unknown";
```

---

## Ejemplos de Código

### React Hook para Flight Tracking

```typescript
import { useState, useEffect, useCallback, useRef } from 'react';

interface UseFlightTrackerOptions {
  flightNumber: string;
  dateLocal: string;
  token: string;
  onTokenExpiring?: () => Promise<string>;
}

export function useFlightTracker({
  flightNumber,
  dateLocal,
  token,
  onTokenExpiring
}: UseFlightTrackerOptions) {
  const [flight, setFlight] = useState<FlightSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const tokenRef = useRef(token);

  // Actualizar token ref cuando cambie
  useEffect(() => {
    tokenRef.current = token;
  }, [token]);

  const connect = useCallback(() => {
    const ws = new WebSocket(
      `wss://api.gt360.app/v1/ws/flights/${flightNumber}/${dateLocal}?token=${tokenRef.current}`
    );

    ws.onopen = () => {
      setIsConnected(true);
      setError(null);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === "pong") {
        console.log("Token renovado");
        return;
      }

      if (data.type === "error") {
        setError(data.detail);
        if (data.code === 401) {
          ws.close();
        }
        return;
      }

      // FlightSnapshot
      setFlight(data);
    };

    ws.onerror = () => {
      setError("Error de conexión");
    };

    ws.onclose = (event) => {
      setIsConnected(false);

      // Reconectar si no fue cierre intencional
      if (event.code !== 1000 && event.code !== 1008) {
        setTimeout(connect, 3000);
      }
    };

    wsRef.current = ws;

    return () => {
      ws.close();
    };
  }, [flightNumber, dateLocal]);

  // Renovar token periódicamente
  useEffect(() => {
    if (!onTokenExpiring) return;

    const interval = setInterval(async () => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        try {
          const newToken = await onTokenExpiring();
          tokenRef.current = newToken;
          wsRef.current.send(JSON.stringify({
            action: "ping",
            token: newToken
          }));
        } catch (e) {
          console.error("Error renovando token:", e);
        }
      }
    }, 50000); // Renovar cada 50s (antes de los 60s de expiración)

    return () => clearInterval(interval);
  }, [onTokenExpiring]);

  useEffect(() => {
    const cleanup = connect();
    return cleanup;
  }, [connect]);

  return { flight, error, isConnected };
}
```

### Uso del Hook

```tsx
function FlightTracker({ flightNumber, date }: Props) {
  const { token, refreshToken } = useAuth();

  const { flight, error, isConnected } = useFlightTracker({
    flightNumber,
    dateLocal: date,
    token,
    onTokenExpiring: refreshToken
  });

  if (error) {
    return <div className="error">{error}</div>;
  }

  if (!flight) {
    return <div>Cargando...</div>;
  }

  return (
    <div className="flight-card">
      <div className="flight-header">
        <span className="flight-number">{flight.flight_number}</span>
        <span className={`status status-${flight.status?.toLowerCase()}`}>
          {flight.status}
        </span>
      </div>

      {flight.minutes_to_arrival !== null && (
        <div className="eta">
          ETA: {flight.minutes_to_arrival} minutos
        </div>
      )}

      {flight.position && (
        <FlightMap
          lat={flight.position.lat}
          lon={flight.position.lon}
          heading={flight.position.true_track}
        />
      )}

      <div className="meta">
        <small>
          Actualizado: {new Date(flight.cached_at_utc).toLocaleTimeString()}
        </small>
        <small className={isConnected ? "connected" : "disconnected"}>
          {isConnected ? "🟢 Conectado" : "🔴 Desconectado"}
        </small>
      </div>
    </div>
  );
}
```

### Batch Fetch con React Query

```typescript
import { useQuery } from '@tanstack/react-query';

interface FlightToTrack {
  flight_number: string;
  date_local: string;
}

async function fetchFlightsBatch(flights: FlightToTrack[]) {
  const response = await fetch('https://api.gt360.app/v1/flights/batch', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ flights }),
  });

  if (!response.ok) {
    throw new Error('Error fetching flights');
  }

  return response.json();
}

export function useFlightsBatch(flights: FlightToTrack[]) {
  return useQuery({
    queryKey: ['flights-batch', flights],
    queryFn: () => fetchFlightsBatch(flights),
    refetchInterval: 5000, // Refetch cada 5s
    enabled: flights.length > 0,
  });
}
```

---

## Mejores Prácticas

### 1. Usar WebSocket para tracking individual

Para un solo vuelo que necesitas seguir en tiempo real, usa WebSocket:

```javascript
// ✅ Correcto
const ws = new WebSocket(`wss://api/v1/ws/flights/WN1234/2026-01-16?token=...`);

// ❌ Evitar polling manual
setInterval(() => fetch('/v1/flights/WN1234/2026-01-16'), 1000);
```

### 2. Usar Batch para dashboards

Para mostrar múltiples vuelos, usa el endpoint batch:

```javascript
// ✅ Correcto - 1 request para 10 vuelos
const response = await fetch('/v1/flights/batch', {
  method: 'POST',
  body: JSON.stringify({ flights: [...] })
});

// ❌ Evitar - 10 requests paralelas
await Promise.all(flights.map(f => fetch(`/v1/flights/${f.number}/${f.date}`)));
```

### 3. Respetar el `ws_interval_seconds`

El servidor te indica el intervalo óptimo de polling. Úsalo:

```javascript
// El servidor ya ajusta el intervalo, pero si haces polling manual:
const interval = flight.ws_interval_seconds * 1000;
```

### 4. Manejar estados terminales

No sigas trackeando vuelos que ya aterrizaron:

```javascript
const terminalStates = ['Landed', 'Arrived', 'Canceled', 'Diverted'];

if (terminalStates.includes(flight.status)) {
  ws.close();
  // Mostrar estado final
}
```

### 5. Monitorear rate limits

Revisa el rate limit antes de hacer muchas requests:

```javascript
const status = await fetch('/v1/flights/rate-limit').then(r => r.json());

if (status.remaining < 10) {
  console.warn('Rate limit bajo, reduciendo frecuencia');
}
```

### 6. Cache local para vuelos frecuentes

```javascript
const flightCache = new Map();

async function getFlightWithCache(flightNumber: string, date: string) {
  const key = `${flightNumber}:${date}`;
  const cached = flightCache.get(key);

  if (cached && Date.now() - cached.timestamp < cached.ttl * 1000) {
    return cached.data;
  }

  const data = await fetch(`/v1/flights/${flightNumber}/${date}`).then(r => r.json());

  flightCache.set(key, {
    data,
    timestamp: Date.now(),
    ttl: data.cache_ttl_seconds
  });

  return data;
}
```

---

## Códigos de Error

| Status | Descripción | Acción Recomendada |
|--------|-------------|-------------------|
| 400 | Parámetros inválidos | Verificar formato de flight_number y date_local |
| 404 | Vuelo no encontrado | El vuelo no existe o la fecha es incorrecta |
| 429 | Rate limited | Esperar y reintentar, reducir frecuencia |
| 500 | Error interno | Reintentar con backoff exponencial |

---

## Soporte

Para reportar problemas o solicitar features:
- GitHub Issues: https://github.com/gt360/api/issues
- Email: soporte@gt360.app
