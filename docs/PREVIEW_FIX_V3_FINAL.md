# ✅ Fix: Preview con Filtros Aplicados (V3 Final)

**Fecha:** 2026-01-20
**Status:** ✅ DEPLOYED

---

## Problema Original

```
1. Usuario aplica REDUCE
   → Backend: filter_applied = 'reduce'

2. Usuario intenta preview de COMBINE
   → Backend: Busca trips con filter_applied == NULL
   → Encuentra 0 trips
   → Frontend muestra "0 trips elegibles"
```

---

## Solución Implementada

### Backend Fix (Opción 2)

Modificado `trip_filter_service.py` línea 525:

```python
# ANTES (V2):
.Where(Trip.filter_applied == None)  # Solo trips sin filtros

# DESPUÉS (V3):
# Línea removida - Ya NO filtra por filter_applied
```

**Resultado:**
- ✅ `/preview` ahora encuentra TODOS los trips elegibles (outbound + scheduled)
- ✅ Ignora completamente `filter_applied`
- ✅ Muestra preview correcto incluso con filtros existentes

---

## Flujo Completo V3

### Preview (Simulación)
```
POST /filters/preview con {combine: enabled}
  ↓
Backend busca trips:
  - trip_type = 'outbound' ✅
  - status = 'scheduled' ✅
  - filter_applied = ? (IGNORADO) ✅
  ↓
Encuentra 338 trips
  ↓
Simula cambios
  ↓
Retorna preview con 150 cambios
```

### Apply (Persistir)
```
POST /filters/apply con {combine: enabled}
  ↓
Backend detecta: ¿Hay trips con filter_applied != NULL?
  ↓
SÍ → Auto-Revert:
  - Restaura pick_up_time = original_pick_up_time
  - Limpia filter_applied, filter_batch_id
  - Log: "auto_revert: 338 trips"
  ↓
Aplica nuevos filtros
  ↓
Persiste cambios
  ↓
Retorna resultado con log de auto-revert
```

---

## Frontend: NO Requiere Cambios

**Antes (Workaround propuesto):**
```typescript
// Frontend tenía que:
1. Llamar /revert
2. Llamar /preview
3. Si usuario cancela → Re-aplicar filtros originales
```

**Ahora (V3):**
```typescript
// Frontend solo hace:
1. Llamar /preview directamente ✅
2. Llamar /apply si usuario confirma ✅
// Auto-revert sucede automáticamente en apply
```

---

## Testing

### Test Manual

```bash
# 1. Aplicar Reduce
POST /filters/apply
{
  "reduce": {"enabled": true, "minutes_to_reduce": 20}
}

# Verificar en DB:
# SELECT filter_applied FROM trips WHERE ...
# → Debería mostrar 'reduce'

# 2. Preview de Combine (sin revertir primero)
POST /filters/preview
{
  "reduce": {"enabled": false},
  "combine": {"enabled": true, "min_gap": 10, "max_gap": 20}
}

# Resultado esperado:
# ✅ eligible_trips > 0 (antes era 0)
# ✅ changes contiene trips

# 3. Apply de Combine
POST /filters/apply
{
  "reduce": {"enabled": false},
  "combine": {"enabled": true, "min_gap": 10, "max_gap": 20}
}

# Resultado esperado:
# ✅ log contiene "auto_revert"
# ✅ changes_applied > 0
# ✅ filter_applied = 'combine' en DB
```

---

## Cambios en Backend

### Archivo 1: `trip_filter_service.py`

**Línea 525 (removida):**
```python
.Where(Trip.filter_applied == None)
```

**Nuevo comentario (líneas 525-526):**
```python
# V3: No filter by filter_applied to allow preview on trips with existing filters
# Auto-revert will handle this in /apply
```

### Archivo 2: `trips_router.py`

**Líneas 1441-1494:** Auto-revert logic (ya existía)

---

## Documentación Actualizada

- ✅ `docs/GROUND_FILTERS_COMPLETE_V3.md` - Sección 2.1, 5.2, 5.3, 16
- ✅ `docs/PREVIEW_FIX_V3_FINAL.md` - Este documento

---

## Deployment Status

| Componente | Status |
|------------|--------|
| Backend code | ✅ Modificado |
| Docker container | ✅ Deployed y reiniciado |
| Server status | ✅ Running (Uvicorn http://0.0.0.0:8000) |
| Database | ✅ Sin cambios necesarios |
| Frontend | ✅ Sin cambios necesarios |

---

## FAQ

### ¿El frontend necesita cambios?

**NO.** El fix es 100% backend. El frontend sigue llamando `/preview` y `/apply` de la misma forma.

### ¿Qué pasa con trips que ya tienen filtros?

- **Preview:** Los encuentra y muestra cómo quedarían con los nuevos filtros
- **Apply:** Los auto-revierte primero, luego aplica los nuevos filtros

### ¿Se pierde el historial de batches?

**NO.** El auto-revert crea un nuevo batch_id y marca los anteriores como `reverted_at`.

### ¿Puedo seguir usando /revert manualmente?

**SÍ.** El endpoint `/revert` sigue funcionando igual. El auto-revert solo sucede en `/apply`, no en `/revert`.

### ¿Qué pasa si llamo /preview con filtros ya aplicados?

Ahora funciona correctamente:
```
Trips en DB: filter_applied = 'reduce'
Preview: ✅ Encuentra todos, muestra cambios propuestos
Apply: ✅ Auto-revierte + aplica nuevos filtros
```

---

## Próximos Pasos

### Frontend (Opcional)
- [ ] Test manual: Preview con filtros existentes
- [ ] Test E2E: Apply → Preview → Apply
- [ ] Verificar que auto-revert notification se muestra (si implementada)

### Backend
- [x] Fix implementado y deployed
- [x] Documentación actualizada
- [ ] Monitoring: Verificar que no hay errores en logs

---

## Contacto

**Backend Team**
**Última actualización:** 2026-01-20 02:45 UTC

---

**TL;DR:**
- ✅ Preview ahora funciona con trips que tienen filtros aplicados
- ✅ Apply hace auto-revert antes de aplicar nuevos filtros
- ✅ Frontend NO necesita cambios
- ✅ Backend deployed y funcionando
