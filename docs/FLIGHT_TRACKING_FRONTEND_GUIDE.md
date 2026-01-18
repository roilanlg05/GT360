# Flight Tracking System - Frontend Integration Guide

## Overview

El sistema de tracking de vuelos en tiempo real tiene dos componentes principales:

1. **Push Notifications** - Notificaciones de cambios de estado del vuelo (AeroDataBox)
2. **Real-Time Tracking** - Posición del avión en tiempo real (ADSB.lol)

### Flujo General

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FLUJO DE TRACKING                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. Frontend envía lista de vuelos a trackear                               │
│     POST /v1/flights/tracking/subscribe                                      │
│                                                                              │
│  2. Frontend conecta a WebSocket de push notifications                       │
│     WS /ws/flights/push?trip_id=xxx&token=JWT                               │
│                                                                              │
│  3. Cuando el vuelo despega (status: "Departed"):                           │
│     - Backend activa tracking automáticamente                                │
│     - Frontend conecta al WS de tracking                                     │
│     WS /ws/flights/tracking?token=JWT                                        │
│                                                                              │
│  4. Frontend recibe posiciones en tiempo real con intervalos adaptativos:   │
│     - >60 min ETA: cada 20 min                                              │
│     - 30-60 min: cada 5 min                                                 │
│     - 20-30 min: cada 2.5 min                                               │
│     - 10-20 min: cada 1 min                                                 │
│     - <10 min: cada 1 segundo                                               │
│                                                                              │
│  5. Cuando el vuelo aterriza (status: "Landed"):                            │
│     - Backend desactiva tracking automáticamente                             │
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

**TypeScript Interface:**
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
  status: string;
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
    "lat": 38.5421,
    "lon": -89.1234,
    "altitude": 35000,
    "ground_speed": 450,
    "heading": 270
  },
  "current_interval": "medium",
  "interval_seconds": 300,
  "subscription_id": "adb-sub-123",
  "subscription_status": "active"
}
```

**TypeScript Interface:**
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

Obtiene la posición actual del avión. Usa cache de 2 segundos.

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

### Conexión

```
wss://api.gt360.app/ws/flights/push?trip_id={trip_id}&token={jwt_token}
```

**Parámetros de Query:**
| Param | Required | Description |
|-------|----------|-------------|
| trip_id | Yes | ID del trip a monitorear |
| token | Yes | JWT token de autenticación |

### Mensajes del Servidor

**1. Conexión exitosa:**
```json
{
  "type": "connected",
  "trip_id": "uuid-del-trip"
}
```

**2. Push notification (cambio de estado):**
```json
{
  "type": "push_notification",
  "trip_id": "uuid-del-trip",
  "notification": {
    "flight_number": "WN1234",
    "flight_iata": "WN1234",
    "flight_icao": "SWA1234",
    "status": "Departed",
    "departure_airport": "ORD",
    "departure_scheduled": "2026-01-18T12:00:00Z",
    "departure_estimated": "2026-01-18T12:05:00Z",
    "departure_actual": "2026-01-18T12:08:00Z",
    "arrival_airport": "SDF",
    "arrival_scheduled": "2026-01-18T14:30:00Z",
    "arrival_estimated": "2026-01-18T14:35:00Z",
    "arrival_actual": null,
    "received_at": "2026-01-18T12:08:05Z"
  }
}
```

**3. Suscripción adicional confirmada:**
```json
{
  "type": "subscribed",
  "trip_id": "otro-trip-id"
}
```

**4. Desuscripción confirmada:**
```json
{
  "type": "unsubscribed",
  "trip_id": "uuid-del-trip"
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

### Mensajes del Cliente

**1. Ping (keep-alive con validación de token):**
```json
{
  "action": "ping",
  "token": "jwt_token_actualizado"
}
```

**2. Suscribirse a otro trip:**
```json
{
  "action": "subscribe",
  "trip_id": "otro-trip-id"
}
```

**3. Desuscribirse de un trip:**
```json
{
  "action": "unsubscribe",
  "trip_id": "uuid-del-trip"
}
```

### Ejemplo de Implementación (React)

```typescript
import { useEffect, useRef, useCallback } from 'react';

interface PushNotification {
  flight_number: string;
  status: string;
  departure_actual: string | null;
  arrival_estimated: string | null;
  // ... otros campos
}

interface UsePushNotificationsOptions {
  tripId: string;
  token: string;
  onNotification: (notification: PushNotification) => void;
  onStatusChange?: (flightNumber: string, status: string) => void;
}

export function usePushNotifications({
  tripId,
  token,
  onNotification,
  onStatusChange,
}: UsePushNotificationsOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const connect = useCallback(() => {
    const ws = new WebSocket(
      `wss://api.gt360.app/ws/flights/push?trip_id=${tripId}&token=${token}`
    );

    ws.onopen = () => {
      console.log('Push WS connected');

      // Ping cada 30 segundos
      pingIntervalRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ action: 'ping', token }));
        }
      }, 30000);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'push_notification':
          onNotification(data.notification);

          // Detectar cuando el vuelo despega para activar tracking
          if (data.notification.status === 'Departed' && onStatusChange) {
            onStatusChange(data.notification.flight_number, 'Departed');
          }
          break;

        case 'error':
          console.error('Push WS error:', data.detail);
          if (data.code === 401) {
            ws.close();
          }
          break;
      }
    };

    ws.onclose = () => {
      console.log('Push WS disconnected');
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
      }

      // Reconectar después de 3 segundos
      setTimeout(connect, 3000);
    };

    wsRef.current = ws;
  }, [tripId, token, onNotification, onStatusChange]);

  useEffect(() => {
    connect();

    return () => {
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
      }
      wsRef.current?.close();
    };
  }, [connect]);

  return wsRef;
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
    "distance_to_destination_nm": 185.4,
    "eta_utc": "2026-01-18T14:30:00Z",
    "minutes_to_arrival": 25,
    "tracking_interval": "close",
    "interval_seconds": 150,
    "position_time": "2026-01-18T14:05:00Z"
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
  minutes_to_arrival: number | null;
  tracking_interval: string;
  interval_seconds: number;
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
}

export function useFlightTracking({
  token,
  onPositionUpdate,
}: UseFlightTrackingOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [trackedFlights, setTrackedFlights] = useState<Set<string>>(new Set());
  const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const connect = useCallback(() => {
    const ws = new WebSocket(
      `wss://api.gt360.app/ws/flights/tracking?token=${token}`
    );

    ws.onopen = () => {
      console.log('Tracking WS connected');
      setIsConnected(true);

      // Ping cada 30 segundos
      pingIntervalRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ action: 'ping', token }));
        }
      }, 30000);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'position_update':
          onPositionUpdate(data.position);
          break;

        case 'tracking_started':
          setTrackedFlights(prev =>
            new Set([...prev, `${data.flight_number}:${data.trip_id}`])
          );
          break;

        case 'tracking_stopped':
          setTrackedFlights(prev => {
            const next = new Set(prev);
            next.delete(`${data.flight_number}:${data.trip_id}`);
            return next;
          });
          break;

        case 'error':
          console.error('Tracking WS error:', data.detail);
          break;
      }
    };

    ws.onclose = () => {
      console.log('Tracking WS disconnected');
      setIsConnected(false);

      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
      }

      // Reconectar después de 3 segundos
      setTimeout(connect, 3000);
    };

    wsRef.current = ws;
  }, [token, onPositionUpdate]);

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
      wsRef.current?.close();
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
// 1. Obtener trips con vuelos
const trips = await fetchTrips();

// 2. Extraer vuelos para suscribir
const flightsToSubscribe = trips
  .filter(trip => trip.flight_number && trip.pick_up_date)
  .map(trip => ({
    flight_number: trip.flight_number,
    trip_id: trip.id,
    date_local: trip.pick_up_date,
  }));

// 3. Suscribir a push notifications
const response = await fetch('/v1/flights/tracking/subscribe', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({ flights: flightsToSubscribe }),
});

// 4. Conectar al WebSocket de push
const pushWs = new WebSocket(
  `wss://api.gt360.app/ws/flights/push?trip_id=${tripId}&token=${token}`
);
```

### 2. Cuando un vuelo despega (recibido via push)

```typescript
pushWs.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.type === 'push_notification') {
    const { flight_number, status, trip_id } = data.notification;

    // Actualizar UI con nuevo estado
    updateFlightStatus(flight_number, status);

    // Si el vuelo despegó, iniciar tracking en tiempo real
    if (status === 'Departed') {
      trackingWs.send(JSON.stringify({
        action: 'track',
        flight_number,
        trip_id,
        destination_icao: 'KSDF', // Aeropuerto destino
      }));
    }

    // Si el vuelo aterrizó, detener tracking
    if (status === 'Landed' || status === 'Arrived') {
      trackingWs.send(JSON.stringify({
        action: 'stop',
        flight_number,
        trip_id,
      }));
    }
  }
};
```

### 3. Mostrar posición en el mapa

```typescript
trackingWs.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.type === 'position_update') {
    const pos = data.position;

    // Actualizar marcador en el mapa
    updateAircraftMarker({
      id: `${pos.flight_number}:${pos.trip_id}`,
      lat: pos.lat,
      lon: pos.lon,
      heading: pos.heading,
      altitude: pos.altitude,
      speed: pos.ground_speed,
    });

    // Mostrar ETA
    if (pos.minutes_to_arrival !== null) {
      updateETA(pos.flight_number, pos.minutes_to_arrival);
    }

    // Log del intervalo actual
    console.log(
      `Tracking ${pos.flight_number}: ` +
      `${pos.minutes_to_arrival} min to arrival, ` +
      `interval: ${pos.tracking_interval} (${pos.interval_seconds}s)`
    );
  }
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

| Code | Descripción | Acción |
|------|-------------|--------|
| 400 | Bad Request | Verificar payload |
| 401 | Token inválido | Renovar token y reconectar |
| 404 | Vuelo no encontrado | Verificar flight_number y date |
| 429 | Rate limit | Esperar y reintentar |
| 1008 | WS Auth failed | Token inválido, cerrar y reconectar |
| 1011 | WS Error interno | Reconectar después de delay |

---

## Variables de Entorno Requeridas (Backend)

```env
AERODATABOX_RAPIDAPI_KEY=tu_api_key
AERODATABOX_RAPIDAPI_HOST=aerodatabox.p.rapidapi.com
FLIGHT_WEBHOOK_URL=https://api.gt360.app/v1/webhooks/flights/push
FLIGHT_SUBSCRIPTION_HOURS=24
```
