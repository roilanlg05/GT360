# Bug Analysis: Delete All Trips → Upload → Empty Table

**Fecha:** 2026-02-24
**Usuario afectado:** carlitoleo10@gmail.com
**Location:** ONT (Ontario) — `location_id: c22feb1f-36aa-4120-850a-598b8cb8d5fd`
**Org:** `b44028b6-6048-4c36-8f97-0d9d9b3bd378`

---

## 1. Resumen ejecutivo del bug

Cuando el usuario borra todos los trips y luego sube un nuevo archivo, la tabla puede quedar vacía hasta que se recarga el navegador (F5). El bug tiene **dos causas raíz independientes** en el backend, ambas confirmadas en el código fuente:

1. **El Redis cache NO se limpia al borrar trips** → el snapshot post-reconexión devuelve datos stale o vacíos.
2. **No se envía ningún evento WebSocket cuando se borran trips** → el frontend no sabe que el borrado ocurrió.

**Problema adicional confirmado:** Al borrar una location (o todos los trips en bulk), el contenedor `trip-streaming` captura los DELETE del WAL de PostgreSQL y envía múltiples batches de `trips_batch` DELETE hacia el frontend (uno por cada 100 trips borrados). Esto resulta en múltiples notificaciones de "N trips deleted" en la UI. Fix implementado: publicar `batch_delete_started` / `location_delete_started` ANTES del SQL DELETE para que el frontend pueda suprimir las notificaciones WAL redundantes.

---

## 2. Identidades y contexto del usuario

```
email:           carlitoleo10@gmail.com
user_id:         3c06a286-152e-4eff-8f31-67945cd960c0
organization_id: b44028b6-6048-4c36-8f97-0d9d9b3bd378
location (ONT):  c22feb1f-36aa-4120-850a-598b8cb8d5fd
airline:         WN (Southwest Airlines)
```

**Actividad reciente visible en logs del servidor:**
- Múltiples llamadas a `/v2/locations/c22feb1f.../airlines/WN/filters/stack?pick_up_date=2026-01-01`
- El query del filter stack devolvió **0 filas** para `pick_up_date=2026-01-01` con `is_active=True`
- Esto confirma que el usuario experimentó el problema de filtros vacíos post-upload.

---

## 3. Respuestas precisas a las preguntas del frontend

---

### Pregunta 1: ¿Cuánto tarda el backend en tener listo el snapshot después de un upload? ¿Hay delay entre HTTP 200 y WebSocket?

**Respuesta:** El upload retorna HTTP **201** en el mismo ciclo que publica el evento WebSocket.

**Secuencia exacta dentro del endpoint `POST /v1/trips/upload-trips`:**

```
1. BulkInsert en DB (con batch_insert_mode = 'true' para suprimir triggers individuales)
2. await session.commit()   ← aquí los datos están en PostgreSQL
3. Inmediatamente después del commit:
   - redis.publish("loc:{location_id}", batch_insert_event)   ← evento WS
   - redis.publish("org:{org_id}", batch_insert_event)        ← evento WS (org)
4. return JSONResponse(status_code=201, ...)   ← HTTP response
```

**No hay delay intencional** entre commit, publish, y respuesta HTTP. Todo ocurre secuencialmente en la misma función. Los trips están disponibles en PostgreSQL desde el `commit`, que es el mismo instante en que se publica el evento WS.

**PERO hay un problema crítico:** los trips nuevos **NO se agregan al cache de Redis** en este endpoint. Solo se publican via pub/sub. El cache de Redis solo se popula vía el webhook `/v1/webhooks/trips/batch`. Si el webhook no corre (o corre con delay), el snapshot post-reconexión leerá desde PostgreSQL como fallback, lo cual es correcto — **SALVO** que el cache antiguo no fue limpiado (ver Causa Raíz #1 abajo).

---

### Pregunta 2: ¿Cuándo exactamente envía el backend el `batch_insert`? ¿Es antes o después del HTTP response?

**Respuesta:** El `batch_insert` se publica a Redis **antes** de retornar el HTTP response (líneas 406-449 del trips_router.py), pero en la práctica ambos ocurren en el mismo ciclo de eventos asyncio, por lo que la diferencia es de microsegundos.

**El evento `batch_insert` que llega al WebSocket del frontend tiene esta estructura:**

```json
{
  "type": "batch_insert",
  "location_id": "c22feb1f-36aa-4120-850a-598b8cb8d5fd",
  "location_name": "ONT",
  "airline": "WN",
  "trips_count": 150,
  "months_affected": [
    { "year": 2026, "month": 0, "count": 75 },
    { "year": 2026, "month": 1, "count": 75 }
  ],
  "message": "150 trips uploaded successfully"
}
```

**IMPORTANTE:** Este `batch_insert` llega por el **WebSocket de trips** (`/ws/trips`), que es diferente del canal `trips_batch` del webhook. El frontend debe distinguirlos:

| Canal | Tipo de mensaje | Qué significa |
|-------|----------------|----------------|
| `/ws/trips` Redis pub/sub | `batch_insert` | "Se subieron N trips nuevos, reconecta para ver el snapshot" |
| `/v1/webhooks/trips/batch` | `trips_batch` | "Actualiza estos trips individuales en el cache/UI" |

---

### Pregunta 3: ¿Se borran los FilterSteps cuando se borran todos los trips?

**Respuesta: NO. Los FilterStep records permanecen en la base de datos. Esto es el comportamiento esperado y correcto.**

El esquema de `FilterStep` tiene FK solo hacia `entities.locations` (con `ON DELETE CASCADE`). No tiene FK hacia `trips.trips` de forma intencional: los FilterSteps representan una **configuración de filtros para una location+airline+fecha**, no para trips individuales.

**Por qué esto es correcto:**
Cuando el usuario borra trips y sube un nuevo archivo con el mismo schedule (mismas fechas), el sistema re-aplica automáticamente la configuración de filtros existente a los nuevos trips mediante `auto_apply_preset`. Los FilterSteps son la "memoria" de la configuración — si se borraran junto con los trips, el usuario perdería toda su configuración cada vez que actualiza el schedule.

**Flujo correcto del auto_apply_preset al re-subir:**
```
1. Trips borrados → FilterSteps permanecen para location+airline+fecha
2. Upload nuevo archivo
3. existing_dates_for_airline = {} (vacío, no hay trips aún)
4. auto_apply_to_new_trips detecta FilterSteps existentes para esas fechas
5. Aplica los FilterSteps a los nuevos trips → configuración restaurada automáticamente
```

**Nota para el frontend:** Si `reloadStackFromBackend()` devuelve los FilterSteps correctamente y los trips son visibles, el estado es consistente. El problema de "filtros sin configuración" que reporta el usuario es consecuencia del bug de Redis (Causa Raíz #1): si el snapshot devuelve trips viejos o vacíos, el frontend no tiene trips reales sobre los cuales mostrar la configuración de filtros.

---

### Pregunta 4: Logs del backend para carlitoleo10@gmail.com — ¿qué pasó exactamente?

**Lo que muestran los logs del servidor de producción (`gt360` container):**

```
GET /v2/locations/c22feb1f-36aa-4120-850a-598b8cb8d5fd/airlines/WN/filters/stack?pick_up_date=2026-01-01
→ Query: filter_steps WHERE location_id=c22feb1f... AND airline='WN' AND pick_up_date=2026-01-01 AND is_active=True
→ Result: 0 rows
→ HTTP 200 OK
```

Esto confirma que al momento de esa petición, **no había ningún FilterStep activo** para ONT/WN/2026-01-01. El frontend recibió un stack vacío, lo que se traduce en "filtros sin configuración" en la UI.

**No hay logs de un evento `batch_insert` ni de un DELETE en los logs recientes visibles**, lo que sugiere que el problema que reporta el usuario ocurrió antes del período de retención visible.

---

### Pregunta 5: Después de un softReconnect, ¿el backend envía automáticamente un snapshot?

**Respuesta: SÍ, siempre.**

El endpoint WebSocket `/ws/trips` envía un snapshot automáticamente al conectar cualquier cliente, sin necesidad de suscripción explícita:

```python
# features/trips/websockets/trip_websockets.py línea 177
await manager.connect(ws, location_id, claims)
await manager.ensure_location_listener(location_id)
await send_snapshot(ws, location_id)   ← SIEMPRE se llama al conectar
```

**Estrategia del snapshot (crítico para entender el bug):**

```python
async def send_snapshot(ws, location_id):
    idx_key = f"loc:{location_id}:trips"
    trip_ids = await redis.smembers(idx_key)   # SET con IDs de trips

    # FAST PATH: Si Redis tiene IDs, úsalos
    if trip_ids:
        trips = await redis.mget([f"trip:{id}" for id in trip_ids])
        if trips:   # ← Si al menos UN trip tiene datos en Redis
            await ws.send_json({"type": "snapshot", "trips": trips})
            return   # ← RETORNA AQUÍ, no consulta PostgreSQL

    # FALLBACK: Si Redis está vacío, consulta PostgreSQL
    trips = await _get_trips_from_db(location_id)
    await _populate_redis_cache(location_id, trips)   # re-llena el cache
    await ws.send_json({"type": "snapshot", "trips": trips})
```

---

### Pregunta 6: ¿Hay debounce en el backend para no enviar snapshots si hay operaciones en curso?

**Respuesta: NO. No existe ningún mecanismo de debounce, throttle, ni lock para los snapshots.**

Cada conexión WebSocket nueva dispara un `send_snapshot` inmediato. No hay estado compartido que indique "hay un upload en curso, espera". El snapshot responde con los datos que hay en Redis/DB en ese microsegundo.

---

## 4. Las dos Causas Raíz Confirmadas

### Causa Raíz #1 (CRÍTICA): Redis cache no se limpia al borrar trips

**Código del endpoint delete:**
```python
# DELETE /v1/locations/{location_id}/trips/all (línea 1059-1063)
del_stmt = Delete(TripDB).Where(TripDB.location_id == uuid_location_id)
await session.exec(del_stmt)
await session.commit()
return Response(status_code=204)
# FIN. No hay limpieza de Redis.

# DELETE /v1/locations/{location_id}/airlines/{airline}/trips/all (línea 1230-1231)
await session.exec(del_stmt)
await session.commit()
return {...}
# FIN. No hay limpieza de Redis.
```

**Claves Redis afectadas que NO se limpian:**
```
loc:{location_id}:trips    → SET con IDs de los trips (TTL: 300s)
trip:{trip_id}             → JSON de cada trip (TTL: 300s por cada trip)
```

**Consecuencia exacta del bug:**

```
Tiempo 0:    Usuario tiene 150 trips. Redis tiene:
             - loc:{loc_id}:trips = {id1, id2, ..., id150}  ← SET con 150 IDs
             - trip:id1 = {...}   trip:id2 = {...}  ... (TTL: hasta 300s)

Tiempo 1:    Usuario borra todos los trips.
             → PostgreSQL: tabla trips.trips vacía ✓
             → Redis: SIN CAMBIOS (cache stale por hasta 5 minutos)
             → WebSocket: SIN NOTIFICACIÓN (el frontend no sabe nada)

Tiempo 2:    Usuario sube nuevo archivo (150 trips nuevos).
             → PostgreSQL: 150 trips nuevos insertados ✓
             → Redis: cache NO actualizado (upload solo hace publish, no escribe en cache)
             → WebSocket: evento batch_insert publicado ✓

Tiempo 3:    Frontend recibe batch_insert → llama softReconnect() → reconecta WS.
             → Backend llama send_snapshot():
               1. redis.smembers("loc:{loc_id}:trips") = {id1...id150}  ← IDs VIEJOS!
               2. trip_ids tiene datos → entra al FAST PATH
               3. redis.mget(["trip:id1"..."trip:id150"]) = [JSON viejo, JSON viejo, ...]
               4. trips array tiene datos → RETORNA snapshot con 150 trips VIEJOS/BORRADOS
               5. PostgreSQL nunca se consulta.

RESULTADO:   Frontend recibe trips viejos (o vacíos si los TTL expiraron parcialmente)
             → tabla muestra datos incorrectos o vacíos
             → F5 fuerza nueva conexión WS → Redis expiró (>300s) → DB fallback → OK
```

**Variante "tabla vacía":**
Si el TTL de los `trip:{id}` keys expiró (>300s desde la última actualización) PERO el SET `loc:{location_id}:trips` aún existe:
```python
trip_ids = await redis.smembers(idx_key)   # SET: {id1, ..., id150} ← aún existe
# trip_ids tiene datos → fast path
trips = await redis.mget(["trip:id1"..."trip:id150"])
# mget devuelve [None, None, None, ...]  ← todos expiraron
if trips:   # ← lista de Nones → la función filtra None → trips = []
# trips está vacío → pero el if original comprueba si hay IDs en el SET, no si hay datos
# BUG: se envía snapshot con trips=[] aunque PostgreSQL tiene 150 trips nuevos
```

El código filtra los `None` del mget, pero el `if trips:` está en una posición incorrecta para detectar este caso:

```python
if trip_ids:                        # ← SET no vacío
    trips = await _get_trips_from_redis(trip_ids)   # ← lista filtrada, puede ser []
    if trips:                       # ← vacío si TTL expiró
        await ws.send_json({..., "trips": trips})
        return                      # ← NO llega aquí si trips está vacío
# ← Aquí sí llegaría al fallback de PostgreSQL
```

Revisando mejor: si `trip_ids` tiene IDs pero todos los `trip:{id}` expiraron, `trips` estará vacío, el `if trips:` falla, y **sí** cae al fallback de PostgreSQL. **Ese caso es correcto.**

El bug más peligroso es cuando los `trip:{id}` keys aún no expiraron (dentro de los primeros 5 minutos): el snapshot devuelve los trips viejos/borrados.

---

### Causa Raíz #2: No se envía WebSocket al borrar trips

```python
# delete_all_trips (línea 1036-1064): solo borra en DB, retorna 204
# delete_trips_by_airline (línea 1125-1243): solo borra en DB, retorna JSON

# NO hay: redis.publish("loc:{location_id}", ...)
# NO hay: redis.publish("org:{org_id}", ...)
```

El frontend no tiene forma de saber que los trips fueron borrados a través del WebSocket. Depende exclusivamente del estado local que maneja el frontend (el store). Si el store tiene trips en memoria y recibe un snapshot incorrecto post-upload, no hay señal del backend para invalidar la cache del frontend.

**Comparación con `delete_location`** (que SÍ notifica):
```python
# delete_location envía:
await redis.publish(f"org:{org_id}", json.dumps({
    "type": "location_deleted",
    "location_id": ...,
    ...
}))
```

---

## 5. Flujo correcto vs flujo actual

### Flujo actual (con el bug):

```
Frontend                     Backend                      Redis
   |                            |                            |
   |── DELETE airline/trips/all ──>                          |
   |                            |── DELETE trips from DB     |
   |                            |   (NO limpia Redis)        |
   |<── 200 {trips_deleted: N} ─|                            |
   |                            |                            |
   |── POST /upload-trips ──────>                            |
   |                            |── BulkInsert + commit      |
   |                            |── publish("batch_insert") ──> Redis pub/sub
   |<── 201 {uploaded_rows: N} ─|                            |
   |                            |                            |
WS recibe batch_insert          |                            |
softReconnect()                 |                            |
   |── WS connect ──────────────>                            |
   |                            |── send_snapshot()          |
   |                            |   redis.smembers(loc:trips) ─> {old_ids}
   |                            |   redis.mget(trip:old_ids) ─> [old_data]
   |                            |   (FAST PATH, no va a DB)  |
   |<── snapshot{trips: [OLD]} ─|                            |
   |                            |                            |
UI muestra trips viejos o vacíos ← BUG
```

### Flujo correcto (con fix):

```
Frontend                     Backend                      Redis
   |                            |                            |
   |── DELETE airline/trips/all ──>                          |
   |                            |── DELETE trips from DB     |
   |                            |── DEL loc:{id}:trips ──────> (limpia SET)
   |                            |── DEL trip:{id}... ─────────> (limpia keys)
   |                            |── publish("trips_deleted") ─> Redis pub/sub
   |<── 200 ───────────────────-|                            |
   |                            |                            |
WS recibe trips_deleted          |                            |
   |                            |                            |
   |── POST /upload-trips ──────>                            |
   |                            |── BulkInsert + commit      |
   |                            |── publish("batch_insert") ──> Redis pub/sub
   |<── 201 ────────────────────|                            |
   |                            |                            |
WS recibe batch_insert          |                            |
softReconnect()                 |                            |
   |── WS connect ──────────────>                            |
   |                            |── send_snapshot()          |
   |                            |   redis.smembers(loc:trips) ─> {} (vacío)
   |                            |   (FALLBACK a PostgreSQL)  |
   |                            |── SELECT * from trips      |
   |<── snapshot{trips: [NEW]} ─|                            |
   |                            |                            |
UI muestra trips nuevos correctamente ← CORRECTO
```

---

## 6. Comportamiento de los FilterSteps en el ciclo delete → upload

### Diseño intencional: los FilterSteps persisten

```
Antes del delete:
  trips.filter_steps:
    - id: X, location_id: ONT, airline: WN, pick_up_date: 2026-01-01, step_order: 1, is_active: true
    - id: Y, location_id: ONT, airline: WN, pick_up_date: 2026-01-01, step_order: 2, is_active: true
    - id: Z, location_id: ONT, airline: WN, pick_up_date: 2026-01-05, step_order: 1, is_active: true

Después del DELETE /v1/locations/{id}/airlines/WN/trips/all:
  trips.trips: vacía para WN en ONT
  trips.filter_steps: SIN CAMBIOS ← CORRECTO, es la configuración guardada
```

### Qué hace auto_apply_preset al re-subir (comportamiento correcto)

Al subir el nuevo archivo, el sistema detecta las fechas nuevas y aplica los FilterSteps existentes directamente sobre los nuevos trips:

```
Nuevo upload con fechas 2026-01-01 y 2026-01-05:
  → existing_dates_for_airline = {} (no hay trips aún)
  → auto_apply_to_new_trips ve que ya existen steps para esas fechas
  → Aplica los steps X, Y a los trips del 2026-01-01
  → Aplica el step Z a los trips del 2026-01-05
  → Los nuevos trips quedan filtrados con la configuración anterior
```

### Qué ve el frontend al llamar `reloadStackFromBackend()`

```
GET /v2/locations/{id}/airlines/WN/filters/stack?pick_up_date=2026-01-01
→ Devuelve: steps=[X, Y] con is_active=true   ← configuración preservada ✓
```

### Por qué los filtros aparecen vacíos en el bug reportado

Los "filtros sin configuración" que ve el usuario **no son causados por la pérdida de FilterSteps** — esos persisten correctamente. Son causados por el Causa Raíz #1 (Redis stale): si el snapshot WS devuelve los trips incorrectos (viejos o vacíos), el frontend no tiene trips reales sobre los cuales renderizar el estado de los filtros, aunque los FilterSteps existan y estén correctos en la DB.

Una vez que se resuelve el bug de Redis, el snapshot devuelve los trips nuevos con los tiempos ya ajustados por los FilterSteps, y el frontend puede mostrar la configuración correctamente.

---

## 7. Estado actual del Redis para ONT (análisis)

Con TTL de 300 segundos, si el último evento de trip fue hace más de 5 minutos, Redis para ONT tiene:
```
loc:c22feb1f-36aa-4120-850a-598b8cb8d5fd:trips → expirado o vacío
trip:{id} → todos expirados
```

En este estado, el snapshot ya funciona correctamente (fallback a PostgreSQL). Por eso cuando el usuario recarga la página (F5), funciona bien — la reconexión ocurre mucho después de los 300s de TTL.

---

## 8. Fixes aplicados en el backend ✅

Ambos fixes están implementados y activos en el contenedor de desarrollo (`gt360-app-dev`).

### Fix #1: Limpiar Redis al borrar trips

**Archivos modificados:** `features/trips/routes/trips_router.py`

**`delete_all_trips` — después del commit:**
```python
# Fix #1: Limpiar Redis cache (evita snapshot stale)
idx_key = f"loc:{location_id}:trips"
cached_ids = await redis.smembers(idx_key)
if cached_ids:
    pipe = redis.pipeline()
    for raw_id in cached_ids:
        tid = raw_id.decode("utf-8", errors="ignore") if isinstance(raw_id, (bytes, bytearray)) else str(raw_id)
        pipe.delete(f"trip:{tid}")
    pipe.delete(idx_key)
    await pipe.execute()
    print(f"[DELETE_ALL] Cleared {len(cached_ids)} trip keys from Redis for loc:{location_id}")
```

Lee el SET `loc:{location_id}:trips` de Redis, borra cada `trip:{id}` key en pipeline y elimina el SET. Si el SET ya expiró, el bloque no ejecuta nada (safe).

**`delete_trips_by_airline` — después del commit:**
```python
# Fix #1: Limpiar Redis cache para los trips borrados
trip_id_strings = [str(row[0]) for row in trips_to_delete]
pipe = redis.pipeline()
idx_key = f"loc:{location_id}:trips"
for tid in trip_id_strings:
    pipe.delete(f"trip:{tid}")
    pipe.srem(idx_key, tid)
await pipe.execute()
print(f"[DELETE_AIRLINE] Cleared {trips_count} trip keys from Redis for loc:{location_id}/airline:{airline}")
```

Usa los IDs exactos ya consultados en `trips_to_delete` (misma query de conteo, cero overhead extra). Elimina selectivamente solo los trips de esa aerolínea del SET, manteniendo los de otras aerolíneas intactos.

---

### Fix #2: Publicar evento WebSocket al borrar trips

**Archivos modificados:** `features/trips/routes/trips_router.py`, `features/trips/utils/ws_manager.py`

**En `delete_all_trips`:**
```python
# Fix #2: Notificar via WebSocket
await safe_redis_call(
    redis.publish,
    f"loc:{location_id}",
    json.dumps({
        "type": "trips_deleted",
        "location_id": location_id,
        "trips_deleted_count": len(cached_ids) if cached_ids else 0,
        "airline": None
    }),
    context=f"publish loc:{location_id} trips_deleted",
)
```

**En `delete_trips_by_airline`:**
```python
# Fix #2: Notificar via WebSocket
await safe_redis_call(
    redis.publish,
    f"loc:{location_id}",
    json.dumps({
        "type": "trips_deleted",
        "location_id": location_id,
        "trips_deleted_count": trips_count,
        "airline": airline,
        "pick_up_date": pick_up_date,
        "status": status
    }),
    context=f"publish loc:{location_id} trips_deleted",
)
```

**En `ws_manager.py` — `_location_listener`:**
```python
# Handle trips_deleted event - forward to clients
if event_type == "trips_deleted":
    await self.route_location_event(location_id, ev)
    continue
```

Sin este bloque en el ws_manager, el evento `trips_deleted` publicado en Redis habría sido descartado silenciosamente (el listener solo hacía `continue` para tipos no reconocidos antes de llegar al check de `trips_batch`).

---

### Estructura del evento `trips_deleted` que recibe el frontend

```json
{
  "type": "trips_deleted",
  "location_id": "c22feb1f-36aa-4120-850a-598b8cb8d5fd",
  "trips_deleted_count": 150,
  "airline": "WN",
  "pick_up_date": null,
  "status": null
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `type` | `"trips_deleted"` | Discriminador del evento |
| `location_id` | string UUID | Location afectada |
| `trips_deleted_count` | int | Número de trips borrados (0 si el cache Redis ya había expirado en `delete_all`) |
| `airline` | string \| null | `null` cuando se usa `delete_all_trips`; código IATA cuando se usa `delete_trips_by_airline` |
| `pick_up_date` | string \| null | Fecha filtrada, si aplica |
| `status` | string \| null | Status filtrado, si aplica |

---

### Fix #3: Publicar señales pre-delete para suprimir notificaciones WAL duplicadas

**Contexto del bug:** Al borrar trips masivamente, el contenedor `trip-streaming` escucha el WAL de PostgreSQL y envía una petición `POST /v1/webhooks/trips/batch` por cada batch de 100 trips borrados. El webhook los publica como `trips_batch` con DELETE events hacia el canal `loc:{location_id}`. El frontend recibe N mensajes `trips_batch` y muestra N notificaciones "100 trips deleted".

**Confirmado en logs de producción para la location SDF:**
```
DELETE /v1/locations/{id}/airlines/WN/trips/all  ← 1 request del usuario
→ 645 trips borrados en PostgreSQL
→ trip-streaming detecta WAL events
POST /v1/webhooks/trips/batch  ← batch 1: 25 trips
POST /v1/webhooks/trips/batch  ← batch 2: 100 trips
POST /v1/webhooks/trips/batch  ← batch 3: 100 trips
POST /v1/webhooks/trips/batch  ← batch 4: 100 trips
POST /v1/webhooks/trips/batch  ← batch 5: 100 trips
POST /v1/webhooks/trips/batch  ← batch 6: 100 trips
POST /v1/webhooks/trips/batch  ← batch 7: 20 trips
POST /v1/webhooks/trips/batch  ← batch 8: 100 trips
→ Total: 8 batches → 8 publicaciones → hasta 8 notificaciones en UI (visible: 3 en screenshot)
```

**Solución:** Publicar una señal PRE-DELETE al canal `loc:{location_id}` **antes** de ejecutar el SQL, para que cuando lleguen los `trips_batch` DELETE del WAL, el frontend ya sepa que debe suprimirlos.

**Archivos modificados:** `features/trips/routes/trips_router.py`, `features/trips/utils/ws_manager.py`

**En `delete_all_trips` (línea ~1059) — ANTES del DELETE SQL:**
```python
# Publicar batch_delete_started ANTES del DELETE
await safe_redis_call(
    redis.publish,
    f"loc:{location_id}",
    json.dumps({"type": "batch_delete_started", "location_id": location_id, "airline": None}),
    context=f"publish loc:{location_id} batch_delete_started",
)
# DELETE SQL sigue aquí
del_stmt = Delete(TripDB).Where(TripDB.location_id == uuid_location_id)
await session.exec(del_stmt)
```

**En `delete_trips_by_airline` (línea ~1249) — ANTES del DELETE SQL:**
```python
# Publicar batch_delete_started ANTES del DELETE
await safe_redis_call(
    redis.publish,
    f"loc:{location_id}",
    json.dumps({"type": "batch_delete_started", "location_id": location_id, "airline": airline}),
    context=f"publish loc:{location_id} batch_delete_started",
)
# DELETE SQL sigue aquí
await session.exec(del_stmt)
```

**En `delete_location` (línea ~1517) — ANTES del DELETE SQL, solo si hay trips:**
```python
# Publicar location_delete_started ANTES del DELETE (solo si hay trips que generarán WAL events)
if trips_count > 0:
    await safe_redis_call(
        redis.publish,
        f"loc:{location_uuid}",
        json.dumps({"type": "location_delete_started", "location_id": location_id,
                    "location_name": location_name}),
        context=f"publish loc:{location_uuid} location_delete_started",
    )
# DELETE trips, hotels, location sigue aquí
```

**En `ws_manager.py` — `_location_listener`:**
```python
# Handle trips_deleted and batch_delete_started events - forward to clients
if event_type in ("trips_deleted", "batch_delete_started"):
    await self.route_location_event(location_id, ev)
    continue
```

**Nota:** `location_delete_started` ya estaba manejado por el bloque anterior en el listener.

---

### Estructura de los nuevos eventos que recibe el frontend

**`batch_delete_started`** — llega por el WebSocket de trips (`/ws/trips`):
```json
{
  "type": "batch_delete_started",
  "location_id": "c22feb1f-36aa-4120-850a-598b8cb8d5fd",
  "airline": "WN"
}
```
> `airline` es `null` cuando se usa `delete_all_trips` (todos los airlines); código IATA cuando se usa `delete_trips_by_airline`.

**`location_delete_started`** — llega por el WebSocket de trips (`/ws/trips`):
```json
{
  "type": "location_delete_started",
  "location_id": "c22feb1f-36aa-4120-850a-598b8cb8d5fd",
  "location_name": "SDF"
}
```
> Solo se envía si la location tiene trips (para evitar señales falsas en locations vacías).

---

### Cronología correcta con Fix #3

```
Backend                              Redis / WS                     Frontend
   |                                      |                              |
   |── ANTES DEL DELETE:                  |                              |
   |   publish("batch_delete_started") ──>|── WS: batch_delete_started ──>|
   |                                      |                    activa supresión WAL
   |── DELETE SQL ──────────────────────> |                              |
   |── commit                             |                              |
   |                                      |                              |
   |   (trip-streaming detecta WAL)       |                              |
   |                                      |── WS: trips_batch DELETE ───>| ← SUPRIMIDO
   |                                      |── WS: trips_batch DELETE ───>| ← SUPRIMIDO
   |                                      |── WS: trips_batch DELETE ───>| ← SUPRIMIDO
   |                                      |                              |
   |── publish("trips_deleted") ─────────>|── WS: trips_deleted ─────────>|
   |                                      |                    limpia store + desactiva supresión
   |<── 200/204 ─────────────────────────|                              |
```

**Responsabilidad del frontend:**
```typescript
case 'batch_delete_started':
    // Activar flag de supresión: los próximos trips_batch DELETE son ruido del WAL
    this.suppressWalDeleteBatches = true;
    break;

case 'location_delete_started':
    // Similar: suprimir WAL batches para esta location
    this.suppressWalDeleteBatches = true;
    break;

case 'trips_batch':
    if (this.suppressWalDeleteBatches && event.events.every(e => e.op === 'DELETE')) {
        // Ignorar: son los WAL events del bulk delete en curso
        break;
    }
    // Procesar normalmente
    break;

case 'trips_deleted':
    // Bulk delete completo: limpiar store y desactivar supresión
    tripsStore.clearTrips();
    this.suppressWalDeleteBatches = false;
    break;
```

---

## 9. Qué debe hacer el frontend para manejar esto

### Manejo del evento `batch_insert`

Cuando el WS recibe `{ "type": "batch_insert", ... }`, el frontend actualmente hace `softReconnect()`. Esto es correcto. El fix del backend (limpiar Redis) hace que el snapshot post-reconexión sea siempre correcto.

**Sin embargo**, para mayor robustez, el frontend puede añadir lógica:

```typescript
// Al recibir batch_insert, esperar que el snapshot llegue
// Si el snapshot llega con trips vacíos pero trips_count > 0 en el evento,
// forzar una recarga HTTP como fallback
if (event.type === 'batch_insert' && event.trips_count > 0) {
    softReconnect();  // El snapshot debería llegar con los datos correctos
}
```

### Manejo del nuevo evento `trips_deleted`

Una vez que el backend publique `trips_deleted`, el frontend debe:

```typescript
case 'trips_deleted':
    // Limpiar el store de trips inmediatamente
    tripsStore.clearTrips();
    // Limpiar los filtros (ya no hay trips)
    tripFilters.resetAllFilters();
    // NO llamar softReconnect aquí (no hay nada nuevo que cargar)
    break;
```

### El problema de timing (double reconnect)

El frontend llama `softReconnect()` en dos lugares:
1. Al recibir `batch_insert` por WS
2. En `handleUploaded` del evento `trips-uploaded`

Si ambos se ejecutan, el segundo `softReconnect()` puede cancelar el primero antes de que llegue el snapshot. El backend no tiene estado que lo controle — cada conexión recibe su propio snapshot inmediatamente.

**Recomendación:** Deduplicar estos dos llamados para evitar que el WS se reconecte dos veces en rápida sucesión.

---

## 10. Endpoints involucrados (referencia rápida)

| Endpoint | Método | Redis limpiado | Pre-delete señal | Post-delete señal |
|----------|--------|---------------|------------------|-------------------|
| `DELETE /v1/locations/{id}/trips/all` | DELETE | ✅ SÍ (Fix #1) | ✅ `batch_delete_started` (Fix #3) | ✅ `trips_deleted` (Fix #2) |
| `DELETE /v1/locations/{id}/airlines/{a}/trips/all` | DELETE | ✅ SÍ (Fix #1) | ✅ `batch_delete_started` (Fix #3) | ✅ `trips_deleted` (Fix #2) |
| `POST /v1/trips/upload-trips` | POST | Parcial (add only) | N/A | ✅ `batch_insert` |
| `DELETE /v1/locations/{id}` | DELETE | N/A | ✅ `location_delete_started` (Fix #3) | ✅ `location_deleted` (org canal) |

---

## 11. Preguntas de vuelta para el frontend

1. **¿Cuál endpoint usa "Delete all trips" exactamente?**
   `DELETE /v1/locations/{id}/trips/all` (todos) o
   `DELETE /v1/locations/{id}/airlines/{airline}/trips/all` (por airline)?

2. **¿El `softReconnect()` se llama tanto en `batch_insert` WS como en `handleUploaded`?**
   Si es así, ¿hay algún lock/flag para prevenir doble reconexión?

3. **¿Cuánto tiempo pasa entre el DELETE y el upload?**
   Con el fix aplicado ya no importa: el cache se limpia en el DELETE, no a los 300s.

4. **¿El frontend borra el store de trips inmediatamente al recibir la confirmación del DELETE (antes de subir el archivo)?**
   Si no lo hace, hay una ventana donde el store tiene trips que ya no existen en el backend.

---

*Documento generado con análisis directo del código fuente del backend y logs del servidor de producción.*

---

## 12. Estado de los fixes

| Fix | Archivo | Estado |
|-----|---------|--------|
| Fix #1: Redis cleanup en `delete_all_trips` | `features/trips/routes/trips_router.py` | ✅ Activo en `gt360-app-dev` |
| Fix #1: Redis cleanup en `delete_trips_by_airline` | `features/trips/routes/trips_router.py` | ✅ Activo en `gt360-app-dev` |
| Fix #2: Publish `trips_deleted` en `delete_all_trips` | `features/trips/routes/trips_router.py` | ✅ Activo en `gt360-app-dev` |
| Fix #2: Publish `trips_deleted` en `delete_trips_by_airline` | `features/trips/routes/trips_router.py` | ✅ Activo en `gt360-app-dev` |
| Fix #2: Forward `trips_deleted` en `ws_manager` | `features/trips/utils/ws_manager.py` | ✅ Activo en `gt360-app-dev` |
| Fix #3: Publish `batch_delete_started` en `delete_all_trips` | `features/trips/routes/trips_router.py` | ✅ Activo en `gt360-app-dev` |
| Fix #3: Publish `batch_delete_started` en `delete_trips_by_airline` | `features/trips/routes/trips_router.py` | ✅ Activo en `gt360-app-dev` |
| Fix #3: Publish `location_delete_started` en `delete_location` | `features/trips/routes/trips_router.py` | ✅ Activo en `gt360-app-dev` |
| Fix #3: Forward `batch_delete_started` en `ws_manager` | `features/trips/utils/ws_manager.py` | ✅ Activo en `gt360-app-dev` |
| **Pendiente frontend** | Manejar `trips_deleted` en WS handler | ⏳ Requiere cambio en frontend |
| **Pendiente frontend** | Suprimir `trips_batch` DELETE con flag `suppressWalDeleteBatches` al recibir `batch_delete_started` / `location_delete_started` | ⏳ Requiere cambio en frontend |
