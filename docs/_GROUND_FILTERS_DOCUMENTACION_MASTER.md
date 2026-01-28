# Ground Filters - Índice Master de Documentación

**Última actualización:** 2026-01-24 00:40 CET
**Estado:** ✅ Sistema V2 completo con Preset Global

---

## 📚 Documentación ACTUAL (Usar estas)

### 1. GUÍA PRINCIPAL (V2.1) ⭐
**[GROUND_FILTERS_V1_V2_COMPLETE_GUIDE.md](GROUND_FILTERS_V1_V2_COMPLETE_GUIDE.md)**
- **Versión:** 2.1 (Correcciones aplicadas)
- **Fecha:** 2026-01-23 23:20
- **Contenido:** Guía completa V1 + V2 verificada contra código
- **Para:** Frontend debe usar SOLO este documento
- **Incluye:**
  - Todos los endpoints V1 (9) y V2 (6)
  - Modelos TypeScript actualizados
  - TimeWindow con 8 campos (config por ventana)
  - Rule B correcta (valida contra Combines activos)
  - hotel_names documentado como temporal
  - trip_type='ground' aclarado
  - Ejemplos completos

### 2. PRESET GLOBAL + AUTO-APPLY ⭐
**[FILTER_PRESET_AUTO_APPLY_GUIDE.md](FILTER_PRESET_AUTO_APPLY_GUIDE.md)**
- **Versión:** 1.0
- **Fecha:** 2026-01-24 00:35
- **Contenido:** Sistema de preset global para auto-aplicar filtros al importar
- **Incluye:**
  - 5 endpoints de preset
  - Lógica de auto-apply (SOLO días nuevos)
  - Ejemplos de uso
  - Tests de verificación

### 3. LIFECYCLE Y PERSISTENCIA
**[GROUND_FILTERS_V2_LIFECYCLE_AND_PERSISTENCE.md](GROUND_FILTERS_V2_LIFECYCLE_AND_PERSISTENCE.md)**
- **Fecha:** 2026-01-23 23:47
- **Contenido:** FK Cascades, persistencia, rehidratación UI
- **Confirma:**
  - Windows persisten aunque trips_affected=0
  - Config NO se borra al borrar trips
  - Config SÍ se borra al borrar location (CASCADE)
  - GET /stack incluye windows completos ✅

### 4. CORRECCIONES APLICADAS
**[GROUND_FILTERS_BACKEND_REVIEW_FIXES_RESULTS.md](GROUND_FILTERS_BACKEND_REVIEW_FIXES_RESULTS.md)**
- **Fecha:** 2026-01-23 23:25
- **Contenido:** Checklist de 9 puntos (2 ✅ OK, 7 🔧 FIXED)
- **Para:** Auditoría y QA

### 5. CONFIRMACIÓN FINAL
**[GROUND_FILTERS_V2_CONFIRMACION_FINAL.md](GROUND_FILTERS_V2_CONFIRMACION_FINAL.md)**
- **Fecha:** 2026-01-23 23:49
- **Contenido:** Respuestas a 3 confirmaciones finales
- **Confirma:**
  - trip_type: SOLO 'outbound'
  - Rule B: valida contra Combines activos
  - hotel_names: string temporal

---

## 🗂️ Documentación LEGACY (No usar para desarrollo nuevo)

| Documento | Fecha | Razón |
|-----------|-------|-------|
| GROUND_FILTERS_COMPLETE_ARCHITECTURE.md | Jan 23 23:20 | ⚠️ V1 Legacy (marcado) |
| GROUND_FILTERS_COMPLETE_WORKFLOW*.md | Jan 17 | Obsoleto (pre-V2) |
| GROUND_FILTERS_V4_INDEPENDENT.md | Jan 20 | Obsoleto (pre-V2) |
| GROUND_FILTERS_V5_FRONTEND_GUIDE.md | Jan 21 | Obsoleto (reemplazado por V2.1) |
| GROUND_FILTERS_FRONTEND_DIAGNOSTIC.md | Jan 23 | Diagnóstico temporal |
| GROUND_FILTERS_BACKEND_FIX.md | Jan 23 | Fix temporal (integrado en V2.1) |
| GROUND_FILTERS_FINAL_FIX.md | Jan 23 | Fix temporal (integrado en V2.1) |

---

## ✅ CONFIRMACIONES FINALES

### 1. Documentación Actual = V2.1

**✅ CONFIRMADO:**
- **Documento principal:** `GROUND_FILTERS_V1_V2_COMPLETE_GUIDE.md` (V2.1)
- **Versión:** 2.1 (Correcciones aplicadas)
- **Estado:** Verificado contra código deployado

**Documentos de soporte actuales:**
- `FILTER_PRESET_AUTO_APPLY_GUIDE.md` (Preset system)
- `GROUND_FILTERS_V2_LIFECYCLE_AND_PERSISTENCE.md` (Lifecycle)
- `GROUND_FILTERS_BACKEND_REVIEW_FIXES_RESULTS.md` (Checklist)
- `GROUND_FILTERS_V2_CONFIRMACION_FINAL.md` (Decisiones)

**Frontend/IA debe usar:**
- ✅ `GROUND_FILTERS_V1_V2_COMPLETE_GUIDE.md` (V2.1) como referencia única
- ✅ `FILTER_PRESET_AUTO_APPLY_GUIDE.md` para preset system
- ❌ Cualquier otro doc marcado como Legacy o con fecha < Jan 23

---

### 2. GET /stack Devuelve windows[] Completos

**✅ CONFIRMADO:**

**Verificación en deploy actual:**
```bash
docker exec gt360 python3 -c "from features.trips.models.filter_models import FilterStepInfo; print(list(FilterStepInfo.model_fields.keys()))"

# Output:
['step_id', 'step_order', 'filter_type', 'windows_count', 'windows', 'trips_affected', 'created_at', 'is_active', 'config']
```

**Campo `windows` presente en índice 4 ✅**

**Código deployado:**
```python
# filter_models.py:349
class FilterStepInfo(BaseModel):
    windows: list[dict] = Field(default_factory=list)  # ✅

# step_filter_service.py:337
step_infos.append(FilterStepInfo(
    windows=step.windows or [],  # ✅ Include full windows
))
```

**Response de GET /stack:**
```json
{
  "steps": [
    {
      "step_id": "uuid",
      "windows": [
        {
          "start": "05:00",
          "end": "10:00",
          "enabled": true,
          "minutes_to_reduce": 10,
          "hotel_names": ["Hotel A"]
        }
      ],
      "trips_affected": 15
    }
  ]
}
```

**✅ Frontend PUEDE rehidratar UI exactamente con un solo request GET /stack**

---

## 📊 Sistema Completo Deployado

### Endpoints Totales: 20

| Sistema | Endpoints | Ruta Base |
|---------|-----------|-----------|
| **V1 Filters** | 9 | `/v1/.../trips/filters/...` |
| **V2 Steps** | 6 | `/v2/.../filters/step/...` |
| **V2 Presets** | 5 | `/v2/.../filters/preset` |

### Features Implementadas

| Feature | Estado | Doc |
|---------|--------|-----|
| **V1 Batch filters** | ✅ Producción | V2.1 Guide |
| **V2 Step/Stack filters** | ✅ Producción | V2.1 Guide |
| **Config por ventana** | ✅ Implementado | V2.1 Guide |
| **Rule B contra stack** | ✅ Implementado | V2.1 Guide |
| **No wrap-around** | ✅ Implementado | V2.1 Guide |
| **Combine location match** | ✅ Implementado | V2.1 Guide |
| **Preset Global** | ✅ Implementado | Preset Guide |
| **Auto-apply en import** | ✅ Implementado | Preset Guide |
| **Windows en stack response** | ✅ Implementado | Lifecycle Doc |

---

## 🎯 Para Frontend/IA

**Usar ÚNICAMENTE estos documentos:**

1. **GROUND_FILTERS_V1_V2_COMPLETE_GUIDE.md (V2.1)** - Guía principal
2. **FILTER_PRESET_AUTO_APPLY_GUIDE.md** - Sistema de preset

**Ignorar cualquier documento:**
- Sin "V2.1" en versión
- Con fecha anterior a Jan 23
- Marcado como "Legacy" o "DEPRECATED"

**Datos clave para Frontend:**

```typescript
// TimeWindow con 8 campos (config por ventana)
interface TimeWindow {
  start: string;
  end: string;
  enabled: boolean;
  minutes_to_reduce?: number;  // 1-120
  min_gap?: number;            // 1-60
  max_gap?: number;            // 1-120
  max_shift?: number;          // 1-20
  hotel_names?: string[];      // Temporal (futuro: hotel_ids)
}

// GET /stack devuelve windows completos
interface FilterStepInfo {
  step_id: string;
  step_order: number;
  filter_type: string;
  windows_count: number;
  windows: TimeWindow[];  // ✅ Completos para rehidratar UI
  trips_affected: number;
  created_at: string;
  is_active: boolean;
  config: object;
}
```

---

## ✅ Resumen de Confirmaciones

| Pregunta | Respuesta |
|----------|-----------|
| **Documento principal?** | `GROUND_FILTERS_V1_V2_COMPLETE_GUIDE.md` (V2.1) |
| **Docs legacy?** | Todos con fecha < Jan 23 o sin "V2.1" |
| **GET /stack incluye windows?** | ✅ SÍ, campo `windows: list[dict]` incluido |
| **Frontend puede rehidratar UI?** | ✅ SÍ, con un solo request GET /stack |
| **Sistema listo?** | ✅ SÍ, 100% deployado y verificado |

---

**Deploy actual:** sha256:ceaa2935bed9...
**Última verificación:** 2026-01-24 00:40 CET
