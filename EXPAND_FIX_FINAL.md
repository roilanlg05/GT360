# 🔧 FIX FINAL - Expand Respetando min_gap

**Fecha:** 2026-02-11
**Status:** ✅ TESTED Y LISTO PARA IMPLEMENTAR
**Archivo a modificar:** `features/trips/services/step_filter_service.py`

---

## ✅ Verificación Completa

### Tests Ejecutados
- ✅ Test Case 1: Gaps con valor 0 (mismo horario) NO se agrupan
- ✅ Test Case 2: Gaps mixtos (algunos en rango, otros no)
- ✅ Test Case 3: Todos los gaps fuera de rango

### Dependencias Verificadas
- ✅ Solo se llama desde un lugar (`_apply_expand` línea 845)
- ✅ No hay tests unitarios que romper
- ✅ No afecta a `_get_expand_pattern` ni otras funciones
- ✅ `window.min_gap` está disponible en el contexto

---

## 📝 CAMBIOS A APLICAR

### CAMBIO #1: Líneas 845-849

**ANTES:**
```python
# Identify chains within this location group
chains = self._identify_expand_chains(
    group_trips,
    max_gap=window.max_gap,
    max_shift=window.max_shift
)
```

**DESPUÉS:**
```python
# Identify chains within this location group
chains = self._identify_expand_chains(
    group_trips,
    min_gap=window.min_gap,     # ← NUEVO
    max_gap=window.max_gap,
    max_shift=window.max_shift
)
```

---

### CAMBIO #2: Líneas 884-924 (Función completa)

**REEMPLAZAR TODA LA FUNCIÓN `_identify_expand_chains` con:**

```python
def _identify_expand_chains(
    self,
    trips: list[Trip],
    min_gap: int,          # ← NUEVO PARÁMETRO
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
        - [B, C, D]: cadena de 3 trips → se expande con patrón [-10, 0, +10]
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

## 🚀 PASOS PARA IMPLEMENTAR

### 1. Backup del Archivo Original
```bash
cd /home/backend/GT360
cp features/trips/services/step_filter_service.py features/trips/services/step_filter_service.py.backup.$(date +%Y%m%d_%H%M%S)
```

### 2. Abrir el Archivo para Editar
```bash
nano features/trips/services/step_filter_service.py
# O usar tu editor preferido (vim, code, etc.)
```

### 3. Aplicar CAMBIO #1 (Líneas ~845-849)

Buscar:
```python
chains = self._identify_expand_chains(
    group_trips,
    max_gap=window.max_gap,
    max_shift=window.max_shift
)
```

Agregar la línea `min_gap=window.min_gap,`:
```python
chains = self._identify_expand_chains(
    group_trips,
    min_gap=window.min_gap,     # ← AGREGAR ESTA LÍNEA
    max_gap=window.max_gap,
    max_shift=window.max_shift
)
```

### 4. Aplicar CAMBIO #2 (Líneas ~884-924)

Buscar la función:
```python
def _identify_expand_chains(
    self,
    trips: list[Trip],
    max_gap: int,
    max_shift: int
) -> list[list[Trip]]:
```

Reemplazar COMPLETA con la nueva versión (arriba).

**IMPORTANTE:** Reemplazar TODO hasta el `return chains` final (línea ~924).

### 5. Guardar y Verificar Sintaxis
```bash
# Verificar sintaxis Python
python3 -m py_compile features/trips/services/step_filter_service.py

# Si no hay errores, continuar
echo "✅ Sintaxis correcta"
```

### 6. Reiniciar el Backend
```bash
sudo systemctl restart backend
# O el comando que uses para reiniciar tu servicio

# Verificar que arrancó correctamente
sudo systemctl status backend
```

### 7. Verificar Logs
```bash
tail -f /var/log/backend.log | grep EXPAND_CHAIN
# O donde estén tus logs

# Buscar líneas como:
# [EXPAND_CHAIN] Applied pattern [-10, 0, +10] to chain of 3 trips
```

---

## 🧪 TESTING MANUAL

### Caso de Prueba 1: Mismo Horario

**Setup en el Frontend:**
1. Ir a la tabla de trips del día que tiene trips con MISMO horario (ejemplo: dos trips a las 08:00)
2. Configurar Expand:
   - Gap mínimo: 20 min
   - Gap máximo: 25 min
   - Max shift: 10 min
3. Aplicar filtro

**Resultado Esperado:**
- Los trips con gap=0 NO deberían estar en la misma cadena
- Solo trips con gaps de 20-25 minutos se expandirían
- Verificar en la tabla que los trips con mismo horario NO se movieron juntos

### Caso de Prueba 2: Preview

**Setup:**
1. Antes de aplicar, hacer PREVIEW del filtro
2. Revisar la sección "Changes" y "Exclusions"

**Verificar:**
- `trips_modified`: Debería ser MENOR que antes (porque no expande trips fuera de rango)
- En exclusions, deberías ver trips individuales excluidos por tener gaps fuera de rango

### Caso de Prueba 3: Logs

```bash
grep "EXPAND_CHAIN" /var/log/backend.log

# Deberías ver:
# [EXPAND_CHAIN] Applied pattern [-10, 0, +10] to chain of 3 trips at Hotel→Airport
```

---

## 📊 COMPORTAMIENTO ESPERADO VS ANTERIOR

### Ejemplo Concreto

**Trips:**
```
A: 08:00
B: 08:00 (gap=0)
C: 08:22 (gap=22 desde B)
D: 08:45 (gap=23 desde C)
```

**Config:** min_gap=20, max_gap=25, max_shift=10

#### ANTES (Con Bug):
```
Cadena identificada: [A, B, C, D]
Patrón aplicado: [-10, 0, 0, +10]

Resultado:
A: 08:00 → 07:50
B: 08:00 → 08:00 (sin cambio)
C: 08:22 → 08:22 (sin cambio)
D: 08:45 → 08:55

❌ Gap B-C: 22 min (sigue en rango problemático)
```

#### DESPUÉS (Con Fix):
```
Cadenas identificadas:
- A: cadena de 1 trip → excluida
- [B, C, D]: cadena de 3 trips

Patrón aplicado a [B,C,D]: [-10, 0, +10]

Resultado:
A: 08:00 → 08:00 (sin cambio, excluido)
B: 08:00 → 07:50
C: 08:22 → 08:22 (sin cambio)
D: 08:45 → 08:55

✅ Gap B-C: 32 min (fuera de rango problemático)
✅ Gap C-D: 33 min (fuera de rango problemático)
```

---

## ⚠️ POSIBLES EFECTOS OBSERVABLES

### 1. Menos Trips Expandidos

**Antes:** Todos los trips con gap <= max_gap se agrupaban
**Ahora:** Solo trips con gap en [min_gap, max_gap] se agrupan

**Impacto:** Algunos trips que antes se expandían ahora NO se expandirán (comportamiento correcto).

### 2. Más Exclusiones

**En Preview verás más trips en la sección "Exclusions":**
```json
{
  "operation": "expand_chain(1 trips)",
  "reason": "Chain of 1 trip (excluded, needs at least 2)",
  "trip_ids": ["uuid-A"]
}
```

Esto es normal y correcto.

### 3. Frontend: Menos Badges Naranja

Si el frontend muestra badges/iconos naranjas para trips expandidos, verás MENOS badges porque menos trips se expandirán.

Esto es el comportamiento correcto - solo trips con gaps problemáticos deben expandirse.

---

## 🔄 ROLLBACK (Si hay problemas)

### Restaurar Backup
```bash
cd /home/backend/GT360
cp features/trips/services/step_filter_service.py.backup.FECHA features/trips/services/step_filter_service.py
sudo systemctl restart backend
```

### Revertir Filtros Aplicados (Opcional)
Si aplicaste el filtro a trips reales y quieres revertir:

```bash
# Usar endpoint de revert
curl -X POST http://localhost:8000/api/filters/revert/last \
  -H "Content-Type: application/json" \
  -d '{
    "location_id": "uuid",
    "airline": "WN",
    "pick_up_date": "2026-02-11"
  }'
```

---

## ✅ CHECKLIST DE IMPLEMENTACIÓN

- [ ] Backup del archivo original creado
- [ ] CAMBIO #1 aplicado (línea 845: agregar `min_gap`)
- [ ] CAMBIO #2 aplicado (función completa reemplazada)
- [ ] Sintaxis verificada (py_compile)
- [ ] Backend reiniciado
- [ ] Logs verificados (sin errores)
- [ ] Test manual caso 1: Mismo horario
- [ ] Test manual caso 2: Preview
- [ ] Test manual caso 3: Aplicar y verificar resultado
- [ ] Documentar cambio en changelog/notas

---

## 📖 DOCUMENTACIÓN A ACTUALIZAR (Opcional)

Si quieres actualizar la documentación:

**Archivo:** `docs/GROUND_FILTERS/BACKEND_CHANGES_EXPAND_SYSTEM.md`

**Sección a actualizar:**
```markdown
### Umbral de Cadena

Antes: Umbral = max_gap

Ahora: Solo agrupa trips con gap en [min_gap, max_gap]

Esto asegura que:
- Trips muy juntos (gap < min_gap) NO se expanden
- Trips ya separados (gap > max_gap) NO se expanden
- Solo trips con gap problemático se expanden
```

---

**STATUS:** ✅ READY TO DEPLOY
**RIESGO:** BAJO (cambio localizado, sin dependencias externas)
**TESTING:** ✅ 3 casos de prueba verificados
**REVERSIBILIDAD:** ✅ Alta (backup + rollback simple)
