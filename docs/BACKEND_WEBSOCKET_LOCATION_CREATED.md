# WebSocket Event: `location_created`

## Resumen Ejecutivo

**Objetivo:** Sincronizar la creación de locations en tiempo real entre múltiples dispositivos del mismo usuario/organización.

**Estado actual:**
- `location_deleted`: ✅ Backend emite, Frontend maneja
- `location_created`: ❌ Backend NO emite, Frontend listo para recibir

**Acción requerida:** Backend debe emitir evento `location_created` cuando se crea una location.

---

## 1. ESPECIFICACIÓN BACKEND

### 1.1 Canal WebSocket

- **Endpoint:** `/ws/org` (ya existe y funciona)
- **Broadcast channel:** `org:{organization_id}`
- **Autenticación:** JWT token en query params (ya implementado)

### 1.2 Evento a Emitir

**Nombre del evento:** `location_created`

**Momento de emisión:** Después de crear exitosamente una location en la base de datos, antes de retornar la respuesta HTTP.

**Endpoint que dispara:** El endpoint que crea locations (ej: `POST /api/locations`)

### 1.3 Estructura del Mensaje

```json
{
  "type": "location_created",
  "location_id": "550e8400-e29b-41d4-a716-446655440000",
  "location_code": "SDF",
  "location_name": "Louisville International Airport",
  "airline_code": "WN",
  "airline_name": "Southwest Airlines",
  "message": "Location 'SDF' created successfully",
  "created_at": "2025-01-05T14:30:00Z"
}
```

### 1.4 Campos Requeridos

| Campo | Tipo | Descripción | Ejemplo |
|-------|------|-------------|---------|
| `type` | string | Siempre `"location_created"` | `"location_created"` |
| `location_id` | string (UUID) | ID único de la location creada | `"550e8400-e29b-41d4-a716-446655440000"` |
| `location_code` | string | Código del aeropuerto (IATA) | `"SDF"` |
| `location_name` | string | Nombre legible de la location | `"Louisville International Airport"` |
| `airline_code` | string | Código de la aerolínea (IATA) | `"WN"` |
| `airline_name` | string | Nombre de la aerolínea | `"Southwest Airlines"` |
| `message` | string | Mensaje descriptivo | `"Location 'SDF' created successfully"` |

### 1.5 Campos Opcionales (Recomendados)

| Campo | Tipo | Descripción | Uso |
|-------|------|-------------|-----|
| `actor_user_id` | string (UUID) | ID del usuario que creó | Para idempotencia |
| `created_at` | string (ISO 8601) | Timestamp de creación | Para ordenamiento |

### 1.6 Pseudocódigo de Implementación

```python
# En el endpoint de creación de location
@router.post("/api/locations")
async def create_location(location_data: LocationCreate, user: User):
    # 1. Crear location en DB
    new_location = await db.locations.create(location_data)

    # 2. Emitir evento WebSocket a todos los usuarios de la organización
    await websocket_manager.broadcast_to_channel(
        channel=f"org:{user.organization_id}",
        message={
            "type": "location_created",
            "location_id": str(new_location.id),
            "location_code": new_location.code,
            "location_name": new_location.name,
            "airline_code": new_location.airline.code,
            "airline_name": new_location.airline.name,
            "message": f"Location '{new_location.code}' created successfully",
            "actor_user_id": str(user.id),  # opcional
            "created_at": new_location.created_at.isoformat()  # opcional
        }
    )

    # 3. Retornar respuesta HTTP
    return new_location
```

### 1.7 Referencia: Evento `location_deleted` existente

Para mantener consistencia, aquí está la estructura del evento `location_deleted` que ya funciona:

```json
{
  "type": "location_deleted",
  "location_id": "550e8400-e29b-41d4-a716-446655440000",
  "location_name": "Louisville International Airport",
  "message": "Location 'SDF' deleted successfully",
  "hotels": [
    {"id": "hotel-uuid-1", "name": "Hilton", "status": "deleted"},
    {"id": "hotel-uuid-2", "name": "Marriott", "status": "deleted"}
  ],
  "hotels_count": 2
}
```

---

## 2. IMPLEMENTACIÓN FRONTEND (para contexto)

El frontend ya está preparado para recibir el evento. Estos son los cambios que se implementarán:

### 2.1 Tipos TypeScript

**Archivo:** `src/lib/websocket/org-types.ts`

```typescript
/**
 * Location created event from backend
 * Sent when a new location is created
 */
export interface OrgEventLocationCreated {
  type: 'location_created'
  location_id: string
  location_code: string
  location_name: string
  airline_code: string
  airline_name: string
  message: string
  actor_user_id?: string
  created_at?: string
}

// Type guard
export function isOrgEventLocationCreated(event: OrgEvent): event is OrgEventLocationCreated {
  return event.type === 'location_created'
}
```

### 2.2 Hook de React

**Archivo:** `src/hooks/use-websocket-org.ts`

Se agregará un nuevo callback:

```typescript
export interface UseWebSocketOrgOptions {
  organizationId: string | null
  enabled?: boolean
  onLocationDeleted?: (event: OrgEventLocationDeleted) => void
  onLocationCreated?: (event: OrgEventLocationCreated) => void  // NUEVO
  onError?: (error: Error) => void
}
```

### 2.3 Handler Global

**Archivo:** `src/app/(main)/dashboard/client-layout.tsx`

```typescript
useWebSocketOrg({
  organizationId,
  enabled: !!organizationId,

  // Handler existente para location_deleted
  onLocationDeleted: (event) => { /* ... */ },

  // NUEVO: Handler para location_created
  onLocationCreated: (event) => {
    console.log('[OrgWebSocketListener] Location created:', event.location_name)

    const STORAGE_KEY = "api360-saved-schedules"

    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]")

      // Verificar si ya existe (idempotencia)
      const exists = saved.some(
        (entry) => entry.locationId === event.location_id
      )

      if (!exists) {
        // Agregar nueva location
        const newEntry = {
          locationId: event.location_id,
          locationCode: event.location_code,
          locationName: event.location_name,
          airlineCode: event.airline_code,
          airlineName: event.airline_name,
          savedAt: new Date().toISOString()
        }
        saved.push(newEntry)
        localStorage.setItem(STORAGE_KEY, JSON.stringify(saved))

        // Disparar evento para actualizar sidebar
        window.dispatchEvent(new Event("saved-schedules-update"))

        // Mostrar notificación toast
        showLocationCreatedByOtherNotification(event)
      }
    } catch (error) {
      console.error('[OrgWebSocketListener] Error:', error)
    }
  },
})
```

### 2.4 Notificación

**Archivo:** `src/lib/trips/notifications.ts`

```typescript
export function showLocationCreatedByOtherNotification(
  event: OrgEventLocationCreated
) {
  toast.success(`Location '${event.location_name}' added`, {
    description: `${event.airline_name} (${event.airline_code})`,
    duration: 4000,
  })
}
```

---

## 3. FLUJO COMPLETO

### 3.1 Escenario de Uso

1. Usuario A tiene sesión activa en laptop y mobile
2. Usuario A crea location "SDF/WN" desde laptop
3. Backend:
   - Crea location en DB
   - Emite `location_created` a `org:{org_id}`
   - Retorna respuesta HTTP

4. **En laptop (dispositivo que creó):**
   - Recibe respuesta HTTP → actualiza UI localmente
   - Recibe evento WS → verifica que ya existe (idempotencia) → ignora

5. **En mobile (otro dispositivo):**
   - Recibe evento WS
   - Agrega location a localStorage
   - Actualiza sidebar automáticamente
   - Muestra toast: "Location 'Louisville' added"

### 3.2 Diagrama de Secuencia

```
Laptop                    Backend                   Mobile
   |                         |                         |
   |--POST /api/locations--->|                         |
   |                         |--Create in DB---------->|
   |                         |                         |
   |                         |--WS: location_created-->|
   |                         |--WS: location_created-->| (a laptop también)
   |<--HTTP 201 Created------|                         |
   |                         |                         |
   |--Update UI locally----->|                         |
   |                         |                         |--Update localStorage
   |--WS received----------->|                         |--Update sidebar
   |--Already exists,------->|                         |--Show toast
   |  skip (idempotent)      |                         |
```

---

## 4. TESTING

### 4.1 Caso de Prueba Manual

1. Abrir la aplicación en 2 dispositivos/pestañas con el mismo usuario
2. En dispositivo A: crear una nueva location
3. **Verificar en dispositivo B:**
   - [ ] La location aparece en el sidebar sin refresh
   - [ ] Se muestra toast notification
   - [ ] No hay duplicados si se crea desde el mismo dispositivo

### 4.2 Verificación de Evento

Para verificar que el evento se está emitiendo correctamente, abrir DevTools → Network → WS y buscar mensajes con `type: "location_created"`.

---

## 5. PREGUNTAS PARA BACKEND

1. ¿Cuál es el endpoint exacto de creación de locations?
2. ¿El `WebSocketManager` ya tiene método para broadcast a `org:{org_id}`?
3. ¿Preferencia de emisión síncrona o asíncrona?
4. ¿Se implementará `actor_user_id` para idempotencia?

---

## 6. TIMELINE SUGERIDO

| Fase | Descripción | Bloqueado por |
|------|-------------|---------------|
| 1. Backend | Emitir evento `location_created` | Nada |
| 2. Frontend | Agregar tipos + handler | Backend (fase 1) |
| 3. Testing | Verificación E2E | Ambos completados |

---

**Última actualización:** 2025-01-05
**Autor:** Frontend Team
**Estado:** Esperando implementación backend
