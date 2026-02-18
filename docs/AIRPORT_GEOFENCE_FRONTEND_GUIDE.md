# 🛫 Guía Frontend: Geocercas del Aeropuerto (Detección de Llegada al Parqueo)

**Fecha:** 2026-02-16
**Propósito:** Documentar cómo obtener y pintar la geocerca PEQUEÑA del aeropuerto (diferente de la geocerca general de Location)

---

## 🎯 Resumen Ejecutivo

Hay **TRES tipos de geocercas** en el sistema:

| Tipo | Entidad | Radio Máximo | Propósito | Campo |
|------|---------|--------------|-----------|-------|
| **Location** (grande) | `entities.locations` | 1.0 milla | Geocerca general de la zona | `location.radio_zone` |
| **Airport** (pequeña) ⭐ | `entities.airports` | 2.0 millas | Detectar llegada al parqueo del aeropuerto | `airport.radio_zone` |
| **Hotel** (pequeña) | `entities.hotels` | 0.1 millas | Detectar llegada a hotel | `hotel.radio_zone` |

**El problema:** La geocerca del **aeropuerto** está en una tabla separada (`entities.airports`) y actualmente **NO hay un endpoint activo** para obtenerla.

---

## 🔍 Arquitectura Actual

### 1. Tabla `entities.airports`

```python
# shared/db/schemas/entities/airports.py

DEFAULT_AIRPORT_RADIUS = 1.0  # 1 milla por defecto
MAX_RADIUS = 2.0              # 2 millas máximo

class Airport(PSQLModel):
    id: uuid
    code: str                   # "SDF", "LAX", etc.
    name: str                   # "Louisville International Airport"
    latitude: float             # 38.2527
    longitude: float            # -85.7585
    country_code: str           # "US"
    zone_code: str              # "EST"

    # ⭐ ESTA ES LA GEOCERCA QUE NECESITAS
    radio_zone: float = Column(default=DEFAULT_AIRPORT_RADIUS)  # En MILLAS

    last_modified_at: timestamptz
    last_modified_by: uuid
```

### 2. Tabla `entities.locations`

```python
# shared/db/schemas/entities/locations.py

class Location(PSQLModel):
    id: uuid
    organization_id: uuid
    name: str                   # Código del aeropuerto (ej: "SDF")

    # Coordenadas COPIADAS del Airport al crear la location
    point: jsonb                # GeoJSON { "type": "Point", "coordinates": [lon, lat] }

    # Geocerca GENERAL (grande)
    radio_zone: float           # Max 1.0 milla

    validation_status: str
    provider: str
    timezone: str
    created_at: timestamptz
```

### 3. Relación entre Location y Airport

❌ **NO hay Foreign Key directa**
✅ **Relación implícita:** `location.name == airport.code`

Cuando se crea una Location (al subir un Excel):

```python
# features/trips/routes/trips_router.py, líneas 118-149

# 1. Buscar el aeropuerto por código
stmt = Select(Airport).Where(Airport.code == airport.upper())
airportdb = await session.exec(stmt).first()

# 2. Crear Location con las coordenadas del aeropuerto
location = Location(
    organization_id=organization.id,
    name=airport,                    # ⭐ Guardar código del aeropuerto
    point={
        "type": "Point",
        "coordinates": [
            airportdb.longitude,     # Copiar coordenadas del airport
            airportdb.latitude
        ]
    },
    radio_zone=0.0,                  # ⚠️ Location radio = 0.0 (NO es el del airport)
    provider=provider,
    timezone=tz_from_latlon(airportdb.latitude, airportdb.longitude)
)
```

---

## 🚨 Problema Actual

### Endpoint Deshabilitado

El endpoint para obtener información del aeropuerto **EXISTE** pero está **DESHABILITADO**:

```python
# .geofencing/routes/geofence_router.py (líneas 378-413)
# ⚠️ TODO EL ARCHIVO ESTÁ COMENTADO CON '''

@router.get(
    "/airports/{airport_id}",
    summary="Get airport details",
    description="Get airport details including geofence configuration."
)
async def get_airport(
    request: Request,
    airport_id: str,
    _user: dict = Depends(verify_role(["manager"]))
):
    """Get airport details with geofence info."""
    try:
        airport_uuid = UUID(airport_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid airport_id UUID format")

    async with AsyncSession(engine) as session:
        airport = await session.exec(
            Select(Airport).Where(Airport.id == airport_uuid)
        ).first()

        if not airport:
            raise HTTPException(status_code=404, detail="Airport not found")

        return {
            "id": str(airport.id),
            "code": airport.code,
            "name": airport.name,
            "latitude": airport.latitude,
            "longitude": airport.longitude,
            "country_code": airport.country_code,
            "zone_code": airport.zone_code,
            "radio_zone": airport.radio_zone,  # ⭐ AQUÍ ESTÁ EL RADIO DEL AEROPUERTO
            "last_modified_at": airport.last_modified_at.isoformat() if airport.last_modified_at else None,
            "last_modified_by": str(airport.last_modified_by) if airport.last_modified_by else None
        }
```

**Estado:** Archivo `.geofencing/routes/geofence_router.py` está comentado con `'''` y el router NO está registrado en `main.py`.

---

## ✅ Solución: Crear Endpoint Nuevo

Ya que el endpoint de geofencing está deshabilitado, necesitamos crear un **nuevo endpoint** en `trips_router.py` para obtener la información del aeropuerto.

### Opción 1: Endpoint Independiente para Airport

```python
# features/trips/routes/trips_router.py

@router.get("/v1/locations/{location_id}/airport")
async def get_location_airport(
    location_id: str,
    session: AsyncSession = Depends(get_db),
    _role = Depends(verify_role(["manager", "driver"]))
):
    """
    Obtiene la información del aeropuerto asociado a una location,
    incluyendo su geocerca específica.
    """
    from uuid import UUID

    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de location inválido")

    # Obtener location
    location = await session.get(Location, location_uuid)

    if not location:
        raise HTTPException(status_code=404, detail="Location no encontrada")

    # Buscar aeropuerto por código (location.name contiene el código)
    airport = await session.exec(
        Select(Airport).Where(Airport.code == location.name.upper())
    ).first()

    if not airport:
        raise HTTPException(status_code=404, detail="Aeropuerto no encontrado")

    return JSONResponse(content={
        "status": "ok",
        "airport": {
            "id": str(airport.id),
            "code": airport.code,
            "name": airport.name,
            "latitude": airport.latitude,
            "longitude": airport.longitude,
            "country_code": airport.country_code,
            "zone_code": airport.zone_code,
            "radio_zone": airport.radio_zone,  # ⭐ Geocerca del aeropuerto
            "last_modified_at": airport.last_modified_at.isoformat() if airport.last_modified_at else None,
            "last_modified_by": str(airport.last_modified_by) if airport.last_modified_by else None
        }
    })
```

### Opción 2: Modificar GET /v1/locations para Incluir Airport

```python
# features/trips/routes/trips_router.py

@router.get("/v1/locations")
async def get_locations(
    request: Request,
    session: AsyncSession = Depends(get_db),
    location_id: str | None = None,
    include_airport: bool = Query(False),  # ⭐ Nuevo parámetro
    _role=Depends(verify_role(["manager", "driver"]))
):
    metadata = request.state.user_data
    org_id = metadata.get("organization_id")

    if location_id:
        location = await session.exec(
            Select(Location)
            .Where((Location.id == location_id) & (Location.organization_id == org_id))
        ).first()

        if not location:
            raise HTTPException(status_code=404, detail="Location not found")

        location_data = location.model_dump(mode="json")

        # ⭐ Incluir información del aeropuerto si se solicita
        if include_airport:
            airport = await session.exec(
                Select(Airport).Where(Airport.code == location.name.upper())
            ).first()

            if airport:
                location_data["airport"] = {
                    "id": str(airport.id),
                    "code": airport.code,
                    "name": airport.name,
                    "latitude": airport.latitude,
                    "longitude": airport.longitude,
                    "radio_zone": airport.radio_zone,  # ⭐ Geocerca del aeropuerto
                }

        return JSONResponse(status_code=200, content={"data": location_data})

    # ... resto del código para listar todas las locations
```

---

## 📝 Implementación Recomendada

**Recomendación:** Usar **Opción 1** (endpoint independiente) porque:

1. ✅ Más claro y explícito
2. ✅ No afecta el comportamiento existente de GET /v1/locations
3. ✅ Permite futuras extensiones (como PATCH del radio del aeropuerto)
4. ✅ Sigue el patrón REST (recurso hijo de location)

---

## 🎨 Uso en el Frontend

### 1. TypeScript Types

```typescript
// types/airport.ts

export interface Airport {
  id: string;
  code: string;               // "SDF"
  name: string;               // "Louisville International Airport"
  latitude: number;           // 38.2527
  longitude: number;          // -85.7585
  country_code: string;       // "US"
  zone_code: string;          // "EST"
  radio_zone: number;         // En MILLAS (default 1.0, max 2.0)
  last_modified_at: string | null;
  last_modified_by: string | null;
}

export interface LocationWithAirport {
  location: Location;
  airport: Airport;
}
```

### 2. Servicio API

```typescript
// services/airport.service.ts

import { API_BASE_URL } from '@/config';
import type { Airport } from '@/types/airport';

class AirportService {
  private getHeaders() {
    const token = localStorage.getItem('token');
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    };
  }

  /**
   * Obtiene la información del aeropuerto asociado a una location
   */
  async getAirportForLocation(locationId: string): Promise<Airport> {
    const response = await fetch(
      `${API_BASE_URL}/v1/locations/${locationId}/airport`,
      {
        headers: this.getHeaders(),
      }
    );

    if (!response.ok) {
      throw new Error(`Error ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    return data.airport;
  }

  /**
   * Convierte millas a metros
   */
  milesToMeters(miles: number): number {
    return miles * 1609.344;
  }
}

export const airportService = new AirportService();
```

### 3. Componente de Mapa

```tsx
// components/LocationMapWithAirport.tsx

import { useState, useEffect } from 'react';
import { GoogleMap, Marker, Circle } from '@react-google-maps/api';
import { geofenceService } from '@/services/geofence.service';
import { airportService } from '@/services/airport.service';
import type { Location } from '@/types/location';
import type { Airport } from '@/types/airport';

interface Props {
  locationId: string;
}

export function LocationMapWithAirport({ locationId }: Props) {
  const [location, setLocation] = useState<Location | null>(null);
  const [airport, setAirport] = useState<Airport | null>(null);
  const [hotels, setHotels] = useState<Hotel[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, [locationId]);

  async function loadData() {
    try {
      setLoading(true);

      // Cargar en paralelo
      const [locationData, airportData, hotelsResponse] = await Promise.all([
        geofenceService.getLocation(locationId),
        airportService.getAirportForLocation(locationId),
        geofenceService.getHotels(locationId, { limit: 100 })
      ]);

      setLocation(locationData);
      setAirport(airportData);
      setHotels(hotelsResponse.data);
    } catch (error) {
      console.error('Error loading data:', error);
    } finally {
      setLoading(false);
    }
  }

  if (loading) return <div>Cargando mapa...</div>;
  if (!location || !airport) return <div>No se pudo cargar la información</div>;

  const center = {
    lat: airport.latitude,
    lng: airport.longitude
  };

  return (
    <GoogleMap
      mapContainerStyle={{ width: '100%', height: '600px' }}
      center={center}
      zoom={13}
    >
      {/* 1. Geocerca GRANDE de la Location (general) */}
      {location.radio_zone && location.radio_zone > 0 && (
        <Circle
          center={center}
          radius={geofenceService.milesToMeters(location.radio_zone)}
          options={{
            fillColor: '#10b981',
            fillOpacity: 0.1,
            strokeColor: '#10b981',
            strokeWeight: 1,
            strokeOpacity: 0.3,
          }}
        />
      )}

      {/* 2. Geocerca PEQUEÑA del Aeropuerto (detección de llegada) ⭐ */}
      {airport.radio_zone && (
        <Circle
          center={center}
          radius={airportService.milesToMeters(airport.radio_zone)}
          options={{
            fillColor: '#3b82f6',
            fillOpacity: 0.2,
            strokeColor: '#3b82f6',
            strokeWeight: 2,
          }}
        />
      )}

      {/* 3. Marcador del Aeropuerto */}
      <Marker
        position={center}
        icon={{
          url: '/icons/airport.svg',
          scaledSize: new google.maps.Size(32, 32),
        }}
        label={{
          text: airport.code,
          color: '#1f2937',
          fontSize: '14px',
          fontWeight: 'bold',
        }}
      />

      {/* 4. Hoteles con sus geocercas */}
      {hotels.map(hotel => {
        if (!hotel.point) return null;

        const hotelCoords = geofenceService.fromGeoJSON(hotel.point);

        return (
          <React.Fragment key={hotel.id}>
            {/* Geocerca del hotel */}
            {hotel.radio_zone && (
              <Circle
                center={hotelCoords}
                radius={geofenceService.milesToMeters(hotel.radio_zone)}
                options={{
                  fillColor: '#f59e0b',
                  fillOpacity: 0.15,
                  strokeColor: '#f59e0b',
                  strokeWeight: 1.5,
                }}
              />
            )}

            {/* Marcador del hotel */}
            <Marker
              position={hotelCoords}
              icon={{
                url: '/icons/hotel.svg',
                scaledSize: new google.maps.Size(24, 24),
              }}
              title={hotel.name}
            />
          </React.Fragment>
        );
      })}
    </GoogleMap>
  );
}
```

### 4. Leyenda del Mapa

```tsx
// components/MapLegend.tsx

export function MapLegend() {
  return (
    <div className="absolute bottom-4 right-4 bg-white p-4 rounded-lg shadow-lg">
      <h3 className="font-semibold mb-2">Geocercas</h3>

      <div className="space-y-2">
        {/* Location (grande) */}
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded-full bg-green-500 opacity-20 border-2 border-green-500"></div>
          <span className="text-sm">Location (general, max 1.0 mi)</span>
        </div>

        {/* Airport (pequeña) ⭐ */}
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded-full bg-blue-500 opacity-40 border-2 border-blue-500"></div>
          <span className="text-sm font-medium">Airport (parqueo, max 2.0 mi) ⭐</span>
        </div>

        {/* Hotel */}
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded-full bg-amber-500 opacity-30 border-2 border-amber-500"></div>
          <span className="text-sm">Hotel (max 0.1 mi)</span>
        </div>
      </div>
    </div>
  );
}
```

---

## 📊 Comparación Visual

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                   │
│         Location radio_zone (GRANDE - verde claro)               │
│         Max: 1.0 milla                                           │
│    ┌─────────────────────────────────────────────────┐          │
│    │                                                  │          │
│    │     Airport radio_zone (PEQUEÑA - azul) ⭐      │          │
│    │     Default: 1.0 milla, Max: 2.0 millas         │          │
│    │  ┌────────────────────────────────┐             │          │
│    │  │                                 │             │          │
│    │  │       🛫 AEROPUERTO             │             │          │
│    │  │       Detecta llegada          │             │          │
│    │  │       al parqueo               │             │          │
│    │  │                                 │             │          │
│    │  └────────────────────────────────┘             │          │
│    │                                                  │          │
│    │    🏨 Hotel 1                 🏨 Hotel 2        │          │
│    │    (0.05 mi)                  (0.08 mi)         │          │
│    │                                                  │          │
│    └─────────────────────────────────────────────────┘          │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🔧 Pasos de Implementación

### Backend

1. ✅ Crear endpoint `GET /v1/locations/{location_id}/airport`
2. ✅ Agregar validaciones de permisos (manager/driver)
3. ✅ Probar con Postman/curl
4. ⚠️ (Opcional) Crear endpoint `PATCH /v1/locations/{location_id}/airport` para modificar radio

### Frontend

1. ✅ Crear `types/airport.ts`
2. ✅ Crear `services/airport.service.ts`
3. ✅ Modificar componente de mapa para cargar airport data
4. ✅ Pintar círculo azul con radio del aeropuerto
5. ✅ Agregar leyenda distinguiendo los 3 tipos de geocercas

---

## 🐛 Debugging

### Verificar que el aeropuerto existe

```sql
SELECT id, code, name, latitude, longitude, radio_zone
FROM entities.airports
WHERE code = 'SDF';
```

### Verificar que la location apunta al aeropuerto correcto

```sql
SELECT l.id, l.name, l.point, l.radio_zone, a.code, a.radio_zone as airport_radius
FROM entities.locations l
LEFT JOIN entities.airports a ON a.code = l.name
WHERE l.name = 'SDF';
```

---

## 📞 Contacto

Si tienes preguntas sobre esta implementación, contacta al equipo de backend.

**Última actualización:** 2026-02-16
**Autor:** GT360 Backend Team
