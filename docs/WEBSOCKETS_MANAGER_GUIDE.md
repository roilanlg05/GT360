vas a # GT360 - WebSocket Integration Guide (Manager Role)

> Guia completa para la implementacion y conexion de los 3 canales WebSocket disponibles para el rol **manager** en el frontend.

---

## Tabla de Contenidos

1. [Arquitectura General](#arquitectura-general)
2. [Autenticacion](#autenticacion)
3. [WS 1 — Eventos de Organizacion (`/ws/org`)](#ws-1--eventos-de-organizacion-wsorg)
4. [WS 2 — Trips en Tiempo Real (`/ws/trips`)](#ws-2--trips-en-tiempo-real-wstrips)
5. [WS 3 — Ubicacion de Drivers (`/ws/driver-locations`)](#ws-3--ubicacion-de-drivers-wsdriver-locations)
6. [Keep-Alive (Ping/Pong)](#keep-alive-pingpong)
7. [Reconexion y Manejo de Errores](#reconexion-y-manejo-de-errores)
8. [Referencia Rapida de Mensajes](#referencia-rapida-de-mensajes)

---

## Arquitectura General

```
┌─────────────────────────────────────────────────────────────────┐
│                     FRONTEND (Manager)                          │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐    │
│  │  /ws/org      │  │  /ws/trips   │  │ /ws/driver-locations│   │
│  │  (1 por app)  │  │ (1 por loc.) │  │ (1 global o por loc)│   │
│  └──────┬───────┘  └──────┬───────┘  └─────────┬──────────┘    │
└─────────┼──────────────────┼───────────────────┼────────────────┘
          │                  │                   │
          ▼                  ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                       BACKEND (FastAPI)                          │
│                                                                 │
│  OrgWSManager          WSManager         DriverLocationWSManager │
│       │                    │                      │              │
│       ▼                    ▼                      ▼              │
│  Redis: org:{org_id}  Redis: loc:{loc_id}  Redis: driver_locations:{org_id} │
└─────────────────────────────────────────────────────────────────┘
```

**Conexiones recomendadas para el manager:**

| WebSocket | Cuando conectar | Cantidad |
|-----------|----------------|----------|
| `/ws/org` | Al iniciar sesion (siempre activo) | 1 por sesion |
| `/ws/trips` | Al abrir una location/dashboard de trips | 1 por location abierta |
| `/ws/driver-locations` | Al abrir el mapa de drivers | 1 (global o filtrado por location) |

---

## Autenticacion

Todos los endpoints WebSocket usan **JWT via query parameter** (no header).

### Obtencion de la URL

```
wss://{BACKEND_URL}/ws/{endpoint}?token={JWT_ACCESS_TOKEN}&{params}
```

> **Nota:** El middleware HTTP `VerifyToken` NO aplica a WebSockets. Cada endpoint WS valida el token manualmente al conectar.

### Flujo de autenticacion

```
1. Cliente envia: wss://api.example.com/ws/org?token=eyJ...&organization_id=uuid
2. Backend llama decode_token(token)
3. Si es invalido → close(code=1008)
4. Si organization_id del token != query param → close(code=1008)
5. Si es valido → accept() + envio de mensaje de confirmacion
```

### Estructura del JWT (claims)

```json
{
  "sub": "user-uuid",
  "iat": 1708700000,
  "exp": 1708703600,
  "metadata": {
    "role": "manager",
    "organization_id": "org-uuid",
    "email": "manager@example.com"
  }
}
```

---

## WS 1 — Eventos de Organizacion (`/ws/org`)

Canal de eventos a nivel organizacion. Recibe notificaciones de eliminacion de locations y **eventos de billing** (solo managers).

### Conexion

```
wss://{BACKEND_URL}/ws/org?organization_id={ORG_ID}&token={JWT}
```

| Parametro | Tipo | Requerido | Descripcion |
|-----------|------|-----------|-------------|
| `organization_id` | `string (UUID)` | Si | ID de la organizacion |
| `token` | `string` | Si | JWT access token |

### Mensaje de confirmacion (al conectar)

```json
{
  "type": "connected",
  "organization_id": "org-uuid",
  "message": "Connected to organization events"
}
```

### Eventos que recibe el manager

#### `location_deleted`

Se recibe cuando una location y sus hotels son eliminados.

```json
{
  "type": "location_deleted",
  "location_id": "location-uuid",
  "location_name": "SDF",
  "message": "Location SDF and its hotels have been deleted",
  "hotels": ["Hotel A", "Hotel B"],
  "hotels_count": 2
}
```

**Accion frontend:** Remover la location del sidebar/lista, mostrar notificacion toast.

#### `billing_event` — `payment_failed`

```json
{
  "type": "billing_event",
  "event": "payment_failed",
  "message": "Payment failed (attempt 2). We will retry March 15, 2026. Please update your payment method to avoid service interruption.",
  "subscription_status": "past_due",
  "attempt_count": 2
}
```

**Accion frontend:** Mostrar banner de alerta rojo, redirigir a pagina de billing.

#### `billing_event` — `payment_recovered`

```json
{
  "type": "billing_event",
  "event": "payment_recovered",
  "message": "Payment received. Your subscription is now active again.",
  "subscription_status": "active"
}
```

**Accion frontend:** Remover banner de alerta, mostrar notificacion de exito.

#### `billing_event` — `subscription_canceled`

```json
{
  "type": "billing_event",
  "event": "subscription_canceled",
  "message": "Your subscription has been canceled. You will lose access to paid features at the end of the current period.",
  "subscription_status": "canceled"
}
```

**Accion frontend:** Mostrar banner informativo, deshabilitar acciones premium.

### Ejemplo de implementacion (TypeScript/React)

```typescript
function useOrgWebSocket(orgId: string, token: string) {
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const url = `wss://${BACKEND_URL}/ws/org?organization_id=${orgId}&token=${token}`;
    const ws = new WebSocket(url);

    ws.onopen = () => {
      console.log("Org WS connected");
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case "connected":
          // Confirmacion de conexion
          break;

        case "location_deleted":
          // Remover location de la UI
          removeLocation(data.location_id);
          showToast(`Location ${data.location_name} deleted`);
          break;

        case "billing_event":
          handleBillingEvent(data);
          break;

        case "pong":
          // Respuesta al ping
          break;

        case "error":
          if (data.code === 401) {
            // Token expirado — refrescar y reconectar
            refreshTokenAndReconnect();
          }
          break;
      }
    };

    ws.onclose = (event) => {
      if (event.code === 1008) {
        // Autenticacion fallida
        redirectToLogin();
      } else {
        // Reconexion automatica
        scheduleReconnect();
      }
    };

    wsRef.current = ws;
    return () => ws.close();
  }, [orgId, token]);

  return wsRef;
}
```

---

## WS 2 — Trips en Tiempo Real (`/ws/trips`)

Canal de actualizaciones de trips para una location especifica. Envia un **snapshot** inicial con todos los trips activos y luego actualizaciones incrementales.

### Conexion

```
wss://{BACKEND_URL}/ws/trips?location_id={LOCATION_ID}&token={JWT}
```

| Parametro | Tipo | Requerido | Descripcion |
|-----------|------|-----------|-------------|
| `location_id` | `string (UUID)` | Si | ID de la location |
| `token` | `string` | Si | JWT access token |

> **Validacion adicional:** El backend verifica que la organizacion del token tenga acceso a la location (`user_can_access_location`).

### Snapshot inicial (al conectar)

Inmediatamente despues de conectar, el backend envia todos los trips activos de la location:

```json
{
  "type": "snapshot",
  "location_id": "location-uuid",
  "location_info": {
    "id": "location-uuid",
    "name": "SDF",
    "timezone": "America/New_York"
  },
  "trips": [
    {
      "id": "trip-uuid",
      "confirmation_number": "ABC123",
      "guest_name": "John Doe",
      "pick_up_date": "2026-02-23",
      "pick_up_time": "14:30:00",
      "pick_up_location": "SDF",
      "drop_off_location": "Hotel A",
      "pax": 2,
      "status": "pending",
      "..."
    }
  ]
}
```

**Accion frontend:**
- Usar `location_info.timezone` para agrupar trips por dia local.
- Comparar `pick_up_location` / `drop_off_location` con `location_info.name` para determinar inbound vs outbound.
- Reemplazar completamente el state de trips con el snapshot.

### Eventos en tiempo real

#### `trips_batch` — Lote de actualizaciones de trips

```json
{
  "type": "trips_batch",
  "location_id": "location-uuid",
  "events": [
    {
      "trip_id": "trip-uuid-1",
      "event_type": "created",
      "trip": { "...trip completo..." }
    },
    {
      "trip_id": "trip-uuid-2",
      "event_type": "updated",
      "trip": { "...trip completo..." }
    },
    {
      "trip_id": "trip-uuid-3",
      "event_type": "deleted",
      "trip": null
    }
  ]
}
```

**Valores posibles de `event_type`:** `"created"`, `"updated"`, `"deleted"`, `"db_update"`

**Accion frontend:**
```typescript
function handleTripsBatch(events: TripEvent[]) {
  for (const event of events) {
    switch (event.event_type) {
      case "created":
        addTrip(event.trip);
        break;
      case "updated":
      case "db_update":
        updateTrip(event.trip_id, event.trip);
        break;
      case "deleted":
        removeTrip(event.trip_id);
        break;
    }
  }
}
```

#### `step_applied` — Filtro aplicado

```json
{
  "type": "step_applied",
  "location_id": "location-uuid",
  "filter_type": "reduce",
  "..."
}
```

#### `step_reverted` — Filtro revertido

```json
{
  "type": "step_reverted",
  "location_id": "location-uuid",
  "filter_type": "reduce",
  "..."
}
```

**Accion frontend:** Actualizar indicadores de filtros activos en la UI.

#### `location_delete_started`

```json
{
  "type": "location_delete_started",
  "location_id": "location-uuid",
  "message": "Location deletion in progress..."
}
```

**Accion frontend:** Mostrar loading/spinner, deshabilitar interacciones.

#### `location_deleted`

```json
{
  "type": "location_deleted",
  "location_id": "location-uuid",
  "message": "Location has been deleted"
}
```

**Accion frontend:** Cerrar la vista de la location, redirigir al dashboard principal.

### Acciones que puede enviar el cliente

#### `subscribe`

```json
{ "action": "subscribe" }
```

Respuesta:
```json
{ "type": "subscribed", "location_id": "location-uuid" }
```

#### `unsubscribe`

```json
{ "action": "unsubscribe" }
```

Respuesta:
```json
{ "type": "unsubscribed", "location_id": "location-uuid" }
```

### Ejemplo de implementacion

```typescript
function useTripsWebSocket(locationId: string, token: string) {
  const [trips, setTrips] = useState<Trip[]>([]);
  const [locationInfo, setLocationInfo] = useState<LocationInfo | null>(null);

  useEffect(() => {
    const url = `wss://${BACKEND_URL}/ws/trips?location_id=${locationId}&token=${token}`;
    const ws = new WebSocket(url);

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case "snapshot":
          setTrips(data.trips);
          setLocationInfo(data.location_info);
          break;

        case "trips_batch":
          setTrips((prev) => applyBatchEvents(prev, data.events));
          break;

        case "step_applied":
        case "step_reverted":
          // Actualizar estado de filtros
          break;

        case "location_delete_started":
          showLoadingOverlay("Location being deleted...");
          break;

        case "location_deleted":
          navigateTo("/dashboard");
          showToast("Location deleted");
          break;
      }
    };

    return () => ws.close();
  }, [locationId, token]);

  return { trips, locationInfo };
}
```

---

## WS 3 — Ubicacion de Drivers (`/ws/driver-locations`)

Canal para visualizar la ubicacion en tiempo real de los drivers en un mapa. El manager recibe un snapshot inicial y luego actualizaciones incrementales.

### Conexion

```
wss://{BACKEND_URL}/ws/driver-locations?token={JWT}
wss://{BACKEND_URL}/ws/driver-locations?token={JWT}&location_id={LOCATION_ID}
```

| Parametro | Tipo | Requerido | Descripcion |
|-----------|------|-----------|-------------|
| `token` | `string` | Si | JWT access token |
| `location_id` | `string (UUID)` | No | Filtrar drivers por location. Si se omite, recibe **todos** los drivers de la organizacion |

> **Nota sobre el filtro:** El `location_id` se aplica **por conexion**. Si un manager conecta sin `location_id`, recibe updates de todos los drivers. Si conecta con `location_id=abc`, solo recibe updates de drivers asignados a esa location.

### Snapshot inicial (al conectar)

```json
{
  "type": "snapshot",
  "drivers": [
    {
      "driver_id": "driver-uuid-1",
      "first_name": "Carlos",
      "last_name": "Lopez",
      "location_id": "location-uuid",
      "lat": 38.1744,
      "lng": -85.7361,
      "updated_at": "2026-02-23T15:30:00+00:00"
    },
    {
      "driver_id": "driver-uuid-2",
      "first_name": "Maria",
      "last_name": "Garcia",
      "location_id": "location-uuid",
      "lat": 38.1780,
      "lng": -85.7400,
      "updated_at": "2026-02-23T15:28:00+00:00"
    }
  ]
}
```

**Accion frontend:** Renderizar todos los marcadores en el mapa.

> **Nota:** Si no hay drivers conectados, `drivers` sera un array vacio `[]`.

### Eventos en tiempo real

#### `location_update` — Actualizacion de posicion de un driver

```json
{
  "type": "location_update",
  "driver_id": "driver-uuid-1",
  "first_name": "Carlos",
  "last_name": "Lopez",
  "location_id": "location-uuid",
  "lat": 38.1750,
  "lng": -85.7365,
  "updated_at": "2026-02-23T15:31:00+00:00"
}
```

**Accion frontend:** Actualizar la posicion del marcador del driver en el mapa. Si el `driver_id` no existe en el state, agregarlo como nuevo marcador.

### Ejemplo de implementacion

```typescript
interface DriverLocation {
  driver_id: string;
  first_name: string;
  last_name: string;
  location_id: string;
  lat: number;
  lng: number;
  updated_at: string;
}

function useDriverLocations(token: string, locationId?: string) {
  const [drivers, setDrivers] = useState<Map<string, DriverLocation>>(new Map());

  useEffect(() => {
    let url = `wss://${BACKEND_URL}/ws/driver-locations?token=${token}`;
    if (locationId) {
      url += `&location_id=${locationId}`;
    }

    const ws = new WebSocket(url);

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case "snapshot":
          // Cargar todos los drivers iniciales
          const map = new Map<string, DriverLocation>();
          for (const driver of data.drivers) {
            map.set(driver.driver_id, driver);
          }
          setDrivers(map);
          break;

        case "location_update":
          // Actualizar posicion de un driver
          setDrivers((prev) => {
            const next = new Map(prev);
            next.set(data.driver_id, {
              driver_id: data.driver_id,
              first_name: data.first_name,
              last_name: data.last_name,
              location_id: data.location_id,
              lat: data.lat,
              lng: data.lng,
              updated_at: data.updated_at,
            });
            return next;
          });
          break;

        case "pong":
          break;

        case "error":
          if (data.code === 401) {
            refreshTokenAndReconnect();
          }
          break;
      }
    };

    return () => ws.close();
  }, [token, locationId]);

  return drivers;
}
```

### Deteccion de drivers desconectados

El backend **elimina** la ubicacion del driver de Redis al desconectarse, pero **no envia un evento de desconexion** al manager. Para detectar drivers inactivos en el frontend:

```typescript
// Marcar como inactivo si no se recibe update en X minutos
const STALE_THRESHOLD_MS = 5 * 60 * 1000; // 5 minutos

function isDriverStale(driver: DriverLocation): boolean {
  const lastUpdate = new Date(driver.updated_at).getTime();
  return Date.now() - lastUpdate > STALE_THRESHOLD_MS;
}
```

---

## Keep-Alive (Ping/Pong)

Todos los WebSockets requieren **ping periodico con token** para mantener la conexion viva y validar que el JWT sigue vigente.

### Formato

```json
// Cliente → Servidor
{ "action": "ping", "token": "eyJ...current_access_token" }

// Servidor → Cliente (exito)
{ "type": "pong" }

// Servidor → Cliente (token expirado)
{ "type": "error", "code": 401, "detail": "Invalid or expired token" }
// Seguido de close(code=1008)
```

> **Importante:** El campo `token` en el ping debe ser el **token actual** (post-refresh si aplica). Si el token expiro, el backend cierra la conexion.

### Implementacion recomendada

```typescript
class WebSocketKeepAlive {
  private ws: WebSocket;
  private interval: ReturnType<typeof setInterval> | null = null;
  private getToken: () => string; // Funcion que retorna el token actual

  constructor(ws: WebSocket, getToken: () => string) {
    this.ws = ws;
    this.getToken = getToken;
  }

  start(intervalMs: number = 30000) {
    this.interval = setInterval(() => {
      if (this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({
          action: "ping",
          token: this.getToken(), // Siempre enviar el token mas reciente
        }));
      }
    }, intervalMs);
  }

  stop() {
    if (this.interval) {
      clearInterval(this.interval);
      this.interval = null;
    }
  }
}
```

### Intervalo recomendado

| Situacion | Intervalo |
|-----------|-----------|
| Pestaña activa | 30 segundos |
| Pestaña en background | 60 segundos |
| Mobile (bateria) | 45 segundos |

---

## Reconexion y Manejo de Errores

### Codigos de cierre

| Codigo | Significado | Accion frontend |
|--------|------------|-----------------|
| `1000` | Cierre normal | No reconectar (cierre intencional) |
| `1001` | Going away | Reconectar con backoff |
| `1006` | Cierre anormal (red) | Reconectar inmediatamente |
| `1008` | Policy violation (auth) | **Refrescar token** y luego reconectar |
| `1011` | Error interno del servidor | Reconectar con backoff |

### Estrategia de reconexion con exponential backoff

```typescript
class ReconnectingWebSocket {
  private url: string;
  private ws: WebSocket | null = null;
  private reconnectAttempt = 0;
  private maxAttempts = 10;
  private baseDelay = 1000; // 1 segundo
  private maxDelay = 30000; // 30 segundos
  private onMessage: (data: any) => void;
  private getToken: () => Promise<string>;

  constructor(
    baseUrl: string,
    params: Record<string, string>,
    getToken: () => Promise<string>,
    onMessage: (data: any) => void,
  ) {
    this.getToken = getToken;
    this.onMessage = onMessage;
    this.url = baseUrl; // Se reconstruye en connect()
    this.connect(baseUrl, params);
  }

  private async connect(baseUrl: string, params: Record<string, string>) {
    const token = await this.getToken();
    const searchParams = new URLSearchParams({ ...params, token });
    const url = `${baseUrl}?${searchParams}`;

    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.reconnectAttempt = 0; // Reset en conexion exitosa
    };

    this.ws.onmessage = (event) => {
      this.onMessage(JSON.parse(event.data));
    };

    this.ws.onclose = (event) => {
      if (event.code === 1000) return; // Cierre intencional

      if (event.code === 1008) {
        // Token invalido — refrescar antes de reconectar
        this.refreshAndReconnect(baseUrl, params);
        return;
      }

      this.scheduleReconnect(baseUrl, params);
    };
  }

  private scheduleReconnect(baseUrl: string, params: Record<string, string>) {
    if (this.reconnectAttempt >= this.maxAttempts) {
      console.error("Max reconnection attempts reached");
      return;
    }

    const delay = Math.min(
      this.baseDelay * Math.pow(2, this.reconnectAttempt),
      this.maxDelay
    );
    this.reconnectAttempt++;

    setTimeout(() => this.connect(baseUrl, params), delay);
  }

  private async refreshAndReconnect(
    baseUrl: string,
    params: Record<string, string>,
  ) {
    try {
      await refreshAccessToken(); // Tu logica de refresh token
      this.connect(baseUrl, params);
    } catch {
      // Si el refresh falla, redirigir a login
      redirectToLogin();
    }
  }

  close() {
    this.ws?.close(1000);
  }
}
```

---

## Referencia Rapida de Mensajes

### Mensajes que el manager RECIBE (Server → Client)

| WebSocket | `type` | Descripcion |
|-----------|--------|-------------|
| `/ws/org` | `connected` | Confirmacion de conexion |
| `/ws/org` | `location_deleted` | Location eliminada de la org |
| `/ws/org` | `billing_event` | Evento de facturacion (payment_failed, payment_recovered, subscription_canceled) |
| `/ws/trips` | `snapshot` | Todos los trips de una location (al conectar) |
| `/ws/trips` | `trips_batch` | Lote de cambios en trips |
| `/ws/trips` | `step_applied` | Filtro aplicado |
| `/ws/trips` | `step_reverted` | Filtro revertido |
| `/ws/trips` | `location_delete_started` | Location en proceso de eliminacion |
| `/ws/trips` | `location_deleted` | Location eliminada |
| `/ws/trips` | `subscribed` | Confirmacion de suscripcion |
| `/ws/trips` | `unsubscribed` | Confirmacion de desuscripcion |
| `/ws/driver-locations` | `snapshot` | Todos los drivers con ubicacion (al conectar) |
| `/ws/driver-locations` | `location_update` | Actualizacion de posicion de un driver |
| **Todos** | `pong` | Respuesta a ping |
| **Todos** | `error` | Error (ver `code` y `detail`) |

### Mensajes que el manager ENVIA (Client → Server)

| WebSocket | `action` | Payload | Descripcion |
|-----------|----------|---------|-------------|
| **Todos** | `ping` | `{ "action": "ping", "token": "eyJ..." }` | Keep-alive con validacion de token |
| `/ws/trips` | `subscribe` | `{ "action": "subscribe" }` | Suscribirse a la location |
| `/ws/trips` | `unsubscribe` | `{ "action": "unsubscribe" }` | Desuscribirse de la location |

---

## Notas Importantes

1. **Un WebSocket por proposito:** No mezclar canales. Conectar `/ws/org` una vez al iniciar la app, `/ws/trips` al abrir cada location, y `/ws/driver-locations` al abrir el mapa.

2. **Token en query param:** A diferencia de las peticiones HTTP que usan `Authorization: Bearer`, los WebSockets reciben el token como query parameter `?token=`.

3. **El snapshot es la fuente de verdad:** Al conectar a `/ws/trips` o `/ws/driver-locations`, el snapshot reemplaza cualquier dato local. No hacer merge con datos previos.

4. **Billing events son exclusivos para managers:** El backend filtra automaticamente; los drivers conectados a `/ws/org` no reciben `billing_event`.

5. **El `location_id` en `/ws/driver-locations` es opcional:** Sin el, recibes drivers de **toda** la organizacion. Utiles para vistas de mapa global vs. mapa por location.

6. **Limpiar al desmontar:** Siempre cerrar el WebSocket con `ws.close(1000)` al desmontar el componente para liberar recursos en el backend.
