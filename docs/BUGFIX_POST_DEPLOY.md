# Bugfix Post-Deploy: PATCH Trip y DELETE Location

**Fecha:** 2026-01-04
**Severidad:** Alta
**Archivo modificado:** `features/trips/routes/trips_router.py`

---

## Resumen

Despues del deploy inicial se detectaron dos errores 500 en los endpoints:
1. `PATCH /v1/locations/{location_id}/trips/{trip_id}` - Error de sintaxis en Join
2. `DELETE /v1/locations/{location_id}` - Violacion de FK con tabla hotels

---

## Bug #1: PATCH Trip - Sintaxis Join Incorrecta

### Error en Logs
```
Unhandled error: SelectQuery.Join() takes 2 positional arguments but 3 were given
```

### Causa
La libreria `psqlmodel` usa una sintaxis de Join encadenada, no con multiples argumentos.

### Codigo Incorrecto (linea 477)
```python
sel_stmt = (
    Select(TripDB, Location)
    .Join(Location, TripDB.location_id == Location.id)  # INCORRECTO
    .Where((TripDB.id == uuid_id) & (TripDB.location_id == uuid_location_id))
)
```

### Codigo Corregido
```python
sel_stmt = (
    Select(TripDB, Location)
    .Join(Location).On(TripDB.location_id == Location.id)  # CORRECTO
    .Where((TripDB.id == uuid_id) & (TripDB.location_id == uuid_location_id))
)
```

### Explicacion
En `psqlmodel`, el metodo `Join()` solo acepta el modelo como argumento. La condicion de join se especifica con el metodo encadenado `.On()`:

```python
# Sintaxis psqlmodel
Select(ModelA, ModelB).Join(ModelB).On(ModelA.fk == ModelB.id)
```

---

## Bug #2: DELETE Location - Violacion FK Hotels

### Error en Logs
```
update or delete on table "locations" violates foreign key constraint "fk_hotels_location_id" on table "hotels"
DETAIL: Key (id)=(00e59980-d224-469a-affc-8ef37d0f2c5f) is still referenced from table "hotels".
```

### Causa
La tabla `hotels` tiene una Foreign Key hacia `locations` sin `ON DELETE CASCADE`. Al intentar eliminar una location que tiene hotels asociados, PostgreSQL rechaza la operacion.

### Solucion
Eliminar los hotels asociados **antes** de eliminar la location.

### Codigo Incorrecto (lineas 527-531)
```python
# Eliminar location (CASCADE eliminara trips, hotels, etc.) <-- FALSO
await session.exec(
    Delete(Location)
    .Where(Location.id == location_uuid)
)
```

### Codigo Corregido
```python
# Primero eliminar hotels asociados (FK sin CASCADE)
await session.exec(
    Delete(Hotel)
    .Where(Hotel.location_id == location_uuid)
)

# Luego eliminar la location (trips si tienen CASCADE)
await session.exec(
    Delete(Location)
    .Where(Location.id == location_uuid)
)
```

---

## Tabla de Foreign Keys

| Tabla | FK Column | Referencia | ON DELETE |
|-------|-----------|------------|-----------|
| trips | location_id | locations.id | CASCADE |
| hotels | location_id | locations.id | NO ACTION |
| drivers | location_id | locations.id | SET NULL |

---

## Verificacion

Despues de aplicar los fixes:

```bash
# Test PATCH trip
curl -X PATCH "https://api.gt360.app/v1/locations/{loc_uuid}/trips/{trip_uuid}" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{"pick_up_location": "Test Hotel"}'
# Esperado: 200 con trip actualizado

# Test DELETE location
curl -X DELETE "https://api.gt360.app/v1/locations/{loc_uuid}" \
  -H "Authorization: Bearer {token}"
# Esperado: 200 "Location deleted successfully"
```

---

## Archivos Modificados

| Archivo | Lineas | Cambio |
|---------|--------|--------|
| `features/trips/routes/trips_router.py` | 477 | Corregir sintaxis Join |
| `features/trips/routes/trips_router.py` | 527-531 | Eliminar hotels antes de location |
| `features/trips/webhooks/trip_webhooks.py` | 41-46 | Incluir objeto trip en eventos delete |
| `docs/BUGFIX_POST_DEPLOY.md` | - | Esta documentacion |

---

## Bug #3: Evento Delete sin datos del Trip

### Problema
Los eventos WebSocket de tipo `delete` solo incluian `trip_id` y `location_id`, sin los datos del trip eliminado.

### Causa
El webhook ignoraba el objeto `trip` en eventos delete (linea 41-45).

### Codigo Incorrecto
```python
pub_event = {
    "location_id": location_id,
    "trip_id": trip_id,
    "event_type": "delete",
}
```

### Codigo Corregido
```python
pub_event = {
    "location_id": location_id,
    "trip_id": trip_id,
    "event_type": "delete",
    "trip": trip,  # Incluir datos del trip para notificaciones
}
```

### Nuevo Formato del Evento Delete
```json
{
  "type": "trip_event",
  "event_type": "delete",
  "location_id": "uuid",
  "trip_id": "uuid",
  "trip": {
    "id": "uuid",
    "pick_up_location": "Hotel Marriott",
    "drop_off_location": "JFK Airport",
    "airline": "United Airlines",
    "flight_number": "UA123",
    ...
  }
}
```

### Impacto en Frontend
Ahora el frontend puede mostrar notificaciones con informacion util:
- `trip.pick_up_location` - "Hotel Marriott"
- `trip.airline` - "United Airlines"
- `trip.flight_number` - "UA123"

Ejemplo de notificacion mejorada:
```
"Se elimino el trip: Hotel Marriott -> JFK Airport (UA123)"
```

---

## Impacto en Frontend

Ninguno. Los endpoints mantienen el mismo contrato de API:
- PATCH trip: 200 con `{"status": "ok", "trip": {...}}`
- DELETE location: 200 con `{"data": "Location '{name}' deleted successfully"}`

---

## Feature #4: Consolidated Location Delete Notification

### Date: 2026-01-04

### Description
When deleting a Location, the system now sends a single consolidated WebSocket notification
that includes the location info and all associated hotels that were deleted.

### Implementation
**File:** `features/trips/routes/trips_router.py` (lines 536-592)

Changes made:
1. Query hotels BEFORE deleting them
2. Publish consolidated notification to Redis channel `org:{organization_id}`

### Notification Format (WebSocket)

| Field | Type | Description |
|-------|------|-------------|
| type | string | Always `"location_deleted"` |
| location_id | uuid | ID of deleted location |
| location_name | string | Name of deleted location |
| message | string | Human-readable message |
| hotels | array | List of deleted hotels with `id`, `name`, `status` |
| hotels_count | int | Number of hotels deleted |

### Example Notification
```json
{
  "type": "location_deleted",
  "location_id": "abc-123-def-456",
  "location_name": "Southwest Airlines - SDF",
  "message": "Location 'Southwest Airlines - SDF' deleted successfully",
  "hotels": [
    {"id": "def-456", "name": "The Galt House", "status": "deleted"},
    {"id": "ghi-789", "name": "Hyatt Regency Louisville", "status": "deleted"}
  ],
  "hotels_count": 2
}
```

### Frontend Display (Suggested)
```
Location 'Southwest Airlines - SDF' deleted successfully
  - The Galt House (deleted)
  - Hyatt Regency Louisville (deleted)
```

### Redis Channel
Notifications are published to: `org:{organization_id}`

Frontend should subscribe to this channel to receive location deletion events.
