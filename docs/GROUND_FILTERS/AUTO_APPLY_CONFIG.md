# Auto-Apply Filters Configuration

> **Estado: ✅ IMPLEMENTADO** (2026-02-03)

## Objetivo
Sistema donde la configuración de filtros se guarda automáticamente y se aplica a nuevos trips importados.

---

# DOCUMENTACIÓN PARA FRONTEND

## Sistema de Configuración Automática de Filtros

### Resumen Ejecutivo

El sistema de filtros ahora guarda automáticamente la configuración cuando el usuario aplica filtros. Esta configuración se aplica automáticamente a nuevos trips importados.

**El frontend NO necesita hacer cambios de UI** - el comportamiento es completamente automático e implícito.

### Comportamiento del Sistema

```
┌─────────────────────────────────────────────────────────────────────┐
│                    FLUJO AUTOMÁTICO                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. Usuario aplica filtros (reduce, combine, expand)                │
│     ↓                                                               │
│     Backend GUARDA automáticamente esta configuración               │
│     como "preset" para location + airline                           │
│                                                                     │
│  2. Usuario sube nuevo archivo Excel con trips                      │
│     ↓                                                               │
│     Backend APLICA automáticamente los filtros guardados            │
│     a todos los trips nuevos                                        │
│                                                                     │
│  3. Usuario modifica filtros (agrega combine, quita reduce, etc.)   │
│     ↓                                                               │
│     Backend ACTUALIZA automáticamente el preset                     │
│                                                                     │
│  4. Usuario hace "Revertir Todos" (bulk revert)                     │
│     ↓                                                               │
│     Backend ELIMINA el preset                                       │
│     Próximos imports NO tendrán filtros automáticos                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Escenarios Detallados

#### Escenario 1: Primera Configuración
```
Estado inicial: No hay preset para WN en Airport X

1. Usuario aplica Reduce (-15 min) al día 2026-02-10
   → Backend guarda preset: { reduce: -15min }

2. Usuario aplica Combine al día 2026-02-10
   → Backend actualiza preset: { reduce: -15min, combine: 10-20min }

3. Usuario sube trips para 2026-02-15, 2026-02-16
   → Backend aplica automáticamente reduce y combine a esos días
```

#### Escenario 2: Modificación de Configuración
```
Estado: Preset existente { reduce: -15min, combine: 10-20min }

1. Usuario aplica Expand al día 2026-02-10
   → Backend actualiza preset: { reduce: -15min, combine: 10-20min, expand: ±10min }

2. Usuario sube nuevos trips
   → Backend aplica reduce, combine y expand automáticamente
```

#### Escenario 3: Eliminar Configuración
```
Estado: Preset existente { reduce, combine, expand }

1. Usuario hace "Revertir Todos los Filtros" (bulk revert)
   → Backend elimina TODOS los filtros de todas las fechas
   → Backend ELIMINA el preset

2. Usuario sube nuevos trips
   → NO se aplican filtros (no hay preset)
```

#### Escenario 4: Trips en Fechas Existentes
```
Día 2026-02-10 ya tiene trips con filtros aplicados (reduce + combine)

1. Usuario sube más trips para el mismo día 2026-02-10
   → Backend aplica los MISMOS filtros (reduce + combine) a los nuevos trips
   → Los trips existentes NO se modifican (ya tienen los filtros)
```

### Lo que el Frontend Debe Saber

| Acción del Usuario | Qué Pasa Automáticamente |
|--------------------|--------------------------|
| Aplicar cualquier filtro | Configuración se guarda/actualiza |
| Subir trips (con config existente) | Filtros se aplican automáticamente |
| Revertir un filtro específico | Configuración se actualiza (sin ese filtro) |
| Revertir TODOS los filtros | Configuración se ELIMINA |
| Borrar location | Configuración se elimina (cascade) |

### NO Requiere Cambios en Frontend

- ❌ NO necesita botón "Guardar configuración"
- ❌ NO necesita indicador visual de "configuración activa"
- ❌ NO necesita confirmación antes de aplicar filtros
- ✅ El comportamiento es 100% automático e implícito

### Endpoints Existentes (Sin Cambios)

Los mismos endpoints que ya usa el frontend:

```
POST /v2/.../filters/step/apply     → Aplica filtro (auto-guarda config)
POST /v2/.../filters/bulk/apply     → Aplica bulk (auto-guarda config)
POST /v2/.../filters/bulk/revert    → Revierte bulk (puede eliminar config)
POST /trips/upload                  → Sube trips (auto-aplica config)
```

### Logs Esperados al Subir Trips

Con configuración activa:
```
[AUTO_PRESET] Processing 100 new trips across 5 dates
[AUTO_TRIPS] 2026-02-10: Has stack, will apply to 20 new trips
[AUTO_TRIPS] 2026-02-15: No stack, will create from preset
[AUTO_PRESET] ✅ Applied filters: 1 new stacks, 4 existing stacks, 85 trips affected
```

Sin configuración:
```
[AUTO_PRESET] Not applied: No preset found for this location+airline
```

---

## Comportamiento Deseado

### 1. Auto-Guardar Configuración
- Cada vez que el usuario **aplica** un filtro → el preset se actualiza automáticamente
- La configuración incluye: tipos de filtros activos + ventanas de tiempo
- Es por **location + airline** (cada aerolínea tiene su propia configuración)

### 2. Auto-Aplicar a Nuevos Trips
- Al importar trips nuevos → se aplica la configuración guardada
- Para fechas CON stack existente → se aplica ese stack a los nuevos trips
- Para fechas SIN stack → se crea stack desde el preset

### 3. Eliminar Configuración
- Al hacer **bulk revert** de todos los filtros → se elimina el preset
- Al **borrar la location** → se elimina el preset (cascade delete)

## Cambios Requeridos en Backend

### A. Auto-guardar preset al aplicar filtro
**Archivo:** `features/trips/services/step_filter_service.py`
- En `apply_step()`: después de aplicar exitosamente, guardar/actualizar preset

### B. Eliminar preset al hacer bulk revert
**Archivo:** `features/trips/services/step_filter_service.py`
- En `revert_bulk()`: si no quedan filtros activos, eliminar el preset

### C. Cascade delete de preset al borrar location
**Archivo:** `shared/db/schemas/trips/filter_presets.py`
- Verificar que `location_id` tiene `on_delete="CASCADE"`

## Cambios Requeridos en Frontend

### NO se requieren cambios de UI
- El comportamiento es implícito/automático
- No se necesita indicador visual
- No se necesita botón de "Guardar preset"

### Lo que el frontend debe saber:
1. Al aplicar filtros → automáticamente se guardan para futuros imports
2. Al subir trips → los filtros se aplican automáticamente si existe configuración
3. Al hacer bulk revert → se elimina la configuración automática

## Archivos Modificados

1. **`features/trips/services/step_filter_service.py`**
   - ✅ `apply_step()`: Auto-guarda preset después de aplicar filtro
   - ✅ `_revert_step_internal()`: Actualiza preset después de revertir
   - ✅ `revert_bulk()`: Elimina preset si no quedan filtros activos
   - ✅ Nuevo método: `_auto_save_preset()` - Guarda el stack del día como preset
   - ✅ Nuevo método: `_update_preset_after_revert()` - Actualiza/elimina preset después de revert

2. **`features/trips/services/filter_preset_service.py`**
   - ✅ Nuevo método: `auto_apply_to_new_trips()` - Aplica filtros a trips específicos

3. **`features/trips/routes/trips_router.py`**
   - ✅ Modificado para llamar `auto_apply_to_new_trips()` con IDs de trips

4. **`shared/db/schemas/trips/filter_presets.py`**
   - ✅ Ya tiene `on_delete="CASCADE"` en `location_id`

## Verificación

Para probar que funciona:

1. Aplicar filtro reduce a un día → verificar en logs: `[AUTO_PRESET] Saved preset...`
2. Aplicar filtro combine al mismo día → verificar que preset se actualiza
3. Subir nuevos trips → verificar en logs: `[AUTO_TRIPS] Applied...`
4. Hacer bulk revert de todos los filtros → verificar: `[AUTO_PRESET] Deleted preset...`
5. Subir trips después del revert → verificar: `[AUTO_PRESET] Not applied: No preset found...`
