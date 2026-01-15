# Frontend: Manejo del evento `location_deleted`

## Resumen

Cuando un usuario (User A) elimina una location, todos los demás usuarios conectados (User B, C, etc.) deben:
1. Recibir una notificación
2. Ver la tabla/vista desaparecer
3. Ser redirigidos a la vista "no location"

El **backend ya envía el evento**. El **frontend debe implementar el handler**.

---

## Eventos WebSocket

### 1. `location_delete_started`

Se envía **antes** de eliminar. Útil para mostrar un loading/spinner.

```json
{
  "type": "location_delete_started",
  "location_id": "e79e27ed-d648-4d9b-8a7c-94ac2cc52c49",
  "location_name": "SDF",
  "trips_count": 150,
  "hotels_count": 5
}
```

### 2. `location_deleted`

Se envía **después** de eliminar. Este es el evento principal para actualizar la UI.

```json
{
  "type": "location_deleted",
  "location_id": "e79e27ed-d648-4d9b-8a7c-94ac2cc52c49",
  "location_name": "SDF",
  "trips_deleted": 150,
  "hotels_deleted": 5,
  "message": "Location SDF deleted",
  "detail": "150 trips and 5 hotels also deleted"
}
```

---

## Implementación Frontend

### React + TypeScript

```typescript
// types/websocket.ts
interface LocationDeleteStartedEvent {
  type: "location_delete_started";
  location_id: string;
  location_name: string;
  trips_count: number;
  hotels_count: number;
}

interface LocationDeletedEvent {
  type: "location_deleted";
  location_id: string;
  location_name: string;
  trips_deleted: number;
  hotels_deleted: number;
  message: string;
  detail: string;
}

type WebSocketEvent =
  | LocationDeleteStartedEvent
  | LocationDeletedEvent
  | TripsBatchEvent
  | SnapshotEvent;
```

### Hook de WebSocket

```typescript
// hooks/useTripsWebSocket.ts
import { useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLocationStore } from '@/stores/locationStore';
import { useNotification } from '@/hooks/useNotification';

export function useTripsWebSocket(locationId: string | null) {
  const navigate = useNavigate();
  const { showNotification } = useNotification();
  const {
    removeLocation,
    currentLocationId,
    setCurrentLocation
  } = useLocationStore();

  const handleMessage = useCallback((event: MessageEvent) => {
    const data = JSON.parse(event.data);

    switch (data.type) {
      case "location_delete_started":
        // Opcional: mostrar loading o mensaje informativo
        showNotification({
          type: "info",
          title: "Eliminando location...",
          message: `${data.location_name} está siendo eliminada`,
          duration: 3000
        });
        break;

      case "location_deleted":
        // 1. Mostrar notificación
        showNotification({
          type: "warning",
          title: "Location eliminada",
          message: `${data.location_name} fue eliminada por otro usuario`,
          description: data.detail,
          duration: 5000
        });

        // 2. Remover location del estado/store
        removeLocation(data.location_id);

        // 3. Si el usuario estaba viendo esta location, redirigir
        if (currentLocationId === data.location_id) {
          setCurrentLocation(null);
          navigate('/locations', {
            state: {
              message: `La location ${data.location_name} fue eliminada`
            }
          });
        }
        break;

      case "trips_batch":
        // ... manejar batch de trips
        break;

      case "snapshot":
        // ... manejar snapshot inicial
        break;
    }
  }, [currentLocationId, navigate, removeLocation, setCurrentLocation, showNotification]);

  useEffect(() => {
    if (!locationId) return;

    const token = getAuthToken();
    const ws = new WebSocket(
      `wss://api.example.com/ws/trips?location_id=${locationId}&token=${token}`
    );

    ws.onmessage = handleMessage;

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    return () => {
      ws.close();
    };
  }, [locationId, handleMessage]);
}
```

### Store (Zustand ejemplo)

```typescript
// stores/locationStore.ts
import { create } from 'zustand';

interface Location {
  id: string;
  name: string;
  // ... otros campos
}

interface LocationStore {
  locations: Location[];
  currentLocationId: string | null;

  setLocations: (locations: Location[]) => void;
  removeLocation: (locationId: string) => void;
  setCurrentLocation: (locationId: string | null) => void;
}

export const useLocationStore = create<LocationStore>((set, get) => ({
  locations: [],
  currentLocationId: null,

  setLocations: (locations) => set({ locations }),

  removeLocation: (locationId) => set((state) => ({
    locations: state.locations.filter(loc => loc.id !== locationId),
    // Si la location actual fue eliminada, limpiar
    currentLocationId: state.currentLocationId === locationId
      ? null
      : state.currentLocationId
  })),

  setCurrentLocation: (locationId) => set({ currentLocationId: locationId })
}));
```

### Componente de Vista

```tsx
// pages/LocationView.tsx
import { useEffect } from 'react';
import { useParams, Navigate } from 'react-router-dom';
import { useLocationStore } from '@/stores/locationStore';
import { useTripsWebSocket } from '@/hooks/useTripsWebSocket';
import { TripsTable } from '@/components/TripsTable';
import { NoLocationView } from '@/components/NoLocationView';

export function LocationView() {
  const { locationId } = useParams<{ locationId: string }>();
  const { locations, currentLocationId } = useLocationStore();

  // Conectar al WebSocket
  useTripsWebSocket(locationId ?? null);

  // Si no hay locationId o fue eliminada, mostrar vista vacía
  const locationExists = locations.some(loc => loc.id === locationId);

  if (!locationId || !locationExists) {
    return <NoLocationView />;
  }

  return (
    <div>
      <TripsTable locationId={locationId} />
    </div>
  );
}
```

### Componente NoLocationView

```tsx
// components/NoLocationView.tsx
import { useNavigate } from 'react-router-dom';

export function NoLocationView() {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col items-center justify-center h-full p-8">
      <div className="text-center">
        <h2 className="text-2xl font-semibold text-gray-700 mb-4">
          No hay location seleccionada
        </h2>
        <p className="text-gray-500 mb-6">
          Selecciona una location del menú o crea una nueva.
        </p>
        <button
          onClick={() => navigate('/locations')}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          Ver locations
        </button>
      </div>
    </div>
  );
}
```

---

## Flujo Completo

```
┌─────────────────────────────────────────────────────────────────┐
│                         User A                                   │
│                    (elimina location)                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Backend                                  │
│  DELETE /v1/locations/{id}                                       │
│    1. Publica "location_delete_started" → Redis                 │
│    2. Elimina trips, hotels, location                           │
│    3. Publica "location_deleted" → Redis                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Redis Pub/Sub                               │
│  Canales: org:{org_id} + loc:{location_id}                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    WebSocket Manager                             │
│  ws_manager.py escucha y reenvía a todos los clientes           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         User B                                   │
│  Frontend recibe evento:                                         │
│    1. Muestra notificación "Location eliminada"                 │
│    2. Remueve location del store                                │
│    3. Redirige a /locations o muestra NoLocationView            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Checklist de Implementación Frontend

- [ ] Agregar tipos TypeScript para `location_delete_started` y `location_deleted`
- [ ] Modificar handler de WebSocket para procesar estos eventos
- [ ] Implementar `removeLocation` en el store
- [ ] Agregar lógica de redirección cuando `currentLocationId` es eliminado
- [ ] Crear componente `NoLocationView`
- [ ] Agregar notificaciones (toast/alert) para informar al usuario
- [ ] Probar con múltiples usuarios en diferentes browsers

---

## Testing

### Escenario de prueba:

1. User A y User B abren la misma location en diferentes browsers
2. Ambos ven la tabla de trips
3. User A elimina la location
4. **Resultado esperado en User B:**
   - Recibe notificación "Location SDF fue eliminada por otro usuario"
   - La tabla desaparece
   - Se muestra vista "No hay location seleccionada"
   - NO necesita hacer F5

---

## Notas Importantes

1. **El backend ya envía los eventos** - No se requieren cambios en el backend
2. **Ambos WebSockets reciben el evento** - `/ws/trips` y `/ws/org`
3. **El frontend DEBE implementar el handler** - Sin esto, los eventos se ignoran
4. **Limpiar el estado local** - Es crucial remover la location del store para evitar errores 404

---

## Buenas Prácticas

### 1. Manejo de Estado Consistente

```typescript
// MALO: Manejar el evento sin actualizar el store
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === "location_deleted") {
    // Solo mostrar notificación sin limpiar estado
    toast.warning("Location eliminada");
    // El usuario sigue viendo datos obsoletos
  }
};

// BUENO: Actualizar store ANTES de navegar
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === "location_deleted") {
    // 1. Primero limpiar el estado
    store.removeLocation(data.location_id);
    store.clearTripsForLocation(data.location_id);

    // 2. Luego mostrar notificación
    toast.warning(`${data.location_name} eliminada`);

    // 3. Finalmente navegar
    if (currentLocationId === data.location_id) {
      navigate('/locations');
    }
  }
};
```

### 2. Evitar Race Conditions

```typescript
// MALO: No verificar si la location aún existe antes de hacer fetch
useEffect(() => {
  fetchTrips(locationId); // Puede fallar si location fue eliminada
}, [locationId]);

// BUENO: Verificar existencia antes de fetch
useEffect(() => {
  const locationExists = locations.some(loc => loc.id === locationId);
  if (!locationExists) {
    navigate('/locations');
    return;
  }
  fetchTrips(locationId);
}, [locationId, locations]);
```

### 3. Debounce de Notificaciones

Si se eliminan múltiples locations rápidamente, evitar spam de notificaciones:

```typescript
// hooks/useLocationDeletedHandler.ts
import { useRef, useCallback } from 'react';
import debounce from 'lodash/debounce';

export function useLocationDeletedHandler() {
  const deletedLocationsRef = useRef<string[]>([]);

  const showBatchNotification = useMemo(
    () => debounce(() => {
      const count = deletedLocationsRef.current.length;
      if (count === 1) {
        toast.warning(`Location eliminada`);
      } else {
        toast.warning(`${count} locations eliminadas`);
      }
      deletedLocationsRef.current = [];
    }, 500),
    []
  );

  const handleLocationDeleted = useCallback((event: LocationDeletedEvent) => {
    deletedLocationsRef.current.push(event.location_id);
    showBatchNotification();
  }, [showBatchNotification]);

  return { handleLocationDeleted };
}
```

### 4. Reconexión Automática del WebSocket

```typescript
// hooks/useRobustWebSocket.ts
export function useRobustWebSocket(url: string, handlers: WebSocketHandlers) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number>();
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 5;

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      reconnectAttempts.current = 0;
      handlers.onConnect?.();
    };

    ws.onmessage = handlers.onMessage;

    ws.onclose = (event) => {
      // Si el cierre fue por location_deleted (code 1000), no reconectar
      if (event.code === 1000 && event.reason === 'location_deleted') {
        return;
      }

      // Reconexión con backoff exponencial
      if (reconnectAttempts.current < maxReconnectAttempts) {
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
        reconnectTimeoutRef.current = window.setTimeout(() => {
          reconnectAttempts.current++;
          connect();
        }, delay);
      }
    };

    ws.onerror = handlers.onError;
  }, [url, handlers]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimeoutRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return wsRef;
}
```

### 5. Optimistic UI vs Confirmación

```typescript
// Opción A: UI Optimista (recomendado para UX fluida)
// El usuario que elimina ve el cambio inmediatamente
const handleDeleteLocation = async (locationId: string) => {
  // Optimistic update
  store.removeLocation(locationId);
  navigate('/locations');

  try {
    await api.delete(`/v1/locations/${locationId}`);
    toast.success('Location eliminada');
  } catch (error) {
    // Rollback si falla
    store.addLocation(previousLocation);
    toast.error('Error al eliminar');
  }
};

// Opción B: Esperar confirmación (más seguro)
const handleDeleteLocation = async (locationId: string) => {
  setIsDeleting(true);
  try {
    await api.delete(`/v1/locations/${locationId}`);
    // El WebSocket notificará a todos (incluido el que eliminó)
    // El handler de location_deleted actualizará el store
  } catch (error) {
    toast.error('Error al eliminar');
  } finally {
    setIsDeleting(false);
  }
};
```

### 6. Manejo de Errores 404 Post-Eliminación

```typescript
// api/trips.ts
export async function fetchTrips(locationId: string) {
  try {
    const response = await api.get(`/v1/locations/${locationId}/trips`);
    return response.data;
  } catch (error) {
    if (error.response?.status === 404) {
      // La location fue eliminada entre la navegación y el fetch
      store.removeLocation(locationId);
      toast.warning('Esta location ya no existe');
      router.navigate('/locations');
      return [];
    }
    throw error;
  }
}
```

### 7. Confirmación de Eliminación para el Usuario que Elimina

```tsx
// components/DeleteLocationModal.tsx
export function DeleteLocationModal({ location, onConfirm, onCancel }) {
  const [isDeleting, setIsDeleting] = useState(false);

  const handleConfirm = async () => {
    setIsDeleting(true);
    try {
      await onConfirm(location.id);
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <Modal>
      <Modal.Header>
        <h3>Eliminar Location</h3>
      </Modal.Header>
      <Modal.Body>
        <p className="text-red-600 font-semibold">
          Esta acción no se puede deshacer.
        </p>
        <p className="mt-2">
          Se eliminarán permanentemente:
        </p>
        <ul className="list-disc ml-6 mt-2">
          <li>La location <strong>{location.name}</strong></li>
          <li>Todos los trips asociados</li>
          <li>Todos los hotels asociados</li>
        </ul>
        <p className="mt-4 text-gray-600">
          Otros usuarios que estén viendo esta location serán notificados
          y redirigidos automáticamente.
        </p>
      </Modal.Body>
      <Modal.Footer>
        <button onClick={onCancel} disabled={isDeleting}>
          Cancelar
        </button>
        <button
          onClick={handleConfirm}
          disabled={isDeleting}
          className="bg-red-600 text-white"
        >
          {isDeleting ? 'Eliminando...' : 'Eliminar Location'}
        </button>
      </Modal.Footer>
    </Modal>
  );
}
```

### 8. Logging para Debugging

```typescript
// utils/websocketLogger.ts
const isDev = process.env.NODE_ENV === 'development';

export function logWebSocketEvent(event: WebSocketEvent) {
  if (!isDev) return;

  const timestamp = new Date().toISOString();
  const color = getEventColor(event.type);

  console.groupCollapsed(
    `%c[WS] ${event.type}`,
    `color: ${color}; font-weight: bold;`
  );
  console.log('Timestamp:', timestamp);
  console.log('Payload:', event);
  console.groupEnd();
}

function getEventColor(type: string): string {
  switch (type) {
    case 'location_deleted': return '#dc2626'; // red
    case 'location_delete_started': return '#f59e0b'; // amber
    case 'trips_batch': return '#3b82f6'; // blue
    case 'snapshot': return '#10b981'; // green
    default: return '#6b7280'; // gray
  }
}
```

---

## Edge Cases a Considerar

| Escenario | Solución |
|-----------|----------|
| Usuario cierra browser antes de recibir `location_deleted` | Al reabrir, el fetch a `/locations` retornará lista actualizada |
| WebSocket desconectado durante eliminación | Al reconectar, hacer fetch de locations para sincronizar |
| Usuario navega a location eliminada por URL directo | Mostrar 404 y redirigir |
| Múltiples locations eliminadas simultáneamente | Debounce de notificaciones + batch update del store |
| Usuario sin permisos intenta eliminar | Backend retorna 403, frontend muestra error |

---

## Estructura de Archivos Sugerida

```
src/
├── hooks/
│   ├── useTripsWebSocket.ts      # Hook principal de WebSocket
│   ├── useRobustWebSocket.ts     # Reconexión automática
│   └── useNotification.ts        # Sistema de notificaciones
├── stores/
│   ├── locationStore.ts          # Estado de locations
│   └── tripStore.ts              # Estado de trips
├── types/
│   └── websocket.ts              # Tipos de eventos WebSocket
├── components/
│   ├── NoLocationView.tsx        # Vista cuando no hay location
│   └── DeleteLocationModal.tsx   # Modal de confirmación
├── pages/
│   └── LocationView.tsx          # Vista principal de location
└── utils/
    └── websocketLogger.ts        # Logging de desarrollo
```

---

## Métricas y Monitoreo

Para producción, considera trackear:

```typescript
// analytics/websocket.ts
export function trackWebSocketEvent(event: WebSocketEvent) {
  analytics.track('websocket_event', {
    type: event.type,
    location_id: event.location_id,
    timestamp: Date.now()
  });
}

export function trackLocationDeletedReaction(data: {
  location_id: string;
  was_current_location: boolean;
  notification_shown: boolean;
  redirect_performed: boolean;
}) {
  analytics.track('location_deleted_reaction', data);
}
```
