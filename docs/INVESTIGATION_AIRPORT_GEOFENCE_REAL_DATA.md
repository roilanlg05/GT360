# 🔍 Investigación: Geocerca del Aeropuerto - Datos Reales

**Fecha:** 2026-02-16
**Investigador:** Claude (Backend Analysis)
**Propósito:** Determinar dónde está guardado y cómo se envía el "radio pequeño del aeropuerto"

---

## 📊 DATOS REALES DE LA BASE DE DATOS

### Consulta Ejecutada:
```sql
SELECT
    l.name as airport_code,
    l.radio_zone as location_radio_zone,
    a.radio_zone as airport_radio_zone
FROM entities.locations l
LEFT JOIN entities.airports a ON a.code = l.name
ORDER BY l.created_at DESC;
```

### Resultados:
```
 airport_code | location_radio_zone | airport_radio_zone
--------------+---------------------+--------------------
 SDF          |                0.04 |               1.00
 SDF          |                0.50 |               1.00
 ONT          |                0.50 |               1.00
 ONT          |                0.50 |               1.00
```

---

## 🎯 HALLAZGOS CLAVE

### 1. HAY DOS VALORES DIFERENTES:

#### **`location.radio_zone`** (Tabla `entities.locations`)
- **Valor real:** 0.04 millas (64 metros) o 0.50 millas (805 metros)
- **Configurado:** MANUALMENTE usando `PATCH /v1/locations/{id}`
- **Propósito:** Geocerca operacional del aeropuerto
- **Quién lo ve:** Driver Y Manager

#### **`airport.radio_zone`** (Tabla `entities.airports`)
- **Valor real:** 1.00 milla (1609 metros)
- **Configurado:** Default en la tabla de aeropuertos
- **Propósito:** Radio máximo del aeropuerto (no se usa actualmente)
- **Quién lo ve:** Nadie (no se envía en endpoints)

---

## 🔄 FLUJO DE CREACIÓN DE LOCATION

### Código de Creación:
```python
# features/trips/routes/trips_router.py, línea 132-149

radio = 0.0  # ❌ Se setea en 0.0, NO se copia del airport

location = Location(
    organization_id=organization.id,
    name=airport,  # "SDF"
    point={
        "type": "Point",
        "coordinates": [airportdb.longitude, airportdb.latitude]
    },
    radio_zone=radio,  # ❌ 0.0, NO 1.00 del airport
    provider=provider,
    timezone=tz_from_latlon(airportdb.latitude, airportdb.longitude)
)
```

### ¿Cómo llegó a 0.04 o 0.50?
Alguien actualizó manualmente usando:
```
PATCH /v1/locations/{location_id}
{
  "radio_zone": 0.04  // o 0.50
}
```

---

## 📡 QUÉ RECIBE EL DRIVER

### Endpoint:
```
GET /v1/locations/{location_id}/trips/{trip_id}/details
```

### Response (LocationDetails):
```json
{
  "location": {
    "id": "45df7204-88ba-4ad4-9d33-1cd14c9a1cdc",
    "name": "SDF",
    "point": {
      "type": "Point",
      "coordinates": [-85.7421183748628, 38.18643251412894]
    },
    "radio_zone": 0.04,  // 👈 ESTA ES LA GEOCERCA QUE VE EL DRIVER
    "validation_status": "VALIDATED",
    "timezone": "America/New_York"
  }
}
```

### En el mapa móvil del driver:
```
Centro: [-85.7421, 38.1864]
Radio: 0.04 millas = 64.37 metros
```

---

## 📡 QUÉ PUEDE VER EL MANAGER

### Endpoint (el MISMO que usa el driver):
```
GET /v1/locations?location_id={id}
```

### Response:
```json
{
  "data": {
    "id": "45df7204-88ba-4ad4-9d33-1cd14c9a1cdc",
    "name": "SDF",
    "point": {
      "type": "Point",
      "coordinates": [-85.7421183748628, 38.18643251412894]
    },
    "radio_zone": 0.04,  // 👈 EL MANAGER TAMBIÉN VE ESTO
    "validation_status": "VALIDATED",
    "timezone": "America/New_York"
  }
}
```

### ✅ CONCLUSIÓN:
**EL MANAGER SÍ PUEDE VER `location.radio_zone = 0.04`**

El frontend del manager YA tiene acceso a esta información usando `GET /v1/locations`.

---

## ❌ LO QUE EL MANAGER **NO** PUEDE VER

### Tabla `entities.airports`:
```sql
SELECT code, radio_zone FROM entities.airports WHERE code = 'SDF';

 code | radio_zone
------+------------
 SDF  |       1.00
```

**Problema:** Este valor (`airport.radio_zone = 1.00`) NO se envía en ningún endpoint actual.

---

## 🎨 CÓMO PINTAR EN EL MAPA (FRONTEND MANAGER)

### Geocerca que SÍ se puede pintar:

```typescript
// Obtener location
const response = await fetch('/api/v1/locations?location_id={id}');
const { data: location } = await response.json();

// Pintar en Google Maps
<Circle
  center={{
    lat: location.point.coordinates[1],  // 38.1864
    lng: location.point.coordinates[0]   // -85.7421
  }}
  radius={location.radio_zone * 1609.344}  // 0.04 * 1609.344 = 64 metros
  options={{
    fillColor: '#3b82f6',
    fillOpacity: 0.2,
    strokeColor: '#3b82f6',
    strokeWeight: 2,
  }}
/>
```

### Geocerca que NO se puede pintar (sin endpoint nuevo):

```typescript
// ❌ NO HAY ENDPOINT PARA ESTO
// airport.radio_zone = 1.00 millas
// Necesitaríamos: GET /v1/locations/{id}/airport
```

---

## 🔍 RESPUESTA A TU PREGUNTA

> "¿Por qué el driver está viendo una geocerca pequeña para el aeropuerto y por qué el manager no la puede ver?"

### RESPUESTA:

1. ✅ **El driver VE `location.radio_zone = 0.04 millas`** (64 metros)
2. ✅ **El manager TAMBIÉN puede ver ese mismo valor** usando `GET /v1/locations`
3. ✅ **Ambos reciben la misma información** del mismo endpoint
4. ❌ **Lo que NADIE puede ver:** `airport.radio_zone = 1.00 millas` (tabla airports)

---

## 💡 SOLUCIÓN

### Para pintar `location.radio_zone` (la geocerca pequeña operacional):

**YA ESTÁ DISPONIBLE** en `GET /v1/locations`:
- Frontend manager: ✅ Puede consumirla
- Frontend driver: ✅ Ya la consume

### Para pintar `airport.radio_zone` (la geocerca del aeropuerto de la tabla airports):

**NECESITA ENDPOINT NUEVO**:
```
GET /v1/locations/{location_id}/airport

Response:
{
  "airport": {
    "id": "uuid",
    "code": "SDF",
    "name": "Louisville Muhammad Ali International Airport",
    "latitude": 38.17,
    "longitude": -85.74,
    "radio_zone": 1.00,  // 👈 ESTE es el que falta
    ...
  }
}
```

---

## 📋 RESUMEN FINAL

| Geocerca | Tabla | Campo | Valor Real | Driver | Manager | Endpoint |
|----------|-------|-------|------------|--------|---------|----------|
| **Operacional** | `entities.locations` | `radio_zone` | 0.04 mi | ✅ Ve | ✅ Ve | `GET /v1/locations` |
| **Aeropuerto** | `entities.airports` | `radio_zone` | 1.00 mi | ❌ No ve | ❌ No ve | ❌ No existe |

---

## 🚀 RECOMENDACIÓN

Si quieres que el frontend del manager pueda pintar **AMBAS** geocercas:

1. ✅ `location.radio_zone` → Ya disponible en `GET /v1/locations`
2. ❌ `airport.radio_zone` → Crear endpoint `GET /v1/locations/{id}/airport`

**Código del endpoint nuevo:** Ver [AIRPORT_GEOFENCE_FRONTEND_GUIDE.md](./AIRPORT_GEOFENCE_FRONTEND_GUIDE.md)

---

**Última actualización:** 2026-02-16
**Investigación completada con datos reales de la base de datos.**
