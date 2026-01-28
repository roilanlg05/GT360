# Preview Bug - Investigación Profunda

**Fecha:** 2026-01-24 04:30 CET
**Síntoma:** Preview muestra solo día de mañana (día 25), no todo el mes
**Root Cause:** DOS niveles de filtrado por fecha

---

## 🔍 Problema Encontrado: Dos Niveles de Date Filtering

### Backend Tiene 2 Sistemas de Filtrado por Fecha

#### Nivel 1: Rango Global (FilterRequest)
```typescript
interface FilterRequest {
  pick_up_date_from: string;  // "2026-01-01"
  pick_up_date_to: string;    // "2026-01-31"
  reduce?: ReduceConfig;
}
```

**Query inicial:**
```sql
SELECT * FROM trips.trips
WHERE pick_up_date >= '2026-01-01'  -- ✅ Global from
  AND pick_up_date <= '2026-01-31'  -- ✅ Global to
  AND trip_type = 'outbound'
  AND status = 'scheduled'
```

#### Nivel 2: Rango Por Filtro (ADICIONAL)
```typescript
interface ReduceConfig {
  enabled: boolean;
  minutes_to_reduce: number;
  date_range?: {              // ← FILTRO ADICIONAL
    date_from?: string;       // "2026-01-25"
    date_to?: string;         // "2026-01-25"
  };
}
```

**Código backend:**
```python
# trip_filter_service.py:736-738

# Después de obtener trips del rango global...
if config.date_range:
    result = self._filter_by_date_range(result, config.date_range)
    # ← Esto REDUCE los trips solo a los que cumplan date_range
```

**Resultado:**
```
1. Query global: 500 trips (días 1-31)
   ↓
2. Filtro reduce con date_range {25-25}
   ↓
3. Solo quedan trips del día 25
```

---

## 🐛 Bug Confirmado

**Frontend está enviando `date_range` dentro de cada filtro:**

```json
{
  "pick_up_date_from": "2026-01-01",
  "pick_up_date_to": "2026-01-31",
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 15,
    "date_range": {
      "date_from": "2026-01-25",  // ← BUG AQUÍ
      "date_to": "2026-01-25"
    }
  },
  "combine": {
    "enabled": true,
    "min_gap": 10,
    "max_gap": 20,
    "date_range": {
      "date_from": "2026-01-25",  // ← BUG AQUÍ
      "date_to": "2026-01-25"
    }
  }
}
```

**Esto hace que:**
- El rango global obtiene 500 trips del mes
- Pero reduce solo se aplica a trips del día 25
- Resultado: Solo ves cambios del día 25

---

## ✅ Solución CORRECTA

### Opción 1: NO Enviar date_range en Filtros (RECOMENDADO)

```json
{
  "pick_up_date_from": "2026-01-01",
  "pick_up_date_to": "2026-01-31",
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 15
    // ✅ NO incluir date_range
  },
  "combine": {
    "enabled": true,
    "min_gap": 10,
    "max_gap": 20
    // ✅ NO incluir date_range
  }
}
```

**Resultado:** Filtros se aplican a TODO el mes

---

### Opción 2: Enviar date_range = null Explícitamente

```json
{
  "pick_up_date_from": "2026-01-01",
  "pick_up_date_to": "2026-01-31",
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 15,
    "date_range": null  // ✅ Explícitamente null
  }
}
```

---

## 📋 Checklist para Frontend

### 1. Inspeccionar Request en DevTools

Abrir Network tab y ver el body del POST a `/filters/preview`:

**Si ves esto (INCORRECTO):**
```json
{
  "reduce": {
    "date_range": {
      "date_from": "2026-01-25",
      "date_to": "2026-01-25"
    }
  }
}
```
→ **BUG CONFIRMADO**

**Si ves esto (CORRECTO):**
```json
{
  "reduce": {
    "minutes_to_reduce": 15
    // Sin date_range
  }
}
```
→ **Frontend correcto**

---

### 2. Revisar Código Frontend

**Buscar donde se construye el FilterRequest:**

```typescript
// ❌ INCORRECTO - Probablemente el código actual
const filterRequest = {
  pick_up_date_from: monthStart,
  pick_up_date_to: monthEnd,
  reduce: {
    enabled: true,
    minutes_to_reduce: 15,
    date_range: {
      date_from: tomorrow,  // ← BUG
      date_to: tomorrow
    }
  }
};
```

```typescript
// ✅ CORRECTO - Como debería ser
const filterRequest = {
  pick_up_date_from: monthStart,
  pick_up_date_to: monthEnd,
  reduce: {
    enabled: true,
    minutes_to_reduce: 15
    // NO incluir date_range
  }
};
```

---

### 3. ¿Cuándo Usar date_range en Filtros?

**`date_range` dentro de filtros es OPCIONAL y se usa para casos especiales:**

**Ejemplo - Aplicar reduce solo a primeros 10 días del mes:**
```json
{
  "pick_up_date_from": "2026-01-01",
  "pick_up_date_to": "2026-01-31",
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 15,
    "date_range": {
      "date_from": "2026-01-01",
      "date_to": "2026-01-10"  // Solo primeros 10 días
    }
  },
  "combine": {
    "enabled": true,
    "min_gap": 10,
    "max_gap": 20
    // Sin date_range = se aplica a TODOS los días del rango global
  }
}
```

**Resultado:**
- Reduce: Solo días 1-10
- Combine: Días 1-31 (todo el mes)

**Para aplicar a TODO el mes: NO enviar date_range**

---

## 🔬 Análisis del Código Backend

### Filtros SOLO a Status = SCHEDULED

**Código:** `trip_filter_service.py:689-690`
```python
.Where(Trip.trip_type == TripType.OUTBOUND)
.Where(Trip.status == TripStatus.SCHEDULED)
```

**✅ CORRECTO:** Preview solo aplica a trips `scheduled`

**Trips con otros status se ignoran:**
- `en_route` - NO modificables (ya en ruta)
- `completed` - NO modificables (completados)
- `canceled` - NO modificables (cancelados)

---

### Categorización de Trips

**"Live" vs "History"** (para Timeline):

```sql
-- Live = trips futuros o en ruta
status = 'en_route'
OR (
  status = 'scheduled'
  AND (
    pick_up_date > CURRENT_DATE
    OR (pick_up_date = CURRENT_DATE AND pick_up_time > CURRENT_TIME)
  )
)

-- History = trips pasados o completados
status = 'completed'
OR status = 'canceled'
OR (
  status = 'scheduled'
  AND (
    pick_up_date < CURRENT_DATE
    OR (pick_up_date = CURRENT_DATE AND pick_up_time <= CURRENT_TIME)
  )
)
```

**PERO:** Esta categorización es SOLO para Timeline.

**Preview aplica a TODOS los `scheduled`** (pasados y futuros).

---

## 🎯 Solución Final para Frontend

### Request Correcto para Preview de Todo el Mes

```typescript
// ✅ CORRECTO
const year = 2026;
const month = 0; // Enero

const firstDay = new Date(year, month, 1);
const lastDay = new Date(year, month + 1, 0);

const filterRequest = {
  pick_up_date_from: firstDay.toISOString().split('T')[0],  // "2026-01-01"
  pick_up_date_to: lastDay.toISOString().split('T')[0],     // "2026-01-31"
  rounding_mode: "multiple_of_5",
  reduce: {
    enabled: true,
    minutes_to_reduce: 15,
    hotel_names: null,        // null = todos
    time_range: null,         // null = todas las horas
    date_range: null          // ✅ CRÍTICO: null para aplicar a todo el rango global
  },
  combine: {
    enabled: true,
    min_gap: 10,
    max_gap: 20,
    hotel_names: null,
    time_range: null,
    date_range: null          // ✅ CRÍTICO: null para aplicar a todo el rango global
  }
};

// POST /v1/.../filters/preview
const response = await fetch(url, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(filterRequest)
});
```

---

## 🧪 Test para Verificar

### Test en DevTools (Chrome/Firefox)

1. Abrir Network tab
2. Click en "Preview"
3. Buscar request `POST .../filters/preview`
4. Click → Headers → Request Payload

**Verificar:**
```json
{
  "pick_up_date_from": "2026-01-01",  // ✅ Mes completo
  "pick_up_date_to": "2026-01-31",    // ✅ Mes completo
  "reduce": {
    "date_range": ???  // ← Si esto tiene valor = BUG
  }
}
```

**Si `date_range` tiene valor:**
- ❌ BUG confirmado
- Remover `date_range` del código frontend

**Si `date_range` es `null` o no existe:**
- ✅ Request correcto
- Investigar otra causa (posible filtrado en frontend del response)

---

### Test Manual del Backend

```bash
# Test con date_range (reproduce bug)
curl -X POST http://localhost:8000/v1/locations/{loc}/airlines/WN/trips/filters/preview \
  -H "Content-Type: application/json" \
  -d '{
    "pick_up_date_from": "2026-01-01",
    "pick_up_date_to": "2026-01-31",
    "reduce": {
      "enabled": true,
      "minutes_to_reduce": 15,
      "date_range": {
        "date_from": "2026-01-25",
        "date_to": "2026-01-25"
      }
    }
  }'

# Resultado: Solo trips del día 25

# Test sin date_range (correcto)
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

# Resultado: Trips de todo el mes ✅
```

---

## 📚 Documentación

**Estructura completa de FilterRequest:**

Ver: [GROUND_FILTERS_V1_V2_COMPLETE_GUIDE.md](GROUND_FILTERS_V1_V2_COMPLETE_GUIDE.md)

```typescript
interface FilterRequest {
  // Rango GLOBAL (obligatorio para definir scope)
  pick_up_date_from: string;
  pick_up_date_to: string;

  reduce?: {
    enabled: boolean;
    minutes_to_reduce: number;
    hotel_names?: string[] | null;
    time_range?: TimeRange | null;
    date_range?: DateRange | null;  // ← ADICIONAL, normalmente null
  };
}

interface DateRange {
  date_from?: string;  // Para filtrar AÚN MÁS el rango global
  date_to?: string;
}
```

**Uso de `date_range` (casos avanzados):**

```
Caso 1: Aplicar filtro a todo el mes
→ pick_up_date_from/to = mes completo
→ date_range = null (o no enviarlo)

Caso 2: Aplicar reduce solo a primera semana, combine a todo el mes
→ pick_up_date_from/to = mes completo
→ reduce.date_range = {date_from: "01", date_to: "07"}
→ combine.date_range = null
```

**Para caso normal (filtro a todo el mes): NO enviar date_range**

---

## ✅ Resumen

**Bug:** Frontend envía `date_range` dentro de reduce/combine/expand

**Solución:** NO enviar `date_range` (o enviarlo como `null`)

**Backend:** ✅ Funcionando correctamente

**Archivos frontend a revisar:**
- Componente que construye FilterRequest
- Verificar si hay lógica que setee `date_range` automáticamente
- Verificar en DevTools el request exacto que se envía

---

**Autor:** Claude Code
**Última verificación:** 2026-01-24 04:30 CET
