# Sistema de Clasificación de Trips (trip_type)

**Fecha de Implementación**: 2026-01-07
**Versión**: 1.0
**Estado**: ✅ Implementado

---

## Resumen Ejecutivo

El backend clasifica automáticamente todos los trips en 3 tipos basándose en las ubicaciones de recogida (pickup) y entrega (dropoff):

- **inbound**: Recogida en aeropuerto → Hotel (llegada/arrival)
- **outbound**: Hotel → Entrega en aeropuerto (salida/departure)
- **ground**: Hotel → Hotel (transferencia local)

## Tabla de Contenidos

- [Lógica de Clasificación](#lógica-de-clasificación)
- [Implementación Técnica](#implementación-técnica)
- [Documentación API](#documentación-api)
- [Guía para Frontend](#guía-para-frontend)
- [Testing](#testing)
- [Archivos Modificados](#archivos-modificados)

---

## Lógica de Clasificación

### Regla de Clasificación

```
Pick up location = aeropuerto → inbound
Drop off location = aeropuerto → outbound
Ninguno = aeropuerto → ground
```

### Implementación

```python
def classify_trip_type_sync(
    pick_up_location: str,
    drop_off_location: str,
    location_airport_code: str,
) -> str:
    """
    Clasificación:
    - Si pick_up_location == airport_code → inbound
    - Si drop_off_location == airport_code → outbound
    - Si ninguno == airport_code → ground
    """
    pick_up_normalized = pick_up_location.strip().upper()
    drop_off_normalized = drop_off_location.strip().upper()
    airport_code_normalized = location_airport_code.strip().upper()

    pickup_is_airport = pick_up_normalized == airport_code_normalized
    dropoff_is_airport = drop_off_normalized == airport_code_normalized

    if pickup_is_airport and not dropoff_is_airport:
        return "inbound"  # Aeropuerto → Hotel
    elif not pickup_is_airport and dropoff_is_airport:
        return "outbound"  # Hotel → Aeropuerto
    else:
        return "ground"  # Hotel → Hotel
```

### Ejemplos

| Pick Up Location | Drop Off Location | Location Code | trip_type | Descripción |
|------------------|-------------------|---------------|-----------|-------------|
| SDF | Marriott Hotel | SDF | inbound | Recogiendo en aeropuerto |
| Holiday Inn | SDF | SDF | outbound | Llevando al aeropuerto |
| Marriott | Holiday Inn | SDF | ground | Transferencia entre hoteles |
| SDF | SDF | SDF | ground | Ambos son aeropuerto (edge case) |

---

## Implementación Técnica

### 1. Base de Datos

**Migración SQL ejecutada**:
```sql
ALTER TABLE trips.trips ADD COLUMN trip_type VARCHAR(10);
CREATE INDEX idx_trips_trip_type ON trips.trips(trip_type);
```

**Características**:
- Tipo: `VARCHAR(10)` (suficiente para "inbound", "outbound", "ground")
- Nullable: `TRUE` (backward compatibility con trips existentes)
- Indexada: `TRUE` (para filtros rápidos)
- Default: `NULL` (se calcula automáticamente en insert)

### 2. Archivos Modificados

#### Schema ORM
- **Archivo**: `shared/db/schemas/trips/trips.py`
- **Cambios**:
  - Clase `TripType` con constantes
  - Campo `trip_type` en modelo `Trip`

#### Clasificador
- **Archivo**: `features/trips/utils/trip_classifier.py` **(NUEVO)**
- **Funciones**:
  - `classify_trip_type_sync()` - Versión sincrónica para importer
  - `classify_trip_type()` - Versión async para API routes

#### Modelos Pydantic
- **Archivo**: `features/trips/models/trip_model.py`
- **Cambios**: Campo `trip_type: Optional[str] = None` en:
  - `Trip`
  - `CreateTrip`
  - `TripUpdate`
  - `TripResponse`

#### Trip Importer
- **Archivo**: `features/trips/utils/trip_importer.py`
- **Cambios**: Calcula `trip_type` automáticamente al importar desde Excel

#### API Router
- **Archivo**: `features/trips/routes/trips_router.py`
- **Endpoints modificados**:
  1. `POST /v1/trips/upload-trips` - Bulk import con trip_type
  2. `POST /v1/locations/{id}/trips` - Crea trip con trip_type calculado
  3. `PATCH /v1/locations/{id}/trips/{id}` - Recalcula trip_type si cambias locations
  4. `GET /v1/locations/{id}/trips` - Nuevo filtro `?trip_type=inbound`

---

## Documentación API

### 1. POST `/v1/trips/upload-trips` - Bulk Import

**Request** (sin cambios):
```bash
POST /v1/trips/upload-trips?airport=SDF&provider=air_crew&airline=WN
Content-Type: multipart/form-data

file: [Excel file]
```

**Response** (nuevo campo `trip_type`):
```json
{
  "status": "ok",
  "uploaded_rows": 150,
  "location_id": "uuid",
  "airport_code": "SDF",
  "trips": [
    {
      "id": "uuid",
      "location_id": "uuid",
      "pick_up_date": "2026-01-15",
      "pick_up_time": "10:00:00-05:00",
      "pick_up_location": "SDF",
      "drop_off_location": "Marriott Hotel Downtown",
      "airline": "WN",
      "flight_number": "1234",
      "riders": {"fligth": 2, "in_fligth": 3},
      "trip_type": "inbound",  // ← NUEVO
      "assigned_driver": null,
      "started_at": null,
      "picked_up_at": null,
      "dropped_off_at": null,
      "created_at": "2026-01-07T10:30:00Z",
      "updated_at": "2026-01-07T10:30:00Z"
    }
  ],
  "hotels": [...]
}
```

### 2. POST `/v1/locations/{location_id}/trips` - Crear Trip

**Request** (NO enviar `trip_type`, se calcula automáticamente):
```json
{
  "pick_up_date": "2026-01-15",
  "pick_up_time": "14:30:00",
  "pick_up_location": "Holiday Inn Airport",
  "drop_off_location": "SDF",
  "airline": "WN",
  "flight_number": "5678",
  "riders": {"fligth": 1, "in_fligth": 2},
  "assigned_driver": null
}
```

**Response** (incluye `trip_type` calculado):
```json
{
  "data": {
    "id": "uuid",
    "location_id": "uuid",
    "pick_up_date": "2026-01-15",
    "pick_up_time": "14:30:00-05:00",
    "pick_up_location": "Holiday Inn Airport",
    "drop_off_location": "SDF",
    "airline": "WN",
    "flight_number": "5678",
    "riders": {"fligth": 1, "in_fligth": 2},
    "trip_type": "outbound",  // ← CALCULADO AUTOMÁTICAMENTE
    "assigned_driver": null,
    "started_at": null,
    "picked_up_at": null,
    "dropped_off_at": null,
    "created_at": "2026-01-07T11:00:00Z",
    "updated_at": "2026-01-07T11:00:00Z"
  }
}
```

### 3. PATCH `/v1/locations/{location_id}/trips/{trip_id}` - Editar Trip

**Request** (cambiar location recalcula `trip_type`):
```json
{
  "pick_up_location": "SDF",  // Cambió de "Holiday Inn" a "SDF"
  "airline": "AA"
}
```

**Response** (nuevo `trip_type` calculado):
```json
{
  "status": "ok",
  "trip": {
    "id": "uuid",
    "pick_up_location": "SDF",
    "drop_off_location": "Marriott",
    "trip_type": "inbound",  // ← RECALCULADO AUTOMÁTICAMENTE
    "airline": "AA",
    ...
  }
}
```

### 4. GET `/v1/locations/{location_id}/trips` - Listar Trips

**Nuevo parámetro de filtro**: `trip_type`

**Ejemplos de uso**:
```bash
# Ver solo llegadas (inbound)
GET /v1/locations/{location_id}/trips?trip_type=inbound

# Ver solo salidas (outbound)
GET /v1/locations/{location_id}/trips?trip_type=outbound&pick_up_date=2026-01-15

# Ver solo traslados (ground)
GET /v1/locations/{location_id}/trips?trip_type=ground

# Todos los trips (sin filtro)
GET /v1/locations/{location_id}/trips
```

**Response**:
```json
{
  "data": [
    {
      "id": "uuid",
      "trip_type": "inbound",
      "pick_up_location": "SDF",
      "drop_off_location": "Hotel",
      ...
    }
  ],
  "skip": 0,
  "limit": 20,
  "total": 45
}
```

---

## Guía para Frontend

### Comportamiento Automático

1. **Bulk Import (Excel)**: El backend calcula `trip_type` automáticamente
2. **Crear Trip Manual**: El backend calcula `trip_type` (NO enviar en request)
3. **Editar Trip**: Si cambias `pick_up_location` o `drop_off_location`, el backend recalcula `trip_type`
4. **Trips Antiguos**: Tendrán `trip_type: null` hasta que sean editados

### Tipos TypeScript

```typescript
// types/trip.ts

export type TripType = 'inbound' | 'outbound' | 'ground';

export interface Trip {
  id: string;
  location_id: string;
  assigned_driver: string | null;
  pick_up_date: string;  // ISO date "2026-01-15"
  pick_up_time: string;  // ISO time "14:30:00-05:00"
  pick_up_location: string;
  drop_off_location: string;
  airline: string;
  flight_number: string;
  riders: {
    fligth: number;      // pilots
    in_fligth: number;   // flight attendants
  };
  trip_type: TripType | null;  // Puede ser null en trips antiguos
  started_at: string | null;
  picked_up_at: string | null;
  dropped_off_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateTripRequest {
  pick_up_date: string;
  pick_up_time: string;
  pick_up_location: string;
  drop_off_location: string;
  airline: string;
  flight_number: string;
  riders: {
    fligth: number;
    in_fligth: number;
  };
  assigned_driver?: string | null;
  // NO incluir trip_type - se calcula automáticamente
}

export interface TripFilters {
  pick_up_date?: string;
  pick_up_date_from?: string;
  pick_up_date_to?: string;
  pick_up_time?: string;
  pick_up_time_from?: string;
  pick_up_time_to?: string;
  pick_up_location?: string;
  drop_off_location?: string;
  airline?: string;
  flight_number?: string;
  trip_type?: TripType;  // ← NUEVO FILTRO
  skip?: number;
  limit?: number;
}
```

### Componentes UI Sugeridos

#### Badge de Tipo de Trip

```tsx
const TripTypeBadge = ({ tripType }: { tripType: string | null }) => {
  if (!tripType) {
    return <span className="badge badge-gray">Sin clasificar</span>;
  }

  const config = {
    inbound: {
      label: 'Llegada',
      icon: '🛬',
      color: 'blue'
    },
    outbound: {
      label: 'Salida',
      icon: '🛫',
      color: 'orange'
    },
    ground: {
      label: 'Traslado',
      icon: '🚗',
      color: 'gray'
    }
  };

  const { label, icon, color } = config[tripType] || config.ground;

  return (
    <span className={`badge badge-${color}`}>
      {icon} {label}
    </span>
  );
};
```

#### Filtros en Lista de Trips

```tsx
const TripFilters = () => {
  const [filters, setFilters] = useState({
    tripType: '',
    pickUpDate: '',
    airline: ''
  });

  return (
    <div className="filters">
      <select
        value={filters.tripType}
        onChange={(e) => setFilters({...filters, tripType: e.target.value})}
      >
        <option value="">Todos los tipos</option>
        <option value="inbound">🛬 Llegadas</option>
        <option value="outbound">🛫 Salidas</option>
        <option value="ground">🚗 Traslados</option>
      </select>

      <input
        type="date"
        value={filters.pickUpDate}
        onChange={(e) => setFilters({...filters, pickUpDate: e.target.value})}
        placeholder="Fecha"
      />

      <button onClick={() => fetchTrips(filters)}>
        Filtrar
      </button>
    </div>
  );
};
```

#### Dashboard de Métricas

```tsx
const TripsDashboard = ({ locationId }: { locationId: string }) => {
  const [stats, setStats] = useState({
    inbound: 0,
    outbound: 0,
    ground: 0,
    total: 0
  });

  useEffect(() => {
    Promise.all([
      fetch(`/api/v1/locations/${locationId}/trips?trip_type=inbound`),
      fetch(`/api/v1/locations/${locationId}/trips?trip_type=outbound`),
      fetch(`/api/v1/locations/${locationId}/trips?trip_type=ground`),
    ]).then(async ([inbound, outbound, ground]) => {
      const [inData, outData, groundData] = await Promise.all([
        inbound.json(),
        outbound.json(),
        ground.json()
      ]);

      setStats({
        inbound: inData.total,
        outbound: outData.total,
        ground: groundData.total,
        total: inData.total + outData.total + groundData.total
      });
    });
  }, [locationId]);

  return (
    <div className="dashboard-cards">
      <Card>
        <h3>🛬 Llegadas</h3>
        <p className="stat-number">{stats.inbound}</p>
      </Card>

      <Card>
        <h3>🛫 Salidas</h3>
        <p className="stat-number">{stats.outbound}</p>
      </Card>

      <Card>
        <h3>🚗 Traslados</h3>
        <p className="stat-number">{stats.ground}</p>
      </Card>

      <Card>
        <h3>📊 Total</h3>
        <p className="stat-number">{stats.total}</p>
      </Card>
    </div>
  );
};
```

### Manejo de Casos Edge

#### Trip sin clasificar (trip_type = null)

```tsx
const displayTripType = (trip: Trip, locationCode: string) => {
  if (trip.trip_type) {
    return trip.trip_type;
  }

  // Fallback: calcular del lado del cliente para trips antiguos
  const pickupIsAirport = trip.pick_up_location.toUpperCase() === locationCode;
  const dropoffIsAirport = trip.drop_off_location.toUpperCase() === locationCode;

  if (pickupIsAirport && !dropoffIsAirport) return 'inbound';
  if (!pickupIsAirport && dropoffIsAirport) return 'outbound';
  return 'ground';
};
```

#### Optimistic Update al editar

```tsx
const updateTrip = async (tripId: string, updates: UpdateTripRequest) => {
  // Si cambiaron locations, predecir el nuevo trip_type
  let predictedTripType = currentTrip.trip_type;

  if (updates.pick_up_location || updates.drop_off_location) {
    const pickup = updates.pick_up_location || currentTrip.pick_up_location;
    const dropoff = updates.drop_off_location || currentTrip.drop_off_location;

    const pickupIsAirport = pickup.toUpperCase() === locationCode;
    const dropoffIsAirport = dropoff.toUpperCase() === locationCode;

    if (pickupIsAirport && !dropoffIsAirport) predictedTripType = 'inbound';
    else if (!pickupIsAirport && dropoffIsAirport) predictedTripType = 'outbound';
    else predictedTripType = 'ground';
  }

  // Update optimista en UI
  setTrips(trips.map(t =>
    t.id === tripId
      ? { ...t, ...updates, trip_type: predictedTripType }
      : t
  ));

  // Request al backend
  const response = await fetch(`/api/v1/locations/${locationId}/trips/${tripId}`, {
    method: 'PATCH',
    body: JSON.stringify(updates)
  });

  const { trip } = await response.json();

  // Actualizar con datos reales del backend
  setTrips(trips.map(t => t.id === tripId ? trip : t));
};
```

---

## Testing

### Validación en Base de Datos

```sql
-- Ver distribución de tipos
SELECT trip_type, COUNT(*)
FROM trips.trips
GROUP BY trip_type;

-- Ver trips sin clasificar
SELECT id, pick_up_location, drop_off_location, trip_type
FROM trips.trips
WHERE trip_type IS NULL
LIMIT 10;

-- Ver ejemplos de cada tipo
SELECT id, pick_up_location, drop_off_location, trip_type
FROM trips.trips
WHERE trip_type = 'inbound'
LIMIT 5;
```

### Testing con curl

```bash
# 1. Crear trip inbound (pickup en aeropuerto)
curl -X POST http://localhost:8000/v1/locations/{location_id}/trips \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "pick_up_date": "2026-01-20",
    "pick_up_time": "10:00:00",
    "pick_up_location": "SDF",
    "drop_off_location": "Marriott Hotel",
    "airline": "WN",
    "flight_number": "1234",
    "riders": {"fligth": 2, "in_fligth": 3}
  }'
# Esperar: trip_type = "inbound"

# 2. Crear trip outbound (dropoff en aeropuerto)
curl -X POST http://localhost:8000/v1/locations/{location_id}/trips \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "pick_up_date": "2026-01-20",
    "pick_up_time": "14:00:00",
    "pick_up_location": "Holiday Inn",
    "drop_off_location": "SDF",
    "airline": "AA",
    "flight_number": "5678",
    "riders": {"fligth": 1, "in_fligth": 2}
  }'
# Esperar: trip_type = "outbound"

# 3. Filtrar por tipo
curl -X GET "http://localhost:8000/v1/locations/{location_id}/trips?trip_type=inbound" \
  -H "Authorization: Bearer $TOKEN"

# 4. Editar trip y verificar recalculo
curl -X PATCH http://localhost:8000/v1/locations/{location_id}/trips/{trip_id} \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "pick_up_location": "SDF"
  }'
# Esperar: trip_type cambia a "inbound"
```

### Checklist de Testing Frontend

- [ ] **Bulk Import**
  - [ ] Subir Excel y verificar que todos los trips tienen `trip_type`
  - [ ] Verificar badges de tipo en la lista
  - [ ] Confirmar que los tipos son correctos

- [ ] **Crear Trip Manual**
  - [ ] Crear trip con pickup en aeropuerto → verificar `trip_type: "inbound"`
  - [ ] Crear trip con dropoff en aeropuerto → verificar `trip_type: "outbound"`
  - [ ] Crear trip hotel→hotel → verificar `trip_type: "ground"`
  - [ ] NO enviar `trip_type` en request

- [ ] **Editar Trip**
  - [ ] Cambiar `pick_up_location` de hotel a aeropuerto → verificar recalcula a `inbound`
  - [ ] Cambiar `drop_off_location` a aeropuerto → verificar recalcula a `outbound`
  - [ ] Cambiar `airline` (sin cambiar locations) → verificar `trip_type` no cambia

- [ ] **Filtros**
  - [ ] Filtrar por `trip_type=inbound` → solo llegadas
  - [ ] Filtrar por `trip_type=outbound` → solo salidas
  - [ ] Filtrar por `trip_type=ground` → solo traslados
  - [ ] Combinar con otros filtros

- [ ] **Trips Antiguos**
  - [ ] Verificar que trips con `trip_type: null` no rompen la UI
  - [ ] Mostrar badge neutral o calcular del lado del cliente

---

## Archivos Modificados

### Base de Datos
- **Tabla**: `trips.trips`
- **Cambios**:
  - Columna `trip_type VARCHAR(10)` agregada
  - Índice `idx_trips_trip_type` creado

### Backend (Python/FastAPI)

1. **`shared/db/schemas/trips/trips.py`**
   - Clase `TripType` con constantes
   - Campo `trip_type` en modelo `Trip`

2. **`shared/db/schemas/__init__.py`**
   - Export `TripType`

3. **`features/trips/utils/trip_classifier.py`** **(NUEVO)**
   - `classify_trip_type_sync()`
   - `classify_trip_type()`

4. **`features/trips/models/trip_model.py`**
   - Campo `trip_type` en 4 modelos Pydantic

5. **`features/trips/utils/trip_importer.py`**
   - Calcula `trip_type` durante bulk import

6. **`features/trips/routes/trips_router.py`**
   - 4 endpoints modificados con soporte para `trip_type`

---

## Notas Importantes

### Para Desarrolladores Backend

1. ✅ Migración SQL ya ejecutada
2. ✅ Código implementado y funcionando
3. ⚠️ Reiniciar FastAPI después de los cambios
4. ⚠️ Verificar logs durante bulk import

### Para Desarrolladores Frontend

1. ⚠️ **NO enviar `trip_type` en requests de creación/edición**
2. ⚠️ Manejar `trip_type: null` en trips antiguos
3. ✅ Los filtros son opcionales
4. ✅ El recálculo en edición es automático

### Métricas de Éxito

- ✅ Todos los trips nuevos tienen `trip_type` != null
- ✅ Bulk import mantiene performance (sin queries extra)
- ✅ Filtros por tipo funcionan correctamente
- ✅ UI muestra badges/indicadores visuales
- ✅ Editar locations recalcula el tipo automáticamente

---

**Última actualización**: 2026-01-07
**Autor**: Claude Code
**Estado**: ✅ Completado e Implementado
