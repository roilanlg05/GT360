# Drivers Endpoint - Frontend Integration Guide

## Overview

Este endpoint permite obtener la lista de drivers de una organizacion con filtros opcionales.

---

## Endpoint

```
GET /v1/organizations/{organization_id}/drivers
```

### Autenticacion
- Requiere token JWT valido
- Solo usuarios con rol `manager` pueden acceder

---

## Parametros

### Path Parameters

| Parametro | Tipo | Requerido | Descripcion |
|-----------|------|-----------|-------------|
| `organization_id` | UUID | **Si** | ID de la organizacion |

### Query Parameters

| Parametro | Tipo | Requerido | Valores | Descripcion |
|-----------|------|-----------|---------|-------------|
| `location_id` | UUID | No | - | Filtrar drivers por location |
| `pay_type` | string | No | `day`, `hour`, `trip` | Filtrar por tipo de pago |
| `driver_id` | UUID | No | - | Obtener info completa de un driver especifico |
| `name` | string | No | - | Buscar por nombre (case-insensitive, partial match) |
| `is_active` | boolean | No | `true`, `false` | Filtrar por estado activo/inactivo |

---

## Response

### Success Response (200)

```json
{
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "first_name": "John",
      "last_name": "Doe",
      "email": "john.doe@example.com",
      "phone": "+15028306579",
      "profile_pic": "https://example.com/pic.jpg",
      "is_active": true,
      "pay_type": "day",
      "location_id": "660e8400-e29b-41d4-a716-446655440001",
      "organization_id": "770e8400-e29b-41d4-a716-446655440002",
      "created_at": "2026-01-23T10:30:00"
    }
  ],
  "total": 1
}
```

### Response Fields

| Campo | Tipo | Nullable | Descripcion |
|-------|------|----------|-------------|
| `data` | array | No | Array de drivers |
| `total` | integer | No | Total de drivers retornados |

### Driver Object Fields

| Campo | Tipo | Nullable | Descripcion |
|-------|------|----------|-------------|
| `id` | string (UUID) | No | ID unico del driver |
| `first_name` | string | Si | Nombre del driver |
| `last_name` | string | Si | Apellido del driver |
| `email` | string | No | Email del driver |
| `phone` | string | Si | Telefono del driver |
| `profile_pic` | string | Si | URL de la foto de perfil |
| `is_active` | boolean | No | Estado activo/inactivo |
| `pay_type` | string | Si | Tipo de pago: `day`, `hour`, `trip` |
| `location_id` | string (UUID) | Si | ID de la location asignada |
| `organization_id` | string (UUID) | Si | ID de la organizacion |
| `created_at` | string (ISO 8601) | Si | Fecha de creacion |

---

## Error Responses

### 400 Bad Request
```json
{
  "detail": "Invalid pay_type. Must be one of: day, hour, trip"
}
```

### 401 Unauthorized
```json
{
  "detail": "Missing or invalid authentication"
}
```

### 403 Forbidden
```json
{
  "detail": "You don't have permission to access this organization's drivers"
}
```

### 404 Not Found
```json
{
  "detail": "Organization not found"
}
```

---

## Frontend Implementation

### TypeScript Interfaces

```typescript
interface Driver {
  id: string;
  first_name: string | null;
  last_name: string | null;
  email: string;
  phone: string | null;
  profile_pic: string | null;
  is_active: boolean;
  pay_type: 'day' | 'hour' | 'trip' | null;
  location_id: string | null;
  organization_id: string | null;
  created_at: string | null;
}

interface DriversResponse {
  data: Driver[];
  total: number;
}

interface DriversFilters {
  location_id?: string;
  pay_type?: 'day' | 'hour' | 'trip';
  driver_id?: string;
  name?: string;
  is_active?: boolean;
}
```

### API Service

```typescript
const API_BASE = 'https://api.gt360.app';

async function getDrivers(
  organizationId: string,
  filters: DriversFilters = {},
  token: string
): Promise<DriversResponse> {
  const params = new URLSearchParams();

  if (filters.location_id) params.append('location_id', filters.location_id);
  if (filters.pay_type) params.append('pay_type', filters.pay_type);
  if (filters.driver_id) params.append('driver_id', filters.driver_id);
  if (filters.name) params.append('name', filters.name);
  if (filters.is_active !== undefined) params.append('is_active', String(filters.is_active));

  const queryString = params.toString();
  const url = `${API_BASE}/v1/organizations/${organizationId}/drivers${queryString ? `?${queryString}` : ''}`;

  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to fetch drivers');
  }

  return response.json();
}
```

### React Hook Example

```typescript
import { useState, useEffect, useCallback } from 'react';
import { useDebounce } from '@/hooks/useDebounce';

interface UseDriversOptions {
  organizationId: string;
  token: string;
  initialFilters?: DriversFilters;
}

function useDrivers({ organizationId, token, initialFilters = {} }: UseDriversOptions) {
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<DriversFilters>(initialFilters);

  // Debounce name search to avoid excessive API calls
  const debouncedName = useDebounce(filters.name, 300);

  const fetchDrivers = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const filtersWithDebouncedName = {
        ...filters,
        name: debouncedName,
      };

      const response = await getDrivers(organizationId, filtersWithDebouncedName, token);
      setDrivers(response.data);
      setTotal(response.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [organizationId, token, filters, debouncedName]);

  useEffect(() => {
    fetchDrivers();
  }, [fetchDrivers]);

  const updateFilter = (key: keyof DriversFilters, value: any) => {
    setFilters(prev => ({ ...prev, [key]: value }));
  };

  const clearFilters = () => {
    setFilters({});
  };

  return {
    drivers,
    total,
    loading,
    error,
    filters,
    updateFilter,
    clearFilters,
    refetch: fetchDrivers,
  };
}
```

### Component Example

```tsx
function DriversPage() {
  const { organizationId } = useAuth();
  const token = getAccessToken();

  const {
    drivers,
    total,
    loading,
    error,
    filters,
    updateFilter,
    clearFilters,
  } = useDrivers({ organizationId, token });

  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold mb-4">Drivers ({total})</h1>

      {/* Filters */}
      <div className="flex gap-4 mb-4">
        {/* Name Search with Debounce */}
        <input
          type="text"
          placeholder="Search by name..."
          value={filters.name || ''}
          onChange={(e) => updateFilter('name', e.target.value)}
          className="border rounded px-3 py-2"
        />

        {/* Pay Type Filter */}
        <select
          value={filters.pay_type || ''}
          onChange={(e) => updateFilter('pay_type', e.target.value || undefined)}
          className="border rounded px-3 py-2"
        >
          <option value="">All Pay Types</option>
          <option value="day">Day</option>
          <option value="hour">Hour</option>
          <option value="trip">Trip</option>
        </select>

        {/* Active/Inactive Filter */}
        <select
          value={filters.is_active === undefined ? '' : String(filters.is_active)}
          onChange={(e) => {
            const value = e.target.value;
            updateFilter('is_active', value === '' ? undefined : value === 'true');
          }}
          className="border rounded px-3 py-2"
        >
          <option value="">All Status</option>
          <option value="true">Active</option>
          <option value="false">Inactive</option>
        </select>

        <button onClick={clearFilters} className="px-4 py-2 bg-gray-200 rounded">
          Clear Filters
        </button>
      </div>

      {/* Loading State */}
      {loading && <div>Loading...</div>}

      {/* Error State */}
      {error && <div className="text-red-500">{error}</div>}

      {/* Drivers Table */}
      {!loading && !error && (
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-gray-100">
              <th className="border p-2 text-left">Name</th>
              <th className="border p-2 text-left">Email</th>
              <th className="border p-2 text-left">Phone</th>
              <th className="border p-2 text-left">Pay Type</th>
              <th className="border p-2 text-left">Status</th>
            </tr>
          </thead>
          <tbody>
            {drivers.map((driver) => (
              <tr key={driver.id}>
                <td className="border p-2">
                  {driver.first_name} {driver.last_name}
                </td>
                <td className="border p-2">{driver.email}</td>
                <td className="border p-2">{driver.phone || '-'}</td>
                <td className="border p-2">
                  {driver.pay_type ? driver.pay_type.toUpperCase() : '-'}
                </td>
                <td className="border p-2">
                  <span className={driver.is_active ? 'text-green-600' : 'text-red-600'}>
                    {driver.is_active ? 'Active' : 'Inactive'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Empty State */}
      {!loading && !error && drivers.length === 0 && (
        <div className="text-gray-500 text-center py-8">
          No drivers found
        </div>
      )}
    </div>
  );
}
```

---

## Usage Examples

### Get all active drivers
```bash
curl -X GET "https://api.gt360.app/v1/organizations/{org_id}/drivers?is_active=true" \
  -H "Authorization: Bearer {token}"
```

### Filter by pay type
```bash
curl -X GET "https://api.gt360.app/v1/organizations/{org_id}/drivers?pay_type=day" \
  -H "Authorization: Bearer {token}"
```

### Search by name
```bash
curl -X GET "https://api.gt360.app/v1/organizations/{org_id}/drivers?name=john" \
  -H "Authorization: Bearer {token}"
```

### Get specific driver
```bash
curl -X GET "https://api.gt360.app/v1/organizations/{org_id}/drivers?driver_id={driver_uuid}" \
  -H "Authorization: Bearer {token}"
```

### Combine multiple filters
```bash
curl -X GET "https://api.gt360.app/v1/organizations/{org_id}/drivers?is_active=true&pay_type=hour&location_id={loc_id}" \
  -H "Authorization: Bearer {token}"
```

---

## Database Schema

### Table: `entities.drivers`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | UUID | No | PK, FK to `entities.users.id` |
| `is_active` | boolean | No | Default: false |
| `point` | JSONB | Yes | GPS location |
| `location_id` | UUID | Yes | FK to `entities.locations.id` |
| `organization_id` | UUID | Yes | FK to `entities.organizations.id` |
| `pay_type` | VARCHAR(10) | Yes | Values: day, hour, trip |
| `profile_pic_url` | VARCHAR | Yes | Profile picture URL |

### Migration SQL

```sql
-- Add pay_type column if not exists
ALTER TABLE entities.drivers
ADD COLUMN IF NOT EXISTS pay_type VARCHAR(10) DEFAULT NULL;

-- Create index for better query performance
CREATE INDEX IF NOT EXISTS idx_drivers_pay_type ON entities.drivers(pay_type);
```

---

## Notes

1. **Name Search**: El parametro `name` usa ILIKE para busqueda case-insensitive y partial match
2. **Debouncing**: Se recomienda implementar debouncing (300ms) en el frontend para el campo de busqueda por nombre
3. **Performance**: Los resultados estan ordenados por `created_at` descendente (mas recientes primero)
4. **Authorization**: El endpoint verifica que el usuario pertenezca a la organizacion solicitada
