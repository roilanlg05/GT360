# Driver Earnings Screen - Frontend Implementation Guide

## Base URL

```
https://dev-api.gt360.app
```

Todos los endpoints requieren header:
```
Authorization: Bearer {driver_jwt_token}
```

El `driver_id` se obtiene del token JWT decodificado (`user_data.id`).

---

## Estructura de Pantallas

```
Earnings (Tab principal)
|
|-- [Header] Current Period Earnings    <-- Dato principal, grande, visible
|-- [Info Cards] Pay Type / Frequency / Rate
|-- [Section] Current Period Breakdown  <-- Desglose del periodo actual
|-- [Section] Pay Periods               <-- Lista de periodos historicos
|-- [Section] Recent Shifts             <-- Ultimos 10 shifts
|-- [FAB] (+) Add Expense              <-- Boton flotante
|
|-- [Sub-screen] Year-to-Date Summary   <-- Accesible via link/boton, NO en vista principal
|-- [Sub-screen] Add Expense Form       <-- Al tocar el FAB
```

---

## PANTALLA 1: Earnings (Vista Principal)

### Datos necesarios

Un solo request trae casi todo:

```
GET /v1/drivers/{driver_id}/earnings?page=1&page_size=10
```

#### Comportamiento de los periodos

- Los periodos se generan **desde la semana actual hacia atras** hasta la semana que contiene el `created_at` del driver
- Cada periodo es una **semana completa** (Lunes a Domingo), sin importar en que dia de la semana empezo el driver
- **Ejemplo:** Si el driver empezo el **miercoles 6 de febrero**, el primer periodo historico sera **Lun 3 Feb - Dom 9 Feb** (la semana completa que contiene el dia 6)
- El **periodo actual siempre aparece** como `periods[0]`, aunque hoy sea lunes y la semana apenas empezo
- Las fechas de `period_start` y `period_end` estan en la **zona horaria local** del driver (no UTC)
- Para `daily`: cada periodo es un dia
- Para `weekly`: cada periodo es Lunes a Domingo
- Para `biweekly`: cada periodo son 2 semanas (14 dias)

#### Response completa:

```json
{
  "driver_id": "8f83da7b-7d21-4d49-891e-1ed75d411e4d",
  "driver_name": "John Doe",
  "pay_type": "hour",
  "pay_frequency": "weekly",
  "rate": 25.0,
  "timezone": "America/Los_Angeles",
  "periods": [
    {
      "period_start": "2026-02-16",
      "period_end": "2026-02-22",
      "gross_earnings": 125.00,
      "verified_expenses": 0,
      "net_pay": 125.00,
      "total_hours": 5.0,
      "total_days": 1,
      "total_trips": 3,
      "total_shifts": 1,
      "expenses_count": 0,
      "shifts": [...],
      "trips": [...],
      "expenses": [...]
    },
    {
      "period_start": "2026-02-09",
      "period_end": "2026-02-15",
      "gross_earnings": 625.00,
      "verified_expenses": 30.00,
      "net_pay": 655.00,
      "total_hours": 25.0,
      "total_days": 5,
      "total_trips": 22,
      "total_shifts": 6,
      "expenses_count": 1,
      "shifts": [...],
      "trips": [...],
      "expenses": [...]
    },
    {
      "period_start": "2026-02-02",
      "period_end": "2026-02-08",
      "gross_earnings": 500.00,
      "verified_expenses": 45.50,
      "net_pay": 545.50,
      "total_hours": 20.0,
      "total_days": 4,
      "total_trips": 18,
      "total_shifts": 5,
      "expenses_count": 2,
      "shifts": [...],
      "trips": [...],
      "expenses": [...]
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 10,
    "total_periods": 3,
    "total_pages": 1
  },
  "year_to_date": {
    "year": 2026,
    "total_gross_earnings": 1250.00,
    "total_expenses_reimbursed": 75.50,
    "total_net_pay": 1325.50,
    "total_hours_worked": 50.0,
    "total_days_worked": 10,
    "total_trips": 43
  }
}
```

> **Nota:** `periods[0]` siempre es la **semana actual** (Feb 16-22 en este ejemplo).
> Aunque hoy sea lunes y solo haya 1 shift, los datos reflejan lo que hay hasta el momento en esa semana.

---

### Seccion 1: Current Period Earnings (Header)

**Que mostrar:** El primer elemento de `periods[]` es el periodo actual (el mas reciente).

```
periods[0].gross_earnings  -->  "$500.00"
```

Mostrar como numero grande, prominente, al tope de la pantalla.

**Label dinamico segun `pay_frequency`:**
- `"weekly"` → "This Week's Earnings"
- `"biweekly"` → "Current Pay Period"
- `"daily"` → "Today's Earnings"

**Sub-label:** Mostrar rango de fechas del periodo:
```
periods[0].period_start + " - " + periods[0].period_end
```
Ejemplo: `"Feb 16 - Feb 22, 2026"`

---

### Seccion 2: Info Cards (Pay Type / Frequency / Rate)

Tres tarjetas horizontales debajo del header:

| Card | Campo | Formato | Ejemplo |
|------|-------|---------|---------|
| Pay Type | `pay_type` | Capitalizar | "Hourly" / "Daily" / "Per Trip" |
| Frequency | `pay_frequency` | Capitalizar | "Weekly" / "Biweekly" / "Daily" |
| Rate | `rate` | Moneda | "$25.00/hr" / "$150.00/day" / "$12.00/trip" |

**Formato del rate segun pay_type:**
- `hour` → `"$XX.XX/hr"`
- `day` → `"$XX.XX/day"`
- `trip` → `"$XX.XX/trip"`

---

### Seccion 3: Current Period Breakdown

Desglose detallado del periodo actual. Datos de `periods[0]`:

| Label | Campo | Formato |
|-------|-------|---------|
| Gross Earnings | `periods[0].gross_earnings` | "$500.00" |
| Reimbursements | `periods[0].verified_expenses` | "$45.50" |
| Net Pay | `periods[0].net_pay` | "$545.50" |
| Trips Completed | `periods[0].total_trips` | "18 trips" |
| Hours Worked | `periods[0].total_hours` | "20.0 hrs" |
| Shifts Worked | `periods[0].total_shifts` | "5 shifts" |
| Days Worked | `periods[0].total_days` | "4 days" |

---

### Seccion 4: Pay Periods (Lista Historica)

Lista scrollable de todos los periodos. Cada item muestra un periodo:

```
┌─────────────────────────────────────┐
│  Feb 9 - Feb 15, 2026              │
│                                     │
│  Gross: $625.00    Reimb: $30.00   │
│  Trips: 22   Hours: 25.0 hrs      │
│  Days: 5     Shifts: 6            │
└─────────────────────────────────────┘
```

**Datos:** Iterar `periods[]` empezando desde `periods[1]` (el [0] ya se muestra arriba como current).

**Paginacion:** Usar `pagination.total_pages` para lazy loading. Si hay mas paginas:

```
GET /v1/drivers/{driver_id}/earnings?page=2&page_size=10
```

**Campos por periodo:**

| Campo | Key |
|-------|-----|
| Rango de fechas | `period_start` - `period_end` |
| Gross Earnings | `gross_earnings` |
| Reimbursements | `verified_expenses` |
| Trips | `total_trips` |
| Hours | `total_hours` |
| Days | `total_days` |
| Shifts | `total_shifts` |

---

### Seccion 5: Recent Shifts

```
GET /v1/drivers/{driver_id}/shifts?page=1&page_size=10
```

#### Response:

```json
{
  "shifts": [
    {
      "shift_id": "uuid",
      "driver_id": "uuid",
      "pay_type": "hour",
      "rate": 25.0,
      "started_at": "2026-02-17T08:00:00Z",
      "ended_at": "2026-02-17T14:30:00Z",
      "duration_hours": 6.5,
      "status": "completed",
      "review_status": null,
      "review_reason": null,
      "reviewed_at": null,
      "reviewed_by": null,
      "manager_notes": null,
      "auto_closed": false,
      "crosses_midnight": false,
      "trips_in_shift": 8,
      "hours_distribution": null,
      "created_at": "2026-02-17T08:00:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 10,
    "total_shifts": 45,
    "total_pages": 5
  },
  "summary": {
    "active_shifts": 0,
    "completed_shifts": 8,
    "under_review_shifts": 2
  }
}
```

**Cada shift en la lista muestra:**

```
┌─────────────────────────────────────┐
│  Mon, Feb 17                        │
│  8:00 AM - 2:30 PM   6.5 hrs      │
│  8 trips   $25.00/hr              │
│  Status: Completed ✓              │
└─────────────────────────────────────┘
```

| Campo | Key | Formato |
|-------|-----|---------|
| Fecha | `started_at` | Formato dia de semana + fecha |
| Horario | `started_at` - `ended_at` | Formato hora local |
| Duracion | `duration_hours` | "X.X hrs" |
| Trips | `trips_in_shift` | "X trips" |
| Rate | `rate` | "$XX.XX/hr" (segun `pay_type`) |
| Status | `status` | Badge de color (ver tabla abajo) |

**Status badges:**

| Status | Color | Label |
|--------|-------|-------|
| `active` | Verde | "Active" |
| `completed` | Azul | "Completed" |
| `under_review` | Amarillo | "Under Review" |
| `reviewed` | Gris | "Reviewed" |
| `auto_closed` | Naranja | "Auto-closed" |

Si `auto_closed == true`, mostrar indicador especial (icono reloj).

---

## PANTALLA 2: Year-to-Date Summary (Sub-pantalla)

**Acceso:** Boton o link "View Year-to-Date" dentro de la pantalla de Earnings. NO mostrar estos datos en la vista principal.

**Datos:** Ya vienen en el response de earnings bajo `year_to_date`.

No requiere request adicional.

```json
{
  "year_to_date": {
    "year": 2026,
    "total_gross_earnings": 4250.00,
    "total_expenses_reimbursed": 320.50,
    "total_net_pay": 4570.50,
    "total_hours_worked": 170.0,
    "total_days_worked": 34,
    "total_trips": 156
  }
}
```

**Layout sugerido:**

```
┌─────────────────────────────────────┐
│      Year-to-Date Summary           │
│           2026                      │
│                                     │
│  ┌───────────────────────────────┐  │
│  │  Total Gross     $4,250.00   │  │
│  │  Reimbursements  +$320.50    │  │
│  │  ─────────────────────────── │  │
│  │  Total Net Pay   $4,570.50   │  │
│  └───────────────────────────────┘  │
│                                     │
│  Trips Completed       156         │
│  Hours Worked          170.0 hrs   │
│  Days Worked           34 days     │
└─────────────────────────────────────┘
```

---

## PANTALLA 3: Add Expense (Sub-pantalla)

**Acceso:** Boton flotante (FAB) con icono `+` en la parte inferior de la pantalla de Earnings. Al tocarlo se despliega un mini-menu:

```
  ┌────────────────────┐
  │  Add Expense       │
  └────────────────────┘
         (+)
```

Por ahora solo tiene una opcion: "Add Expense". Al tocarla, se abre la pantalla de formulario.

### Endpoint para enviar expense

```
POST /v1/drivers/{driver_id}/expenses
Content-Type: multipart/form-data
```

**IMPORTANTE:** Este endpoint usa `multipart/form-data`, NO JSON. Todos los campos van como form fields.

### Campos del formulario

| Campo | Key | Tipo | Requerido | Descripcion |
|-------|-----|------|-----------|-------------|
| Receipt Photo | `receipt_photo` | File (image/pdf) | **Si** | Foto del recibo. Max 10MB. Formatos: JPG, PNG, PDF |
| Amount | `amount` | number | **Si** | Monto del gasto. Debe ser > 0 |
| Category | `expense_type` | string | **Si** | Categoria del gasto (ver lista abajo) |
| Date | `expense_date` | string | **Si** | Fecha del gasto. Formato YYYY-MM-DD |
| Description | `description` | string | No | Detalle opcional del gasto. Puede ser null |

### Categorias de Expenses (`expense_type`)

| Valor | Label para UI | Icono sugerido | Descripcion |
|-------|---------------|----------------|-------------|
| `gas` | Gas / Fuel | fuel pump | Gasolina para el vehiculo |
| `maintenance` | Maintenance | wrench | Reparaciones, cambio de aceite, llantas |
| `parking` | Parking | parking sign | Estacionamiento |
| `car_wash` | Car Wash | car | Lavado del vehiculo |
| `supplies` | Supplies | box | Agua, snacks para pasajeros, materiales |
| `tolls` | Tolls | road | Peajes (si aplica) |
| `other` | Other (Custom) | dots | Otro gasto - el driver describe en `description` |

**Comportamiento de la UI para categorias:**

1. Mostrar las categorias como chips/botones seleccionables en grid
2. Las primeras 6 son predefinidas (gas, maintenance, parking, car_wash, supplies, tolls)
3. "Other" es la opcion custom: cuando el driver la selecciona, el campo `description` se vuelve obligatorio visualmente (para que explique que gasto es)
4. Para las demas categorias, `description` es opcional

### Layout del formulario

```
┌─────────────────────────────────────┐
│          Add Expense                │
│                                     │
│  ┌───────────────────────────────┐  │
│  │                               │  │
│  │   [Upload icon]               │  │
│  │   Click to upload receipt     │  │
│  │   or drag & drop here         │  │
│  │                               │  │
│  └───────────────────────────────┘  │
│                                     │
│  Amount                             │
│  ┌───────────────────────────────┐  │
│  │  $ |                          │  │
│  └───────────────────────────────┘  │
│                                     │
│  Category                           │
│  ┌──────┐ ┌───────────┐ ┌───────┐  │
│  │ Gas  │ │Maintenance│ │Parking│  │
│  └──────┘ └───────────┘ └───────┘  │
│  ┌────────┐ ┌────────┐ ┌───────┐  │
│  │Car Wash│ │Supplies│ │ Tolls │  │
│  └────────┘ └────────┘ └───────┘  │
│  ┌───────┐                         │
│  │ Other │                         │
│  └───────┘                         │
│                                     │
│  Date                               │
│  ┌───────────────────────────────┐  │
│  │  02/17/2026          [cal]   │  │
│  └───────────────────────────────┘  │
│                                     │
│  Description (optional)             │
│  ┌───────────────────────────────┐  │
│  │                               │  │
│  │                               │  │
│  └───────────────────────────────┘  │
│                                     │
│  ┌───────────────────────────────┐  │
│  │         Submit Expense        │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

### Ejemplo de request

```typescript
const formData = new FormData();
formData.append('receipt_photo', imageFile);  // File object
formData.append('amount', '45.50');
formData.append('expense_type', 'gas');
formData.append('expense_date', '2026-02-17');
formData.append('description', 'Filled up tank, was almost empty');

const response = await fetch(
  `${API_BASE}/v1/drivers/${driverId}/expenses`,
  {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      // NO poner Content-Type, el browser lo pone automaticamente con boundary
    },
    body: formData,
  }
);
```

### Response exitosa (200)

```json
{
  "status": "ok",
  "message": "Expense submitted for review",
  "expense": {
    "expense_id": "uuid",
    "driver_id": "uuid",
    "amount": 45.50,
    "expense_type": "gas",
    "description": "Filled up tank, was almost empty",
    "expense_date": "2026-02-17",
    "receipt_photo_url": "https://storage.../receipts/uuid.jpg",
    "receipt_uploaded": true,
    "status": "pending",
    "reviewed_at": null,
    "reviewed_by": null,
    "manager_notes": null,
    "rejection_reason": null,
    "pay_period_start": null,
    "pay_period_end": null,
    "included_in_payment": false,
    "created_at": "2026-02-17T15:30:00Z"
  }
}
```

### Validaciones (errores posibles)

| Error | Codigo | Causa |
|-------|--------|-------|
| `"Amount must be greater than 0"` | 400 | Monto es 0 o negativo |
| `"Expense date cannot be in the future"` | 400 | Fecha es posterior a hoy |
| `"Expense date cannot be more than 30 days in the past"` | 400 | Fecha tiene mas de 30 dias |
| `"Invalid expense type"` | 400 | Categoria no es una de las validas |
| `"Invalid date format. Use YYYY-MM-DD"` | 400 | Formato de fecha incorrecto |
| `"Driver not found"` | 404 | ID de driver invalido |
| `"Driver is not active"` | 403 | Driver esta desactivado |

### Despues de enviar exitosamente

1. Mostrar toast/snackbar: "Expense submitted for review"
2. Volver a la pantalla de Earnings
3. El expense aparecera en el desglose del periodo actual cuando el manager lo apruebe

---

## Resumen de Endpoints

| # | Metodo | Endpoint | Uso |
|---|--------|----------|-----|
| 1 | `GET` | `/v1/drivers/{id}/earnings?page=1&page_size=10` | Pantalla principal: current period, periodos, YTD |
| 2 | `GET` | `/v1/drivers/{id}/shifts?page=1&page_size=10` | Seccion Recent Shifts |
| 3 | `POST` | `/v1/drivers/{id}/expenses` | Enviar nuevo expense (multipart/form-data) |
| 4 | `GET` | `/v1/profile/driver` | Perfil del driver (pay_type, rate, frequency, location) |

### Flujo de carga de la pantalla

```
1. Al entrar a la tab "Earnings":
   |
   |-- GET /v1/drivers/{id}/earnings?page=1&page_size=10
   |   |
   |   |-- periods[0]          --> Current Period Earnings (header)
   |   |-- pay_type/frequency/rate --> Info Cards
   |   |-- periods[0] details  --> Current Period Breakdown
   |   |-- periods[1..n]       --> Pay Periods list
   |   |-- year_to_date        --> Guardar en state para sub-pantalla YTD
   |
   |-- GET /v1/drivers/{id}/shifts?page=1&page_size=10
   |   |
   |   |-- shifts[]            --> Recent Shifts section
   |
2. Al scroll en Pay Periods (lazy load):
   |-- GET /v1/drivers/{id}/earnings?page=2&page_size=10
   |
3. Al tocar "View Year-to-Date":
   |-- (No request adicional, usar year_to_date del state)
   |
4. Al tocar FAB (+) > "Add Expense":
   |-- Abrir formulario
   |-- POST /v1/drivers/{id}/expenses (al submit)
   |-- Refrescar earnings al volver
```

---

## TypeScript Interfaces

```typescript
// === EARNINGS ===

interface EarningsResponse {
  driver_id: string;
  driver_name: string;
  pay_type: 'hour' | 'day' | 'trip' | null;
  pay_frequency: 'daily' | 'weekly' | 'biweekly';
  rate: number | null;
  timezone: string;
  periods: Period[];
  pagination: Pagination;
  year_to_date: YearToDate;
}

interface Period {
  period_start: string;       // "2026-02-16"
  period_end: string;         // "2026-02-22"
  gross_earnings: number;
  verified_expenses: number;
  net_pay: number;
  total_hours: number;
  total_days: number;
  total_trips: number;
  total_shifts: number;
  expenses_count: number;
}

interface YearToDate {
  year: number;
  total_gross_earnings: number;
  total_expenses_reimbursed: number;
  total_net_pay: number;
  total_hours_worked: number;
  total_days_worked: number;
  total_trips: number;
}

interface Pagination {
  page: number;
  page_size: number;
  total_periods: number;   // o total_shifts / total_expenses
  total_pages: number;
}

// === SHIFTS ===

interface ShiftsResponse {
  shifts: Shift[];
  pagination: Pagination;
  summary: ShiftSummary;
}

interface Shift {
  shift_id: string;
  driver_id: string;
  pay_type: string | null;
  rate: number | null;
  started_at: string;         // ISO 8601
  ended_at: string | null;
  duration_hours: number | null;
  status: 'active' | 'completed' | 'under_review' | 'reviewed' | 'auto_closed';
  review_status: string | null;
  review_reason: string | null;
  reviewed_at: string | null;
  reviewed_by: string | null;
  manager_notes: string | null;
  auto_closed: boolean;
  crosses_midnight: boolean;
  trips_in_shift: number;
  hours_distribution: Record<string, number> | null;
  created_at: string;
}

interface ShiftSummary {
  active_shifts: number;
  completed_shifts: number;
  under_review_shifts: number;
}

// === EXPENSES ===

type ExpenseType = 'gas' | 'maintenance' | 'parking' | 'car_wash' | 'supplies' | 'tolls' | 'other';

interface SubmitExpenseForm {
  receipt_photo: File;
  amount: number;
  expense_type: ExpenseType;
  expense_date: string;       // YYYY-MM-DD
  description?: string;
}

interface ExpenseResponse {
  expense_id: string;
  driver_id: string;
  amount: number;
  expense_type: ExpenseType;
  description: string | null;
  expense_date: string;
  receipt_photo_url: string;
  receipt_uploaded: boolean;
  status: 'pending' | 'verified' | 'rejected';
  reviewed_at: string | null;
  reviewed_by: string | null;
  manager_notes: string | null;
  rejection_reason: string | null;
  pay_period_start: string | null;
  pay_period_end: string | null;
  included_in_payment: boolean;
  created_at: string;
}

// === DRIVER PROFILE ===

interface DriverProfile {
  id: string;
  first_name: string | null;
  last_name: string | null;
  email: string;
  phone: string | null;
  profile_pic: string | null;
  created_at: string;
  is_active: boolean;
  pay_type: string | null;
  pay_frequency: string | null;
  rate: number | null;
  location: {
    id: string;
    name: string;
    address: string | null;
    timezone: string;
  } | null;
  organization_id: string | null;
  organization_name: string | null;
}
```

---

## React Hooks (Web)

```typescript
import { useState, useEffect, useCallback } from 'react';

const API_BASE = 'https://api.gt360.app';

// ─────────────────────────────────────────────
// Hook para cargar la pantalla de earnings
// ─────────────────────────────────────────────
function useEarningsScreen(driverId: string, token: string) {
  const [earnings, setEarnings] = useState<EarningsResponse | null>(null);
  const [shifts, setShifts] = useState<Shift[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const headers = { 'Authorization': `Bearer ${token}` };

      const [earningsRes, shiftsRes] = await Promise.all([
        fetch(`${API_BASE}/v1/drivers/${driverId}/earnings?page=1&page_size=10`, { headers }),
        fetch(`${API_BASE}/v1/drivers/${driverId}/shifts?page=1&page_size=10`, { headers }),
      ]);

      if (!earningsRes.ok) throw new Error('Failed to load earnings');
      if (!shiftsRes.ok) throw new Error('Failed to load shifts');

      const earningsData: EarningsResponse = await earningsRes.json();
      const shiftsData: ShiftsResponse = await shiftsRes.json();

      setEarnings(earningsData);
      setShifts(shiftsData.shifts);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [driverId, token]);

  useEffect(() => { loadData(); }, [loadData]);

  // Current period = primer elemento de la lista (el mas reciente)
  const currentPeriod = earnings?.periods?.[0] ?? null;
  const pastPeriods = earnings?.periods?.slice(1) ?? [];
  const yearToDate = earnings?.year_to_date ?? null;

  return {
    earnings,
    currentPeriod,
    pastPeriods,
    yearToDate,
    shifts,
    loading,
    error,
    refresh: loadData,
  };
}


// ─────────────────────────────────────────────
// Hook para cargar mas periodos (paginacion)
// ─────────────────────────────────────────────
function useLoadMorePeriods(driverId: string, token: string) {
  const [periods, setPeriods] = useState<Period[]>([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(false);

  const loadMore = useCallback(async () => {
    if (loading || !hasMore) return;
    setLoading(true);

    const nextPage = page + 1;
    try {
      const res = await fetch(
        `${API_BASE}/v1/drivers/${driverId}/earnings?page=${nextPage}&page_size=10`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      const data: EarningsResponse = await res.json();

      setPeriods(prev => [...prev, ...data.periods]);
      setPage(nextPage);
      setHasMore(nextPage < data.pagination.total_pages);
    } finally {
      setLoading(false);
    }
  }, [driverId, token, page, hasMore, loading]);

  return { periods, loadMore, hasMore, loading };
}


// ─────────────────────────────────────────────
// Hook para enviar expense
// ─────────────────────────────────────────────
function useSubmitExpense(driverId: string, token: string) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = useCallback(async (data: SubmitExpenseForm): Promise<ExpenseResponse | null> => {
    setLoading(true);
    setError(null);

    const formData = new FormData();
    formData.append('receipt_photo', data.receipt_photo);
    formData.append('amount', data.amount.toString());
    formData.append('expense_type', data.expense_type);
    formData.append('expense_date', data.expense_date);
    if (data.description) {
      formData.append('description', data.description);
    }

    try {
      const response = await fetch(
        `${API_BASE}/v1/drivers/${driverId}/expenses`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            // NO poner Content-Type, el browser lo pone automaticamente con boundary
          },
          body: formData,
        }
      );

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to submit expense');
      }

      const result = await response.json();
      return result.expense;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      return null;
    } finally {
      setLoading(false);
    }
  }, [driverId, token]);

  return { submit, loading, error };
}
```

### Ejemplo de uso en componente React

```tsx
function EarningsPage() {
  const { user } = useAuth(); // tu hook de auth
  const driverId = user.id;
  const token = user.token;

  const {
    earnings,
    currentPeriod,
    pastPeriods,
    yearToDate,
    shifts,
    loading,
    refresh,
  } = useEarningsScreen(driverId, token);

  const { submit, loading: submitting, error: submitError } = useSubmitExpense(driverId, token);
  const [showExpenseModal, setShowExpenseModal] = useState(false);

  if (loading) return <Spinner />;

  return (
    <div className="earnings-page">
      {/* Header - Current Period */}
      <div className="current-earnings">
        <p className="label">
          {earnings?.pay_frequency === 'weekly' && "This Week's Earnings"}
          {earnings?.pay_frequency === 'biweekly' && "Current Pay Period"}
          {earnings?.pay_frequency === 'daily' && "Today's Earnings"}
        </p>
        <h1 className="amount">{formatCurrency(currentPeriod?.gross_earnings)}</h1>
        <p className="dates">
          {formatDateRange(currentPeriod?.period_start, currentPeriod?.period_end)}
        </p>
      </div>

      {/* Info Cards */}
      <div className="info-cards">
        <Card label="Pay Type" value={formatPayType(earnings?.pay_type)} />
        <Card label="Frequency" value={capitalize(earnings?.pay_frequency)} />
        <Card label="Rate" value={formatRate(earnings?.rate, earnings?.pay_type)} />
      </div>

      {/* Current Period Breakdown */}
      <section className="breakdown">
        <h3>Current Period Breakdown</h3>
        <Stat label="Gross Earnings" value={formatCurrency(currentPeriod?.gross_earnings)} />
        <Stat label="Reimbursements" value={formatCurrency(currentPeriod?.verified_expenses)} />
        <Stat label="Net Pay" value={formatCurrency(currentPeriod?.net_pay)} />
        <Stat label="Trips" value={currentPeriod?.total_trips} />
        <Stat label="Hours" value={`${currentPeriod?.total_hours} hrs`} />
        <Stat label="Shifts" value={currentPeriod?.total_shifts} />
      </section>

      {/* Pay Periods List */}
      <section className="pay-periods">
        <h3>Pay Periods</h3>
        {pastPeriods.map((period, i) => (
          <PeriodCard key={i} period={period} />
        ))}
      </section>

      {/* Recent Shifts */}
      <section className="recent-shifts">
        <h3>Recent Shifts</h3>
        {shifts.map(shift => (
          <ShiftCard key={shift.shift_id} shift={shift} />
        ))}
      </section>

      {/* YTD Link */}
      <Link to="/earnings/year-to-date">View Year-to-Date Summary</Link>

      {/* FAB - Add Expense */}
      <button className="fab" onClick={() => setShowExpenseModal(true)}>+</button>

      {showExpenseModal && (
        <AddExpenseModal
          onSubmit={async (data) => {
            const result = await submit(data);
            if (result) {
              setShowExpenseModal(false);
              refresh(); // recargar earnings
            }
          }}
          onClose={() => setShowExpenseModal(false)}
          loading={submitting}
          error={submitError}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// Helper functions
// ─────────────────────────────────────────────
function formatCurrency(value?: number | null): string {
  if (value == null) return '$0.00';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(value);
}

function formatPayType(payType?: string | null): string {
  switch (payType) {
    case 'hour': return 'Hourly';
    case 'day': return 'Daily';
    case 'trip': return 'Per Trip';
    default: return 'N/A';
  }
}

function formatRate(rate?: number | null, payType?: string | null): string {
  if (rate == null) return 'N/A';
  const formatted = formatCurrency(rate);
  switch (payType) {
    case 'hour': return `${formatted}/hr`;
    case 'day': return `${formatted}/day`;
    case 'trip': return `${formatted}/trip`;
    default: return formatted;
  }
}

function formatDateRange(start?: string | null, end?: string | null): string {
  if (!start || !end) return '';
  const s = new Date(start + 'T00:00:00');
  const e = new Date(end + 'T00:00:00');
  const opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' };
  const yearOpts: Intl.DateTimeFormatOptions = { ...opts, year: 'numeric' };
  return `${s.toLocaleDateString('en-US', opts)} - ${e.toLocaleDateString('en-US', yearOpts)}`;
}

function capitalize(s?: string | null): string {
  if (!s) return 'N/A';
  return s.charAt(0).toUpperCase() + s.slice(1);
}
```

---

## Notas Importantes

1. **`periods[0]` = periodo actual.** La lista viene ordenada del mas reciente al mas antiguo. El primer elemento siempre es el periodo de pago en curso.

2. **`year_to_date` viene incluido** en el response de earnings. No hace falta un request separado. Guardarlo en state y mostrarlo solo cuando el usuario navegue a la sub-pantalla de YTD.

3. **Expenses usa `multipart/form-data`**, no JSON. No poner `Content-Type: application/json`. Dejar que el browser/RN ponga el content-type automaticamente con el boundary.

4. **La fecha del expense** no puede ser futura ni mas de 30 dias atras.

5. **El receipt (foto) es obligatorio.** No se puede enviar un expense sin recibo.

6. **El status del expense empieza como `"pending"`**. El driver lo vera en sus expenses pero no se sumara a sus earnings hasta que el manager lo apruebe (`"verified"`).

7. **Rate por shift:** Cada shift guarda el rate que tenia el driver al iniciarlo. Si el manager cambia el rate, los shifts viejos mantienen su rate original.

8. **Formato de moneda:** Siempre USD. Usar `Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })` o equivalente.

9. **Timezone:** El response incluye el timezone del driver. Usar para formatear las horas de los shifts en hora local.

---

**Ultima actualizacion:** 2026-02-17
