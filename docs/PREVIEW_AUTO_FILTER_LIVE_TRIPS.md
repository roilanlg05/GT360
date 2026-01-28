# Preview - Filtro Automático a Trips Live (Futuros)

**Fecha:** 2026-01-24 05:06 CET
**Cambio:** Preview ahora filtra automáticamente a trips futuros (live)
**Deploy:** sha256:ef8a755c6f75...

---

## 🎯 Comportamiento Nuevo (ACTUAL)

### Preview Muestra SOLO Trips Futuros (Live)

**Definición de "Live":**
```
scheduled = live

Trip es "live" si:
  pick_up_date > HOY
  O
  (pick_up_date = HOY Y pickup_time > HORA_ACTUAL)
```

**Trips EXCLUIDOS del preview:**
```
- pick_up_date < hoy (pasados)
- pick_up_date = hoy Y pickup_time <= hora_actual (ya pasaron)
- status != 'scheduled' (completed, canceled, en_route)
- trip_type != 'outbound'
```

---

## 💻 Código Implementado

**Archivo:** `trip_filter_service.py:669-709`

```python
async def _get_eligible_trips(self, location_id, airline, date_from, date_to):
    """
    Get trips eligible for filtering.

    Criteria:
    - trip_type = OUTBOUND only
    - status = SCHEDULED only
    - LIVE trips only (future pickup)
    - Respects date_from/to params
    """
    from datetime import datetime

    # Get current date/time
    now = datetime.utcnow()
    current_date = now.date()
    current_time = now.time()

    query = (
        Select(Trip)
        .Where(Trip.location_id == location_id)
        .Where(Trip.airline == airline)
        .Where(Trip.trip_type == TripType.OUTBOUND)
        .Where(Trip.status == TripStatus.SCHEDULED)
        # LIVE trips only
        .Where(
            (Trip.pick_up_date > current_date) |
            ((Trip.pick_up_date == current_date) & (Trip.pick_up_time > current_time))
        )
    )

    # Apply date filters (respects params from frontend)
    if date_from:
        query = query.Where(Trip.pick_up_date >= date_from)
    if date_to:
        query = query.Where(Trip.pick_up_date <= date_to)

    return await self.session.exec(query).all()
```

---

## 📊 Ejemplos

### Hoy es 2026-01-24 a las 10:00

**Trips en DB:**
```
2026-01-24 09:00 - scheduled  → ❌ Excluido (ya pasó)
2026-01-24 11:00 - scheduled  → ✅ Incluido (quedan 1h)
2026-01-24 15:00 - scheduled  → ✅ Incluido (futuro)
2026-01-25 05:00 - scheduled  → ✅ Incluido (mañana)
2026-01-26 06:00 - scheduled  → ✅ Incluido (pasado mañana)
2026-01-23 10:00 - scheduled  → ❌ Excluido (ayer)
```

**Frontend envía:**
```json
{
  "pick_up_date_from": "2026-01-01",
  "pick_up_date_to": "2026-01-31"
}
```

**Backend devuelve cambios de:**
```
2026-01-24 (solo trips con pickup_time > 10:00)
2026-01-25 (todos los trips)
2026-01-26 (todos los trips)
...
2026-01-31 (todos los trips)
```

**Total:** Todos los trips futuros del mes, desde ahora hasta fin de mes.

---

## 🔄 Cambio de Comportamiento

### Antes (Sin Filtro Live)

```
Preview incluía:
- Trips pasados ✓
- Trips de hoy (todos) ✓
- Trips futuros ✓

Problema: Mostraba trips que ya no se pueden modificar
```

### Ahora (Con Filtro Live)

```
Preview incluye:
- Trips pasados ✗
- Trips de hoy (solo los que quedan) ✓
- Trips futuros ✓

Beneficio: Solo muestra trips que realmente se van a modificar
```

---

## 🎨 Impacto en Frontend

### Request NO Cambia

Frontend sigue enviando el mismo request:

```json
{
  "pick_up_date_from": "2026-01-01",
  "pick_up_date_to": "2026-01-31",
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 15
  }
}
```

### Response Ahora Incluye SOLO Trips Futuros

**Antes (sin filtro):**
```json
{
  "changes": [
    {"pick_up_date": "2026-01-21", ...},  // Ayer
    {"pick_up_date": "2026-01-22", ...},  // Ayer
    {"pick_up_date": "2026-01-24", ...},  // Hoy (todos)
    {"pick_up_date": "2026-01-25", ...},  // Mañana
    ...
  ],
  "eligible_trips": 500
}
```

**Ahora (con filtro live):**
```json
{
  "changes": [
    {"pick_up_date": "2026-01-24", ...},  // Solo los que quedan hoy
    {"pick_up_date": "2026-01-25", ...},  // Mañana
    {"pick_up_date": "2026-01-26", ...},  // Pasado mañana
    ...
  ],
  "eligible_trips": 300  // Menos porque excluye pasados
}
```

---

## 📋 Para Frontend

### No Requiere Cambios en Request

Frontend puede seguir enviando:
```typescript
const filterRequest = {
  pick_up_date_from: monthStart,  // Primer día del mes
  pick_up_date_to: monthEnd,      // Último día del mes
  reduce: {
    enabled: true,
    minutes_to_reduce: 15
    // ✅ NO enviar date_range
  }
};
```

**Backend automáticamente filtra a futuros.**

---

### Mostrar en UI

```typescript
// Response ya viene filtrado a futuros
const preview = await fetchPreview(filterRequest);

// Agrupar por día para scroll
const byDay = preview.changes.reduce((acc, change) => {
  const day = change.pick_up_date;
  if (!acc[day]) acc[day] = [];
  acc[day].push(change);
  return acc;
}, {});

// Mostrar en scroll
Object.entries(byDay).map(([day, changes]) => (
  <DayGroup date={day}>
    {changes.map(change => <TripChange {...change} />)}
  </DayGroup>
))
```

---

## ✅ Verificación

### Test Manual

```bash
# Asumiendo hoy es 2026-01-24 10:00

curl -X POST http://localhost:8000/v1/locations/{loc}/airlines/WN/trips/filters/preview \
  -H "Content-Type: application/json" \
  -d '{
    "pick_up_date_from": "2026-01-01",
    "pick_up_date_to": "2026-01-31",
    "reduce": {
      "enabled": true,
      "minutes_to_reduce": 15
    }
  }'

# Response debe incluir:
# - Trips del 24 con pickup_time > 10:00 ✅
# - Trips del 25 al 31 ✅
# - NO trips del 21, 22, 23 ✅
# - NO trips del 24 con pickup_time <= 10:00 ✅
```

---

## 🎯 Resumen

| Aspecto | Antes | Ahora |
|---------|-------|-------|
| **Trips incluidos** | Todos scheduled | Solo scheduled futuros (live) |
| **Trips pasados** | Incluidos | Excluidos automáticamente |
| **Trips de hoy** | Todos | Solo con pickup_time > hora actual |
| **Request params** | Respetados | Respetados + filtro live adicional |
| **Frontend cambios** | - | Ninguno requerido |

**El preview ahora muestra desde el primer trip que queda hoy hasta el futuro.** ✅

---

**Autor:** Claude Code
**Deploy:** sha256:ef8a755c6f75...
**Última actualización:** 2026-01-24 05:06 CET
