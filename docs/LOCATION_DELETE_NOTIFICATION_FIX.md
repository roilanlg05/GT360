# Location Delete — Fix de Notificaciones Duplicadas

## Problema

Al borrar una location, el frontend mostraba **3 toasts** en vez de 1:

| Toast | Texto | Origen | Canal |
|-------|-------|--------|-------|
| 1 | `Location "SDF" deleted / 688 trips and 2 hotels also deleted` | WS org event `location_deleted` | `/ws/org` |
| 2 | `Location "Louisville Muhammad Ali..." deleted successfully` | REST response del `DELETE /v1/locations/{id}` | HTTP |
| 3 | `25 trips deleted successfully` | WS trips event `trips_batch` | `/ws/trips` |

## Investigación del Backend

El análisis del frontend asumía que durante el cascade delete se generaban `trips_batch` events individuales por DB triggers. **Esto era incorrecto.**

El backend:
- **NO tiene DB triggers** que disparen eventos de delete
- **NO genera `trips_batch` events** durante location delete — usa `DELETE ... WHERE` en bulk sin publicar nada a Redis
- Los `trips_batch` events **solo existen durante trip uploads** (inserciones), nunca para deletes

El problema real era que el backend publicaba **4 mensajes Redis** (2 eventos × 2 canales):
- `location_delete_started` → `org:{org_id}` + `loc:{location_id}`
- `location_deleted` → `org:{org_id}` + `loc:{location_id}`

El frontend escuchaba en ambos canales (`/ws/org` y `/ws/trips`) y reaccionaba múltiples veces al mismo evento.

## Qué se cambió en el Backend

**Archivo:** `features/trips/routes/trips_router.py` — endpoint `DELETE /v1/locations/{location_id}`

### Antes (4 publishes)
```
1. PUBLISH location_delete_started → org:{org_id}
2. PUBLISH location_delete_started → loc:{location_id}
3. DELETE trips, hotels, location + COMMIT
4. PUBLISH location_deleted → org:{org_id}
5. PUBLISH location_deleted → loc:{location_id}
```

### Ahora (1 publish)
```
1. DELETE trips, hotels, location + COMMIT
2. PUBLISH location_deleted → org:{org_id}   ← único evento
```

### Cambios específicos
1. Se eliminó `location_delete_started` — no aporta valor porque no hay batch events intermedios que suprimir
2. Se eliminó el publish a `loc:{location_id}` — la location ya no existe post-delete, y el canal `/ws/trips` no necesita este evento
3. Se agregó el campo `deleted_by` al evento — contiene el `user_id` (UUID) del manager que ejecutó el delete
4. Se publica **un solo evento** `location_deleted` al canal `org:{org_id}` **después del commit**

## Evento WebSocket actualizado

El evento que llega por `/ws/org` ahora tiene esta estructura:

```json
{
  "type": "location_deleted",
  "location_id": "uuid-de-la-location",
  "location_name": "SDF",
  "trips_deleted": 688,
  "hotels_deleted": 2,
  "deleted_by": "uuid-del-manager-que-borró",
  "message": "Location SDF deleted",
  "detail": "688 trips and 2 hotels also deleted"
}
```

### Campo nuevo: `deleted_by`
- **Tipo:** `string` (UUID del usuario)
- **Valor:** el `id` del manager autenticado que hizo el DELETE
- **Propósito:** permite al frontend distinguir si fue el usuario actual quien borró la location (self-deletion) o si fue otro manager de la misma org

## Qué debe cambiar el Frontend

### 1. Eliminar el toast del REST response (`my-locations-card.tsx`)

El `toast.success()` que se dispara cuando el `DELETE /v1/locations/{id}` responde OK ya no es necesario. El único toast debe venir del evento WebSocket.

```diff
  const result = await locationService.deleteLocation(locationToDelete.id)
- toast.success(`Location "${locationToDelete.name}" deleted successfully`)
```

### 2. Usar `deleted_by` para decidir qué toast mostrar (`client-layout.tsx`)

En el `OrgWebSocketListener`, comparar `event.deleted_by` con el user_id local:

```typescript
onLocationDeleted: (event) => {
  // Limpiar localStorage, sidebar, etc. (siempre)

  const currentUserId = /* obtener user_id del auth context */;

  if (event.deleted_by === currentUserId) {
    // Self-deletion: mostrar toast de éxito simple
    toast.success(`Location "${event.location_name}" deleted successfully`);
  } else {
    // Otro manager borró la location: mostrar warning con detalle
    toast.warning(`Location "${event.location_name}" deleted`, {
      description: event.detail,
      duration: 6000,
    });
  }
}
```

### 3. Eliminar lógica de supresión de `trips_batch` para location deletes (`use-websocket-trips.ts`)

Ya no llegan eventos por el canal `loc:{id}` durante location delete, así que se puede eliminar:
- El flag `isAnyLocationBeingDeleted()` y su setter `markLocationBeingDeleted()`
- La heurística `isLikelyLocationDeletion = allDeletes && count >= 50`
- Cualquier lógica de supresión relacionada con `location_delete_started`

Estos mecanismos ya no son necesarios porque el backend simplemente no publica nada al canal `loc:{id}` durante la eliminación de una location.

### 4. Eliminar handler de `location_delete_started` en `/ws/trips`

El backend ya no emite este evento. Si el frontend lo escuchaba en el WebSocket de trips, ese handler se puede eliminar.

## Resumen del flujo final

```
Usuario click "Delete Location"
         │
         ▼
[my-locations-card.tsx]
  DELETE /v1/locations/{id}
         │
         ├── REST response 200 OK (datos en JSON, NO mostrar toast aquí)
         │
         ▼
    BACKEND
         │
         ├─ DELETE trips (bulk SQL)
         ├─ DELETE hotels (bulk SQL)
         ├─ DELETE location
         ├─ COMMIT
         │
         └─ PUBLISH location_deleted → org:{org_id}  ← ÚNICO EVENTO
                   │
                   ▼
             /ws/org → OrgWebSocketListener
                   │
                   ├─ deleted_by === currentUserId?
                   │     YES → toast.success("Location X deleted successfully")
                   │     NO  → toast.warning("Location X deleted", { description: detail })
                   │
                   └─ Limpiar estado (localStorage, sidebar, redirect si estaba en esa location)
```

**Resultado:** 1 sola notificación por location delete, siempre.
