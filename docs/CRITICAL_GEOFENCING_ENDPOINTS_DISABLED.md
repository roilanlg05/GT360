# 🚨 CRÍTICO: Endpoints de Geofencing Deshabilitados en Backend

**Fecha:** 2026-01-09
**Severidad:** CRÍTICA
**Impacto:** El frontend se queda cargando indefinidamente en funcionalidades de geofencing

---

## 📋 Resumen Ejecutivo

Los endpoints de geofencing y validación de hoteles están **completamente deshabilitados** en el backend, causando que el frontend se quede cargando cuando intenta:
1. Validar geofences de hoteles
2. Enviar pings de localización GPS
3. Obtener eventos de geofencing
4. Configurar zonas de visibilidad

---

## 🔍 Causa Raíz

### 1. Archivos Comentados con Triple Comillas

Los siguientes archivos están **COMPLETAMENTE deshabilitados** usando comillas triples (`'''`):

#### Archivo: `.geofencing/routes/validation_router.py`
```python
'''"""
Hotel Validation Router
...
"""
(332 líneas de código comentadas)
'''
```

**Endpoints afectados:**
- `GET /v1/locations/{location_id}/hotels/pending-validation`
- `GET /v1/locations/{location_id}/hotels`
- `POST /v1/locations/{location_id}/hotels/{hotel_id}/validate`
- `PATCH /v1/locations/{location_id}/hotels/{hotel_id}/geofence`
- `POST /v1/locations/{location_id}/hotels/{hotel_id}/disable`
- `POST /v1/locations/{location_id}/hotels/{hotel_id}/enable`

#### Archivo: `.geofencing/routes/geofence_router.py`
```python
'''"""
Geofencing Router
...
"""
(527 líneas de código comentadas)
'''
```

**Endpoints críticos afectados:**
- `POST /v1/location/update` ⚠️ **CRÍTICO - Procesa pings de GPS**
- `GET /v1/geofence-events`
- `GET /v1/geofence-events/{actor_type}/{actor_id}/current-state`
- `GET /v1/organization/geofence-settings`
- `PATCH /v1/organization/geofence-settings`
- `GET /v1/locations/{location_id}/visibility`
- `PATCH /v1/locations/{location_id}/visibility`
- `GET /v1/airports/{airport_id}`
- `PATCH /v1/airports/{airport_id}/geofence`

---

### 2. Routers No Registrados en `main.py`

#### Archivo: `main.py`

```python
# Líneas 9-12: Imports comentados
"""from features.geofencing.routes.validation_router import router as validation_router
from features.geofencing.routes.geofence_router import router as geofence_router
from features.geofencing.jobs import dwell_checker
"""

# Líneas 28, 31: DWELL checker comentado
#dwell_checker.start(interval_seconds=60)
#await dwell_checker.stop()

# Líneas 62-63: Routers no incluidos
#app.include_router(validation_router)
#app.include_router(geofence_router)
```

---

## 🐛 Síntomas en el Frontend

### 1. Loading Infinito
Cuando el frontend intenta llamar a cualquier endpoint de geofencing:
```typescript
// Ejemplo: Ping de localización
POST /v1/location/update
{
  "lat": 38.2527,
  "lon": -85.7585
}

// Respuesta: 404 Not Found
// Frontend: Se queda cargando esperando respuesta 200
```

### 2. Validación de Hoteles
```typescript
// Intento de validar hotel
POST /v1/locations/{location_id}/hotels/{hotel_id}/validate

// Respuesta: 404 Not Found
// UI: Spinner infinito, usuario no puede completar la acción
```

### 3. Obtener Eventos de Geofencing
```typescript
// Intento de obtener eventos
GET /v1/geofence-events?location_id={id}

// Respuesta: 404 Not Found
// Dashboard: Sin datos, estado de carga permanente
```

---

## ✅ Solución Inmediata para el Frontend

### Opción 1: Deshabilitar Funcionalidades de Geofencing (Recomendado)

Hasta que el backend rehabilite los endpoints, el frontend debe:

#### 1. Deshabilitar GPS Tracking
```typescript
// features/location/useLocationTracking.ts

export const useLocationTracking = () => {
  const [isGeofencingEnabled, setIsGeofencingEnabled] = useState(false);

  // IMPORTANTE: Deshabilitar hasta que backend esté listo
  useEffect(() => {
    console.warn('[GEOFENCING] Backend endpoints disabled. GPS tracking suspended.');
    setIsGeofencingEnabled(false);
  }, []);

  const sendLocationUpdate = async (lat: number, lon: number) => {
    if (!isGeofencingEnabled) {
      console.warn('[GEOFENCING] Location update skipped - backend endpoints disabled');
      return { processed: false, reason: 'backend_disabled' };
    }

    // Código normal aquí...
  };

  return { sendLocationUpdate, isGeofencingEnabled };
};
```

#### 2. Ocultar UI de Validación de Hoteles
```typescript
// features/hotels/HotelValidationPanel.tsx

export const HotelValidationPanel = () => {
  const isGeofencingAvailable = useGeofencingAvailability();

  if (!isGeofencingAvailable) {
    return (
      <Alert severity="warning">
        <AlertTitle>Funcionalidad Temporalmente No Disponible</AlertTitle>
        La validación de geofencing está temporalmente deshabilitada.
        Por favor contacte al administrador del sistema.
      </Alert>
    );
  }

  // Componente normal aquí...
};
```

#### 3. Feature Flag para Geofencing
```typescript
// config/features.ts

export const FEATURE_FLAGS = {
  GEOFENCING_ENABLED: false, // ⚠️ CAMBIAR A false HASTA QUE BACKEND SE ARREGLE
  HOTEL_VALIDATION_ENABLED: false,
  GPS_TRACKING_ENABLED: false,
  VISIBILITY_ZONE_ENABLED: false,
};

// Uso en componentes:
import { FEATURE_FLAGS } from '@/config/features';

const MyComponent = () => {
  if (!FEATURE_FLAGS.GEOFENCING_ENABLED) {
    return <DisabledFeatureMessage feature="Geofencing" />;
  }

  // Código normal...
};
```

#### 4. Manejo Graceful de Errores 404
```typescript
// services/api/geofencing.ts

export const geofencingApi = {
  async sendLocationUpdate(lat: number, lon: number) {
    try {
      const response = await fetch('/v1/location/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lat, lon })
      });

      if (response.status === 404) {
        console.error('[GEOFENCING] Backend endpoints not available (404)');
        // NO mostrar error al usuario, solo loguear
        return {
          processed: false,
          error: 'backend_not_ready',
          message: 'Geofencing endpoints are not available yet'
        };
      }

      return await response.json();
    } catch (error) {
      console.error('[GEOFENCING] Network error:', error);
      return { processed: false, error: 'network_error' };
    }
  },

  async getPendingHotels(locationId: string) {
    try {
      const response = await fetch(`/v1/locations/${locationId}/hotels/pending-validation`);

      if (response.status === 404) {
        console.warn('[GEOFENCING] Validation endpoints not available');
        return []; // Retornar array vacío en lugar de error
      }

      return await response.json();
    } catch (error) {
      console.error('[GEOFENCING] Error fetching pending hotels:', error);
      return [];
    }
  }
};
```

---

### Opción 2: Polling con Backoff (No Recomendado)

Si el frontend necesita **esperar** a que los endpoints estén disponibles:

```typescript
// utils/waitForBackend.ts

export async function waitForGeofencingEndpoints(
  maxRetries = 10,
  initialDelay = 2000
) {
  let retries = 0;
  let delay = initialDelay;

  while (retries < maxRetries) {
    try {
      // Intentar un endpoint simple
      const response = await fetch('/v1/organization/geofence-settings', {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (response.ok || response.status !== 404) {
        console.log('[GEOFENCING] Backend endpoints are now available');
        return true;
      }

      console.log(`[GEOFENCING] Endpoints not ready, retry ${retries + 1}/${maxRetries}`);
      await new Promise(resolve => setTimeout(resolve, delay));

      // Exponential backoff
      delay = Math.min(delay * 1.5, 30000);
      retries++;

    } catch (error) {
      console.error('[GEOFENCING] Health check error:', error);
      retries++;
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }

  console.error('[GEOFENCING] Backend endpoints not available after max retries');
  return false;
}
```

⚠️ **ADVERTENCIA:** Esta opción NO es recomendada porque puede crear latencia innecesaria y mala experiencia de usuario.

---

## 📝 Checklist para el Desarrollador Frontend

### Acciones Inmediatas

- [ ] Cambiar `FEATURE_FLAGS.GEOFENCING_ENABLED = false`
- [ ] Agregar manejo de errores 404 en todas las llamadas a endpoints de geofencing
- [ ] Ocultar/deshabilitar UI de validación de hoteles
- [ ] Deshabilitar GPS tracking automático
- [ ] Mostrar mensaje de "Funcionalidad no disponible" en lugar de loading infinito
- [ ] Agregar logs de debug para verificar intentos de llamadas a endpoints
- [ ] Notificar al equipo de backend sobre el problema

### Verificación Post-Fix (Cuando Backend Se Arregle)

- [ ] Verificar que `POST /v1/location/update` responde 200/201
- [ ] Verificar que `GET /v1/locations/{id}/hotels/pending-validation` responde
- [ ] Verificar que `POST /v1/locations/{id}/hotels/{id}/validate` funciona
- [ ] Habilitar `FEATURE_FLAGS.GEOFENCING_ENABLED = true`
- [ ] Probar flujo completo de validación de hotel
- [ ] Probar flujo completo de GPS tracking
- [ ] Verificar WebSocket events de geofencing

---

## 🔧 Para el Desarrollador Backend

### Acciones Requeridas

1. **Remover comillas triples de los archivos:**
   ```bash
   # Editar .geofencing/routes/validation_router.py
   # Eliminar línea 1: '''
   # Eliminar línea 332: '''

   # Editar .geofencing/routes/geofence_router.py
   # Eliminar línea 1: '''
   # Eliminar línea 527: '''
   ```

2. **Descomentar imports en `main.py`:**
   ```python
   # Línea 9-12: Descomentar
   from features.geofencing.routes.validation_router import router as validation_router
   from features.geofencing.routes.geofence_router import router as geofence_router
   from features.geofencing.jobs import dwell_checker
   ```

3. **Registrar routers:**
   ```python
   # Línea 62-63: Descomentar
   app.include_router(validation_router)
   app.include_router(geofence_router)
   ```

4. **Habilitar DWELL checker (opcional):**
   ```python
   # Línea 28: Descomentar si se necesita
   dwell_checker.start(interval_seconds=60)

   # Línea 31: Descomentar
   await dwell_checker.stop()
   ```

5. **Reiniciar el servidor:**
   ```bash
   docker-compose restart backend
   # O
   docker restart gt360_backend
   ```

6. **Verificar que los endpoints estén disponibles:**
   ```bash
   curl -X POST http://localhost:8000/v1/location/update \
     -H "Authorization: Bearer {token}" \
     -H "Content-Type: application/json" \
     -d '{"lat": 38.2527, "lon": -85.7585}'

   # Debe retornar 200, no 404
   ```

---

## 📊 Endpoints Afectados - Tabla Completa

| Método | Endpoint | Estado | Impacto Frontend |
|--------|----------|--------|------------------|
| POST | `/v1/location/update` | ❌ 404 | GPS tracking no funciona, loading infinito |
| GET | `/v1/locations/{id}/hotels/pending-validation` | ❌ 404 | No se puede ver hoteles pendientes |
| GET | `/v1/locations/{id}/hotels` | ❌ 404 | Lista de hoteles vacía |
| POST | `/v1/locations/{id}/hotels/{id}/validate` | ❌ 404 | No se puede validar hoteles |
| PATCH | `/v1/locations/{id}/hotels/{id}/geofence` | ❌ 404 | No se puede editar geofence |
| POST | `/v1/locations/{id}/hotels/{id}/disable` | ❌ 404 | No se puede deshabilitar hotel |
| POST | `/v1/locations/{id}/hotels/{id}/enable` | ❌ 404 | No se puede habilitar hotel |
| GET | `/v1/geofence-events` | ❌ 404 | Dashboard sin eventos |
| GET | `/v1/geofence-events/{type}/{id}/current-state` | ❌ 404 | Estado actual no disponible |
| GET | `/v1/organization/geofence-settings` | ❌ 404 | Configuración no disponible |
| PATCH | `/v1/organization/geofence-settings` | ❌ 404 | No se puede configurar |
| GET | `/v1/locations/{id}/visibility` | ❌ 404 | Visibility zone no disponible |
| PATCH | `/v1/locations/{id}/visibility` | ❌ 404 | No se puede editar visibility |
| GET | `/v1/airports/{id}` | ❌ 404 | Info de aeropuerto no disponible |
| PATCH | `/v1/airports/{id}/geofence` | ❌ 404 | No se puede editar geofence aeropuerto |

---

## 🔗 Documentación Relacionada

- [GEOFENCE_VALIDATION_SYSTEM.md](./GEOFENCE_VALIDATION_SYSTEM.md) - Sistema completo de geofencing
- [WEBSOCKET_FRONTEND_GUIDE.md](./WEBSOCKET_FRONTEND_GUIDE.md) - Integración de WebSockets
- [GEOFENCING_DASHBOARD_INTEGRATION_GUIDE.md](./GEOFENCING_DASHBOARD_INTEGRATION_GUIDE.md) - Integración del dashboard

---

## 📞 Contacto

Si tienes preguntas sobre este documento, contacta al equipo de backend para confirmar cuándo estarán disponibles los endpoints de geofencing.

**Prioridad:** CRÍTICA
**Fecha de descubrimiento:** 2026-01-09
**Estado:** PENDIENTE DE CORRECCIÓN EN BACKEND
