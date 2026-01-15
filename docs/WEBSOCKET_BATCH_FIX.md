# WebSocket Batch Fix - Guía para Frontend Developer

**Fecha:** 2026-01-05
**Estado:** Implementado
**Versión:** 1.0

---

## Resumen de Cambios Backend

Se realizaron los siguientes cambios en el backend para resolver:
1. Error "Maximum update depth exceeded" al eliminar locations con muchos trips
2. Trips duplicados al subir archivos XLS
3. Warnings "too many requests"

| Cambio | Archivo | Impacto |
|--------|---------|---------|
| `SEND_WS_BATCH = True` | `ws_manager.py:19` | Nuevo tipo de mensaje `trips_batch` |
| Deduplicación de eventos | `trip_webhooks.py` | Menos eventos duplicados |
| Rate limit aumentado | `rate_limiter.py` | 1000 req/hora (antes 100) |

---

## Nuevo Tipo de Mensaje: `trips_batch`

### Antes (N mensajes individuales)
```json
{"type": "trip_event", "event_type": "delete", "trip_id": "uuid1", "trip": {...}}
{"type": "trip_event", "event_type": "delete", "trip_id": "uuid2", "trip": {...}}
{"type": "trip_event", "event_type": "delete", "trip_id": "uuid3", "trip": {...}}
... (688 mensajes separados al eliminar una location)
```

### Ahora (1 mensaje batch)
```json
{
  "type": "trips_batch",
  "location_id": "uuid-location",
  "events": [
    {"trip_id": "uuid1", "event_type": "delete", "location_id": "...", "trip": {...}},
    {"trip_id": "uuid2", "event_type": "delete", "location_id": "...", "trip": {...}},
    {"trip_id": "uuid3", "event_type": "delete", "location_id": "...", "trip": {...}},
    ... (688 eventos en UN solo mensaje)
  ]
}
```

---

## Cambios Requeridos en Frontend

### 1. Agregar Tipos TypeScript

**Archivo:** `src/lib/websocket/types.ts`

```typescript
// Evento individual dentro del batch
interface TripsBatchEvent {
  trip_id: string;
  event_type: 'insert' | 'update' | 'delete';
  location_id: string;
  trip: Trip;
}

// Mensaje batch completo
interface TripsBatchMessage {
  type: 'trips_batch';
  location_id: string;
  events: TripsBatchEvent[];
}

// Actualizar union type
type WebSocketMessage =
  | TripEventSnapshot
  | TripEventMessage
  | TripsBatchMessage  // <- AGREGAR
  | PongMessage
  | ErrorMessage;
```

### 2. Handler para `trips_batch`

**Archivo:** `src/hooks/use-websocket-trips.ts`

Agregar caso en el switch de `message.type`:

```typescript
case 'trips_batch':
  handleTripsBatch(message);
  break;
```

Nueva función:

```typescript
const handleTripsBatch = useCallback((message: TripsBatchMessage) => {
  const events = message.events || [];

  // Procesar TODO el batch en UNA sola actualización de estado
  setTrips((prevTrips) => {
    let newTrips = [...prevTrips];

    for (const event of events) {
      const { trip_id, event_type, trip } = event;

      switch (event_type) {
        case 'insert':
          // CRÍTICO: Verificar que no exista antes de agregar
          if (!newTrips.find(t => t.id === trip_id)) {
            newTrips.push(trip);
          }
          break;

        case 'update':
          newTrips = newTrips.map(t =>
            t.id === trip_id ? trip : t
          );
          break;

        case 'delete':
          newTrips = newTrips.filter(t => t.id !== trip_id);
          break;
      }
    }

    return newTrips;
  });
}, [setTrips]);
```

### 3. Verificar Duplicados en Insert

**CRÍTICO:** Tanto en `trip_event` como en `trips_batch`, verificar duplicados:

```typescript
// ❌ INCORRECTO - Puede causar duplicados
case 'insert':
  return [...prevTrips, event.trip];

// ✅ CORRECTO - Previene duplicados
case 'insert':
  if (!prevTrips.find(t => t.id === event.trip_id)) {
    return [...prevTrips, event.trip];
  }
  return prevTrips;
```

---

## Compatibilidad

El frontend debe manejar **AMBOS** tipos de mensajes:

| Operación | Tipo de Mensaje |
|-----------|-----------------|
| CRUD individual (crear/editar/eliminar 1 trip) | `trip_event` |
| Operaciones masivas (bulk insert, eliminar location) | `trips_batch` |

---

## Testing Checklist

- [ ] Manejar mensaje `trips_batch` además de `trip_event`
- [ ] Verificar duplicados en `insert` (prevTrips.find)
- [ ] Procesar batch de 100+ eventos sin error
- [ ] Eliminar location con muchos trips sin "Maximum update depth"
- [ ] Subir XLS sin ver trips duplicados en la tabla
- [ ] CRUD individual sigue funcionando normalmente

---

## Logs Esperados

### Correcto (con batch)
```
[WebSocket] Received: trips_batch with 688 events
[WebSocket] Processing batch: 688 delete events
[WebSocket] Batch processed successfully
```

### Incorrecto (sin batch - ya no debería pasar)
```
[WebSocket] Received: trip_event delete
[WebSocket] Received: trip_event delete
... (688 veces)
Error: Maximum update depth exceeded
```

---

## Troubleshooting

### Error: Maximum update depth exceeded
**Causa:** Frontend no maneja `trips_batch` y sigue recibiendo eventos individuales.
**Solución:** Verificar que el handler de `trips_batch` esté implementado.

### Error: Trips duplicados
**Causa:** Handler de `insert` no verifica si el trip ya existe.
**Solución:** Agregar `if (!prevTrips.find(t => t.id === trip_id))` antes de push.

### Error: WebSocket Max reconnection attempts
**Causa:** Backend reiniciándose o token expirado.
**Solución:** Verificar `docker compose ps` y logs del backend.

---

## Documentación Relacionada

| Documento | Descripción |
|-----------|-------------|
| [TIMELINE_WITH_TIMEZONE.md](TIMELINE_WITH_TIMEZONE.md) | Feature de Timeline con timezone |
| [UNIFIED_TRIPS_WEBSOCKET_PIPELINE.md](Docs_From_Frontend/UNIFIED_TRIPS_WEBSOCKET_PIPELINE.md) | Arquitectura WebSocket |
| Plan completo | `/home/backend/.claude/plans/sorted-knitting-codd.md` |

---

**Documento Creado:** 2026-01-05
