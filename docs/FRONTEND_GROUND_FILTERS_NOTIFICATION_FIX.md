# Ground Filters: Fix de Notificaciones Batch

**Fecha:** 2026-01-21
**Tipo:** Fix de bug + Cambio en contrato de API
**Impacto:** Frontend debe actualizar handler de WebSocket

---

## 🐛 Problema Resuelto

### Antes (Bug)
```
Aplicar filtros a 150 trips →
Frontend recibe 150 notificaciones "update" individuales →
Usuario confundido con múltiples notificaciones que no tienen sentido
```

### Ahora (Fix)
```
Aplicar filtros a 150 trips →
Frontend recibe 1 notificación "filters_applied" batch →
Usuario ve mensaje claro: "✅ Filtros aplicados (150 trips)"
```

---

## 🔄 Cambios en el Backend

### Nuevo Evento WebSocket: `filters_applied`

Cuando se aplican filtros (`POST /filters/apply`), el backend ahora envía **UNA notificación batch** en lugar de N notificaciones individuales.

**Evento anterior (ya no se envía):**
```json
// Evento 1 de 150
{
  "event": "update",
  "schema": "trips",
  "table": "trips",
  "old": { "id": "...", "pick_up_time": "16:30:00", ... },
  "new": { "id": "...", "pick_up_time": "16:05:00", ... }
}

// Evento 2 de 150
{
  "event": "update",
  ...
}

// ... 148 eventos más ...
```

**Evento nuevo (enviado ahora):**
```json
{
  "type": "filters_applied",
  "location_id": "b88b3f47-5d97-4854-9590-b32da5f2efef",
  "airline": "WN",
  "batch_id": "550e8400-e29b-41d4-a716-446655440000",
  "filters": ["reduce", "combine"],
  "trips_affected": 150,
  "timestamp": "2026-01-21T20:00:00.000Z",
  "message": "Filters applied: reduce, combine (150 trips affected)"
}
```

### Nuevo Evento WebSocket: `filters_reverted`

Cuando se revierten filtros (`POST /filters/revert`):

```json
{
  "type": "filters_reverted",
  "location_id": "b88b3f47-5d97-4854-9590-b32da5f2efef",
  "airline": "WN",
  "batch_ids": ["batch-uuid-1", "batch-uuid-2"],
  "trips_reverted": 150,
  "timestamp": "2026-01-21T20:05:00.000Z",
  "message": "Filters reverted (150 trips restored)"
}
```

---

## 📋 Cambios Requeridos en Frontend

### 1. Agregar Tipos TypeScript

**Archivo:** `src/types/websocket.ts` (o similar)

```typescript
// Nuevo evento: Filters Applied
interface FiltersAppliedEvent {
  type: 'filters_applied';
  location_id: string;
  airline: string;
  batch_id: string;
  filters: string[];  // ["reduce", "combine", "expand"]
  trips_affected: number;
  timestamp: string;
  message: string;
}

// Nuevo evento: Filters Reverted
interface FiltersRevertedEvent {
  type: 'filters_reverted';
  location_id: string;
  airline: string;
  batch_ids: string[];
  trips_reverted: number;
  timestamp: string;
  message: string;
}

// Actualizar union type
type WebSocketMessage =
  | TripEventSnapshot
  | TripEventMessage
  | TripsBatchMessage
  | FiltersAppliedEvent    // ← AGREGAR
  | FiltersRevertedEvent   // ← AGREGAR
  | PongMessage
  | ErrorMessage;
```

### 2. Handler para `filters_applied`

**Archivo:** `src/hooks/use-websocket-trips.ts` (o donde manejes WS events)

```typescript
// Agregar caso en el switch de message.type

switch (message.type) {
  // ... casos existentes ...

  case 'filters_applied':
    handleFiltersApplied(message);
    break;

  case 'filters_reverted':
    handleFiltersReverted(message);
    break;
}
```

**Implementar handlers:**

```typescript
const handleFiltersApplied = useCallback((event: FiltersAppliedEvent) => {
  console.log('[WS] Filters applied:', event.filters.join(', '));
  console.log('[WS] Trips affected:', event.trips_affected);

  // Opción 1: Mostrar toast/notification
  toast.success(event.message, {
    duration: 5000,
    icon: '✅',
  });

  // Opción 2: Invalidar datos y mostrar banner de refresh
  setShowRefreshBanner(true);
  setRefreshMessage(event.message);

  // Opción 3: Refetch automático (solo si estás viendo la airline afectada)
  if (event.airline === selectedAirline) {
    refetchTrips();
  }

  // Opción 4: Actualizar desde snapshot de WS
  // (Los trips ya deberían estar actualizados en el snapshot porque
  // el trigger sigue funcionando normalmente después del apply)
  // NO hacer nada - los datos ya están actualizados vía snapshot

}, [selectedAirline, refetchTrips]);

const handleFiltersReverted = useCallback((event: FiltersRevertedEvent) => {
  console.log('[WS] Filters reverted:', event.trips_reverted);

  toast.info(event.message, {
    duration: 5000,
    icon: 'ℹ️',
  });

  // Refetch si estás viendo la airline afectada
  if (event.airline === selectedAirline) {
    refetchTrips();
  }
}, [selectedAirline, refetchTrips]);
```

### 3. Remover Lógica Antigua (Si Existe)

Si el frontend tenía lógica especial para manejar múltiples eventos "update" durante aplicación de filtros, **puede removerse**:

```typescript
// ❌ REMOVER (ya no es necesario)
// const [isApplyingFilters, setIsApplyingFilters] = useState(false);
// const [updateQueue, setUpdateQueue] = useState([]);

// useEffect(() => {
//   // Procesar queue después de que terminen los updates...
// }, [updateQueue, isApplyingFilters]);
```

---

## 🎯 Comportamiento Esperado

### Aplicar Filtros

1. **Usuario hace click en "Apply Filters"**
   ```typescript
   const applyFilters = async () => {
     const response = await api.post('/filters/apply', {
       reduce: { enabled: true, minutes_to_reduce: 20 }
     })
     // response.changes_applied = 150
   }
   ```

2. **Backend aplica cambios**
   - Modifica 150 trips en la BD
   - Trigger deshabilitado temporalmente
   - Commit sin notificaciones individuales

3. **Backend envía notificación batch**
   ```json
   { "type": "filters_applied", "trips_affected": 150, ... }
   ```

4. **Frontend recibe el evento**
   ```typescript
   case 'filters_applied':
     toast.success("✅ Filtros aplicados (150 trips)")
   ```

5. **UI actualizada**
   - Toast notification visible
   - Datos actualizados (via refetch o snapshot de WS)
   - Usuario ve feedback claro

### Revertir Filtros

Similar al apply:
```
POST /filters/revert → 1 notificación "filters_reverted" →
Toast: "Filtros revertidos (150 trips restaurados)"
```

---

## 🧪 Testing

### Test 1: Aplicar Filtros a 100 Trips

```typescript
test('recibe evento filters_applied en lugar de 100 updates', async () => {
  const onMessage = jest.fn()
  websocket.on('message', onMessage)

  // Aplicar filtros desde UI
  await applyFilters({
    reduce: { enabled: true, minutes_to_reduce: 20 }
  })

  // Esperar eventos
  await new Promise(resolve => setTimeout(resolve, 1000))

  // Verificar que se recibió solo 1 evento batch
  const filtersAppliedEvents = onMessage.mock.calls.filter(
    call => call[0].type === 'filters_applied'
  )

  expect(filtersAppliedEvents).toHaveLength(1)
  expect(filtersAppliedEvents[0][0].trips_affected).toBe(100)

  // Verificar que NO se recibieron 100 eventos "update" individuales
  const updateEvents = onMessage.mock.calls.filter(
    call => call[0].event === 'update'
  )

  // Debería haber 0 o muy pocos eventos update (no 100)
  expect(updateEvents.length).toBeLessThan(10)
})
```

### Test 2: Mostrar Toast Correcto

```typescript
test('muestra toast con mensaje correcto', async () => {
  render(<ScheduleDashboard />)

  // Simular evento filters_applied
  act(() => {
    mockWebSocket.emit('message', {
      type: 'filters_applied',
      filters: ['reduce', 'combine'],
      trips_affected: 85,
      message: 'Filters applied: reduce, combine (85 trips affected)'
    })
  })

  // Verificar que aparece toast
  await waitFor(() => {
    expect(screen.getByText(/Filters applied/i)).toBeInTheDocument()
    expect(screen.getByText(/85 trips/i)).toBeInTheDocument()
  })
})
```

---

## 📊 Impacto Esperado

| Métrica | Antes | Ahora |
|---------|-------|-------|
| Eventos WebSocket (apply 150 trips) | 150 eventos | 1 evento |
| Payload total | ~150KB | ~0.5KB |
| Updates de UI | 150 re-renders | 1 re-render |
| UX | Confusa (múltiples notif) | Clara (1 notif) |
| Performance | Degradada | Óptima |

---

## ⚠️ Notas Importantes

### 1. Permisos de Base de Datos

El backend ahora ejecuta:
```sql
ALTER TABLE trips.trips DISABLE TRIGGER ...
ALTER TABLE trips.trips ENABLE TRIGGER ...
```

**Requisito:** El usuario de BD (`gt360`) debe tener permisos para modificar triggers.

**Verificación:**
```sql
-- En PostgreSQL
GRANT ALTER ON TABLE trips.trips TO gt360;
```

### 2. WebSocket Snapshot

El WebSocket snapshot (`/ws/trips`) sigue funcionando normalmente y enviando todos los trips al conectar. Los eventos batch solo afectan las notificaciones de cambios durante operaciones de filtros.

### 3. Otros Endpoints No Afectados

Este fix SOLO afecta:
- `POST /filters/apply`
- `POST /filters/revert`

**NO afecta:**
- `POST /trips` (crear trip)
- `PATCH /trips/{id}` (editar trip)
- `DELETE /trips/{id}` (eliminar trip)

Estos siguen enviando notificaciones individuales via trigger (comportamiento correcto para operaciones de 1 trip).

---

## 🔗 Referencias

- [BUG_GROUND_FILTERS_MULTIPLE_NOTIFICATIONS.md](./BUG_GROUND_FILTERS_MULTIPLE_NOTIFICATIONS.md) - Análisis detallado del bug
- [WEBSOCKET_BATCH_FIX.md](./WEBSOCKET_BATCH_FIX.md) - Sistema de batching para uploads
- Commit que introdujo el bug: `0c2c3c9`
- Commit del fix: (próximo commit)

---

**Estado:** ✅ Fix implementado y desplegado
**Acción requerida:** Frontend debe agregar handler para `filters_applied`
**Prioridad:** 🟠 Media (el backend funciona, frontend debe adaptarse)
**Última actualización:** 2026-01-21
