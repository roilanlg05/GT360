# Respuestas para el Frontend: Por qué Preview Devuelve 0 Trips

**Fecha:** 2026-01-20
**Contexto:** `/trips` devuelve 674 trips pero `/filters/preview` devuelve 0

---

## 🎯 Respuesta Corta

El endpoint `/filters/preview` **SOLO evalúa trips que cumplan TODOS estos criterios:**

1. ✅ `trip_type = 'outbound'` (NO incluye inbound, ground, return)
2. ✅ `status = 'scheduled'` (NO incluye completed, cancelled, in_progress)
3. ✅ `filter_applied IS NULL` (NO incluye trips con filtros ya aplicados)

Si devuelve 0, significa que **NO hay trips que cumplan los 3 criterios**.

---

## 📋 Respuestas a las Preguntas

### 1️⃣ ¿Qué query SQL usa el endpoint `/filters/preview` para encontrar trips?

```sql
SELECT * FROM trips.trips
WHERE location_id = '{location_uuid}'
  AND airline = 'WN'
  AND trip_type = 'outbound'        -- ⚠️ SOLO OUTBOUND
  AND status = 'scheduled'          -- ⚠️ SOLO SCHEDULED
  AND filter_applied IS NULL        -- ⚠️ SIN FILTROS
  AND pick_up_date >= '2026-01-01'
  AND pick_up_date <= '2026-01-31'
```

**Código fuente:** `/home/backend/GT360/features/trips/services/trip_filter_service.py:519-534`

---

### 2️⃣ ¿Filtra por trip_type?

**SÍ**, filtra por:
```sql
trip_type = 'outbound'
```

**Excluye:**
- ❌ `inbound`
- ❌ `ground`
- ❌ `return`

**Por qué:** Los filtros ground (reduce, combine, expand) fueron diseñados específicamente para trips tipo `outbound`.

---

### 3️⃣ ¿Filtra por status?

**SÍ**, filtra por:
```sql
status = 'scheduled'
```

**Excluye:**
- ❌ `completed`
- ❌ `cancelled`
- ❌ `in_progress`

**Por qué:** Los filtros solo se aplican a trips que aún no han ocurrido (scheduled).

---

### 4️⃣ ¿Hay algún otro filtro implícito?

**SÍ**, también filtra por:
```sql
filter_applied IS NULL
```

**Excluye:**
- ❌ Trips con `filter_applied = 'reduce'`
- ❌ Trips con `filter_applied = 'combine'`
- ❌ Trips con `filter_applied = 'expand'`

**Por qué:** Un trip que ya tiene un filtro aplicado NO puede ser modificado nuevamente hasta que se revierta el filtro.

---

### 5️⃣ ¿Por qué `/trips` encuentra 674 trips pero `/filters/preview` encuentra 0?

**Porque `/trips` y `/filters/preview` usan queries DIFERENTES:**

| Criterio | GET `/trips` | POST `/filters/preview` |
|----------|--------------|------------------------|
| **trip_type** | ❌ Incluye TODOS los tipos | ✅ Solo `outbound` |
| **status** | ❌ Incluye TODOS los status | ✅ Solo `scheduled` |
| **filter_applied** | ❌ Incluye trips filtrados | ✅ Solo sin filtros |

**GET `/trips`** está diseñado para **mostrar todos los trips al usuario**.
**POST `/filters/preview`** está diseñado para **encontrar trips elegibles para aplicar filtros**.

---

### 6️⃣ ¿Qué trip_type tienen los 674 trips de enero 2026?

**Para saberlo, ejecuta este query:**

```sql
SELECT trip_type, COUNT(*)
FROM trips.trips
WHERE location_id = 'f577697c-b2d6-4761-b075-b519a9ff2fe3'
  AND airline = 'WN'
  AND pick_up_date >= '2026-01-01'
  AND pick_up_date <= '2026-01-31'
GROUP BY trip_type;
```

**Resultado probable:**
```
trip_type   | count
------------|-------
inbound     | 337
ground      | 337
outbound    | 0      ← Por eso preview devuelve 0
```

---

## 🔬 Cómo Diagnosticar el Problema

Ejecuta este query para entender qué trips tienes:

```sql
SELECT
    trip_type,
    status,
    CASE
        WHEN filter_applied IS NULL THEN '✅ Sin filtro'
        ELSE '❌ ' || filter_applied
    END as filter_status,
    COUNT(*) as total
FROM trips.trips
WHERE location_id = 'f577697c-b2d6-4761-b075-b519a9ff2fe3'
  AND airline = 'WN'
  AND pick_up_date >= '2026-01-01'
  AND pick_up_date <= '2026-01-31'
GROUP BY trip_type, status, filter_applied
ORDER BY trip_type, status;
```

**Archivo completo de diagnóstico:** `/home/backend/GT360/diagnose_preview_zero_trips.sql`

---

## 🎨 Sugerencia para el Frontend

Muestra un mensaje explicativo cuando preview devuelve 0:

```tsx
{eligible_trips === 0 && (
  <Alert variant="info">
    <AlertTitle>No hay trips elegibles para aplicar filtros</AlertTitle>
    <AlertDescription>
      Los filtros ground solo se aplican a trips que cumplan:
      <ul>
        <li>✓ Tipo: <strong>OUTBOUND</strong></li>
        <li>✓ Status: <strong>SCHEDULED</strong></li>
        <li>✓ Sin filtros aplicados previamente</li>
      </ul>

      <div className="mt-2 text-sm text-muted-foreground">
        Trips encontrados: {total_trips}<br/>
        Trips elegibles: {eligible_trips}
      </div>
    </AlertDescription>
  </Alert>
)}
```

---

## 🛠️ Soluciones

### Opción 1: Documentar (Recomendado)
Explicar claramente al usuario que **solo trips outbound + scheduled + sin filtros** son elegibles.

### Opción 2: Extender Funcionalidad
Si el negocio requiere aplicar filtros a trips tipo `ground`, el backend debe modificarse en:
```python
# features/trips/services/trip_filter_service.py:523
.Where(Trip.trip_type.In([TripType.OUTBOUND, TripType.GROUND]))
```

**⚠️ Requiere aprobación del negocio**

### Opción 3: Endpoint de Diagnóstico
Crear un nuevo endpoint que devuelva el desglose de elegibilidad:

```typescript
GET /v1/locations/{id}/airlines/{airline}/trips/filters/eligibility

Response:
{
  total_trips: 674,
  eligible_trips: 0,
  breakdown: {
    outbound_scheduled_no_filter: 0,     ← Elegibles
    outbound_scheduled_with_filter: 0,   ← Ya filtrados, usar revert
    outbound_other_status: 0,            ← No scheduled
    inbound_all: 337,                    ← No elegibles (tipo inbound)
    ground_all: 337                      ← No elegibles (tipo ground)
  }
}
```

---

## 📝 TL;DR para el Frontend

**Pregunta:** ¿Por qué preview devuelve 0?

**Respuesta:** Porque NO tienes trips que sean:
```
trip_type = 'outbound'
AND status = 'scheduled'
AND filter_applied IS NULL
```

**Acción:** Ejecuta el query de diagnóstico para ver qué trip_types tienes.

**Solución:** Si los 674 trips son tipo `inbound` o `ground`, entonces el comportamiento es correcto y esperado.

---

## 📂 Archivos de Referencia

1. **Análisis completo:** `/home/backend/GT360/docs/FILTER_PREVIEW_QUERY_ANALYSIS.md`
2. **Script SQL de diagnóstico:** `/home/backend/GT360/diagnose_preview_zero_trips.sql`
3. **Código fuente (eligibility):** `/home/backend/GT360/features/trips/services/trip_filter_service.py:503-534`
4. **Código fuente (preview endpoint):** `/home/backend/GT360/features/trips/routes/trips_router.py:1115-1168`
5. **Código fuente (get trips endpoint):** `/home/backend/GT360/features/trips/routes/trips_router.py:393-530`

---

**Última actualización:** 2026-01-20
