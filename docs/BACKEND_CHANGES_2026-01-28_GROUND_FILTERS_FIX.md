# Backend Changes: Ground Filters Performance & Race Condition Fix

**Fecha:** 2026-01-28
**Autor:** Backend Team
**Estado:** Deployed
**Para:** Frontend Developer

---

## Resumen Ejecutivo

Se implementaron 3 cambios críticos en el backend que **requieren ajustes en el frontend** para aprovechar las mejoras:

| Cambio | Problema Resuelto | Impacto Frontend |
|--------|-------------------|------------------|
| Single Commit Pattern | Race condition + Performance | Eliminar workarounds de delay |
| Conteo Independiente | Notificaciones incorrectas | Usar nuevo campo en response |
| WebSocket Inmediato | Delay innecesario | Refetch más rápido |

---

## Cambio 1: Single Commit Pattern

### Problema Anterior

```
Backend hacía ~308 commits secuenciales para revertir 112 steps:
- Commit 1: Reset trips
- Commit 2-N: Re-apply cada step activo
- Delay 50ms (insuficiente)
- WebSocket enviado

Frontend recibía WebSocket ANTES de que commits estuvieran propagados.
```

**Resultado:** Columna Ground Filters mostraba estado "un paso atrás"

### Solución Implementada

```
Backend ahora hace 1 SINGLE COMMIT atómico:
- Acumula TODOS los cambios en memoria
- Single commit al final
- WebSocket enviado DESPUÉS del commit
- Sin delay necesario
```

**Archivo modificado:** `features/trips/services/step_filter_service.py`
**Método:** `_revert_step_internal()` (líneas 718-830)

### Impacto en Frontend

#### ANTES (Workarounds que ya NO son necesarios)

```typescript
// schedule-dashboard-client.tsx línea 1606
// Este delay adicional YA NO ES NECESARIO
await new Promise(resolve => setTimeout(resolve, 150))
infiniteScroll.reset()
```

```typescript
// use-trip-filters-v2.ts
// Los 150ms adicionales después del WebSocket YA NO SON NECESARIOS
```

#### DESPUÉS (Recomendado)

```typescript
// Cuando recibas WebSocket "step_reverted":
// Puedes hacer refetch INMEDIATAMENTE sin delays adicionales
case "step_reverted":
  // Sin delay - el commit ya está propagado
  await infiniteScroll.reset()
  break
```

### Verificación

```typescript
// Test: Aplicar 3 filtros y revertir el último
// INMEDIATAMENTE después del WebSocket, los trips deben tener:
// - reduce_applied: true  ✅
// - combine_applied: true ✅
// - expand_applied: false ✅

// Ya NO deberías ver:
// - reduce_applied: false ❌
// - combine_applied: false ❌
```

---

## Cambio 2: Conteo Independiente de Trips

### Problema Anterior

```
Cuando aplicabas filtros en secuencia:
- REDUCE: 25 trips ✅
- COMBINE después: 40 trips ❌ (debería ser ~15)

El conteo incluía trips que ya tenían otros filtros aplicados.
```

### Solución Implementada

El backend ahora retorna `trips_modified` como **trips NUEVOS para este filtro específico** (trips que NO tenían este filtro antes).

**Archivos modificados:** `features/trips/services/step_filter_service.py`
**Métodos:** `apply_step()` y `preview_step()`

### Cambios en el Response

#### StepResult (apply_step, preview_step)

```typescript
// ANTES
interface StepResult {
  trips_modified: number;  // Todos los cambios (acumulativo)
  summary: {
    modified: number;
    excluded: number;
  }
}

// DESPUÉS
interface StepResult {
  trips_modified: number;  // Solo trips NUEVOS para este filtro
  summary: {
    modified: number;       // Igual que trips_modified
    total_changes: number;  // NUEVO: Total de cambios (para debugging)
    excluded: number;
  }
}
```

### Ejemplo de Response

```json
// Después de aplicar REDUCE (primer filtro)
{
  "filter_type": "reduce",
  "trips_modified": 25,
  "summary": {
    "modified": 25,
    "total_changes": 25,
    "excluded": 3
  }
}

// Después de aplicar COMBINE (segundo filtro)
{
  "filter_type": "combine",
  "trips_modified": 15,    // Solo los 15 NUEVOS para combine
  "summary": {
    "modified": 15,
    "total_changes": 30,   // 15 pares = 30 cambios totales
    "excluded": 5
  }
}
```

### Impacto en Frontend - Notificaciones

#### ANTES

```typescript
// toast.success mostraba número incorrecto
toast.success(`${result.trips_modified} trips afectados`)
// Mostraba: "40 trips afectados" (incorrecto para COMBINE)
```

#### DESPUÉS

```typescript
// toast.success ahora muestra número correcto
toast.success(`${result.trips_modified} trips afectados por ${result.filter_type}`)
// Muestra: "15 trips afectados por combine" (correcto)
```

### Para Preview

El preview también retorna conteo independiente:

```typescript
// Preview de COMBINE después de REDUCE
const preview = await previewStep({ filter_type: "combine", ... })

// preview.trips_modified = 15 (solo nuevos para combine)
// preview.summary.total_changes = 30 (total de cambios si necesitas debugging)
```

---

## Cambio 3: WebSocket Sin Delay

### Problema Anterior

```python
# Backend hacía delay de 50ms antes del WebSocket
await asyncio.sleep(0.05)  # 50ms delay
await self._send_revert_notification(...)
```

Este delay era un workaround para la race condition que **ya no existe**.

### Solución Implementada

```python
# Ya no hay delay - el single commit garantiza consistencia
await self.session.commit()  # Single commit atómico
await self._send_revert_notification(...)  # Inmediato
```

### Impacto en Frontend

El WebSocket `step_reverted` ahora llega **después** de que el commit esté completamente propagado.

```typescript
// Ya puedes confiar en que cuando recibes el WebSocket,
// los datos en la DB son consistentes
websocket.onmessage = (event) => {
  const data = JSON.parse(event.data)

  if (data.type === "step_reverted") {
    // Refetch inmediato - datos garantizados consistentes
    await refetchTrips()
  }
}
```

---

## Performance Mejorada

### Benchmark Esperado

| Operación | Antes | Después | Mejora |
|-----------|-------|---------|--------|
| Revert 1 step (3 activos) | ~500ms | ~50ms | 10x |
| Revert bulk 28 días | 12-15s | <2s | 6-8x |
| Revert bulk 112 steps | ~15s | <3s | 5x |

### Implicaciones para UX

```typescript
// El loading toast puede ser más corto
const loadingToastId = toast.loading(`Revirtiendo ${filterType}...`, {
  // Ya no necesitas advertencia de "puede tardar varios segundos"
  description: 'Procesando...',
})

// El toast se cierra más rápido porque la operación es más rápida
```

---

## Cambios Requeridos en Frontend

### 1. Eliminar Delays de Workaround

```typescript
// ELIMINAR estos delays que ya no son necesarios:

// En schedule-dashboard-client.tsx
- await new Promise(resolve => setTimeout(resolve, 150))

// En use-trip-filters-v2.ts (si existe delay adicional después del WebSocket)
- await new Promise(resolve => setTimeout(resolve, 150))
```

### 2. Actualizar Tipos (Opcional pero recomendado)

```typescript
// Actualizar interface StepResult si la tienes tipada
interface StepResult {
  step_id: string | null;
  filter_type: "reduce" | "combine" | "expand";
  pick_up_date: string;
  trips_modified: number;  // Ahora es conteo independiente
  changes: TripChange[];
  exclusions: FilterExclusion[];
  summary: {
    modified: number;
    total_changes: number;  // NUEVO campo
    excluded: number;
  };
}
```

### 3. Actualizar Notificaciones

```typescript
// Las notificaciones ahora mostrarán conteos correctos automáticamente
// No necesitas cambiar la lógica, solo verificar que uses trips_modified
toast.success(`${result.trips_modified} trips modificados`)
```

### 4. Simplificar Manejo de WebSocket

```typescript
// ANTES (con workarounds)
case "step_reverted":
  await rehidration.reload()
  await new Promise(resolve => setTimeout(resolve, 150))  // ELIMINAR
  await infiniteScroll.reset()
  break

// DESPUÉS (sin workarounds)
case "step_reverted":
  await rehidration.reload()
  await infiniteScroll.reset()  // Inmediato
  break
```

---

## Testing Checklist

### Test 1: Race Condition Resuelta

```
1. Aplicar REDUCE en un día
2. Aplicar COMBINE
3. Aplicar EXPAND
4. Revertir EXPAND

Esperado:
- Columna Ground Filters muestra [reduce] [combine] INMEDIATAMENTE
- trips tienen reduce_applied=true, combine_applied=true
```

### Test 2: Conteo Independiente

```
1. Aplicar REDUCE → Response: trips_modified = 25
2. Aplicar COMBINE → Response: trips_modified = ~15 (no 40)

Verificar que la notificación muestra el número correcto.
```

### Test 3: Performance

```
1. Aplicar filtros en 28 días
2. Hacer revert bulk

Esperado: Completa en <5 segundos (antes era 12-15s)
```

---

## Compatibilidad

### Backward Compatible?

**SÍ** - Los cambios son backward compatible:

- `trips_modified` sigue existiendo (solo cambió el significado)
- `summary.modified` sigue existiendo
- `summary.total_changes` es NUEVO pero opcional

### Breaking Changes?

**NO** - No hay breaking changes en la API.

El único cambio es el **significado** de `trips_modified`:
- Antes: Total de cambios
- Ahora: Trips únicos nuevos para este filtro

Si tu lógica dependía del comportamiento anterior, usa `summary.total_changes`.

---

## Archivos Modificados en Backend

| Archivo | Líneas | Cambio |
|---------|--------|--------|
| `features/trips/services/step_filter_service.py` | 77-135 | preview_step() con conteo independiente |
| `features/trips/services/step_filter_service.py` | 136-270 | apply_step() con conteo independiente |
| `features/trips/services/step_filter_service.py` | 718-830 | _revert_step_internal() con single commit |

---

## Contacto

Si tienes preguntas sobre estos cambios o necesitas ayuda con la integración frontend, contacta al equipo de backend.

**Deployed:** 2026-01-28 18:18 UTC
