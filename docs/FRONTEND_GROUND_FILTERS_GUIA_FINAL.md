# Ground Filters - Guía Final para Frontend

**Fecha:** 2026-01-24 05:08 CET
**Versión Backend:** V2.1 con filtro automático a trips live
**Deploy:** sha256:ef8a755c6f75...

---

## 🎯 Qué Hace el Preview Ahora

### Preview Muestra SOLO Trips Futuros (Live)

**Automáticamente filtra a:**
```
✅ trip_type = 'outbound'
✅ status = 'scheduled'
✅ pick_up_date > hoy
   O (pick_up_date = hoy Y pickup_time > hora_actual)
```

**Ejemplo - Hoy 24 Enero 10:00:**
```
Trips en DB:
- 2026-01-23 → ❌ Excluido (pasado)
- 2026-01-24 09:00 → ❌ Excluido (ya pasó hace 1h)
- 2026-01-24 11:00 → ✅ Incluido (queda 1h)
- 2026-01-25 → ✅ Incluido (mañana)
- 2026-01-26 → ✅ Incluido (pasado mañana)
```

---

## 📝 Request Correcto (V1 Preview)

### Estructura del Request

```typescript
interface FilterRequest {
  // Rango global (respetar pero ADEMÁS filtra a futuros)
  pick_up_date_from: string;  // "2026-01-01"
  pick_up_date_to: string;    // "2026-01-31"

  rounding_mode: "multiple_of_5" | "odd_minutes";
  time_format?: "24h" | "12h";

  reduce?: {
    enabled: boolean;
    minutes_to_reduce: number;  // 1-120
    hotel_names?: string[] | null;  // null = todos
    time_range?: TimeRange | null;  // null = todas las horas
    date_range?: DateRange | null;  // null = NO filtrar más
  };

  combine?: {
    enabled: boolean;
    min_gap: number;
    max_gap: number;
    hotel_names?: string[] | null;
    time_range?: TimeRange | null;
    date_range?: DateRange | null;  // null = NO filtrar más
  };

  expand?: {
    enabled: boolean;
    min_gap: number;
    max_gap: number;
    max_shift: number;
    hotel_names?: string[] | null;
    time_range?: TimeRange | null;
    date_range?: DateRange | null;  // null = NO filtrar más
  };
}
```

---

### Request para Preview de TODO EL MES

```typescript
const year = 2026;
const month = 0; // Enero (0-11 en JS)

const firstDay = new Date(year, month, 1);
const lastDay = new Date(year, month + 1, 0);

const filterRequest = {
  pick_up_date_from: firstDay.toISOString().split('T')[0],  // "2026-01-01"
  pick_up_date_to: lastDay.toISOString().split('T')[0],     // "2026-01-31"
  rounding_mode: "multiple_of_5",
  time_format: "24h",

  reduce: {
    enabled: true,
    minutes_to_reduce: 15,
    hotel_names: null,     // ✅ null = todos los hoteles
    time_range: null,      // ✅ null = todas las horas
    date_range: null       // ✅ CRÍTICO: null = no limitar más
  },

  combine: {
    enabled: true,
    min_gap: 10,
    max_gap: 20,
    hotel_names: null,
    time_range: null,
    date_range: null       // ✅ CRÍTICO: null
  },

  expand: {
    enabled: false
  }
};

// POST /v1/.../filters/preview
const response = await fetch(url, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(filterRequest)
});

const preview = await response.json();
```

---

## 🔍 Qué Devuelve el Backend

### Response Structure

```json
{
  "location_id": "uuid",
  "airline": "WN",
  "changes": [
    {
      "trip_id": "uuid1",
      "pick_up_date": "2026-01-24",
      "original_time": "11:00:00",
      "new_time": "10:45:00",
      "filter_applied": "reduce",
      "hotel_name": "Hotel A",
      "airline": "WN",
      "flight_number": "1234"
    },
    {
      "trip_id": "uuid2",
      "pick_up_date": "2026-01-25",
      "original_time": "05:00:00",
      "new_time": "04:45:00",
      "filter_applied": "reduce",
      "hotel_name": "Hotel B",
      "airline": "WN",
      "flight_number": "5678"
    }
    // ... más cambios de días futuros ...
  ],
  "exclusions": [],
  "summary": {
    "reduce": 250,    // Total de cambios
    "combine": 100,
    "expand": 0,
    "excluded": 5
  },
  "total_trips_evaluated": 300,  // Trips futuros en el rango
  "eligible_trips": 300
}
```

---

## 🎨 Cómo Mostrar en UI

### Agrupar por Día

```typescript
interface DayGroup {
  date: string;
  changes: TripChange[];
}

const groupByDay = (changes: TripChange[]): DayGroup[] => {
  const groups = changes.reduce((acc, change) => {
    const day = change.pick_up_date;
    if (!acc[day]) {
      acc[day] = {
        date: day,
        changes: []
      };
    }
    acc[day].changes.push(change);
    return acc;
  }, {} as Record<string, DayGroup>);

  return Object.values(groups).sort((a, b) =>
    a.date.localeCompare(b.date)
  );
};

// Usar
const dayGroups = groupByDay(preview.changes);

// Renderizar
<ScrollArea>
  {dayGroups.map(group => (
    <DaySection key={group.date} date={group.date}>
      <h3>{formatDate(group.date)}</h3>
      <p>{group.changes.length} trips modificados</p>

      {group.changes.map(change => (
        <TripChange key={change.trip_id}>
          <span>{change.original_time} → {change.new_time}</span>
          <Badge>{change.filter_applied}</Badge>
        </TripChange>
      ))}
    </DaySection>
  ))}
</ScrollArea>
```

---

## ⚠️ IMPORTANTE: NO Enviar date_range en Filtros

### ❌ INCORRECTO (Causa el Bug)

```json
{
  "pick_up_date_from": "2026-01-01",
  "pick_up_date_to": "2026-01-31",
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 15,
    "date_range": {
      "date_from": "2026-01-25",  // ← BUG
      "date_to": "2026-01-25"
    }
  }
}
```

**Resultado:** Solo día 25 (aunque rango global sea todo el mes)

---

### ✅ CORRECTO

```json
{
  "pick_up_date_from": "2026-01-01",
  "pick_up_date_to": "2026-01-31",
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 15
    // ✅ NO incluir date_range
  }
}
```

**Resultado:** Todos los días futuros del mes (desde hoy)

---

## 🧪 Testing

### Verificar en DevTools

1. Network tab → POST `/filters/preview`
2. Ver Request Payload
3. Verificar que `reduce.date_range` NO exista o sea `null`

### Test de Comportamiento

```
Hoy: 2026-01-24 10:00

Request:
- pick_up_date_from: "2026-01-01"
- pick_up_date_to: "2026-01-31"
- reduce: {enabled: true, minutes_to_reduce: 15}

Response debe incluir:
✅ Trips del 24 con pickup_time > 10:00
✅ Trips del 25, 26, 27, 28, 29, 30, 31
❌ Trips del 21, 22, 23
❌ Trips del 24 con pickup_time <= 10:00

Verificar en UI:
- Primer día mostrado = 24 (con solo algunos trips)
- Último día mostrado = 31 (con todos los trips)
```

---

## 📚 Documentación de Referencia

**Guía principal:**
- [GROUND_FILTERS_V1_V2_COMPLETE_GUIDE.md](GROUND_FILTERS_V1_V2_COMPLETE_GUIDE.md) - V2.1

**Cambio de comportamiento:**
- [PREVIEW_AUTO_FILTER_LIVE_TRIPS.md](PREVIEW_AUTO_FILTER_LIVE_TRIPS.md) - Filtro automático

---

## ✅ Checklist Final

- [ ] Verificar que `date_range` NO se envíe en reduce/combine/expand
- [ ] Request debe tener `pick_up_date_from` = primer día del mes
- [ ] Request debe tener `pick_up_date_to` = último día del mes
- [ ] Verificar en DevTools el request exacto
- [ ] Verificar que response incluye múltiples días (no solo uno)
- [ ] Agrupar changes por `pick_up_date` en UI
- [ ] Mostrar en scroll vertical por día

---

**Backend deployado con filtro automático a trips live.** ✅
**Frontend NO requiere cambios, solo verificar que NO envíe date_range.** ✅

---

**Última actualización:** 2026-01-24 05:08 CET
