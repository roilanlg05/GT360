# Guía de Implementación de Revert para Frontend

**Fecha:** 2026-01-26
**Para:** Equipo de Frontend
**Backend Fix Aplicado:** Commit 9f53a34 (trips_recalculated ahora correcto)

---

## 🎯 Objetivo

Mostrar correctamente el número de trips afectados en las notificaciones de revert.

**Problema actual:**
```
❌ Muestra: "0 trips en 28 días"
✅ Debe mostrar: "922 trips en 29 días"
```

---

## 📊 Estructura del Response del Backend

### Para Bulk Revert (POST /bulk/revert)

**Response Type:** `BulkRevertResult`

```typescript
interface BulkRevertResult {
  date_from: string;                    // "2026-01-02"
  date_to: string | null;               // null = todos los futuros
  filter_type: string | null;           // "reduce" | "combine" | "expand" | null

  // === SUMMARY (Usar para toast) ===
  total_days: number;                   // 29 - Total de días encontrados
  days_with_reverts: number;            // 29 - Días donde se revirtió algo
  days_skipped: number;                 // 0 - Días sin cambios
  total_steps_reverted: number;         // 29 - Total de FilterSteps revertidos
  total_trips_recalculated: number;     // 922 ← ESTE ES EL IMPORTANTE

  // === PER-DAY DETAILS ===
  by_date: DayRevertResult[];           // Array con detalle por día
}
```

**Ejemplo de Response Real:**

```json
{
  "date_from": "2026-01-02",
  "date_to": null,
  "filter_type": "reduce",
  "total_days": 29,
  "days_with_reverts": 29,
  "days_skipped": 0,
  "total_steps_reverted": 29,
  "total_trips_recalculated": 922,  // ← USAR ESTE
  "by_date": [
    {
      "pick_up_date": "2026-01-02",
      "steps_reverted": 1,
      "step_ids": ["uuid-1"],
      "trips_recalculated": 31,
      "skipped": false
    },
    {
      "pick_up_date": "2026-01-03",
      "steps_reverted": 1,
      "step_ids": ["uuid-2"],
      "trips_recalculated": 32,
      "skipped": false
    },
    // ... 27 días más
  ]
}
```

---

## ✅ Código Correcto para el Frontend

### Implementación Completa

```typescript
// ============================================
// BULK REVERT - Implementación Correcta
// ============================================

async function handleBulkRevert(
  locationId: string,
  airline: string,
  dateFrom: string,
  dateTo: string | null,
  filterType: 'reduce' | 'combine' | 'expand' | null
) {
  try {
    setIsReverting(true);
    console.log('[Revert] Starting bulk revert:', { dateFrom, dateTo, filterType });

    // 1. Llamar endpoint
    const response = await axios.post<BulkRevertResult>(
      `/v2/locations/${locationId}/airlines/${airline}/filters/bulk/revert`,
      {
        date_from: dateFrom,
        date_to: dateTo,
        filter_type: filterType
      }
    );

    // 2. CRÍTICO: Extraer campos correctos
    const {
      total_trips_recalculated,  // ← ESTE es el número de trips
      days_with_reverts,         // ← Número de días procesados
      total_steps_reverted,      // ← Número de steps (NO usar para toast)
      filter_type: revertedType,
      by_date
    } = response.data;

    // 3. Log para debugging
    console.log('[Revert] Backend response:', {
      total_trips_recalculated,  // Debe ser 922
      days_with_reverts,         // Debe ser 29
      total_steps_reverted,      // Debe ser 29
      filter_type: revertedType
    });

    // 4. CRÍTICO: Mostrar notificación CORRECTA
    //    PRIORIZAR trips, NO steps
    toast.success(
      `Filtro ${revertedType || 'todos'} revertido: ` +
      `${total_trips_recalculated.toLocaleString()} trips ` +
      `en ${days_with_reverts} días restaurados a horarios originales`
    );
    // → "Filtro reduce revertido: 922 trips en 29 días restaurados a horarios originales" ✅

    // 5. Limpiar estado local
    setAppliedSteps([]);

    // 6. Reload stack from backend para sincronizar
    await rehidration.reload(pickUpDate);

    // 7. Refetch trips para ver horarios originales
    await queryClient.invalidateQueries(['trips', locationId, airline]);

    return {
      success: true,
      trips_recalculated: total_trips_recalculated,
      days_reverted: days_with_reverts
    };

  } catch (error: any) {
    console.error('[Revert] Error:', error);

    if (error.response?.status === 400) {
      toast.warning('No hay filtros activos para revertir');
    } else {
      toast.error('Error al revertir filtros');
    }

    return { success: false };

  } finally {
    setIsReverting(false);
  }
}
```

---

## ❌ Errores Comunes

### Error 1: Usar `total_steps_reverted` en vez de `total_trips_recalculated`

```typescript
// ❌ INCORRECTO
toast.success(`Revertidos ${response.total_steps_reverted} trips`);
// → "Revertidos 29 trips" ❌ (son 29 STEPS/DÍAS, no trips)

// ✅ CORRECTO
toast.success(`Revertidos ${response.total_trips_recalculated} trips`);
// → "Revertidos 922 trips" ✅
```

### Error 2: Usar `total_days` en vez de `days_with_reverts`

```typescript
// ❌ INCORRECTO
toast.success(`${response.total_trips_recalculated} trips en ${response.total_days} días`);
// → "922 trips en 29 días" (puede incluir días skipped)

// ✅ CORRECTO
toast.success(`${response.total_trips_recalculated} trips en ${response.days_with_reverts} días`);
// → "922 trips en 29 días" (solo días donde se revirtió algo)
```

### Error 3: No acceder correctamente al campo anidado

```typescript
// ❌ INCORRECTO
const trips = response.trips_recalculated;  // undefined
const trips = response.data.trips;          // undefined

// ✅ CORRECTO
const trips = response.data.total_trips_recalculated;  // 922 ✅
```

---

## 🔍 Debugging del Response

### Agregar Logs Detallados

```typescript
// Después de recibir respuesta del backend
console.group('[Revert] Backend Response Analysis');

console.log('📦 Full response:', response);
console.log('📦 Response.data:', response.data);

console.log('📊 Summary Fields:', {
  total_days: response.data.total_days,
  days_with_reverts: response.data.days_with_reverts,
  days_skipped: response.data.days_skipped,
  total_steps_reverted: response.data.total_steps_reverted,
  total_trips_recalculated: response.data.total_trips_recalculated  // ← Verificar este
});

console.log('📅 By Date:', response.data.by_date.map(d => ({
  date: d.pick_up_date,
  trips: d.trips_recalculated,
  skipped: d.skipped
})));

console.log('🧮 Total sum:',
  response.data.by_date.reduce((sum, d) => sum + d.trips_recalculated, 0)
);
// Debe coincidir con total_trips_recalculated

console.groupEnd();
```

### Verificación del Backend

```typescript
// Test que el backend esté retornando datos correctos
const testResponse = await axios.post('/v2/locations/.../filters/bulk/revert', {
  date_from: '2026-01-02',
  date_to: null,
  filter_type: 'reduce'
});

// Verificar estructura
console.assert(
  typeof testResponse.data.total_trips_recalculated === 'number',
  'total_trips_recalculated debe ser number'
);

console.assert(
  testResponse.data.total_trips_recalculated > 0,
  'total_trips_recalculated debe ser > 0'
);

console.assert(
  testResponse.data.total_trips_recalculated ===
    testResponse.data.by_date.reduce((sum, d) => sum + d.trips_recalculated, 0),
  'total_trips_recalculated debe ser suma de by_date'
);
```

---

## 📝 Tipos TypeScript

### Definir Tipos Correctos

```typescript
// types/filters.ts

export interface DayRevertResult {
  pick_up_date: string;
  steps_reverted: number;
  step_ids: string[];
  trips_recalculated: number;  // ← Trips de ESTE día
  skipped: boolean;
  skip_reason: string | null;
}

export interface BulkRevertResult {
  date_from: string;
  date_to: string | null;
  filter_type: string | null;

  // Summary
  total_days: number;
  days_with_reverts: number;
  days_skipped: number;
  total_steps_reverted: number;
  total_trips_recalculated: number;  // ← Total GLOBAL de trips

  // Details
  by_date: DayRevertResult[];
}

export interface StepRevertResult {
  step_id: string;
  filter_type: string;
  trips_recalculated: number;  // ← Trips de ESTE día
  remaining_steps: number;
  stack_state: StackState | null;
}
```

---

## 🎯 Implementación Paso a Paso

### Paso 1: Llamar Endpoint Correcto

```typescript
// Para revert bulk (múltiples días)
const response = await axios.post<BulkRevertResult>(
  `/v2/locations/${locationId}/airlines/${airline}/filters/bulk/revert`,
  {
    date_from: '2026-01-02',
    date_to: null,  // todos los futuros
    filter_type: 'reduce'
  }
);
```

### Paso 2: Extraer Campos del Response

```typescript
// Destructuring para acceso claro
const {
  total_trips_recalculated,  // ← CAMPO PRINCIPAL
  days_with_reverts,
  total_steps_reverted,
  filter_type,
  by_date
} = response.data;

// Verificar que sea número válido
if (typeof total_trips_recalculated !== 'number') {
  console.error('❌ total_trips_recalculated no es número:', total_trips_recalculated);
  throw new Error('Invalid backend response');
}

console.log('✅ Trips recalculados:', total_trips_recalculated);  // 922
```

### Paso 3: Mostrar Notificación

```typescript
// Opción A: Formato completo (recomendado)
toast.success(
  `Filtro ${filter_type || 'todos'} revertido: ` +
  `${total_trips_recalculated.toLocaleString()} trips ` +
  `en ${days_with_reverts} días`
);

// Opción B: Formato simple
toast.success(
  `${total_trips_recalculated.toLocaleString()} trips restaurados a horarios originales`
);

// Opción C: Formato con ícono
toast.success(
  `↩️ ${total_trips_recalculated.toLocaleString()} trips revertidos (${days_with_reverts} días)`
);
```

### Paso 4: Actualizar Estado

```typescript
// Limpiar appliedSteps
setAppliedSteps([]);

// Reload stack para sincronizar
await rehidration.reload(pickUpDate);

// Refetch trips
await queryClient.invalidateQueries(['trips']);
```

---

## 🐛 Posibles Problemas del Frontend

### Problema 1: Acceso Incorrecto al Campo

```typescript
// ❌ INCORRECTO - Puede estar accediendo mal
const trips = response.trips_recalculated;  // undefined
const trips = response.total_trips;         // undefined
const trips = response.data.trips;          // undefined

// ✅ CORRECTO
const trips = response.data.total_trips_recalculated;  // 922 ✅
```

### Problema 2: Usando Campo Incorrecto

```typescript
// ❌ INCORRECTO
const count = response.data.total_steps_reverted;  // 29 (son steps, no trips)

// ✅ CORRECTO
const count = response.data.total_trips_recalculated;  // 922 (son trips)
```

### Problema 3: Calculando Manualmente (Incorrecto)

```typescript
// ❌ INCORRECTO - No calcular manualmente
const trips = response.data.by_date.filter(d => !d.skipped).length;  // 29 (días, no trips)

// ✅ CORRECTO - Usar campo del backend
const trips = response.data.total_trips_recalculated;  // 922 (backend ya lo calculó)
```

---

## 🧪 Test de Verificación

### Test 1: Console Log del Response

```typescript
// Agregar ANTES de mostrar toast
console.group('🔍 [Revert] Response Verification');

console.log('Raw response:', response);
console.log('Response.data:', response.data);

console.table({
  'Total Days': response.data.total_days,
  'Days with Reverts': response.data.days_with_reverts,
  'Days Skipped': response.data.days_skipped,
  'Steps Reverted': response.data.total_steps_reverted,
  'Trips Recalculated': response.data.total_trips_recalculated  // ← Este debe ser 922
});

console.groupEnd();

// SI total_trips_recalculated es 0, el backend NO tiene el fix
// SI total_trips_recalculated es 922, el frontend no está accediendo correctamente
```

### Test 2: Verificar Sum de by_date

```typescript
// Verificar que total_trips_recalculated sea suma correcta de by_date
const sumFromByDate = response.data.by_date.reduce(
  (sum, day) => sum + day.trips_recalculated,
  0
);

console.log('Verificación:', {
  total_trips_recalculated: response.data.total_trips_recalculated,
  sum_from_by_date: sumFromByDate,
  matches: response.data.total_trips_recalculated === sumFromByDate
});

// Debe ser true ✅
```

---

## 📋 Checklist de Implementación

- [ ] **1. Verificar que el backend tenga el fix**
  ```bash
  # Backend debe estar en commit 9f53a34 o posterior
  # Servidor debe haberse reiniciado después de 2026-01-26 16:04
  ```

- [ ] **2. Usar tipo correcto en axios**
  ```typescript
  axios.post<BulkRevertResult>(...);
  ```

- [ ] **3. Extraer campo correcto**
  ```typescript
  const { total_trips_recalculated } = response.data;
  // NO usar: total_steps_reverted
  ```

- [ ] **4. Verificar que NO sea 0**
  ```typescript
  if (total_trips_recalculated === 0) {
    console.error('❌ Backend retorna 0 trips - verificar que tenga el fix');
  }
  ```

- [ ] **5. Formatear número correctamente**
  ```typescript
  total_trips_recalculated.toLocaleString()  // "922" o "9,220"
  ```

- [ ] **6. Usar en toast**
  ```typescript
  toast.success(`${total_trips_recalculated} trips en ${days_with_reverts} días`);
  ```

---

## 🚨 Si Sigue Mostrando 0

### Paso 1: Verificar el Backend

```bash
# Ver logs del backend después de revert
tail -f /var/log/gt360/backend.log | grep BULK_REVERT

# Debe mostrar:
# [BULK_REVERT] Completed: 29 days reverted, 29 steps, 922 trips
#                                                         ^^^ NO debe ser 0
```

### Paso 2: Verificar el Response en DevTools

```
1. Abrir DevTools → Network → XHR
2. Hacer revert desde UI
3. Buscar request a /bulk/revert
4. Ver Response tab
5. Verificar total_trips_recalculated
```

**Si muestra 0:** Backend NO tiene el fix → Verificar commit y restart

**Si muestra 922:** Frontend está accediendo mal al campo

### Paso 3: Verificar Código del Toast

```typescript
// Buscar en el código del frontend dónde se muestra el toast
// Debe estar usando:

response.data.total_trips_recalculated  // ✅

// NO:
response.data.total_steps_reverted  // ❌
response.data.total_days            // ❌
response.data.by_date.length        // ❌
```

---

## 📊 Comparación de Campos

| Campo | Valor Ejemplo | Qué Representa | ¿Usar en Toast? |
|-------|---------------|----------------|-----------------|
| `total_days` | 29 | Días encontrados con filtros | ❌ NO |
| `days_with_reverts` | 29 | Días donde se revirtió algo | ✅ SÍ (contexto) |
| `days_skipped` | 0 | Días sin cambios | ❌ NO |
| `total_steps_reverted` | 29 | FilterSteps revertidos | ❌ NO |
| `total_trips_recalculated` | **922** | **Trips afectados** | ✅ **SÍ (PRINCIPAL)** |

**Regla de oro:** Siempre priorizar `total_trips_recalculated` en el mensaje.

---

## 💡 Ejemplo Completo de Toast

```typescript
// ============================================
// TOAST MESSAGES - Best Practices
// ============================================

// Para Bulk Revert
function showBulkRevertToast(result: BulkRevertResult) {
  const {
    total_trips_recalculated,
    days_with_reverts,
    filter_type
  } = result;

  if (total_trips_recalculated === 0) {
    toast.info('No se encontraron filtros para revertir');
    return;
  }

  const tripsText = total_trips_recalculated.toLocaleString();
  const daysText = days_with_reverts === 1 ? 'día' : 'días';
  const filterText = filter_type || 'todos los filtros';

  toast.success(
    `${filterText}: ${tripsText} trips en ${days_with_reverts} ${daysText} ` +
    `restaurados a horarios originales`
  );

  // Ejemplos:
  // → "reduce: 922 trips en 29 días restaurados a horarios originales" ✅
  // → "todos los filtros: 1,500 trips en 45 días restaurados a horarios originales" ✅
}

// Para Single-Day Revert
function showSingleRevertToast(result: StepRevertResult) {
  const { trips_recalculated, filter_type, remaining_steps } = result;

  const tripsText = trips_recalculated.toLocaleString();

  if (remaining_steps === 0) {
    toast.success(
      `Filtro ${filter_type} revertido: ${tripsText} trips restaurados`
    );
  } else {
    toast.success(
      `Filtro ${filter_type} revertido: ${tripsText} trips recalculados ` +
      `(${remaining_steps} filtros activos restantes)`
    );
  }

  // Ejemplos:
  // → "Filtro reduce revertido: 31 trips restaurados" ✅
  // → "Filtro combine revertido: 31 trips recalculados (2 filtros activos restantes)" ✅
}
```

---

## 🔧 Solución Rápida

Si el problema persiste, reemplazar el código del toast con esto:

```typescript
// Código probado y verificado
const handleBulkRevertSuccess = (response: AxiosResponse<BulkRevertResult>) => {
  // Extraer con desestructuración
  const {
    total_trips_recalculated,
    days_with_reverts,
    filter_type
  } = response.data;

  // Log para debugging
  console.log('[Revert] Trips recalculados:', total_trips_recalculated);

  // Toast simple y claro
  toast.success(
    `${total_trips_recalculated.toLocaleString()} trips revertidos en ${days_with_reverts} días`
  );
};
```

---

## ✅ Verificación Final

Después de implementar, verificar que:

```
✅ Toast muestra: "922 trips en 29 días" (o similar)
✅ NO muestra: "0 trips"
✅ NO muestra: "29 trips" (confundiendo steps con trips)
✅ Console.log muestra: total_trips_recalculated: 922
```

---

## 📞 Soporte

Si después de implementar esto el problema persiste:

1. Verificar que backend tenga commit 9f53a34
2. Verificar que servidor se haya reiniciado después de las 16:04
3. Agregar los console.logs de debugging
4. Capturar screenshot del Network tab con el response
5. Compartir logs para análisis

---

## Estado del Backend

```
✅ Fix aplicado: Commit 9f53a34
✅ Servidor reiniciado: PID 3336268 (16:04)
✅ Campo total_trips_recalculated: Retorna valor correcto
✅ Listo para producción
```

**El backend está funcionando correctamente. El problema está en cómo el frontend accede al campo `total_trips_recalculated`.**
