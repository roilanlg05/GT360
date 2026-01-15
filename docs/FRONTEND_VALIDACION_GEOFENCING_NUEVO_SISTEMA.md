# Sistema de Validaciones de Aeropuertos y Hoteles - Guia Frontend

**Fecha:** 2026-01-10
**Version:** 3.0 - Sistema Actual Simplificado

---

## Resumen Ejecutivo

Este documento describe el **sistema actual** de validacion de geofencing para aeropuertos y hoteles. El sistema antiguo (carpeta `.geofencing/`) esta **completamente deshabilitado** y no debe usarse.

### Estado de los Endpoints

| Sistema | Estado | Ubicacion |
|---------|--------|-----------|
| **Sistema Actual (activo)** | `trips_router.py` | Endpoints `/v1/locations/...` y `/v1/locations/.../hotels/...` |
| **Sistema Viejo (deshabilitado)** | `.geofencing/` | TODO comentado con `'''` y removido de `main.py` |

---

## Arquitectura del Sistema

### Jerarquia de Geocercas

```
+------------------------------------------------------------------+
|                    ORGANIZATION                                   |
|                                                                   |
|  +------------------------------------------------------------+  |
|  |                     LOCATION                                |  |
|  |  - point (centro GeoJSON)                                   |  |
|  |  - radio_zone (geocerca general, max 1 milla)               |  |
|  |  - validation_status                                        |  |
|  |                                                             |  |
|  |  +------------------+       +------------------------+      |  |
|  |  |    AIRPORT       |       |    HOTEL 1             |      |  |
|  |  | (coordenadas     |       | - point (GeoJSON)      |      |  |
|  |  |  predefinidas)   |       | - radio_zone (0.1 mi)  |      |  |
|  |  | - radio_zone     |       | - validation_status    |      |  |
|  |  +------------------+       +------------------------+      |  |
|  |                                                             |  |
|  |                             +------------------------+      |  |
|  |                             |    HOTEL 2             |      |  |
|  |                             | - point (GeoJSON)      |      |  |
|  |                             | - radio_zone (0.1 mi)  |      |  |
|  |                             +------------------------+      |  |
|  +------------------------------------------------------------+  |
+------------------------------------------------------------------+
```

---

## Limites y Constantes

### Radios Maximos por Entidad

| Entidad | Campo | Maximo | Default | Unidad BD | Descripcion |
|---------|-------|--------|---------|-----------|-------------|
| **Location** | `radio_zone` | 1.0 millas | null | millas | Geocerca general (grande) |
| **Hotel** | `radio_zone` | 0.1 millas (~160 m) | null | millas | Geocerca individual de hotel |
| **Airport** | `radio_zone` | 2.0 millas (~3218 m) | 1.0 milla | metros | Geocerca del aeropuerto |

### Constantes en el Codigo

```typescript
// src/constants/geofencing.ts

export const GEOFENCING_LIMITS = {
  // Location (geocerca general grande)
  LOCATION_MAX_RADIUS_MILES: 1.0,

  // Hotel
  HOTEL_MAX_RADIUS_MILES: 0.1,
  HOTEL_MAX_RADIUS_METERS: 160.934,  // 0.1 * 1609.344

  // Airport
  AIRPORT_DEFAULT_RADIUS_METERS: 1609.344,  // 1 milla
  AIRPORT_MAX_RADIUS_METERS: 3218.688,      // 2 millas

  // Conversiones
  METERS_PER_MILE: 1609.344,
};
```

---

## Formato GeoJSON Point

El backend usa **GeoJSON Point** para todas las coordenadas:

```typescript
interface GeoJSONPoint {
  type: "Point";
  coordinates: [longitude, latitude];  // IMPORTANTE: [lon, lat], NO [lat, lon]
}

// Ejemplo:
const hotelPoint: GeoJSONPoint = {
  type: "Point",
  coordinates: [-85.7585, 38.2527]  // [longitude, latitude]
};
```

**ADVERTENCIA:** El orden es `[longitude, latitude]`, que es el opuesto a lo que retornan muchas APIs de mapas.

---

## Endpoints Activos

### 1. Actualizar Location (Geocerca General)

**Endpoint:**
```http
PATCH /v1/locations/{location_id}
Authorization: Bearer {token}
Content-Type: application/json
```

**Body:**
```json
{
  "point": {
    "type": "Point",
    "coordinates": [-85.7585, 38.2527]
  },
  "radio_zone": 0.5,
  "address": "123 Main St, Louisville, KY",
  "validation_status": "VALIDATED"
}
```

**Campos (todos opcionales):**

| Campo | Tipo | Descripcion | Limite |
|-------|------|-------------|--------|
| `point` | GeoJSON Point | Centro de la geocerca | - |
| `radio_zone` | float | Radio en **millas** | max 1.0 |
| `address` | string | Direccion legible | max 255 chars |
| `validation_status` | string | Estado de validacion | NEEDS_VALIDATION, VALIDATED, DISABLED |

**Response:**
```json
{
  "status": "ok",
  "location": {
    "id": "uuid",
    "organization_id": "uuid",
    "name": "SDF",
    "point": {
      "type": "Point",
      "coordinates": [-85.7585, 38.2527]
    },
    "radio_zone": 0.5,
    "address": "123 Main St, Louisville, KY",
    "validation_status": "VALIDATED",
    "timezone": "America/New_York",
    "created_at": "2026-01-10T12:00:00Z"
  }
}
```

---

### 2. Obtener Hoteles de una Location

**Endpoint:**
```http
GET /v1/locations/{location_id}/hotels
Authorization: Bearer {token}
```

**Query Parameters:**

| Parametro | Tipo | Default | Descripcion |
|-----------|------|---------|-------------|
| `name` | string | - | Buscar por nombre (parcial o exacto) |
| `exact` | boolean | false | Si true, busqueda exacta de nombre |
| `skip` | int | 0 | Offset para paginacion |
| `limit` | int | 20 | Cantidad por pagina (max 100) |

**Response:**
```json
{
  "data": [
    {
      "id": "hotel-uuid-1",
      "name": "Hilton Downtown",
      "location_id": "location-uuid",
      "address": null,
      "point": null,
      "radio_zone": null,
      "validation_status": "NEEDS_VALIDATION",
      "validated_at": null,
      "validated_by": null,
      "created_at": "2026-01-10T10:00:00Z",
      "updated_at": "2026-01-10T10:00:00Z"
    },
    {
      "id": "hotel-uuid-2",
      "name": "Marriott Airport",
      "location_id": "location-uuid",
      "address": "456 Airport Rd, Louisville, KY",
      "point": {
        "type": "Point",
        "coordinates": [-85.7400, 38.1800]
      },
      "radio_zone": 0.05,
      "validation_status": "VALIDATED",
      "validated_at": "2026-01-10T11:00:00Z",
      "validated_by": "manager-uuid",
      "created_at": "2026-01-10T10:00:00Z",
      "updated_at": "2026-01-10T11:00:00Z"
    }
  ],
  "skip": 0,
  "limit": 20,
  "total": 15
}
```

---

### 3. Actualizar Hotel (Validar Geofence)

**Endpoint:**
```http
PATCH /v1/locations/{location_id}/hotels/{hotel_id}
Authorization: Bearer {token}
Content-Type: application/json
```

**Body:**
```json
{
  "point": {
    "type": "Point",
    "coordinates": [-85.7400, 38.1800]
  },
  "radio_zone": 0.05,
  "address": "456 Airport Rd, Louisville, KY",
  "validation_status": "VALIDATED"
}
```

**Campos (todos opcionales):**

| Campo | Tipo | Descripcion | Limite |
|-------|------|-------------|--------|
| `point` | GeoJSON Point | Centro de la geocerca del hotel | - |
| `radio_zone` | float | Radio en **millas** | max 0.1 |
| `address` | string | Direccion del hotel | max 250 chars |
| `validation_status` | string | Estado de validacion | NEEDS_VALIDATION, VALIDATED, DISABLED |

**Response:**
```json
{
  "status": "ok",
  "hotel": {
    "id": "hotel-uuid",
    "name": "Marriott Airport",
    "location_id": "location-uuid",
    "address": "456 Airport Rd, Louisville, KY",
    "point": {
      "type": "Point",
      "coordinates": [-85.7400, 38.1800]
    },
    "radio_zone": 0.05,
    "validation_status": "VALIDATED",
    "validated_at": "2026-01-10T11:00:00Z",
    "validated_by": "manager-uuid",
    "created_at": "2026-01-10T10:00:00Z",
    "updated_at": "2026-01-10T11:00:00Z"
  }
}
```

---

## Flujo de Validacion Completo

### Escenario: Manager quiere validar 1 aeropuerto y 3 hoteles

```
+---------------------------------------------------------------+
|  PASO 1: Subir Excel con Schedule                              |
|  POST /v1/trips/upload-trips?airport=SDF&provider=...          |
|                                                                |
|  Response:                                                     |
|  - location_id: "loc-123"                                      |
|  - 3 hoteles creados con validation_status = NEEDS_VALIDATION  |
+---------------------------------------------------------------+
                            |
                            v
+---------------------------------------------------------------+
|  PASO 2: Configurar Location (Geocerca General Grande)         |
|  PATCH /v1/locations/loc-123                                   |
|                                                                |
|  Body:                                                         |
|  {                                                             |
|    "point": {"type":"Point","coordinates":[-85.7585,38.2527]}, |
|    "radio_zone": 0.8,  // 0.8 millas (geocerca general)        |
|    "validation_status": "VALIDATED"                            |
|  }                                                             |
+---------------------------------------------------------------+
                            |
                            v
+---------------------------------------------------------------+
|  PASO 3: Validar Hotel 1 (Hilton Downtown)                     |
|  PATCH /v1/locations/loc-123/hotels/hotel-1                    |
|                                                                |
|  Body:                                                         |
|  {                                                             |
|    "point": {"type":"Point","coordinates":[-85.7600,38.2500]}, |
|    "radio_zone": 0.05,  // 0.05 millas (~80 metros)            |
|    "address": "501 W Main St, Louisville, KY",                 |
|    "validation_status": "VALIDATED"                            |
|  }                                                             |
+---------------------------------------------------------------+
                            |
                            v
+---------------------------------------------------------------+
|  PASO 4: Validar Hotel 2 (Marriott Airport)                    |
|  PATCH /v1/locations/loc-123/hotels/hotel-2                    |
|                                                                |
|  Body:                                                         |
|  {                                                             |
|    "point": {"type":"Point","coordinates":[-85.7400,38.1800]}, |
|    "radio_zone": 0.08,  // 0.08 millas (~130 metros)           |
|    "address": "1921 Bishop Lane, Louisville, KY",              |
|    "validation_status": "VALIDATED"                            |
|  }                                                             |
+---------------------------------------------------------------+
                            |
                            v
+---------------------------------------------------------------+
|  PASO 5: Validar Hotel 3 (Hampton Inn)                         |
|  PATCH /v1/locations/loc-123/hotels/hotel-3                    |
|                                                                |
|  Body:                                                         |
|  {                                                             |
|    "point": {"type":"Point","coordinates":[-85.7550,38.1900]}, |
|    "radio_zone": 0.06,  // 0.06 millas (~97 metros)            |
|    "address": "125 Airport Plaza Dr, Louisville, KY",          |
|    "validation_status": "VALIDATED"                            |
|  }                                                             |
+---------------------------------------------------------------+
```

---

## Notas sobre el Aeropuerto

El aeropuerto tiene un tratamiento especial:

1. **Las coordenadas son fijas** - Vienen de una tabla maestra `entities.airports` y no se pueden modificar desde el frontend
2. **Solo se puede modificar el radio** - A traves de un endpoint especifico (actualmente deshabilitado en el sistema viejo)
3. **El aeropuerto se asocia automaticamente** - Cuando se sube un Excel con `airport=SDF`, el backend busca el aeropuerto en la tabla y usa sus coordenadas

### Schema del Aeropuerto (solo lectura para el frontend)

```typescript
interface Airport {
  id: string;
  code: string;                // "SDF"
  name: string;                // "Louisville International"
  latitude: number;            // 38.2527
  longitude: number;           // -85.7585
  country_code: string;        // "US"
  zone_code: string;           // "EST"
  radio_zone: number | null;   // metros (default: 1609.344 = 1 milla)
}
```

**Nota:** Actualmente NO hay endpoint activo para modificar el `radio_zone` del aeropuerto. Si se necesita, habria que habilitar el endpoint del sistema viejo o crear uno nuevo.

---

## Estados de Validacion

```typescript
type ValidationStatus = "NEEDS_VALIDATION" | "VALIDATED" | "DISABLED";
```

### Transiciones Permitidas

```
[Hotel Creado] -----> NEEDS_VALIDATION
                           |
                           | (Frontend envia point + radio_zone + status)
                           v
                      VALIDATED <--------+
                           |             |
                           | (disable)   | (enable)
                           v             |
                       DISABLED ---------+
```

### Logica de Negocio

| Estado | `point` | `radio_zone` | Genera Eventos Geofence |
|--------|---------|--------------|------------------------|
| NEEDS_VALIDATION | null | null | NO |
| VALIDATED | coordenadas | numero | SI (cuando se habilite el geofencing) |
| DISABLED | coordenadas | numero | NO |

---

## TypeScript - Tipos Completos

```typescript
// ============================================================================
// GeoJSON
// ============================================================================

interface GeoJSONPoint {
  type: "Point";
  coordinates: [number, number];  // [longitude, latitude]
}

// ============================================================================
// Validation Status
// ============================================================================

type ValidationStatus = "NEEDS_VALIDATION" | "VALIDATED" | "DISABLED";

// ============================================================================
// Location
// ============================================================================

interface Location {
  id: string;
  organization_id: string;
  name: string;
  point: GeoJSONPoint | null;
  address: string | null;
  radio_zone: number | null;              // millas (max 1.0)
  validation_status: ValidationStatus;
  provider: string | null;
  timezone: string;
  created_at: string;
}

interface LocationZoneUpdate {
  point?: GeoJSONPoint;
  radio_zone?: number;                    // millas (max 1.0)
  address?: string;
  validation_status?: ValidationStatus;
}

interface LocationUpdateResponse {
  status: "ok";
  location: Location;
}

// ============================================================================
// Hotel
// ============================================================================

interface Hotel {
  id: string;
  name: string;
  location_id: string;
  address: string | null;
  point: GeoJSONPoint | null;
  radio_zone: number | null;              // millas (max 0.1)
  validation_status: ValidationStatus;
  validated_at: string | null;
  validated_by: string | null;
  last_modified_at: string | null;
  last_modified_by: string | null;
  created_at: string;
  updated_at: string;
}

interface HotelPointUpdate {
  point?: GeoJSONPoint;
  radio_zone?: number;                    // millas (max 0.1)
  address?: string;
  validation_status?: ValidationStatus;
}

interface HotelUpdateResponse {
  status: "ok";
  hotel: Hotel;
}

interface HotelsListResponse {
  data: Hotel[];
  skip: number;
  limit: number;
  total: number;
}

// ============================================================================
// Airport (solo lectura)
// ============================================================================

interface Airport {
  id: string;
  code: string;
  name: string;
  latitude: number;
  longitude: number;
  country_code: string;
  zone_code: string;
  radio_zone: number | null;              // metros (max 3218.688)
  last_modified_at: string | null;
  last_modified_by: string | null;
}
```

---

## Ejemplo de Implementacion Frontend

### Servicio de Geofencing

```typescript
// src/services/geofencing.service.ts

import type {
  GeoJSONPoint,
  LocationZoneUpdate,
  HotelPointUpdate,
  Hotel,
  HotelsListResponse
} from '@/types/geofencing';

class GeofencingService {
  private baseUrl = '/api/v1';

  constructor(private getToken: () => string | null) {}

  private get headers(): HeadersInit {
    const token = this.getToken();
    return {
      'Content-Type': 'application/json',
      ...(token && { Authorization: `Bearer ${token}` }),
    };
  }

  // ===== Location =====

  async updateLocation(
    locationId: string,
    data: LocationZoneUpdate
  ): Promise<Location> {
    const response = await fetch(
      `${this.baseUrl}/locations/${locationId}`,
      {
        method: 'PATCH',
        headers: this.headers,
        body: JSON.stringify(data),
      }
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Error actualizando location');
    }

    const result = await response.json();
    return result.location;
  }

  // ===== Hotels =====

  async getHotels(
    locationId: string,
    options: {
      name?: string;
      exact?: boolean;
      skip?: number;
      limit?: number;
    } = {}
  ): Promise<HotelsListResponse> {
    const params = new URLSearchParams();
    if (options.name) params.append('name', options.name);
    if (options.exact) params.append('exact', 'true');
    if (options.skip) params.append('skip', String(options.skip));
    if (options.limit) params.append('limit', String(options.limit));

    const response = await fetch(
      `${this.baseUrl}/locations/${locationId}/hotels?${params}`,
      { headers: this.headers }
    );

    if (!response.ok) {
      throw new Error('Error obteniendo hoteles');
    }

    return response.json();
  }

  async updateHotel(
    locationId: string,
    hotelId: string,
    data: HotelPointUpdate
  ): Promise<Hotel> {
    const response = await fetch(
      `${this.baseUrl}/locations/${locationId}/hotels/${hotelId}`,
      {
        method: 'PATCH',
        headers: this.headers,
        body: JSON.stringify(data),
      }
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Error actualizando hotel');
    }

    const result = await response.json();
    return result.hotel;
  }

  // ===== Helpers =====

  /**
   * Convierte coordenadas de [lat, lon] (formato comun de Maps APIs)
   * a GeoJSON Point [lon, lat] (formato backend)
   */
  toGeoJSON(latitude: number, longitude: number): GeoJSONPoint {
    return {
      type: 'Point',
      coordinates: [longitude, latitude],
    };
  }

  /**
   * Extrae lat/lon de un GeoJSON Point
   */
  fromGeoJSON(point: GeoJSONPoint): { latitude: number; longitude: number } {
    return {
      longitude: point.coordinates[0],
      latitude: point.coordinates[1],
    };
  }
}

// Singleton
export const geofencingService = new GeofencingService(
  () => localStorage.getItem('auth_token')
);
```

### Componente de Validacion de Hotel

```typescript
// src/components/HotelValidationModal.tsx

import React, { useState } from 'react';
import { geofencingService } from '@/services/geofencing.service';
import type { Hotel, HotelPointUpdate } from '@/types/geofencing';

interface Props {
  hotel: Hotel;
  locationId: string;
  onClose: () => void;
  onValidated: (hotel: Hotel) => void;
}

export const HotelValidationModal: React.FC<Props> = ({
  hotel,
  locationId,
  onClose,
  onValidated,
}) => {
  // Estado inicial: coordenadas existentes o null
  const [latitude, setLatitude] = useState<number>(
    hotel.point ? hotel.point.coordinates[1] : 0
  );
  const [longitude, setLongitude] = useState<number>(
    hotel.point ? hotel.point.coordinates[0] : 0
  );
  const [radiusMiles, setRadiusMiles] = useState<number>(
    hotel.radio_zone ?? 0.05
  );
  const [address, setAddress] = useState<string>(hotel.address ?? '');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    // Validaciones
    if (latitude === 0 || longitude === 0) {
      setError('Las coordenadas son requeridas');
      return;
    }
    if (radiusMiles <= 0 || radiusMiles > 0.1) {
      setError('El radio debe estar entre 0 y 0.1 millas');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const updateData: HotelPointUpdate = {
        point: geofencingService.toGeoJSON(latitude, longitude),
        radio_zone: radiusMiles,
        address: address || undefined,
        validation_status: 'VALIDATED',
      };

      const updatedHotel = await geofencingService.updateHotel(
        locationId,
        hotel.id,
        updateData
      );

      onValidated(updatedHotel);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal">
      <h2>Validar Hotel: {hotel.name}</h2>

      {error && <div className="error">{error}</div>}

      <div className="form-group">
        <label>Latitud:</label>
        <input
          type="number"
          step="0.0001"
          value={latitude}
          onChange={(e) => setLatitude(parseFloat(e.target.value))}
        />
      </div>

      <div className="form-group">
        <label>Longitud:</label>
        <input
          type="number"
          step="0.0001"
          value={longitude}
          onChange={(e) => setLongitude(parseFloat(e.target.value))}
        />
      </div>

      <div className="form-group">
        <label>Radio (millas, max 0.1):</label>
        <input
          type="range"
          min="0.01"
          max="0.1"
          step="0.01"
          value={radiusMiles}
          onChange={(e) => setRadiusMiles(parseFloat(e.target.value))}
        />
        <span>{radiusMiles.toFixed(2)} millas (~{Math.round(radiusMiles * 1609.344)} metros)</span>
      </div>

      <div className="form-group">
        <label>Direccion (opcional):</label>
        <input
          type="text"
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          placeholder="123 Main St, City, State"
        />
      </div>

      <div className="actions">
        <button onClick={onClose} disabled={loading}>
          Cancelar
        </button>
        <button onClick={handleSubmit} disabled={loading}>
          {loading ? 'Guardando...' : 'Validar Hotel'}
        </button>
      </div>
    </div>
  );
};
```

---

## Sobre la Geocerca General (Location)

### Que es?

La **geocerca de la Location** es una zona circular grande (hasta 1 milla de radio) que representa el area general de operacion. Esta centrada en el punto definido para la location.

### Para que sirve?

1. **Delimitar zona de interes** - Define el area donde se espera que operen los drivers/crew
2. **Filtrado inicial** - Antes de verificar geocercas individuales de hoteles, se verifica si el usuario esta dentro de la zona de la location
3. **Visualizacion en mapa** - Permite mostrar un circulo general en el dashboard

### Diferencia con Hoteles

| Aspecto | Location | Hotel |
|---------|----------|-------|
| Radio maximo | 1.0 milla | 0.1 milla |
| Proposito | Zona general | Geocerca especifica |
| Cantidad | 1 por location | Multiples por location |

---

## FAQ - Preguntas Frecuentes

### 1. Por que los radios de hoteles estan en millas y no en metros?

Es una decision de diseno del schema. El frontend debe mostrar la conversion a metros si es necesario:
```typescript
const radiusMeters = radiusMiles * 1609.344;
```

### 2. Puedo validar un hotel sin coordenadas?

No. El backend requiere que `point` tenga coordenadas validas para cambiar el status a `VALIDATED`.

### 3. Que pasa si envio un radio mayor al permitido?

El backend rechazara la peticion con un error de constraint:
```json
{
  "detail": "check constraint \"ck_hotel_max_radius\" is violated by some row"
}
```

### 4. Como obtengo las coordenadas del aeropuerto?

Las coordenadas del aeropuerto estan en la respuesta del upload:
```typescript
const response = await uploadSchedule(file, 'SDF', ...);
// response.airport_code = 'SDF'
// El aeropuerto ya tiene coordenadas en la BD, no se pueden modificar
```

### 5. Hay un endpoint para listar aeropuertos?

No en el sistema actual activo. El aeropuerto se asocia automaticamente al crear la location desde el upload.

---

## Endpoints del Sistema Viejo (DESHABILITADOS)

Los siguientes endpoints estan **completamente deshabilitados** y NO deben usarse:

| Endpoint | Estado |
|----------|--------|
| `POST /v1/location/update` | DESHABILITADO |
| `GET /v1/locations/{id}/hotels/pending-validation` | DESHABILITADO |
| `POST /v1/locations/{id}/hotels/{id}/validate` | DESHABILITADO |
| `PATCH /v1/locations/{id}/hotels/{id}/geofence` | DESHABILITADO |
| `POST /v1/locations/{id}/hotels/{id}/disable` | DESHABILITADO |
| `POST /v1/locations/{id}/hotels/{id}/enable` | DESHABILITADO |
| `GET /v1/geofence-events` | DESHABILITADO |
| `GET /v1/organization/geofence-settings` | DESHABILITADO |
| `PATCH /v1/organization/geofence-settings` | DESHABILITADO |
| `GET /v1/locations/{id}/visibility` | DESHABILITADO |
| `PATCH /v1/locations/{id}/visibility` | DESHABILITADO |
| `GET /v1/airports/{id}` | DESHABILITADO |
| `PATCH /v1/airports/{id}/geofence` | DESHABILITADO |

**Razon:** Todo el modulo `.geofencing/` esta comentado con `'''` y los routers no estan registrados en `main.py`.

---

## Resumen de Endpoints Activos

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| `PATCH` | `/v1/locations/{location_id}` | Actualizar location (point, radio_zone, status) |
| `GET` | `/v1/locations/{location_id}/hotels` | Listar hoteles de una location |
| `PATCH` | `/v1/locations/{location_id}/hotels/{hotel_id}` | Actualizar hotel (point, radio_zone, status) |
| `GET` | `/v1/locations` | Listar locations del usuario |
| `DELETE` | `/v1/locations/{location_id}` | Eliminar location y sus hoteles |

---

## Contacto

Si tienes preguntas sobre este documento o necesitas que se habiliten endpoints adicionales, contacta al equipo de backend.

**Ultima actualizacion:** 2026-01-10
