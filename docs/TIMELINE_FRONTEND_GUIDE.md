# Timeline Frontend Implementation Guide

## Overview

Este documento describe los nuevos endpoints de Timeline que permiten:
- Mostrar trips organizados por LIVE (vivos) vs HISTORY (pasados)
- Paginación bidireccional con cursor (scroll hacia adelante y atrás)
- "Saltar a ahora" sin cargar todo el mes
- Paginador diario con conteo de trips live/history

---

## Conceptos Clave

### Clasificación LIVE vs HISTORY

La clasificación usa **Status + Tiempo**:

| Status | Clasificación | Descripción |
|--------|---------------|-------------|
| `completed` | **HISTORY** | Siempre historia (trip terminado) |
| `canceled` | **HISTORY** | Siempre historia (trip cancelado) |
| `en_route` | **LIVE** | Siempre vivo (driver en camino) |
| `scheduled` | **Depende del tiempo** | LIVE si pickup_time > now, HISTORY si ya pasó |

### Timezone

Todas las operaciones de tiempo usan el **timezone de la location**:
- Cada location tiene un campo `timezone` (ej: "America/New_York")
- "Ahora" se calcula en el timezone de la location, no UTC
- Esto garantiza que un trip a las 3pm en Phoenix se compare con las 3pm en Phoenix

---

## Endpoints

### 1. GET `/v1/locations/{location_id}/days`

Obtiene los días disponibles para un mes específico con conteo de trips live/history.

#### Request
```http
GET /v1/locations/{location_id}/days?year=2026&month=0&airline=WN
Authorization: Bearer {token}
```

#### Query Parameters
| Param | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `year` | int | ✅ | Año (ej: 2026) |
| `month` | int | ✅ | Mes en formato JavaScript (0-11, donde 0=Enero) |
| `airline` | string | ❌ | Filtrar por aerolínea |

#### Response
```json
{
  "location_id": "550e8400-e29b-41d4-a716-446655440000",
  "year": 2026,
  "month": 0,
  "timezone": "America/New_York",
  "current_day": 21,
  "days": [
    {
      "day": 20,
      "count": 45,
      "live_count": 0,
      "history_count": 45
    },
    {
      "day": 21,
      "count": 85,
      "live_count": 42,
      "history_count": 43
    },
    {
      "day": 22,
      "count": 50,
      "live_count": 50,
      "history_count": 0
    }
  ]
}
```

#### Response Fields
| Campo | Descripción |
|-------|-------------|
| `timezone` | Timezone IANA de la location |
| `current_day` | Día actual en el timezone de la location (null si no es el mes actual) |
| `days[].day` | Número del día (1-31) |
| `days[].count` | Total de trips ese día |
| `days[].live_count` | Trips LIVE (upcoming) |
| `days[].history_count` | Trips HISTORY (pasados) |

#### Uso en Frontend
```typescript
// Al seleccionar un mes en el paginador mensual
const loadDays = async (locationId: string, year: number, month: number) => {
  const response = await fetch(
    `/api/v1/locations/${locationId}/days?year=${year}&month=${month}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  const data = await response.json();

  // Destacar el día actual
  if (data.current_day) {
    setSelectedDay(data.current_day);
  }

  // Renderizar calendario con badges de conteo
  setDays(data.days);
};
```

---

### 2. GET `/v1/locations/{location_id}/timeline/anchor`

Obtiene el "punto de anclaje" para saltar directamente a "ahora" sin cargar todo el mes.

#### Request
```http
GET /v1/locations/{location_id}/timeline/anchor?airline=WN
Authorization: Bearer {token}
```

#### Query Parameters
| Param | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `airline` | string | ❌ | Filtrar por aerolínea |

#### Response
```json
{
  "location_id": "550e8400-e29b-41d4-a716-446655440000",
  "timezone": "America/New_York",
  "current_datetime": "2026-01-21T14:30:00-05:00",
  "current_date": "2026-01-21",
  "current_year": 2026,
  "current_month": 0,
  "current_day": 21,
  "first_live_trip": {
    "id": "trip-uuid-123",
    "pick_up_date": "2026-01-21",
    "pick_up_time": "15:00:00",
    "cursor": "2026-01-21T15:00:00_trip-uuid-123"
  },
  "today_summary": {
    "total": 85,
    "live": 42,
    "history": 43,
    "by_status": {
      "scheduled": 40,
      "en_route": 2,
      "completed": 38,
      "canceled": 5
    }
  }
}
```

#### Response Fields
| Campo | Descripción |
|-------|-------------|
| `current_datetime` | Fecha/hora actual en el timezone de la location (ISO 8601) |
| `current_date` | Fecha actual (YYYY-MM-DD) |
| `current_year` | Año actual |
| `current_month` | Mes actual (0-11 JavaScript format) |
| `current_day` | Día actual (1-31) |
| `first_live_trip` | Primer trip LIVE, o `null` si no hay trips vivos |
| `first_live_trip.cursor` | Cursor para usar en `/timeline` |
| `today_summary` | Resumen de trips del día actual |

#### Uso en Frontend
```typescript
// Al cargar la app o presionar "Ir a Hoy"
const goToNow = async (locationId: string) => {
  const response = await fetch(
    `/api/v1/locations/${locationId}/timeline/anchor`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  const anchor = await response.json();

  // Actualizar el paginador al mes/día actual
  setSelectedYear(anchor.current_year);
  setSelectedMonth(anchor.current_month);
  setSelectedDay(anchor.current_day);

  // Cargar trips desde el primer trip LIVE
  if (anchor.first_live_trip) {
    await loadTimeline(locationId, anchor.first_live_trip.cursor, 'forward');
  } else {
    // No hay trips LIVE, cargar el día actual completo
    await loadTimeline(locationId, null, 'forward', anchor.current_date);
  }
};
```

---

### 3. GET `/v1/locations/{location_id}/timeline`

Obtiene trips con paginación bidireccional basada en cursor.

#### Request
```http
GET /v1/locations/{location_id}/timeline?cursor={cursor}&direction=forward&limit=50
Authorization: Bearer {token}
```

#### Query Parameters
| Param | Tipo | Requerido | Default | Descripción |
|-------|------|-----------|---------|-------------|
| `cursor` | string | ❌ | - | Cursor de paginación |
| `direction` | string | ❌ | "forward" | "forward" o "backward" |
| `date` | string | ❌ | - | Fecha específica (YYYY-MM-DD), alternativa al cursor |
| `category` | string | ❌ | "all" | "all", "live", o "history" |
| `status` | string | ❌ | - | Filtrar por status específico |
| `airline` | string | ❌ | - | Filtrar por aerolínea |
| `limit` | int | ❌ | 50 | Cantidad de trips (1-100) |

#### Response
```json
{
  "location_id": "550e8400-e29b-41d4-a716-446655440000",
  "timezone": "America/New_York",
  "current_datetime": "2026-01-21T14:30:00-05:00",
  "data": [
    {
      "id": "trip-uuid-1",
      "pick_up_date": "2026-01-21",
      "pick_up_time": "15:00:00",
      "pick_up_time_formatted": "3:00 PM",
      "is_live": true,
      "status": "scheduled",
      "airline": "WN",
      "flight_number": "1234",
      "pick_up_location": "Hilton Downtown",
      "drop_off_location": "SDF",
      "riders": [...],
      "assigned_driver": null,
      "trip_type": "outbound"
    },
    {
      "id": "trip-uuid-2",
      "pick_up_date": "2026-01-21",
      "pick_up_time": "15:30:00",
      "pick_up_time_formatted": "3:30 PM",
      "is_live": true,
      "status": "en_route",
      "airline": "WN",
      "flight_number": "5678",
      ...
    }
  ],
  "pagination": {
    "has_more_forward": true,
    "has_more_backward": true,
    "next_cursor": "2026-01-21T16:00:00_trip-uuid-10",
    "prev_cursor": "2026-01-21T14:30:00_trip-uuid-0"
  },
  "summary": {
    "live": 8,
    "history": 2,
    "by_status": {
      "scheduled": 7,
      "en_route": 1,
      "completed": 2,
      "canceled": 0
    }
  }
}
```

#### Response Fields
| Campo | Descripción |
|-------|-------------|
| `data[].is_live` | `true` si el trip es LIVE, `false` si es HISTORY |
| `data[].pick_up_time_formatted` | Hora formateada según preferencia del usuario (12h/24h) |
| `pagination.has_more_forward` | `true` si hay más trips hacia adelante |
| `pagination.has_more_backward` | `true` si hay más trips hacia atrás |
| `pagination.next_cursor` | Cursor para cargar más trips hacia adelante |
| `pagination.prev_cursor` | Cursor para cargar más trips hacia atrás |
| `summary` | Conteo de trips en la página actual |

---

## Flujos de Frontend

### Flujo 1: Carga Inicial (Ir a Ahora)

```
┌──────────────────────────────────────────────────────────────┐
│  1. App carga                                                │
│     GET /timeline/anchor                                     │
│     → Obtiene: current_day, current_month, first_live_trip   │
├──────────────────────────────────────────────────────────────┤
│  2. Cargar trips desde el anchor                             │
│     GET /timeline?cursor={first_live_trip.cursor}            │
│            &direction=forward                                │
│     → Obtiene: trips LIVE ordenados por pickup_time          │
├──────────────────────────────────────────────────────────────┤
│  3. Renderizar UI                                            │
│     - Paginador mensual: mes actual destacado                │
│     - Paginador diario: día actual destacado                 │
│     - Lista de trips: primer trip LIVE visible               │
└──────────────────────────────────────────────────────────────┘
```

### Flujo 2: Scroll Infinito Bidireccional

```typescript
// Estado del componente
const [trips, setTrips] = useState<Trip[]>([]);
const [nextCursor, setNextCursor] = useState<string | null>(null);
const [prevCursor, setPrevCursor] = useState<string | null>(null);
const [hasMoreForward, setHasMoreForward] = useState(true);
const [hasMoreBackward, setHasMoreBackward] = useState(true);

// Cargar más trips hacia adelante (scroll down)
const loadMoreForward = async () => {
  if (!hasMoreForward || !nextCursor) return;

  const response = await fetch(
    `/api/v1/locations/${locationId}/timeline?cursor=${nextCursor}&direction=forward`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  const data = await response.json();

  // Agregar trips al final
  setTrips(prev => [...prev, ...data.data]);
  setNextCursor(data.pagination.next_cursor);
  setHasMoreForward(data.pagination.has_more_forward);
};

// Cargar más trips hacia atrás (scroll up)
const loadMoreBackward = async () => {
  if (!hasMoreBackward || !prevCursor) return;

  const response = await fetch(
    `/api/v1/locations/${locationId}/timeline?cursor=${prevCursor}&direction=backward`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  const data = await response.json();

  // Agregar trips al inicio (mantener posición de scroll)
  setTrips(prev => [...data.data, ...prev]);
  setPrevCursor(data.pagination.prev_cursor);
  setHasMoreBackward(data.pagination.has_more_backward);
};
```

### Flujo 3: Seleccionar Día Específico

```typescript
const selectDay = async (day: number) => {
  const dateStr = `${selectedYear}-${String(selectedMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;

  const response = await fetch(
    `/api/v1/locations/${locationId}/timeline?date=${dateStr}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  const data = await response.json();

  // Reemplazar lista de trips
  setTrips(data.data);
  setNextCursor(data.pagination.next_cursor);
  setPrevCursor(data.pagination.prev_cursor);
  setHasMoreForward(data.pagination.has_more_forward);
  setHasMoreBackward(data.pagination.has_more_backward);
};
```

### Flujo 4: Filtrar por Categoría

```typescript
// Solo trips LIVE
const showLiveOnly = async () => {
  const response = await fetch(
    `/api/v1/locations/${locationId}/timeline?category=live`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  // ...
};

// Solo trips HISTORY
const showHistoryOnly = async () => {
  const response = await fetch(
    `/api/v1/locations/${locationId}/timeline?category=history`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  // ...
};
```

---

## Renderizado de UI

### Componente de Trip Card

```tsx
interface Trip {
  id: string;
  pick_up_date: string;
  pick_up_time: string;
  pick_up_time_formatted: string;
  is_live: boolean;
  status: 'scheduled' | 'en_route' | 'completed' | 'canceled';
  airline: string;
  flight_number: string;
  pick_up_location: string;
  drop_off_location: string;
  // ...
}

const TripCard: React.FC<{ trip: Trip }> = ({ trip }) => {
  // Determinar estilos basados en is_live y status
  const getStatusColor = () => {
    if (trip.status === 'en_route') return 'blue';
    if (trip.status === 'completed') return 'green';
    if (trip.status === 'canceled') return 'red';
    if (trip.is_live) return 'orange';  // scheduled + future
    return 'gray';  // scheduled + past (history)
  };

  const getStatusLabel = () => {
    if (trip.status === 'en_route') return 'En Route';
    if (trip.status === 'completed') return 'Completed';
    if (trip.status === 'canceled') return 'Canceled';
    if (trip.is_live) return 'Upcoming';
    return 'Passed';
  };

  return (
    <div className={`trip-card ${trip.is_live ? 'live' : 'history'}`}>
      <div className="trip-time">
        {trip.pick_up_time_formatted}
      </div>
      <div className={`trip-status status-${getStatusColor()}`}>
        {getStatusLabel()}
      </div>
      <div className="trip-details">
        <span>{trip.airline} {trip.flight_number}</span>
        <span>{trip.pick_up_location} → {trip.drop_off_location}</span>
      </div>
    </div>
  );
};
```

### Separador LIVE / HISTORY

```tsx
const TimelineList: React.FC<{ trips: Trip[] }> = ({ trips }) => {
  // Encontrar el índice donde cambia de LIVE a HISTORY
  const firstHistoryIndex = trips.findIndex(t => !t.is_live);

  return (
    <div className="timeline-list">
      {trips.map((trip, index) => (
        <React.Fragment key={trip.id}>
          {/* Separador entre LIVE y HISTORY */}
          {index === firstHistoryIndex && firstHistoryIndex > 0 && (
            <div className="timeline-separator">
              <span>— Ahora —</span>
            </div>
          )}
          <TripCard trip={trip} />
        </React.Fragment>
      ))}
    </div>
  );
};
```

### Paginador Diario con Badges

```tsx
const DayPaginator: React.FC<{ days: DayInfo[], currentDay: number | null }> = ({ days, currentDay }) => {
  return (
    <div className="day-paginator">
      {days.map(day => (
        <button
          key={day.day}
          className={`day-button ${day.day === currentDay ? 'current' : ''}`}
          onClick={() => selectDay(day.day)}
        >
          <span className="day-number">{day.day}</span>
          <div className="day-badges">
            {day.live_count > 0 && (
              <span className="badge live">{day.live_count}</span>
            )}
            {day.history_count > 0 && (
              <span className="badge history">{day.history_count}</span>
            )}
          </div>
        </button>
      ))}
    </div>
  );
};
```

---

## Tipos TypeScript

```typescript
// Response de /days
interface DaysResponse {
  location_id: string;
  year: number;
  month: number;  // 0-11
  timezone: string;
  current_day: number | null;
  days: DayInfo[];
}

interface DayInfo {
  day: number;  // 1-31
  count: number;
  live_count: number;
  history_count: number;
}

// Response de /timeline/anchor
interface AnchorResponse {
  location_id: string;
  timezone: string;
  current_datetime: string;  // ISO 8601
  current_date: string;  // YYYY-MM-DD
  current_year: number;
  current_month: number;  // 0-11
  current_day: number;  // 1-31
  first_live_trip: {
    id: string;
    pick_up_date: string;
    pick_up_time: string;
    cursor: string;
  } | null;
  today_summary: {
    total: number;
    live: number;
    history: number;
    by_status: Record<string, number>;
  };
}

// Response de /timeline
interface TimelineResponse {
  location_id: string;
  timezone: string;
  current_datetime: string;
  data: Trip[];
  pagination: {
    has_more_forward: boolean;
    has_more_backward: boolean;
    next_cursor: string | null;
    prev_cursor: string | null;
  };
  summary: {
    live: number;
    history: number;
    by_status: Record<string, number>;
  };
}

interface Trip {
  id: string;
  pick_up_date: string;
  pick_up_time: string;
  pick_up_time_formatted: string;
  is_live: boolean;
  status: 'scheduled' | 'en_route' | 'completed' | 'canceled';
  airline: string;
  flight_number: string;
  pick_up_location: string;
  drop_off_location: string;
  trip_type: 'inbound' | 'outbound' | 'ground';
  riders: any[];
  assigned_driver: string | null;
  // ... otros campos
}
```

---

## Formato del Cursor

El cursor es un string con el formato:
```
{pick_up_date}T{pick_up_time}_{trip_id}
```

Ejemplo:
```
2026-01-21T15:00:00_550e8400-e29b-41d4-a716-446655440000
```

**Importante**: El cursor es opaco para el frontend. No lo parseés ni lo modifiques, solo úsalo tal cual lo devuelve el backend.

---

## Consideraciones de Performance

1. **No cargar todo el mes**: Usa siempre paginación con cursor
2. **Límite recomendado**: 50 trips por página es un buen balance
3. **Prefetch**: Considera precargar la siguiente página cuando el usuario se acerca al final
4. **Virtualización**: Para listas largas, usa react-window o similar

```typescript
// Ejemplo de prefetch
const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
  const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;

  // Si está cerca del final, precargar más
  if (scrollHeight - scrollTop - clientHeight < 500) {
    loadMoreForward();
  }

  // Si está cerca del inicio, precargar hacia atrás
  if (scrollTop < 500) {
    loadMoreBackward();
  }
};
```

---

## Manejo de Real-time (WebSocket)

El WebSocket existente notifica cambios en trips. Cuando recibes una actualización:

```typescript
// Cuando un trip cambia de status
websocket.on('trip_update', (updatedTrip) => {
  setTrips(prev => prev.map(trip => {
    if (trip.id === updatedTrip.id) {
      // Recalcular is_live localmente
      const isLive = computeIsLive(updatedTrip.status, updatedTrip.pick_up_time, timezone);
      return { ...updatedTrip, is_live: isLive };
    }
    return trip;
  }));
});

// Función para calcular is_live en el frontend
const computeIsLive = (
  status: string,
  pickupDateTime: string,  // ISO string
  locationTimezone: string
): boolean => {
  // Status-based rules
  if (status === 'completed' || status === 'canceled') return false;
  if (status === 'en_route') return true;

  // Time-based rule for scheduled
  const now = new Date();
  const pickup = new Date(pickupDateTime);
  return pickup > now;
};
```

---

## Resumen de Endpoints

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/v1/locations/{id}/months` | GET | Meses disponibles (existente) |
| `/v1/locations/{id}/days` | GET | Días de un mes con conteo live/history |
| `/v1/locations/{id}/timeline/anchor` | GET | Punto de anclaje para "ir a ahora" |
| `/v1/locations/{id}/timeline` | GET | Trips con paginación bidireccional |

---

## Checklist de Implementación

- [ ] Integrar endpoint `/timeline/anchor` en carga inicial
- [ ] Implementar paginador diario con `/days`
- [ ] Implementar lista de trips con `/timeline`
- [ ] Agregar scroll infinito bidireccional
- [ ] Mostrar separador LIVE/HISTORY
- [ ] Agregar filtros por categoría (all/live/history)
- [ ] Botón "Ir a Hoy"
- [ ] Sincronizar con WebSocket para actualizaciones
