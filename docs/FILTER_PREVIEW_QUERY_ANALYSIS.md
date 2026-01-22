# Análisis: Diferencia entre `/trips` y `/filters/preview`

**Fecha:** 2026-01-20
**Contexto:** Frontend reporta que `/trips` devuelve 674 trips pero `/filters/preview` devuelve 0 trips para el mismo location/airline/fecha

---

## 🔍 Respuestas a las Preguntas del Frontend

### 1. Query SQL del `/filters/preview` endpoint

**Archivo:** `/home/backend/GT360/features/trips/services/trip_filter_service.py` (líneas 503-534)

```python
async def _get_eligible_trips(
    self,
    location_id: UUID,
    airline: str,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[Trip]:
    """
    Get trips eligible for filtering.

    Criteria:
    - trip_type = OUTBOUND only
    - status = SCHEDULED only
    - Matches location_id and airline
    - Optionally filters by pick_up_date range
    """
    query = (
        Select(Trip)
        .Where(Trip.location_id == location_id)
        .Where(Trip.airline == airline)
        .Where(Trip.trip_type == TripType.OUTBOUND)       # ✅ FILTRO 1
        .Where(Trip.status == TripStatus.SCHEDULED)       # ✅ FILTRO 2
        .Where(Trip.filter_applied == None)               # ✅ FILTRO 3
    )

    # Apply date filters if provided
    if date_from:
        query = query.Where(Trip.pick_up_date >= date_from)
    if date_to:
        query = query.Where(Trip.pick_up_date <= date_to)

    return await self.session.exec(query).all()
```

**Traducido a SQL:**
```sql
SELECT * FROM trips.trips
WHERE location_id = '{location_uuid}'
  AND airline = 'WN'
  AND trip_type = 'outbound'           -- ⚠️ IMPORTANTE
  AND status = 'scheduled'             -- ⚠️ IMPORTANTE
  AND filter_applied IS NULL           -- ⚠️ IMPORTANTE
  AND pick_up_date >= '2026-01-01'
  AND pick_up_date <= '2026-01-31'
```

---

### 2. Query SQL del `/trips` endpoint

**Archivo:** `/home/backend/GT360/features/trips/routes/trips_router.py` (líneas 393-530)

```python
@router.get("/v1/locations/{location_id}/trips")
async def get_trips(
    location_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
    pick_up_date_from: Optional[str] = None,
    pick_up_date_to: Optional[str] = None,
    airline: Optional[str] = None,
    trip_type: Optional[str] = None,  # ⚠️ OPCIONAL, no filtrado por defecto
    ...
):
    # Construir condiciones dinámicas según parámetros opcionales
    filters = [TripDB.location_id == location_uuid]

    # Solo filtra por trip_type SI el usuario lo pasa como query param
    if trip_type:
        filters.append(TripDB.trip_type == trip_type)

    # NO filtra por status
    # NO filtra por filter_applied

    if pick_up_date_from_obj:
        filters.append(TripDB.pick_up_date >= pick_up_date_from_obj)
    if pick_up_date_to_obj:
        filters.append(TripDB.pick_up_date <= pick_up_date_to_obj)
    if airline:
        filters.append(TripDB.airline.ilike(f"%{airline}%"))
```

**Traducido a SQL:**
```sql
SELECT * FROM trips.trips
WHERE location_id = '{location_uuid}'
  AND airline ILIKE '%WN%'
  AND pick_up_date >= '2026-01-01'
  AND pick_up_date <= '2026-01-31'
-- ❌ NO filtra por trip_type (incluye inbound, outbound, ground, return)
-- ❌ NO filtra por status (incluye scheduled, cancelled, completed, etc.)
-- ❌ NO filtra por filter_applied (incluye trips con filtros ya aplicados)
```

---

## 🚨 DIFERENCIAS CRÍTICAS

| Aspecto | `/trips` | `/filters/preview` |
|---------|----------|-------------------|
| **trip_type** | ❌ NO filtra (todos los tipos) | ✅ Solo `OUTBOUND` |
| **status** | ❌ NO filtra (todos los status) | ✅ Solo `SCHEDULED` |
| **filter_applied** | ❌ NO filtra (incluye filtrados) | ✅ Solo trips SIN filtros (`filter_applied IS NULL`) |
| **airline** | ✅ ILIKE (case insensitive) | ✅ Exact match |
| **Uso** | Mostrar todos los trips al usuario | Encontrar trips ELEGIBLES para aplicar filtros |

---

## 📊 Diagnóstico: Por Qué Preview Devuelve 0

Dado que `/trips` devuelve 674 trips pero `/filters/preview` devuelve 0, las causas posibles son:

### Causa 1: Trips NO son tipo `outbound`
Los 674 trips incluyen otros tipos: `inbound`, `ground`, `return`

**Verificación:**
```sql
SELECT trip_type, COUNT(*)
FROM trips.trips
WHERE location_id = 'f577697c-b2d6-4761-b075-b519a9ff2fe3'
  AND airline = 'WN'
  AND pick_up_date >= '2026-01-01'
  AND pick_up_date <= '2026-01-31'
GROUP BY trip_type;
```

**Resultado esperado:**
```
trip_type   | count
------------|-------
inbound     | 337
ground      | 337
outbound    | 0     ← Por eso preview devuelve 0
```

### Causa 2: Trips NO están en status `scheduled`
Los trips están en otro status: `completed`, `cancelled`, `in_progress`

**Verificación:**
```sql
SELECT status, COUNT(*)
FROM trips.trips
WHERE location_id = 'f577697c-b2d6-4761-b075-b519a9ff2fe3'
  AND airline = 'WN'
  AND pick_up_date >= '2026-01-01'
  AND pick_up_date <= '2026-01-31'
  AND trip_type = 'outbound'
GROUP BY status;
```

### Causa 3: Trips YA tienen filtros aplicados
Los trips tienen `filter_applied` != NULL

**Verificación:**
```sql
SELECT
    filter_applied,
    COUNT(*)
FROM trips.trips
WHERE location_id = 'f577697c-b2d6-4761-b075-b519a9ff2fe3'
  AND airline = 'WN'
  AND pick_up_date >= '2026-01-01'
  AND pick_up_date <= '2026-01-31'
  AND trip_type = 'outbound'
  AND status = 'scheduled'
GROUP BY filter_applied;
```

**Resultado esperado:**
```
filter_applied | count
---------------|-------
reduce         | 50
combine        | 30
NULL           | 0     ← Por eso preview devuelve 0
```

---

## ✅ Query de Diagnóstico Completo

Ejecuta este query para ver el desglose completo:

```sql
SELECT
    trip_type,
    status,
    CASE
        WHEN filter_applied IS NULL THEN 'no_filter'
        ELSE filter_applied
    END as filter_status,
    COUNT(*) as total
FROM trips.trips
WHERE location_id = 'f577697c-b2d6-4761-b075-b519a9ff2fe3'
  AND airline = 'WN'
  AND pick_up_date >= '2026-01-01'
  AND pick_up_date <= '2026-01-31'
GROUP BY trip_type, status, filter_applied
ORDER BY trip_type, status, filter_applied;
```

---

## 🔧 Soluciones Propuestas

### Opción 1: Documentar Restricciones (Recomendado)
Explicar claramente al usuario que **solo trips OUTBOUND + SCHEDULED + SIN FILTROS** son elegibles para filtros.

**Frontend debe mostrar:**
```
⚠️ No hay trips elegibles para filtros

Criterios de elegibilidad:
✓ Tipo: OUTBOUND
✓ Status: SCHEDULED
✓ Sin filtros aplicados previamente

Trips encontrados: 674
Trips elegibles: 0
```

### Opción 2: Agregar Endpoint de Diagnóstico
Crear un endpoint que devuelva el desglose de por qué los trips NO son elegibles.

```python
@router.get("/v1/locations/{location_id}/airlines/{airline}/trips/filters/eligibility")
async def check_eligibility(...):
    """
    Returns:
    {
        "total_trips": 674,
        "eligible_trips": 0,
        "breakdown": {
            "inbound": 337,
            "ground": 337,
            "outbound_scheduled_no_filter": 0,
            "outbound_scheduled_with_filter": 0,
            "outbound_other_status": 0
        }
    }
    """
```

### Opción 3: Permitir Filtros en Ground Trips (Cambio de Lógica)
Si el negocio lo permite, modificar `_get_eligible_trips()` para incluir trips tipo `ground`.

**⚠️ Requiere validación del negocio**

```python
.Where(Trip.trip_type.In([TripType.OUTBOUND, TripType.GROUND]))
```

---

## 📝 Respuestas Directas a las Preguntas

### 1. ¿Qué query SQL usa `/filters/preview`?
```sql
SELECT * FROM trips.trips
WHERE location_id = '{uuid}'
  AND airline = 'WN'
  AND trip_type = 'outbound'
  AND status = 'scheduled'
  AND filter_applied IS NULL
  AND pick_up_date >= '2026-01-01'
  AND pick_up_date <= '2026-01-31'
```

### 2. ¿Filtra por trip_type?
✅ **SÍ** - Solo `OUTBOUND`

### 3. ¿Filtra por status?
✅ **SÍ** - Solo `SCHEDULED`

### 4. ¿Hay algún otro filtro implícito?
✅ **SÍ** - `filter_applied IS NULL` (trips que NO tienen filtros aplicados)

### 5. ¿Por qué `/trips` encuentra 674 pero `/filters/preview` encuentra 0?
**Porque usan queries diferentes:**
- `/trips`: Devuelve TODOS los trips (inbound, ground, outbound, cualquier status, con/sin filtros)
- `/filters/preview`: Solo devuelve trips ELEGIBLES (outbound + scheduled + sin filtros)

**Los 674 trips probablemente son:**
- 337 trips tipo `inbound`
- 337 trips tipo `ground`
- 0 trips tipo `outbound` + `scheduled` + sin filtros

### 6. ¿Qué muestra el log del backend?
El log mostrará:
```
[FILTER] Eligible trips found: 0 for location={uuid}, airline=WN
```

---

## 🎯 Conclusión

**El comportamiento es correcto según el diseño actual.**

Los filtros ground (reduce, combine, expand) fueron diseñados SOLO para trips:
- Tipo: `OUTBOUND`
- Status: `SCHEDULED`
- Sin filtros previamente aplicados

Si los 674 trips son de tipo `inbound` o `ground`, entonces **NO son elegibles** y el preview correctamente devuelve 0.

**Acción recomendada:** Ejecutar el query de diagnóstico para confirmar la distribución de trip_types.

---

## 📎 Archivos Relevantes

1. **Query eligibility:** `/home/backend/GT360/features/trips/services/trip_filter_service.py:503-534`
2. **Preview endpoint:** `/home/backend/GT360/features/trips/routes/trips_router.py:1115-1168`
3. **Get trips endpoint:** `/home/backend/GT360/features/trips/routes/trips_router.py:393-530`

---

**Última actualización:** 2026-01-20
