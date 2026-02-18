# 📍 Guía Frontend: Gestión de Geofence del Aeropuerto (Location)

**Fecha:** 2026-02-16
**Propósito:** Documentar cómo eliminar y editar el geofence del aeropuerto desde el frontend

---

## 📋 RESPUESTAS A TUS PREGUNTAS

### ❓ **PREGUNTA 1:** ¿Se borra el geofence cuando elimino la location?

✅ **SÍ**, cuando eliminas una location, se borra **TODO**:

1. ✅ La **location** (aeropuerto) con su geofence
2. ✅ Todos los **hotels** asociados con sus geofences
3. ✅ Todos los **trips** asociados
4. ✅ Notificación en tiempo real vía WebSocket

**Endpoint:**
```
DELETE /v1/locations/{location_id}
Authorization: Bearer {token}
Role: manager
```

---

### ❓ **PREGUNTA 2:** ¿Puedo editar el geofence del aeropuerto?

✅ **SÍ**, puedes editar:
- ✅ **Coordenadas** (`point`) - Mover el aeropuerto en el mapa
- ✅ **Radio** (`radio_zone`) - Agrandar o achicar el círculo
- ✅ **Dirección** (`address`)
- ✅ **Estado** (`validation_status`)

**Endpoint:**
```
PATCH /v1/locations/{location_id}
Authorization: Bearer {token}
Role: manager, driver
```

---

## 🗑️ ELIMINAR LOCATION (Borrar Geofence)

### Endpoint DELETE

```http
DELETE /v1/locations/{location_id}
Authorization: Bearer {access_token}
```

### Request

```javascript
DELETE https://api.gt360.app/v1/locations/abc168b5-b74d-4ecb-98a0-c48b68b404bc
Headers:
  Authorization: Bearer eyJhbGci...
```

### Response Success (200)

```json
{
  "status": "ok",
  "data": {
    "location_id": "abc168b5-b74d-4ecb-98a0-c48b68b404bc",
    "location_name": "SDF",
    "trips_deleted": 150,
    "hotels_deleted": 5,
    "message": "Location SDF deleted successfully"
  }
}
```

### ¿Qué se elimina?

```
Location SDF
   ├─ point: [-85.7416, 38.1868]        ❌ ELIMINADO
   ├─ radio_zone: 0.50 millas           ❌ ELIMINADO
   ├─ Hotels (5 hoteles)                ❌ ELIMINADOS
   │   ├─ Hyatt Regency (con geofence)  ❌ ELIMINADO
   │   ├─ The Galt House (con geofence) ❌ ELIMINADO
   │   └─ ...
   └─ Trips (150 trips)                 ❌ ELIMINADOS
```

### Código Frontend (TypeScript)

```typescript
// services/locations.api.ts

async function deleteLocation(locationId: string): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/v1/locations/${locationId}`,
    {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    }
  );

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error('Location no encontrada');
    }
    throw new Error(`Error ${response.status}: ${response.statusText}`);
  }

  const data = await response.json();
  return data;
}
```

### Componente de Confirmación

```typescript
// components/DeleteLocationButton.tsx

import { useState } from 'react';
import { Trash2 } from 'lucide-react';

interface Props {
  locationId: string;
  locationName: string;
  onDeleted: () => void;
}

export function DeleteLocationButton({ locationId, locationName, onDeleted }: Props) {
  const [isConfirming, setIsConfirming] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  async function handleDelete() {
    setIsDeleting(true);
    try {
      const result = await locationsApi.delete(locationId);

      toast.success(
        `Location ${locationName} eliminada`,
        `${result.trips_deleted} trips y ${result.hotels_deleted} hoteles también fueron eliminados`
      );

      onDeleted();
    } catch (error) {
      toast.error('Error al eliminar location: ' + error.message);
    } finally {
      setIsDeleting(false);
      setIsConfirming(false);
    }
  }

  if (isConfirming) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <p className="text-red-800 font-semibold mb-2">
          ⚠️ ¿Estás seguro?
        </p>
        <p className="text-red-700 text-sm mb-4">
          Esto eliminará:
          • Location {locationName}
          • Todos los hoteles y sus geofences
          • Todos los trips asociados

          Esta acción NO se puede deshacer.
        </p>
        <div className="flex gap-2">
          <button
            onClick={handleDelete}
            disabled={isDeleting}
            className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
          >
            {isDeleting ? 'Eliminando...' : 'Sí, eliminar'}
          </button>
          <button
            onClick={() => setIsConfirming(false)}
            disabled={isDeleting}
            className="px-4 py-2 bg-gray-200 rounded hover:bg-gray-300"
          >
            Cancelar
          </button>
        </div>
      </div>
    );
  }

  return (
    <button
      onClick={() => setIsConfirming(true)}
      className="p-2 text-red-600 hover:bg-red-50 rounded"
      title="Eliminar location"
    >
      <Trash2 className="w-5 h-5" />
    </button>
  );
}
```

### WebSocket Events

Cuando eliminas una location, el backend envía eventos WebSocket:

#### 1. Evento de Inicio
```json
{
  "type": "location_delete_started",
  "location_id": "abc168b5-...",
  "location_name": "SDF",
  "trips_count": 150,
  "hotels_count": 5
}
```

#### 2. Evento de Completado
```json
{
  "type": "location_deleted",
  "location_id": "abc168b5-...",
  "location_name": "SDF",
  "trips_deleted": 150,
  "hotels_deleted": 5,
  "message": "Location SDF deleted"
}
```

### Manejo de WebSocket en Frontend

```typescript
// hooks/useWebSocket.ts

useEffect(() => {
  if (!socket) return;

  socket.on('message', (event) => {
    const data = JSON.parse(event);

    if (data.type === 'location_delete_started') {
      // Mostrar loading
      setDeletingLocationId(data.location_id);
      toast.info(`Eliminando location ${data.location_name}...`);
    }

    if (data.type === 'location_deleted') {
      // Remover location de la lista local
      setLocations(prev => prev.filter(l => l.id !== data.location_id));

      // Limpiar localStorage si era la location activa
      const cached = localStorage.getItem('location_id');
      if (cached === data.location_id) {
        localStorage.removeItem('location_id');
      }

      toast.success(
        `Location ${data.location_name} eliminada`,
        `${data.trips_deleted} trips y ${data.hotels_deleted} hoteles eliminados`
      );

      setDeletingLocationId(null);
    }
  });
}, [socket]);
```

---

## ✏️ EDITAR GEOFENCE DEL AEROPUERTO (Location)

### Endpoint PATCH

```http
PATCH /v1/locations/{location_id}
Authorization: Bearer {access_token}
Content-Type: application/json
```

### Request Body (todos los campos opcionales)

```json
{
  "point": {
    "type": "Point",
    "coordinates": [-85.7385, 38.1744]
  },
  "radio_zone": 0.8,
  "address": "600 Terminal Dr, Louisville, KY 40209",
  "validation_status": "VALIDATED"
}
```

### Response Success (200)

```json
{
  "status": "ok",
  "location": {
    "id": "abc168b5-b74d-4ecb-98a0-c48b68b404bc",
    "name": "SDF",
    "organization_id": "345dac5b-7e03-4ae9-ab5f-5bb504c28068",
    "point": {
      "type": "Point",
      "coordinates": [-85.7385, 38.1744]
    },
    "radio_zone": 0.8,
    "address": "600 Terminal Dr, Louisville, KY 40209",
    "validation_status": "VALIDATED",
    "provider": "google",
    "timezone": "America/New_York",
    "created_at": "2026-02-16T02:46:13.705617+00:00"
  }
}
```

### Código Frontend (TypeScript)

```typescript
// services/locations.api.ts

interface LocationUpdateRequest {
  point?: {
    type: 'Point';
    coordinates: [number, number];  // [longitude, latitude]
  };
  radio_zone?: number;  // En millas (max 1.0)
  address?: string;
  validation_status?: 'NEEDS_VALIDATION' | 'VALIDATED' | 'DISABLED';
}

async function updateLocation(
  locationId: string,
  updates: LocationUpdateRequest
): Promise<Location> {
  const response = await fetch(
    `${API_BASE_URL}/v1/locations/${locationId}`,
    {
      method: 'PATCH',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(updates),
    }
  );

  if (!response.ok) {
    throw new Error(`Error ${response.status}: ${response.statusText}`);
  }

  const data = await response.json();
  return data.location;
}
```

---

## 🗺️ COMPONENTE DE EDICIÓN DE GEOFENCE (Aeropuerto)

```typescript
// components/AirportGeofenceEditor.tsx

import { useState, useCallback } from 'react';
import { GoogleMap, Marker, Circle } from '@react-google-maps/api';
import { locationsApi } from '@/services/locations.api';
import { toast } from 'react-hot-toast';

interface Props {
  location: Location;
  onUpdate: () => void;
}

export function AirportGeofenceEditor({ location, onUpdate }: Props) {
  const [isSaving, setIsSaving] = useState(false);
  const [radius, setRadius] = useState(location.radio_zone || 0.5);

  // Convertir GeoJSON a Google Maps LatLng
  const center = location.point
    ? {
        lat: location.point.coordinates[1],
        lng: location.point.coordinates[0]
      }
    : { lat: 38.1744, lng: -85.7385 };

  // Manejar arrastre del marcador
  const handleMarkerDragEnd = useCallback(
    async (event: google.maps.MapMouseEvent) => {
      if (!event.latLng) return;

      const lat = event.latLng.lat();
      const lng = event.latLng.lng();

      setIsSaving(true);
      try {
        await locationsApi.update(location.id, {
          point: {
            type: 'Point',
            coordinates: [lng, lat]  // GeoJSON: [lon, lat]
          },
          validation_status: 'VALIDATED'
        });

        toast.success('Coordenadas del aeropuerto actualizadas');
        onUpdate();
      } catch (error) {
        toast.error('Error al actualizar: ' + error.message);
      } finally {
        setIsSaving(false);
      }
    },
    [location.id, onUpdate]
  );

  // Manejar cambio de radio
  const handleRadiusChange = async (newRadius: number) => {
    if (newRadius < 0 || newRadius > 1.0) {
      toast.error('El radio debe estar entre 0 y 1.0 millas');
      return;
    }

    setRadius(newRadius);

    try {
      await locationsApi.update(location.id, {
        radio_zone: newRadius
      });

      toast.success(`Radio actualizado a ${newRadius} millas`);
      onUpdate();
    } catch (error) {
      toast.error('Error al actualizar radio');
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-lg">
          Geofence del Aeropuerto: {location.name}
        </h3>
        {isSaving && (
          <span className="text-sm text-blue-600">Guardando...</span>
        )}
      </div>

      {/* Mapa con marcador arrastrable */}
      <div className="h-96 rounded-lg overflow-hidden border border-gray-300">
        <GoogleMap
          mapContainerStyle={{ width: '100%', height: '100%' }}
          center={center}
          zoom={13}
        >
          {/* Marcador del aeropuerto (arrastrable) */}
          <Marker
            position={center}
            draggable={true}
            onDragEnd={handleMarkerDragEnd}
            icon={{
              url: '/icons/airport.svg',
              scaledSize: new google.maps.Size(40, 40),
            }}
            label={{
              text: location.name,
              color: '#1f2937',
              fontSize: '14px',
              fontWeight: 'bold',
            }}
          />

          {/* Círculo del geofence */}
          {location.point && (
            <Circle
              center={center}
              radius={radius * 1609.344}  // Convertir millas a metros
              options={{
                fillColor: '#3b82f6',
                fillOpacity: 0.2,
                strokeColor: '#3b82f6',
                strokeWeight: 2,
              }}
            />
          )}
        </GoogleMap>
      </div>

      {/* Slider para ajustar radio */}
      <div className="space-y-2">
        <label className="block text-sm font-medium text-gray-700">
          Radio del Geofence: {radius.toFixed(2)} millas
          ({Math.round(radius * 1609.344)} metros)
        </label>
        <input
          type="range"
          min="0.1"
          max="1.0"
          step="0.05"
          value={radius}
          onChange={(e) => handleRadiusChange(parseFloat(e.target.value))}
          className="w-full h-2 bg-gray-200 rounded-lg cursor-pointer"
        />
        <div className="flex justify-between text-xs text-gray-500">
          <span>0.1 mi (161m)</span>
          <span>0.5 mi (805m)</span>
          <span>1.0 mi (1.6km) - máx.</span>
        </div>
      </div>

      {/* Información de coordenadas */}
      {location.point && (
        <div className="bg-gray-50 rounded p-3 text-sm space-y-1">
          <p className="font-medium text-gray-700">Coordenadas actuales:</p>
          <p className="text-gray-600">
            Latitud: {location.point.coordinates[1].toFixed(6)}
          </p>
          <p className="text-gray-600">
            Longitud: {location.point.coordinates[0].toFixed(6)}
          </p>
        </div>
      )}

      {/* Instrucciones */}
      <div className="bg-blue-50 border border-blue-200 rounded p-3 text-sm text-blue-800">
        <p className="font-medium mb-1">💡 Cómo editar:</p>
        <ul className="list-disc list-inside space-y-1">
          <li>Arrastra el marcador para cambiar las coordenadas</li>
          <li>Usa el slider para ajustar el radio del geofence</li>
          <li>Los cambios se guardan automáticamente</li>
        </ul>
      </div>
    </div>
  );
}
```

---

## 📱 INTEGRACIÓN EN SETTINGS

```typescript
// pages/Settings/Locations.tsx

import { AirportGeofenceEditor } from '@/components/AirportGeofenceEditor';
import { DeleteLocationButton } from '@/components/DeleteLocationButton';

export function LocationsSettings() {
  const [locations, setLocations] = useState<Location[]>([]);
  const [selectedLocation, setSelectedLocation] = useState<Location | null>(null);

  useEffect(() => {
    loadLocations();
  }, []);

  async function loadLocations() {
    const data = await locationsApi.getAll();
    setLocations(data);
  }

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">Gestión de Locations</h1>

      {/* Lista de locations */}
      <div className="space-y-4 mb-8">
        {locations.map(location => (
          <div
            key={location.id}
            className="border rounded-lg p-4 flex items-center justify-between"
          >
            <div>
              <h3 className="font-semibold">{location.name}</h3>
              <p className="text-sm text-gray-600">{location.timezone}</p>
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => setSelectedLocation(location)}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
              >
                Editar Geofence
              </button>

              <DeleteLocationButton
                locationId={location.id}
                locationName={location.name}
                onDeleted={loadLocations}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Editor de geofence */}
      {selectedLocation && (
        <div className="border-t pt-6">
          <AirportGeofenceEditor
            location={selectedLocation}
            onUpdate={loadLocations}
          />
        </div>
      )}
    </div>
  );
}
```

---

## 🔒 VALIDACIONES

### Límites del Radio (Backend)

```sql
-- Constraint en la base de datos
CheckConstraint("radio_zone IS NULL OR radio_zone <= 1.0", name="ck_location_max_radius")
```

**Máximo:** 1.0 milla (1609.344 metros)

### Validación en Frontend

```typescript
function validateRadius(radius: number): string | null {
  if (radius < 0) return 'El radio no puede ser negativo';
  if (radius > 1.0) return 'El radio máximo es 1.0 millas';
  return null;
}
```

---

## 📊 RESUMEN

### ✅ LO QUE YA FUNCIONA:

| Acción | Endpoint | Frontend | Backend |
|--------|----------|----------|---------|
| **Eliminar Location** | `DELETE /v1/locations/{id}` | ✅ Botón en Settings | ✅ Funciona |
| **Editar Geofence** | `PATCH /v1/locations/{id}` | ❌ **Falta implementar** | ✅ Funciona |

### 🛠️ LO QUE NECESITAS IMPLEMENTAR EN EL FRONTEND:

1. ✅ Botón de eliminar → Ya lo tienes (captura de pantalla)
2. ❌ **Editor de geofence del aeropuerto** → Usar código de `AirportGeofenceEditor.tsx`
3. ❌ **Mapa interactivo** → Arrastra marcador, ajusta radio
4. ❌ **Manejo de WebSocket** → Actualizar UI cuando se elimina location

---

## 🚀 PRÓXIMOS PASOS

1. **Implementar componente `AirportGeofenceEditor`**
2. **Agregar botón "Editar Geofence" en la UI de Settings**
3. **Integrar Google Maps** (si no lo tienes ya)
4. **Probar eliminación** y verificar que se borra el geofence
5. **Probar edición** arrastrando marcador y ajustando radio

---

**Última actualización:** 2026-02-16
**Backend:** ✅ Listo
**Frontend:** ⚠️ Necesita implementar editor de geofence
