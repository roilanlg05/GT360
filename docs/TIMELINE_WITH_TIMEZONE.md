# Timeline con Soporte de Timezone - Guía de Implementación

**Version:** 1.0
**Date:** 2026-01-05
**Status:** Implemented

---

## Tabla de Contenidos

1. [Resumen Ejecutivo](#1-resumen-ejecutivo)
2. [Definiciones Oficiales](#2-definiciones-oficiales)
3. [Arquitectura de Datos](#3-arquitectura-de-datos)
4. [Backend - Cambios Implementados](#4-backend---cambios-implementados)
5. [Frontend - Guía de Implementación](#5-frontend---guía-de-implementación)
6. [Ejemplos de Código](#6-ejemplos-de-código)
7. [Testing](#7-testing)

---

## 1. Resumen Ejecutivo

### Objetivo
Permitir al App developer mostrar un **Timeline de trips** en la pestaña trips , agrupando los viajes por día según el timezone de la ubicación (aeropuerto) y distinguiendo entre **inbound** (llegadas) y **outbound** (salidas).

### Cambios Realizados
- El snapshot de WebSocket ahora incluye `location_info` con el timezone de la ubicación
- El app developer  puede usar esta información para ordenar y agrupar trips correctamente

---

## 2. Definiciones Oficiales

### Inbound Trip (Llegada)
Un trip es **INBOUND** cuando el pasajero **llega** al aeropuerto desde un vuelo.

```
Condición: trip.pick_up_location === location_info.id
```

**Escenario:** El avión aterriza en el aeropuerto (SDF). El conductor recoge al pasajero EN el aeropuerto y lo lleva a su destino (hotel, oficina, etc).

```
[Vuelo] → [Aeropuerto SDF] → [Conductor recoge] → [Hotel/Destino]
           pick_up_location
```

### Outbound Trip (Salida)
Un trip es **OUTBOUND** cuando el pasajero **sale** hacia el aeropuerto para tomar un vuelo.

```
Condición: trip.drop_off_location === location_info.id
```

**Escenario:** El conductor recoge al pasajero en su ubicación (hotel, oficina) y lo lleva AL aeropuerto para que tome su vuelo.

```
[Hotel/Origen] → [Conductor lleva] → [Aeropuerto SDF] → [Vuelo]
                                      drop_off_location
```

### Tabla de Referencia Rápida

| Tipo | Condición | El pasajero... | El conductor... |
|------|-----------|----------------|-----------------|
| **INBOUND** | `pick_up_location === airport` | Llega de un vuelo | Recoge EN el aeropuerto |
| **OUTBOUND** | `drop_off_location === airport` | Sale hacia un vuelo | Deja EN el aeropuerto |

---

## 3. Arquitectura de Datos

### Nuevo Formato del Snapshot

**Antes:**
```json
{
  "type": "snapshot",
  "location_id": "uuid",
  "trips": [...]
}
```

**Ahora:**
```json
{
  "type": "snapshot",
  "location_id": "uuid",
  "location_info": {
    "id": "uuid",
    "name": "SDF",
    "timezone": "America/New_York"
  },
  "trips": [...]
}
```

### Estructura de un Trip

```typescript
interface Trip {
  id: string;                    // UUID del trip
  location_id: string;           // UUID de la ubicación (aeropuerto)

  // Ubicaciones
  pick_up_location: string;      // UUID - Donde se recoge al pasajero
  drop_off_location: string;     // UUID - Donde se deja al pasajero

  // Fecha y hora del servicio
  pick_up_date: string;          // "2026-01-15" (ISO date)
  pick_up_time: string;          // "14:30:00" (ISO time)

  // Información del vuelo
  airline: string | null;        // "Delta", "United", etc.
  flight_number: string | null;  // "DL1234"

  // Otros campos...
  passenger_name: string;
  pax_count: number;
  status: string;
  notes: string | null;
}
```

### Estructura de Location Info

```typescript
interface LocationInfo {
  id: string;          // UUID de la ubicación
  name: string;        // Código del aeropuerto (e.g., "SDF", "JFK", "LAX")
  timezone: string;    // IANA timezone (e.g., "America/New_York")
}
```

---

## 4. Backend - Cambios Implementados

### Archivo Modificado
`features/trips/websockets/trip_websockets.py`

### Nueva Función: `_get_location_info()`

```python
async def _get_location_info(location_id: str) -> dict | None:
    """
    Get location metadata for Timeline ordering.

    Returns:
        dict with: id, name (airport code), timezone
        Used by frontend to:
        - Determine inbound/outbound (compare with pick_up_location/drop_off_location)
        - Group trips by day using the correct timezone
    """
    try:
        location_uuid = UUID(location_id)
    except ValueError:
        return None

    async with AsyncSession(engine) as session:
        location = await session.exec(
            Select(Location).Where(Location.id == location_uuid)
        ).first()

        if not location:
            return None

        return {
            "id": str(location.id),
            "name": location.name,  # Airport code (e.g., "SDF")
            "timezone": location.timezone,  # e.g., "America/New_York"
        }
```

### Modificación: `send_snapshot()`

El snapshot ahora incluye `location_info`:

```python
await ws.send_json({
    "type": "snapshot",
    "location_id": location_id,
    "location_info": location_info,  # NEW: Para Timeline
    "trips": trips
})
```

---

## 5. Frontend - Guía de Implementación

### 5.1 Recibir y Almacenar Location Info

```typescript
// En tu WebSocket handler
websocket.onmessage = (event) => {
  const message = JSON.parse(event.data);

  if (message.type === 'snapshot') {
    // Guardar location_info para uso en Timeline
    const locationInfo: LocationInfo = message.location_info;
    const trips: Trip[] = message.trips;

    // Almacenar en estado
    setLocationInfo(locationInfo);
    setTrips(trips);
  }
};
```

### 5.2 Determinar Tipo de Trip (Inbound/Outbound)

```typescript
type TripDirection = 'inbound' | 'outbound' | 'unknown';

function getTripDirection(trip: Trip, locationInfo: LocationInfo): TripDirection {
  const airportId = locationInfo.id;

  if (trip.pick_up_location === airportId) {
    return 'inbound';  // Pasajero llega al aeropuerto
  }

  if (trip.drop_off_location === airportId) {
    return 'outbound';  // Pasajero sale hacia el aeropuerto
  }

  return 'unknown';  // Edge case: ninguno coincide
}
```

### 5.3 Agrupar Trips por Día (con Timezone)

```typescript
import { zonedTimeToUtc, utcToZonedTime, format } from 'date-fns-tz';

interface GroupedTrips {
  [date: string]: Trip[];  // "2026-01-15" -> [trip1, trip2, ...]
}

function groupTripsByDay(trips: Trip[], timezone: string): GroupedTrips {
  const grouped: GroupedTrips = {};

  for (const trip of trips) {
    // Crear datetime completo en UTC
    const dateTimeString = `${trip.pick_up_date}T${trip.pick_up_time}`;
    const utcDate = zonedTimeToUtc(dateTimeString, timezone);

    // Convertir a la zona horaria del aeropuerto para obtener el día correcto
    const zonedDate = utcToZonedTime(utcDate, timezone);
    const dayKey = format(zonedDate, 'yyyy-MM-dd', { timeZone: timezone });

    if (!grouped[dayKey]) {
      grouped[dayKey] = [];
    }
    grouped[dayKey].push(trip);
  }

  return grouped;
}
```

### 5.4 Ordenar Trips dentro de cada Día

```typescript
function sortTripsInDay(trips: Trip[], timezone: string): Trip[] {
  return [...trips].sort((a, b) => {
    const dateTimeA = `${a.pick_up_date}T${a.pick_up_time}`;
    const dateTimeB = `${b.pick_up_date}T${b.pick_up_time}`;

    const utcA = zonedTimeToUtc(dateTimeA, timezone);
    const utcB = zonedTimeToUtc(dateTimeB, timezone);

    return utcA.getTime() - utcB.getTime();
  });
}
```

### 5.5 Componente Timeline Completo

```typescript
interface TimelineDay {
  date: string;           // "2026-01-15"
  displayDate: string;    // "Wednesday, January 15"
  trips: TripWithDirection[];
}

interface TripWithDirection extends Trip {
  direction: TripDirection;
  displayTime: string;    // "2:30 PM"
}

function buildTimeline(
  trips: Trip[],
  locationInfo: LocationInfo
): TimelineDay[] {
  const { timezone } = locationInfo;

  // 1. Agrupar por día
  const grouped = groupTripsByDay(trips, timezone);

  // 2. Construir timeline
  const timeline: TimelineDay[] = Object.entries(grouped)
    .map(([date, dayTrips]) => {
      // Ordenar trips del día
      const sortedTrips = sortTripsInDay(dayTrips, timezone);

      // Agregar dirección y hora formateada
      const tripsWithDirection: TripWithDirection[] = sortedTrips.map(trip => ({
        ...trip,
        direction: getTripDirection(trip, locationInfo),
        displayTime: formatTripTime(trip, timezone),
      }));

      return {
        date,
        displayDate: formatDayHeader(date, timezone),
        trips: tripsWithDirection,
      };
    })
    .sort((a, b) => a.date.localeCompare(b.date));  // Ordenar días

  return timeline;
}

function formatTripTime(trip: Trip, timezone: string): string {
  const dateTimeString = `${trip.pick_up_date}T${trip.pick_up_time}`;
  const utcDate = zonedTimeToUtc(dateTimeString, timezone);
  const zonedDate = utcToZonedTime(utcDate, timezone);

  return format(zonedDate, 'h:mm a', { timeZone: timezone });
}

function formatDayHeader(dateStr: string, timezone: string): string {
  const date = new Date(dateStr + 'T12:00:00');  // Mediodía para evitar edge cases
  const zonedDate = utcToZonedTime(date, timezone);

  return format(zonedDate, 'EEEE, MMMM d', { timeZone: timezone });
}
```

### 5.6 Renderizado del Timeline

```tsx
function TimelineComponent({ trips, locationInfo }: Props) {
  const timeline = useMemo(
    () => buildTimeline(trips, locationInfo),
    [trips, locationInfo]
  );

  return (
    <div className="timeline">
      {timeline.map(day => (
        <div key={day.date} className="timeline-day">
          <h3 className="day-header">{day.displayDate}</h3>

          <div className="day-trips">
            {day.trips.map(trip => (
              <TripCard
                key={trip.id}
                trip={trip}
                direction={trip.direction}
                displayTime={trip.displayTime}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function TripCard({ trip, direction, displayTime }: TripCardProps) {
  return (
    <div className={`trip-card ${direction}`}>
      <div className="trip-time">{displayTime}</div>

      <div className="trip-direction">
        {direction === 'inbound' ? (
          <span className="badge inbound">ARRIVAL</span>
        ) : (
          <span className="badge outbound">DEPARTURE</span>
        )}
      </div>

      <div className="trip-details">
        <div className="passenger">{trip.passenger_name}</div>
        {trip.flight_number && (
          <div className="flight">
            {trip.airline} {trip.flight_number}
          </div>
        )}
      </div>
    </div>
  );
}
```

### 5.7 CSS Sugerido

```css
.timeline {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.timeline-day {
  border-left: 2px solid #e0e0e0;
  padding-left: 16px;
}

.day-header {
  font-size: 14px;
  font-weight: 600;
  color: #666;
  margin-bottom: 12px;
}

.trip-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 8px;
  margin-bottom: 8px;
}

.trip-card.inbound {
  background: #e8f5e9;  /* Verde claro */
  border-left: 4px solid #4caf50;
}

.trip-card.outbound {
  background: #e3f2fd;  /* Azul claro */
  border-left: 4px solid #2196f3;
}

.badge {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
}

.badge.inbound {
  background: #4caf50;
  color: white;
}

.badge.outbound {
  background: #2196f3;
  color: white;
}
```

---

## 6. Ejemplos de Código

### Ejemplo 1: Snapshot Real

```json
{
  "type": "snapshot",
  "location_id": "550e8400-e29b-41d4-a716-446655440000",
  "location_info": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "SDF",
    "timezone": "America/New_York"
  },
  "trips": [
    {
      "id": "trip-001",
      "location_id": "550e8400-e29b-41d4-a716-446655440000",
      "pick_up_location": "550e8400-e29b-41d4-a716-446655440000",
      "drop_off_location": "hotel-uuid-here",
      "pick_up_date": "2026-01-15",
      "pick_up_time": "14:30:00",
      "airline": "Delta",
      "flight_number": "DL1234",
      "passenger_name": "John Smith",
      "pax_count": 2,
      "status": "confirmed"
    },
    {
      "id": "trip-002",
      "location_id": "550e8400-e29b-41d4-a716-446655440000",
      "pick_up_location": "office-uuid-here",
      "drop_off_location": "550e8400-e29b-41d4-a716-446655440000",
      "pick_up_date": "2026-01-15",
      "pick_up_time": "06:00:00",
      "airline": "United",
      "flight_number": "UA567",
      "passenger_name": "Jane Doe",
      "pax_count": 1,
      "status": "confirmed"
    }
  ]
}
```

### Ejemplo 2: Resultado del Timeline

Para el snapshot anterior, el Timeline mostraría:

```
Wednesday, January 15
├─ 6:00 AM  [DEPARTURE] Jane Doe - United UA567
│           → Pasajero sale hacia SDF para tomar vuelo
│
└─ 2:30 PM  [ARRIVAL] John Smith - Delta DL1234
            → Pasajero llega a SDF, conductor lo recoge
```

### Ejemplo 3: Hook Completo

```typescript
import { useState, useEffect, useMemo } from 'react';

interface UseTimelineResult {
  timeline: TimelineDay[];
  locationInfo: LocationInfo | null;
  isLoading: boolean;
  error: Error | null;
}

export function useTimeline(locationId: string, token: string): UseTimelineResult {
  const [trips, setTrips] = useState<Trip[]>([]);
  const [locationInfo, setLocationInfo] = useState<LocationInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    const wsUrl = `wss://api.example.com/ws/trips?location_id=${locationId}&token=${token}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      setIsLoading(false);
    };

    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);

      switch (message.type) {
        case 'snapshot':
          setLocationInfo(message.location_info);
          setTrips(message.trips);
          break;

        case 'trip_event':
          handleTripEvent(message);
          break;
      }
    };

    ws.onerror = (e) => {
      setError(new Error('WebSocket error'));
    };

    return () => ws.close();
  }, [locationId, token]);

  const handleTripEvent = (event: TripEvent) => {
    switch (event.event_type) {
      case 'insert':
        setTrips(prev => [...prev, event.trip]);
        break;
      case 'update':
        setTrips(prev => prev.map(t => t.id === event.trip_id ? event.trip : t));
        break;
      case 'delete':
        setTrips(prev => prev.filter(t => t.id !== event.trip_id));
        break;
    }
  };

  const timeline = useMemo(() => {
    if (!locationInfo) return [];
    return buildTimeline(trips, locationInfo);
  }, [trips, locationInfo]);

  return { timeline, locationInfo, isLoading, error };
}
```

---

## 7. Testing

### Test Cases para Frontend

| # | Escenario | Input | Expected |
|---|-----------|-------|----------|
| 1 | Trip inbound básico | `pick_up_location === airport.id` | direction = "inbound" |
| 2 | Trip outbound básico | `drop_off_location === airport.id` | direction = "outbound" |
| 3 | Agrupación por día | Trips de diferentes días | Grupos separados por fecha |
| 4 | Ordenamiento por hora | Trips del mismo día | Ordenados por pick_up_time |
| 5 | Timezone edge case | Trip a las 11 PM EST | Día correcto en EST, no UTC |
| 6 | Location info null | Backend retorna null | Graceful degradation |

### Comandos de Verificación

```bash
# Verificar que el streaming service esté corriendo
docker ps | grep streaming

# Ver logs del WebSocket
docker logs gt360-api-1 2>&1 | grep -i websocket

# Probar conexión WebSocket (wscat)
wscat -c "wss://api.example.com/ws/trips?location_id=UUID&token=JWT"
```

---

## Appendix A: Timezones Comunes en US

| Aeropuerto | Timezone |
|------------|----------|
| SDF (Louisville) | America/New_York |
| JFK (New York) | America/New_York |
| ORD (Chicago) | America/Chicago |
| DFW (Dallas) | America/Chicago |
| DEN (Denver) | America/Denver |
| LAX (Los Angeles) | America/Los_Angeles |
| SEA (Seattle) | America/Los_Angeles |

---

## Appendix B: Dependencias Recomendadas (Frontend)

```json
{
  "dependencies": {
    "date-fns": "^2.30.0",
    "date-fns-tz": "^2.0.0"
  }
}
```

---

**Documento Finalizado**
