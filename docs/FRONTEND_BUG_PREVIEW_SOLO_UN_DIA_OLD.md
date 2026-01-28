# Bug: Preview Muestra Solo Un Día (Siempre el 24)

**Fecha:** 2026-01-24
**Componente:** Frontend - Ground Filters V1 Preview
**Severidad:** 🔴 ALTA - Funcionalidad incorrecta

---

## 🐛 Síntoma del Bug

**Comportamiento actual:**
- Preview muestra solo trips del día 24
- Siempre el mismo día, independiente del mes seleccionado
- No muestra el mes completo

**Comportamiento esperado:**
- Preview debe mostrar TODOS los trips del mes
- Ej: Si estamos en Enero 2026, mostrar días 1-31

---

## 🔍 Root Cause (Investigación Backend)

### Backend Está CORRECTO ✅

**Endpoint:** `POST /v1/locations/{loc}/airlines/{airline}/trips/filters/preview`

**Código verificado:**
```python
# trip_filter_service.py:118-123

# Parse date filters
date_from = date.fromisoformat(config.pick_up_date_from) if config.pick_up_date_from else None
date_to = date.fromisoformat(config.pick_up_date_to) if config.pick_up_date_to else None

# Get eligible trips
trips = await self._get_eligible_trips(location_id, airline, date_from, date_to)
```

**Query en _get_eligible_trips:**
```python
# trip_filter_service.py:696-699

if date_from:
    query = query.Where(Trip.pick_up_date >= date_from)  # ✅ Correcto
if date_to:
    query = query.Where(Trip.pick_up_date <= date_to)    # ✅ Correcto
```

**✅ Backend usa correctamente el rango [pick_up_date_from, pick_up_date_to]**

---

## 🔴 Bug Está en FRONTEND

### Request Incorrecto que Envía Frontend

**Lo que el frontend está enviando (INCORRECTO):**
```json
{
  "pick_up_date_from": "2026-01-24",
  "pick_up_date_to": "2026-01-24",
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 15
  }
}
```

**Problema:** Mismo día para ambos parámetros → Solo devuelve trips del día 24

---

### Request Correcto (Lo que DEBERÍA enviar)

**Para mostrar TODO EL MES de Enero 2026:**
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

**Para mostrar TODO EL MES de Febrero 2026:**
```json
{
  "pick_up_date_from": "2026-02-01",
  "pick_up_date_to": "2026-02-28",
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 15
  }
}
```

---

## 🔧 Solución para Frontend

### Archivo a Revisar

**Frontend debe revisar el archivo que construye el `FilterRequest`**

Buscar código que:
1. Obtiene el mes seleccionado en UI
2. Construye `pick_up_date_from` y `pick_up_date_to`
3. Hace el POST a `/v1/.../filters/preview`

**Ejemplo de código INCORRECTO (probablemente lo que tienen):**
```typescript
// ❌ INCORRECTO - Siempre día 24
const filterRequest = {
  pick_up_date_from: "2026-01-24",  // ← Hardcoded o mal calculado
  pick_up_date_to: "2026-01-24",    // ← Mismo día
  reduce: { enabled: true, minutes_to_reduce: 15 }
};
```

**Ejemplo de código CORRECTO:**
```typescript
// ✅ CORRECTO - Todo el mes
const selectedMonth = 0; // Enero (0-11)
const selectedYear = 2026;

// Calcular primer y último día del mes
const firstDay = new Date(selectedYear, selectedMonth, 1);
const lastDay = new Date(selectedYear, selectedMonth + 1, 0); // Día 0 del mes siguiente = último día del mes actual

const filterRequest = {
  pick_up_date_from: firstDay.toISOString().split('T')[0],  // "2026-01-01"
  pick_up_date_to: lastDay.toISOString().split('T')[0],     // "2026-01-31"
  reduce: { enabled: true, minutes_to_reduce: 15 }
};

// POST /v1/.../filters/preview
const response = await fetch(url, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(filterRequest)
});
```

---

## 🧪 Testing

### Verificar Request en DevTools

1. Abrir DevTools → Network
2. Hacer preview
3. Buscar request a `/filters/preview`
4. Ver Request Payload:

**Si ves esto (INCORRECTO):**
```json
{
  "pick_up_date_from": "2026-01-24",
  "pick_up_date_to": "2026-01-24"
}
```
→ **Bug confirmado en frontend**

**Si ves esto (CORRECTO):**
```json
{
  "pick_up_date_from": "2026-01-01",
  "pick_up_date_to": "2026-01-31"
}
```
→ **Frontend está bien, investigar otro problema**

---

### Test Manual del Backend

```bash
# Test 1: Request con UN día (reproduce el bug)
curl -X POST http://localhost:8000/v1/locations/{loc}/airlines/WN/trips/filters/preview \
  -H "Content-Type: application/json" \
  -d '{
    "pick_up_date_from": "2026-01-24",
    "pick_up_date_to": "2026-01-24",
    "reduce": {
      "enabled": true,
      "minutes_to_reduce": 15
    }
  }'

# Resultado: Solo trips del día 24

# Test 2: Request con TODO EL MES (correcto)
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

## 📋 Checklist para Frontend

- [ ] Revisar cómo se obtiene `selectedMonth` y `selectedYear` en UI
- [ ] Verificar cálculo de primer día del mes
- [ ] Verificar cálculo de último día del mes
- [ ] Asegurar que `pick_up_date_from` y `pick_up_date_to` cubren TODO el mes
- [ ] Verificar en DevTools que el request tenga el rango correcto
- [ ] Probar con diferentes meses (Enero, Febrero, etc.)
- [ ] Verificar que no haya valores hardcoded ("2026-01-24")

---

## 📚 Documentación de Referencia

**Para entender el sistema de filtros:**
- [GROUND_FILTERS_V1_V2_COMPLETE_GUIDE.md](GROUND_FILTERS_V1_V2_COMPLETE_GUIDE.md) - Guía V2.1

**FilterRequest (V1) estructura:**
```typescript
interface FilterRequest {
  pick_up_date_from: string;  // "YYYY-MM-DD" - Primer día del rango
  pick_up_date_to: string;    // "YYYY-MM-DD" - Último día del rango
  rounding_mode: "multiple_of_5" | "odd_minutes";
  time_format?: "24h" | "12h";
  reduce?: {
    enabled: boolean;
    minutes_to_reduce: number;
    hotel_names?: string[] | null;
    time_range?: {
      start: string;  // "HH:MM:SS"
      end: string;    // "HH:MM:SS"
    } | null;
    date_range?: {
      date_from?: string;  // "YYYY-MM-DD"
      date_to?: string;    // "YYYY-MM-DD"
    } | null;
  };
  combine?: { /* ... */ };
  expand?: { /* ... */ };
}
```

**IMPORTANTE:** `date_range` dentro de cada filtro es ADICIONAL al `pick_up_date_from/to` global.

---

## ✅ Resumen

**Bug:** Frontend envía `pick_up_date_from` y `pick_up_date_to` con el mismo día

**Solución:** Calcular correctamente el primer y último día del mes seleccionado

**Backend:** ✅ Funcionando correctamente (verificado)

**Archivos frontend a revisar:**
- Componente de Ground Filters UI
- Función que construye `FilterRequest`
- Handler del botón "Preview"

---

**Autor:** Claude Code
**Fecha:** 2026-01-24 00:42 CET
**Verificado en:** Backend deployado sha256:ceaa2935bed9...
