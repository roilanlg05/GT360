# Diagnóstico Final: Bug de Configuración Perdida al Hacer F5

**Fecha:** 2026-01-26 04:55
**Severidad:** CRÍTICA - Afecta UX del sistema
**Status:** En investigación

---

## 🔴 RESUMEN DEL BUG CONFIRMADO

### Síntomas

```
1. Usuario aplica filtro Reduce (bulk a todos los futuros)
   → Backend procesa: 29 días, 461 trips ✅
   → Frontend muestra: success ✅

2. Usuario hace F5 (refresh)
   → Frontend llama: GET /stack?pick_up_date=2026-01-01
   → Backend retorna: steps: [] (vacío) ❌
   → Frontend muestra: Filtro apagado ❌

3. PERO los trips mantienen filtros aplicados
   → reduce_applied: true ✅
   → original_pick_up_time guardado ✅
   → Tiempos modificados ✅
```

---

## ✅ CONFIRMADO: No es Problema de Datos Viejos

El usuario confirmó que **eliminó la location antes de la prueba**, por lo tanto:

- ❌ NO son datos inconsistentes del pasado
- ✅ ES un bug activo en el código del backend
- ✅ ES reproducible con data limpia

---

## 🔬 INVESTIGACIÓN DEL CÓDIGO

### Backend: Flujo de apply_bulk()

**Archivo:** `features/trips/services/step_filter_service.py:1382-1496`

```python
async def apply_bulk(...):
    # 1. Obtener fechas con trips elegibles
    dates = await self._get_dates_with_eligible_trips(
        location_id, airline, date_from, date_to
    )
    # dates = [2026-01-01, 2026-01-02, ..., 2026-01-29]  (29 días)

    # 2. Iterar por cada fecha
    for pick_up_date in dates:
        # 3. Llamar apply_step para CADA día
        result = await self.apply_step(location_id, airline, day_config)
        #                              ↑ Debería crear FilterStep para cada día

        days_processed += 1  # 29 días procesados
```

### Backend: Flujo de apply_step()

**Archivo:** `features/trips/services/step_filter_service.py:182-258`

```python
async def apply_step(...):
    # 1. Crear FilterStep
    step_id = uuid4()
    filter_step = FilterStep(
        id=step_id,
        location_id=location_id,
        airline=airline,
        pick_up_date=pick_up_date,  # ← Fecha específica del día
        is_active=True,              # ← Marcado como activo
        windows=[...],               # ← Configuración guardada
        trips_affected=len(self.changes)
    )
    self.session.add(filter_step)  # ← Agregar a sesión

    # 2. Modificar trips
    for change in self.changes:
        trip.reduce_applied = True
        trip.current_step_id = step_id
        self.session.add(trip)

    # 3. Commit TODO
    await self.session.commit()    # ← Guardar en PostgreSQL

    logger.info(f"[STEP_FILTER] Applied step {step_id}: {len(self.changes)} trips modified")
```

**Conclusión del código:**
- ✅ El código se ve **correcto**
- ✅ **Debería** crear FilterStep para cada día
- ✅ **Debería** hacer commit

---

## 🚨 POSIBLES CAUSAS DEL BUG

### Teoría 1: Problema de Fechas - ¿Qué Días Procesó Realmente?

**Sospecha:**
```
Backend procesa: 2026-01-02, 2026-01-03, ..., 2026-01-30 (29 días)
                 ↑ NO incluye 2026-01-01 (sin trips elegibles ese día)

Frontend busca: GET /stack?pick_up_date=2026-01-01
                ↑ Día que NO se procesó

Resultado: Vacío (correcto según el backend)
```

**Para verificar:**
- Ver el array `by_date` en la respuesta del backend
- Confirmar si incluye `2026-01-01`

---

### Teoría 2: Commit Falla Silenciosamente

**Sospecha:**
```python
await self.session.commit()

# Si esto falla pero NO lanza excepción...
# Los trips se quedan en caché pero no en DB
```

**Evidencia en contra:**
- El código tiene try/except que debería capturar errores
- Si fallara, el frontend vería HTTP 500, no success
- Poco probable

---

### Teoría 3: Transacción se Rollbackea Después

**Sospecha:**
```python
# apply_step hace commit
await self.session.commit()  # ✅ Guardado

# Pero luego apply_bulk llama a siguiente apply_step
# con la MISMA sesión...
# ¿Podría causar un rollback implícito?
```

**Para verificar:**
- Revisar si session.commit() persiste entre llamadas
- Ver si hay rollback automático

---

## 🔍 INFORMACIÓN NECESARIA PARA EL DIAGNÓSTICO FINAL

### Del Frontend (Logs):

1. **¿Qué días procesó el backend?**
   ```javascript
   console.log('Backend result by_date:', result.by_date);
   // Debería mostrar array con pick_up_date de cada día procesado
   ```

2. **¿2026-01-01 fue procesado?**
   ```javascript
   const day0101 = result.by_date.find(d => d.pick_up_date === '2026-01-01');
   console.log('2026-01-01 procesado:', day0101);
   // Si es null → No se procesó (no había trips ese día)
   ```

3. **¿Qué fecha usa para GET /stack?**
   ```javascript
   console.log('Rehidratando fecha:', pickUpDate);
   // Debe coincidir con un día que fue procesado
   ```

### Del Backend (DB):

```sql
-- Ver qué fechas tienen FilterSteps guardados
SELECT DISTINCT pick_up_date, COUNT(*) as steps_count
FROM trips.filter_steps
WHERE location_id = 'd9f81f73-3059-4bcf-a980-47cca92fe594'
  AND airline = 'WN'
  AND is_active = true
GROUP BY pick_up_date
ORDER BY pick_up_date;

-- ¿Hay step para 2026-01-01?
```

---

## 🎯 DIAGNÓSTICO PRELIMINAR

Basándome en la evidencia disponible, **la causa más probable es:**

### **Teoría 1: Mismatch de Fechas** (80% probabilidad)

```
Backend procesa fechas: 2026-01-02 a 2026-01-30 (29 días)
                        ↑ NO incluye 2026-01-01 (sin trips ese día)

Frontend rehidrata: GET /stack?pick_up_date=2026-01-01
                    ↑ Día que NO tiene FilterStep

Resultado: steps: [] (correcto - ese día no se procesó)
```

**Esto explicaría:**
- ✅ Por qué backend dice success (procesó 29 días correctamente)
- ✅ Por qué trips tienen filtros (de fechas 2026-01-02+)
- ✅ Por qué GET /stack está vacío (2026-01-01 no se procesó)

**Solución (Frontend):**
- Al rehidratar, usar la primera fecha que SÍ fue procesada
- O guardar en localStorage qué fechas fueron procesadas
- O usar una fecha diferente como "selected date"

---

## 📋 PASOS PARA CONFIRMAR

1. **Pedir al usuario que ejecute esto después de Apply:**
   ```javascript
   console.log('Días procesados:', result.by_date.map(d => d.pick_up_date));
   // Ver si incluye 2026-01-01
   ```

2. **Ejecutar query SQL:**
   ```sql
   SELECT pick_up_date, is_active
   FROM trips.filter_steps
   WHERE location_id = 'd9f81f73-3059-4bcf-a980-47cca92fe594'
     AND airline = 'WN'
   ORDER BY pick_up_date;
   ```

3. **Si 2026-01-01 NO aparece:**
   - ✅ Confirmado: Teoría 1 es correcta
   - El problema es que el frontend busca en una fecha sin filtros
   - Solución: Frontend debe buscar en una fecha que SÍ fue procesada

4. **Si 2026-01-01 SÍ aparece con is_active=true:**
   - ❌ Hay un bug más profundo en get_stack()
   - Necesitaría investigación adicional

---

## ⚠️ RECOMENDACIÓN INMEDIATA

**No tocar el código del backend todavía.**

Primero confirmar:
- ¿Qué días procesó el apply_bulk?
- ¿En qué fecha busca el GET /stack?
- ¿Coinciden?

Si NO coinciden → Problema del frontend (lógica de selección de fecha)
Si SÍ coinciden → Problema del backend (guardar/recuperar FilterSteps)

---

**Estado:** Esperando confirmación de fechas procesadas vs fecha de rehidratación
