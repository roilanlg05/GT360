# Bugfix: UUID Validation in Trips Router

**Fecha:** 2026-01-04
**Archivo modificado:** `features/trips/routes/trips_router.py`
**Severidad:** Alta

---

## Resumen

Se corrigieron dos bugs críticos relacionados con la validación de UUIDs en los endpoints de trips y locations. Ambos bugs causaban errores 404 y 500 respectivamente debido a comparaciones incorrectas entre tipos de datos (string vs UUID).

---

## Bug #1: GET /v1/locations/{location_id}/trips retornaba 404

### Problema

El endpoint recibía `location_id` como string y lo comparaba directamente con `TripDB.location_id` que es de tipo UUID en PostgreSQL.

**Código anterior (línea 285):**
```python
filters = [TripDB.location_id == location_id]  # location_id es string
```

**Error resultante:**
- PostgreSQL no encontraba resultados debido a la incompatibilidad de tipos
- El endpoint retornaba 404 "No trips matching your filters" aunque existieran trips

### Solución

1. Convertir `location_id` a UUID antes de usarlo
2. Validar existencia de la location
3. Retornar lista vacía `[]` en lugar de 404 cuando no hay trips

**Código corregido:**
```python
from uuid import UUID

# Validar UUID de location
try:
    location_uuid = UUID(location_id)
except ValueError:
    raise HTTPException(status_code=400, detail="ID de location inválido")

# Validar existencia de location
location = await session.exec(
    Select(Location).Where(Location.id == location_uuid)
).first()

if not location:
    raise HTTPException(status_code=404, detail="Location no encontrada")

# Usar UUID en el filtro
filters = [TripDB.location_id == location_uuid]
```

**Cambio adicional - Retornar lista vacía:**
```python
# Antes: lanzaba 404
if not rows:
    raise HTTPException(status_code=404, detail="No trips matching...")

# Después: retorna lista vacía
if not rows:
    return {
        "data": [],
        "skip": skip,
        "limit": limit,
        "total": 0
    }
```

---

## Bug #2: DELETE /v1/locations/{location_id} retornaba 500

### Problema

El endpoint eliminaba la location sin validar el UUID ni verificar su existencia, causando un error interno del servidor.

**Código anterior (líneas 511-514):**
```python
await session.exec(
    Delete(Location)
    .Where(Location.id == location_id)  # location_id es string
)
```

**Error resultante:**
- PostgreSQL lanzaba: `operator does not exist: uuid = text`
- El servidor retornaba 500 Internal Server Error
- El navegador mostraba error CORS adicional porque el 500 no incluía headers CORS

### Solución

1. Convertir `location_id` a UUID
2. Validar existencia de la location antes de eliminar
3. Usar el UUID en la consulta DELETE

**Código corregido:**
```python
from uuid import UUID

# Validar UUID de location
try:
    location_uuid = UUID(location_id)
except ValueError:
    raise HTTPException(status_code=400, detail="ID de location inválido")

# Validar existencia de location
location = await session.exec(
    Select(Location).Where(Location.id == location_uuid)
).first()

if not location:
    raise HTTPException(status_code=404, detail="Location no encontrada")

# Eliminar location (CASCADE eliminará trips, hotels, etc.)
await session.exec(
    Delete(Location)
    .Where(Location.id == location_uuid)
)

await session.commit()
```

---

## Endpoints Afectados

| Endpoint | Bug | Estado |
|----------|-----|--------|
| `GET /v1/locations/{location_id}/trips` | 404 incorrecto | Corregido |
| `DELETE /v1/locations/{location_id}` | 500 + CORS | Corregido |

---

## Nuevos Códigos de Respuesta

### GET /v1/locations/{location_id}/trips

| Código | Condición | Respuesta |
|--------|-----------|-----------|
| 200 | Éxito (con o sin trips) | `{"data": [...], "skip": 0, "limit": 20, "total": N}` |
| 400 | UUID inválido | `{"detail": "ID de location inválido"}` |
| 401 | Sin autenticación | `{"detail": "Missing or invalid authentication"}` |
| 403 | Sin permisos | `{"detail": "Not Authorized..."}` |
| 404 | Location no existe | `{"detail": "Location no encontrada"}` |

### DELETE /v1/locations/{location_id}

| Código | Condición | Respuesta |
|--------|-----------|-----------|
| 200 | Éxito | `{"data": "Location {id} deleted successfully"}` |
| 400 | UUID inválido | `{"detail": "ID de location inválido"}` |
| 401 | Sin autenticación | `{"detail": "Missing or invalid authentication"}` |
| 403 | Sin permisos | `{"detail": "Not Authorized..."}` |
| 404 | Location no existe | `{"detail": "Location no encontrada"}` |

---

## Comparación con Endpoints Existentes

Los siguientes endpoints ya tenían la validación correcta y sirvieron como referencia:

| Endpoint | Validación UUID | Validación Existencia |
|----------|-----------------|----------------------|
| `POST /v1/locations/{location_id}/trips` | ✅ | ✅ |
| `DELETE /v1/locations/{location_id}/trips/{trip_id}` | ✅ | ✅ |
| `PATCH /v1/locations/{location_id}/trips/{trip_id}` | ✅ | ✅ |
| `DELETE /v1/locations/{location_id}/trips` | ✅ | ✅ |

---

## Impacto en Frontend

El frontend ahora debe manejar:

1. **GET trips con lista vacía:** Ya no recibirá 404 cuando no hay trips, sino 200 con `data: []`
2. **DELETE location con validación:** Recibirá 400 o 404 con mensajes claros en lugar de 500

---

## Testing

Para verificar las correcciones:

```bash
# Test GET trips con location válida sin trips
curl -X GET "https://api.gt360.app/v1/locations/{valid_uuid}/trips" \
  -H "Authorization: Bearer {token}"
# Esperado: 200 con data: []

# Test GET trips con UUID inválido
curl -X GET "https://api.gt360.app/v1/locations/invalid-uuid/trips" \
  -H "Authorization: Bearer {token}"
# Esperado: 400 "ID de location inválido"

# Test DELETE location
curl -X DELETE "https://api.gt360.app/v1/locations/{valid_uuid}" \
  -H "Authorization: Bearer {token}"
# Esperado: 200 "Location {id} deleted successfully"
```
