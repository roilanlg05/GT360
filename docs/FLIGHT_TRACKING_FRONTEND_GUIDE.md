# Flight Tracking System - Frontend Integration Guide

## Overview

El sistema de tracking de vuelos en tiempo real tiene dos componentes principales:

1. **Push Notifications** - Notificaciones de cambios de estado del vuelo (AeroDataBox)
2. **Real-Time Tracking** - Posición del avión en tiempo real (ADSB.lol)

### Arquitectura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ARQUITECTURA DEL SISTEMA                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐        │
│  │   Frontend   │◄───────►│   Backend    │◄───────►│    Redis     │        │
│  │   (React)    │   WS    │   (FastAPI)  │  Cache  │   Pub/Sub    │        │
│  └──────────────┘         └──────────────┘         └──────────────┘        │
│                                  │                                          │
│                    ┌─────────────┼─────────────┐                           │
│                    ▼             ▼             ▼                           │
│           ┌──────────────┐ ┌──────────┐ ┌──────────────┐                   │
│           │ AeroDataBox  │ │ ADSB.lol │ │   Webhook    │                   │
│           │ (Push API)   │ │ (Pos API)│ │   Handler    │                   │
│           └──────────────┘ └──────────┘ └──────────────┘                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Flujo General

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FLUJO DE TRACKING                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. Frontend envía lista de vuelos a trackear (para AeroDataBox)            │
│     POST /v1/flights/tracking/subscribe                                      │
│                                                                              │
│  2. Frontend conecta a WebSocket de push notifications                       │
│     WS /ws/flights/push?location_id=xxx&flight_numbers=WN1036,AA123&token=JWT│
│                                                                              │
│     ⚠️ El location_id determina el aeropuerto de destino (IATA)             │
│     Solo se reciben notificaciones de vuelos que llegan a ese aeropuerto    │
│                                                                              │
│  3. Cuando el vuelo despega (status: "Departed"):                           │
│     - Frontend recibe: {"message": "Flight WN1036 has departed at 11:52"}   │
│     - Frontend conecta al WS de tracking para posición en tiempo real       │
│     WS /ws/flights/tracking?token=JWT                                        │
│                                                                              │
│  4. Frontend recibe posiciones en tiempo real con intervalos adaptativos:   │
│     - >60 min ETA: cada 20 min                                              │
│     - 30-60 min: cada 5 min                                                 │
│     - 20-30 min: cada 2.5 min                                               │
│     - 10-20 min: cada 1 min                                                 │
│     - <10 min: cada 1 segundo                                               │
│                                                                              │
│  5. Cuando el vuelo aterriza (status: "Arrived"):                           │
│     - Frontend recibe: {"message": "Flight WN1036 has arrived at 13:28"}    │
│     - Frontend puede desconectar el WS de tracking                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## REST API Endpoints

Base URL: `https://api.gt360.app/v1/flights/tracking`

### 1. Suscribir Vuelos para Notificaciones Push

Registra vuelos para recibir notificaciones de cambios de estado.

```http
POST /v1/flights/tracking/subscribe
Authorization: Bearer {jwt_token}
Content-Type: application/json
```

**Request Body:**
```json
{
  "flights": [
    {
      "flight_number": "WN1234",
      "trip_id": "uuid-del-trip",
      "date_local": "2026-01-20"
    },
    {
      "flight_number": "AA567",
      "trip_id": "uuid-del-trip-2",
      "date_local": "2026-01-20"
    }
  ]
}
```

**Límites:**
- Máximo 50 vuelos por request
- La lista no puede estar vacía

**Response (200 OK):**
```json
{
  "subscribed": [
    {
      "flight_number": "WN1234",
      "trip_id": "uuid-del-trip",
      "date_local": "2026-01-20",
      "subscription_id": "adb-sub-123",
      "status": "active",
      "created_at": "2026-01-18T10:30:00Z",
      "expires_at": "2026-01-19T10:30:00Z"
    }
  ],
  "failed": [
    {
      "flight_number": "AA567",
      "trip_id": "uuid-del-trip-2",
      "error": "error: 404 - Flight not found"
    }
  ],
  "total": 2,
  "success_count": 1,
  "failure_count": 1
}
```

**TypeScript Interfaces:**
```typescript
interface FlightToSubscribe {
  flight_number: string;
  trip_id: string;
  date_local: string; // YYYY-MM-DD
}

interface SubscribeRequest {
  flights: FlightToSubscribe[];
}

interface FlightSubscription {
  flight_number: string;
  trip_id: string;
  date_local: string;
  subscription_id: string | null;
  status: "pending" | "active" | "expired" | "error";
  created_at: string;
  expires_at: string | null;
}

interface SubscribeResponse {
  subscribed: FlightSubscription[];
  failed: { flight_number: string; trip_id: string; error: string }[];
  total: number;
  success_count: number;
  failure_count: number;
}
```

---

### 2. Cancelar Suscripción

```http
DELETE /v1/flights/tracking/subscribe/{flight_number}?trip_id={trip_id}
Authorization: Bearer {jwt_token}
```

**Ejemplo:**
```http
DELETE /v1/flights/tracking/subscribe/WN1234?trip_id=uuid-del-trip
```

**Response (200 OK):**
```json
{
  "status": "ok",
  "flight_number": "WN1234",
  "trip_id": "uuid-del-trip"
}
```

---

### 3. Obtener Estado de Suscripción

```http
GET /v1/flights/tracking/subscription/{flight_number}?trip_id={trip_id}
Authorization: Bearer {jwt_token}
```

**Response (200 OK):**
```json
{
  "flight_number": "WN1234",
  "trip_id": "uuid-del-trip",
  "date_local": "2026-01-20",
  "subscription_id": "adb-sub-123",
  "status": "active",
  "created_at": "2026-01-18T10:30:00Z",
  "expires_at": "2026-01-19T10:30:00Z"
}
```

**Response (null si no existe):**
```json
null
```

---

### 4. Obtener Estado de Tracking

Retorna el estado actual del tracking para un vuelo.

```http
GET /v1/flights/tracking/state/{flight_number}?trip_id={trip_id}
Authorization: Bearer {jwt_token}
```

**Response (200 OK):**
```json
{
  "flight_number": "WN1234",
  "trip_id": "uuid-del-trip",
  "date_local": "2026-01-20",
  "status": "EnRoute",
  "is_tracking_active": true,
  "last_position": {
    "flight_number": "WN1234",
    "trip_id": "uuid-del-trip",
    "lat": 38.5421,
    "lon": -89.1234,
    "altitude": 35000,
    "ground_speed": 450,
    "heading": 270,
    "vertical_rate": -500,
    "origin_icao": "KORD",
    "origin_iata": "ORD",
    "destination_icao": "KSDF",
    "destination_iata": "SDF",
    "distance_to_destination_nm": 185.4,
    "eta_utc": "2026-01-18T14:30:00Z",
    "minutes_to_arrival": 25,
    "tracking_interval": "close",
    "interval_seconds": 150,
    "position_time": "2026-01-18T14:05:00Z",
    "cached_at": "2026-01-18T14:05:01Z",
    "cache_ttl_seconds": 2
  },
  "current_interval": "close",
  "interval_seconds": 150,
  "subscription_id": "adb-sub-123",
  "subscription_status": "active"
}
```

**TypeScript Interfaces:**
```typescript
type FlightStatus =
  | "Scheduled"
  | "Boarding"
  | "Departed"
  | "EnRoute"
  | "Landed"
  | "Arrived"
  | "Canceled"
  | "Diverted"
  | "Unknown";

type TrackingInterval =
  | "real_time"   // <10 min: cada 1 segundo
  | "very_close"  // 10-20 min: cada 1 minuto
  | "close"       // 20-30 min: cada 2.5 minutos
  | "medium"      // 30-60 min: cada 5 minutos
  | "far";        // >60 min: cada 20 minutos

interface FlightTrackingState {
  flight_number: string;
  trip_id: string;
  date_local: string;
  status: FlightStatus;
  is_tracking_active: boolean;
  last_position: FlightPosition | null;
  current_interval: TrackingInterval;
  interval_seconds: number;
  subscription_id: string | null;
  subscription_status: string;
}
```

---

### 5. Obtener Posición Actual

Obtiene la posición actual del avión. Usa cache de 2 segundos con patrón singleflight.

```http
GET /v1/flights/tracking/position/{flight_number}?trip_id={trip_id}&destination_icao={icao}
Authorization: Bearer {jwt_token}
```

**Query Parameters:**
| Param | Required | Description |
|-------|----------|-------------|
| trip_id | Yes | ID del trip |
| origin_icao | No | Código ICAO del aeropuerto de origen |
| destination_icao | No | Código ICAO del destino (para calcular ETA) |

**Ejemplo:**
```http
GET /v1/flights/tracking/position/WN1234?trip_id=uuid&destination_icao=KSDF
```

**Response (200 OK):**
```json
{
  "flight_number": "WN1234",
  "trip_id": "uuid-del-trip",
  "lat": 38.5421,
  "lon": -89.1234,
  "altitude": 35000,
  "ground_speed": 450.5,
  "heading": 270.3,
  "vertical_rate": -500,
  "origin_icao": "KORD",
  "origin_iata": "ORD",
  "destination_icao": "KSDF",
  "destination_iata": "SDF",
  "distance_to_destination_nm": 185.4,
  "eta_utc": "2026-01-18T14:30:00Z",
  "minutes_to_arrival": 25,
  "tracking_interval": "close",
  "interval_seconds": 150,
  "position_time": "2026-01-18T14:05:00Z",
  "cached_at": "2026-01-18T14:05:01Z",
  "cache_ttl_seconds": 2
}
```

**TypeScript Interface:**
```typescript
interface FlightPosition {
  flight_number: string;
  trip_id: string;

  // Position
  lat: number;
  lon: number;
  altitude: number | null;       // feet
  ground_speed: number | null;   // knots
  heading: number | null;        // degrees
  vertical_rate: number | null;  // feet/min (negative = descending)

  // Airports
  origin_icao: string | null;
  origin_iata: string | null;
  destination_icao: string | null;
  destination_iata: string | null;

  // ETA
  distance_to_destination_nm: number | null;  // nautical miles
  eta_utc: string | null;                     // ISO timestamp
  minutes_to_arrival: number | null;

  // Tracking info
  tracking_interval: TrackingInterval;
  interval_seconds: number;

  // Timestamps
  position_time: string;
  cached_at: string;
  cache_ttl_seconds: number;
}
```

---

### 6. Listar Vuelos Activos

```http
GET /v1/flights/tracking/active
Authorization: Bearer {jwt_token}
```

**Response (200 OK):**
```json
{
  "active_flights": [
    "WN1234:uuid-trip-1",
    "AA567:uuid-trip-2"
  ],
  "count": 2
}
```

---

### 7. Activar/Desactivar Tracking Manualmente

Normalmente el tracking se activa automáticamente cuando el vuelo despega.
Estos endpoints son para control manual.

**Activar:**
```http
POST /v1/flights/tracking/activate/{flight_number}?trip_id={trip_id}
Authorization: Bearer {jwt_token}
```

**Desactivar:**
```http
POST /v1/flights/tracking/deactivate/{flight_number}?trip_id={trip_id}
Authorization: Bearer {jwt_token}
```

**Response (200 OK):**
```json
{
  "status": "ok",
  "flight_number": "WN1234",
  "trip_id": "uuid-del-trip",
  "tracking_active": true
}
```

---

## WebSocket: Push Notifications

Recibe notificaciones de cambios de estado del vuelo en tiempo real.

### Arquitectura de Suscripción

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FLUJO DE PUSH NOTIFICATIONS                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. Frontend se conecta con location_id + lista de flight_numbers           │
│                                                                              │
│  2. Backend obtiene el IATA de la location desde la DB                      │
│     Ejemplo: location_id="abc123" -> location.name="SDF"                    │
│                                                                              │
│  3. Backend suscribe al cliente a rooms:                                     │
│     - push:SDF:WN1036                                                        │
│     - push:SDF:AA123                                                         │
│                                                                              │
│  4. Webhook recibe notificación de AeroDataBox:                             │
│     - Extrae arrival_iata del payload (ej: "SDF")                           │
│     - Extrae flight_number (ej: "WN1036")                                   │
│     - Publica a canal: flight:push:SDF:WN1036                               │
│                                                                              │
│  5. Solo los clientes suscritos a SDF + WN1036 reciben la notificación      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Conexión

```
wss://api.gt360.app/ws/flights/push?location_id={location_id}&flight_numbers={flight_numbers}&token={jwt_token}
```

**Parámetros de Query:**
| Param | Required | Description | Example |
|-------|----------|-------------|---------|
| location_id | Yes | UUID de la location a monitorear | `abc123-def456-...` |
| flight_numbers | Yes | Lista de vuelos separados por coma | `WN1036,AA123,DL456` |
| token | Yes | JWT token de autenticación | `eyJhbG...` |

**Ejemplo de URL completa:**
```
wss://api.gt360.app/ws/flights/push?location_id=15da8f3a-aa38-44b7-9454-88dea364b4cf&flight_numbers=WN1036,AA123&token=eyJhbGciOiJIUzI1NiIs...
```

### Flujo de Autenticación

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FLUJO DE AUTENTICACIÓN                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. CONEXIÓN INICIAL                                                         │
│     - Cliente envía token JWT en query parameter                             │
│     - Backend valida token y extrae claims                                   │
│     - Si token inválido: cierra conexión con código 1008                    │
│                                                                              │
│  2. VALIDACIÓN DE LOCATION                                                   │
│     - Backend consulta DB para obtener location.name (IATA)                 │
│     - Si location no existe: envía error y cierra conexión                  │
│                                                                              │
│  3. KEEP-ALIVE (cada 30 segundos)                                           │
│     - Cliente envía ping con token actualizado                              │
│     - Backend valida token en cada ping                                      │
│     - Si token expirado: envía error 401 y cierra conexión                  │
│                                                                              │
│  ⚠️ IMPORTANTE: El token es REQUERIDO en cada ping                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Mensajes del Servidor

**1. Conexión exitosa:**
```json
{
  "type": "connected",
  "location_id": "15da8f3a-aa38-44b7-9454-88dea364b4cf",
  "location_iata": "SDF",
  "flight_numbers": ["WN1036", "AA123"]
}
```

**2. Flight update (cambio de estado):**
```json
{
  "type": "flight_update",
  "flight_number": "WN1036",
  "status": "Arrived",
  "message": "Flight WN1036 has arrived at 13:28",
  "departure": {
    "airport_iata": "BWI",
    "airport_name": "Baltimore Washington Thurgood Marshall",
    "scheduled_time": "2026-01-21 11:40-05:00",
    "actual_time": "2026-01-21 11:52-05:00"
  },
  "arrival": {
    "airport_iata": "SDF",
    "airport_name": "Louisville Standiford Field",
    "scheduled_time": "2026-01-21 13:35-05:00",
    "actual_time": "2026-01-21 13:28-05:00"
  },
  "airline": {
    "name": "Southwest Airlines",
    "iata": "WN"
  },
  "aircraft": {
    "reg": "N480WN",
    "modeS": "A5EA9A",
    "model": "Boeing 737-700"
  },
  "last_updated": "2026-01-21 18:29Z",
  "received_at": "2026-01-21T18:29:25.720990+00:00",
  "raw": { ... }
}
```

**Mensajes según status:**
| Status | Mensaje |
|--------|---------|
| Arrived | `Flight WN1036 has arrived at 13:28` |
| Departed | `Flight WN1036 has departed at 11:52` |
| EnRoute | `Flight WN1036 is en route` |
| Boarding | `Flight WN1036 is now boarding` |
| GateClosed | `Flight WN1036 gate is now closed` |
| Delayed | `Flight WN1036 has been delayed` |
| Canceled | `Flight WN1036 has been canceled` |
| Diverted | `Flight WN1036 has been diverted` |
| Approaching | `Flight WN1036 is approaching SDF` |
| CheckIn | `Flight WN1036 check-in is now open` |
| Expected | `Flight WN1036 is expected at 13:35` |

**3. Suscripción adicional confirmada:**
```json
{
  "type": "subscribed",
  "flight_number": "DL789"
}
```

**4. Desuscripción confirmada:**
```json
{
  "type": "unsubscribed",
  "flight_number": "AA123"
}
```

**5. Pong (respuesta a ping):**
```json
{
  "type": "pong"
}
```

**6. Error:**
```json
{
  "type": "error",
  "code": 401,
  "detail": "Invalid or expired token"
}
```

```json
{
  "type": "error",
  "code": 404,
  "detail": "Location not found"
}
```

```json
{
  "type": "error",
  "code": 400,
  "detail": "No flight numbers provided"
}
```

### Mensajes del Cliente

**1. Ping (keep-alive con validación de token):**
```json
{
  "action": "ping",
  "token": "jwt_token_actualizado"
}
```
> ⚠️ El token es **REQUERIDO** en el ping. Si no se envía, se cerrará la conexión con código 1008.

**2. Suscribirse a un vuelo adicional:**
```json
{
  "action": "subscribe",
  "flight_number": "DL789"
}
```

**3. Desuscribirse de un vuelo:**
```json
{
  "action": "unsubscribe",
  "flight_number": "AA123"
}
```

### Estados de Vuelo (AeroDataBox)

| Código | Status | Descripción |
|--------|--------|-------------|
| 0 | Unknown | Estado desconocido |
| 1 | Expected | Vuelo esperado |
| 2 | EnRoute | En ruta |
| 3 | CheckIn | Check-in abierto |
| 4 | Boarding | Embarcando |
| 5 | GateClosed | Puerta cerrada |
| 6 | Departed | Despegó |
| 7 | Delayed | Retrasado |
| 8 | Approaching | Aproximándose |
| 9 | Arrived | Aterrizó |
| 10 | Canceled | Cancelado |
| 11 | Diverted | Desviado |
| 12 | CanceledUncertain | Cancelación incierta |

### TypeScript Interfaces

```typescript
// Parámetros de conexión
interface PushWSConnectionParams {
  location_id: string;      // UUID de la location
  flight_numbers: string;   // Comma-separated: "WN1036,AA123"
  token: string;            // JWT token
}

// Mensaje de conexión exitosa
interface ConnectedMessage {
  type: "connected";
  location_id: string;
  location_iata: string;
  flight_numbers: string[];
}

// Actualización de vuelo
interface FlightUpdateMessage {
  type: "flight_update";
  flight_number: string;
  status: FlightStatus;
  message: string;          // Human-readable message
  departure: {
    airport_iata: string | null;
    airport_name: string | null;
    scheduled_time: string | null;
    actual_time: string | null;
  };
  arrival: {
    airport_iata: string | null;
    airport_name: string | null;
    scheduled_time: string | null;
    actual_time: string | null;
  };
  airline: {
    name: string | null;
    iata: string | null;
  };
  aircraft: {
    reg: string;
    modeS: string;
    model: string;
  } | null;
  last_updated: string;
  received_at: string;
  raw: Record<string, any>;
}

type FlightStatus =
  | "Unknown"
  | "Expected"
  | "EnRoute"
  | "CheckIn"
  | "Boarding"
  | "GateClosed"
  | "Departed"
  | "Delayed"
  | "Approaching"
  | "Arrived"
  | "Canceled"
  | "Diverted"
  | "CanceledUncertain";

// Mensajes del servidor
type ServerMessage =
  | ConnectedMessage
  | FlightUpdateMessage
  | { type: "subscribed"; flight_number: string }
  | { type: "unsubscribed"; flight_number: string }
  | { type: "pong" }
  | { type: "error"; code?: number; detail: string };

// Mensajes del cliente
type ClientMessage =
  | { action: "ping"; token: string }
  | { action: "subscribe"; flight_number: string }
  | { action: "unsubscribe"; flight_number: string };
```

### Ejemplo de Implementación (React)

```typescript
import { useEffect, useRef, useCallback, useState } from 'react';

interface FlightUpdate {
  type: "flight_update";
  flight_number: string;
  status: string;
  message: string;
  departure: {
    airport_iata: string | null;
    airport_name: string | null;
    scheduled_time: string | null;
    actual_time: string | null;
  };
  arrival: {
    airport_iata: string | null;
    airport_name: string | null;
    scheduled_time: string | null;
    actual_time: string | null;
  };
  airline: {
    name: string | null;
    iata: string | null;
  };
  received_at: string;
}

interface UsePushNotificationsOptions {
  locationId: string;
  flightNumbers: string[];
  token: string;
  onFlightUpdate: (update: FlightUpdate) => void;
  onError?: (error: { code?: number; detail: string }) => void;
  onConnected?: (locationIata: string, flights: string[]) => void;
}

export function usePushNotifications({
  locationId,
  flightNumbers,
  token,
  onFlightUpdate,
  onError,
  onConnected,
}: UsePushNotificationsOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const tokenRef = useRef(token);
  const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [locationIata, setLocationIata] = useState<string | null>(null);

  // Keep token reference updated
  useEffect(() => {
    tokenRef.current = token;
  }, [token]);

  const connect = useCallback(() => {
    // Clear any existing reconnect timeout
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }

    // Build connection URL
    const flightNumbersParam = flightNumbers.join(',');
    const wsUrl = `wss://api.gt360.app/ws/flights/push?location_id=${locationId}&flight_numbers=${flightNumbersParam}&token=${token}`;

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('Push WS connected');
      setIsConnected(true);

      // Ping every 30 seconds with updated token
      pingIntervalRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({
            action: 'ping',
            token: tokenRef.current,  // Use current token
          }));
        }
      }, 30000);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'connected':
          console.log(`Connected to location: ${data.location_iata}`);
          console.log(`Monitoring flights: ${data.flight_numbers.join(', ')}`);
          setLocationIata(data.location_iata);
          onConnected?.(data.location_iata, data.flight_numbers);
          break;

        case 'flight_update':
          console.log(`Flight update: ${data.message}`);
          onFlightUpdate(data);
          break;

        case 'subscribed':
          console.log(`Subscribed to flight: ${data.flight_number}`);
          break;

        case 'unsubscribed':
          console.log(`Unsubscribed from flight: ${data.flight_number}`);
          break;

        case 'pong':
          // Keep-alive acknowledged
          break;

        case 'error':
          console.error('Push WS error:', data.detail);
          onError?.({ code: data.code, detail: data.detail });
          if (data.code === 401) {
            ws.close();
          }
          break;
      }
    };

    ws.onclose = (event) => {
      console.log('Push WS disconnected', event.code);
      setIsConnected(false);
      setLocationIata(null);

      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
      }

      // Reconnect after 3 seconds (except if intentionally closed)
      if (event.code !== 1000) {
        reconnectTimeoutRef.current = setTimeout(connect, 3000);
      }
    };

    ws.onerror = (error) => {
      console.error('Push WS error:', error);
    };

    wsRef.current = ws;
  }, [locationId, flightNumbers, token, onFlightUpdate, onError, onConnected]);

  // Subscribe to additional flight
  const subscribeToFlight = useCallback((flightNumber: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        action: 'subscribe',
        flight_number: flightNumber.toUpperCase(),
      }));
    }
  }, []);

  // Unsubscribe from flight
  const unsubscribeFromFlight = useCallback((flightNumber: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        action: 'unsubscribe',
        flight_number: flightNumber.toUpperCase(),
      }));
    }
  }, []);

  useEffect(() => {
    if (locationId && flightNumbers.length > 0 && token) {
      connect();
    }

    return () => {
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      wsRef.current?.close(1000);
    };
  }, [connect, locationId, flightNumbers, token]);

  return {
    isConnected,
    locationIata,
    subscribeToFlight,
    unsubscribeFromFlight,
  };
}
```

### Ejemplo de Uso del Hook

```typescript
function FlightMonitor({ locationId, trips }: Props) {
  const { token } = useAuth();

  // Extract flight numbers from trips
  const flightNumbers = useMemo(() =>
    trips
      .filter(t => t.flight_number)
      .map(t => t.flight_number!.replace(/\s/g, '')),  // Remove spaces
    [trips]
  );

  const handleFlightUpdate = useCallback((update: FlightUpdate) => {
    // Show notification
    toast.info(update.message);

    // Update trip status in state
    setTrips(prev => prev.map(trip => {
      if (trip.flight_number?.replace(/\s/g, '') === update.flight_number) {
        return {
          ...trip,
          flight_status: update.status,
          flight_arrival_time: update.arrival.actual_time,
        };
      }
      return trip;
    }));

    // If flight arrived, maybe trigger some action
    if (update.status === 'Arrived') {
      console.log(`🛬 ${update.flight_number} arrived at ${update.arrival.airport_iata}`);
    }
  }, []);

  const { isConnected, locationIata } = usePushNotifications({
    locationId,
    flightNumbers,
    token,
    onFlightUpdate: handleFlightUpdate,
    onConnected: (iata, flights) => {
      console.log(`Monitoring ${flights.length} flights arriving at ${iata}`);
    },
    onError: (error) => {
      if (error.code === 401) {
        // Token expired, refresh it
        refreshToken();
      }
    },
  });

  return (
    <div>
      <ConnectionStatus connected={isConnected} location={locationIata} />
      <TripsList trips={trips} />
    </div>
  );
}
```

---

## WebSocket: Real-Time Tracking

Recibe posiciones del avión en tiempo real con intervalos adaptativos.

### Conexión

```
wss://api.gt360.app/ws/flights/tracking?token={jwt_token}
```

**Parámetros de Query:**
| Param | Required | Description |
|-------|----------|-------------|
| token | Yes | JWT token de autenticación |

### Mensajes del Servidor

**1. Conexión exitosa:**
```json
{
  "type": "connected"
}
```

**2. Tracking iniciado:**
```json
{
  "type": "tracking_started",
  "flight_number": "WN1234",
  "trip_id": "uuid-del-trip"
}
```

**3. Actualización de posición:**
```json
{
  "type": "position_update",
  "position": {
    "flight_number": "WN1234",
    "trip_id": "uuid-del-trip",
    "lat": 38.5421,
    "lon": -89.1234,
    "altitude": 35000,
    "ground_speed": 450.5,
    "heading": 270.3,
    "vertical_rate": -500,
    "origin_icao": "KORD",
    "origin_iata": "ORD",
    "destination_icao": "KSDF",
    "destination_iata": "SDF",
    "distance_to_destination_nm": 185.4,
    "eta_utc": "2026-01-18T14:30:00Z",
    "minutes_to_arrival": 25,
    "tracking_interval": "close",
    "interval_seconds": 150,
    "position_time": "2026-01-18T14:05:00Z",
    "cached_at": "2026-01-18T14:05:01Z",
    "cache_ttl_seconds": 2
  }
}
```

**4. Tracking detenido:**
```json
{
  "type": "tracking_stopped",
  "flight_number": "WN1234",
  "trip_id": "uuid-del-trip"
}
```

**5. Pong:**
```json
{
  "type": "pong"
}
```

**6. Error:**
```json
{
  "type": "error",
  "detail": "flight_number and trip_id required"
}
```

### Mensajes del Cliente

**1. Iniciar tracking de un vuelo:**
```json
{
  "action": "track",
  "flight_number": "WN1234",
  "trip_id": "uuid-del-trip",
  "origin_icao": "KORD",
  "destination_icao": "KSDF"
}
```
> Los campos `origin_icao` y `destination_icao` son opcionales pero recomendados para cálculo de ETA.

**2. Detener tracking:**
```json
{
  "action": "stop",
  "flight_number": "WN1234",
  "trip_id": "uuid-del-trip"
}
```

**3. Ping (keep-alive):**
```json
{
  "action": "ping",
  "token": "jwt_token_actualizado"
}
```
> ⚠️ El token es **requerido** en el ping. Si no se envía, se cerrará la conexión.

### Ejemplo de Implementación (React)

```typescript
import { useEffect, useRef, useCallback, useState } from 'react';

interface FlightPosition {
  flight_number: string;
  trip_id: string;
  lat: number;
  lon: number;
  altitude: number | null;
  ground_speed: number | null;
  heading: number | null;
  vertical_rate: number | null;
  origin_icao: string | null;
  origin_iata: string | null;
  destination_icao: string | null;
  destination_iata: string | null;
  distance_to_destination_nm: number | null;
  eta_utc: string | null;
  minutes_to_arrival: number | null;
  tracking_interval: string;
  interval_seconds: number;
  position_time: string;
  cached_at: string;
  cache_ttl_seconds: number;
}

interface FlightToTrack {
  flight_number: string;
  trip_id: string;
  origin_icao?: string;
  destination_icao?: string;
}

interface UseFlightTrackingOptions {
  token: string;
  onPositionUpdate: (position: FlightPosition) => void;
  onTrackingStarted?: (flightNumber: string, tripId: string) => void;
  onTrackingStopped?: (flightNumber: string, tripId: string) => void;
  onError?: (error: string) => void;
}

export function useFlightTracking({
  token,
  onPositionUpdate,
  onTrackingStarted,
  onTrackingStopped,
  onError,
}: UseFlightTrackingOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [trackedFlights, setTrackedFlights] = useState<Set<string>>(new Set());
  const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const connect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }

    const ws = new WebSocket(
      `wss://api.gt360.app/ws/flights/tracking?token=${token}`
    );

    ws.onopen = () => {
      console.log('Tracking WS connected');
      setIsConnected(true);

      // Ping cada 30 segundos con token
      pingIntervalRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ action: 'ping', token }));
        }
      }, 30000);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'connected':
          console.log('Tracking WS ready');
          break;

        case 'position_update':
          onPositionUpdate(data.position);
          break;

        case 'tracking_started':
          setTrackedFlights(prev =>
            new Set([...prev, `${data.flight_number}:${data.trip_id}`])
          );
          onTrackingStarted?.(data.flight_number, data.trip_id);
          break;

        case 'tracking_stopped':
          setTrackedFlights(prev => {
            const next = new Set(prev);
            next.delete(`${data.flight_number}:${data.trip_id}`);
            return next;
          });
          onTrackingStopped?.(data.flight_number, data.trip_id);
          break;

        case 'error':
          console.error('Tracking WS error:', data.detail);
          onError?.(data.detail);
          if (data.code === 401) {
            ws.close();
          }
          break;
      }
    };

    ws.onclose = (event) => {
      console.log('Tracking WS disconnected', event.code);
      setIsConnected(false);

      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
      }

      // Reconectar después de 3 segundos
      if (event.code !== 1000) {
        reconnectTimeoutRef.current = setTimeout(connect, 3000);
      }
    };

    ws.onerror = (error) => {
      console.error('Tracking WS error:', error);
    };

    wsRef.current = ws;
  }, [token, onPositionUpdate, onTrackingStarted, onTrackingStopped, onError]);

  const startTracking = useCallback((flight: FlightToTrack) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        action: 'track',
        flight_number: flight.flight_number,
        trip_id: flight.trip_id,
        origin_icao: flight.origin_icao,
        destination_icao: flight.destination_icao,
      }));
    }
  }, []);

  const stopTracking = useCallback((flightNumber: string, tripId: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        action: 'stop',
        flight_number: flightNumber,
        trip_id: tripId,
      }));
    }
  }, []);

  useEffect(() => {
    connect();

    return () => {
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      wsRef.current?.close(1000);
    };
  }, [connect]);

  return {
    isConnected,
    trackedFlights,
    startTracking,
    stopTracking,
  };
}
```

---

## Flujo Completo de Integración

### 1. Al cargar la página de trips

```typescript
// 1. Obtener trips con vuelos para una location específica
const trips = await fetchTrips(locationId);

// 2. Extraer flight numbers (sin espacios, uppercase)
const flightNumbers = trips
  .filter(trip => trip.flight_number)
  .map(trip => trip.flight_number!.replace(/\s/g, '').toUpperCase());

// 3. Suscribir a push notifications via REST (para AeroDataBox)
const flightsToSubscribe = trips
  .filter(trip => trip.flight_number && trip.pick_up_date)
  .map(trip => ({
    flight_number: trip.flight_number!.replace(/\s/g, ''),
    trip_id: trip.id,
    date_local: trip.pick_up_date,
  }));

const response = await fetch('/v1/flights/tracking/subscribe', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({ flights: flightsToSubscribe }),
});

const result = await response.json();
console.log(`Subscribed to AeroDataBox: ${result.success_count}/${result.total}`);

// 4. Conectar al WebSocket de push con location_id + flight_numbers
// Solo necesitas UNA conexión por location
const wsUrl = `wss://api.gt360.app/ws/flights/push?location_id=${locationId}&flight_numbers=${flightNumbers.join(',')}&token=${token}`;
const pushWs = new WebSocket(wsUrl);
```

### 2. Cuando un vuelo cambia de estado (recibido via push WS)

```typescript
// En el handler de flight updates
const handleFlightUpdate = (update: FlightUpdate) => {
  const { flight_number, status, message } = update;

  // Mostrar notificación con el mensaje formateado
  toast.info(message);  // "Flight WN1036 has arrived at 13:28"

  // Actualizar UI con nuevo estado
  updateFlightStatus(flight_number, status);

  // Si el vuelo despegó, iniciar tracking en tiempo real
  if (['Departed', 'EnRoute'].includes(status)) {
    // Encontrar el trip correspondiente para obtener trip_id
    const trip = trips.find(t =>
      t.flight_number?.replace(/\s/g, '') === flight_number
    );

    if (trip) {
      trackingWs.startTracking({
        flight_number,
        trip_id: trip.id,
        origin_icao: trip.origin_icao,
        destination_icao: trip.destination_icao,
      });
    }
  }

  // Si el vuelo aterrizó, detener tracking
  if (['Arrived', 'Canceled', 'Diverted'].includes(status)) {
    const trip = trips.find(t =>
      t.flight_number?.replace(/\s/g, '') === flight_number
    );

    if (trip) {
      trackingWs.stopTracking(flight_number, trip.id);
    }
  }
};
```

### 3. Mostrar posición en el mapa

```typescript
// En el handler de position updates
const handlePositionUpdate = (position: FlightPosition) => {
  // Actualizar marcador en el mapa
  updateAircraftMarker({
    id: `${position.flight_number}:${position.trip_id}`,
    lat: position.lat,
    lon: position.lon,
    heading: position.heading,
    altitude: position.altitude,
    speed: position.ground_speed,
  });

  // Mostrar información de vuelo
  updateFlightInfo({
    flightNumber: position.flight_number,
    altitude: position.altitude ? `${position.altitude.toLocaleString()} ft` : 'N/A',
    speed: position.ground_speed ? `${Math.round(position.ground_speed)} kts` : 'N/A',
    heading: position.heading ? `${Math.round(position.heading)}°` : 'N/A',
    verticalRate: position.vertical_rate
      ? `${position.vertical_rate > 0 ? '+' : ''}${position.vertical_rate} ft/min`
      : 'N/A',
  });

  // Mostrar ETA
  if (position.minutes_to_arrival !== null) {
    const hours = Math.floor(position.minutes_to_arrival / 60);
    const mins = position.minutes_to_arrival % 60;
    updateETA(
      position.flight_number,
      hours > 0 ? `${hours}h ${mins}m` : `${mins}m`
    );
  }

  // Log del intervalo actual (para debugging)
  console.log(
    `Tracking ${position.flight_number}: ` +
    `${position.minutes_to_arrival ?? '?'} min to arrival, ` +
    `interval: ${position.tracking_interval} (${position.interval_seconds}s)`
  );
};
```

---

## Tabla de Intervalos de Tracking

| ETA (min) | Intervalo | Frecuencia | Uso |
|-----------|-----------|------------|-----|
| >60 | `far` | cada 20 min | Vuelo en crucero, lejos del destino |
| 30-60 | `medium` | cada 5 min | Aproximándose |
| 20-30 | `close` | cada 2.5 min | Comenzando descenso |
| 10-20 | `very_close` | cada 1 min | En aproximación final |
| <10 | `real_time` | cada 1 seg | Aterrizando |

---

## Códigos de Error

### HTTP Errors

| Code | Descripción | Acción |
|------|-------------|--------|
| 400 | Bad Request - payload inválido o lista vacía | Verificar payload |
| 400 | Maximum 50 flights per request | Dividir en múltiples requests |
| 401 | Token inválido o expirado | Renovar token |
| 404 | Vuelo no encontrado | Verificar flight_number y date |
| 429 | Rate limit | Esperar y reintentar con backoff |

### WebSocket Errors

| Code | Descripción | Acción |
|------|-------------|--------|
| 401 | Token inválido en ping | Reconectar con token válido |
| 1008 | WS Auth failed | Token inválido, cerrar y reconectar |
| 1011 | WS Error interno | Reconectar después de delay |

### Error Response Format

```json
{
  "type": "error",
  "code": 401,
  "detail": "Invalid or expired token"
}
```

---

## Mejores Prácticas

### 1. Manejo de Reconexión

```typescript
const RECONNECT_DELAYS = [1000, 2000, 5000, 10000, 30000]; // Backoff exponencial

let reconnectAttempt = 0;

ws.onclose = (event) => {
  if (event.code !== 1000) { // No fue cierre intencional
    const delay = RECONNECT_DELAYS[Math.min(reconnectAttempt, RECONNECT_DELAYS.length - 1)];
    reconnectAttempt++;
    setTimeout(connect, delay);
  }
};

ws.onopen = () => {
  reconnectAttempt = 0; // Reset on successful connection
};
```

### 2. Actualización de Token

```typescript
// Cuando el token se renueva, actualizar la referencia
const tokenRef = useRef(token);

useEffect(() => {
  tokenRef.current = token;
}, [token]);

// En el ping, siempre usar el token más reciente
pingIntervalRef.current = setInterval(() => {
  ws.send(JSON.stringify({ action: 'ping', token: tokenRef.current }));
}, 30000);
```

### 3. Limpieza de Recursos

```typescript
useEffect(() => {
  return () => {
    // Detener todos los trackings antes de desconectar
    trackedFlights.forEach(key => {
      const [flightNumber, tripId] = key.split(':');
      stopTracking(flightNumber, tripId);
    });

    // Cerrar conexiones
    wsRef.current?.close(1000);
  };
}, []);
```

### 4. Optimización de Renders

```typescript
// Usar useCallback para callbacks estables
const handlePositionUpdate = useCallback((position: FlightPosition) => {
  // Actualizar solo si la posición cambió significativamente
  setPositions(prev => {
    const key = `${position.flight_number}:${position.trip_id}`;
    const existing = prev.get(key);

    if (existing &&
        Math.abs(existing.lat - position.lat) < 0.0001 &&
        Math.abs(existing.lon - position.lon) < 0.0001) {
      return prev; // No actualizar si el cambio es mínimo
    }

    return new Map(prev).set(key, position);
  });
}, []);
```

---

## Variables de Entorno (Backend)

```env
# AeroDataBox Push API
AERODATABOX_RAPIDAPI_KEY=tu_api_key
AERODATABOX_RAPIDAPI_HOST=aerodatabox.p.rapidapi.com

# Webhook configuration
FLIGHT_WEBHOOK_URL=https://api.gt360.app/v1/webhooks/flights/push
FLIGHT_SUBSCRIPTION_HOURS=24

# Redis (para pub/sub y cache)
REDIS_URL=redis://localhost:6379
```

---

## Webhook Endpoint (Para Referencia)

El backend expone un webhook para recibir notificaciones de AeroDataBox:

```
POST /v1/webhooks/flights/push
```

Este endpoint:
1. Parsea la notificación de AeroDataBox
2. Extrae `flight_number` de `subscription.subject.id` o `flights[0].number`
3. Extrae `arrival_iata` de `flights[0].arrival.airport.iata`
4. Genera mensaje formateado según el status (ej: "Flight WN1036 has arrived at 13:28")
5. Publica a Redis canal: `flight:push:{arrival_iata}:{flight_number}`
6. Solo clientes suscritos a ese arrival_iata + flight_number reciben la notificación

**Response:**
```json
{
  "status": "ok",
  "flight_number": "WN1036",
  "arrival_iata": "SDF",
  "flight_status": "Arrived",
  "message": "Flight WN1036 has arrived at 13:28"
}
```

**Health Check:**
```
GET /v1/webhooks/flights/push/health
```

Response:
```json
{
  "status": "ok",
  "timestamp": "2026-01-18T14:30:00Z"
}
```

---

## Resumen de Cambios Recientes

### Nuevo formato de Push WebSocket (v2)

| Aspecto | Antes | Ahora |
|---------|-------|-------|
| Parámetros | `trip_id` | `location_id` + `flight_numbers` |
| Filtrado | Por trip_id | Por arrival_iata (del location) + flight_number |
| Mensajes | `push_notification` con raw data | `flight_update` con mensaje formateado |
| Suscripción dinámica | Por trip_id | Por flight_number |

### Normalización de Flight Numbers

⚠️ **IMPORTANTE**: Los flight numbers deben normalizarse sin espacios:
- AeroDataBox envía: `"WN 1036"` (con espacio)
- Frontend debe enviar: `"WN1036"` (sin espacio)
- Backend normaliza ambos a uppercase sin espacios para matching
