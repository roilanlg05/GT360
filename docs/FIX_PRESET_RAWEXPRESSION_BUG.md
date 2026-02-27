# Fix: Filter Preset Auto-Save Bug (RawExpression)

## Resumen

Los filtros preset no se actualizaban correctamente al agregar nuevos pasos (ej: expand despues de reduce). Esto causaba que al importar trips nuevos, solo se auto-aplicara el primer filtro configurado.

---

## Sintoma Reportado

1. Usuario sube trips de Febrero a ubicacion SDF
2. Aplica dos filtros manualmente: **reduce** y luego **expand**
3. Sube trips de Diciembre a la misma ubicacion SDF
4. **Esperado**: Ambos filtros (reduce + expand) se auto-aplican a Diciembre
5. **Real**: Solo **reduce** se aplico a Diciembre

---

## Causa Raiz

### El Bug

En `features/trips/services/filter_preset_service.py`, metodo `create_or_update_preset`, el path de **CREATE** (cuando el preset no existe aun):

```python
# ANTES (con bug)
preset = FilterPresetDB(
    id=preset_id,
    location_id=location_id,
    airline=airline,
    stack_template=stack_template,
    created_by=user_id,
)
self.session.add(preset)
await self.session.commit()
# ❌ FALTA: await self.session.refresh(preset)

return FilterPresetResponse(
    ...
    created_at=preset.created_at,   # ← RawExpression, NO datetime
    updated_at=preset.updated_at,   # ← RawExpression, NO datetime
    ...
)
```

### Por que ocurre

1. El modelo ORM `FilterPresetDB` define `created_at` y `updated_at` con `default=now` de psqlmodel
2. `now` genera un `RawExpression` que se traduce a `NOW()` en SQL
3. Despues del `session.commit()`, la base de datos tiene el datetime correcto, pero el **objeto Python** retiene el `RawExpression`
4. Al construir `FilterPresetResponse` (modelo Pydantic), la validacion falla porque `RawExpression` no es un `datetime` valido

### Error en logs

```
[AUTO_PRESET] Failed to save preset: 2 validation errors for FilterPresetResponse
created_at: Input should be a valid datetime [type=datetime_type, input_value=<psqlmodel.orm.column.RawExpression>, input_type=RawExpression]
updated_at: Input should be a valid datetime [type=datetime_type, input_value=<psqlmodel.orm.column.RawExpression>, input_type=RawExpression]
```

Este error se repitio **28+ veces** en los logs de Docker.

### Cadena de Fallo Completa

```
1. Usuario aplica filtro "reduce" a Febrero
   → apply_step() ejecuta exitosamente
   → _auto_save_preset() se llama
   → create_or_update_preset() CREA preset con stack_template=[reduce]
   → session.commit() → OK en DB
   → FilterPresetResponse(created_at=RawExpression) → FALLA ❌
   → _auto_save_preset() captura el error silenciosamente
   → Preset en DB: [reduce] ✓ (se guardo correctamente en DB)

2. Usuario aplica filtro "expand" a Febrero
   → apply_step() ejecuta exitosamente
   → _auto_save_preset() se llama
   → create_or_update_preset() detecta preset existente → path UPDATE
   → get_preset() consulta DB
   → Identity map de SQLAlchemy retorna objeto cacheado con RawExpression
   → FilterPresetResponse(created_at=RawExpression) → FALLA ❌
   → _auto_save_preset() captura el error silenciosamente
   → Preset en DB: SIGUE SIENDO [reduce] (nunca se actualizo a [reduce, expand])

3. Usuario sube trips de Diciembre
   → auto_apply_to_new_trips() lee preset de DB
   → Preset tiene stack_template = [reduce] (solo un filtro)
   → Solo "reduce" se aplica a Diciembre
   → "expand" nunca se aplica ❌
```

---

## Solucion

### Cambio Aplicado

**Archivo**: `features/trips/services/filter_preset_service.py`
**Linea**: 91 (path CREATE de `create_or_update_preset`)

```python
# DESPUES (fix aplicado)
self.session.add(preset)
await self.session.commit()
await self.session.refresh(preset)  # ← FIX: resuelve RawExpression a datetime real

return FilterPresetResponse(
    ...
    created_at=preset.created_at,   # ← ahora es datetime correcto
    updated_at=preset.updated_at,   # ← ahora es datetime correcto
    ...
)
```

### Que hace `session.refresh()`

- Recarga el objeto ORM desde la base de datos
- Reemplaza `RawExpression` con los valores reales (`datetime`) que la DB genero
- Es una operacion segura, ya usada 20+ veces en el codebase

---

## Impacto del Fix

### Callers Beneficiados

| Caller | Ubicacion | Efecto |
|--------|-----------|--------|
| `_auto_save_preset()` | `step_filter_service.py:1703` | Preset se actualiza correctamente despues de cada filtro |
| `PUT /presets` | `filter_preset_router.py:56` | Endpoint retorna respuesta valida |
| `POST /presets/save-current` | `filter_preset_router.py:122` | Endpoint retorna respuesta valida |
| `POST /presets/auto-apply` | `filter_preset_router.py:258` | Endpoint retorna respuesta valida |

### Sin Efectos Secundarios

- No cambia firmas de funciones ni tipos de retorno
- `session.refresh()` es patron establecido en el codebase
- El path UPDATE no se ve afectado (usa `datetime.utcnow()` directamente)
- `get_preset()` funcionara correctamente una vez que el identity map tenga datos reales

---

## Evidencia en Base de Datos

Antes del fix, la DB mostraba:

```sql
-- Preset de SDF solo tenia [reduce]
SELECT stack_template FROM trips.filter_presets
WHERE location_id = '9c341be7-3145-4db7-9211-ede11493f3a1';
-- Resultado: [{"filter_type": "reduce", "windows": [...]}]
-- Faltaba: expand

-- Diciembre solo tenia reduce steps
SELECT DISTINCT filter_type FROM trips.filter_steps
WHERE location_id = '9c341be7-...' AND pick_up_date >= '2025-12-01';
-- Resultado: solo "reduce" (0 expand steps)

-- Febrero si tenia ambos (aplicados manualmente)
SELECT DISTINCT filter_type FROM trips.filter_steps
WHERE location_id = '9c341be7-...' AND pick_up_date >= '2025-02-01' AND pick_up_date < '2025-03-01';
-- Resultado: "reduce", "expand"
```

---

## Pasos para Verificar el Fix

1. **Reiniciar el backend** para que tome el cambio
2. **Aplicar filtros manualmente** a un dia (reduce + expand)
3. **Verificar en DB** que el preset tiene ambos filtros:
   ```sql
   SELECT stack_template FROM trips.filter_presets
   WHERE location_id = '<location_id>';
   ```
4. **Subir trips nuevos** para un dia diferente
5. **Verificar** que ambos filtros se auto-aplicaron

### Para corregir datos existentes de Diciembre

El preset actual en DB solo tiene `[reduce]`. Para que Diciembre tenga ambos filtros:

1. Aplicar manualmente expand a cualquier dia de la ubicacion SDF
2. El `_auto_save_preset` ahora guardara `[reduce, expand]` correctamente
3. Los proximos uploads auto-aplicaran ambos filtros

O alternativamente, re-aplicar expand manualmente a los dias de Diciembre que lo necesiten.
