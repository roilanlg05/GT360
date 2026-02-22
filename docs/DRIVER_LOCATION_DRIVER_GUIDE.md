# Driver Location WebSocket — Guía para Driver (Frontend/Mobile)

## Endpoint

```
WS /ws/driver-locations?token={access_token}
```

El rol se detecta automáticamente desde el JWT. Si el token pertenece a un driver, la conexión entra en modo envío.

---

## Conexión

```js
const token = "eyJ..."; // access token del driver
const ws = new WebSocket(`wss://api.gt360.app/ws/driver-locations?token=${token}`);
```

Si el token es inválido o el rol no es `driver`, el servidor cierra con código **1008**.

El servidor no envía mensaje de confirmación al conectar — la conexión está lista para enviar cuando `ws.readyState === WebSocket.OPEN`.

---

## Enviar posición

### Mensaje `location_update`

```json
{
  "action": "location_update",
  "lat": 38.123456,
  "lng": -85.456789
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `action` | string | Siempre `"location_update"` |
| `lat` | number | Latitud en grados decimales |
| `lng` | number | Longitud en grados decimales |

- Enviar cada **5 segundos** mientras el driver esté activo.
- Si `lat` o `lng` están ausentes, el servidor responde con un error y **no** cierra la conexión.
- No se espera ninguna respuesta del servidor al enviar una ubicación.

---

## Ping / keep-alive

Enviar periódicamente para mantener la conexión viva y re-validar el token antes de que expire.

```json
{ "action": "ping", "token": "eyJ..." }
```

El servidor responde con:
```json
{ "type": "pong" }
```

Si el token expiró, el servidor responde con error y cierra con código **1008** — en ese caso renovar el token y reconectar.

**Recomendación:** enviar ping cada 30 segundos con el access token más reciente.

---

## Mensajes que puede recibir el driver

### Mensajes básicos

```json
{ "type": "pong" }
{ "type": "error", "detail": "lat and lng required" }
{ "type": "error", "code": 401, "detail": "Invalid or expired token" }
{ "type": "error", "detail": "Unknown action" }
```

### Mensajes de ubicación de otros drivers (Driver-to-Driver Sharing)

El manager puede activar una opción que permite a los drivers ver la ubicación de otros drivers asignados a la **misma location** (mismo aeropuerto). Cuando esta opción está activa, el driver recibe mensajes adicionales:

#### `driver_snapshot` — al conectar (si sharing está activo)

Llega inmediatamente después de conectarse si el manager activó el sharing. Contiene la última posición conocida de todos los otros drivers de la misma location.

```json
{
  "type": "driver_snapshot",
  "drivers": [
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

- Solo incluye drivers de la **misma location** que el driver conectado.
- **No** incluye al propio driver (excluye self).
- `drivers` puede ser un array vacío `[]` si no hay otros drivers activos.

#### `location_update` — en tiempo real

Llega cada vez que **otro driver de la misma location** envía una nueva posición. Mismo formato que el manager recibe:

```json
{
  "type": "location_update",
  "driver_id": "e5f6g7h8-...",
  "first_name": "María",
  "last_name": "López",
  "lat": 38.201,
  "lng": -85.501,
  "location_id": "uuid-de-la-sede",
  "updated_at": "2026-02-21T10:30:10+00:00"
}
```

- Solo llega si el sharing está activo.
- Solo incluye drivers de la misma location.
- **Nunca** incluye la propia ubicación del driver (se excluye automáticamente).

#### `sharing_enabled` — el manager activó el sharing en vivo

Si el manager activa la opción mientras el driver ya está conectado, el driver recibe este mensaje con el snapshot de otros drivers:

```json
{
  "type": "sharing_enabled",
  "drivers": [
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

**Acción recomendada en el frontend:** tratar igual que `driver_snapshot` — poblar el mapa con los drivers recibidos y empezar a procesar `location_update`.

#### `sharing_disabled` — el manager desactivó el sharing en vivo

Si el manager desactiva la opción mientras el driver está conectado:

```json
{
  "type": "sharing_disabled"
}
```

**Acción recomendada en el frontend:** limpiar todos los markers de otros drivers del mapa. Dejar de procesar `location_update` de otros drivers hasta que se reciba `sharing_enabled` o se reconecte.

---

## Cómo manejar el sharing en el frontend

```js
// Estado del driver
const [otherDrivers, setOtherDrivers] = useState({});
const [sharingActive, setSharingActive] = useState(false);

ws.current.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  switch (msg.type) {
    case "driver_snapshot":
    case "sharing_enabled": {
      // Snapshot inicial o re-activación del sharing
      setSharingActive(true);
      const initial = {};
      for (const driver of msg.drivers) {
        initial[driver.driver_id] = driver;
      }
      setOtherDrivers(initial);
      break;
    }

    case "location_update": {
      // Actualización en tiempo real de otro driver
      if (sharingActive) {
        setOtherDrivers((prev) => ({
          ...prev,
          [msg.driver_id]: msg,
        }));
      }
      break;
    }

    case "sharing_disabled": {
      // Manager desactivó el sharing — limpiar mapa
      setSharingActive(false);
      setOtherDrivers({});
      break;
    }

    case "pong":
      break;

    case "error":
      if (msg.code === 401) {
        console.warn("[WS] Token expirado");
      }
      break;
  }
};
```

---

## Implementación de referencia (React Native)

```js
import { useEffect, useRef } from "react";

const WS_URL = "wss://dev-api.gt360.app/ws/driver-locations";
const LOCATION_INTERVAL_MS = 5_000;
const PING_INTERVAL_MS = 30_000;

export function useDriverLocationSender(token, getToken) {
  const ws = useRef(null);

  useEffect(() => {
    ws.current = new WebSocket(`${WS_URL}?token=${token}`);

    ws.current.onopen = () => {
      console.log("[WS] Conectado, iniciando envío de ubicación");
    };

    ws.current.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === "error" && msg.code === 401) {
        // Token expirado — el servidor cerrará la conexión
        console.warn("[WS] Token expirado");
      }
    };

    ws.current.onclose = (event) => {
      if (event.code === 1008) {
        console.error("[WS] Autenticación fallida, reconectar con nuevo token");
      }
    };

    // Enviar ubicación cada 5s
    const locationInterval = setInterval(async () => {
      if (ws.current?.readyState !== WebSocket.OPEN) return;

      try {
        // Obtener posición del dispositivo
        const position = await getCurrentPosition();
        ws.current.send(JSON.stringify({
          action: "location_update",
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        }));
      } catch (err) {
        console.warn("[WS] No se pudo obtener posición:", err);
      }
    }, LOCATION_INTERVAL_MS);

    // Ping cada 30s con token actualizado
    const pingInterval = setInterval(async () => {
      if (ws.current?.readyState !== WebSocket.OPEN) return;
      const currentToken = await getToken(); // función que retorna el token más fresco
      ws.current.send(JSON.stringify({ action: "ping", token: currentToken }));
    }, PING_INTERVAL_MS);

    return () => {
      clearInterval(locationInterval);
      clearInterval(pingInterval);
      ws.current?.close();
    };
  }, [token]);
}

// Helper — reemplazar con expo-location o react-native-geolocation
function getCurrentPosition() {
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(resolve, reject, {
      enableHighAccuracy: true,
      timeout: 4000,
    });
  });
}
```

---

## Flujo completo

```
App abre  →  ws.connect()
                │
                ▼
         readyState === OPEN
                │
                ├── Si sharing activo → recibe "driver_snapshot" con otros drivers
                │
         cada 5s: send location_update
                │
         cada 30s: send ping (con token fresco)
                │
                ├── Puede recibir "location_update" de otros drivers (si sharing activo)
                ├── Puede recibir "sharing_enabled" (manager activó sharing en vivo)
                ├── Puede recibir "sharing_disabled" (manager desactivó sharing en vivo)
                │
         App cierra / driver va offline
                │
         ws.close()  (la ubicación se elimina del servidor al desconectar)
```

> **Nota:** Al desconectarse, la posición del driver se elimina del servidor. Los otros drivers dejarán de ver a este driver.

---

## Cuándo conectar y desconectar

| Evento | Acción |
|--------|--------|
| Driver abre la app y está en turno | Conectar WS e iniciar envío |
| Driver pausa la app (background) | Mantener conexión si el OS lo permite; si no, reconectar al volver |
| Driver termina turno / se pone offline | Cerrar WS (`ws.close()`) |
| Token expirado (código 1008) | Renovar token con refresh endpoint y reconectar |
| Error de red | Reconectar con backoff exponencial |

---

## Códigos de cierre WebSocket

| Código | Significado |
|--------|-------------|
| 1008   | Token inválido, expirado, o rol incorrecto |
| 1011   | Error interno del servidor |
| 1000   | Cierre normal |
