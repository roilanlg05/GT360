# 🔌 Guía de Integración WebSocket - Trips Real-time

## Índice

1. [Conexión](#1-conexión)
2. [Eventos del WebSocket](#2-eventos-del-websocket)
3. [Estructura de Mensajes](#3-estructura-de-mensajes)
4. [Workflow Recomendado](#4-workflow-recomendado)
5. [Implementación Completa (TypeScript)](#5-implementación-completa-typescript)
6. [Ejemplo de Uso en React](#6-ejemplo-de-uso-en-react)
7. [Resumen de Flujo](#7-resumen-de-flujo)
8. [Manejo de Errores](#8-manejo-de-errores)
9. [Consideraciones de Seguridad](#9-consideraciones-de-seguridad)

---

## 1. Conexión

### URL de conexión

```
wss://tu-dominio.com/ws/trips?location_id={LOCATION_ID}&token={JWT_TOKEN}
```

### Parámetros requeridos

| Parámetro     | Tipo   | Descripción                                      |
|---------------|--------|--------------------------------------------------|
| `location_id` | UUID   | ID de la location a la que quieres conectarte    |
| `token`       | string | JWT token válido del usuario                     |

### Ejemplo de conexión

```typescript
const locationId = "0d1a3647-c3fc-4e01-990b-a4995fd2e357";
const token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...";

const ws = new WebSocket(
  `wss://api.example.com/ws/trips?location_id=${locationId}&token=${token}`
);
```

### Códigos de cierre

| Código | Significado                                    |
|--------|------------------------------------------------|
| 1000   | Cierre normal                                  |
| 1008   | Error de autenticación (token inválido/expirado) |
| 1011   | Error interno del servidor                     |

---

## 2. Eventos del WebSocket

### Eventos que puedes ENVIAR (Frontend → Backend)

| Action        | Payload                                  | Descripción                          |
|---------------|------------------------------------------|--------------------------------------|
| `subscribe`   | `{"action": "subscribe"}`                | Confirma suscripción a la location   |
| `unsubscribe` | `{"action": "unsubscribe"}`              | Desuscribirse de la location         |
| `ping`        | `{"action": "ping", "token": "<jwt>"}`   | Validar token (enviar cada 1 minuto) |

### Eventos que puedes RECIBIR (Backend → Frontend)

| Type           | Descripción                                           |
|----------------|-------------------------------------------------------|
| `snapshot`     | Lista inicial de todos los trips de la location       |
| `subscribed`   | Confirmación de suscripción                           |
| `unsubscribed` | Confirmación de desuscripción                         |
| `pong`         | Respuesta a ping (token válido)                       |
| `trip_event`   | Evento de cambio en un trip (insert/update/delete)    |
| `error`        | Error (incluye `code` y `detail`)                     |

---

## 3. Estructura de Mensajes

### 📥 Snapshot (recibido automáticamente al conectar)

```json
{
  "type": "snapshot",
  "location_id": "0d1a3647-c3fc-4e01-990b-a4995fd2e357",
  "trips": [
    {
      "id": "000bc3f8-2d80-42a6-9f3e-65d0466ce688",
      "assigned_driver": null,
      "location_id": "0d1a3647-c3fc-4e01-990b-a4995fd2e357",
      "pick_up_date": "2025-11-29",
      "pick_up_time": "04:10:00",
      "pick_up_location": "Hyatt Regency Louisville",
      "drop_off_location": "CFG",
      "airline": "WN",
      "flight_number": "4285",
      "riders": {
        "fligth": 2,
        "in_fligth": 3
      },
      "started_at": null,
      "picked_up_at": null,
      "dropped_off_at": null,
      "created_at": "2026-01-01T06:53:46.326605+00:00",
      "updated_at": "2026-01-01T06:53:46.326605+00:00"
    }
  ]
}
```

### 📥 Subscribed (confirmación de suscripción)

```json
{
  "type": "subscribed",
  "location_id": "0d1a3647-c3fc-4e01-990b-a4995fd2e357"
}
```

### 📥 Unsubscribed (confirmación de desuscripción)

```json
{
  "type": "unsubscribed",
  "location_id": "0d1a3647-c3fc-4e01-990b-a4995fd2e357"
}
```

### 📥 Pong (respuesta a ping)

```json
{
  "type": "pong"
}
```

### 📥 Trip Event (cambios en tiempo real)

#### Insert (nuevo trip)

```json
{
  "type": "trip_event",
  "event_type": "insert",
  "location_id": "0d1a3647-c3fc-4e01-990b-a4995fd2e357",
  "trip_id": "000bc3f8-2d80-42a6-9f3e-65d0466ce688",
  "trip": {
    "id": "000bc3f8-2d80-42a6-9f3e-65d0466ce688",
    "assigned_driver": null,
    "location_id": "0d1a3647-c3fc-4e01-990b-a4995fd2e357",
    "pick_up_date": "2025-11-29",
    "pick_up_time": "04:10:00",
    "pick_up_location": "Hyatt Regency Louisville",
    "drop_off_location": "CFG",
    "airline": "WN",
    "flight_number": "4285",
    "riders": {
      "fligth": 2,
      "in_fligth": 3
    },
    "started_at": null,
    "picked_up_at": null,
    "dropped_off_at": null,
    "created_at": "2026-01-01T06:53:46.326605+00:00",
    "updated_at": "2026-01-01T06:53:46.326605+00:00"
  }
}
```

#### Update (trip modificado)

```json
{
  "type": "trip_event",
  "event_type": "update",
  "location_id": "0d1a3647-c3fc-4e01-990b-a4995fd2e357",
  "trip_id": "000bc3f8-2d80-42a6-9f3e-65d0466ce688",
  "trip": {
    "id": "000bc3f8-2d80-42a6-9f3e-65d0466ce688",
    "assigned_driver": "driver-uuid-here",
    "location_id": "0d1a3647-c3fc-4e01-990b-a4995fd2e357",
    "pick_up_date": "2025-11-29",
    "pick_up_time": "04:10:00",
    "pick_up_location": "Hyatt Regency Louisville",
    "drop_off_location": "CFG",
    "airline": "WN",
    "flight_number": "4285",
    "riders": {
      "fligth": 2,
      "in_fligth": 3
    },
    "started_at": "2026-01-01T07:00:00.000000+00:00",
    "picked_up_at": null,
    "dropped_off_at": null,
    "created_at": "2026-01-01T06:53:46.326605+00:00",
    "updated_at": "2026-01-01T07:00:00.000000+00:00"
  }
}
```

#### Delete (trip eliminado)

```json
{
  "type": "trip_event",
  "event_type": "delete",
  "location_id": "0d1a3647-c3fc-4e01-990b-a4995fd2e357",
  "trip_id": "000bc3f8-2d80-42a6-9f3e-65d0466ce688"
}
```

### 📥 Error

```json
{
  "type": "error",
  "code": 401,
  "detail": "Invalid or expired token"
}
```

#### Códigos de error

| Code | Descripción                     |
|------|---------------------------------|
| 401  | Token inválido o expirado       |
| 400  | Token no proporcionado          |

---

## 4. Workflow Recomendado

```
┌─────────────────────────────────────────────────────────────────┐
│                    FRONTEND WORKFLOW                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. CONECTAR                                                    │
│     └── new WebSocket(url?location_id=X&token=Y)                │
│                                                                 │
│  2. RECIBIR SNAPSHOT (automático)                               │
│     └── { type: "snapshot", trips: [...] }                      │
│     └── Renderizar lista inicial de trips                       │
│                                                                 │
│  3. ENVIAR SUBSCRIBE (opcional, confirma suscripción)           │
│     └── { action: "subscribe" }                                 │
│                                                                 │
│  4. ESCUCHAR EVENTOS EN TIEMPO REAL                             │
│     └── { type: "trip_event", event_type: "insert|update|delete"│
│     └── Actualizar UI según evento                              │
│                                                                 │
│  5. PING/PONG (cada 60 segundos)                                │
│     └── Enviar: { action: "ping", token: "<current_jwt>" }      │
│     └── Esperar: { type: "pong" }                               │
│     └── Si error 401 → Renovar token o cerrar sesión            │
│                                                                 │
│  6. DESCONECTAR                                                 │
│     └── ws.close() o { action: "unsubscribe" }                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Diagrama de secuencia

```
Frontend                                    Backend
   │                                           │
   │──── WebSocket Connect ───────────────────>│
   │     ?location_id=X&token=Y                │
   │                                           │
   │<─── Connection Accepted ─────────────────│
   │                                           │
   │<─── { type: "snapshot", trips: [...] } ──│
   │                                           │
   │──── { action: "subscribe" } ─────────────>│
   │                                           │
   │<─── { type: "subscribed" } ──────────────│
   │                                           │
   │         ... tiempo pasa ...               │
   │                                           │
   │<─── { type: "trip_event", ... } ─────────│
   │                                           │
   │         ... cada 60 segundos ...          │
   │                                           │
   │──── { action: "ping", token: "..." } ────>│
   │                                           │
   │<─── { type: "pong" } ────────────────────│
   │                                           │
   │         ... al salir ...                  │
   │                                           │
   │──── { action: "unsubscribe" } ───────────>│
   │                                           │
   │<─── { type: "unsubscribed" } ────────────│
   │                                           │
   │──── WebSocket Close ─────────────────────>│
   │                                           │
```

---

## 5. Implementación Completa (TypeScript)

### Tipos

```typescript
// types/trips.ts

export interface Trip {
  id: string;
  location_id: string;
  pick_up_date: string;
  pick_up_time: string;
  pick_up_location: string;
  drop_off_location: string;
  airline: string;
  flight_number: string;
  assigned_driver: string | null;
  riders: {
    fligth: number;
    in_fligth: number;
  };
  started_at: string | null;
  picked_up_at: string | null;
  dropped_off_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TripEvent {
  type: "trip_event";
  event_type: "insert" | "update" | "delete";
  location_id: string;
  trip_id: string;
  trip?: Trip;
}

export interface SnapshotEvent {
  type: "snapshot";
  location_id: string;
  trips: Trip[];
}

export interface SubscribedEvent {
  type: "subscribed";
  location_id: string;
}

export interface UnsubscribedEvent {
  type: "unsubscribed";
  location_id: string;
}

export interface PongEvent {
  type: "pong";
}

export interface ErrorEvent {
  type: "error";
  code: number;
  detail: string;
}

export type WSMessage =
  | TripEvent
  | SnapshotEvent
  | SubscribedEvent
  | UnsubscribedEvent
  | PongEvent
  | ErrorEvent;
```

### Clase WebSocket Manager

```typescript
// services/TripsWebSocket.ts

import { Trip, TripEvent, WSMessage } from "../types/trips";

export interface TripsWebSocketConfig {
  baseUrl: string;
  locationId: string;
  getToken: () => string;
  onTripsUpdate: (trips: Trip[]) => void;
  onTripEvent: (event: TripEvent) => void;
  onError: (error: { code: number; detail: string }) => void;
  onConnectionChange: (connected: boolean) => void;
}

export class TripsWebSocket {
  private ws: WebSocket | null = null;
  private pingInterval: NodeJS.Timeout | null = null;
  private reconnectTimeout: NodeJS.Timeout | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private isIntentionallyClosed = false;

  private baseUrl: string;
  private locationId: string;
  private getToken: () => string;
  private onTripsUpdate: (trips: Trip[]) => void;
  private onTripEvent: (event: TripEvent) => void;
  private onError: (error: { code: number; detail: string }) => void;
  private onConnectionChange: (connected: boolean) => void;

  constructor(config: TripsWebSocketConfig) {
    this.baseUrl = config.baseUrl;
    this.locationId = config.locationId;
    this.getToken = config.getToken;
    this.onTripsUpdate = config.onTripsUpdate;
    this.onTripEvent = config.onTripEvent;
    this.onError = config.onError;
    this.onConnectionChange = config.onConnectionChange;
  }

  /**
   * Conectar al WebSocket
   */
  connect(): void {
    this.isIntentionallyClosed = false;
    const token = this.getToken();
    const url = `${this.baseUrl}/ws/trips?location_id=${this.locationId}&token=${token}`;

    console.log("[WS] Connecting to:", url);
    this.ws = new WebSocket(url);

    this.ws.onopen = this.handleOpen.bind(this);
    this.ws.onmessage = this.handleMessage.bind(this);
    this.ws.onclose = this.handleClose.bind(this);
    this.ws.onerror = this.handleError.bind(this);
  }

  /**
   * Desconectar del WebSocket
   */
  disconnect(): void {
    this.isIntentionallyClosed = true;
    this.stopPingInterval();
    this.clearReconnectTimeout();

    if (this.ws) {
      this.send({ action: "unsubscribe" });
      this.ws.close(1000, "Client disconnecting");
      this.ws = null;
    }
  }

  /**
   * Enviar mensaje al servidor
   */
  send(data: object): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    } else {
      console.warn("[WS] Cannot send, WebSocket is not open");
    }
  }

  /**
   * Verificar si está conectado
   */
  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  // ─────────────────────────────────────────────────────────────
  // Event Handlers
  // ─────────────────────────────────────────────────────────────

  private handleOpen(): void {
    console.log("[WS] Connected");
    this.reconnectAttempts = 0;
    this.onConnectionChange(true);
    this.startPingInterval();

    // Confirmar suscripción
    this.send({ action: "subscribe" });
  }

  private handleMessage(event: MessageEvent): void {
    try {
      const data: WSMessage = JSON.parse(event.data);
      this.processMessage(data);
    } catch (error) {
      console.error("[WS] Failed to parse message:", error);
    }
  }

  private handleClose(event: CloseEvent): void {
    console.log("[WS] Disconnected, code:", event.code, "reason:", event.reason);
    this.onConnectionChange(false);
    this.stopPingInterval();

    // No reconectar si:
    // - Fue cierre intencional
    // - Fue error de autenticación (1008)
    // - Superamos el máximo de intentos
    if (
      this.isIntentionallyClosed ||
      event.code === 1008 ||
      this.reconnectAttempts >= this.maxReconnectAttempts
    ) {
      return;
    }

    this.scheduleReconnect();
  }

  private handleError(error: Event): void {
    console.error("[WS] Error:", error);
  }

  // ─────────────────────────────────────────────────────────────
  // Message Processing
  // ─────────────────────────────────────────────────────────────

  private processMessage(data: WSMessage): void {
    switch (data.type) {
      case "snapshot":
        console.log("[WS] Snapshot received:", data.trips.length, "trips");
        this.onTripsUpdate(data.trips);
        break;

      case "subscribed":
        console.log("[WS] Subscribed to location:", data.location_id);
        break;

      case "unsubscribed":
        console.log("[WS] Unsubscribed from location:", data.location_id);
        break;

      case "trip_event":
        console.log("[WS] Trip event:", data.event_type, data.trip_id);
        this.onTripEvent(data);
        break;

      case "pong":
        console.log("[WS] Pong received - token valid");
        break;

      case "error":
        console.error("[WS] Error:", data.code, data.detail);
        this.onError({ code: data.code, detail: data.detail });

        // Si es 401, el token expiró - cerrar conexión
        if (data.code === 401) {
          this.disconnect();
        }
        break;

      default:
        console.log("[WS] Unknown message type:", data);
    }
  }

  // ─────────────────────────────────────────────────────────────
  // Ping/Pong
  // ─────────────────────────────────────────────────────────────

  private startPingInterval(): void {
    // Ping cada 60 segundos para validar token
    this.pingInterval = setInterval(() => {
      this.sendPing();
    }, 60_000);
  }

  private stopPingInterval(): void {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  private sendPing(): void {
    const token = this.getToken(); // Obtener token actualizado
    console.log("[WS] Sending ping...");
    this.send({ action: "ping", token });
  }

  // ─────────────────────────────────────────────────────────────
  // Reconnection
  // ─────────────────────────────────────────────────────────────

  private scheduleReconnect(): void {
    // Exponential backoff: 1s, 2s, 4s, 8s, 16s (max 30s)
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
    console.log(`[WS] Reconnecting in ${delay}ms... (attempt ${this.reconnectAttempts + 1})`);

    this.reconnectTimeout = setTimeout(() => {
      this.reconnectAttempts++;
      this.connect();
    }, delay);
  }

  private clearReconnectTimeout(): void {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
  }
}

export default TripsWebSocket;
```

---

## 6. Ejemplo de Uso en React

### Hook personalizado

```typescript
// hooks/useTripsWebSocket.ts

import { useEffect, useState, useRef, useCallback } from "react";
import { TripsWebSocket } from "../services/TripsWebSocket";
import { Trip, TripEvent } from "../types/trips";

interface UseTripsWebSocketOptions {
  locationId: string;
  baseUrl: string;
  enabled?: boolean;
}

interface UseTripsWebSocketReturn {
  trips: Trip[];
  connected: boolean;
  error: { code: number; detail: string } | null;
}

export function useTripsWebSocket({
  locationId,
  baseUrl,
  enabled = true,
}: UseTripsWebSocketOptions): UseTripsWebSocketReturn {
  const [trips, setTrips] = useState<Trip[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<{ code: number; detail: string } | null>(null);
  const wsRef = useRef<TripsWebSocket | null>(null);

  const getToken = useCallback(() => {
    return localStorage.getItem("access_token") || "";
  }, []);

  const handleTripsUpdate = useCallback((newTrips: Trip[]) => {
    setTrips(newTrips);
  }, []);

  const handleTripEvent = useCallback((event: TripEvent) => {
    setTrips((prevTrips) => {
      switch (event.event_type) {
        case "insert":
          // Verificar que no exista ya
          if (prevTrips.some((t) => t.id === event.trip_id)) {
            return prevTrips;
          }
          return [...prevTrips, event.trip!];

        case "update":
          return prevTrips.map((trip) =>
            trip.id === event.trip_id ? event.trip! : trip
          );

        case "delete":
          return prevTrips.filter((trip) => trip.id !== event.trip_id);

        default:
          return prevTrips;
      }
    });
  }, []);

  const handleError = useCallback((err: { code: number; detail: string }) => {
    setError(err);

    if (err.code === 401) {
      // Token expirado - aquí puedes:
      // 1. Intentar renovar el token
      // 2. Redirigir al login
      console.log("Token expired, handle refresh or redirect to login");
    }
  }, []);

  const handleConnectionChange = useCallback((isConnected: boolean) => {
    setConnected(isConnected);
    if (isConnected) {
      setError(null);
    }
  }, []);

  useEffect(() => {
    if (!enabled || !locationId) {
      return;
    }

    wsRef.current = new TripsWebSocket({
      baseUrl,
      locationId,
      getToken,
      onTripsUpdate: handleTripsUpdate,
      onTripEvent: handleTripEvent,
      onError: handleError,
      onConnectionChange: handleConnectionChange,
    });

    wsRef.current.connect();

    return () => {
      wsRef.current?.disconnect();
      wsRef.current = null;
    };
  }, [
    enabled,
    locationId,
    baseUrl,
    getToken,
    handleTripsUpdate,
    handleTripEvent,
    handleError,
    handleConnectionChange,
  ]);

  return { trips, connected, error };
}

export default useTripsWebSocket;
```

### Componente de ejemplo

```tsx
// components/TripsView.tsx

import React from "react";
import { useTripsWebSocket } from "../hooks/useTripsWebSocket";
import { Trip } from "../types/trips";

interface TripsViewProps {
  locationId: string;
}

export function TripsView({ locationId }: TripsViewProps) {
  const { trips, connected, error } = useTripsWebSocket({
    locationId,
    baseUrl: "wss://api.example.com",
    enabled: true,
  });

  return (
    <div className="trips-container">
      {/* Status indicator */}
      <div className="connection-status">
        <span className={`status-dot ${connected ? "connected" : "disconnected"}`} />
        {connected ? "🟢 Conectado" : "🔴 Desconectado"}
      </div>

      {/* Error message */}
      {error && (
        <div className="error-banner">
          Error {error.code}: {error.detail}
        </div>
      )}

      {/* Trips list */}
      <div className="trips-list">
        {trips.length === 0 ? (
          <p>No hay trips disponibles</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Hora</th>
                <th>Pickup</th>
                <th>Dropoff</th>
                <th>Vuelo</th>
                <th>Driver</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {trips.map((trip) => (
                <TripRow key={trip.id} trip={trip} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function TripRow({ trip }: { trip: Trip }) {
  const getStatus = () => {
    if (trip.dropped_off_at) return "✅ Completado";
    if (trip.picked_up_at) return "🚗 En camino";
    if (trip.started_at) return "🏃 Iniciado";
    if (trip.assigned_driver) return "👤 Asignado";
    return "⏳ Pendiente";
  };

  return (
    <tr>
      <td>{trip.pick_up_date}</td>
      <td>{trip.pick_up_time}</td>
      <td>{trip.pick_up_location}</td>
      <td>{trip.drop_off_location}</td>
      <td>
        {trip.airline} {trip.flight_number}
      </td>
      <td>{trip.assigned_driver || "-"}</td>
      <td>{getStatus()}</td>
    </tr>
  );
}

export default TripsView;
```

### Estilos CSS básicos

```css
/* styles/trips.css */

.trips-container {
  padding: 20px;
}

.connection-status {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  font-size: 14px;
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.status-dot.connected {
  background-color: #22c55e;
}

.status-dot.disconnected {
  background-color: #ef4444;
}

.error-banner {
  background-color: #fef2f2;
  border: 1px solid #fecaca;
  color: #dc2626;
  padding: 12px;
  border-radius: 8px;
  margin-bottom: 16px;
}

.trips-list table {
  width: 100%;
  border-collapse: collapse;
}

.trips-list th,
.trips-list td {
  padding: 12px;
  text-align: left;
  border-bottom: 1px solid #e5e7eb;
}

.trips-list th {
  background-color: #f9fafb;
  font-weight: 600;
}

.trips-list tr:hover {
  background-color: #f9fafb;
}
```

---

## 7. Resumen de Flujo

| Paso | Acción Frontend                              | Respuesta Backend                    |
|------|----------------------------------------------|--------------------------------------|
| 1    | Conectar con `?location_id=X&token=Y`        | Acepta conexión                      |
| 2    | -                                            | Recibe `snapshot` automáticamente    |
| 3    | Envía `{"action": "subscribe"}`              | Recibe `{"type": "subscribed"}`      |
| 4    | Escucha eventos                              | Recibe `trip_event` (insert/update/delete) |
| 5    | Cada 60s: `{"action": "ping", "token": "..."}` | Recibe `{"type": "pong"}` o error 401 |
| 6    | `{"action": "unsubscribe"}` o `ws.close()`   | Recibe `{"type": "unsubscribed"}`    |

---

## 8. Manejo de Errores

### Errores de conexión

```typescript
ws.onerror = (error) => {
  console.error("WebSocket error:", error);
  // Mostrar notificación al usuario
  showNotification("Error de conexión", "error");
};

ws.onclose = (event) => {
  if (event.code === 1008) {
    // Error de autenticación
    redirectToLogin();
  } else if (event.code !== 1000) {
    // Cierre inesperado - intentar reconectar
    scheduleReconnect();
  }
};
```

### Errores de token (401)

```typescript
if (data.type === "error" && data.code === 401) {
  // Opción 1: Intentar renovar el token
  const newToken = await refreshToken();
  if (newToken) {
    // Reconectar con nuevo token
    reconnect();
  } else {
    // Redirigir a login
    redirectToLogin();
  }
}
```

### Reconexión automática con backoff exponencial

```typescript
let reconnectAttempts = 0;
const maxAttempts = 5;

function scheduleReconnect() {
  if (reconnectAttempts >= maxAttempts) {
    showNotification("No se puede conectar al servidor", "error");
    return;
  }

  const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
  console.log(`Reconectando en ${delay}ms...`);

  setTimeout(() => {
    reconnectAttempts++;
    connect();
  }, delay);
}
```

---

## 9. Consideraciones de Seguridad

### Token JWT

- **Nunca** almacenar el token en localStorage en producción si hay riesgo de XSS
- Usar `httpOnly` cookies cuando sea posible
- El token debe tener un tiempo de expiración razonable (ej: 15-30 minutos)
- Implementar refresh tokens para renovar la sesión

### Validación de mensajes

```typescript
// Siempre validar los mensajes recibidos
function isValidTripEvent(data: unknown): data is TripEvent {
  return (
    typeof data === "object" &&
    data !== null &&
    "type" in data &&
    data.type === "trip_event" &&
    "event_type" in data &&
    "trip_id" in data
  );
}
```

### Rate limiting

- El backend implementa rate limiting
- No enviar más de 1 ping por minuto
- Evitar spam de subscribe/unsubscribe

---

## Ejemplo Completo: Conexión Mínima

```typescript
// Ejemplo mínimo funcional
const locationId = "your-location-id";
const token = "your-jwt-token";

const ws = new WebSocket(
  `wss://api.example.com/ws/trips?location_id=${locationId}&token=${token}`
);

let trips = [];

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  switch (data.type) {
    case "snapshot":
      trips = data.trips;
      renderTrips(trips);
      break;

    case "trip_event":
      if (data.event_type === "insert") {
        trips.push(data.trip);
      } else if (data.event_type === "update") {
        trips = trips.map((t) => (t.id === data.trip_id ? data.trip : t));
      } else if (data.event_type === "delete") {
        trips = trips.filter((t) => t.id !== data.trip_id);
      }
      renderTrips(trips);
      break;

    case "pong":
      console.log("Token válido");
      break;

    case "error":
      if (data.code === 401) {
        ws.close();
        redirectToLogin();
      }
      break;
  }
};

// Ping cada minuto
setInterval(() => {
  ws.send(JSON.stringify({ action: "ping", token: getLatestToken() }));
}, 60000);
```

---

## Changelog

| Versión | Fecha       | Cambios                                      |
|---------|-------------|----------------------------------------------|
| 1.0.0   | 2026-01-03  | Versión inicial - suscripción por location  |

---

## Contacto

Para dudas o problemas con la integración, contactar al equipo de backend.
