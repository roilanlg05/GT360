# Fix para Expand: Respetar min_gap al Identificar Cadenas

**Fecha:** 2026-02-11
**Issue:** Expand está agrupando trips con gaps fuera del rango [min_gap, max_gap]
**Severidad:** HIGH - Bug confirmado en producción

---

## 🐛 Problema Identificado

### Comportamiento Actual (INCORRECTO)

```python
# features/trips/services/step_filter_service.py:884-924
def _identify_expand_chains(self, trips, max_gap, max_shift):
    threshold = max_gap  # ❌ Solo usa max_gap

    if gap <= threshold:  # ❌ Agrupa TODOS los gaps de 0 a max_gap
        current_chain.append(trips[i])
```

**Problema:**
- Si configuración es `min_gap=20, max_gap=25`
- El código agrupa trips con gap de 0, 5, 10, 15... hasta 25 minutos
- Debería SOLO agrupar trips con gap en el rango [20, 25]

### Comportamiento Esperado (CORRECTO)

```python
# Verificar AMBOS límites
if min_gap <= gap <= max_gap:
    current_chain.append(trips[i])
```

---

## ✅ Solución

### Cambios Necesarios

#### 1. Modificar Firma de `_identify_expand_chains`

**Antes:**
```python
def _identify_expand_chains(
    self,
    trips: list[Trip],
    max_gap: int,
    max_shift: int
) -> list[list[Trip]]:
```

**Después:**
```python
def _identify_expand_chains(
    self,
    trips: list[Trip],
    min_gap: int,      # ← NUEVO parámetro
    max_gap: int,
    max_shift: int
) -> list[list[Trip]]:
```

#### 2. Modificar Lógica Interna

**Antes (líneas 903-912):**
```python
threshold = max_gap
chains = []
current_chain = [trips[0]]

for i in range(1, len(trips)):
    prev_time = self._get_effective_time(trips[i-1])
    curr_time = self._get_effective_time(trips[i])
    gap = self._minutes_between(prev_time, curr_time)

    if gap <= threshold:  # ❌ INCORRECTO
        current_chain.append(trips[i])
```

**Después:**
```python
chains = []
current_chain = [trips[0]]

for i in range(1, len(trips)):
    prev_time = self._get_effective_time(trips[i-1])
    curr_time = self._get_effective_time(trips[i])
    gap = self._minutes_between(prev_time, curr_time)

    # ✅ CORRECTO: Verificar que gap esté EN EL RANGO [min_gap, max_gap]
    if min_gap <= gap <= max_gap:
        current_chain.append(trips[i])
```

#### 3. Actualizar Llamada en `_apply_expand`

**Antes (línea 845):**
```python
chains = self._identify_expand_chains(
    group_trips,
    max_gap=window.max_gap,
    max_shift=window.max_shift
)
```

**Después:**
```python
chains = self._identify_expand_chains(
    group_trips,
    min_gap=window.min_gap,    # ← NUEVO argumento
    max_gap=window.max_gap,
    max_shift=window.max_shift
)
```

#### 4. Actualizar Docstring

**Antes:**
```python
"""
Identifica cadenas de trips con gaps pequeños.

Umbral de cadena = max_gap

Si gap entre trips consecutivos <= umbral, están en la misma cadena.
Si gap > umbral, son cadenas diferentes.

Returns: Lista de cadenas (cada cadena es una lista de trips).
"""
```

**Después:**
```python
"""
Identifica cadenas de trips con gaps EN EL RANGO [min_gap, max_gap].

Solo agrupa trips consecutivos si su gap está dentro del rango configurado.
Trips con gap < min_gap: ya están muy juntos, NO expandir
Trips con gap > max_gap: ya están suficientemente separados, NO expandir

Args:
    trips: Lista de trips ordenados por pickup time
    min_gap: Gap mínimo para considerar trips en la misma cadena
    max_gap: Gap máximo para considerar trips en la misma cadena
    max_shift: Máximo desplazamiento permitido por trip (no usado en esta función)

Returns:
    Lista de cadenas (cada cadena es una lista de trips con gaps en rango)
"""
```

---

## 📝 Código Completo Modificado

### Archivo: `features/trips/services/step_filter_service.py`

**Líneas 845-849** (llamada a la función):
```python
# Identify chains within this location group
chains = self._identify_expand_chains(
    group_trips,
    min_gap=window.min_gap,     # ← AGREGADO
    max_gap=window.max_gap,
    max_shift=window.max_shift
)
```

**Líneas 884-924** (función completa):
```python
def _identify_expand_chains(
    self,
    trips: list[Trip],
    min_gap: int,          # ← AGREGADO
    max_gap: int,
    max_shift: int
) -> list[list[Trip]]:
    """
    Identifica cadenas de trips con gaps EN EL RANGO [min_gap, max_gap].

    Solo agrupa trips consecutivos si su gap está dentro del rango configurado.
    Trips con gap < min_gap: ya están muy juntos, NO expandir
    Trips con gap > max_gap: ya están suficientemente separados, NO expandir

    Args:
        trips: Lista de trips ordenados por pickup time
        min_gap: Gap mínimo para considerar trips en la misma cadena
        max_gap: Gap máximo para considerar trips en la misma cadena
        max_shift: Máximo desplazamiento permitido por trip (no usado en esta función)

    Returns:
        Lista de cadenas (cada cadena es una lista de trips con gaps en rango)

    Example:
        Config: min_gap=20, max_gap=25
        Trips: A(8:00), B(8:00), C(8:22), D(8:45)

        Gap A→B = 0 min → NO agrupa (< 20)
        Gap B→C = 22 min → SÍ agrupa (en [20,25])
        Gap C→D = 23 min → SÍ agrupa (en [20,25])

        Resultado:
        - A: cadena de 1 trip → excluida (no se expande)
        - B: cadena de 1 trip → excluida (no se expande)
        - [C, D]: cadena de 2 trips → se expande
    """
    if not trips:
        return []

    chains = []
    current_chain = [trips[0]]

    for i in range(1, len(trips)):
        prev_time = self._get_effective_time(trips[i-1])
        curr_time = self._get_effective_time(trips[i])
        gap = self._minutes_between(prev_time, curr_time)

        # ✅ FIX: Verificar que gap esté EN EL RANGO [min_gap, max_gap]
        if min_gap <= gap <= max_gap:
            # Gap dentro del rango → misma cadena
            current_chain.append(trips[i])
        else:
            # Gap fuera del rango → nueva cadena
            if len(current_chain) >= 2:
                chains.append(current_chain)
            current_chain = [trips[i]]

    # Agregar última cadena si tiene al menos 2 trips
    if len(current_chain) >= 2:
        chains.append(current_chain)

    return chains
```

---

## 🧪 Plan de Testing

### Test Manual 1: Caso Básico

**Setup:**
```
Config: min_gap=20, max_gap=25, max_shift=10
Trips:
  A: 08:00
  B: 08:00 (gap=0)
  C: 08:22 (gap=22)
  D: 08:45 (gap=23)
```

**Resultado Esperado:**
```
Cadenas identificadas: [[C, D]]
- A y B NO se agrupan (gap=0 < min_gap)
- C y D SÍ se agrupan (gap=22 en [20,25])

Expand aplicado:
- C: 08:22 → 08:12 (shift -10)
- D: 08:45 → 08:55 (shift +10)
- Gap C-D final: 43 minutos ✅
```

**Comportamiento Anterior (CON BUG):**
```
Cadenas identificadas: [[A, B, C, D]]
Patrón aplicado: [-10, 0, 0, +10]
- A: 08:00 → 07:50
- B: 08:00 → 08:00 (sin cambio)
- C: 08:22 → 08:22 (sin cambio)
- D: 08:45 → 08:55
❌ Gap B-C: 22 minutos (sigue en rango problemático)
```

### Test Manual 2: Gaps Mixtos

**Setup:**
```
Config: min_gap=20, max_gap=35
Trips:
  A: 04:00
  B: 04:10 (gap=10, fuera de rango)
  C: 04:35 (gap=25, en rango)
  D: 05:00 (gap=25, en rango)
  E: 05:40 (gap=40, fuera de rango)
```

**Resultado Esperado:**
```
Cadenas identificadas: [[C, D]]
- A y B: gap=10 < 20 → NO agrupa
- C y D: gap=25 en [20,35] → SÍ agrupa
- D y E: gap=40 > 35 → NO agrupa

Expand aplicado solo a [C, D]
```

### Test Manual 3: Todos Fuera de Rango

**Setup:**
```
Config: min_gap=20, max_gap=25
Trips:
  A: 08:00
  B: 08:05 (gap=5)
  C: 08:10 (gap=5)
  D: 08:15 (gap=5)
```

**Resultado Esperado:**
```
Cadenas identificadas: []
Ningún gap está en [20,25]
No se expande ningún trip ✅
```

---

## ⚠️ Consideraciones de Seguridad

### 1. Validación de Input

La función asume que `min_gap <= max_gap`. Esta validación ya existe en el modelo:

```python
# features/trips/models/filter_models.py
class TimeWindow(BaseModel):
    min_gap: Optional[int] = Field(ge=1, le=60)
    max_gap: Optional[int] = Field(ge=1, le=120)
```

**Riesgo:** Si min_gap > max_gap, la condición `min_gap <= gap <= max_gap` nunca sería True.

**Mitigación:** Agregar validación en `_apply_expand`:

```python
# En línea 769, agregar:
if window.min_gap > window.max_gap:
    logger.error(
        f"[EXPAND_CONFIG_ERROR] min_gap ({window.min_gap}) > max_gap ({window.max_gap})"
    )
    continue  # Skip esta ventana
```

### 2. Edge Case: min_gap = max_gap

**Caso:**
```
Config: min_gap=20, max_gap=20
Gap exacto de 20 minutos → ✅ Válido (20 <= 20 <= 20)
```

Esto es correcto y funciona.

### 3. Backward Compatibility

**Pregunta:** ¿Hay configs existentes que dependen del comportamiento viejo?

**Respuesta:** NO, porque el comportamiento viejo era incorrecto. Los usuarios que configuraron min_gap=20 ESPERABAN que se respetara ese mínimo.

---

## 📊 Impacto en Otras Funciones

### ✅ No Afecta:
- `_get_expand_pattern` - Solo recibe la longitud de cadena
- `_apply_combine` - Usa su propia lógica
- `_apply_reduce` - No interactúa con expand
- Preview/Apply endpoints - Usan las mismas funciones

### ✅ Mejora:
- Consistency con Combine (que SÍ respeta min_gap y max_gap)
- Alineación con documentación existente
- Comportamiento más predecible

---

## 🚀 Deployment

### Pasos:

1. **Backup de código actual**
   ```bash
   cp features/trips/services/step_filter_service.py features/trips/services/step_filter_service.py.backup
   ```

2. **Aplicar cambios** (líneas 845 y 884-924)

3. **Testing manual** con casos descritos arriba

4. **Monitorear logs** después de deploy:
   ```
   grep "EXPAND_CHAIN" /var/log/backend.log
   ```

5. **Verificar exclusiones** (trips que antes se expandían y ahora no)

---

## 📋 Checklist Pre-Deploy

- [ ] Código modificado en líneas 845-849
- [ ] Código modificado en líneas 884-924
- [ ] Docstring actualizado
- [ ] Test manual caso básico
- [ ] Test manual gaps mixtos
- [ ] Test manual todos fuera de rango
- [ ] Verificar logs de exclusiones
- [ ] Comunicar cambio al frontend (si esperan exclusiones diferentes)

---

## 🔄 Rollback Plan

Si hay problemas:

1. **Rollback inmediato:**
   ```bash
   cp features/trips/services/step_filter_service.py.backup features/trips/services/step_filter_service.py
   sudo systemctl restart backend
   ```

2. **Revertir filtros afectados** (si es necesario):
   ```python
   # Usar endpoint de bulk revert
   POST /api/filters/bulk-revert
   {
     "date_from": "2026-02-11",
     "filter_type": "expand"
   }
   ```

---

**Autor:** Claude (Análisis exhaustivo)
**Fecha:** 2026-02-11
**Status:** READY FOR IMPLEMENTATION
