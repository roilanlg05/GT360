# Nuevo Endpoint: GET Airlines por Location

**Fecha:** 2026-01-14
**Tipo:** Nueva funcionalidad
**Impacto:** Resuelve problema de navegación entre airlines

---

## 🎯 Problema Resuelto

### Antes (Problema)
```
URL: /dashboard/locations/SDF/WN
      ↓
Backend: GET /v1/locations/{id}/trips?airline=WN
      ↓
Respuesta: Solo trips de WN
      ↓
Frontend: uniqueAirlines = ["WN"]
      ↓
Dropdown: Solo muestra "WN" ❌
```

**Resultado:** No había forma de saber qué otras airlines existen para navegar.

### Ahora (Solución)
```
Frontend: GET /v1/locations/{id}/airlines
      ↓
Respuesta: ["WN", "AA", "DEL", "UA", "DL"]
      ↓
Dropdown: Muestra todas las airlines ✅
      ↓
Navegación: "SDF / WN - AA - DEL - UA - DL"
```

---

## 📡 Nuevo Endpoint

### Request

```http
GET /v1/locations/{location_id}/airlines
Authorization: Bearer <JWT_TOKEN>
```

**Parámetros:**
- `location_id` (path, required): UUID de la location

**Autenticación:**
- Requiere rol: `manager` o `driver`
- Token JWT válido en header Authorization

### Response 200 (Success)

```json
{
  "location_id": "6d636fef-0a01-4126-87e5-2759f4ec4074",
  "location_name": "SDF",
  "airlines": ["AA", "DEL", "DL", "UA", "WN"],
  "total": 5
}
```

**Campos:**
- `location_id`: UUID de la location
- `location_name`: Nombre/código de la location (ej: "SDF")
- `airlines`: Array de strings con códigos de airlines, ordenados alfabéticamente
- `total`: Número total de airlines únicas

### Respuestas de Error

| Código | Condición | Respuesta |
|--------|-----------|-----------|
| 400 | UUID inválido | `{"detail": "ID de location inválido"}` |
| 404 | Location no existe | `{"detail": "Location no encontrada"}` |
| 401 | Sin token | `{"detail": "Not authenticated"}` |
| 403 | Sin permisos | `{"detail": "Insufficient permissions"}` |

---

## 💻 Implementación en Frontend

### Opción 1: Fetch al cargar la página (Recomendado)

```typescript
// En tu page.tsx o componente principal
import { useEffect, useState } from 'react';

interface AirlinesResponse {
  location_id: string;
  location_name: string;
  airlines: string[];
  total: number;
}

function SchedulePage({ params }: { params: { code: string; airline: string } }) {
  const [availableAirlines, setAvailableAirlines] = useState<string[]>([]);
  const [currentAirline, setCurrentAirline] = useState(params.airline);

  useEffect(() => {
    // Fetch airlines disponibles para la location
    async function fetchAirlines() {
      try {
        const response = await fetch(
          `${API_URL}/v1/locations/${locationId}/airlines`,
          {
            headers: {
              'Authorization': `Bearer ${token}`
            }
          }
        );

        if (!response.ok) {
          throw new Error('Failed to fetch airlines');
        }

        const data: AirlinesResponse = await response.json();
        setAvailableAirlines(data.airlines);
      } catch (error) {
        console.error('Error fetching airlines:', error);
        setAvailableAirlines([]);
      }
    }

    fetchAirlines();
  }, [locationId]);

  return (
    <div>
      {/* Navegación tipo tabs */}
      <div className="flex gap-2 mb-4">
        {availableAirlines.map(airline => (
          <button
            key={airline}
            onClick={() => router.push(`/dashboard/locations/${params.code}/${airline}`)}
            className={currentAirline === airline ? 'active' : ''}
          >
            {airline}
          </button>
        ))}
      </div>

      {/* Resto del dashboard */}
      <ScheduleDashboard airline={currentAirline} />
    </div>
  );
}
```

### Opción 2: Integrar con tu API client existente

```typescript
// En tu api.ts o services/api.ts
export async function getLocationAirlines(locationId: string): Promise<string[]> {
  const response = await fetch(
    `${API_URL}/v1/locations/${locationId}/airlines`,
    {
      headers: {
        'Authorization': `Bearer ${getToken()}`
      }
    }
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch airlines: ${response.statusText}`);
  }

  const data = await response.json();
  return data.airlines;
}

// Usar en tu componente
const airlines = await getLocationAirlines(locationId);
```

### Opción 3: Custom Hook

```typescript
// hooks/useLocationAirlines.ts
import { useEffect, useState } from 'react';

export function useLocationAirlines(locationId: string | null) {
  const [airlines, setAirlines] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!locationId) {
      setLoading(false);
      return;
    }

    let cancelled = false;

    async function fetchAirlines() {
      try {
        setLoading(true);
        const response = await fetch(
          `${API_URL}/v1/locations/${locationId}/airlines`,
          {
            headers: {
              'Authorization': `Bearer ${getToken()}`
            }
          }
        );

        if (!response.ok) {
          throw new Error('Failed to fetch airlines');
        }

        const data = await response.json();

        if (!cancelled) {
          setAirlines(data.airlines);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err as Error);
          setAirlines([]);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    fetchAirlines();

    return () => {
      cancelled = true;
    };
  }, [locationId]);

  return { airlines, loading, error };
}

// Usar en componente
function MyComponent() {
  const { airlines, loading, error } = useLocationAirlines(locationId);

  if (loading) return <Spinner />;
  if (error) return <ErrorMessage error={error} />;

  return (
    <AirlineNavigator airlines={airlines} current={currentAirline} />
  );
}
```

---

## 🎨 Sugerencias de UI/UX

### 1. Tabs horizontales (Recomendado)
```tsx
<div className="flex gap-2 border-b mb-4">
  {airlines.map(code => (
    <Link
      key={code}
      href={`/dashboard/locations/${locationCode}/${code}`}
      className={cn(
        "px-4 py-2 font-medium transition-colors",
        currentAirline === code
          ? "border-b-2 border-primary text-primary"
          : "text-muted-foreground hover:text-foreground"
      )}
    >
      {code}
    </Link>
  ))}
</div>
```

### 2. Dropdown con navegación
```tsx
<Select value={currentAirline} onValueChange={(code) => {
  router.push(`/dashboard/locations/${locationCode}/${code}`)
}}>
  <SelectTrigger className="w-32">
    <SelectValue placeholder="Airline" />
  </SelectTrigger>
  <SelectContent>
    {airlines.map(code => (
      <SelectItem key={code} value={code}>
        {code}
      </SelectItem>
    ))}
  </SelectContent>
</Select>
```

### 3. Pills con badge de count (Avanzado)
```tsx
{airlines.map(code => (
  <Badge
    key={code}
    variant={currentAirline === code ? "default" : "outline"}
    className="cursor-pointer"
    onClick={() => router.push(`/dashboard/locations/${locationCode}/${code}`)}
  >
    {code}
    {tripCounts[code] && (
      <span className="ml-1 text-xs opacity-70">
        ({tripCounts[code]})
      </span>
    )}
  </Badge>
))}
```

---

## ⚡ Performance

### Características del Endpoint

1. **Query SQL optimizada:**
   ```sql
   SELECT DISTINCT airline
   FROM trips.trips
   WHERE location_id = 'uuid'
   ORDER BY airline ASC
   ```

2. **Respuesta pequeña:**
   - Típicamente 5-20 airlines
   - ~200-500 bytes de payload
   - Muy rápido (<50ms en la mayoría de casos)

3. **Caché recomendado:**
   ```typescript
   // Cachear por 5 minutos (las airlines no cambian frecuentemente)
   const CACHE_TTL = 5 * 60 * 1000; // 5 minutos

   const cachedAirlines = useMemo(() => {
     // Tu lógica de caché
   }, [locationId]);
   ```

---

## 🔄 Flujo de Navegación Mejorado

### Antes
```
Usuario en /SDF/WN
  → Solo ve "WN" en dropdown
  → No sabe que hay otras airlines
  → Tiene que adivinar o buscar manualmente
```

### Después
```
Usuario en /SDF/WN
  → Ve tabs: "WN | AA | DEL | UA | DL"
  → Click en "AA"
  → Navega a /SDF/AA
  → Dashboard carga trips de AA
  → Tabs siguen mostrando todas las airlines disponibles
```

---

## 📊 Casos de Uso

### 1. Location con muchas airlines (ej: SDF)
```json
{
  "location_id": "6d636fef-0a01-4126-87e5-2759f4ec4074",
  "location_name": "SDF",
  "airlines": ["AA", "DEL", "DL", "F9", "NK", "UA", "WN"],
  "total": 7
}
```
→ Mostrar tabs o dropdown

### 2. Location con pocas airlines (ej: Location pequeña)
```json
{
  "location_id": "uuid-123",
  "location_name": "XYZ",
  "airlines": ["WN"],
  "total": 1
}
```
→ Ocultar navegación (solo 1 airline)

### 3. Location sin trips aún
```json
{
  "location_id": "uuid-456",
  "location_name": "ABC",
  "airlines": [],
  "total": 0
}
```
→ Mostrar mensaje: "No airlines available yet"

---

## 🧪 Testing

### Test Manual
```bash
# 1. Obtener token
TOKEN="eyJhbGc..."

# 2. Probar el endpoint
curl -X GET \
  "https://api.gt360.app/v1/locations/6d636fef-0a01-4126-87e5-2759f4ec4074/airlines" \
  -H "Authorization: Bearer $TOKEN"

# Respuesta esperada:
{
  "location_id": "6d636fef-0a01-4126-87e5-2759f4ec4074",
  "location_name": "SDF",
  "airlines": ["AA", "DEL", "DL", "UA", "WN"],
  "total": 5
}
```

### Test de Error Handling
```typescript
// Test: Location no existe
const response = await fetch(`${API_URL}/v1/locations/invalid-uuid/airlines`);
// Espera: 400 "ID de location inválido"

// Test: Location válida pero no existe
const response = await fetch(`${API_URL}/v1/locations/${validUuid}/airlines`);
// Espera: 404 "Location no encontrada"

// Test: Sin token
const response = await fetch(`${API_URL}/v1/locations/${validUuid}/airlines`);
// Espera: 401 "Not authenticated"
```

---

## ✅ Checklist de Implementación

### Backend
- [x] Endpoint creado: `GET /v1/locations/{id}/airlines`
- [x] Validación de UUID
- [x] Validación de location existente
- [x] Query SQL optimizada con DISTINCT
- [x] Respuesta ordenada alfabéticamente
- [x] Autorización (manager/driver)
- [x] Backend desplegado y funcionando

### Frontend (Tu trabajo)
- [ ] Crear servicio/función para llamar al endpoint
- [ ] Implementar UI de navegación (tabs/dropdown/pills)
- [ ] Agregar manejo de errores
- [ ] Agregar loading state
- [ ] Integrar con router para navegación
- [ ] Testear con locations reales
- [ ] Considerar caché si aplica

---

## 🚀 Deployment Status

**Backend:** ✅ Desplegado
**Endpoint:** ✅ Disponible en producción
**URL Base:** `https://api.gt360.app`

---

## 📞 Soporte

Si tienes dudas o problemas:
1. Verifica que el token JWT sea válido
2. Verifica que el `location_id` sea un UUID correcto
3. Revisa los logs del navegador (Network tab)
4. Compara con los ejemplos de este documento

---

**Última actualización:** 2026-01-14
**Versión Backend:** Latest (con airlines endpoint)
**Estado:** ✅ Listo para usar
