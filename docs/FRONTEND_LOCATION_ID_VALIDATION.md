# ✅ Solución: Validación de Location ID en Frontend

**Fecha:** 2026-02-16
**Problema:** Frontend usa `location_id` del localStorage sin validar si existe en el backend
**Impacto:** Errores 404, mapas vacíos, datos no cargan

---

## 🚨 **EL PROBLEMA**

### Código Incorrecto (Frontend):
```typescript
// ❌ MAL - Usa ID del localStorage sin validar
function useDashboard() {
  const [locationId, setLocationId] = useState(() => {
    // Carga ID del localStorage directamente
    const cached = localStorage.getItem('api360-dashboard-filters-v2');
    if (cached) {
      const filters = JSON.parse(cached);
      return filters.locationId;  // ❌ Puede ser un ID que ya no existe
    }
    return null;
  });

  // Usa locationId sin verificar
  useEffect(() => {
    if (locationId) {
      fetchTrips(locationId);  // ❌ Puede fallar si el ID no existe
    }
  }, [locationId]);
}
```

### ¿Qué pasa cuando falla?
1. Usuario hace login → Frontend carga `location_id` del localStorage
2. Esa location fue eliminada del backend
3. Frontend intenta cargar datos: `GET /v1/locations/476d9905.../trips` → **404 Not Found**
4. Mapa vacío, sin datos, usuario confundido

---

## ✅ **LA SOLUCIÓN CORRECTA**

### Arquitectura Correcta:
```
1. Usuario hace login
   ↓
2. Frontend obtiene user_data del token (incluye location_id del manager)
   ↓
3. Frontend carga TODAS las locations disponibles: GET /v1/locations
   ↓
4. Frontend valida:
   - ¿Hay location_id en localStorage?
   - ¿Ese ID existe en la lista del backend?
   - SI existe → usar ese ID
   - NO existe → usar location_id del user o la primera disponible
   ↓
5. Actualizar localStorage con ID válido
   ↓
6. Cargar datos usando el ID validado
```

---

## 💻 **CÓDIGO CORRECTO (TypeScript/React)**

### 1. Hook de Validación de Location

```typescript
// hooks/useValidatedLocationId.ts

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { locationsApi } from '@/services/locations.api';

interface Location {
  id: string;
  name: string;
  organization_id: string;
  // ... otros campos
}

const STORAGE_KEY = 'api360-dashboard-filters-v2';

export function useValidatedLocationId() {
  const { user } = useAuth();
  const [locationId, setLocationId] = useState<string | null>(null);
  const [availableLocations, setAvailableLocations] = useState<Location[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    validateAndSetLocationId();
  }, [user]);

  async function validateAndSetLocationId() {
    try {
      setLoading(true);
      setError(null);

      // 1. Obtener TODAS las locations disponibles desde el backend
      const locations = await locationsApi.getAll();
      setAvailableLocations(locations);

      if (locations.length === 0) {
        setError('No hay locations disponibles');
        setLoading(false);
        return;
      }

      // 2. Intentar usar location_id del localStorage
      let selectedId: string | null = null;

      try {
        const cached = localStorage.getItem(STORAGE_KEY);
        if (cached) {
          const filters = JSON.parse(cached);
          const cachedLocationId = filters.locationId;

          // 3. VALIDAR que el ID cacheado existe en el backend
          const exists = locations.some(loc => loc.id === cachedLocationId);

          if (exists) {
            console.log('✅ Location ID del localStorage es válido:', cachedLocationId);
            selectedId = cachedLocationId;
          } else {
            console.warn('⚠️ Location ID del localStorage no existe en el backend:', cachedLocationId);
            console.warn('   IDs disponibles:', locations.map(l => l.id));
          }
        }
      } catch (e) {
        console.error('Error leyendo localStorage:', e);
      }

      // 4. Fallback si no hay ID válido en localStorage
      if (!selectedId) {
        // Opción A: Usar location_id del usuario (del token JWT)
        if (user?.location_id) {
          const userLocationExists = locations.some(loc => loc.id === user.location_id);
          if (userLocationExists) {
            console.log('✅ Usando location_id del usuario:', user.location_id);
            selectedId = user.location_id;
          }
        }

        // Opción B: Usar la primera location disponible
        if (!selectedId) {
          console.log('✅ Usando primera location disponible:', locations[0].id);
          selectedId = locations[0].id;
        }
      }

      // 5. Guardar ID validado en localStorage
      const filters = localStorage.getItem(STORAGE_KEY);
      const updatedFilters = filters ? JSON.parse(filters) : {};
      updatedFilters.locationId = selectedId;
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updatedFilters));

      // 6. Setear el ID validado
      setLocationId(selectedId);
      setLoading(false);

    } catch (err) {
      console.error('Error validando location ID:', err);
      setError(err instanceof Error ? err.message : 'Error desconocido');
      setLoading(false);
    }
  }

  // Función para cambiar de location
  function changeLocation(newLocationId: string) {
    // Validar que el nuevo ID existe
    const exists = availableLocations.some(loc => loc.id === newLocationId);

    if (!exists) {
      console.error('❌ Location ID no válido:', newLocationId);
      return;
    }

    // Actualizar localStorage
    const filters = localStorage.getItem(STORAGE_KEY);
    const updatedFilters = filters ? JSON.parse(filters) : {};
    updatedFilters.locationId = newLocationId;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updatedFilters));

    // Actualizar estado
    setLocationId(newLocationId);
  }

  return {
    locationId,
    availableLocations,
    loading,
    error,
    changeLocation,
    refetch: validateAndSetLocationId
  };
}
```

---

### 2. Uso en Componentes

```typescript
// pages/Dashboard.tsx

import { useValidatedLocationId } from '@/hooks/useValidatedLocationId';
import { useTrips } from '@/hooks/useTrips';
import { MapView } from '@/components/MapView';

export function Dashboard() {
  const {
    locationId,
    availableLocations,
    loading: loadingLocation,
    error: locationError,
    changeLocation
  } = useValidatedLocationId();

  const {
    trips,
    loading: loadingTrips
  } = useTrips(locationId);  // ✅ Solo carga si locationId es válido

  if (loadingLocation) {
    return <div>Cargando locations...</div>;
  }

  if (locationError) {
    return <div>Error: {locationError}</div>;
  }

  if (!locationId) {
    return <div>No hay location seleccionada</div>;
  }

  return (
    <div>
      {/* Selector de Location */}
      <select
        value={locationId}
        onChange={(e) => changeLocation(e.target.value)}
      >
        {availableLocations.map(location => (
          <option key={location.id} value={location.id}>
            {location.name}
          </option>
        ))}
      </select>

      {/* Mapa */}
      <MapView locationId={locationId} />

      {/* Trips */}
      {loadingTrips ? (
        <div>Cargando trips...</div>
      ) : (
        <TripsList trips={trips} />
      )}
    </div>
  );
}
```

---

### 3. API Service

```typescript
// services/locations.api.ts

import { API_BASE_URL } from '@/config';

interface Location {
  id: string;
  name: string;
  organization_id: string;
  point: {
    type: string;
    coordinates: [number, number];
  } | null;
  radio_zone: number | null;
  validation_status: string;
  timezone: string;
}

class LocationsApi {
  private getHeaders() {
    const token = localStorage.getItem('access_token');
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    };
  }

  /**
   * Obtiene TODAS las locations de la organización del usuario.
   * SIEMPRE llamar este endpoint primero antes de usar location_id.
   */
  async getAll(): Promise<Location[]> {
    const response = await fetch(`${API_BASE_URL}/v1/locations`, {
      headers: this.getHeaders(),
    });

    if (!response.ok) {
      throw new Error(`Error ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    return data.data;  // Array de locations
  }

  /**
   * Obtiene UNA location específica.
   * Solo llamar si ya validaste que el ID existe.
   */
  async getById(locationId: string): Promise<Location> {
    const response = await fetch(
      `${API_BASE_URL}/v1/locations?location_id=${locationId}`,
      {
        headers: this.getHeaders(),
      }
    );

    if (!response.ok) {
      throw new Error(`Error ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    return data.data;
  }
}

export const locationsApi = new LocationsApi();
```

---

## 🔒 **VALIDACIÓN ADICIONAL EN CADA REQUEST**

Además del hook, valida en cada request crítico:

```typescript
// hooks/useTrips.ts

export function useTrips(locationId: string | null) {
  const [trips, setTrips] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // ✅ No hacer nada si locationId es null o inválido
    if (!locationId) {
      console.warn('⚠️ locationId es null, no se cargarán trips');
      return;
    }

    fetchTrips();
  }, [locationId]);

  async function fetchTrips() {
    try {
      setLoading(true);
      setError(null);

      const response = await fetch(
        `/api/v1/locations/${locationId}/trips`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        }
      );

      // ✅ Manejar 404 específicamente
      if (response.status === 404) {
        setError(`Location ${locationId} no encontrada. Por favor selecciona otra location.`);
        setLoading(false);
        return;
      }

      if (!response.ok) {
        throw new Error(`Error ${response.status}`);
      }

      const data = await response.json();
      setTrips(data.data);
      setLoading(false);

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido');
      setLoading(false);
    }
  }

  return { trips, loading, error };
}
```

---

## 📋 **CHECKLIST DE IMPLEMENTACIÓN**

### Backend (Ya está correcto):
- ✅ Endpoint `GET /v1/locations` retorna todas las locations del usuario
- ✅ Endpoint valida que location pertenece a la organización del usuario
- ✅ Retorna 404 si location no existe

### Frontend (Debe implementar):
- [ ] Crear hook `useValidatedLocationId`
- [ ] **SIEMPRE** cargar locations desde backend primero
- [ ] Validar ID del localStorage contra lista del backend
- [ ] Usar fallback si ID no existe
- [ ] Actualizar localStorage con ID válido
- [ ] Manejar errores 404 gracefully
- [ ] Mostrar mensaje al usuario si location no existe
- [ ] No permitir que el usuario "use" un ID que no existe

---

## 🚫 **LO QUE NO DEBE HACER EL FRONTEND**

```typescript
// ❌ NUNCA hacer esto:
const locationId = localStorage.getItem('location_id');
fetchData(locationId);  // ❌ Sin validar

// ❌ NUNCA asumir que el localStorage es verdad:
const cachedId = getFromCache();
if (cachedId) {
  useLocation(cachedId);  // ❌ Sin verificar que existe
}

// ❌ NUNCA depender solo del localStorage:
function getLocationId() {
  return localStorage.getItem('location_id') || 'default-id';  // ❌ default-id puede no existir
}
```

---

## ✅ **LO QUE SÍ DEBE HACER EL FRONTEND**

```typescript
// ✅ SIEMPRE validar primero:
async function getValidLocationId() {
  // 1. Cargar locations disponibles
  const locations = await api.getLocations();

  // 2. Validar ID del cache
  const cachedId = localStorage.getItem('location_id');
  const isValid = locations.some(l => l.id === cachedId);

  // 3. Retornar ID válido o fallback
  return isValid ? cachedId : locations[0]?.id || null;
}

// ✅ SIEMPRE manejar el caso de ID inválido:
if (!locationId) {
  return <NoLocationMessage />;
}

// ✅ SIEMPRE sincronizar localStorage con backend:
useEffect(() => {
  validateAndSyncLocationId();
}, []);
```

---

## 🎯 **FLUJO CORRECTO COMPLETO**

```
Usuario abre la app
    ↓
1. Frontend: Leer token JWT → Obtener user_data.location_id
    ↓
2. Frontend: GET /v1/locations → Obtener TODAS las locations disponibles
    ↓
3. Frontend: ¿Hay location_id en localStorage?
    ├─ SÍ → ¿Existe en la lista del backend?
    │   ├─ SÍ → ✅ Usar ese ID
    │   └─ NO → Usar fallback (user.location_id o primera location)
    └─ NO → Usar fallback (user.location_id o primera location)
    ↓
4. Frontend: Guardar ID validado en localStorage
    ↓
5. Frontend: setLocationId(validatedId)
    ↓
6. Frontend: Cargar datos usando el ID validado
    ↓
7. Backend: Validar que el ID pertenece a la org del usuario
    ↓
8. Backend: Retornar datos
```

---

## 🔧 **TESTING**

### Casos de prueba:

```typescript
describe('useValidatedLocationId', () => {
  it('debe usar location_id del localStorage si es válido', async () => {
    localStorage.setItem('location_id', 'valid-id');
    mockApi.getLocations.mockResolvedValue([{ id: 'valid-id', name: 'SDF' }]);

    const { result } = renderHook(() => useValidatedLocationId());
    await waitFor(() => expect(result.current.locationId).toBe('valid-id'));
  });

  it('debe usar fallback si location_id del localStorage no existe', async () => {
    localStorage.setItem('location_id', 'invalid-id');
    mockApi.getLocations.mockResolvedValue([{ id: 'correct-id', name: 'SDF' }]);

    const { result } = renderHook(() => useValidatedLocationId());
    await waitFor(() => expect(result.current.locationId).toBe('correct-id'));
  });

  it('debe actualizar localStorage con ID válido', async () => {
    localStorage.setItem('location_id', 'old-invalid-id');
    mockApi.getLocations.mockResolvedValue([{ id: 'new-valid-id', name: 'SDF' }]);

    renderHook(() => useValidatedLocationId());
    await waitFor(() => {
      expect(localStorage.getItem('location_id')).toBe('new-valid-id');
    });
  });
});
```

---

## 📞 **RESUMEN PARA EL EQUIPO DE FRONTEND**

**Problema:** localStorage puede tener IDs obsoletos que ya no existen en el backend.

**Solución:**
1. ✅ SIEMPRE cargar locations desde el backend PRIMERO
2. ✅ Validar que el ID del localStorage existe en la lista
3. ✅ Usar fallback si no existe
4. ✅ Actualizar localStorage con ID válido
5. ✅ Manejar errores 404 gracefully

**NO depender de localStorage como fuente de verdad. El backend es la fuente de verdad.**

---

**Última actualización:** 2026-02-16
