# Análisis: Auto-Aplicación de Filtros a Trips Nuevos

**Fecha:** 2026-01-26
**Estado Actual:** Sistema de Presets IMPLEMENTADO pero con limitación
**Objetivo:** Aplicar filtros automáticamente a trips nuevos del botón "Update"

---

## ✅ **SISTEMA ACTUAL (Ya Implementado)**

### **Existe y Funciona:**

1. **Tabla:** `trips.filter_presets` ✅
2. **Servicio:** `FilterPresetService` ✅
3. **Método:** `auto_apply_preset()` ✅
4. **Integración:** Se llama automáticamente después de import ✅
5. **Endpoints:** CRUD completo de presets ✅

**Ubicación del código:**
- `features/trips/services/filter_preset_service.py:152-266`
- `features/trips/routes/trips_router.py:316-363`
- `features/trips/routes/filter_preset_router.py`

---

## ⚠️ **LIMITACIÓN DETECTADA**

### **Problema:**

El sistema solo aplica filtros a **fechas completamente nuevas**.

```python
# trips_router.py:326
new_dates = [d for d in unique_dates if d not in existing_dates_for_airline]
```

**Esto significa:**

| Situación | Comportamiento Actual | Comportamiento Deseado |
|-----------|----------------------|------------------------|
| **Import fecha nueva (2026-02-20)** | ✅ Auto-aplica preset | ✅ Auto-aplica |
| **Update misma fecha (2026-02-20)** | ❌ NO auto-aplica (fecha ya existía) | ✅ Debería auto-aplicar |

**Ejemplo del problema:**

```
1. Import 10 trips para 2026-02-20 (fecha nueva)
   → Auto-aplica preset ✅
   → 10 trips con filtros ✅

2. Update (botón Update) trae 5 trips MÁS para 2026-02-20
   → Fecha YA existe
   → NO auto-aplica ❌
   → 5 trips SIN filtros ❌

Resultado final:
  - 10 trips CON filtros
  - 5 trips SIN filtros
  - Inconsistencia ❌
```

---

## 🔧 **SOLUCIÓN RECOMENDADA**

### **Propuesta: Aplicar Filtros Activos a Trips Nuevos**

Modificar el sistema para que:
1. Después de insertar trips nuevos
2. Si hay FilterSteps ACTIVOS para ese día (no solo preset)
3. Aplicar esos filtros SOLO a los trips recién insertados

### **Implementación en el Backend**

#### Paso 1: Crear Método para Aplicar a Trips Específicos

```python
# En step_filter_service.py

async def apply_to_specific_trips(
    self,
    location_id: UUID,
    airline: str,
    pick_up_date: date,
    trip_ids: list[UUID],  # Solo estos trips
) -> int:
    """
    Apply active filters to specific trips only.

    Used for auto-applying to newly inserted trips
    without re-processing all trips of the day.

    Returns: Number of trips modified
    """
    # 1. Get active steps for this day
    active_steps_query = (
        Select(FilterStep)
        .Where(FilterStep.location_id == location_id)
        .Where(FilterStep.airline == airline)
        .Where(FilterStep.pick_up_date == pick_up_date)
        .Where(FilterStep.is_active == True)
        .OrderBy(FilterStep.step_order.Asc())
    )
    active_steps = await self.session.exec(active_steps_query).all()

    if not active_steps:
        return 0  # No active filters for this day

    # 2. Get ONLY the specified trips
    trips_query = (
        Select(Trip)
        .Where(Trip.id.In(trip_ids))
        .Where(Trip.trip_type == TripType.OUTBOUND)
        .Where(Trip.status == TripStatus.SCHEDULED)
    )
    trips = await self.session.exec(trips_query).all()

    if not trips:
        return 0

    # 3. Apply each active step in order
    trips_modified = 0

    for step in active_steps:
        self._reset_state()

        # Rebuild config
        config = FilterStepConfig(
            filter_type=step.filter_type,
            pick_up_date=str(pick_up_date),
            windows=[TimeWindow(**w) for w in step.windows]
        )

        # Apply filter to these specific trips
        if config.filter_type == "reduce":
            self._apply_reduce(trips, config)
        elif config.filter_type == "combine":
            self._apply_combine(trips, config)
        elif config.filter_type == "expand":
            await self._apply_expand(trips, config)

        # Persist changes
        now = datetime.utcnow()
        for change in self.changes:
            trip = next((t for t in trips if t.id == change.trip_id), None)
            if trip:
                if trip.original_pick_up_time is None:
                    trip.original_pick_up_time = trip.pick_up_time

                trip.pick_up_time = change.new_time
                trip.current_step_id = step.id
                trip.updated_at = now

                if config.filter_type == "reduce":
                    trip.reduce_applied = True
                elif config.filter_type == "combine":
                    trip.combine_applied = True
                elif config.filter_type == "expand":
                    trip.expand_applied = True

                trip.filtered_at = now
                self.session.add(trip)
                trips_modified += 1

    await self.session.commit()

    logger.info(
        f"[AUTO_APPLY] Applied {len(active_steps)} filters to "
        f"{trips_modified} new trips for {pick_up_date}"
    )

    return trips_modified
```

#### Paso 2: Modificar trips_router.py

```python
# En trips_router.py después de insertar trips (línea ~315)

# ===================================================================
# AUTO-APPLY FILTERS TO NEW TRIPS
# ===================================================================
if trips_to_create and airline:
    from features.trips.services.step_filter_service import StepFilterService

    # Group new trips by date
    trips_by_date = defaultdict(list)
    for trip in trips_to_create:
        trips_by_date[trip.pick_up_date].append(trip.id)

    step_service = StepFilterService(session)
    total_auto_applied = 0

    for pick_up_date, trip_ids in trips_by_date.items():
        # Auto-apply active filters to these new trips
        trips_modified = await step_service.apply_to_specific_trips(
            location_id=location.id,
            airline=airline,
            pick_up_date=pick_up_date,
            trip_ids=trip_ids
        )
        total_auto_applied += trips_modified

        if trips_modified > 0:
            print(
                f"[AUTO_APPLY] ✅ Applied filters to {trips_modified} new trips "
                f"for {pick_up_date}"
            )

    if total_auto_applied > 0:
        print(f"[AUTO_APPLY] Total: {total_auto_applied} trips auto-filtered")
```

---

## 📊 **Comparación de Enfoques**

| Enfoque | Qué Hace | Ventajas | Desventajas |
|---------|----------|----------|-------------|
| **Sistema Actual (Presets)** | Solo aplica a fechas completamente nuevas | ✅ No sobreescribe config manual | ❌ No aplica a Update del mismo día |
| **Solución Propuesta** | Aplica filtros activos a trips nuevos | ✅ Funciona con Update<br>✅ Usa filtros existentes (no solo presets) | ⚠️ Requiere nuevo método en backend |
| **Frontend Re-Aplica** | Frontend llama bulk apply después de Update | ✅ Sin cambios backend | ❌ Re-procesa todos los trips<br>❌ Más lento |

---

## ✅ **Mi Recomendación**

### **Implementar la Solución Propuesta**

**Por qué:**
1. ✅ Resuelve el problema de Update con trips nuevos
2. ✅ Funciona con filtros manuales (no solo presets)
3. ✅ Más eficiente (solo procesa trips nuevos)
4. ✅ Reutiliza toda la lógica existente

**Esfuerzo:**
- ~100 líneas de código nuevo
- 1-2 horas de implementación
- Test y deployment

---

## 📋 **Plan de Implementación**

### Backend (Cambios Necesarios)

#### 1. Crear método `apply_to_specific_trips()`
**Archivo:** `features/trips/services/step_filter_service.py`
**Ubicación:** Después de `apply_step()` (~línea 260)
**Líneas:** ~100 líneas

#### 2. Integrar en trips_router.py
**Archivo:** `features/trips/routes/trips_router.py`
**Ubicación:** Reemplazar bloque auto-preset (líneas 316-363)
**Cambios:** Modificar lógica existente

### Frontend (Sin Cambios)

- ✅ NO requiere cambios
- ✅ Trips vienen automáticamente con filtros
- ✅ Refetch muestra datos correctos

---

## 🎯 **Diferencias Clave**

### **Sistema Actual (Presets):**
```
Criterio: ¿La FECHA es nueva?
  Sí → Auto-aplica preset
  No → Skip (aunque haya trips nuevos)
```

### **Sistema Propuesto:**
```
Criterio: ¿Hay filtros ACTIVOS para este día?
  Sí → Aplicar a trips NUEVOS de ese día
  No → Skip
```

**Ventaja:** Funciona tanto con presets como con filtros manuales.

---

## 🚀 **Implementación Inmediata (Sin Cambios Backend)**

Si quieren una solución YA sin modificar backend:

```javascript
// Frontend: Después de Update

async function handleUpdateTrips() {
  // 1. Fetch nuevos trips
  const updateResult = await updateTripsFromSource();

  // 2. Obtener fechas afectadas
  const affectedDates = getAffectedDates(updateResult);

  // 3. Para cada fecha, verificar si hay filtros activos
  for (const pickUpDate of affectedDates) {
    const stack = await GET(`/stack?pick_up_date=${pickUpDate}`);

    if (stack.steps.length > 0) {
      // Hay filtros activos
      // Re-aplicar bulk a ese día específico
      await POST('/bulk/apply', {
        date_from: pickUpDate,
        date_to: pickUpDate,
        filter_type: stack.steps[0].filter_type,
        windows: stack.steps[0].windows,
        skip_days_with_stack: false  // ← Importante
      });
    }
  }

  // 4. Refetch
  await refetchTrips();
}
```

**Ventajas:**
- ✅ Funciona AHORA
- ✅ Sin esperar cambios backend

**Desventajas:**
- ⚠️ Re-aplica a TODOS los trips (no solo nuevos)
- ⚠️ Más lento

---

## 📝 **Resumen Ejecutivo**

| Aspecto | Estado |
|---------|--------|
| **Sistema de Presets** | ✅ YA EXISTE e implementado |
| **Auto-apply en import** | ✅ YA FUNCIONA |
| **Limitación actual** | ⚠️ Solo fechas nuevas, no trips nuevos del mismo día |
| **Solución temporal** | Frontend puede re-aplicar después de Update |
| **Solución definitiva** | Backend: Crear `apply_to_specific_trips()` |

**Mi recomendación:** Implementar `apply_to_specific_trips()` en el backend para resolver el caso de Update correctamente.

---

## ¿Quieres que implemente la solución en el backend?

Puedo crear el código completo de `apply_to_specific_trips()` y modificar `trips_router.py` para que funcione exactamente como quieres.
