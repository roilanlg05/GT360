# Solución: Fix para Múltiples Windows y Contador de Preview

**Fecha:** 2026-01-29
**Implementación:** Propuesta

---

## Solución 1: Fix Notificación con 0 Trips

### Problema

Cuando se reaplica un filtro con múltiples windows, la notificación muestra "0 trips" aunque SÍ hubo cambios.

### Solución: Enviar Ambos Conteos

**Modificar** `_send_step_notification()` para enviar tanto conteo independiente como total:

```python
# Línea 1165-1199
async def _send_step_notification(
    self,
    location_id: UUID,
    airline: str,
    step_id: UUID,
    filter_type: str,
    trips_affected: int,
    total_changes: int = None,  # ← NUEVO parámetro
):
    """Send notification when a step is applied."""
    from shared.redis.redis_client import redis_client
    import json

    # Si total_changes no se provee, usar trips_affected
    if total_changes is None:
        total_changes = trips_affected

    # Mensaje inteligente
    if trips_affected == 0 and total_changes > 0:
        message = f"Filter step re-applied: {filter_type} ({total_changes} trips updated)"
    else:
        message = f"Filter step applied: {filter_type} ({trips_affected} new trips)"

    event = {
        "type": "step_applied",
        "location_id": str(location_id),
        "airline": airline,
        "step_id": str(step_id),
        "filter_type": filter_type,
        "trips_affected": trips_affected,     # Solo nuevos
        "total_changes": total_changes,        # Total modificados ← NUEVO
        "timestamp": datetime.utcnow().isoformat(),
        "message": message
    }

    channel = f"loc:{location_id}"
    await safe_redis_call(
        redis_client.publish,
        channel,
        json.dumps(event),
        context=f"publish {channel}",
    )

    logger.info(
        f"[STEP_FILTER] Notification sent: step={step_id}, "
        f"filter={filter_type}, new={trips_affected}, total={total_changes}"
    )
```

**Llamada actualizada** en `apply_step()` línea 272:

```python
await self._send_step_notification(
    location_id, airline, step_id, config.filter_type,
    trips_affected=independent_count,
    total_changes=len(self.changes)  # ← Agregar total
)
```

### Frontend Actualizado

```typescript
// WebSocket handler
websocket.onmessage = (event) => {
  const { filter_type, trips_affected, total_changes } = event;

  if (trips_affected === 0 && total_changes > 0) {
    // Re-aplicación
    toast.info(`${total_changes} trips re-aplicados (${filter_type})`);
  } else {
    // Nueva aplicación
    toast.success(`${trips_affected} trips nuevos (${filter_type})`);
  }
};
```

---

## Solución 2: Contador de Trips Nuevos ANTES de Preview

### Problema

El usuario quiere saber cuántos trips NUEVOS se aplicarían **ANTES** de hacer preview.

### Solución: Mejorar Endpoint de Eligibility

**Modificar** `get_eligibility()` para aceptar `filter_type` y contar trips específicos:

```python
async def get_eligibility(
    self,
    location_id: UUID,
    airline: str,
    pick_up_date_str: str,
    filter_type: str = None,  # ← NUEVO parámetro opcional
) -> EligibilityResult:
    """
    Check filter eligibility for a day.

    If filter_type is provided, returns breakdown of trips that:
    - Already have this filter applied
    - Would be NEW for this filter
    """
    pick_up_date = date.fromisoformat(pick_up_date_str)

    # Get all eligible trips
    trips = await self._get_eligible_trips(location_id, airline, pick_up_date)

    # Count by hotel
    by_hotel: dict[str, int] = defaultdict(int)
    already_filtered = 0
    already_with_filter_type = 0

    for trip in trips:
        by_hotel[trip.pick_up_location or "Unknown"] += 1

        # General: ¿tiene algún filtro?
        if trip.original_pick_up_time is not None:
            already_filtered += 1

        # Específico: ¿tiene ESTE filtro?
        if filter_type:
            filter_flag = f"{filter_type}_applied"
            if getattr(trip, filter_flag, False):
                already_with_filter_type += 1

    # Calcular trips nuevos para este filtro
    trips_new_for_filter = None
    if filter_type:
        trips_new_for_filter = len(trips) - already_with_filter_type

    return EligibilityResult(
        location_id=location_id,
        airline=airline,
        pick_up_date=pick_up_date_str,
        filter_type=filter_type,  # ← NUEVO
        total_trips=len(trips),
        eligible_trips=len(trips),
        already_filtered=already_filtered,
        trips_with_filter=already_with_filter_type,  # ← NUEVO
        trips_new=trips_new_for_filter,              # ← NUEVO
        by_hotel=dict(by_hotel),
    )
```

### Actualizar Modelo EligibilityResult

```python
# features/trips/models/filter_models.py
class EligibilityResult(BaseModel):
    location_id: UUID
    airline: str
    pick_up_date: str
    filter_type: Optional[str] = None  # ← NUEVO
    total_trips: int
    eligible_trips: int
    already_filtered: int
    trips_with_filter: Optional[int] = None  # ← NUEVO: trips con ESTE filtro
    trips_new: Optional[int] = None          # ← NUEVO: trips SIN este filtro
    by_hotel: dict[str, int]
```

### Uso en Frontend

```typescript
// ANTES de mostrar modal de preview
const eligibility = await fetch(
  `/v2/locations/${id}/airlines/${airline}/filters/eligibility?` +
  `pick_up_date=${date}&filter_type=reduce`
);

console.log(`Total trips: ${eligibility.total_trips}`);
console.log(`Ya tienen Reduce: ${eligibility.trips_with_filter}`);
console.log(`Trips NUEVOS: ${eligibility.trips_new}`);

// Mostrar en UI
<Button onClick={handlePreview}>
  Preview Changes
  <Badge>{eligibility.trips_new} new trips</Badge>
</Button>
```

---

## Implementación Completa

### Paso 1: Modificar _send_step_notification()

**Archivo:** `features/trips/services/step_filter_service.py` línea 1165

```python
async def _send_step_notification(
    self,
    location_id: UUID,
    airline: str,
    step_id: UUID,
    filter_type: str,
    trips_affected: int,
    total_changes: int = None,
):
    if total_changes is None:
        total_changes = trips_affected

    if trips_affected == 0 and total_changes > 0:
        message = f"Filter re-applied: {filter_type} ({total_changes} trips updated)"
    else:
        message = f"Filter applied: {filter_type} ({trips_affected} new trips)"

    event = {
        "type": "step_applied",
        "location_id": str(location_id),
        "airline": airline,
        "step_id": str(step_id),
        "filter_type": filter_type,
        "trips_affected": trips_affected,
        "total_changes": total_changes,  # ← NUEVO campo
        "timestamp": datetime.utcnow().isoformat(),
        "message": message
    }

    # ... resto igual
```

### Paso 2: Actualizar Llamada en apply_step()

**Línea 272:**

```python
await self._send_step_notification(
    location_id, airline, step_id, config.filter_type,
    trips_affected=independent_count,
    total_changes=len(self.changes)  # ← Agregar
)
```

### Paso 3: Mejorar get_eligibility()

**Línea 393:**

```python
async def get_eligibility(
    self,
    location_id: UUID,
    airline: str,
    pick_up_date_str: str,
    filter_type: str = None,  # ← NUEVO
) -> EligibilityResult:
    pick_up_date = date.fromisoformat(pick_up_date_str)

    trips = await self._get_eligible_trips(location_id, airline, pick_up_date)

    by_hotel = defaultdict(int)
    already_filtered = 0
    trips_with_this_filter = 0

    for trip in trips:
        by_hotel[trip.pick_up_location or "Unknown"] += 1

        if trip.original_pick_up_time is not None:
            already_filtered += 1

        if filter_type:
            filter_flag = f"{filter_type}_applied"
            if getattr(trip, filter_flag, False):
                trips_with_this_filter += 1

    return EligibilityResult(
        location_id=location_id,
        airline=airline,
        pick_up_date=pick_up_date_str,
        filter_type=filter_type,
        total_trips=len(trips),
        eligible_trips=len(trips),
        already_filtered=already_filtered,
        trips_with_filter=trips_with_this_filter,
        trips_new=len(trips) - trips_with_this_filter if filter_type else None,
        by_hotel=dict(by_hotel),
    )
```

### Paso 4: Actualizar EligibilityResult Model

**Archivo:** `features/trips/models/filter_models.py`

```python
class EligibilityResult(BaseModel):
    location_id: UUID
    airline: str
    pick_up_date: str
    filter_type: Optional[str] = None
    total_trips: int
    eligible_trips: int
    already_filtered: int
    trips_with_filter: Optional[int] = None  # Trips con ESTE filtro
    trips_new: Optional[int] = None          # Trips SIN este filtro
    by_hotel: dict[str, int]
```

---

## Frontend: Flujo Completo

```typescript
// 1. Usuario selecciona configuración
const config = {
  filter_type: "reduce",
  pick_up_date: "2026-01-28",
  windows: [...]
};

// 2. ANTES de preview, verificar elegibilidad
const eligibility = await getEligibility(
  locationId,
  airline,
  config.pick_up_date,
  config.filter_type  // ← Pasar tipo
);

// 3. Mostrar contador
<div className="preview-info">
  <p>Total trips: {eligibility.total_trips}</p>
  <p>Ya filtrados: {eligibility.trips_with_filter}</p>
  <p>Trips nuevos: {eligibility.trips_new}</p>  ← Mostrar AQUÍ
</div>

<Button onClick={handlePreview}>
  Preview Changes
  <Badge>{eligibility.trips_new}</Badge>  ← Badge con conteo
</Button>

// 4. Usuario hace preview
const preview = await previewStep(config);

// 5. Mostrar preview con conteo confirmado
<PreviewModal>
  <p>{preview.trips_modified} trips nuevos</p>  ← Confirma el conteo
  <p>{preview.summary.total_changes} cambios totales</p>
  {preview.changes.map(...)}
</PreviewModal>

// 6. Usuario aplica
const result = await applyStep(config);

// 7. WebSocket notification
// Frontend recibe:
{
  "trips_affected": 10,    // Nuevos
  "total_changes": 15      // Total
}

// Mostrar notificación inteligente
if (trips_affected === 0 && total_changes > 0) {
  toast.info(`${total_changes} trips re-aplicados`);
} else {
  toast.success(`${trips_affected} trips nuevos aplicados`);
}
```

---

## Resumen de Cambios

### Backend

| Archivo | Cambio |
|---------|--------|
| `step_filter_service.py` línea 1165 | Agregar `total_changes` a `_send_step_notification()` |
| `step_filter_service.py` línea 272 | Pasar `total_changes` en llamada |
| `step_filter_service.py` línea 393 | Agregar `filter_type` a `get_eligibility()` |
| `filter_models.py` | Actualizar `EligibilityResult` con campos nuevos |

### Frontend

| Componente | Cambio |
|------------|--------|
| WebSocket handler | Leer `total_changes` y mostrar mensaje inteligente |
| Preview UI | Llamar eligibility ANTES con `filter_type` |
| Preview button | Mostrar badge con `trips_new` del eligibility |

---

## Testing

### Test 1: Múltiples Windows (Fix del Bug)

```bash
# Aplicar Reduce con 2 windows
POST /filters/step
Body: {
  "filter_type": "reduce",
  "windows": [
    { "start": "08:00", "end": "12:00", "minutes_to_reduce": 10 },
    { "start": "14:00", "end": "18:00", "minutes_to_reduce": 10 }
  ]
}

# Primera vez:
Notification: {
  "trips_affected": 50,
  "total_changes": 50
}
Mensaje: "50 new trips"

# Re-aplicar (cambio config):
Notification: {
  "trips_affected": 0,     // Ninguno nuevo
  "total_changes": 50      // Pero 50 modificados
}
Mensaje: "50 trips re-aplicados"
```

### Test 2: Eligibility con Tipo

```bash
GET /filters/eligibility?pick_up_date=2026-01-28&filter_type=reduce

Response:
{
  "filter_type": "reduce",
  "total_trips": 100,
  "trips_with_filter": 40,  // Ya tienen reduce_applied
  "trips_new": 60            // Nuevos para reduce
}
```

---

## ¿Procedo con la Implementación?

Estos cambios son:
- ✅ Simples (3-4 archivos)
- ✅ Backward compatible
- ✅ Resuelven ambos problemas

¿Quieres que implemente las soluciones?
