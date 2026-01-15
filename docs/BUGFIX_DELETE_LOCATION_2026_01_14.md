# Bugfix: DELETE Location Endpoint

**Fecha:** 2026-01-14 01:45 UTC
**Estado:** Corregido y desplegado

---

## Resumen del Bug

El endpoint `DELETE /v1/locations/{location_id}` retornaba **500 Internal Server Error** con el mensaje:

```
TypeError: 'list' object is not callable
```

---

## Causa Raiz

Lineas 709 y 714 de `trips_router.py` usaban sintaxis incorrecta:

**ANTES (incorrecto):**
```python
# Mezcla de SQLAlchemy (func.count) con psqlmodel (Select)
trips_count_result = await session.exec(
    Select(func.count(TripDB.id)).where(TripDB.location_id == location_uuid)
).first()
```

**DESPUES (correcto):**
```python
# Sintaxis pura de psqlmodel con .From()
trips_count_result = await session.exec(
    Select(Count(TripDB.id)).From(TripDB).Where(TripDB.location_id == location_uuid)
).first()
```

---

## Cambios Realizados

| Archivo | Linea | Cambio |
|---------|-------|--------|
| `features/trips/routes/trips_router.py` | 709 | `func.count()` → `Count()`, `.where()` → `.Where()`, agregar `.From(TripDB)` |
| `features/trips/routes/trips_router.py` | 714 | `func.count()` → `Count()`, `.where()` → `.Where()`, agregar `.From(Hotel)` |

---

## Endpoint Afectado

| Metodo | Endpoint | Estado |
|--------|----------|--------|
| DELETE | `/v1/locations/{location_id}` | Funcionando |

---

## Comportamiento Esperado

### Request
```http
DELETE /v1/locations/{location_id}
Authorization: Bearer {token}
```

### Response (200 OK)
```json
{
  "status": "ok",
  "data": {
    "location_id": "uuid",
    "location_name": "SDF",
    "trips_deleted": 1344,
    "hotels_deleted": 15,
    "message": "Location SDF deleted successfully"
  }
}
```

### Errores Posibles

| Codigo | Mensaje | Causa |
|--------|---------|-------|
| 400 | "ID de location invalido" | UUID mal formado |
| 401 | "Invalid token" | Token JWT invalido o expirado |
| 404 | "Location no encontrada" | Location no existe |

---

## Eventos WebSocket Emitidos

Al eliminar una location, el backend publica estos eventos:

### 1. `location_delete_started`
```json
{
  "type": "location_delete_started",
  "location_id": "uuid",
  "location_name": "SDF",
  "trips_count": 1344,
  "hotels_count": 15
}
```

### 2. `location_deleted`
```json
{
  "type": "location_deleted",
  "location_id": "uuid",
  "location_name": "SDF",
  "trips_deleted": 1344,
  "hotels_deleted": 15,
  "message": "Location SDF deleted",
  "detail": "1344 trips and 15 hotels also deleted"
}
```

---

## Notas

- Este bug NO afecta a los Ground Filters
- El error se producia solo al intentar eliminar una location completa
- Los endpoints de eliminar trips individuales funcionaban correctamente
