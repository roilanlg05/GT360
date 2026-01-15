# Unified Real-Time Trips Pipeline

**Fecha de implementación:** 2026-01-05
**Estado:** Completado

## Resumen

Se implementó un pipeline unificado de WebSocket para sincronización en tiempo real de trips entre todos los componentes de la aplicación (Table y Cards).

## Problema Anterior

```
┌─────────────────────────────────────┐
│   Schedule Dashboard (Table)         │
│   └─ useWebSocketTrips Hook #1       │  ← WebSocket Connection #1
│      └─ WebSocketTripsManager #1     │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│   Dashboard Home (Cards)             │
│   └─ useWebSocketTrips Hook #2       │  ← WebSocket Connection #2
│      └─ WebSocketTripsManager #2     │
└─────────────────────────────────────┘

⚠️ DOS conexiones WebSocket separadas al mismo endpoint
⚠️ DOS managers compitiendo por la misma location
⚠️ Potencial inconsistencia entre tabla y cards
⚠️ Notificaciones duplicadas cuando ambos componentes están activos
```

## Arquitectura Nueva

```
┌────────────────────────────────────────────┐
│        client-layout.tsx                   │
│  ┌──────────────────────────────────────┐  │
│  │ TripsWebSocketProvider (ÚNICO)       │  │
│  │  └─ useWebSocketTrips (1 conexión)   │  │
│  │    └─ Actualiza useTripsStore        │  │
│  │    └─ Muestra notificaciones         │  │
│  └──────────────────────────────────────┘  │
│                    ↓                        │
│  ┌──────────────────────────────────────┐  │
│  │ useTripsStore (ÚNICA FUENTE)         │  │
│  │  ├─ trips: Trip[]                    │  │
│  │  ├─ isConnected: boolean             │  │
│  │  └─ locationId: string               │  │
│  └──────────────────────────────────────┘  │
│              ↙           ↘                  │
│    ┌─────────────┐   ┌────────────┐        │
│    │ Table View  │   │ Cards View │        │
│    │ (schedule)  │   │ (home)     │        │
│    └─────────────┘   └────────────┘        │
└────────────────────────────────────────────┘

✓ UNA conexión WebSocket por locationId
✓ UN store como fuente de verdad
✓ Sincronización automática
✓ Notificaciones centralizadas (sin duplicados)
```

## Archivos Creados

### `src/providers/trips-websocket-provider.tsx`

Provider centralizado que maneja:

- **Conexión WebSocket única** para toda la aplicación
- **Actualización del store** en snapshot y eventos de trips
- **Notificaciones** via `showTripNotification()`
- **Detección de optimistic updates** para evitar notificaciones propias
- **Estado de conexión** expuesto via context

```typescript
interface TripsWebSocketContextValue {
  locationId: string | null
  isConnected: boolean
  connectionStatus: ConnectionStatus
  connectionState: ConnectionState
  error: string | null
  isInitialized: boolean
  setLocationId: (id: string | null) => void
  reconnect: () => void
  disconnect: () => void
}
```

**Uso:**

```typescript
import { useTripsWebSocket } from '@/providers/trips-websocket-provider'

function MyComponent() {
  const { isConnected, setLocationId, error } = useTripsWebSocket()

  useEffect(() => {
    setLocationId('location-uuid')
  }, [setLocationId])

  // Leer trips del store
  const trips = useTripsStore((state) => state.trips)
}
```

## Archivos Modificados

### `src/app/(main)/dashboard/client-layout.tsx`

- Agregado import de `TripsWebSocketProvider`
- Provider envuelve todos los children del dashboard

```tsx
return (
  <SidebarProvider defaultOpen={defaultOpen}>
    <OrgWebSocketListener />
    <TripsWebSocketProvider>
      <AppSidebar ... />
      <SidebarInset ...>
        {children}
      </SidebarInset>
    </TripsWebSocketProvider>
  </SidebarProvider>
)
```

### `src/app/(main)/dashboard/home/page.tsx`

**Antes:**
- Usaba `useWebSocketTrips` directamente (creaba conexión propia)
- Tenía `handleTripEvent` local para notificaciones y store

**Después:**
- Usa `useTripsWebSocket()` del provider
- Solo setea `locationId` cuando cambia
- Lee trips del store directamente

```typescript
// Shared WebSocket connection from provider
const {
  isConnected: wsConnected,
  isInitialized: wsInitialized,
  error: wsError,
  setLocationId,
} = useTripsWebSocket()

// Set location for WebSocket when it changes
useEffect(() => {
  if (currentLocationId && user) {
    setLocationId(currentLocationId)
  }
}, [currentLocationId, user, setLocationId])
```

### `src/app/(main)/dashboard/locations/[code]/[airline]/schedule-dashboard-client.tsx`

**Antes:**
- Usaba `useWebSocketTrips` directamente
- Tenía `handleTripEvent` para notificaciones, store y rowsData
- Manejaba su propia conexión WebSocket

**Después:**
- Usa `useTripsWebSocket()` del provider
- Suscripción al store para sincronizar `rowsData`
- Detección de cambios eficiente (insert/update/delete)

```typescript
// Shared WebSocket connection from provider
const {
  isConnected: wsConnected,
  isInitialized: wsInitialized,
  error: wsError,
  setLocationId,
  connectionState,
} = useTripsWebSocket()

// Subscribe to store trips changes and sync with local rowsData
const storeTrips = useTripsStore((state) => state.trips)

useEffect(() => {
  const prevTrips = prevTripsRef.current
  prevTripsRef.current = storeTrips

  // Detect deleted, added, updated trips
  // Update rowsData accordingly
}, [storeTrips])
```

## Flujo de Datos

### 1. Conexión WebSocket

```
Usuario navega a /dashboard/locations/SDF/WN
    ↓
schedule-dashboard-client.tsx
    ↓
setLocationId('uuid-de-location')
    ↓
TripsWebSocketProvider recibe nuevo locationId
    ↓
useWebSocketTrips crea conexión a wss://api.gt360.app/ws/trips?location_id=...
    ↓
Servidor envía snapshot inicial
    ↓
Provider llama setTrips(trips) en el store
```

### 2. Evento en Tiempo Real

```
Otro usuario edita un trip
    ↓
Servidor envía evento trip_event { type: 'update', trip_id, trip }
    ↓
TripsWebSocketProvider recibe evento
    ↓
Provider verifica si es optimistic update (propio)
    ↓
Si NO es propio:
  - Muestra toast via showTripNotification()
  - Actualiza store via updateTrip(trip_id, trip)
    ↓
schedule-dashboard-client detecta cambio en storeTrips
    ↓
Actualiza rowsData localmente
    ↓
Tabla se re-renderiza con datos actualizados
```

### 3. Acción del Usuario (Optimistic)

```
Usuario edita trip en la tabla
    ↓
schedule-dashboard-client.tsx
    ↓
markOptimistic(trip_id) // Marca como optimistic
    ↓
Llama API PUT /api/trips/{id}
    ↓
Servidor responde OK
    ↓
Servidor broadcast evento via WebSocket
    ↓
TripsWebSocketProvider recibe evento
    ↓
Provider verifica isOptimistic(trip_id) → TRUE
    ↓
Ignora notificación (el usuario ya sabe que editó)
    ↓
Store se actualiza (datos reales del servidor)
```

## Sincronización de rowsData

La tabla (`schedule-dashboard-client.tsx`) mantiene estado local `rowsData` porque:

1. **REST API es fuente de verdad para paginación** - La tabla carga trips paginados via REST
2. **WebSocket es para actualizaciones en tiempo real** - Solo para insert/update/delete incrementales

La sincronización funciona así:

```typescript
const storeTrips = useTripsStore((state) => state.trips)
const prevTripsRef = useRef<Trip[]>([])

useEffect(() => {
  const prevTrips = prevTripsRef.current
  prevTripsRef.current = storeTrips

  // Build lookup maps
  const prevMap = new Map(prevTrips.map(t => [t.id, t]))
  const currMap = new Map(storeTrips.map(t => [t.id, t]))

  // Detect deleted
  const deletedIds = [...prevMap.keys()].filter(id => !currMap.has(id))

  // Detect added
  const addedTrips = storeTrips.filter(t => !prevMap.has(t.id))

  // Detect updated (different reference)
  const updatedTrips = storeTrips.filter(t => {
    const prev = prevMap.get(t.id)
    return prev && prev !== t
  })

  // Apply changes to rowsData
  setRowsData(prev => {
    let next = prev
    // Remove deleted
    // Add new
    // Update existing
    return next
  })
}, [storeTrips])
```

## Testing

### Verificar Una Sola Conexión

1. Abrir DevTools → Network → Filtrar por WS
2. Navegar a `/dashboard/locations/SDF/WN`
3. Verificar que solo hay 1 conexión a `/ws/trips`
4. Navegar a `/dashboard/home`
5. Verificar que sigue siendo la MISMA conexión (no se crea nueva)

### Sincronización Table → Cards

1. Abrir `/dashboard/locations/SDF/WN` en pestaña A
2. Abrir `/dashboard/home` en pestaña B (mismo usuario)
3. En pestaña A: editar un trip
4. **Esperado en pestaña B:** Card se actualiza automáticamente

### Sincronización Multi-Dispositivo

1. Abrir app en dispositivo A
2. Abrir app en dispositivo B (mismo usuario)
3. En dispositivo A: agregar un trip
4. **Esperado en dispositivo B:**
   - Toast success: "Trip added"
   - Trip aparece en la lista

### Reconexión

1. Abrir app en location con trips
2. Desconectar red momentáneamente
3. **Esperado:** Banner "Reconnecting..."
4. Reconectar red
5. **Esperado:** Banner desaparece, datos sincronizados

## Notas Importantes

### Paginación REST

La tabla usa REST para paginación (`GET /api/trips?page=1&limit=50`). El WebSocket solo maneja actualizaciones incrementales. Esto es intencional para:

- Cargar grandes cantidades de datos eficientemente
- Mantener estado de paginación (página actual, total de páginas)
- El snapshot de WebSocket sirve como fallback si REST no ha cargado

### Multi-Location

El sistema solo soporta UNA location a la vez. Si el usuario navega a otra location:

1. `setLocationId(newLocationId)` es llamado
2. Provider desconecta de la location anterior
3. Provider conecta a la nueva location
4. Store se limpia y recibe nuevo snapshot

### Optimistic Updates

Para evitar notificaciones duplicadas cuando el usuario hace una acción:

1. Antes de llamar API: `markOptimistic(tripId)`
2. Cuando llega evento WebSocket: `isOptimistic(tripId)` → skip notification
3. El marker expira automáticamente después de 5 segundos

## Dependencias

- `useWebSocketTrips` hook - Maneja conexión WebSocket
- `useTripsStore` - Estado global de trips (Zustand)
- `showTripNotification` - Sistema de notificaciones
- `optimisticTracker` - Tracking de actualizaciones optimistas

## Archivos Relacionados

| Archivo | Propósito |
|---------|-----------|
| `src/providers/trips-websocket-provider.tsx` | Provider centralizado |
| `src/hooks/use-websocket-trips.ts` | Hook de WebSocket |
| `src/stores/trips/trips-store.ts` | Store de Zustand |
| `src/stores/trips/websocket-manager.ts` | Manager de conexión WebSocket |
| `src/lib/trips/notifications.ts` | Sistema de notificaciones |
| `src/lib/websocket/types.ts` | Tipos de eventos WebSocket |
