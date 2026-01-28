# Guía Frontend: Endpoints de Airlines y Months

**Fecha:** 2026-01-21
**Versión:** 1.0.0
**Tipo:** Guía de integración frontend

---

## 📋 Índice

1. [Sistema de Autenticación](#sistema-de-autenticación)
2. [Endpoint GET /airlines](#endpoint-get-airlines)
3. [Endpoint GET /months](#endpoint-get-months)
4. [Error "Invalid Token" - Troubleshooting](#error-invalid-token)
5. [Implementación Frontend](#implementación-frontend)
6. [Hooks Recomendados](#hooks-recomendados)
7. [Testing](#testing)
8. [FAQ](#faq)

---

## 🔐 Sistema de Autenticación

### Flujo de Autenticación

```
Usuario → Login → Backend genera JWT → Frontend guarda token →
Frontend envía token en cada request → Backend valida token → Response
```

### Estructura del JWT Token

**Payload del token:**
```json
{
  "sub": "550e8400-e29b-41d4-a716-446655440000",  // User ID
  "iat": 1737417600,                               // Issued at (timestamp)
  "exp": 1737421200,                               // Expiration (timestamp)
  "metadata": {
    "email": "user@example.com",
    "phone": "+15551234567",
    "role": "manager",                             // manager | driver | crew
    "organization_id": "org-uuid-here"
  }
}
```

### Middleware de Verificación

**Archivo:** `features/auth/middlewares/verify_token.py`

El middleware `VerifyToken` intercepta **TODAS las requests** (excepto WebSocket y OPTIONS) y:

1. **Extrae el token** del header `Authorization: Bearer {token}`
2. **Decodifica el token** usando JWT con `JWT_SECRET_KEY`
3. **Valida:**
   - Firma del token (no modificado)
   - Token no expirado (`exp` > ahora)
   - Token no en blacklist (Redis)
4. **Pone los datos en `request.state.user_data`:**
   ```python
   request.state.user_data = {
       "id": "user-uuid",
       "email": "user@example.com",
       "phone": "+15551234567",
       "role": "manager",
       "organization_id": "org-uuid"
   }
   ```

### Causas de Error 401 "Invalid token"

| Causa | Descripción |
|-------|-------------|
| **Token expirado** | `exp` < timestamp actual |
| **Token malformado** | JWT no puede ser decodificado |
| **Firma inválida** | Token fue modificado |
| **Sin header Authorization** | Falta el header en la request |
| **Formato incorrecto** | No es "Bearer {token}" |
| **Token en blacklist** | Token fue revocado (logout) |

---

## 📡 Endpoint GET /airlines

### Descripción

Retorna todas las **airlines únicas** disponibles para una location específica.

**Utilidad:**
- Poblar dropdowns de airlines sin cargar todos los trips
- Navegación entre airlines
- Source of truth para airlines disponibles

### Request

```http
GET /v1/locations/{location_id}/airlines
Authorization: Bearer {JWT_TOKEN}
```

**Parámetros:**
- `location_id` (path, required): UUID de la location

**Autenticación:**
- Requiere rol: `manager` o `driver`
- Token JWT válido en header Authorization

### Response 200 (Success)

```json
{
  "location_id": "b88b3f47-5d97-4854-9590-b32da5f2efef",
  "location_name": "SDF",
  "airlines": [
    "AA",
    "DL",
    "UA",
    "WN"
  ],
  "total": 4
}
```

**Campos:**
- `location_id`: UUID de la location
- `location_name`: Código/nombre de la location (ej: "SDF", "ORD")
- `airlines`: Array de strings con códigos IATA (ordenados alfabéticamente)
- `total`: Número total de airlines únicas

### Respuestas de Error

| Código | Condición | Response |
|--------|-----------|----------|
| 400 | UUID inválido | `{"detail": "ID de location inválido"}` |
| 401 | Sin token / Token inválido | `{"detail": "Invalid token"}` |
| 403 | Sin permisos (rol incorrecto) | `{"detail": "Not Authorized: We couldn't validate the role"}` |
| 404 | Location no existe | `{"detail": "Location no encontrada"}` |

### Implementación Backend

**Archivo:** `features/trips/routes/trips_router.py` (líneas 912-973)

**Query SQL:**
```python
airlines_stmt = (
    Select(TripDB.airline)
    .Where(TripDB.location_id == location_uuid)
    .Distinct()
    .OrderBy(TripDB.airline.Asc())
)
```

**Optimización:**
- Solo consulta la columna `airline` (no toda la tabla)
- `DISTINCT` elimina duplicados en SQL (no en Python)
- `ORDER BY` ordena alfabéticamente en SQL
- Muy rápido (~10-30ms) incluso con miles de trips

---

## 📅 Endpoint GET /months

### Descripción

Retorna todos los **meses únicos** con trips disponibles para una location (opcionalmente filtrados por airline).

**Utilidad:**
- Poblar MonthYearPicker sin calcular client-side
- Source of truth para meses disponibles
- Evita procesar miles de trips en el frontend
- No depende de snapshot de WebSocket

### Request

```http
GET /v1/locations/{location_id}/months?airline={airline}
Authorization: Bearer {JWT_TOKEN}
```

**Parámetros:**
- `location_id` (path, required): UUID de la location
- `airline` (query, optional): Código IATA para filtrar (ej: "WN", "AA")

**Autenticación:**
- Requiere rol: `manager` o `driver`
- Token JWT válido en header Authorization

### Response 200 (Success)

#### Sin filtro de airline

```json
{
  "location_id": "b88b3f47-5d97-4854-9590-b32da5f2efef",
  "location_name": "SDF",
  "airline": null,
  "months": [
    { "year": 2026, "month": 2, "count": 1341 },   // Marzo (month: 2 en JS)
    { "year": 2026, "month": 1, "count": 890 },    // Febrero
    { "year": 2026, "month": 0, "count": 750 }     // Enero
  ],
  "total_months": 3
}
```

#### Con filtro de airline

```json
{
  "location_id": "b88b3f47-5d97-4854-9590-b32da5f2efef",
  "location_name": "SDF",
  "airline": "WN",
  "months": [
    { "year": 2026, "month": 1, "count": 450 },
    { "year": 2026, "month": 0, "count": 320 }
  ],
  "total_months": 2
}
```

**IMPORTANTE:** El campo `month` usa el formato de JavaScript (0-11):
- 0 = Enero
- 1 = Febrero
- ...
- 11 = Diciembre

**Campos:**
- `location_id`: UUID de la location
- `location_name`: Código/nombre de la location
- `airline`: Airline filtrada (null si no se especificó)
- `months`: Array de objetos ordenados por año/mes DESC (más reciente primero)
  - `year`: Año (ej: 2026)
  - `month`: Mes en formato JS 0-11
  - `count`: Número de trips en ese mes/año
- `total_months`: Total de meses únicos encontrados

### Respuestas de Error

| Código | Condición | Response |
|--------|-----------|----------|
| 400 | UUID inválido | `{"detail": "ID de location inválido"}` |
| 401 | Sin token / Token inválido | `{"detail": "Invalid token"}` |
| 403 | Sin permisos | `{"detail": "Not Authorized: We couldn't validate the role"}` |
| 404 | Location no existe | `{"detail": "Location no encontrada"}` |

### Implementación Backend

**Archivo:** `features/trips/routes/trips_router.py` (líneas 975+)

**Query SQL:**
```sql
SELECT
    EXTRACT(YEAR FROM pick_up_date)::int AS year,
    EXTRACT(MONTH FROM pick_up_date)::int AS month,
    COUNT(*)::int AS trips_count
FROM trips.trips
WHERE location_id = :location_id
  AND airline ILIKE :airline  -- Solo si se especifica airline
GROUP BY year, month
ORDER BY year DESC, month DESC
```

**Optimización:**
- Query SQL optimizada con `GROUP BY`
- Solo procesa fechas (no carga trips completos)
- Muy rápido (~20-50ms) con miles de trips
- Respuesta pequeña (~200-800 bytes)

---

## ❌ Error "Invalid Token" - Troubleshooting

### Síntoma

```javascript
[useLocationAirlines] Error: "Invalid token"
```

### Causas Posibles y Soluciones

#### 1. Token Expirado

**Causa:** JWT tiene `exp` menor que el timestamp actual.

**Cómo verificar:**
```javascript
// Decodificar el token (en consola del navegador)
const token = localStorage.getItem('token')
const [header, payload, signature] = token.split('.')
const decoded = JSON.parse(atob(payload))

console.log('Token expira en:', new Date(decoded.exp * 1000))
console.log('Ahora:', new Date())

if (decoded.exp * 1000 < Date.now()) {
  console.error('❌ TOKEN EXPIRADO')
}
```

**Solución:**
```typescript
// Implementar refresh automático antes de que expire
const refreshTokenBeforeExpiry = async () => {
  const decoded = decodeToken(token)
  const expiresIn = (decoded.exp * 1000) - Date.now()

  // Refrescar 5 minutos antes de expirar
  if (expiresIn < 5 * 60 * 1000) {
    await refreshAuthToken()
  }
}
```

#### 2. Token No Enviado o Formato Incorrecto

**Causa:** Header `Authorization` falta o no tiene formato `Bearer {token}`.

**Cómo verificar:**
```javascript
// En Network tab de DevTools
// Headers de la request:
Authorization: Bearer eyJhbGc...  // ✅ Correcto
Authorization: eyJhbGc...         // ❌ Falta "Bearer "
// (sin header)                   // ❌ Falta header completo
```

**Solución:**
```typescript
// Asegurarse de enviar el header correctamente
const response = await fetch(`${API_URL}/v1/locations/${locationId}/airlines`, {
  headers: {
    'Authorization': `Bearer ${token}`,  // ✅ Incluir "Bearer "
    'Content-Type': 'application/json'
  }
})
```

#### 3. Token Guardado Incorrectamente

**Causa:** Token en localStorage/sessionStorage está corrupto o incompleto.

**Cómo verificar:**
```javascript
const token = localStorage.getItem('token')
console.log('Token length:', token?.length)
console.log('Token starts with:', token?.substring(0, 10))

// Un JWT válido tiene formato: xxxxx.yyyyy.zzzzz
const parts = token?.split('.')
if (parts?.length !== 3) {
  console.error('❌ TOKEN MALFORMADO (debe tener 3 partes)')
}
```

**Solución:**
```typescript
// Al guardar el token después del login:
const saveToken = (tokenFromBackend: string) => {
  // Validar formato antes de guardar
  const parts = tokenFromBackend.split('.')
  if (parts.length !== 3) {
    throw new Error('Invalid token format')
  }

  localStorage.setItem('token', tokenFromBackend)
}
```

#### 4. Token de Otro Ambiente

**Causa:** Usando token de staging en producción o viceversa.

**Cómo verificar:**
```javascript
const token = localStorage.getItem('token')
const payload = JSON.parse(atob(token.split('.')[1]))

console.log('Token metadata:', payload.metadata)
// Verificar que organization_id, email sean correctos
```

**Solución:**
```typescript
// Limpiar tokens al cambiar de ambiente
if (window.location.hostname.includes('staging')) {
  // Staging environment
  if (token && !isTokenForStaging(token)) {
    localStorage.removeItem('token')
    redirectToLogin()
  }
}
```

#### 5. CORS Bloqueando el Header

**Causa:** Backend no retorna headers CORS correctos en error 401.

**Cómo verificar:**
```
Network tab → Request → Response Headers
Access-Control-Allow-Origin: (debería estar presente)
```

**Nota:** El backend YA maneja esto correctamente (líneas 28-38 de `verify_token.py`):
```python
allowed_origins = [
    "https://www.gt360.com",
    "https://gt360.com",
    "https://web.gt360.app",
    "https://charmaine-leadless-ryleigh.ngrok-free.dev"
]
if origin in allowed_origins:
    response.headers["Access-Control-Allow-Origin"] = origin
```

---

## 💻 Implementación Frontend

### Hook useLocationAirlines

```typescript
// hooks/useLocationAirlines.ts
import { useEffect, useState } from 'react'

interface AirlinesResponse {
  location_id: string
  location_name: string
  airlines: string[]
  total: number
}

export function useLocationAirlines(locationId: string | null) {
  const [airlines, setAirlines] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    if (!locationId) {
      setLoading(false)
      return
    }

    let cancelled = false

    async function fetchAirlines() {
      try {
        setLoading(true)

        const token = localStorage.getItem('token')
        if (!token) {
          throw new Error('No authentication token found')
        }

        const url = `${process.env.NEXT_PUBLIC_API_URL}/v1/locations/${locationId}/airlines`

        const response = await fetch(url, {
          headers: {
            'Authorization': `Bearer ${token}`,  // ✅ Incluir Bearer
            'Content-Type': 'application/json'
          }
        })

        if (!response.ok) {
          // Leer el body del error
          const errorData = await response.json()
          throw new Error(errorData.detail || `HTTP ${response.status}`)
        }

        const data: AirlinesResponse = await response.json()

        if (!cancelled) {
          setAirlines(data.airlines)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) {
          console.error('[useLocationAirlines] Error:', err.message)
          setError(err as Error)
          setAirlines([])
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    fetchAirlines()

    return () => {
      cancelled = true
    }
  }, [locationId])

  return { airlines, loading, error }
}
```

### Hook useLocationMonths

```typescript
// hooks/useLocationMonths.ts
import { useEffect, useState } from 'react'

interface MonthData {
  year: number
  month: number  // 0-11 (JavaScript format)
  count: number
}

interface MonthsResponse {
  location_id: string
  location_name: string
  airline: string | null
  months: MonthData[]
  total_months: number
}

export function useLocationMonths(
  locationId: string | null,
  airline?: string | null
) {
  const [months, setMonths] = useState<MonthData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    if (!locationId) {
      setLoading(false)
      return
    }

    let cancelled = false

    async function fetchMonths() {
      try {
        setLoading(true)

        const token = localStorage.getItem('token')
        if (!token) {
          throw new Error('No authentication token found')
        }

        const url = new URL(
          `${process.env.NEXT_PUBLIC_API_URL}/v1/locations/${locationId}/months`
        )

        if (airline) {
          url.searchParams.set('airline', airline)
        }

        const response = await fetch(url.toString(), {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        })

        if (!response.ok) {
          const errorData = await response.json()
          throw new Error(errorData.detail || `HTTP ${response.status}`)
        }

        const data: MonthsResponse = await response.json()

        if (!cancelled) {
          setMonths(data.months)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) {
          console.error('[useLocationMonths] Error:', err.message)
          setError(err as Error)
          setMonths([])
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    fetchMonths()

    return () => {
      cancelled = true
    }
  }, [locationId, airline])

  return { months, loading, error }
}
```

### Uso en Componentes

```typescript
// components/ScheduleDashboard.tsx
import { useLocationAirlines } from '@/hooks/useLocationAirlines'
import { useLocationMonths } from '@/hooks/useLocationMonths'

export function ScheduleDashboard({ locationId }: { locationId: string }) {
  // 1. Obtener airlines disponibles
  const {
    airlines,
    loading: airlinesLoading,
    error: airlinesError
  } = useLocationAirlines(locationId)

  const [selectedAirline, setSelectedAirline] = useState<string | null>(null)

  // 2. Auto-seleccionar primera airline
  useEffect(() => {
    if (airlines.length > 0 && !selectedAirline) {
      setSelectedAirline(airlines[0])
    }
  }, [airlines, selectedAirline])

  // 3. Obtener meses disponibles para airline seleccionada
  const {
    months: availableMonths,
    loading: monthsLoading,
    error: monthsError
  } = useLocationMonths(locationId, selectedAirline)

  const [selectedMonth, setSelectedMonth] = useState<number | null>(null)
  const [selectedYear, setSelectedYear] = useState<number | null>(null)

  // 4. Auto-seleccionar mes más reciente
  useEffect(() => {
    if (availableMonths.length > 0 && selectedMonth === null) {
      const latest = availableMonths[0] // Ya viene ordenado DESC
      setSelectedMonth(latest.month)
      setSelectedYear(latest.year)
    }
  }, [availableMonths, selectedMonth])

  return (
    <div>
      {/* Airline Selector */}
      {airlinesLoading ? (
        <Spinner />
      ) : airlinesError ? (
        <ErrorBanner error={airlinesError} />
      ) : (
        <select
          value={selectedAirline || ''}
          onChange={(e) => setSelectedAirline(e.target.value)}
        >
          {airlines.map(airline => (
            <option key={airline} value={airline}>
              {airline}
            </option>
          ))}
        </select>
      )}

      {/* Month/Year Picker */}
      {monthsLoading ? (
        <Spinner />
      ) : monthsError ? (
        <ErrorBanner error={monthsError} />
      ) : (
        <MonthYearPicker
          availableMonths={availableMonths}
          selectedMonth={selectedMonth}
          selectedYear={selectedYear}
          onMonthChange={setSelectedMonth}
          onYearChange={setSelectedYear}
        />
      )}

      {/* Trips Table */}
      <TripsTable
        locationId={locationId}
        airline={selectedAirline}
        month={selectedMonth}
        year={selectedYear}
      />
    </div>
  )
}
```

---

## 🧪 Testing

### Test Manual con cURL

```bash
# 1. Obtener token (login)
TOKEN=$(curl -X POST "https://api.gt360.app/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "password123"
  }' | jq -r '.access_token')

echo "Token: $TOKEN"

# 2. Test /airlines
curl -X GET "https://api.gt360.app/v1/locations/b88b3f47-5d97-4854-9590-b32da5f2efef/airlines" \
  -H "Authorization: Bearer $TOKEN" \
  | jq

# Esperado:
# {
#   "location_id": "...",
#   "location_name": "SDF",
#   "airlines": ["AA", "DL", "UA", "WN"],
#   "total": 4
# }

# 3. Test /months sin filtro
curl -X GET "https://api.gt360.app/v1/locations/b88b3f47-5d97-4854-9590-b32da5f2efef/months" \
  -H "Authorization: Bearer $TOKEN" \
  | jq

# 4. Test /months con filtro de airline
curl -X GET "https://api.gt360.app/v1/locations/b88b3f47-5d97-4854-9590-b32da5f2efef/months?airline=WN" \
  -H "Authorization: Bearer $TOKEN" \
  | jq

# 5. Test error: token inválido
curl -X GET "https://api.gt360.app/v1/locations/b88b3f47-5d97-4854-9590-b32da5f2efef/airlines" \
  -H "Authorization: Bearer invalid-token" \
  | jq

# Esperado: {"detail": "Invalid token"}
```

### Test en Frontend (DevTools Console)

```javascript
// 1. Verificar token
const token = localStorage.getItem('token')
console.log('Token exists:', !!token)
console.log('Token length:', token?.length)

// 2. Decodificar token
if (token) {
  try {
    const parts = token.split('.')
    const payload = JSON.parse(atob(parts[1]))
    console.log('Token payload:', payload)
    console.log('Expira en:', new Date(payload.exp * 1000))
    console.log('Expirado:', payload.exp * 1000 < Date.now())
  } catch (e) {
    console.error('Error decodificando token:', e)
  }
}

// 3. Test fetch manual
const testAirlines = async () => {
  try {
    const response = await fetch(
      'https://api.gt360.app/v1/locations/b88b3f47-5d97-4854-9590-b32da5f2efef/airlines',
      {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      }
    )

    console.log('Status:', response.status)
    const data = await response.json()
    console.log('Data:', data)
  } catch (error) {
    console.error('Error:', error)
  }
}

testAirlines()
```

---

## ❓ FAQ

### ¿Por qué el frontend NO debería calcular airlines/months client-side?

**Razones:**

1. **Ineficiente:** Procesar miles de trips para extraer valores únicos
2. **Inconsistente:** Depende de snapshot de WebSocket (puede estar incompleto)
3. **Lento:** Se recalcula cada vez que llega un evento WebSocket
4. **No es source of truth:** Base de datos es la fuente definitiva

**Ejemplo del problema:**
```typescript
// ❌ MAL: Procesa 5000 trips client-side
const airlines = extractUniqueAirlines(storeTrips) // Procesa 5000 trips
const months = extractAvailableMonths(storeTrips)  // Procesa 5000 trips

// Se ejecuta cada vez que:
// - Llega evento WebSocket (1000 veces si subes 1000 trips)
// - Cambia la location
// - Se actualiza el store

// ✅ BIEN: Query SQL optimizada
const { airlines } = useLocationAirlines(locationId)  // ~10-30ms
const { months } = useLocationMonths(locationId)      // ~20-50ms
```

### ¿Los endpoints se cachean?

**En el backend:** No hay caché actualmente.

**Recomendación frontend:**
```typescript
// Cachear por 2 minutos (airlines no cambian frecuentemente)
const CACHE_TTL = 2 * 60 * 1000

const cachedFetch = async (key: string, fetcher: () => Promise<any>) => {
  const cached = sessionStorage.getItem(key)
  if (cached) {
    const { data, timestamp } = JSON.parse(cached)
    if (Date.now() - timestamp < CACHE_TTL) {
      return data
    }
  }

  const data = await fetcher()
  sessionStorage.setItem(key, JSON.stringify({
    data,
    timestamp: Date.now()
  }))
  return data
}
```

### ¿Cuándo refetch airlines/months?

**Refetch airlines cuando:**
- Cambia la location
- Después de upload de Excel (pueden haberse agregado nuevas airlines)

**Refetch months cuando:**
- Cambia la location
- Cambia la airline seleccionada
- Después de upload de Excel (pueden haberse agregado nuevos meses)

**NO refetch:**
- Cada vez que llega un evento WebSocket
- Al navegar entre meses (meses no cambian)

### ¿Qué hacer si el token expira?

**Opciones:**

1. **Refresh automático antes de expirar:**
```typescript
const refreshTokenBeforeExpiry = () => {
  const token = localStorage.getItem('token')
  const decoded = decodeToken(token)
  const expiresIn = (decoded.exp * 1000) - Date.now()

  if (expiresIn < 5 * 60 * 1000) {
    // Refrescar 5 min antes
    refreshAuthToken()
  }
}

// Ejecutar cada minuto
setInterval(refreshTokenBeforeExpiry, 60 * 1000)
```

2. **Interceptor global que detecta 401:**
```typescript
const fetchWithAuth = async (url: string, options: RequestInit = {}) => {
  const response = await fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      'Authorization': `Bearer ${localStorage.getItem('token')}`
    }
  })

  if (response.status === 401) {
    // Token expirado, redirect a login
    localStorage.removeItem('token')
    window.location.href = '/login'
  }

  return response
}
```

### ¿Los meses se ordenan automáticamente?

**Sí.** El backend retorna meses ordenados **DESC** (más reciente primero):

```json
{
  "months": [
    { "year": 2026, "month": 2 },   // Marzo 2026 (más reciente)
    { "year": 2026, "month": 1 },   // Febrero 2026
    { "year": 2026, "month": 0 },   // Enero 2026
    { "year": 2025, "month": 11 }   // Diciembre 2025 (más antiguo)
  ]
}
```

Para auto-seleccionar el mes más reciente:
```typescript
const latest = months[0]  // Primer elemento = más reciente
setSelectedMonth(latest.month)
setSelectedYear(latest.year)
```

---

## 🔗 Referencias

- [ANALISIS_PROBLEMA_PAGINADOR.md](./ANALISIS_PROBLEMA_PAGINADOR.md) - Problema original del paginador
- [FRONTEND_MONTHS_ENDPOINT.md](./FRONTEND_MONTHS_ENDPOINT.md) - Detalle del endpoint /months
- [FLIGHT_TRACKING_FRONTEND_GUIDE.md](./FLIGHT_TRACKING_FRONTEND_GUIDE.md) - Sistema de autenticación

---

## 📊 Comparación de Performance

| Operación | Client-Side (antes) | Endpoint (ahora) |
|-----------|---------------------|------------------|
| Obtener airlines | Procesar 5000 trips (~200-500ms) | Query SQL (~10-30ms) |
| Obtener months | Procesar 5000 trips (~200-500ms) | Query SQL (~20-50ms) |
| Recalcular al WebSocket event | Sí (1000 veces en upload) | No (se llama 1 vez) |
| Depende de snapshot WS | Sí (puede estar incompleto) | No (source of truth: DB) |
| Payload de respuesta | N/A (ya está en memoria) | ~200-800 bytes |
| Source of truth | Frontend (inestable) | Backend (confiable) |

---

**Estado:** ✅ Endpoints implementados y funcionando
**Backend:** Producción (https://api.gt360.app)
**Versión:** 1.0.0
**Última actualización:** 2026-01-21
