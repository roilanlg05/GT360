# Búsqueda de Trips por Número de Vuelo - Guía Frontend

## 📋 Descripción

Endpoint optimizado para buscar trips por **número de vuelo** en **todas las locations** de una organización sin necesidad de especificar `location_id`.

---

## 🔗 Endpoint

```
GET /v1/organizations/{organization_id}/trips/search-by-flight
```

**Autenticación:** Requerida (Bearer Token)
**Roles permitidos:** `manager`, `driver`, `crew`

---

## 📥 Request

### Path Parameters

| Parámetro | Tipo | Required | Descripción |
|-----------|------|----------|-------------|
| `organization_id` | UUID | ✅ | ID de la organización |

### Query Parameters

| Parámetro | Tipo | Required | Default | Descripción |
|-----------|------|----------|---------|-------------|
| `flight_number` | string | ✅ | - | Número de vuelo a buscar |
| `airline` | string | ❌ | - | Código de aerolínea (ej: WN, AA) |
| `date` | string | ❌ | - | Fecha exacta (YYYY-MM-DD) |
| `date_from` | string | ❌ | - | Fecha desde (YYYY-MM-DD) |
| `date_to` | string | ❌ | - | Fecha hasta (YYYY-MM-DD) |
| `trip_type` | string | ❌ | - | Tipo: `inbound`, `outbound`, `ground` |
| `limit` | integer | ❌ | 50 | Límite de resultados (1-200) |
| `skip` | integer | ❌ | 0 | Offset para paginación |

**Nota:** `date` es mutuamente exclusivo con `date_from`/`date_to`. Si usas `date`, se ignoran los otros dos.

---

## 📤 Response

### Success Response (200 OK)

```typescript
interface TripSearchResponse {
  trips: TripSearchResult[];
  total: number;
  limit: number;
  skip: number;
}

interface TripSearchResult {
  id: string;  // UUID
  assigned_driver: string | null;  // UUID
  location_id: string;  // UUID
  location_name: string;  // ⭐ Nombre de la location
  pick_up_date: string;  // YYYY-MM-DD
  pick_up_time: string;  // HH:MM:SS
  pick_up_location: string;
  drop_off_location: string;
  airline: string;
  flight_number: string;
  trip_type: 'inbound' | 'outbound' | 'ground' | null;
  status: string | null;

  // ⭐ Riders breakdown (pilotos, flight attendants, etc.)
  riders: {
    pilots?: number;           // Número de pilotos
    flight_attendants?: number; // Número de flight attendants
    deadheads?: number;        // Deadheads
    adults?: number;
    children?: number;
    infants?: number;
  } | null;

  // ⭐ Filter information (qué filtros fueron aplicados)
  original_pick_up_time: string | null;  // Hora original antes de filtros
  reduce_applied: boolean;    // ¿Se aplicó filtro REDUCE?
  combine_applied: boolean;   // ¿Se aplicó filtro COMBINE?
  expand_applied: boolean;    // ¿Se aplicó filtro EXPAND?
  filtered_at: string | null; // Fecha/hora cuando se filtró
  current_step_id: string | null;  // UUID del paso de filtro actual

  // Timestamps
  started_at: string | null;  // ISO 8601
  picked_up_at: string | null;  // ISO 8601
  dropped_off_at: string | null;  // ISO 8601
  created_at: string;  // ISO 8601
  updated_at: string;  // ISO 8601
}
```

### Ejemplo de Respuesta

```json
{
  "trips": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "assigned_driver": null,
      "location_id": "789e4567-e89b-12d3-a456-426614174999",
      "location_name": "San Diego Airport (SAN)",
      "pick_up_date": "2026-02-10",
      "pick_up_time": "14:30:00",
      "pick_up_location": "Terminal 2, Gate 5",
      "drop_off_location": "Hotel Del Coronado",
      "airline": "WN",
      "flight_number": "5468",
      "trip_type": "inbound",
      "status": "pending",

      "riders": {
        "pilots": 2,
        "flight_attendants": 4,
        "deadheads": 0
      },

      "original_pick_up_time": "14:00:00",
      "reduce_applied": true,
      "combine_applied": false,
      "expand_applied": false,
      "filtered_at": "2026-02-01T08:00:00Z",
      "current_step_id": "abc12345-e89b-12d3-a456-426614174111",

      "started_at": null,
      "picked_up_at": null,
      "dropped_off_at": null,
      "created_at": "2026-02-01T10:00:00Z",
      "updated_at": "2026-02-01T10:00:00Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "skip": 0
}
```

### 💡 Interpretación de Filtros

| Campo | Descripción | Uso en UI |
|-------|-------------|-----------|
| `reduce_applied` | El trip fue reducido (hora cambiada) | Mostrar badge "REDUCED" |
| `combine_applied` | El trip fue combinado con otros | Mostrar badge "COMBINED" |
| `expand_applied` | El trip fue expandido | Mostrar badge "EXPANDED" |
| `original_pick_up_time` | Hora original antes de filtros | Mostrar "Original: 14:00" |
| `filtered_at` | Cuándo se aplicó el filtro | Para auditoría |
| `current_step_id` | ID del paso de filtro actual | Para debugging |

**Ejemplo de Badge en UI:**
```tsx
{trip.reduce_applied && <Badge color="orange">REDUCED</Badge>}
{trip.combine_applied && <Badge color="blue">COMBINED</Badge>}
{trip.expand_applied && <Badge color="green">EXPANDED</Badge>}
```

---

## 🚀 Ejemplos de Uso

### 1. TypeScript Types

```typescript
// types/trips.ts

export interface TripSearchResult {
  id: string;
  assigned_driver: string | null;
  location_id: string;
  location_name: string;
  pick_up_date: string;
  pick_up_time: string;
  pick_up_location: string;
  drop_off_location: string;
  airline: string;
  flight_number: string;
  trip_type: 'inbound' | 'outbound' | 'ground' | null;
  status: string | null;

  // Riders breakdown
  riders: {
    pilots?: number;
    flight_attendants?: number;
    deadheads?: number;
    adults?: number;
    children?: number;
    infants?: number;
  } | null;

  // Filter information
  original_pick_up_time: string | null;
  reduce_applied: boolean;
  combine_applied: boolean;
  expand_applied: boolean;
  filtered_at: string | null;
  current_step_id: string | null;

  // Timestamps
  started_at: string | null;
  picked_up_at: string | null;
  dropped_off_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TripSearchResponse {
  trips: TripSearchResult[];
  total: number;
  limit: number;
  skip: number;
}

export interface FlightSearchParams {
  flight_number: string;
  airline?: string;
  date?: string;
  date_from?: string;
  date_to?: string;
  trip_type?: 'inbound' | 'outbound' | 'ground';
  limit?: number;
  skip?: number;
}
```

---

### 2. API Service (Axios)

```typescript
// services/tripsService.ts

import axios from 'axios';
import { TripSearchResponse, FlightSearchParams } from '@/types/trips';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

export const searchTripsByFlight = async (
  organizationId: string,
  params: FlightSearchParams
): Promise<TripSearchResponse> => {
  const response = await axios.get<TripSearchResponse>(
    `${API_BASE_URL}/v1/organizations/${organizationId}/trips/search-by-flight`,
    { params }
  );
  return response.data;
};
```

---

### 3. React Query Hook

```typescript
// hooks/useFlightSearch.ts

import { useQuery } from '@tanstack/react-query';
import { searchTripsByFlight } from '@/services/tripsService';
import { FlightSearchParams } from '@/types/trips';

export const useFlightSearch = (
  organizationId: string,
  params: FlightSearchParams,
  options?: { enabled?: boolean }
) => {
  return useQuery({
    queryKey: ['trips', 'search-by-flight', organizationId, params],
    queryFn: () => searchTripsByFlight(organizationId, params),
    enabled: options?.enabled ?? !!params.flight_number, // Solo buscar si hay flight_number
    staleTime: 30000, // 30 segundos
  });
};
```

---

### 4. Componente de Búsqueda Simple

```typescript
// components/FlightSearchBar.tsx

import React, { useState } from 'react';
import { useFlightSearch } from '@/hooks/useFlightSearch';

interface FlightSearchBarProps {
  organizationId: string;
}

export const FlightSearchBar: React.FC<FlightSearchBarProps> = ({ organizationId }) => {
  const [flightNumber, setFlightNumber] = useState('');
  const [airline, setAirline] = useState('');

  const { data, isLoading, error } = useFlightSearch(
    organizationId,
    {
      flight_number: flightNumber,
      airline: airline || undefined,
      limit: 20,
    },
    { enabled: flightNumber.length >= 2 } // Buscar solo si hay al menos 2 caracteres
  );

  return (
    <div className="flight-search">
      <div className="search-inputs">
        <input
          type="text"
          placeholder="Número de vuelo (ej: 5468)"
          value={flightNumber}
          onChange={(e) => setFlightNumber(e.target.value)}
          className="search-input"
        />
        <input
          type="text"
          placeholder="Aerolínea (opcional)"
          value={airline}
          onChange={(e) => setAirline(e.target.value.toUpperCase())}
          className="search-input"
          maxLength={3}
        />
      </div>

      {isLoading && <p>Buscando...</p>}
      {error && <p className="error">Error al buscar: {error.message}</p>}

      {data && (
        <div className="results">
          <p className="results-count">
            {data.total} resultado{data.total !== 1 ? 's' : ''} encontrado{data.total !== 1 ? 's' : ''}
          </p>
          <div className="trips-list">
            {data.trips.map((trip) => (
              <div key={trip.id} className="trip-card">
                <div className="trip-header">
                  <span className="flight-number">
                    {trip.airline} {trip.flight_number}
                  </span>
                  <span className="location-badge">{trip.location_name}</span>
                </div>
                <div className="trip-details">
                  <p><strong>Fecha:</strong> {trip.pick_up_date}</p>
                  <p><strong>Hora:</strong> {trip.pick_up_time}</p>
                  <p><strong>Pick-up:</strong> {trip.pick_up_location}</p>
                  <p><strong>Drop-off:</strong> {trip.drop_off_location}</p>
                  <p><strong>Tipo:</strong> {trip.trip_type}</p>
                  <p><strong>Pasajeros:</strong> {trip.riders.adults || 0} adultos</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
```

---

### 5. Búsqueda con Filtros Avanzados

```typescript
// components/AdvancedFlightSearch.tsx

import React, { useState } from 'react';
import { useFlightSearch } from '@/hooks/useFlightSearch';

export const AdvancedFlightSearch: React.FC<{ organizationId: string }> = ({ organizationId }) => {
  const [filters, setFilters] = useState({
    flight_number: '',
    airline: '',
    date: '',
    trip_type: '' as '' | 'inbound' | 'outbound' | 'ground',
  });

  const { data, isLoading } = useFlightSearch(organizationId, {
    ...filters,
    airline: filters.airline || undefined,
    date: filters.date || undefined,
    trip_type: filters.trip_type || undefined,
  });

  return (
    <div className="advanced-search">
      <h2>Búsqueda Avanzada de Vuelos</h2>

      <div className="filter-grid">
        <input
          type="text"
          placeholder="Número de vuelo *"
          value={filters.flight_number}
          onChange={(e) => setFilters({ ...filters, flight_number: e.target.value })}
          required
        />

        <input
          type="text"
          placeholder="Aerolínea (ej: WN)"
          value={filters.airline}
          onChange={(e) => setFilters({ ...filters, airline: e.target.value.toUpperCase() })}
          maxLength={3}
        />

        <input
          type="date"
          value={filters.date}
          onChange={(e) => setFilters({ ...filters, date: e.target.value })}
        />

        <select
          value={filters.trip_type}
          onChange={(e) => setFilters({ ...filters, trip_type: e.target.value as any })}
        >
          <option value="">Todos los tipos</option>
          <option value="inbound">Inbound</option>
          <option value="outbound">Outbound</option>
          <option value="ground">Ground</option>
        </select>
      </div>

      {/* Results display */}
      {isLoading ? (
        <div className="loading">Cargando...</div>
      ) : data ? (
        <div className="results">
          <h3>{data.total} resultados</h3>
          {/* Render trips */}
        </div>
      ) : null}
    </div>
  );
};
```

---

### 6. Búsqueda con Rango de Fechas

```typescript
const { data } = useFlightSearch(organizationId, {
  flight_number: '5468',
  airline: 'WN',
  date_from: '2026-02-01',
  date_to: '2026-02-28',
  limit: 100,
});
```

---

### 7. Búsqueda con Paginación (Infinite Scroll)

```typescript
// hooks/useInfiniteFlightSearch.ts

import { useInfiniteQuery } from '@tanstack/react-query';
import { searchTripsByFlight } from '@/services/tripsService';
import { FlightSearchParams } from '@/types/trips';

export const useInfiniteFlightSearch = (
  organizationId: string,
  baseParams: Omit<FlightSearchParams, 'skip'>
) => {
  return useInfiniteQuery({
    queryKey: ['trips', 'search-infinite', organizationId, baseParams],
    queryFn: ({ pageParam = 0 }) =>
      searchTripsByFlight(organizationId, {
        ...baseParams,
        skip: pageParam,
        limit: 20,
      }),
    getNextPageParam: (lastPage, allPages) => {
      const nextOffset = allPages.length * 20;
      return nextOffset < lastPage.total ? nextOffset : undefined;
    },
    enabled: !!baseParams.flight_number,
  });
};

// Uso en componente
const { data, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteFlightSearch(
  organizationId,
  { flight_number: '5468' }
);
```

---

## ⚠️ Manejo de Errores

### Códigos de Error Comunes

| Código | Descripción | Solución |
|--------|-------------|----------|
| 400 | Bad Request - Parámetros inválidos | Verificar formato de fechas (YYYY-MM-DD) y UUIDs |
| 401 | Unauthorized - Token inválido/expirado | Refrescar token de autenticación |
| 403 | Forbidden - No pertenece a la organización | Verificar que el usuario tenga acceso a la org |
| 404 | Not Found - Organización no existe | Verificar que el organization_id sea correcto |

### Ejemplo de Manejo de Errores

```typescript
const { data, error } = useFlightSearch(organizationId, params);

if (error) {
  if (error.response?.status === 403) {
    // Mostrar mensaje: "No tienes acceso a esta organización"
  } else if (error.response?.status === 400) {
    // Mostrar mensaje: "Parámetros de búsqueda inválidos"
  } else {
    // Mostrar mensaje genérico
  }
}
```

---

## 🎯 Casos de Uso Recomendados

### 1. Buscador Global en Dashboard

Implementa un campo de búsqueda en la barra superior que permita buscar cualquier vuelo rápidamente:

```typescript
<GlobalSearch organizationId={currentOrgId} />
```

### 2. Modal de Búsqueda Rápida (Cmd+K)

Implementa un modal activado por teclado para búsqueda rápida:

```typescript
// Presionar Cmd+K o Ctrl+K abre el modal
<FlightSearchModal organizationId={currentOrgId} />
```

### 3. Vista de Trips Filtrada

Lista de trips con búsqueda integrada y filtros:

```typescript
<TripsTable
  organizationId={currentOrgId}
  searchBar={<FlightSearchBar />}
/>
```

### 4. Búsqueda por Voz

Integra búsqueda por voz para facilitar el ingreso:

```typescript
const searchByVoice = () => {
  const recognition = new (window as any).webkitSpeechRecognition();
  recognition.onresult = (event: any) => {
    const flightNumber = event.results[0][0].transcript;
    setFlightNumber(flightNumber);
  };
  recognition.start();
};
```

---

## 🔍 Optimizaciones

### 1. Debounce para Búsqueda en Tiempo Real

```typescript
import { useMemo } from 'react';
import { debounce } from 'lodash';

const debouncedSearch = useMemo(
  () => debounce((value: string) => setFlightNumber(value), 300),
  []
);
```

### 2. Cache de Resultados

```typescript
const { data } = useFlightSearch(organizationId, params, {
  staleTime: 5 * 60 * 1000, // 5 minutos
  cacheTime: 10 * 60 * 1000, // 10 minutos
});
```

### 3. Prefetch para Búsquedas Populares

```typescript
const queryClient = useQueryClient();

// Prefetch vuelos comunes
useEffect(() => {
  popularFlights.forEach((flight) => {
    queryClient.prefetchQuery({
      queryKey: ['trips', 'search', organizationId, { flight_number: flight }],
      queryFn: () => searchTripsByFlight(organizationId, { flight_number: flight }),
    });
  });
}, []);
```

---

## 📊 Performance

- **Query optimizado** con JOIN a `locations` en una sola query
- **Índice en `flight_number`** para búsqueda rápida
- **Paginación** para evitar cargar demasiados resultados
- **Límite máximo:** 200 resultados por request

---

## ✅ Checklist de Implementación

- [ ] Crear tipos TypeScript para request/response
- [ ] Implementar servicio API con axios
- [ ] Crear hook React Query para búsqueda
- [ ] Diseñar componente de búsqueda UI
- [ ] Agregar debounce para búsqueda en tiempo real
- [ ] Implementar manejo de errores
- [ ] Agregar loading states
- [ ] Implementar paginación (si es necesario)
- [ ] Agregar validación de inputs
- [ ] Testing (unit + integration)

---

## 📝 Notas Adicionales

1. **Búsqueda case-insensitive:** El campo `airline` no distingue mayúsculas/minúsculas
2. **Flight number exact match:** El número de vuelo debe coincidir exactamente
3. **Multi-location:** Busca en TODAS las locations de la organización automáticamente
4. **Orden de resultados:** Los trips se ordenan por fecha descendente (más recientes primero)

---

## 🆘 Soporte

Para reportar problemas o solicitar mejoras:
- Backend: `features/trips/routes/trips_router.py` (línea ~2150)
- Modelos: `features/trips/models/trip_model.py`
