# 📊 Sistema de Filtrado de Trips para Frontend

**Fecha**: 2026-01-10
**Para**: Equipo Frontend
**De**: Backend Developer

---

## 🎯 Respuesta Directa: ¿De Dónde Sale el Año Fiable?

### El año viene del campo `pick_up_date` de cada trip

```json
{
  "id": "uuid",
  "pick_up_date": "2025-12-01",  // ← AÑO AQUÍ: 2025
  "pick_up_time": "04:20:00+00:00",
  "pick_up_location": "Hyatt Regency Louisville",
  "drop_off_location": "SDF",
  "airline": "WN",
  "flight_number": "4285"
}
```

### Origen del Año en el Backend

1. **Excel tiene columna DATE**: `01-Dec-2025`
2. **Backend parsea con `_parse_service_date()`**: Convierte a `date(2025, 12, 1)`
3. **Se guarda en DB**: Campo `pick_up_date` tipo DATE
4. **Se envía al frontend**: Como string ISO `"2025-12-01"`

### Formatos de Fecha Soportados por el Backend

```python
# trip_importer.py línea 95
FORMATOS_SOPORTADOS = [
    "%Y-%m-%d",    # 2025-12-01
    "%m/%d/%Y",    # 12/01/2025
    "%d/%m/%Y",    # 01/12/2025
    "%d-%b-%Y",    # 01-Dec-2025  ← Formato del Excel SDF
    "%d-%B-%Y",    # 01-December-2025
]
```

---

## 📋 Endpoints Disponibles para Filtrado

### 1. Obtener Todas las Locations del Manager

```http
GET /v1/locations
Authorization: Bearer {token}
```

**Response:**
```json
{
  "data": [
    {
      "id": "uuid-location-1",
      "name": "SDF",
      "timezone": "America/Kentucky/Louisville",
      "provider": "api"
    },
    {
      "id": "uuid-location-2",
      "name": "JFK",
      "timezone": "America/New_York",
      "provider": "api"
    }
  ]
}
```

---

### 2. Obtener Trips con Filtros

```http
GET /v1/locations/{location_id}/trips
Authorization: Bearer {token}
```

**Query Parameters:**

| Parámetro | Tipo | Descripción | Ejemplo |
|-----------|------|-------------|---------|
| `pick_up_date` | string | Fecha exacta | `2025-12-01` |
| `pick_up_date_from` | string | Desde fecha | `2025-12-01` |
| `pick_up_date_to` | string | Hasta fecha | `2025-12-31` |
| `airline` | string | Filtrar por aerolínea | `WN` |
| `trip_type` | string | inbound/outbound | `outbound` |
| `skip` | int | Offset paginación | `0` |
| `limit` | int | Límite (max 50) | `50` |

**Ejemplo - Filtrar por Mes (Diciembre 2025):**
```http
GET /v1/locations/{uuid}/trips?pick_up_date_from=2025-12-01&pick_up_date_to=2025-12-31&limit=50
```

**Response:**
```json
{
  "data": [
    {
      "id": "trip-uuid-1",
      "pick_up_date": "2025-12-01",
      "pick_up_time": "04:20:00+00:00",
      "pick_up_location": "Hyatt Regency Louisville",
      "drop_off_location": "SDF",
      "airline": "WN",
      "flight_number": "4285",
      "trip_type": "outbound",
      "riders": {"fligth": 2, "in_fligth": 3}
    }
  ],
  "skip": 0,
  "limit": 50,
  "total": 707
}
```

---

## 🗓️ Estrategia para Obtener Meses/Años Disponibles

### Opción A: Query Inicial (RECOMENDADA)

Al cargar la página, obtener todos los trips sin filtro de fecha y extraer meses únicos:

```typescript
// 1. Obtener TODOS los trips de una location (puede ser costoso si hay muchos)
const response = await fetch(`/v1/locations/${locationId}/trips?limit=50`);

// 2. Extraer meses/años únicos del campo pick_up_date
function extractAvailableMonths(trips: Trip[]): MonthYear[] {
  const monthsSet = new Set<string>();

  trips.forEach(trip => {
    const date = new Date(trip.pick_up_date);
    const monthKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
    monthsSet.add(monthKey);
  });

  return Array.from(monthsSet)
    .sort()
    .map(key => {
      const [year, month] = key.split('-');
      return { year: parseInt(year), month: parseInt(month) };
    });
}
```

### Opción B: Endpoint Dedicado (SI SE NECESITA)

Si el frontend requiere un endpoint específico para meses disponibles, puedo crearlo:

```http
GET /v1/locations/{location_id}/trips/available-months
Authorization: Bearer {token}
```

**Response propuesta:**
```json
{
  "data": [
    {"year": 2025, "month": 11, "count": 450},
    {"year": 2025, "month": 12, "count": 707},
    {"year": 2026, "month": 1, "count": 123}
  ]
}
```

**¿Necesitas este endpoint? Házmelo saber y lo creo.**

---

## 📱 Implementación del Sistema de Filtrado

### Estructura de Datos Propuesta

```typescript
interface FilterState {
  // Filtros de ubicación
  selectedLocations: string[];      // UUIDs de locations
  selectedAirlines: string[];       // ["WN", "AA", "DL"]

  // Filtros de tiempo
  selectedMonth: number;            // 1-12
  selectedYear: number;             // 2025, 2026...

  // Estado de UI
  currentDay: Date;                 // Día actual mostrado en scroll
}

interface MonthYear {
  year: number;
  month: number;
  count?: number;  // Opcional: cantidad de trips
}

interface LocationWithTrips {
  id: string;
  name: string;
  timezone: string;
  airlines: string[];              // Aerolíneas únicas en esta location
  availableMonths: MonthYear[];    // Meses con trips
}
```

---

### Flujo de Datos Completo

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. CARGA INICIAL                                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   GET /v1/locations                                                 │
│        ↓                                                            │
│   Para cada location:                                               │
│        GET /v1/locations/{id}/trips?limit=1                        │
│        (Solo para saber si tiene trips y obtener fechas min/max)   │
│        ↓                                                            │
│   Construir lista de locations con meses disponibles               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 2. SELECCIÓN DE MES                                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   Usuario selecciona: Diciembre 2025                               │
│        ↓                                                            │
│   GET /v1/locations/{id}/trips                                     │
│       ?pick_up_date_from=2025-12-01                                │
│       &pick_up_date_to=2025-12-31                                  │
│       &limit=50                                                     │
│        ↓                                                            │
│   Renderizar tabla con trips del mes                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 3. POSICIONAMIENTO AUTOMÁTICO                                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   Si mes == mes actual:                                             │
│       → Scroll a día actual                                         │
│   Si mes < mes actual (pasado):                                     │
│       → Mostrar último día del mes                                  │
│   Si mes > mes actual (futuro):                                     │
│       → Mostrar primer día del mes                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📅 Lógica de Posicionamiento por Día

### Código TypeScript

```typescript
interface ScrollPosition {
  targetDay: string;  // "2025-12-13" formato ISO
  reason: 'current' | 'last' | 'first';
}

function calculateScrollPosition(
  selectedYear: number,
  selectedMonth: number,
  trips: Trip[]
): ScrollPosition {
  const now = new Date();
  const currentYear = now.getFullYear();
  const currentMonth = now.getMonth() + 1;
  const currentDay = now.getDate();

  // Obtener días únicos ordenados del mes seleccionado
  const daysInMonth = getUniqueDays(trips, selectedYear, selectedMonth);

  if (daysInMonth.length === 0) {
    // No hay trips en este mes
    return { targetDay: '', reason: 'first' };
  }

  // Caso 1: Mes actual → ir al día de hoy
  if (selectedYear === currentYear && selectedMonth === currentMonth) {
    // Buscar el día de hoy o el más cercano
    const todayStr = `${selectedYear}-${String(selectedMonth).padStart(2, '0')}-${String(currentDay).padStart(2, '0')}`;

    // Si hay trips hoy, ir a hoy
    if (daysInMonth.includes(todayStr)) {
      return { targetDay: todayStr, reason: 'current' };
    }

    // Si no hay trips hoy, buscar el día más cercano hacia adelante
    const closestDay = daysInMonth.find(d => d >= todayStr) || daysInMonth[daysInMonth.length - 1];
    return { targetDay: closestDay, reason: 'current' };
  }

  // Caso 2: Mes pasado → ir al último día con trips
  if (selectedYear < currentYear ||
      (selectedYear === currentYear && selectedMonth < currentMonth)) {
    return {
      targetDay: daysInMonth[daysInMonth.length - 1],
      reason: 'last'
    };
  }

  // Caso 3: Mes futuro → ir al primer día con trips
  return {
    targetDay: daysInMonth[0],
    reason: 'first'
  };
}

function getUniqueDays(trips: Trip[], year: number, month: number): string[] {
  const days = new Set<string>();

  trips.forEach(trip => {
    const tripDate = new Date(trip.pick_up_date);
    if (tripDate.getFullYear() === year && tripDate.getMonth() + 1 === month) {
      days.add(trip.pick_up_date);
    }
  });

  return Array.from(days).sort();
}
```

---

## 🎨 Separación Visual por Días

### CSS para Líneas de Separación

```css
/* Contenedor de la tabla */
.trips-table {
  width: 100%;
  border-collapse: collapse;
}

/* Fila separadora de día */
.day-separator {
  position: relative;
}

.day-separator::before {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  height: 1px;
  background: linear-gradient(
    to right,
    transparent 0%,
    #e0e0e0 10%,
    #e0e0e0 90%,
    transparent 100%
  );
}

/* Header del día */
.day-header-row {
  background: #f8f9fa;
  font-weight: 600;
  font-size: 13px;
  color: #495057;
  padding: 12px 16px;
  border-top: 2px solid #dee2e6;
  position: sticky;
  top: 0;
  z-index: 10;
}

.day-header-row.today {
  background: #e3f2fd;
  border-top-color: #2196f3;
}

.day-header-row.today::after {
  content: 'HOY';
  margin-left: 8px;
  font-size: 10px;
  background: #2196f3;
  color: white;
  padding: 2px 6px;
  border-radius: 3px;
}

/* Fila de trip normal */
.trip-row {
  border-bottom: 1px solid #f0f0f0;
  transition: background 0.15s ease;
}

.trip-row:hover {
  background: #f5f5f5;
}

/* Primera fila de cada día */
.trip-row.first-of-day {
  /* Sin borde superior adicional, ya tiene el day-header */
}

/* Última fila de cada día */
.trip-row.last-of-day {
  border-bottom: 1px solid #e0e0e0;
}
```

### Componente React para Tabla con Separadores

```tsx
interface GroupedTrips {
  [date: string]: Trip[];
}

function TripsTable({ trips, timezone }: { trips: Trip[], timezone: string }) {
  // Agrupar trips por día
  const groupedByDay = useMemo(() => {
    const groups: GroupedTrips = {};

    trips.forEach(trip => {
      const dayKey = trip.pick_up_date;
      if (!groups[dayKey]) {
        groups[dayKey] = [];
      }
      groups[dayKey].push(trip);
    });

    // Ordenar dentro de cada día por hora
    Object.keys(groups).forEach(day => {
      groups[day].sort((a, b) =>
        a.pick_up_time.localeCompare(b.pick_up_time)
      );
    });

    return groups;
  }, [trips]);

  // Ordenar días
  const sortedDays = useMemo(() =>
    Object.keys(groupedByDay).sort(),
    [groupedByDay]
  );

  const today = new Date().toISOString().split('T')[0];

  return (
    <table className="trips-table">
      <thead>
        <tr>
          <th>Hora</th>
          <th>Tipo</th>
          <th>Pickup</th>
          <th>Dropoff</th>
          <th>Vuelo</th>
          <th>Pasajeros</th>
        </tr>
      </thead>
      <tbody>
        {sortedDays.map(day => (
          <React.Fragment key={day}>
            {/* Header del día */}
            <tr className={`day-header-row ${day === today ? 'today' : ''}`}>
              <td colSpan={6}>
                {formatDayHeader(day, timezone)}
              </td>
            </tr>

            {/* Trips del día */}
            {groupedByDay[day].map((trip, index) => (
              <tr
                key={trip.id}
                className={`
                  trip-row
                  ${index === 0 ? 'first-of-day' : ''}
                  ${index === groupedByDay[day].length - 1 ? 'last-of-day' : ''}
                `}
              >
                <td>{formatTime(trip.pick_up_time, timezone)}</td>
                <td>
                  <TripTypeBadge type={trip.trip_type} />
                </td>
                <td>{trip.pick_up_location}</td>
                <td>{trip.drop_off_location}</td>
                <td>{trip.airline} {trip.flight_number}</td>
                <td>{getRidersCount(trip.riders)}</td>
              </tr>
            ))}
          </React.Fragment>
        ))}
      </tbody>
    </table>
  );
}

function formatDayHeader(dateStr: string, timezone: string): string {
  const date = new Date(dateStr + 'T12:00:00');
  return new Intl.DateTimeFormat('es-ES', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone: timezone,
  }).format(date);
}

function formatTime(timeStr: string, timezone: string): string {
  // timeStr viene como "04:20:00+00:00"
  const [time] = timeStr.split('+');
  const [hours, minutes] = time.split(':');
  const hour = parseInt(hours);
  const ampm = hour >= 12 ? 'PM' : 'AM';
  const hour12 = hour % 12 || 12;
  return `${hour12}:${minutes} ${ampm}`;
}

function TripTypeBadge({ type }: { type: string }) {
  return (
    <span className={`badge ${type}`}>
      {type === 'inbound' ? '🛬 Llegada' : '🛫 Salida'}
    </span>
  );
}

function getRidersCount(riders: Record<string, number>): number {
  return Object.values(riders).reduce((sum, count) => sum + count, 0);
}
```

---

## 🔄 Scroll Infinito / Paginación

### Implementación con Infinite Scroll

```typescript
function useTripsInfiniteScroll(
  locationId: string,
  year: number,
  month: number
) {
  const [trips, setTrips] = useState<Trip[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [skip, setSkip] = useState(0);
  const limit = 50;

  const dateFrom = `${year}-${String(month).padStart(2, '0')}-01`;
  const dateTo = `${year}-${String(month).padStart(2, '0')}-${getLastDayOfMonth(year, month)}`;

  const loadMore = useCallback(async () => {
    if (loading || !hasMore) return;

    setLoading(true);

    try {
      const response = await fetch(
        `/v1/locations/${locationId}/trips` +
        `?pick_up_date_from=${dateFrom}` +
        `&pick_up_date_to=${dateTo}` +
        `&skip=${skip}` +
        `&limit=${limit}`
      );

      const data = await response.json();

      setTrips(prev => [...prev, ...data.data]);
      setSkip(prev => prev + limit);
      setHasMore(data.data.length === limit && skip + limit < data.total);

    } finally {
      setLoading(false);
    }
  }, [locationId, dateFrom, dateTo, skip, loading, hasMore]);

  // Reset cuando cambia el mes
  useEffect(() => {
    setTrips([]);
    setSkip(0);
    setHasMore(true);
  }, [year, month, locationId]);

  return { trips, loading, hasMore, loadMore };
}

function getLastDayOfMonth(year: number, month: number): string {
  const date = new Date(year, month, 0);
  return String(date.getDate()).padStart(2, '0');
}
```

---

## 📊 Resumen de Endpoints Necesarios

| Endpoint | Propósito | Status |
|----------|-----------|--------|
| `GET /v1/locations` | Obtener locations del manager | ✅ Existe |
| `GET /v1/locations/{id}/trips` | Obtener trips con filtros | ✅ Existe |
| `GET /v1/locations/{id}/hotels` | Obtener hoteles | ✅ Existe |
| `GET /v1/locations/{id}/trips/available-months` | Meses disponibles | ⚠️ **Puedo crear** |

---

## ✅ Checklist de Implementación Frontend

- [ ] Obtener locations del manager al inicio
- [ ] Para cada location, determinar meses disponibles
- [ ] Implementar selector de location (multi-select)
- [ ] Implementar selector de aerolínea
- [ ] Implementar selector de mes/año
- [ ] Implementar tabla con separadores de día
- [ ] Implementar scroll automático al día correcto
- [ ] Implementar paginación/infinite scroll
- [ ] Sincronizar con WebSocket para actualizaciones en tiempo real

---

## 📞 ¿Necesitas el Endpoint de Meses Disponibles?

Si el frontend requiere un endpoint dedicado para obtener los meses con trips:

```http
GET /v1/locations/{location_id}/trips/available-months
```

**Respuesta:**
```json
{
  "data": {
    "months": [
      {"year": 2025, "month": 11, "count": 450, "airlines": ["WN"]},
      {"year": 2025, "month": 12, "count": 707, "airlines": ["WN"]},
      {"year": 2026, "month": 1, "count": 123, "airlines": ["WN", "AA"]}
    ],
    "location_id": "uuid",
    "location_name": "SDF"
  }
}
```

**Dime si lo necesitas y lo implemento inmediatamente.**

---

**Última actualización**: 2026-01-10 12:35 UTC
