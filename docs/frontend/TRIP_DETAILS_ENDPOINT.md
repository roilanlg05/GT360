# Endpoint de Detalles Completos de Trip - Guía para Frontend

## 📋 Resumen

Este endpoint proporciona **todos los detalles de un trip** en una sola llamada API, incluyendo datos relacionados de Location, Driver, FilterStep y Hotels. Diseñado para minimizar llamadas al backend y proporcionar toda la información necesaria para mostrar detalles completos de un viaje al manager.

---

## 🔗 Endpoint

```
GET /v1/locations/{location_id}/trips/{trip_id}/details
```

### Parámetros de Ruta

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `location_id` | UUID | ID de la location (aeropuerto) |
| `trip_id` | UUID | ID del trip a consultar |

### Autenticación

**Requerida**: Sí

**Header**:
```
Authorization: Bearer <access_token>
```

**Roles permitidos**:
- `manager` - Acceso completo a todos los trips de su organización
- `driver` - Solo puede ver trips asignados a él mismo

---

## 📦 Estructura de Respuesta

### Response Code: `200 OK`

```typescript
interface TripDetailedResponse {
  trip: Trip;                           // Trip completo (23 campos)
  location: LocationDetails;            // Detalles de la location
  driver: DriverDetails | null;         // Info del driver (null si no asignado)
  filter_step: FilterStepDetails | null; // Config de filtro (null si no aplicado)
  pickup_hotel: HotelDetails | null;    // Hotel de pickup (null si no existe)
  dropoff_hotel: HotelDetails | null;   // Hotel de dropoff (null si no existe)
}
```

### 1. Trip (Objeto Completo)

```typescript
interface Trip {
  // Identificación
  id: string;                    // UUID del trip
  location_id: string;           // UUID de la location
  trip_hash: string;             // Hash único del trip (no expuesto)

  // Información del Vuelo
  airline: string;               // Código de aerolínea (ej: "WN", "AA")
  flight_number: string;         // Número de vuelo
  trip_type: "inbound" | "outbound" | "ground" | null;

  // Detalles de Pickup/Dropoff
  pick_up_date: string;          // Formato: "YYYY-MM-DD"
  pick_up_time: string;          // Formato: "HH:MM" (12h o 24h según preferencia)
  pick_up_location: string;      // Nombre del lugar de recogida
  drop_off_location: string;     // Nombre del lugar de destino

  // Pasajeros
  riders: {
    pilots: number;
    flight_attendants: number;
  } | null;

  // Driver Asignado
  assigned_driver: string | null; // UUID del driver (solo ID, ver objeto driver)

  // Estado del Trip
  status: "scheduled" | "en_route" | "completed" | "canceled" | null;

  // Timestamps del Lifecycle
  created_at: string;            // ISO 8601 timestamp
  updated_at: string;            // ISO 8601 timestamp
  started_at: string | null;     // Cuando driver inició el trip
  picked_up_at: string | null;   // Cuando se recogieron pasajeros
  dropped_off_at: string | null; // Cuando se dejaron pasajeros

  // Tracking de Filtros (Ground Filters V2)
  original_pick_up_time: string | null;  // Tiempo antes de filtros aplicados
  reduce_applied: boolean;               // ¿Filtro Reduce aplicado?
  combine_applied: boolean;              // ¿Filtro Combine aplicado?
  expand_applied: boolean;               // ¿Filtro Expand aplicado?
  filtered_at: string | null;            // Timestamp de aplicación de filtro
  current_step_id: string | null;        // UUID del step activo (ver filter_step)
}
```

### 2. LocationDetails

```typescript
interface LocationDetails {
  id: string;                    // UUID de la location
  name: string;                  // Código del aeropuerto (ej: "SDF", "JFK")
  timezone: string;              // IANA timezone (ej: "America/New_York")
  address: string | null;        // Dirección completa
  coordinates: GeoJSONPoint | null;  // Coordenadas GPS
  radio_zone: number | null;     // Radio de geofence en millas
  validation_status: "NEEDS_VALIDATION" | "VALIDATED" | "DISABLED";
  provider: string | null;       // Proveedor de datos (ej: "uber")
}

interface GeoJSONPoint {
  type: "Point";
  coordinates: [number, number]; // [longitude, latitude]
}
```

**Uso en Frontend**:
- `timezone`: Usar para convertir timestamps a hora local
- `coordinates`: Mostrar en mapa
- `radio_zone`: Dibujar zona de geofence en mapa

### 3. DriverDetails (Opcional)

```typescript
interface DriverDetails {
  id: string;                    // UUID del driver
  first_name: string | null;
  last_name: string | null;
  email: string;
  phone: string | null;          // Formato: "+1234567890"
  pay_type: "day" | "hour" | "trip" | null;
  is_active: boolean;            // ¿Driver activo/disponible?
  current_location: GeoJSONPoint | null;  // Ubicación GPS actual del driver
}
```

**Valores Null**: Si `trip.assigned_driver` es `null`, este objeto será `null`.

**Uso en Frontend**:
- Mostrar información de contacto del driver
- Mostrar ubicación actual en mapa
- Indicar disponibilidad (`is_active`)

### 4. FilterStepDetails (Opcional)

```typescript
interface FilterStepDetails {
  id: string;                    // UUID del filter step
  filter_type: "reduce" | "combine" | "expand";
  step_order: number;            // Orden en el stack de filtros (1, 2, 3...)
  config: FilterConfig;          // Configuración específica del filtro
  windows: TimeWindow[];         // Ventanas de tiempo donde aplica
  trips_affected: number;        // Cuántos trips modificó este filtro
  created_at: string;            // ISO 8601 timestamp
  is_active: boolean;            // ¿Step está activo o fue revertido?
}

// Configuración por tipo de filtro
interface FilterConfig {
  // Para "reduce"
  minutes_to_reduce?: number;    // ej: 15

  // Para "combine" y "expand"
  min_gap?: number;              // ej: 10
  max_gap?: number;              // ej: 20
  max_shift?: number;            // ej: 10
}

interface TimeWindow {
  start: string;                 // Formato "HH:MM"
  end: string;                   // Formato "HH:MM"
  enabled: boolean;
  minutes_to_reduce?: number;    // Solo para reduce
}
```

**Valores Null**: Si `trip.current_step_id` es `null`, este objeto será `null`.

**Uso en Frontend**:
- Mostrar badge "FILTRADO" si existe
- Mostrar tooltip con detalles del filtro aplicado
- Comparar `original_pick_up_time` vs `pick_up_time` para ver cambio

### 5. HotelDetails (Opcional)

```typescript
interface HotelDetails {
  id: string;                    // UUID del hotel
  name: string;                  // Nombre del hotel
  address: string | null;        // Dirección completa
  coordinates: GeoJSONPoint | null;  // Coordenadas GPS
  radio_zone: number | null;     // Radio de geofence en millas (máx 0.1)
  validation_status: "NEEDS_VALIDATION" | "VALIDATED" | "DISABLED";
}
```

**Valores Null**:
- `pickup_hotel`: `null` si el pickup location no es un hotel (ej: aeropuerto)
- `dropoff_hotel`: `null` si el dropoff location no es un hotel

**Uso en Frontend**:
- Mostrar dirección completa del hotel
- Mostrar en mapa con geofence circular
- Indicar estado de validación

---

## 🎯 Casos de Uso

### 1. Vista Detallada de Trip (Manager Dashboard)

```typescript
async function showTripDetails(locationId: string, tripId: string) {
  const response = await fetch(
    `/v1/locations/${locationId}/trips/${tripId}/details`,
    {
      headers: {
        'Authorization': `Bearer ${accessToken}`,
      },
    }
  );

  if (!response.ok) {
    handleError(response.status);
    return;
  }

  const data: TripDetailedResponse = await response.json();

  // Mostrar información del trip
  displayTripInfo(data.trip);

  // Mostrar información del driver (si está asignado)
  if (data.driver) {
    displayDriverInfo(data.driver);
    showDriverOnMap(data.driver.current_location);
  } else {
    showAssignDriverButton();
  }

  // Mostrar información de filtros (si se aplicaron)
  if (data.filter_step) {
    showFilterBadge(data.filter_step);
    highlightTimeChange(
      data.trip.original_pick_up_time,
      data.trip.pick_up_time
    );
  }

  // Mostrar ubicaciones en mapa
  if (data.pickup_hotel) {
    addHotelMarker(data.pickup_hotel, 'pickup');
  }
  if (data.dropoff_hotel) {
    addHotelMarker(data.dropoff_hotel, 'dropoff');
  }

  // Mostrar location/aeropuerto
  addLocationMarker(data.location);
}
```

### 2. Modal de Detalles Rápidos

```tsx
function TripDetailsModal({ locationId, tripId }: Props) {
  const { data, loading, error } = useTripDetails(locationId, tripId);

  if (loading) return <Spinner />;
  if (error) return <ErrorMessage error={error} />;
  if (!data) return null;

  return (
    <Modal>
      <TripHeader trip={data.trip} location={data.location} />

      <Section title="Detalles del Vuelo">
        <FlightInfo
          airline={data.trip.airline}
          flightNumber={data.trip.flight_number}
          tripType={data.trip.trip_type}
        />
      </Section>

      <Section title="Ubicaciones">
        <LocationPair
          pickup={data.trip.pick_up_location}
          dropoff={data.trip.drop_off_location}
          pickupHotel={data.pickup_hotel}
          dropoffHotel={data.dropoff_hotel}
        />
      </Section>

      {data.driver && (
        <Section title="Driver Asignado">
          <DriverCard driver={data.driver} />
        </Section>
      )}

      {data.filter_step && (
        <Section title="Filtros Aplicados">
          <FilterBadge
            filterType={data.filter_step.filter_type}
            originalTime={data.trip.original_pick_up_time}
            currentTime={data.trip.pick_up_time}
          />
        </Section>
      )}

      <Section title="Pasajeros">
        <RiderCount riders={data.trip.riders} />
      </Section>

      <Section title="Estado">
        <StatusTimeline
          status={data.trip.status}
          createdAt={data.trip.created_at}
          startedAt={data.trip.started_at}
          pickedUpAt={data.trip.picked_up_at}
          droppedOffAt={data.trip.dropped_off_at}
        />
      </Section>
    </Modal>
  );
}
```

### 3. Mapa con Detalles Completos

```typescript
async function loadTripOnMap(locationId: string, tripId: string) {
  const data = await fetchTripDetails(locationId, tripId);

  // Centro del mapa en la location
  map.setCenter({
    lat: data.location.coordinates.coordinates[1],
    lng: data.location.coordinates.coordinates[0],
  });

  // Agregar marcador de location con geofence
  addCircle(
    data.location.coordinates,
    data.location.radio_zone * 1609.34 // millas a metros
  );

  // Agregar hoteles con geofence
  if (data.pickup_hotel?.coordinates) {
    addHotelMarker(data.pickup_hotel, 'green');
    addCircle(
      data.pickup_hotel.coordinates,
      data.pickup_hotel.radio_zone * 1609.34
    );
  }

  if (data.dropoff_hotel?.coordinates) {
    addHotelMarker(data.dropoff_hotel, 'red');
    addCircle(
      data.dropoff_hotel.coordinates,
      data.dropoff_hotel.radio_zone * 1609.34
    );
  }

  // Mostrar ubicación actual del driver
  if (data.driver?.current_location) {
    addDriverMarker(data.driver.current_location);
    drawRoute(data.driver.current_location, data.pickup_hotel?.coordinates);
  }
}
```

---

## ⚠️ Manejo de Errores

### Códigos de Error

| Status | Descripción | Acción Recomendada |
|--------|-------------|--------------------|
| `400` | UUID inválido | Validar formato de IDs antes de llamar |
| `401` | No autenticado | Redirigir a login |
| `403` | Sin permiso | Mostrar "No tienes acceso a este trip" |
| `404` | Trip no encontrado | Mostrar "Trip no encontrado" |
| `500` | Error del servidor | Mostrar error genérico y reintentar |

### Ejemplo de Manejo

```typescript
async function fetchTripDetails(
  locationId: string,
  tripId: string
): Promise<TripDetailedResponse> {
  try {
    const response = await fetch(
      `/v1/locations/${locationId}/trips/${tripId}/details`,
      {
        headers: {
          'Authorization': `Bearer ${getAccessToken()}`,
        },
      }
    );

    if (!response.ok) {
      switch (response.status) {
        case 400:
          throw new Error('ID de trip o location inválido');
        case 401:
          redirectToLogin();
          throw new Error('Sesión expirada');
        case 403:
          throw new Error('No tienes permiso para ver este trip');
        case 404:
          throw new Error('Trip no encontrado');
        default:
          throw new Error('Error al cargar detalles del trip');
      }
    }

    return await response.json();
  } catch (error) {
    console.error('Error fetching trip details:', error);
    throw error;
  }
}
```

---

## 🔐 Permisos y Seguridad

### Managers
- ✅ Pueden ver **todos los trips** de locations en su organización
- ✅ Acceso completo a todos los campos

### Drivers
- ✅ Pueden ver **solo trips asignados a ellos**
- ⚠️ Si intentan acceder a trip de otro driver → `403 Forbidden`
- ✅ Mismo formato de respuesta que managers

### Ejemplo de Verificación en Frontend

```typescript
function canViewTripDetails(userRole: string, tripDriverId: string | null): boolean {
  if (userRole === 'manager') {
    return true; // Managers pueden ver todo
  }

  if (userRole === 'driver') {
    const currentUserId = getCurrentUserId();
    return tripDriverId === currentUserId;
  }

  return false; // Otros roles no tienen acceso
}
```

---

## 📊 Ejemplo de Respuesta Completa

```json
{
  "trip": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "location_id": "123e4567-e89b-12d3-a456-426614174000",
    "assigned_driver": "987e6543-e21b-12d3-a456-426614174000",
    "pick_up_date": "2026-01-31",
    "pick_up_time": "14:30",
    "pick_up_location": "Brown Hotel",
    "drop_off_location": "SDF Airport",
    "airline": "WN",
    "flight_number": "5468",
    "riders": {
      "pilots": 2,
      "flight_attendants": 4
    },
    "trip_type": "outbound",
    "status": "scheduled",
    "created_at": "2026-01-30T10:00:00Z",
    "updated_at": "2026-01-30T15:30:00Z",
    "started_at": null,
    "picked_up_at": null,
    "dropped_off_at": null,
    "original_pick_up_time": "14:45",
    "reduce_applied": true,
    "combine_applied": false,
    "expand_applied": false,
    "filtered_at": "2026-01-30T12:00:00Z",
    "current_step_id": "abc12345-e89b-12d3-a456-426614174000"
  },
  "location": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "name": "SDF",
    "timezone": "America/New_York",
    "address": "600 Terminal Dr, Louisville, KY 40209",
    "coordinates": {
      "type": "Point",
      "coordinates": [-85.7364, 38.1742]
    },
    "radio_zone": 5.0,
    "validation_status": "VALIDATED",
    "provider": "uber"
  },
  "driver": {
    "id": "987e6543-e21b-12d3-a456-426614174000",
    "first_name": "John",
    "last_name": "Smith",
    "email": "john.smith@example.com",
    "phone": "+15025551234",
    "pay_type": "hour",
    "is_active": true,
    "current_location": {
      "type": "Point",
      "coordinates": [-85.7350, 38.1750]
    }
  },
  "filter_step": {
    "id": "abc12345-e89b-12d3-a456-426614174000",
    "filter_type": "reduce",
    "step_order": 1,
    "config": {
      "minutes_to_reduce": 15
    },
    "windows": [
      {
        "start": "00:00",
        "end": "24:00",
        "enabled": true,
        "minutes_to_reduce": 15
      }
    ],
    "trips_affected": 45,
    "created_at": "2026-01-30T12:00:00Z",
    "is_active": true
  },
  "pickup_hotel": {
    "id": "def67890-e89b-12d3-a456-426614174000",
    "name": "Brown Hotel",
    "address": "335 W Broadway, Louisville, KY 40202",
    "coordinates": {
      "type": "Point",
      "coordinates": [-85.7546, 38.2527]
    },
    "radio_zone": 0.05,
    "validation_status": "VALIDATED"
  },
  "dropoff_hotel": null
}
```

---

## 🚀 Integración Recomendada

### 1. React Hook Personalizado

```typescript
// hooks/useTripDetails.ts
import { useQuery } from '@tanstack/react-query';

export function useTripDetails(locationId: string, tripId: string) {
  return useQuery({
    queryKey: ['trip-details', locationId, tripId],
    queryFn: async () => {
      const response = await fetch(
        `/v1/locations/${locationId}/trips/${tripId}/details`,
        {
          headers: {
            'Authorization': `Bearer ${getAccessToken()}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      return response.json() as Promise<TripDetailedResponse>;
    },
    staleTime: 30000, // 30 segundos
    retry: 2,
  });
}
```

### 2. Redux/Zustand Store

```typescript
// stores/tripDetailsStore.ts
interface TripDetailsState {
  details: TripDetailedResponse | null;
  loading: boolean;
  error: string | null;
  fetchTripDetails: (locationId: string, tripId: string) => Promise<void>;
}

export const useTripDetailsStore = create<TripDetailsState>((set) => ({
  details: null,
  loading: false,
  error: null,

  fetchTripDetails: async (locationId, tripId) => {
    set({ loading: true, error: null });

    try {
      const response = await fetch(
        `/v1/locations/${locationId}/trips/${tripId}/details`,
        {
          headers: {
            'Authorization': `Bearer ${getAccessToken()}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const details = await response.json();
      set({ details, loading: false });
    } catch (error) {
      set({ error: error.message, loading: false });
    }
  },
}));
```

---

## 🔄 Comparación con Endpoints Existentes

### Antes (Múltiples Llamadas)

```typescript
// ❌ Requiere 5 llamadas al backend
const trip = await fetch(`/v1/locations/${locationId}/trips/${tripId}`);
const location = await fetch(`/v1/locations/${locationId}`);
const driver = await fetch(`/v1/drivers/${trip.assigned_driver}`);
const filterStep = await fetch(`/v1/filter-steps/${trip.current_step_id}`);
const hotels = await fetch(`/v1/locations/${locationId}/hotels`);
```

### Ahora (Una Sola Llamada)

```typescript
// ✅ Una sola llamada con todo incluido
const data = await fetch(
  `/v1/locations/${locationId}/trips/${tripId}/details`
);
```

**Beneficios**:
- ⚡ Menor latencia (1 request vs 5)
- 📉 Menos carga en el servidor
- 🎯 Código más simple en frontend
- 🔄 Datos consistentes (misma transacción)

---

## 📝 Notas Importantes

1. **Timezone**: Todos los timestamps están en UTC. Usa `location.timezone` para convertir a hora local.

2. **Formato de Tiempo**: `pick_up_time` y `original_pick_up_time` están formateados según la preferencia del usuario (12h/24h).

3. **Datos Opcionales**: Siempre verifica `null` antes de usar:
   - `driver` - null si no hay driver asignado
   - `filter_step` - null si no se aplicaron filtros
   - `pickup_hotel` / `dropoff_hotel` - null si location no es hotel

4. **Geolocalización**: Coordenadas en formato GeoJSON `[longitude, latitude]`

5. **Caché**: Considera cachear la respuesta por 30-60 segundos para reducir llamadas innecesarias.

6. **Actualización en Tiempo Real**: Para updates en vivo, usa WebSocket `/ws/trips` que envía eventos cuando cambia un trip.

---

## 🧪 Testing

### Casos de Prueba Recomendados

1. ✅ Trip completo con driver y filtros
2. ✅ Trip sin driver asignado
3. ✅ Trip sin filtros aplicados
4. ✅ Trip Airport → Airport (sin hoteles)
5. ✅ Driver accediendo a su propio trip
6. ❌ Driver intentando acceder a trip de otro
7. ❌ UUID inválido
8. ❌ Trip no existe

---

## 📞 Contacto y Soporte

- **Documentación Adicional**: Ver [GROUND_FILTERS_GUIDE.md](./GROUND_FILTERS_GUIDE.md)
- **Endpoint Timeline**: Ver `/v1/locations/{location_id}/timeline` para vista cronológica
- **Endpoint QR**: Ver `QR_CODE_SYSTEM_GUIDE.md` para acceso público via QR

---

**Última actualización**: 2026-01-31
**Versión**: 1.0
**Status**: ✅ Implementado y listo para uso
