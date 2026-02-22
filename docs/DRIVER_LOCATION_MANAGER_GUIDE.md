# Driver Location WebSocket — Guía para Manager (Frontend)

## Endpoint

```
WS /ws/driver-locations?token={access_token}
WS /ws/driver-locations?token={access_token}&location_id={uuid}
```

El rol se detecta automáticamente desde el JWT. Si el token pertenece a un manager, la conexión entra en modo recepción.

---

## Conexión

```js
const token = "eyJ..."; // access token del manager
const ws = new WebSocket(`wss://api.gt360.app/ws/driver-locations?token=${token}`);
```

Con filtro por location (solo ver drivers de esa sede):
```js
const ws = new WebSocket(
  `wss://api.gt360.app/ws/driver-locations?token=${token}&location_id=${locationId}`
);
```

Si el token es inválido o el rol no es `manager`, el servidor cierra con código **1008**.

---

## Mensajes que recibe el manager

### 1. `snapshot` — al conectar

Llega inmediatamente después de conectarse. Contiene la última posición conocida de todos los drivers de la organización (o de la sede si usaste `location_id`).

```json
{
  "type": "snapshot",
  "drivers": [
    {
      "driver_id": "a1b2c3d4-...",
      "first_name": "Juan",
      "last_name": "Pérez",
      "lat": 38.123,
      "lng": -85.456,
      "location_id": "uuid-de-la-sede",
      "updated_at": "2026-02-21T10:30:00+00:00"
    },
    {
      "driver_id": "e5f6g7h8-...",
      "first_name": "María",
      "last_name": "López",
      "lat": 38.200,
      "lng": -85.500,
      "location_id": "uuid-de-la-sede",
      "updated_at": "2026-02-21T10:29:45+00:00"
    }
  ]
}
```

- `drivers` puede ser un array vacío `[]` si ningún driver ha enviado su posición aún.
- La posición de cada driver es la **última conocida**, independientemente de si está activo ahora o no.

### 2. `location_update` — en tiempo real

Llega cada vez que un driver envía una nueva posición. Actualiza un driver específico en el mapa.

```json
{
  "type": "location_update",
  "driver_id": "a1b2c3d4-...",
  "first_name": "Juan",
  "last_name": "Pérez",
  "lat": 38.124,
  "lng": -85.457,
  "location_id": "uuid-de-la-sede",
  "updated_at": "2026-02-21T10:30:05+00:00"
}
```

### 3. `pong` — respuesta al ping

```json
{ "type": "pong" }
```

### 4. `error`

```json
{ "type": "error", "detail": "..." }
{ "type": "error", "code": 401, "detail": "Invalid or expired token" }
```

---

## Mensajes que envía el manager

### Ping / keep-alive

Enviar periódicamente para mantener la conexión viva y re-validar el token.

```json
{ "action": "ping", "token": "eyJ..." }
```

El servidor responde con `{ "type": "pong" }`. Si el token expiró, cierra con código **1008**.

---

## Cómo detectar si un driver está activo

El backend **no elimina** posiciones cuando un driver se desconecta — conserva la última posición conocida. Para distinguir drivers activos de inactivos, compara `updated_at` con la hora actual en el frontend:

```js
function isDriverActive(updatedAt, thresholdSeconds = 30) {
  const lastSeen = new Date(updatedAt);
  const now = new Date();
  const diffSeconds = (now - lastSeen) / 1000;
  return diffSeconds <= thresholdSeconds;
}
```

Recomendación visual:
- `updated_at` < 30s → ícono verde (activo)
- `updated_at` entre 30s y 5min → ícono amarillo (sin señal reciente)
- `updated_at` > 5min → ícono gris (offline / última posición conocida)

---

## Implementación de referencia (React)

```jsx
import { useEffect, useRef, useState } from "react";

export function useDriverLocations(token, locationId = null) {
  const [drivers, setDrivers] = useState({});
  const ws = useRef(null);

  useEffect(() => {
    const url = locationId
      ? `wss://api.gt360.app/ws/driver-locations?token=${token}&location_id=${locationId}`
      : `wss://api.gt360.app/ws/driver-locations?token=${token}`;

    ws.current = new WebSocket(url);

    ws.current.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      if (msg.type === "snapshot") {
        // Cargar estado inicial — indexar por driver_id
        const initial = {};
        for (const driver of msg.drivers) {
          initial[driver.driver_id] = driver;
        }
        setDrivers(initial);
      }

      if (msg.type === "location_update") {
        // Actualizar un driver específico
        setDrivers((prev) => ({
          ...prev,
          [msg.driver_id]: msg,
        }));
      }
    };

    ws.current.onclose = (event) => {
      if (event.code === 1008) {
        // Token inválido — redirigir a login o renovar token
        console.error("Token inválido o expirado");
      }
    };

    // Ping cada 30s para mantener conexión viva
    const pingInterval = setInterval(() => {
      if (ws.current?.readyState === WebSocket.OPEN) {
        ws.current.send(JSON.stringify({ action: "ping", token }));
      }
    }, 30_000);

    return () => {
      clearInterval(pingInterval);
      ws.current?.close();
    };
  }, [token, locationId]);

  return drivers; // { [driver_id]: { driver_id, first_name, last_name, lat, lng, location_id, updated_at } }
}
```

---

## Comportamiento del filtro `location_id`

- **Sin `location_id`**: el manager recibe actualizaciones de **todos** los drivers de su organización.
- **Con `location_id`**: el manager solo recibe actualizaciones de drivers asignados a esa sede. El filtro aplica tanto al snapshot inicial como a los eventos en tiempo real.
- El filtro es fijo por conexión. Para cambiar de sede, cerrar la conexión y abrir una nueva.

---

## Driver-to-Driver Location Sharing (Configuración del Manager)

El manager puede activar/desactivar la visibilidad de ubicaciones entre drivers. Cuando está activo, los drivers de la **misma location** (mismo aeropuerto) pueden ver la posición GPS de los otros drivers en tiempo real.

### Consultar estado actual

```
GET /v1/organizations/{organization_id}/settings/driver-location-sharing
Authorization: Bearer {manager_token}
```

Respuesta:
```json
{
  "driver_location_sharing": false,
  "organization_id": "d4aa0fcc-..."
}
```

### Activar/Desactivar sharing

```
PATCH /v1/organizations/{organization_id}/settings/driver-location-sharing
Authorization: Bearer {manager_token}
Content-Type: application/json

{
  "driver_location_sharing": true
}
```

Respuesta:
```json
{
  "driver_location_sharing": true,
  "organization_id": "d4aa0fcc-..."
}
```

### Efecto inmediato

El cambio tiene efecto **inmediato** sobre todos los drivers conectados:

- **Al activar (`true`):** todos los drivers conectados reciben un mensaje WebSocket `sharing_enabled` con un snapshot de los otros drivers de su misma location. A partir de ese momento reciben `location_update` en tiempo real de los otros drivers.

- **Al desactivar (`false`):** todos los drivers conectados reciben un mensaje WebSocket `sharing_disabled`. El frontend del driver debe limpiar los markers de otros drivers del mapa. Los drivers dejan de recibir `location_update` de otros drivers inmediatamente.

### Reglas de visibilidad

| Regla | Descripción |
|-------|-------------|
| Misma location | Solo drivers asignados al mismo `location_id` se ven entre sí |
| Excluye self | Un driver nunca recibe su propia ubicación de vuelta |
| Por organización | El toggle aplica a toda la organización (todos las locations) |
| Sin location | Drivers sin `location_id` asignado no participan en el sharing |

### Implementación de referencia (Toggle en Settings)

```jsx
import { useState, useEffect } from "react";

export function DriverSharingToggle({ organizationId, token }) {
  const [sharing, setSharing] = useState(false);
  const [loading, setLoading] = useState(true);

  const API_URL = "https://dev-api.gt360.app";

  // Cargar estado actual
  useEffect(() => {
    fetch(`${API_URL}/v1/organizations/${organizationId}/settings/driver-location-sharing`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => res.json())
      .then((data) => {
        setSharing(data.driver_location_sharing);
        setLoading(false);
      });
  }, [organizationId]);

  // Toggle
  const handleToggle = async () => {
    const newValue = !sharing;
    setLoading(true);

    const res = await fetch(
      `${API_URL}/v1/organizations/${organizationId}/settings/driver-location-sharing`,
      {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ driver_location_sharing: newValue }),
      }
    );

    const data = await res.json();
    setSharing(data.driver_location_sharing);
    setLoading(false);
  };

  if (loading) return <span>Loading...</span>;

  return (
    <label>
      <input type="checkbox" checked={sharing} onChange={handleToggle} />
      Allow drivers to see each other's location
    </label>
  );
}
```

---

## Códigos de cierre WebSocket

| Código | Significado |
|--------|-------------|
| 1008   | Token inválido, expirado, o rol incorrecto |
| 1011   | Error interno del servidor |
| 1000   | Cierre normal |
