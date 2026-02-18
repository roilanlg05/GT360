# Guía Frontend: Gestión de Geofences (Locations y Hoteles)

**Última actualización:** 2026-02-05
**Propósito:** Documentación completa para implementar la gestión de geofences de locations y hoteles en el frontend

---

## Tabla de Contenidos

1. [Resumen](#resumen)
2. [Conceptos Clave](#conceptos-clave)
3. [Endpoints Disponibles](#endpoints-disponibles)
4. [Tipos TypeScript](#tipos-typescript)
5. [Obtener Datos (GET)](#obtener-datos-get)
6. [Actualizar Geofences (PATCH)](#actualizar-geofences-patch)
7. [Servicios Frontend](#servicios-frontend)
8. [Componentes UI Recomendados](#componentes-ui-recomendados)
9. [Flujo Completo de Usuario](#flujo-completo-de-usuario)
10. [Validaciones y Límites](#validaciones-y-límites)

---

## Resumen

Este documento explica cómo implementar una sección de **Settings → Geofences** en el frontend donde los managers pueden:

- Ver todas las locations (aeropuertos) de su organización
- Modificar las coordenadas (latitud/longitud) de cada location
- Ajustar el radio del geofence de cada location (máx. 1.0 milla)
- Ver todos los hoteles de cada location
- Modificar las coordenadas de cada hotel
- Ajustar el radio del geofence de cada hotel (máx. 0.1 millas)

---

## Conceptos Clave

### 1. **Location (Aeropuerto/Ubicación)**

Una **Location** representa un aeropuerto o base de operaciones. Tiene:

- **Coordenadas:** Almacenadas en formato GeoJSON Point en el campo `point`
- **Geofence:** Radio circular alrededor del punto, en millas (campo `radio_zone`)
- **Límite:** Máximo 1.0 milla (1609.344 metros)
- **Formato GeoJSON:**
  ```json
  {
    "type": "Point",
    "coordinates": [-85.7585, 38.2527]  // [longitude, latitude]
  }
  ```

### 2. **Hotel**

Un **Hotel** pertenece a una Location. Tiene:

- **Coordenadas:** Almacenadas en formato GeoJSON Point en el campo `point`
- **Geofence:** Radio circular alrededor del punto, en millas (campo `radio_zone`)
- **Límite:** Máximo 0.1 millas (~160.934 metros)
- **Formato GeoJSON:** Igual que Location

### 3. **Formato GeoJSON Point**

```json
{
  "type": "Point",
  "coordinates": [longitude, latitude]
}
```

⚠️ **IMPORTANTE:** El orden es `[longitude, latitude]`, NO `[latitude, longitude]`

**Conversión desde Google Maps / Mapbox:**

```typescript
// Google Maps devuelve: { lat: 38.2527, lng: -85.7585 }
// Debes convertir a GeoJSON:

const toGeoJSON = (lat: number, lng: number) => ({
  type: 'Point',
  coordinates: [lng, lat]  // Invertir el orden
});

// Ejemplo:
const googleMapsLatLng = { lat: 38.2527, lng: -85.7585 };
const geoJSON = toGeoJSON(googleMapsLatLng.lat, googleMapsLatLng.lng);
// Resultado: { type: 'Point', coordinates: [-85.7585, 38.2527] }
```

**Conversión desde GeoJSON a Google Maps / Mapbox:**

```typescript
const fromGeoJSON = (point: GeoJSONPoint) => ({
  lat: point.coordinates[1],
  lng: point.coordinates[0]
});

// Ejemplo:
const geoJSON = { type: 'Point', coordinates: [-85.7585, 38.2527] };
const latLng = fromGeoJSON(geoJSON);
// Resultado: { lat: 38.2527, lng: -85.7585 }
```

---

## Endpoints Disponibles

### 📍 **Locations**

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `GET` | `/v1/locations` | Lista todas las locations de la organización |
| `GET` | `/v1/locations?location_id={id}` | Obtiene una location específica |
| `PATCH` | `/v1/locations/{location_id}` | Actualiza coordenadas y/o geofence |

### 🏨 **Hoteles**

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `GET` | `/v1/locations/{location_id}/hotels` | Lista hoteles de una location (paginado) |
| `PATCH` | `/v1/locations/{location_id}/hotels/{hotel_id}` | Actualiza coordenadas y/o geofence |

---

## Tipos TypeScript

### **GeoJSON Point**

```typescript
interface GeoJSONPoint {
  type: 'Point';
  coordinates: [number, number]; // [longitude, latitude]
}
```

### **Location**

```typescript
interface Location {
  id: string;
  organization_id: string;
  name: string;
  address: string | null;
  point: GeoJSONPoint | null;
  radio_zone: number | null;  // En millas (máx 1.0)
  validation_status: 'NEEDS_VALIDATION' | 'VALIDATED' | 'DISABLED';
  provider: string | null;
  timezone: string;
  created_at: string;  // ISO 8601
}
```

### **Hotel**

```typescript
interface Hotel {
  id: string;
  name: string;
  location_id: string;
  address: string | null;
  point: GeoJSONPoint | null;
  radio_zone: number | null;  // En millas (máx 0.1)
  validation_status: 'NEEDS_VALIDATION' | 'VALIDATED' | 'DISABLED';
  validated_at: string | null;  // ISO 8601
  validated_by: string | null;
  last_modified_at: string | null;  // ISO 8601
  last_modified_by: string | null;
  created_at: string;  // ISO 8601
  updated_at: string;  // ISO 8601
}
```

### **Request Bodies para PATCH**

```typescript
interface LocationUpdateRequest {
  point?: GeoJSONPoint;
  radio_zone?: number;  // 0.0 - 1.0 millas
  address?: string;
  validation_status?: 'NEEDS_VALIDATION' | 'VALIDATED' | 'DISABLED';
}

interface HotelUpdateRequest {
  point?: GeoJSONPoint;
  radio_zone?: number;  // 0.0 - 0.1 millas
  address?: string;
  validation_status?: 'NEEDS_VALIDATION' | 'VALIDATED' | 'DISABLED';
}
```

---

## Obtener Datos (GET)

### 1️⃣ **Listar Todas las Locations de la Organización**

```typescript
// Request
GET /v1/locations
Authorization: Bearer {token}

// Response
{
  "data": [
    {
      "id": "a1b2c3d4-...",
      "organization_id": "org-uuid",
      "name": "Louisville International Airport",
      "address": "600 Terminal Dr, Louisville, KY 40209",
      "point": {
        "type": "Point",
        "coordinates": [-85.7585, 38.2527]
      },
      "radio_zone": 1.0,
      "validation_status": "VALIDATED",
      "provider": "google",
      "timezone": "America/New_York",
      "created_at": "2025-01-15T10:00:00Z"
    },
    {
      "id": "e5f6g7h8-...",
      "name": "Cincinnati Airport",
      "point": {
        "type": "Point",
        "coordinates": [-84.6678, 39.0488]
      },
      "radio_zone": 0.8,
      // ... más campos
    }
  ]
}
```

**Código TypeScript:**

```typescript
async function getLocations(): Promise<Location[]> {
  const response = await fetch('/api/v1/locations', {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error(`Error ${response.status}: ${response.statusText}`);
  }

  const data = await response.json();
  return data.data;
}

// Uso:
const locations = await getLocations();
console.log(locations);
```

### 2️⃣ **Obtener una Location Específica**

```typescript
// Request
GET /v1/locations?location_id=a1b2c3d4-...
Authorization: Bearer {token}

// Response
{
  "data": {
    "id": "a1b2c3d4-...",
    "name": "Louisville International Airport",
    "point": {
      "type": "Point",
      "coordinates": [-85.7585, 38.2527]
    },
    "radio_zone": 1.0,
    // ... más campos
  }
}
```

**Código TypeScript:**

```typescript
async function getLocation(locationId: string): Promise<Location> {
  const response = await fetch(`/api/v1/locations?location_id=${locationId}`, {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error(`Error ${response.status}: ${response.statusText}`);
  }

  const data = await response.json();
  return data.data;
}
```

### 3️⃣ **Listar Hoteles de una Location**

```typescript
// Request
GET /v1/locations/{location_id}/hotels?skip=0&limit=100
Authorization: Bearer {token}

// Response
{
  "data": [
    {
      "id": "hotel-uuid-1",
      "name": "Marriott Airport Hotel",
      "location_id": "a1b2c3d4-...",
      "address": "456 Hotel St, Louisville, KY",
      "point": {
        "type": "Point",
        "coordinates": [-85.7400, 38.1800]
      },
      "radio_zone": 0.05,
      "validation_status": "VALIDATED",
      "validated_at": "2025-01-10T11:00:00Z",
      "validated_by": "manager-uuid",
      "created_at": "2025-01-10T10:00:00Z",
      "updated_at": "2025-01-10T11:00:00Z"
    },
    {
      "id": "hotel-uuid-2",
      "name": "Holiday Inn Express",
      "address": "789 Express Way, Louisville, KY",
      "point": {
        "type": "Point",
        "coordinates": [-85.7550, 38.1850]
      },
      "radio_zone": 0.08,
      "validation_status": "NEEDS_VALIDATION",
      // ... más campos
    }
  ],
  "skip": 0,
  "limit": 100,
  "total": 2
}
```

**Código TypeScript:**

```typescript
interface HotelsResponse {
  data: Hotel[];
  skip: number;
  limit: number;
  total: number;
}

async function getHotels(
  locationId: string,
  options?: { skip?: number; limit?: number; name?: string }
): Promise<HotelsResponse> {
  const params = new URLSearchParams({
    skip: String(options?.skip ?? 0),
    limit: String(options?.limit ?? 100),
    ...(options?.name && { name: options.name }),
  });

  const response = await fetch(
    `/api/v1/locations/${locationId}/hotels?${params}`,
    {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    }
  );

  if (!response.ok) {
    throw new Error(`Error ${response.status}: ${response.statusText}`);
  }

  return response.json();
}

// Uso:
const { data: hotels, total } = await getHotels('location-uuid', { limit: 50 });
console.log(`Encontrados ${total} hoteles:`, hotels);
```

### 4️⃣ **Obtener Location con Hoteles (2 llamadas en paralelo)**

```typescript
async function getLocationWithHotels(locationId: string) {
  const [location, hotelsResponse] = await Promise.all([
    getLocation(locationId),
    getHotels(locationId, { limit: 100 })
  ]);

  return {
    location,
    hotels: hotelsResponse.data,
    totalHotels: hotelsResponse.total
  };
}

// Uso:
const { location, hotels, totalHotels } = await getLocationWithHotels('location-uuid');
console.log(`Location: ${location.name}`);
console.log(`Tiene ${totalHotels} hoteles`);
```

---

## Actualizar Geofences (PATCH)

### 1️⃣ **Actualizar Location (Coordenadas y/o Geofence)**

```typescript
// Request
PATCH /v1/locations/{location_id}
Authorization: Bearer {token}
Content-Type: application/json

{
  "point": {
    "type": "Point",
    "coordinates": [-85.7585, 38.2527]
  },
  "radio_zone": 0.8,
  "address": "600 Terminal Dr, Louisville, KY 40209",
  "validation_status": "VALIDATED"
}

// Response
{
  "status": "ok",
  "location": {
    "id": "a1b2c3d4-...",
    "name": "Louisville International Airport",
    "point": {
      "type": "Point",
      "coordinates": [-85.7585, 38.2527]
    },
    "radio_zone": 0.8,
    "address": "600 Terminal Dr, Louisville, KY 40209",
    "validation_status": "VALIDATED",
    // ... más campos actualizados
  }
}
```

**Código TypeScript:**

```typescript
async function updateLocation(
  locationId: string,
  updates: LocationUpdateRequest
): Promise<Location> {
  const response = await fetch(`/api/v1/locations/${locationId}`, {
    method: 'PATCH',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(updates),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Error ${response.status}`);
  }

  const data = await response.json();
  return data.location;
}

// Ejemplo 1: Actualizar solo coordenadas
const updatedLocation = await updateLocation('location-uuid', {
  point: {
    type: 'Point',
    coordinates: [-85.7585, 38.2527]
  }
});

// Ejemplo 2: Actualizar solo radio del geofence
await updateLocation('location-uuid', {
  radio_zone: 0.9
});

// Ejemplo 3: Actualizar todo
await updateLocation('location-uuid', {
  point: {
    type: 'Point',
    coordinates: [-85.7585, 38.2527]
  },
  radio_zone: 1.0,
  address: 'Nueva dirección',
  validation_status: 'VALIDATED'
});
```

**Desde Google Maps (arrastrar marcador):**

```typescript
// Usuario arrastra el marcador en Google Maps
function onLocationMarkerDragEnd(event: google.maps.MapMouseEvent) {
  const newLatLng = event.latLng;
  if (!newLatLng) return;

  const lat = newLatLng.lat();
  const lng = newLatLng.lng();

  // Convertir a GeoJSON
  const geoJSONPoint: GeoJSONPoint = {
    type: 'Point',
    coordinates: [lng, lat]  // Orden correcto
  };

  // Actualizar en el backend
  updateLocation(currentLocationId, {
    point: geoJSONPoint,
    validation_status: 'VALIDATED'
  })
    .then(() => {
      toast.success('Ubicación actualizada correctamente');
    })
    .catch(error => {
      toast.error('Error al actualizar: ' + error.message);
    });
}
```

### 2️⃣ **Actualizar Hotel (Coordenadas y/o Geofence)**

```typescript
// Request
PATCH /v1/locations/{location_id}/hotels/{hotel_id}
Authorization: Bearer {token}
Content-Type: application/json

{
  "point": {
    "type": "Point",
    "coordinates": [-85.7400, 38.1800]
  },
  "radio_zone": 0.06,
  "address": "456 Hotel St, Louisville, KY",
  "validation_status": "VALIDATED"
}

// Response
{
  "status": "ok",
  "hotel": {
    "id": "hotel-uuid",
    "name": "Marriott Airport Hotel",
    "location_id": "location-uuid",
    "point": {
      "type": "Point",
      "coordinates": [-85.7400, 38.1800]
    },
    "radio_zone": 0.06,
    "address": "456 Hotel St, Louisville, KY",
    "validation_status": "VALIDATED",
    "validated_at": "2026-02-05T15:30:00Z",
    "validated_by": "manager-uuid",
    // ... más campos actualizados
  }
}
```

**Código TypeScript:**

```typescript
async function updateHotel(
  locationId: string,
  hotelId: string,
  updates: HotelUpdateRequest
): Promise<Hotel> {
  const response = await fetch(
    `/api/v1/locations/${locationId}/hotels/${hotelId}`,
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
    const error = await response.json();
    throw new Error(error.detail || `Error ${response.status}`);
  }

  const data = await response.json();
  return data.hotel;
}

// Ejemplo 1: Actualizar solo coordenadas del hotel
await updateHotel('location-uuid', 'hotel-uuid', {
  point: {
    type: 'Point',
    coordinates: [-85.7400, 38.1800]
  },
  validation_status: 'VALIDATED'
});

// Ejemplo 2: Actualizar solo radio del geofence
await updateHotel('location-uuid', 'hotel-uuid', {
  radio_zone: 0.05
});

// Ejemplo 3: Actualizar todo
await updateHotel('location-uuid', 'hotel-uuid', {
  point: {
    type: 'Point',
    coordinates: [-85.7400, 38.1800]
  },
  radio_zone: 0.08,
  address: 'Nueva dirección del hotel',
  validation_status: 'VALIDATED'
});
```

---

## Servicios Frontend

### **geofence.service.ts**

```typescript
// src/services/geofence.service.ts

import { API_BASE_URL } from '@/config';

export interface GeoJSONPoint {
  type: 'Point';
  coordinates: [number, number]; // [longitude, latitude]
}

export interface Location {
  id: string;
  organization_id: string;
  name: string;
  address: string | null;
  point: GeoJSONPoint | null;
  radio_zone: number | null;
  validation_status: 'NEEDS_VALIDATION' | 'VALIDATED' | 'DISABLED';
  provider: string | null;
  timezone: string;
  created_at: string;
}

export interface Hotel {
  id: string;
  name: string;
  location_id: string;
  address: string | null;
  point: GeoJSONPoint | null;
  radio_zone: number | null;
  validation_status: 'NEEDS_VALIDATION' | 'VALIDATED' | 'DISABLED';
  validated_at: string | null;
  validated_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface LocationUpdateRequest {
  point?: GeoJSONPoint;
  radio_zone?: number;
  address?: string;
  validation_status?: 'NEEDS_VALIDATION' | 'VALIDATED' | 'DISABLED';
}

export interface HotelUpdateRequest {
  point?: GeoJSONPoint;
  radio_zone?: number;
  address?: string;
  validation_status?: 'NEEDS_VALIDATION' | 'VALIDATED' | 'DISABLED';
}

export interface HotelsResponse {
  data: Hotel[];
  skip: number;
  limit: number;
  total: number;
}

class GeofenceService {
  private getHeaders() {
    const token = localStorage.getItem('token');
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    };
  }

  // ========== LOCATIONS ==========

  async getLocations(): Promise<Location[]> {
    const response = await fetch(`${API_BASE_URL}/v1/locations`, {
      headers: this.getHeaders(),
    });

    if (!response.ok) {
      throw new Error(`Error ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    return data.data;
  }

  async getLocation(locationId: string): Promise<Location> {
    const response = await fetch(
      `${API_BASE_URL}/v1/locations?location_id=${locationId}`,
      {
        headers: this.getHeaders(),
      }
    );

    if (!response.ok) {
      throw new Error(`Error ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    return data.data;
  }

  async updateLocation(
    locationId: string,
    updates: LocationUpdateRequest
  ): Promise<Location> {
    const response = await fetch(
      `${API_BASE_URL}/v1/locations/${locationId}`,
      {
        method: 'PATCH',
        headers: this.getHeaders(),
        body: JSON.stringify(updates),
      }
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || `Error ${response.status}`);
    }

    const data = await response.json();
    return data.location;
  }

  // ========== HOTELS ==========

  async getHotels(
    locationId: string,
    options?: { skip?: number; limit?: number; name?: string }
  ): Promise<HotelsResponse> {
    const params = new URLSearchParams({
      skip: String(options?.skip ?? 0),
      limit: String(options?.limit ?? 100),
      ...(options?.name && { name: options.name }),
    });

    const response = await fetch(
      `${API_BASE_URL}/v1/locations/${locationId}/hotels?${params}`,
      {
        headers: this.getHeaders(),
      }
    );

    if (!response.ok) {
      throw new Error(`Error ${response.status}: ${response.statusText}`);
    }

    return response.json();
  }

  async updateHotel(
    locationId: string,
    hotelId: string,
    updates: HotelUpdateRequest
  ): Promise<Hotel> {
    const response = await fetch(
      `${API_BASE_URL}/v1/locations/${locationId}/hotels/${hotelId}`,
      {
        method: 'PATCH',
        headers: this.getHeaders(),
        body: JSON.stringify(updates),
      }
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || `Error ${response.status}`);
    }

    const data = await response.json();
    return data.hotel;
  }

  // ========== HELPERS ==========

  /**
   * Convierte coordenadas de Google Maps/Mapbox a GeoJSON Point
   */
  toGeoJSON(latitude: number, longitude: number): GeoJSONPoint {
    return {
      type: 'Point',
      coordinates: [longitude, latitude],
    };
  }

  /**
   * Convierte GeoJSON Point a coordenadas de Google Maps/Mapbox
   */
  fromGeoJSON(point: GeoJSONPoint): { lat: number; lng: number } {
    return {
      lat: point.coordinates[1],
      lng: point.coordinates[0],
    };
  }

  /**
   * Convierte millas a metros
   */
  milesToMeters(miles: number): number {
    return miles * 1609.344;
  }

  /**
   * Convierte metros a millas
   */
  metersToMiles(meters: number): number {
    return meters / 1609.344;
  }
}

export const geofenceService = new GeofenceService();
```

---

## Componentes UI Recomendados

### 1️⃣ **Settings Page - Geofences Management**

```tsx
// src/pages/settings/geofences/index.tsx

import { useState, useEffect } from 'react';
import { geofenceService, Location } from '@/services/geofence.service';
import { LocationCard } from './LocationCard';
import { toast } from 'react-hot-toast';

export function GeofencesSettingsPage() {
  const [locations, setLocations] = useState<Location[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadLocations();
  }, []);

  async function loadLocations() {
    try {
      setLoading(true);
      setError(null);
      const data = await geofenceService.getLocations();
      setLocations(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al cargar locations');
      toast.error('Error al cargar locations');
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return <div className="p-8">Cargando locations...</div>;
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-800">{error}</p>
          <button
            onClick={loadLocations}
            className="mt-2 text-red-600 underline"
          >
            Reintentar
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">
          Gestión de Geofences
        </h1>
        <p className="mt-2 text-gray-600">
          Configura las coordenadas y radios de geofence para tus locations y hoteles
        </p>
      </div>

      {locations.length === 0 ? (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-8 text-center">
          <p className="text-gray-600">No hay locations configuradas</p>
        </div>
      ) : (
        <div className="space-y-4">
          {locations.map(location => (
            <LocationCard
              key={location.id}
              location={location}
              onUpdate={loadLocations}
            />
          ))}
        </div>
      )}
    </div>
  );
}
```

### 2️⃣ **Location Card (Expandible)**

```tsx
// src/pages/settings/geofences/LocationCard.tsx

import { useState } from 'react';
import { Location } from '@/services/geofence.service';
import { LocationMapEditor } from './LocationMapEditor';
import { HotelsList } from './HotelsList';
import { ChevronDown, ChevronUp, MapPin } from 'lucide-react';

interface LocationCardProps {
  location: Location;
  onUpdate: () => void;
}

export function LocationCard({ location, onUpdate }: LocationCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const hasCoordinates = location.point !== null;
  const coordinates = hasCoordinates
    ? `${location.point!.coordinates[1].toFixed(4)}, ${location.point!.coordinates[0].toFixed(4)}`
    : 'Sin configurar';

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-6 py-4 bg-white hover:bg-gray-50 transition-colors flex items-center justify-between"
      >
        <div className="flex items-center gap-4">
          <MapPin className="w-5 h-5 text-gray-400" />
          <div className="text-left">
            <h3 className="font-semibold text-gray-900">{location.name}</h3>
            <p className="text-sm text-gray-600">{coordinates}</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {location.radio_zone && (
            <span className="text-sm text-gray-600">
              Radio: {location.radio_zone} mi
            </span>
          )}
          <span className={`
            px-2 py-1 rounded-full text-xs font-medium
            ${location.validation_status === 'VALIDATED'
              ? 'bg-green-100 text-green-800'
              : 'bg-yellow-100 text-yellow-800'
            }
          `}>
            {location.validation_status === 'VALIDATED' ? 'Validado' : 'Pendiente'}
          </span>
          {isExpanded ? (
            <ChevronUp className="w-5 h-5 text-gray-400" />
          ) : (
            <ChevronDown className="w-5 h-5 text-gray-400" />
          )}
        </div>
      </button>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="border-t border-gray-200 bg-gray-50">
          <div className="p-6 space-y-6">
            {/* Location Map Editor */}
            <LocationMapEditor location={location} onUpdate={onUpdate} />

            {/* Hotels List */}
            <HotelsList locationId={location.id} />
          </div>
        </div>
      )}
    </div>
  );
}
```

### 3️⃣ **Location Map Editor**

```tsx
// src/pages/settings/geofences/LocationMapEditor.tsx

import { useState, useCallback } from 'react';
import { GoogleMap, Marker, Circle } from '@react-google-maps/api';
import { geofenceService, Location } from '@/services/geofence.service';
import { toast } from 'react-hot-toast';

interface LocationMapEditorProps {
  location: Location;
  onUpdate: () => void;
}

export function LocationMapEditor({ location, onUpdate }: LocationMapEditorProps) {
  const [isSaving, setIsSaving] = useState(false);
  const [radius, setRadius] = useState(location.radio_zone || 1.0);

  const center = location.point
    ? geofenceService.fromGeoJSON(location.point)
    : { lat: 38.2527, lng: -85.7585 };

  const handleMarkerDragEnd = useCallback(
    async (event: google.maps.MapMouseEvent) => {
      if (!event.latLng) return;

      const lat = event.latLng.lat();
      const lng = event.latLng.lng();

      setIsSaving(true);
      try {
        await geofenceService.updateLocation(location.id, {
          point: geofenceService.toGeoJSON(lat, lng),
          validation_status: 'VALIDATED'
        });

        toast.success('Coordenadas actualizadas');
        onUpdate();
      } catch (error) {
        toast.error('Error al actualizar: ' + (error as Error).message);
      } finally {
        setIsSaving(false);
      }
    },
    [location.id, onUpdate]
  );

  const handleRadiusChange = async (newRadius: number) => {
    if (newRadius < 0 || newRadius > 1.0) {
      toast.error('El radio debe estar entre 0 y 1.0 millas');
      return;
    }

    setRadius(newRadius);

    try {
      await geofenceService.updateLocation(location.id, {
        radio_zone: newRadius
      });

      toast.success('Radio actualizado');
      onUpdate();
    } catch (error) {
      toast.error('Error al actualizar radio');
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="font-semibold text-gray-900">Ubicación del Aeropuerto</h4>
        {isSaving && (
          <span className="text-sm text-blue-600">Guardando...</span>
        )}
      </div>

      {/* Map */}
      <div className="h-96 rounded-lg overflow-hidden border border-gray-300">
        <GoogleMap
          mapContainerStyle={{ width: '100%', height: '100%' }}
          center={center}
          zoom={13}
        >
          <Marker
            position={center}
            draggable
            onDragEnd={handleMarkerDragEnd}
          />

          {location.point && (
            <Circle
              center={center}
              radius={geofenceService.milesToMeters(radius)}
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

      {/* Radius Slider */}
      <div className="space-y-2">
        <label className="block text-sm font-medium text-gray-700">
          Radio del Geofence: {radius.toFixed(2)} millas ({geofenceService.milesToMeters(radius).toFixed(0)} metros)
        </label>
        <input
          type="range"
          min="0"
          max="1.0"
          step="0.05"
          value={radius}
          onChange={(e) => handleRadiusChange(parseFloat(e.target.value))}
          className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
        />
        <div className="flex justify-between text-xs text-gray-500">
          <span>0 mi</span>
          <span>0.5 mi</span>
          <span>1.0 mi (máx.)</span>
        </div>
      </div>

      {/* Coordinates Display */}
      {location.point && (
        <div className="text-sm text-gray-600">
          <p>Latitud: {location.point.coordinates[1].toFixed(6)}</p>
          <p>Longitud: {location.point.coordinates[0].toFixed(6)}</p>
        </div>
      )}
    </div>
  );
}
```

### 4️⃣ **Hotels List**

```tsx
// src/pages/settings/geofences/HotelsList.tsx

import { useState, useEffect } from 'react';
import { geofenceService, Hotel } from '@/services/geofence.service';
import { HotelCard } from './HotelCard';

interface HotelsListProps {
  locationId: string;
}

export function HotelsList({ locationId }: HotelsListProps) {
  const [hotels, setHotels] = useState<Hotel[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadHotels();
  }, [locationId]);

  async function loadHotels() {
    try {
      setLoading(true);
      const response = await geofenceService.getHotels(locationId, { limit: 100 });
      setHotels(response.data);
    } catch (error) {
      console.error('Error loading hotels:', error);
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return <div className="text-sm text-gray-600">Cargando hoteles...</div>;
  }

  if (hotels.length === 0) {
    return (
      <div className="bg-gray-100 rounded-lg p-4 text-center">
        <p className="text-gray-600">No hay hoteles configurados</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h4 className="font-semibold text-gray-900">
        Hoteles ({hotels.length})
      </h4>

      <div className="space-y-2">
        {hotels.map(hotel => (
          <HotelCard
            key={hotel.id}
            hotel={hotel}
            locationId={locationId}
            onUpdate={loadHotels}
          />
        ))}
      </div>
    </div>
  );
}
```

### 5️⃣ **Hotel Card (Similar a Location Card)**

```tsx
// src/pages/settings/geofences/HotelCard.tsx

import { useState } from 'react';
import { Hotel } from '@/services/geofence.service';
import { HotelMapEditor } from './HotelMapEditor';
import { ChevronDown, ChevronUp, Building2 } from 'lucide-react';

interface HotelCardProps {
  hotel: Hotel;
  locationId: string;
  onUpdate: () => void;
}

export function HotelCard({ hotel, locationId, onUpdate }: HotelCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const hasCoordinates = hotel.point !== null;
  const coordinates = hasCoordinates
    ? `${hotel.point!.coordinates[1].toFixed(4)}, ${hotel.point!.coordinates[0].toFixed(4)}`
    : 'Sin configurar';

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden bg-white">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-3 hover:bg-gray-50 transition-colors flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <Building2 className="w-4 h-4 text-gray-400" />
          <div className="text-left">
            <h5 className="font-medium text-gray-900">{hotel.name}</h5>
            <p className="text-xs text-gray-500">{coordinates}</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {hotel.radio_zone && (
            <span className="text-xs text-gray-600">
              {hotel.radio_zone} mi
            </span>
          )}
          <span className={`
            px-2 py-0.5 rounded-full text-xs font-medium
            ${hotel.validation_status === 'VALIDATED'
              ? 'bg-green-100 text-green-700'
              : 'bg-yellow-100 text-yellow-700'
            }
          `}>
            {hotel.validation_status === 'VALIDATED' ? '✓' : '!'}
          </span>
          {isExpanded ? (
            <ChevronUp className="w-4 h-4 text-gray-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-gray-400" />
          )}
        </div>
      </button>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="border-t border-gray-200 bg-gray-50 p-4">
          <HotelMapEditor
            hotel={hotel}
            locationId={locationId}
            onUpdate={onUpdate}
          />
        </div>
      )}
    </div>
  );
}
```

---

## Flujo Completo de Usuario

### **Escenario: Manager actualiza geofence de aeropuerto**

1. **Usuario navega a Settings → Geofences**
2. **Sistema carga** todas las locations con `GET /v1/locations`
3. **Usuario hace clic** en una location para expandir
4. **Sistema muestra**:
   - Mapa con marcador en la ubicación actual
   - Círculo mostrando el radio del geofence
   - Slider para ajustar el radio
5. **Usuario arrastra el marcador** a nueva posición
6. **Sistema envía** `PATCH /v1/locations/{id}` con nuevo `point`
7. **Backend actualiza** coordenadas y devuelve location actualizada
8. **Mapa se actualiza** con nueva posición
9. **Usuario ajusta slider** del radio
10. **Sistema envía** `PATCH /v1/locations/{id}` con nuevo `radio_zone`
11. **Círculo se redibuja** con nuevo radio

### **Escenario: Manager actualiza geofence de hotel**

1. **En la misma página**, dentro de la location expandida
2. **Sistema muestra lista de hoteles** cargados con `GET /v1/locations/{id}/hotels`
3. **Usuario hace clic** en un hotel para expandir
4. **Sistema muestra mapa** del hotel con su geofence
5. **Usuario arrastra marcador** del hotel
6. **Sistema envía** `PATCH /v1/locations/{location_id}/hotels/{hotel_id}` con nuevo `point`
7. **Hotel se actualiza** en la UI

---

## Validaciones y Límites

### **Validaciones en el Frontend**

```typescript
// Validar radio de location
function validateLocationRadius(radius: number): string | null {
  if (radius < 0) return 'El radio no puede ser negativo';
  if (radius > 1.0) return 'El radio máximo es 1.0 millas';
  return null;
}

// Validar radio de hotel
function validateHotelRadius(radius: number): string | null {
  if (radius < 0) return 'El radio no puede ser negativo';
  if (radius > 0.1) return 'El radio máximo es 0.1 millas (~160 metros)';
  return null;
}

// Validar coordenadas
function validateCoordinates(lat: number, lng: number): string | null {
  if (lat < -90 || lat > 90) return 'Latitud inválida (debe estar entre -90 y 90)';
  if (lng < -180 || lng > 180) return 'Longitud inválida (debe estar entre -180 y 180)';
  return null;
}
```

### **Límites del Sistema**

| Entidad | Campo | Mínimo | Máximo | Unidad |
|---------|-------|--------|--------|--------|
| **Location** | `radio_zone` | 0.0 | 1.0 | millas |
| **Location** | `radio_zone` | 0 | 1609.344 | metros |
| **Hotel** | `radio_zone` | 0.0 | 0.1 | millas |
| **Hotel** | `radio_zone` | 0 | 160.934 | metros |

### **Errores Comunes del Backend**

```typescript
// 400 Bad Request
{
  "detail": "ID de location inválido"
}

// 404 Not Found
{
  "detail": "Location no encontrada"
}

// 422 Validation Error (radio excede límite)
{
  "detail": [
    {
      "loc": ["body", "radio_zone"],
      "msg": "Radio exceeds maximum allowed (1.0 miles)",
      "type": "value_error"
    }
  ]
}
```

### **Manejo de Errores en el Frontend**

```typescript
async function updateLocationWithErrorHandling(
  locationId: string,
  updates: LocationUpdateRequest
) {
  try {
    // Validar antes de enviar
    if (updates.radio_zone !== undefined) {
      const error = validateLocationRadius(updates.radio_zone);
      if (error) {
        toast.error(error);
        return;
      }
    }

    const updated = await geofenceService.updateLocation(locationId, updates);
    toast.success('Location actualizada correctamente');
    return updated;

  } catch (error) {
    if (error instanceof Error) {
      // Errores específicos del backend
      if (error.message.includes('404')) {
        toast.error('Location no encontrada');
      } else if (error.message.includes('400')) {
        toast.error('Datos inválidos');
      } else {
        toast.error('Error al actualizar: ' + error.message);
      }
    }
    throw error;
  }
}
```

---

## Resumen de Implementación

### **Paso 1: Crear el servicio**
- Copia `geofence.service.ts` a tu proyecto
- Ajusta `API_BASE_URL` según tu configuración

### **Paso 2: Crear componentes UI**
- `GeofencesSettingsPage` - Página principal
- `LocationCard` - Card expandible por location
- `LocationMapEditor` - Editor de mapa para location
- `HotelsList` - Lista de hoteles
- `HotelCard` - Card expandible por hotel
- `HotelMapEditor` - Editor de mapa para hotel

### **Paso 3: Integrar con Google Maps**
```bash
npm install @react-google-maps/api
```

### **Paso 4: Configurar rutas**
```tsx
// En tu router
import { GeofencesSettingsPage } from '@/pages/settings/geofences';

<Route path="/settings/geofences" element={<GeofencesSettingsPage />} />
```

### **Paso 5: Agregar al menú de Settings**
```tsx
<Link to="/settings/geofences">
  <MapPin className="w-5 h-5" />
  Geofences
</Link>
```

---

## Próximos Pasos

1. ✅ **Endpoints ya existen y funcionan**
2. ⚠️ **Falta crear** `GET /v1/locations/{location_id}/details` (opcional, para 1 sola llamada)
3. ✅ **Documentación completa**
4. 🚀 **Listo para implementar en el frontend**

---

## Soporte y Preguntas

Si tienes dudas sobre:
- **Formato GeoJSON** → Recuerda siempre `[longitude, latitude]`
- **Límites de radio** → Location max 1.0 mi, Hotel max 0.1 mi
- **Validaciones** → El backend rechazará valores fuera de rango
- **Coordenadas** → Usa los helpers `toGeoJSON()` y `fromGeoJSON()`

---

**Última actualización:** 2026-02-05
**Autor:** GT360 Backend Team
