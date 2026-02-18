# Trip Alarm System - Frontend/Mobile Integration Guide

## Overview

Los drivers pueden configurar alarmas personales asociadas a trips desde la trip card. Al tocar el icono de reloj en la card, se abre un picker para configurar la hora de la alarma (pre-cargada con la hora del trip). Las alarmas son **per-user**: solo el usuario que la configura la ve.

Al abrir la app, el frontend carga todas las alarmas activas del usuario y programa notificaciones locales. Por ahora se emiten desde la web (setTimeout); en el futuro se usara un bridge nativo.

---

## Autenticacion

Todos los endpoints de alarmas requieren token JWT valido con rol `driver` o `manager`.

```
Authorization: Bearer {access_token}
```

Para detalles completos de auth, ver [REACT_NATIVE_DRIVER_AUTH_GUIDE.md](./REACT_NATIVE_DRIVER_AUTH_GUIDE.md).

**Resumen rapido:**
1. Login: `POST /v1/auth/sign-in` → obtener `access_token`
2. Guardar token en AsyncStorage
3. Enviar en cada request: `Authorization: Bearer {token}`
4. En 401: refrescar con `POST /v1/auth/refresh` (cookies automaticas)

---

## Endpoints

### 1. POST `/v1/trips/{trip_id}/alarm` - Crear Alarma

Crea una alarma para el usuario autenticado en un trip especifico. El `user_id` se extrae del token (no se envia en el body).

**Auth:** `driver` o `manager`

#### Request

```
POST /v1/trips/{trip_id}/alarm
Authorization: Bearer {access_token}
Content-Type: application/json
```

```json
{
  "alarm_at": "2025-01-15T06:00:00-05:00"
}
```

| Campo | Tipo | Requerido | Descripcion |
|-------|------|-----------|-------------|
| `alarm_at` | string (ISO 8601) | **Si** | Fecha/hora en que debe sonar la alarma (con timezone) |

#### Response Success (201)

```json
{
  "status": "ok",
  "message": "Alarm created",
  "alarm": {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "trip_id": "550e8400-e29b-41d4-a716-446655440000",
    "user_id": "660e8400-e29b-41d4-a716-446655440000",
    "alarm_at": "2025-01-15T11:00:00+00:00",
    "is_active": true,
    "created_at": "2025-01-14T20:00:00+00:00",
    "updated_at": "2025-01-14T20:00:00+00:00"
  }
}
```

#### Errores

| Codigo | Mensaje | Causa |
|--------|---------|-------|
| 400 | `"Invalid trip ID"` | UUID invalido |
| 404 | `"Trip not found"` | Trip no existe |
| 409 | `"Alarm already exists for this trip"` | Ya tiene alarma en este trip |

---

### 2. GET `/v1/trips/alarms` - Listar Alarmas Activas

Lista todas las alarmas activas del usuario autenticado. **Llamar al abrir la app** y despues de crear/actualizar/eliminar una alarma.

Si se envia `local_time`, el backend elimina automaticamente las alarmas cuyo trip ya paso (comparando `pick_up_date + pick_up_time` del trip contra la hora local del cliente).

**Auth:** `driver` o `manager`

#### Request

```
GET /v1/trips/alarms?local_time=2026-02-09T09:00:00
Authorization: Bearer {access_token}
```

#### Query Parameters

| Parametro | Tipo | Requerido | Descripcion |
|-----------|------|-----------|-------------|
| `local_time` | string (ISO 8601) | No | Hora local actual del cliente. Si se envia, se eliminan alarmas de trips cuyo pickup ya paso |

#### Response Success (200)

```json
{
  "alarms": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "trip_id": "550e8400-e29b-41d4-a716-446655440000",
      "user_id": "660e8400-e29b-41d4-a716-446655440000",
      "alarm_at": "2025-01-15T11:00:00+00:00",
      "is_active": true,
      "created_at": "2025-01-14T20:00:00+00:00",
      "updated_at": "2025-01-14T20:00:00+00:00"
    }
  ],
  "total": 1
}
```

---

### 3. PATCH `/v1/trips/{trip_id}/alarm` - Actualizar Alarma

Actualiza la hora y/o el estado activo de la alarma. Ambos campos son opcionales.

**Auth:** `driver` o `manager`

#### Request

```
PATCH /v1/trips/{trip_id}/alarm
Authorization: Bearer {access_token}
Content-Type: application/json
```

```json
{
  "alarm_at": "2025-01-15T07:00:00-05:00",
  "is_active": false
}
```

| Campo | Tipo | Requerido | Descripcion |
|-------|------|-----------|-------------|
| `alarm_at` | string (ISO 8601) | No | Nueva hora de la alarma |
| `is_active` | boolean | No | `true` = activa, `false` = desactivada |

#### Response Success (200)

```json
{
  "status": "ok",
  "message": "Alarm updated",
  "alarm": {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "trip_id": "550e8400-e29b-41d4-a716-446655440000",
    "user_id": "660e8400-e29b-41d4-a716-446655440000",
    "alarm_at": "2025-01-15T12:00:00+00:00",
    "is_active": false,
    "created_at": "2025-01-14T20:00:00+00:00",
    "updated_at": "2025-01-14T20:05:00+00:00"
  }
}
```

#### Errores

| Codigo | Mensaje | Causa |
|--------|---------|-------|
| 400 | `"Invalid trip ID"` | UUID invalido |
| 404 | `"Alarm not found"` | No existe alarma para este usuario+trip |

---

### 4. DELETE `/v1/trips/{trip_id}/alarm` - Eliminar Alarma

Elimina permanentemente la alarma del usuario en ese trip.

**Auth:** `driver` o `manager`

#### Request

```
DELETE /v1/trips/{trip_id}/alarm
Authorization: Bearer {access_token}
```

#### Response Success (200)

```json
{
  "status": "ok",
  "message": "Alarm deleted",
  "trip_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### Errores

| Codigo | Mensaje | Causa |
|--------|---------|-------|
| 400 | `"Invalid trip ID"` | UUID invalido |
| 404 | `"Alarm not found"` | No existe alarma para este usuario+trip |

---

## TypeScript/Kotlin/Swift Types

### TypeScript

```typescript
// === Request Models ===

interface CreateAlarmRequest {
  alarm_at: string; // ISO 8601 datetime con timezone
}

interface UpdateAlarmRequest {
  alarm_at?: string;  // ISO 8601 datetime con timezone
  is_active?: boolean;
}

// === Response Models ===

interface Alarm {
  id: string;
  trip_id: string;
  user_id: string;
  alarm_at: string;    // ISO 8601
  is_active: boolean;
  created_at: string;  // ISO 8601
  updated_at: string;  // ISO 8601
}

interface CreateAlarmResponse {
  status: string;
  message: string;
  alarm: Alarm;
}

interface ListAlarmsResponse {
  alarms: Alarm[];
  total: number;
}

interface UpdateAlarmResponse {
  status: string;
  message: string;
  alarm: Alarm;
}

interface DeleteAlarmResponse {
  status: string;
  message: string;
  trip_id: string;
}
```

### Kotlin (Android)

```kotlin
// === Request Models ===

data class CreateAlarmRequest(
    val alarm_at: String  // ISO 8601
)

data class UpdateAlarmRequest(
    val alarm_at: String? = null,
    val is_active: Boolean? = null
)

// === Response Models ===

data class Alarm(
    val id: String,
    val trip_id: String,
    val user_id: String,
    val alarm_at: String,
    val is_active: Boolean,
    val created_at: String,
    val updated_at: String
)

data class CreateAlarmResponse(
    val status: String,
    val message: String,
    val alarm: Alarm
)

data class ListAlarmsResponse(
    val alarms: List<Alarm>,
    val total: Int
)

data class UpdateAlarmResponse(
    val status: String,
    val message: String,
    val alarm: Alarm
)

data class DeleteAlarmResponse(
    val status: String,
    val message: String,
    val trip_id: String
)
```

### Swift (iOS)

```swift
// === Request Models ===

struct CreateAlarmRequest: Codable {
    let alarm_at: String  // ISO 8601
}

struct UpdateAlarmRequest: Codable {
    let alarm_at: String?
    let is_active: Bool?
}

// === Response Models ===

struct Alarm: Codable {
    let id: String
    let trip_id: String
    let user_id: String
    let alarm_at: String
    let is_active: Bool
    let created_at: String
    let updated_at: String
}

struct CreateAlarmResponse: Codable {
    let status: String
    let message: String
    let alarm: Alarm
}

struct ListAlarmsResponse: Codable {
    let alarms: [Alarm]
    let total: Int
}

struct UpdateAlarmResponse: Codable {
    let status: String
    let message: String
    let alarm: Alarm
}

struct DeleteAlarmResponse: Codable {
    let status: String
    let message: String
    let trip_id: String
}
```

---

## API Service

### TypeScript (React Native / Web)

```typescript
import apiClient from './apiClient'; // Axios con interceptors (ver auth guide)

export const alarmService = {

  async createAlarm(tripId: string, alarmAt: string): Promise<CreateAlarmResponse> {
    const response = await apiClient.post(`/v1/trips/${tripId}/alarm`, {
      alarm_at: alarmAt,
    });
    return response.data;
  },

  async getAlarms(): Promise<ListAlarmsResponse> {
    const localTime = new Date().toISOString();
    const response = await apiClient.get('/v1/trips/alarms', {
      params: { local_time: localTime },
    });
    return response.data;
  },

  async updateAlarm(
    tripId: string,
    data: UpdateAlarmRequest
  ): Promise<UpdateAlarmResponse> {
    const response = await apiClient.patch(`/v1/trips/${tripId}/alarm`, data);
    return response.data;
  },

  async deleteAlarm(tripId: string): Promise<DeleteAlarmResponse> {
    const response = await apiClient.delete(`/v1/trips/${tripId}/alarm`);
    return response.data;
  },
};
```

### Kotlin (Android)

```kotlin
class AlarmApiService(
    private val httpClient: HttpClient,
    private val baseUrl: String
) {
    suspend fun createAlarm(
        tripId: String,
        alarmAt: String,
        token: String
    ): Result<CreateAlarmResponse> {
        return try {
            val response = httpClient.post("$baseUrl/v1/trips/$tripId/alarm") {
                header("Authorization", "Bearer $token")
                contentType(ContentType.Application.Json)
                setBody(CreateAlarmRequest(alarm_at = alarmAt))
            }
            when (response.status) {
                HttpStatusCode.Created -> Result.success(response.body())
                HttpStatusCode.Conflict -> Result.failure(Exception("Alarm already exists"))
                else -> Result.failure(Exception("Error ${response.status}"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun getAlarms(
        token: String
    ): Result<ListAlarmsResponse> {
        return try {
            val localTime = java.time.LocalDateTime.now().toString()
            val response = httpClient.get("$baseUrl/v1/trips/alarms?local_time=$localTime") {
                header("Authorization", "Bearer $token")
            }
            Result.success(response.body())
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun updateAlarm(
        tripId: String,
        data: UpdateAlarmRequest,
        token: String
    ): Result<UpdateAlarmResponse> {
        return try {
            val response = httpClient.patch("$baseUrl/v1/trips/$tripId/alarm") {
                header("Authorization", "Bearer $token")
                contentType(ContentType.Application.Json)
                setBody(data)
            }
            Result.success(response.body())
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun deleteAlarm(
        tripId: String,
        token: String
    ): Result<DeleteAlarmResponse> {
        return try {
            val response = httpClient.delete("$baseUrl/v1/trips/$tripId/alarm") {
                header("Authorization", "Bearer $token")
            }
            Result.success(response.body())
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
```

### Swift (iOS)

```swift
class AlarmApiService {
    let baseURL: String

    init(baseURL: String) {
        self.baseURL = baseURL
    }

    func createAlarm(
        tripId: String,
        alarmAt: String,
        token: String
    ) async throws -> CreateAlarmResponse {
        let url = URL(string: "\(baseURL)/v1/trips/\(tripId)/alarm")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(CreateAlarmRequest(alarm_at: alarmAt))

        let (data, _) = try await URLSession.shared.data(for: request)
        return try JSONDecoder().decode(CreateAlarmResponse.self, from: data)
    }

    func getAlarms(
        token: String
    ) async throws -> ListAlarmsResponse {
        let formatter = ISO8601DateFormatter()
        let localTime = formatter.string(from: Date())
        let url = URL(string: "\(baseURL)/v1/trips/alarms?local_time=\(localTime)")!
        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        let (data, _) = try await URLSession.shared.data(for: request)
        return try JSONDecoder().decode(ListAlarmsResponse.self, from: data)
    }

    func updateAlarm(
        tripId: String,
        alarmAt: String? = nil,
        isActive: Bool? = nil,
        token: String
    ) async throws -> UpdateAlarmResponse {
        let url = URL(string: "\(baseURL)/v1/trips/\(tripId)/alarm")!
        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(
            UpdateAlarmRequest(alarm_at: alarmAt, is_active: isActive)
        )

        let (data, _) = try await URLSession.shared.data(for: request)
        return try JSONDecoder().decode(UpdateAlarmResponse.self, from: data)
    }

    func deleteAlarm(
        tripId: String,
        token: String
    ) async throws -> DeleteAlarmResponse {
        let url = URL(string: "\(baseURL)/v1/trips/\(tripId)/alarm")!
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        let (data, _) = try await URLSession.shared.data(for: request)
        return try JSONDecoder().decode(DeleteAlarmResponse.self, from: data)
    }
}
```

---

## Comportamiento del UI

### Icono de Reloj en la Trip Card

El icono de reloj en la trip card tiene dos estados:

| Estado | Visual | Accion al tocar |
|--------|--------|-----------------|
| Sin alarma | Reloj gris / outline | Abre modal para crear alarma |
| Con alarma activa | Reloj azul / filled | Desactiva o elimina la alarma |

### Flujo: Crear Alarma

```
1. Driver toca icono de reloj en la trip card
   |
   v
2. Se abre modal/bottom-sheet con time picker
   - Pre-cargado con pick_up_time del trip (campo del trip)
   - Driver puede ajustar la hora
   |
   v
3. Driver confirma la hora
   |
   v
4. POST /v1/trips/{trip_id}/alarm { alarm_at: "..." }
   |
   v
5. Si 201: alarma creada
   - Actualizar icono a estado "activa" (azul/filled)
   - Re-fetch alarmas: GET /v1/trips/alarms
   - Programar notificacion local con la nueva lista
   |
   v
6. Si 409: alarma ya existe (edge case)
   - Mostrar mensaje: "Ya tienes una alarma para este viaje"
```

### Flujo: Desactivar/Eliminar Alarma

```
1. Driver toca icono de reloj activo (azul) en la trip card
   |
   v
2. Opcion A - Toggle rapido:
   PATCH /v1/trips/{trip_id}/alarm { is_active: false }
   - Desactiva la alarma sin eliminarla
   - Icono cambia a gris
   |
   Opcion B - Eliminar:
   DELETE /v1/trips/{trip_id}/alarm
   - Elimina la alarma permanentemente
   - Icono cambia a gris
   |
   v
3. Re-fetch alarmas: GET /v1/trips/alarms
4. Re-programar notificaciones con la lista actualizada
```

### Pre-cargar Hora del Trip

Cuando se abre el modal de alarma, el time picker debe iniciar con la hora del trip:

```typescript
// El trip ya tiene pick_up_date y pick_up_time
// Combinarlos para crear el datetime inicial del picker

const trip = {
  pick_up_date: "2025-01-15",      // date
  pick_up_time: "06:00:00",         // time
  // ...
};

// Crear datetime para el picker (usar timezone de la location)
const defaultAlarmAt = `${trip.pick_up_date}T${trip.pick_up_time}`;
```

---

## Sistema de Notificaciones Locales

### Carga Inicial (App Startup)

Al abrir la app, inmediatamente despues de autenticarse:

```typescript
// En el componente principal o en el AuthContext despues del login
async function initAlarms() {
  const { alarms } = await alarmService.getAlarms();
  scheduleAllAlarms(alarms);
}
```

### Programar Alarmas (Web - setTimeout)

Implementacion temporal con setTimeout. Se reemplazara por bridge nativo.

```typescript
// Map para trackear los timeouts activos
const activeTimers: Map<string, NodeJS.Timeout> = new Map();

function scheduleAllAlarms(alarms: Alarm[]) {
  // Limpiar todos los timers anteriores
  activeTimers.forEach((timer) => clearTimeout(timer));
  activeTimers.clear();

  const now = Date.now();

  alarms.forEach((alarm) => {
    const alarmTime = new Date(alarm.alarm_at).getTime();
    const delay = alarmTime - now;

    // Solo programar si la alarma es en el futuro
    if (delay > 0) {
      const timer = setTimeout(() => {
        fireAlarm(alarm);
        activeTimers.delete(alarm.id);
      }, delay);

      activeTimers.set(alarm.id, timer);
    }
  });
}

function fireAlarm(alarm: Alarm) {
  // Web: usar Notification API o alert
  if ('Notification' in window && Notification.permission === 'granted') {
    new Notification('Trip Alarm', {
      body: `Alarm for trip ${alarm.trip_id}`,
      icon: '/alarm-icon.png',
    });
  } else {
    // Fallback
    alert(`Alarm! Trip: ${alarm.trip_id}`);
  }
}

// Limpiar al cerrar la app o hacer logout
function clearAllAlarms() {
  activeTimers.forEach((timer) => clearTimeout(timer));
  activeTimers.clear();
}
```

### Refrescar Alarmas

Llamar despues de cada operacion CRUD:

```typescript
async function refreshAlarms() {
  const { alarms } = await alarmService.getAlarms();
  scheduleAllAlarms(alarms); // Limpia los anteriores y programa los nuevos
  return alarms;
}

// Uso despues de crear alarma:
await alarmService.createAlarm(tripId, alarmAt);
const alarms = await refreshAlarms();
// Actualizar UI con la nueva lista

// Uso despues de eliminar alarma:
await alarmService.deleteAlarm(tripId);
const alarms = await refreshAlarms();
// Actualizar UI
```

### React Native - Futuro Bridge Nativo

Cuando el bridge nativo este disponible, reemplazar `scheduleAllAlarms`:

```typescript
// Futuro: usar react-native-push-notification o expo-notifications
import * as Notifications from 'expo-notifications';

async function scheduleAllAlarmsNative(alarms: Alarm[]) {
  // Cancelar todas las notificaciones previas
  await Notifications.cancelAllScheduledNotificationsAsync();

  for (const alarm of alarms) {
    const triggerDate = new Date(alarm.alarm_at);

    // Solo programar si es en el futuro
    if (triggerDate.getTime() > Date.now()) {
      await Notifications.scheduleNotificationAsync({
        content: {
          title: 'Trip Alarm',
          body: `Your trip alarm is going off!`,
          data: { trip_id: alarm.trip_id, alarm_id: alarm.id },
        },
        trigger: triggerDate,
      });
    }
  }
}
```

---

## React Hook: useAlarms

```typescript
import { useState, useEffect, useCallback, useRef } from 'react';
import { alarmService } from '../services/alarmService';

interface UseAlarmsReturn {
  alarms: Alarm[];
  loading: boolean;
  error: string | null;
  hasAlarmForTrip: (tripId: string) => boolean;
  createAlarm: (tripId: string, alarmAt: string) => Promise<void>;
  toggleAlarm: (tripId: string) => Promise<void>;
  deleteAlarm: (tripId: string) => Promise<void>;
}

export function useAlarms(): UseAlarmsReturn {
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timersRef = useRef<Map<string, NodeJS.Timeout>>(new Map());

  // Cargar alarmas y programar notificaciones
  const fetchAndSchedule = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await alarmService.getAlarms();
      setAlarms(response.alarms);
      scheduleAlarms(response.alarms);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error loading alarms');
    } finally {
      setLoading(false);
    }
  }, []);

  // Programar timeouts para cada alarma
  const scheduleAlarms = useCallback((alarmList: Alarm[]) => {
    // Limpiar timers anteriores
    timersRef.current.forEach((timer) => clearTimeout(timer));
    timersRef.current.clear();

    const now = Date.now();
    alarmList.forEach((alarm) => {
      const delay = new Date(alarm.alarm_at).getTime() - now;
      if (delay > 0) {
        const timer = setTimeout(() => {
          fireAlarm(alarm);
          timersRef.current.delete(alarm.id);
        }, delay);
        timersRef.current.set(alarm.id, timer);
      }
    });
  }, []);

  // Emitir alarma
  const fireAlarm = (alarm: Alarm) => {
    if ('Notification' in window && Notification.permission === 'granted') {
      new Notification('Trip Alarm', {
        body: `Your alarm for the trip is going off!`,
      });
    }
    // TODO: Reemplazar con bridge nativo cuando este disponible
  };

  // Cargar al montar
  useEffect(() => {
    fetchAndSchedule();
    return () => {
      timersRef.current.forEach((timer) => clearTimeout(timer));
      timersRef.current.clear();
    };
  }, [fetchAndSchedule]);

  // Verificar si un trip tiene alarma
  const hasAlarmForTrip = useCallback(
    (tripId: string) => alarms.some((a) => a.trip_id === tripId),
    [alarms]
  );

  // Crear alarma
  const createAlarm = useCallback(async (tripId: string, alarmAt: string) => {
    await alarmService.createAlarm(tripId, alarmAt);
    await fetchAndSchedule(); // Re-fetch y re-programar
  }, [fetchAndSchedule]);

  // Toggle: si esta activa la desactiva, si no existe no hace nada
  const toggleAlarm = useCallback(async (tripId: string) => {
    const alarm = alarms.find((a) => a.trip_id === tripId);
    if (!alarm) return;

    await alarmService.deleteAlarm(tripId);
    await fetchAndSchedule();
  }, [alarms, fetchAndSchedule]);

  // Eliminar alarma
  const deleteAlarm = useCallback(async (tripId: string) => {
    await alarmService.deleteAlarm(tripId);
    await fetchAndSchedule();
  }, [fetchAndSchedule]);

  return {
    alarms,
    loading,
    error,
    hasAlarmForTrip,
    createAlarm,
    toggleAlarm,
    deleteAlarm,
  };
}
```

---

## Componente: Trip Card con Alarma

```tsx
import React, { useState } from 'react';
import { useAlarms } from '../hooks/useAlarms';

interface TripCardProps {
  trip: {
    id: string;
    pick_up_date: string;
    pick_up_time: string;
    pick_up_location: string;
    drop_off_location: string;
    airline: string;
    flight_number: string;
  };
}

function TripCard({ trip }: TripCardProps) {
  const { hasAlarmForTrip, createAlarm, toggleAlarm } = useAlarms();
  const [showAlarmModal, setShowAlarmModal] = useState(false);
  const hasAlarm = hasAlarmForTrip(trip.id);

  const handleAlarmPress = () => {
    if (hasAlarm) {
      // Ya tiene alarma → eliminar/desactivar
      toggleAlarm(trip.id);
    } else {
      // No tiene alarma → abrir modal para crear
      setShowAlarmModal(true);
    }
  };

  const handleAlarmConfirm = async (selectedTime: string) => {
    // selectedTime ya viene en ISO 8601 del picker
    await createAlarm(trip.id, selectedTime);
    setShowAlarmModal(false);
  };

  return (
    <div className="trip-card">
      {/* ... otros datos del trip ... */}
      <div className="trip-card-header">
        <span>{trip.airline} {trip.flight_number}</span>
        <span>{trip.pick_up_time}</span>

        {/* Icono de alarma */}
        <button
          onClick={handleAlarmPress}
          className={`alarm-icon ${hasAlarm ? 'active' : ''}`}
        >
          {hasAlarm ? '🔔' : '🔕'}
        </button>
      </div>

      <div className="trip-card-body">
        <span>{trip.pick_up_location} → {trip.drop_off_location}</span>
      </div>

      {/* Modal de alarma */}
      {showAlarmModal && (
        <AlarmModal
          defaultTime={`${trip.pick_up_date}T${trip.pick_up_time}`}
          onConfirm={handleAlarmConfirm}
          onClose={() => setShowAlarmModal(false)}
        />
      )}
    </div>
  );
}
```

### Componente: Alarm Modal

```tsx
import React, { useState } from 'react';

interface AlarmModalProps {
  defaultTime: string;  // ISO 8601 datetime pre-cargado con hora del trip
  onConfirm: (alarmAt: string) => void;
  onClose: () => void;
}

function AlarmModal({ defaultTime, onConfirm, onClose }: AlarmModalProps) {
  const [selectedTime, setSelectedTime] = useState(defaultTime);

  return (
    <div className="alarm-modal-overlay" onClick={onClose}>
      <div className="alarm-modal" onClick={(e) => e.stopPropagation()}>
        <h3>Set Alarm</h3>

        <input
          type="datetime-local"
          value={selectedTime}
          onChange={(e) => setSelectedTime(e.target.value)}
        />

        <div className="alarm-modal-actions">
          <button onClick={onClose}>Cancel</button>
          <button onClick={() => onConfirm(new Date(selectedTime).toISOString())}>
            Confirm
          </button>
        </div>
      </div>
    </div>
  );
}
```

---

## Flujo Completo

```
APP STARTUP
   |
   v
Login → POST /v1/auth/sign-in
   |
   v
Cargar alarmas → GET /v1/trips/alarms
   |
   v
Programar setTimeout por cada alarm_at en el futuro
   |
   v
Driver navega a la lista de trips
   |
   v
Por cada trip card:
   - Si tiene alarma → icono azul/filled
   - Si no tiene → icono gris/outline
   |
   v
Driver toca reloj GRIS (sin alarma):
   |→ Abre modal con pick_up_time del trip
   |→ Driver ajusta hora
   |→ Confirma → POST /v1/trips/{trip_id}/alarm
   |→ Re-fetch: GET /v1/trips/alarms
   |→ Re-programar todos los setTimeout
   |→ Icono cambia a azul
   |
   v
Driver toca reloj AZUL (con alarma):
   |→ DELETE /v1/trips/{trip_id}/alarm
   |→ Re-fetch: GET /v1/trips/alarms
   |→ Re-programar todos los setTimeout
   |→ Icono cambia a gris
   |
   v
Cuando llega la hora (setTimeout se dispara):
   |→ Emitir Notification API o alert
   |→ (Futuro: bridge nativo para notificacion real)
   |
   v
Cuando trip se completa (drop-off):
   |→ Trip se borra del backend
   |→ FK CASCADE borra la alarma automaticamente
   |→ Proximo GET /v1/trips/alarms ya no la incluye
```

---

## Notas Importantes

1. **Pre-carga**: El modal de alarma siempre abre con la hora `pick_up_time` del trip como default
2. **Re-fetch despues de cada accion**: Siempre llamar `GET /v1/trips/alarms` despues de crear, actualizar o eliminar una alarma para mantener sincronizado
3. **Permisos de Notification**: En web, solicitar permisos con `Notification.requestPermission()` al primer uso
4. **setTimeout limitacion**: Para alarmas muy lejanas (>24h), considerar usar `setInterval` de verificacion o programar solo las proximas 24 horas
5. **Cleanup de FK CASCADE**: Cuando un trip se completa y se archiva, la alarma se borra automaticamente en el backend. El frontend solo necesita re-fetchear
6. **Futuro - Tab de Alarmas**: Se planea una tab dedicada para gestionar todas las alarmas (editar, eliminar, crear alarmas no asociadas a trips). Por ahora el toggle rapido desde la trip card es suficiente
7. **Futuro - Bridge Nativo**: La implementacion actual con setTimeout es temporal. Se reemplazara por `expo-notifications` o `react-native-push-notification` para emitir alarmas nativas del OS

---

## Ejemplos cURL

### Crear alarma
```bash
curl -X POST "https://web.gt360.app/v1/trips/{trip_id}/alarm" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{"alarm_at": "2025-01-15T06:00:00-05:00"}'
```

### Listar alarmas
```bash
curl -X GET "https://web.gt360.app/v1/trips/alarms?local_time=2026-02-09T09:00:00" \
  -H "Authorization: Bearer {token}"
```

### Actualizar alarma (cambiar hora)
```bash
curl -X PATCH "https://web.gt360.app/v1/trips/{trip_id}/alarm" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{"alarm_at": "2025-01-15T07:00:00-05:00"}'
```

### Desactivar alarma
```bash
curl -X PATCH "https://web.gt360.app/v1/trips/{trip_id}/alarm" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{"is_active": false}'
```

### Eliminar alarma
```bash
curl -X DELETE "https://web.gt360.app/v1/trips/{trip_id}/alarm" \
  -H "Authorization: Bearer {token}"
```

---

**Last updated:** 2026-02-08
