# Guía de Implementación Frontend: Sistema de Formato de Hora

## Resumen

El backend ahora soporta preferencias de usuario para formato de hora (Militar/24h vs AM/PM/12h). Esta guía documenta cómo implementar el frontend sin inconsistencias.

---

## 📋 Índice

1. [Cambios en el Backend](#cambios-en-el-backend)
2. [Nuevos Endpoints](#nuevos-endpoints)
3. [Formato de Respuestas](#formato-de-respuestas)
4. [Implementación Frontend](#implementación-frontend)
5. [Flujo de Usuario](#flujo-de-usuario)
6. [Casos de Uso](#casos-de-uso)
7. [Manejo de Errores](#manejo-de-errores)
8. [Testing](#testing)
9. [Migración de Datos Existentes](#migración-de-datos-existentes)

---

## 1. Cambios en el Backend

### Sistema Implementado

El backend ahora:
- ✅ Almacena preferencia de formato de hora por usuario en tabla `entities.user_settings`
- ✅ Serializa campos `pick_up_time` según la preferencia del usuario (24h o 12h)
- ✅ Retorna strings formateados directamente (NO objetos time)
- ✅ Respeta el sistema de timezone existente (sin cambios)
- ✅ Default: formato militar (24h) para retrocompatibilidad

### Endpoints Afectados

Todos los endpoints que retornan trips ahora usan formato de hora según preferencia:

- `POST /v1/trips/upload-trips` - Upload de Excel
- `GET /v1/locations/{location_id}/trips` - Listar trips
- `POST /v1/locations/{location_id}/trips` - Crear trip
- `PATCH /v1/locations/{location_id}/trips/{trip_id}` - Editar trip
- `PATCH /v1/organizations/{org_id}/locations/{loc_id}/trips/{trip_id}/assign` - Asignar driver
- `GET /v1/organizations/{org_id}/locations/{loc_id}/trips/search` - Buscar trip

---

## 2. Nuevos Endpoints

### GET /v1/profile/settings

Obtiene las preferencias del usuario actual.

**Request:**
```http
GET /v1/profile/settings
Authorization: Bearer {token}
```

**Response 200:**
```json
{
  "user_id": "uuid-here",
  "time_format": "24h",
  "created_at": "2026-01-17T20:00:00Z",
  "updated_at": "2026-01-17T20:00:00Z"
}
```

**Notas:**
- Si el usuario no tiene settings, se crean automáticamente con default `"24h"`
- Siempre retorna un objeto válido (nunca 404)

---

### PATCH /v1/profile/settings

Actualiza la preferencia de formato de hora.

**Request:**
```http
PATCH /v1/profile/settings
Authorization: Bearer {token}
Content-Type: application/json

{
  "time_format": "12h"
}
```

**Valores válidos:**
- `"24h"` - Formato militar (16:30, 23:45)
- `"12h"` - Formato AM/PM (04:30 PM, 11:45 PM)

**Response 200:**
```json
{
  "user_id": "uuid-here",
  "time_format": "12h",
  "created_at": "2026-01-17T20:00:00Z",
  "updated_at": "2026-01-17T20:15:00Z"
}
```

**Response 400 (Error de validación):**
```json
{
  "detail": "time_format debe ser '24h' o '12h'"
}
```

---

## 3. Formato de Respuestas

### Antes (Sin Preferencias)

Todos los usuarios recibían hora en formato ISO con segundos:

```json
{
  "id": "uuid",
  "pick_up_time": "16:30:00",
  "pick_up_date": "2026-01-17",
  "pick_up_location": "Holiday Inn",
  "drop_off_location": "SDF"
}
```

### Ahora (Con Preferencias)

#### Usuario con preferencia "24h" (default):

```json
{
  "id": "uuid",
  "pick_up_time": "16:30",
  "pick_up_date": "2026-01-17",
  "pick_up_location": "Holiday Inn",
  "drop_off_location": "SDF"
}
```

#### Usuario con preferencia "12h":

```json
{
  "id": "uuid",
  "pick_up_time": "04:30 PM",
  "pick_up_date": "2026-01-17",
  "pick_up_location": "Holiday Inn",
  "drop_off_location": "SDF"
}
```

### Cambios Clave

| Aspecto | Antes | Ahora (24h) | Ahora (12h) |
|---------|-------|-------------|-------------|
| Formato | `"HH:MM:SS"` | `"HH:MM"` | `"hh:MM AM/PM"` |
| Ejemplo 16:30 | `"16:30:00"` | `"16:30"` | `"04:30 PM"` |
| Ejemplo 00:00 | `"00:00:00"` | `"00:00"` | `"12:00 AM"` |
| Ejemplo 12:00 | `"12:00:00"` | `"12:00"` | `"12:00 PM"` |
| Ejemplo 23:59 | `"23:59:00"` | `"23:59"` | `"11:59 PM"` |

---

## 4. Implementación Frontend

### 4.1 Componente de Settings

Crear un componente para que el usuario cambie su preferencia:

```tsx
// components/UserSettings.tsx
import { useState, useEffect } from 'react';
import { api } from '@/lib/api';

interface UserSettings {
  user_id: string;
  time_format: '24h' | '12h';
  created_at: string;
  updated_at: string;
}

export function TimeFormatSettings() {
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [loading, setLoading] = useState(false);

  // Cargar settings al montar
  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const response = await api.get('/v1/profile/settings');
      setSettings(response.data);
    } catch (error) {
      console.error('Error loading settings:', error);
    }
  };

  const updateFormat = async (format: '24h' | '12h') => {
    setLoading(true);
    try {
      const response = await api.patch('/v1/profile/settings', {
        time_format: format
      });
      setSettings(response.data);

      // IMPORTANTE: Recargar datos de trips para ver cambio inmediato
      window.location.reload(); // O mejor: invalidar queries de React Query
    } catch (error) {
      console.error('Error updating settings:', error);
      alert('Error al actualizar preferencia');
    } finally {
      setLoading(false);
    }
  };

  if (!settings) return <div>Cargando...</div>;

  return (
    <div className="settings-panel">
      <h3>Formato de Hora</h3>

      <div className="format-options">
        <button
          className={settings.time_format === '24h' ? 'active' : ''}
          onClick={() => updateFormat('24h')}
          disabled={loading}
        >
          <span className="format-label">Formato Militar (24h)</span>
          <span className="format-example">16:30</span>
        </button>

        <button
          className={settings.time_format === '12h' ? 'active' : ''}
          onClick={() => updateFormat('12h')}
          disabled={loading}
        >
          <span className="format-label">Formato AM/PM (12h)</span>
          <span className="format-example">04:30 PM</span>
        </button>
      </div>

      <p className="help-text">
        Los horarios en toda la aplicación se mostrarán en el formato seleccionado.
      </p>
    </div>
  );
}
```

### 4.2 Mostrar Horas (NO REQUIERE CONVERSIÓN)

**IMPORTANTE:** El frontend NO necesita convertir las horas. Solo mostrar el string recibido.

```tsx
// components/TripCard.tsx
interface Trip {
  id: string;
  pick_up_time: string; // Ya viene formateado: "16:30" o "04:30 PM"
  pick_up_date: string;
  pick_up_location: string;
  drop_off_location: string;
}

export function TripCard({ trip }: { trip: Trip }) {
  return (
    <div className="trip-card">
      <div className="time">
        {/* NO hacer conversión, solo mostrar */}
        <span className="time-display">{trip.pick_up_time}</span>
      </div>
      <div className="date">{trip.pick_up_date}</div>
      <div className="route">
        {trip.pick_up_location} → {trip.drop_off_location}
      </div>
    </div>
  );
}
```

### 4.3 Inputs/Formularios (Crear/Editar Trip)

**IMPORTANTE:** Al crear o editar trips, SIEMPRE enviar en formato militar (24h).

El backend siempre espera formato `"HH:MM"` (militar) en inputs.

```tsx
// components/CreateTripForm.tsx
import { useState } from 'react';

export function CreateTripForm() {
  const [formData, setFormData] = useState({
    pick_up_time: '', // Usuario ingresa
    pick_up_date: '',
    pick_up_location: '',
    drop_off_location: '',
    airline: '',
    flight_number: '',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // IMPORTANTE: Enviar SIEMPRE en formato militar (HH:MM)
    const payload = {
      ...formData,
      pick_up_time: convertToMilitary(formData.pick_up_time), // Si necesario
    };

    await api.post('/v1/locations/{location_id}/trips', payload);
  };

  return (
    <form onSubmit={handleSubmit}>
      {/* Input de hora - usar formato militar */}
      <input
        type="time"
        value={formData.pick_up_time}
        onChange={(e) => setFormData({...formData, pick_up_time: e.target.value})}
        placeholder="HH:MM"
        required
      />
      {/* Otros campos... */}
    </form>
  );
}

// Helper para convertir si el usuario ingresa en formato AM/PM
function convertToMilitary(time: string): string {
  // Si ya está en formato HH:MM, retornar directo
  if (/^\d{2}:\d{2}$/.test(time)) {
    return time;
  }

  // Si está en formato AM/PM, convertir a militar
  // Ejemplo: "04:30 PM" -> "16:30"
  const match = time.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/i);
  if (!match) return time;

  let [_, hours, minutes, period] = match;
  let hour = parseInt(hours);

  if (period.toUpperCase() === 'PM' && hour !== 12) {
    hour += 12;
  } else if (period.toUpperCase() === 'AM' && hour === 12) {
    hour = 0;
  }

  return `${hour.toString().padStart(2, '0')}:${minutes}`;
}
```

---

## 5. Flujo de Usuario

### Flujo Completo

1. **Usuario inicia sesión**
   - Frontend NO necesita cargar settings inmediatamente
   - Al cargar trips, backend ya retorna con formato correcto

2. **Usuario navega a Settings**
   - Frontend hace GET `/v1/profile/settings`
   - Muestra opción actual (24h o 12h)

3. **Usuario cambia formato**
   - Frontend hace PATCH `/v1/profile/settings` con nuevo valor
   - Backend actualiza preferencia
   - Frontend recarga datos de trips (o invalida cache)

4. **Usuario ve trips actualizados**
   - Todas las requests subsiguientes retornan horas en nuevo formato
   - NO se requiere lógica de conversión en frontend

### Diagrama de Secuencia

```
┌──────────┐         ┌──────────┐         ┌──────────┐
│ Frontend │         │ Backend  │         │    DB    │
└────┬─────┘         └────┬─────┘         └────┬─────┘
     │                    │                     │
     │ GET /trips         │                     │
     ├───────────────────>│                     │
     │                    │ Get user settings   │
     │                    ├────────────────────>│
     │                    │<────────────────────┤
     │                    │ time_format: "24h"  │
     │                    │                     │
     │                    │ Get trips from DB   │
     │                    ├────────────────────>│
     │                    │<────────────────────┤
     │                    │                     │
     │                    │ Format times: "16:30"
     │<───────────────────┤                     │
     │ {"pick_up_time":   │                     │
     │  "16:30"}          │                     │
     │                    │                     │
     │ PATCH /settings    │                     │
     │ {"time_format":    │                     │
     │  "12h"}            │                     │
     ├───────────────────>│                     │
     │                    │ Update settings     │
     │                    ├────────────────────>│
     │<───────────────────┤                     │
     │                    │                     │
     │ GET /trips         │                     │
     ├───────────────────>│                     │
     │                    │ Get user settings   │
     │                    ├────────────────────>│
     │                    │<────────────────────┤
     │                    │ time_format: "12h"  │
     │                    │                     │
     │                    │ Format times: "04:30 PM"
     │<───────────────────┤                     │
     │ {"pick_up_time":   │                     │
     │  "04:30 PM"}       │                     │
```

---

## 6. Casos de Uso

### Caso 1: Usuario Nuevo

**Comportamiento:**
- Al crear cuenta, NO tiene settings
- En primer GET de trips, backend crea settings con default `"24h"`
- Usuario ve horas en formato militar: "16:30"

**Implementación Frontend:**
```tsx
// NO requiere acción especial
// Backend maneja la creación automática de settings
```

### Caso 2: Usuario Existente (Migración)

**Comportamiento:**
- Usuario existente sin settings (tabla nueva)
- En primer GET de settings o trips, backend crea settings con default `"24h"`
- NO hay interrupción de servicio

**Implementación Frontend:**
```tsx
// NO requiere migración en frontend
// Backend maneja retrocompatibilidad automáticamente
```

### Caso 3: Cambio de Formato Durante Sesión

**Comportamiento:**
- Usuario cambia de 24h a 12h
- Horas en memoria pueden estar en formato anterior
- Se requiere refresh de datos

**Implementación Frontend:**
```tsx
const updateFormat = async (format: '24h' | '12h') => {
  await api.patch('/v1/profile/settings', { time_format: format });

  // Opción 1: Reload completo (simple pero no elegante)
  window.location.reload();

  // Opción 2: Invalidar queries (React Query)
  queryClient.invalidateQueries(['trips']);

  // Opción 3: Refetch manual
  await refetchTrips();
};
```

### Caso 4: Upload de Excel

**Comportamiento:**
- Excel SIEMPRE tiene formato militar (16:00, 23:00)
- Backend parsea en formato militar (sin cambios)
- Backend retorna trips en formato según preferencia del usuario

**Implementación Frontend:**
```tsx
// Subir archivo Excel
const uploadExcel = async (file: File, location: string, airline: string) => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await api.post(
    `/v1/trips/upload-trips?airport=${location}&provider=ground&airline=${airline}`,
    formData
  );

  // Los trips en response.data.trips ya vienen con formato correcto
  // "16:30" o "04:30 PM" según preferencia del usuario
  console.log(response.data.trips);
};
```

### Caso 5: Crear Trip Manual

**Comportamiento:**
- Usuario ingresa hora (puede ser 24h o 12h en UI)
- Frontend DEBE enviar en formato militar al backend
- Backend almacena y retorna según preferencia

**Implementación Frontend:**
```tsx
const createTrip = async (tripData: any) => {
  // IMPORTANTE: Convertir a formato militar si es necesario
  const payload = {
    ...tripData,
    pick_up_time: convertToMilitary(tripData.pick_up_time),
  };

  const response = await api.post(`/v1/locations/${locationId}/trips`, payload);

  // La respuesta tiene pick_up_time formateado según preferencia
  return response.data;
};
```

---

## 7. Manejo de Errores

### Error: Formato Inválido

```json
{
  "detail": "time_format debe ser '24h' o '12h'"
}
```

**Causa:** Frontend envió valor inválido (ej: "military", "ampm")

**Solución:**
```tsx
const validFormats = ['24h', '12h'] as const;
type TimeFormat = typeof validFormats[number];

const updateFormat = async (format: TimeFormat) => {
  if (!validFormats.includes(format)) {
    console.error('Invalid format:', format);
    return;
  }
  // Continuar...
};
```

### Error: Token Expirado

```json
{
  "detail": "Token has expired"
}
```

**Causa:** Token de autenticación expirado

**Solución:** Refrescar token antes de hacer request

### Error: Usuario No Encontrado

```json
{
  "detail": "ID de usuario inválido"
}
```

**Causa:** Token inválido o corrompido

**Solución:** Logout y redirect a login

---

## 8. Testing

### Tests Frontend

#### Test 1: Mostrar Hora 24h

```tsx
test('displays time in 24h format', () => {
  const trip = {
    id: '1',
    pick_up_time: '16:30',
    pick_up_date: '2026-01-17',
    pick_up_location: 'Hotel',
    drop_off_location: 'Airport'
  };

  render(<TripCard trip={trip} />);

  expect(screen.getByText('16:30')).toBeInTheDocument();
});
```

#### Test 2: Mostrar Hora 12h

```tsx
test('displays time in 12h format', () => {
  const trip = {
    id: '1',
    pick_up_time: '04:30 PM',
    pick_up_date: '2026-01-17',
    pick_up_location: 'Hotel',
    drop_off_location: 'Airport'
  };

  render(<TripCard trip={trip} />);

  expect(screen.getByText('04:30 PM')).toBeInTheDocument();
});
```

#### Test 3: Cambiar Formato

```tsx
test('updates format preference', async () => {
  const mockPatch = jest.fn().mockResolvedValue({
    data: { time_format: '12h' }
  });
  api.patch = mockPatch;

  render(<TimeFormatSettings />);

  const button12h = screen.getByText('Formato AM/PM (12h)');
  fireEvent.click(button12h);

  await waitFor(() => {
    expect(mockPatch).toHaveBeenCalledWith('/v1/profile/settings', {
      time_format: '12h'
    });
  });
});
```

### Tests Backend (Ya implementados)

```bash
# Test manual con curl
curl -X GET http://localhost:8000/v1/profile/settings \
  -H "Authorization: Bearer {token}"

curl -X PATCH http://localhost:8000/v1/profile/settings \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{"time_format": "12h"}'

curl -X GET "http://localhost:8000/v1/locations/{location_id}/trips" \
  -H "Authorization: Bearer {token}"
```

---

## 9. Migración de Datos Existentes

### Base de Datos

La tabla `entities.user_settings` se crea con la migración 004:

```sql
CREATE TABLE IF NOT EXISTS entities.user_settings (
    user_id UUID PRIMARY KEY REFERENCES entities.users(id) ON DELETE CASCADE,
    time_format VARCHAR(10) NOT NULL DEFAULT '24h',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Características:**
- ✅ Usuarios existentes NO tienen entrada automáticamente
- ✅ Al primer GET de settings, backend crea entrada con default "24h"
- ✅ NO requiere migración de datos existentes
- ✅ Retrocompatible al 100%

### Frontend

**NO requiere migración de código existente.**

**Cambios mínimos:**
1. Agregar componente de settings (nuevo)
2. Remover lógica de conversión de hora si existe (limpieza)
3. Confiar en strings recibidos del backend

---

## 10. Ejemplos de Código Completo

### Ejemplo 1: Hook de React para Settings

```tsx
// hooks/useUserSettings.ts
import { useState, useEffect } from 'react';
import { api } from '@/lib/api';

interface UserSettings {
  user_id: string;
  time_format: '24h' | '12h';
  created_at: string;
  updated_at: string;
}

export function useUserSettings() {
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      setLoading(true);
      const response = await api.get<UserSettings>('/v1/profile/settings');
      setSettings(response.data);
      setError(null);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const updateTimeFormat = async (format: '24h' | '12h') => {
    try {
      setLoading(true);
      const response = await api.patch<UserSettings>('/v1/profile/settings', {
        time_format: format
      });
      setSettings(response.data);
      setError(null);
      return true;
    } catch (err: any) {
      setError(err.message);
      return false;
    } finally {
      setLoading(false);
    }
  };

  return {
    settings,
    loading,
    error,
    updateTimeFormat,
    refetch: loadSettings
  };
}
```

### Ejemplo 2: Context Provider para Settings

```tsx
// contexts/SettingsContext.tsx
import { createContext, useContext, ReactNode } from 'react';
import { useUserSettings } from '@/hooks/useUserSettings';

interface SettingsContextType {
  timeFormat: '24h' | '12h';
  updateTimeFormat: (format: '24h' | '12h') => Promise<boolean>;
  loading: boolean;
}

const SettingsContext = createContext<SettingsContextType | null>(null);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const { settings, loading, updateTimeFormat } = useUserSettings();

  const value = {
    timeFormat: settings?.time_format || '24h',
    updateTimeFormat,
    loading
  };

  return (
    <SettingsContext.Provider value={value}>
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings() {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error('useSettings must be used within SettingsProvider');
  }
  return context;
}
```

### Ejemplo 3: Component Settings UI

```tsx
// components/UserSettings.tsx
import { useSettings } from '@/contexts/SettingsContext';
import { useQueryClient } from '@tanstack/react-query';

export function UserSettingsPanel() {
  const { timeFormat, updateTimeFormat, loading } = useSettings();
  const queryClient = useQueryClient();

  const handleFormatChange = async (format: '24h' | '12h') => {
    const success = await updateTimeFormat(format);

    if (success) {
      // Invalidar todas las queries de trips para refrescar datos
      queryClient.invalidateQueries({ queryKey: ['trips'] });

      // Mostrar mensaje de éxito
      toast.success('Formato de hora actualizado');
    } else {
      toast.error('Error al actualizar formato');
    }
  };

  return (
    <div className="settings-panel">
      <h2>Preferencias</h2>

      <div className="setting-group">
        <label>Formato de Hora</label>

        <div className="button-group">
          <button
            className={timeFormat === '24h' ? 'active' : ''}
            onClick={() => handleFormatChange('24h')}
            disabled={loading}
          >
            <div className="option-label">
              <strong>24 Horas (Militar)</strong>
              <span className="example">16:30, 23:45</span>
            </div>
          </button>

          <button
            className={timeFormat === '12h' ? 'active' : ''}
            onClick={() => handleFormatChange('12h')}
            disabled={loading}
          >
            <div className="option-label">
              <strong>12 Horas (AM/PM)</strong>
              <span className="example">04:30 PM, 11:45 PM</span>
            </div>
          </button>
        </div>

        <p className="help-text">
          Los horarios en toda la aplicación se mostrarán en el formato seleccionado.
        </p>
      </div>
    </div>
  );
}
```

---

## 11. Checklist de Implementación

### Backend (✅ Completado)

- [x] Crear migración de base de datos
- [x] Crear schema UserSettings
- [x] Crear modelos Pydantic
- [x] Crear endpoints GET/PATCH /v1/profile/settings
- [x] Integrar formateo en todos los endpoints de trips
- [x] Testing manual con curl

### Frontend (Por Implementar)

- [ ] Crear hook `useUserSettings`
- [ ] Crear context provider `SettingsProvider`
- [ ] Crear componente UI `UserSettingsPanel`
- [ ] Agregar a página de Settings/Profile
- [ ] Remover lógica de conversión de hora si existe
- [ ] Actualizar tests unitarios
- [ ] Testing E2E con formato 24h
- [ ] Testing E2E con formato 12h
- [ ] Testing de cambio de formato durante sesión

---

## 12. FAQ

### ¿El frontend necesita convertir horas?

**NO.** El backend envía strings formateados directamente. Solo mostrar el valor recibido.

### ¿Qué pasa con horas en cache del frontend?

Al cambiar formato, invalidar cache o recargar datos. El backend retorna en nuevo formato inmediatamente.

### ¿El sistema de timezone cambia?

**NO.** El timezone NO cambia. La conversión 24h/12h es solo visual/presentacional.

### ¿Los archivos Excel cambian?

**NO.** Los Excel siempre usan formato militar. Solo la respuesta JSON cambia.

### ¿Qué pasa con WebSockets?

Los WebSockets actualmente retornan formato ISO sin preferencias. Esto puede actualizarse en futuras versiones.

### ¿Puedo tener diferentes formatos en diferentes dispositivos?

SÍ. La preferencia está atada al usuario, no al dispositivo. El formato se aplica en todas las sesiones del mismo usuario.

### ¿Qué pasa si borro mis settings?

El backend crea settings automáticamente con default "24h" en la próxima request.

---

## 13. Contacto y Soporte

Para preguntas o problemas con la implementación:

1. Revisar logs del backend para errores de serialización
2. Verificar que requests incluyan Authorization header
3. Verificar que valores enviados sean "24h" o "12h" exactamente
4. Probar con curl antes de implementar en frontend

---

**Última Actualización:** 2026-01-17
**Versión del Backend:** 1.0.0 (Migration 004)
**Versión de la Documentación:** 1.0.0
