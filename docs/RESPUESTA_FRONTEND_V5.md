# Respuesta: Pregunta sobre enabled: false en V5

**Fecha:** 2026-01-20
**Para:** Frontend Team
**De:** Backend Team

---

## Pregunta del Frontend

> **Cuando envío `{reduce: {enabled: false}, combine: {enabled: true}}`, y ya existe `reduce_applied=TRUE`, ¿qué pasa con `reduce_applied`?**

---

## Respuesta: Opción A ✅

**`reduce_applied` se vuelve FALSE**

### Comportamiento en V5

En la versión V5 desplegada ahora, cuando envías:

```json
{
  "reduce": {"enabled": false},
  "combine": {"enabled": true, "min_gap_minutes": 10}
}
```

**El backend hace:**

1. ✅ **Desactiva REDUCE:** Marca `reduce_applied = FALSE`
2. ✅ **Activa COMBINE:** Aplica el filtro y marca `combine_applied = TRUE`
3. ✅ **Ajusta pick_up_time:** Revierte a original y re-aplica solo COMBINE

---

## Ejemplo Completo

### Escenario Inicial

```typescript
// Trip antes del request
{
  id: "trip-123",
  pick_up_time: "09:35",           // Con reduce + combine
  original_pick_up_time: "10:00",  // Original sin filtros
  reduce_applied: true,
  combine_applied: true,
  expand_applied: false
}
```

### Request Frontend

```typescript
POST /v1/locations/{location_id}/airlines/WN/trips/filters/apply

{
  "reduce": {"enabled": false},    // ← Desactivar REDUCE
  "combine": {"enabled": true, "min_gap_minutes": 10, "max_gap_minutes": 20}
}
```

### Resultado en Backend

```typescript
// Trip después del request
{
  id: "trip-123",
  pick_up_time: "09:50",           // Solo COMBINE ahora
  original_pick_up_time: "10:00",  // Mantiene referencia original
  reduce_applied: false,           // ✅ DESACTIVADO
  combine_applied: true,           // ✅ MANTIENE ACTIVO
  expand_applied: false
}
```

---

## Semántica Completa de `enabled`

| Valor en Request | Comportamiento Backend | Estado Final |
|------------------|------------------------|--------------|
| `enabled: true` | Aplica filtro + marca TRUE | `xxx_applied: true` |
| `enabled: false` | NO aplica + marca FALSE | `xxx_applied: false` |
| Campo omitido | No toca ese filtro | Mantiene estado actual |

---

## Comparación con Opción B (Descartada)

**Opción B decía:** "enabled: false activamente desactiva el filtro"
**Respuesta:** Esto es EXACTAMENTE lo que hace V5. Opción B es la implementación actual.

**Opción A del frontend decía:** "Solo agrega combine, no toca reduce"
**Respuesta:** Esto sería si OMITES el campo reduce (no lo incluyes en el request).

---

## Código Backend (Referencia)

**Archivo:** `features/trips/services/trip_filter_service.py:247-262`

```python
# V5: Set independent filter flags based on config
# enabled: true → TRUE, enabled: false → FALSE, None → don't change
if filters_state['reduce'] is True:
    trip.reduce_applied = True
elif filters_state['reduce'] is False:
    trip.reduce_applied = False  # ← Aquí se desactiva

if filters_state['combine'] is True:
    trip.combine_applied = True
elif filters_state['combine'] is False:
    trip.combine_applied = False

if filters_state['expand'] is True:
    trip.expand_applied = True
elif filters_state['expand'] is False:
    trip.expand_applied = False
```

---

## Ejemplos de Uso

### Ejemplo 1: Desactivar REDUCE, mantener COMBINE

```typescript
// Estado inicial
reduce_applied: true
combine_applied: true

// Request
{
  "reduce": {"enabled": false},
  "combine": {"enabled": true, "min_gap_minutes": 10}
}

// Resultado
reduce_applied: false  // ✅
combine_applied: true  // ✅
```

### Ejemplo 2: Activar solo EXPAND (no tocar reduce/combine)

```typescript
// Estado inicial
reduce_applied: true
combine_applied: true

// Request (OMITE reduce y combine)
{
  "expand": {"enabled": true, "minutes_to_expand": 15}
}

// Resultado
reduce_applied: true   // ✅ Mantiene (no fue especificado)
combine_applied: true  // ✅ Mantiene (no fue especificado)
expand_applied: true   // ✅ Activado
```

### Ejemplo 3: Desactivar TODO

```typescript
// Request
{
  "reduce": {"enabled": false},
  "combine": {"enabled": false},
  "expand": {"enabled": false}
}

// Resultado
reduce_applied: false
combine_applied: false
expand_applied: false
pick_up_time: "10:00"  // Restaurado a original
original_pick_up_time: null
```

---

## Flujo Interno en Backend (V5)

Cuando envías `{reduce: {enabled: false}, combine: {enabled: true}}`:

```
1. Backend detecta: filters_state = {reduce: false, combine: true}

2. Revierte trips a original_pick_up_time

3. Re-aplica solo COMBINE (porque enabled: true)

4. Actualiza flags:
   - reduce_applied = FALSE
   - combine_applied = TRUE

5. Persiste cambios en DB

6. Retorna resultado al frontend
```

---

## ¿Cómo NO Tocar un Filtro?

Si quieres mantener el estado actual de un filtro, **NO lo incluyas** en el request:

```typescript
// Correcto: Solo activa EXPAND, no toca reduce/combine
{
  "expand": {"enabled": true, "minutes_to_expand": 15}
}

// Incorrecto: Desactiva explícitamente reduce/combine
{
  "reduce": {"enabled": false},
  "combine": {"enabled": false},
  "expand": {"enabled": true, "minutes_to_expand": 15}
}
```

---

## API para Remover Filtros Individuales

### Opción 1: /apply con enabled: false (V5 - Nuevo)

```typescript
POST /filters/apply
{
  "reduce": {"enabled": false},
  "combine": {"enabled": true, "min_gap_minutes": 10}
}
```

**Ventaja:** Más simple, un solo endpoint
**Resultado:** reduce_applied = FALSE, combine_applied = TRUE

### Opción 2: /revert-partial (V3/V4 - Legacy)

```typescript
DELETE /filters/revert-partial?filter_type=reduce
```

**Ventaja:** Compatible con V3/V4
**Desventaja:** Dos requests (revert + re-apply interno)
**Resultado:** Igual que Opción 1

**Recomendación:** Usar Opción 1 en V5 (más directo).

---

## Testing

### Verificar en Frontend

```typescript
// 1. Estado inicial
const tripsBefore = await fetchTrips();
console.log(tripsBefore[0].reduce_applied);  // true
console.log(tripsBefore[0].combine_applied); // true

// 2. Desactivar REDUCE
await fetch('/filters/apply', {
  method: 'POST',
  body: JSON.stringify({
    reduce: { enabled: false },
    combine: { enabled: true, min_gap_minutes: 10 },
  }),
});

// 3. Verificar estado final
const tripsAfter = await fetchTrips();
console.log(tripsAfter[0].reduce_applied);   // false ✅
console.log(tripsAfter[0].combine_applied);  // true ✅
console.log(tripsAfter[0].pick_up_time);     // "09:50" (solo combine)
```

### Verificar en Database

```sql
-- Ver estado de filtros
SELECT
    id,
    pick_up_time,
    original_pick_up_time,
    reduce_applied,
    combine_applied,
    expand_applied
FROM trips.trips
WHERE location_id = '{location_uuid}'
  AND airline = 'WN'
  AND (reduce_applied OR combine_applied OR expand_applied);
```

---

## Resumen Final

| Tu Pregunta | Respuesta |
|-------------|-----------|
| **Envío `reduce: {enabled: false}`** | ✅ `reduce_applied` se vuelve FALSE |
| **Estado de `combine_applied`** | ✅ Se vuelve TRUE (porque enabled: true) |
| **`pick_up_time`** | Se ajusta para reflejar solo COMBINE |
| **`original_pick_up_time`** | Se mantiene como referencia |

**TL;DR:** En V5, `enabled: false` desactiva activamente el filtro (marca FALSE).

---

## Documentación Completa

Para más detalles sobre V5, lee:

📄 **[GROUND_FILTERS_FRONTEND_GUIDE_V5.md](./GROUND_FILTERS_FRONTEND_GUIDE_V5.md)**
Guía completa con ejemplos, componentes React, y casos de uso

📄 **[GROUND_FILTERS_V4_INDEPENDENT.md](./GROUND_FILTERS_V4_INDEPENDENT.md)**
Documentación técnica de la arquitectura V4/V5

---

**Backend Team**
**2026-01-20**
