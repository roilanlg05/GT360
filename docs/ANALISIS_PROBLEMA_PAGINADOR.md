# Análisis del Problema: Paginador se Marea y Muestra Datos Antiguos

**Fecha:** 2026-01-14
**Reportado por:** Usuario (Manager)
**Severidad:** Alta - Afecta UX crítico

---

## 🔴 Síntomas Reportados

1. **El paginador se marea, se pierde, se queda en loading**
2. **Muestra "rastros de paginación antigua que ya fue eliminada"**
3. **No toma la "fuente de la verdad"**
4. **No está actualizando correctamente**
5. **Posiblemente no espera a que se carguen todos los trips antes de actualizar**
6. **Hay una paginación de 50 trips en la tabla**

---

## 🔍 Root Cause Analysis

### Problema #1: RACE CONDITION en Upload Masivo ⚠️ CRÍTICO

**Arquitectura Actual:**
```
Usuario sube Excel con 1000 trips
         ↓
Backend: BulkInsert en chunks de 5000
         ↓
Database: Trigger AFTER INSERT por CADA trip
         ↓
1000 pg_notify() individuales → Redis → WebSocket
         ↓
Frontend recibe 1000 eventos "insert" UNO POR UNO
         ↓
Mientras tanto...
Frontend ya llamó loadInitialTrips() y wsReconnect()
```

**El Problema:**

Cuando subes un archivo con 1000 trips de **Marzo 2026**:

1. **Backend procesa el Excel:**
   ```python
   # features/trips/routes/trips_router.py:184-189
   for i in range(0, len(trips_to_create), chunk_size):
       batch = trips_to_create[i : i + chunk_size]
       await session.BulkInsert(batch)  # Inserta 5000 a la vez
   ```

2. **Database Trigger se ejecuta POR CADA trip:**
   ```sql
   -- Trigger: __sub_trips_insert_17b502_fn
   PERFORM pg_notify('__sub_...', json_build_object(...))
   -- ¡Se ejecuta 1000 veces! Una por cada trip insertado
   ```

3. **Backend responde al frontend INMEDIATAMENTE:**
   ```python
   # Línea 258-268
   return JSONResponse({
       "status": "ok",
       "uploaded_rows": 1000,  # ← Frontend recibe esto ANTES de que terminen los eventos WS
       "trips": [... primeros 50 ...]
   })
   ```

4. **Frontend recibe respuesta del upload:**
   ```typescript
   // UpdateTripsButton dispara evento
   window.dispatchEvent(new CustomEvent('trips-uploaded', {...}))

   // schedule-dashboard-client.tsx inmediatamente:
   handleUploaded() {
       setRowsData([])              // ← Limpia la tabla
       loadInitialTrips()           // ← Carga trips vía REST
       wsReconnect()                // ← Reconecta WebSocket
   }
   ```

5. **PERO... los 1000 eventos WebSocket AÚN están llegando:**
   ```
   WS Event 1: insert trip de Marzo  ←┐
   WS Event 2: insert trip de Marzo   │
   WS Event 3: insert trip de Marzo   │ Llegan DURANTE
   ...                                 │ el loadInitialTrips()
   WS Event 998: insert trip de Marzo │ y wsReconnect()
   WS Event 999: insert trip de Marzo │
   WS Event 1000: insert trip de Marzo ┘
   ```

**Resultado:**
- `storeTrips` está siendo actualizado 1000 veces (uno por evento)
- `rowsData` está siendo actualizado por REST API + eventos WS simultáneos
- `availableMonths` se recalcula 1000 veces mientras llegan eventos
- El estado queda **inconsistente y "mareado"**
- Loading states se superponen
- Se ven "rastros de datos antiguos" porque hay múltiples fuentes actualizando al mismo tiempo

---

### Problema #2: `availableMonths` Calculado en Cliente de Forma Ineficiente

**Arquitectura Actual:**
```typescript
// src/lib/trips/available-months.ts (aproximado)
// Frontend calcula qué meses existen basándose en storeTrips

const availableMonths = useMemo(() => {
  return extractAvailableMonths(storeTrips, airline)
}, [storeTrips, airline])

// storeTrips puede tener MILES de trips (snapshot completo de la location)
// Se recalcula cada vez que llega UN evento WebSocket
```

**El Problema:**
1. **No es source of truth:** Frontend confía en datos del WebSocket para decidir qué meses mostrar
2. **Ineficiente:** Procesa miles de trips client-side solo para extraer meses únicos
3. **Race conditions:** Si el snapshot del WebSocket no está completo, falta meses
4. **Lento:** Con muchos trips, el cálculo client-side es costoso

**Evidencia del documento:**
```
Lines 973:
const months = extractAvailableMonths(storeTrips, "UAL")

// Filtra storeTrips (TODOS los trips de la location) por airline
// Extrae años/meses únicos
// MonthYearPicker solo muestra meses con trips de UAL
```

---

### Problema #3: Paginación de 50 + Eventos WebSocket = Confusión

**Escenario:**
1. Usuario sube 1000 trips de Marzo
2. Usuario navega a Marzo
3. REST API carga primeros 50 trips (skip=0, limit=50)
4. `rowsData = [trip1...trip50]`
5. `serverTotalTrips = 1000`

**PERO...**
- Mientras carga, llegan eventos WebSocket de los otros 950 trips
- Frontend filtra por mes actual: "¿Este trip es de Marzo? Sí → agregar a rowsData"
- `rowsData` se actualiza con trips que deberían estar en páginas 2, 3, 4...
- Resultado: **Duplicados** y **orden inconsistente**

**Código del problema:**
```typescript
// schedule-dashboard-client.tsx:1087-1105
// Cuando llega evento WebSocket "insert"

const filtered = addedTrips.filter(
  trip => trip.date >= from && trip.date <= to  // ← Filtra por mes actual
)

// Agrega a rowsData si pasa el filtro
setRowsData(prev => {
  const seen = new Set(prev.map(r => r.id))
  const merged = [...prev]
  for (const trip of filtered) {
    if (!seen.has(trip.id)) {
      merged.push(trip)  // ← Se agrega aunque esté en página 3, 4, etc.
    }
  }
  return merged
})
```

**Resultado:**
- La tabla muestra 50 trips de REST + X trips de WebSocket
- Total en tabla > 50
- Paginación se rompe porque `rowsData.length` ya no coincide con `skip/limit`

---

### Problema #4: No Espera a que Termine el Upload

**Código Actual:**
```python
# Backend: features/trips/routes/trips_router.py:240-268

await session.commit()  # ← Commits a DB

return JSONResponse({    # ← Responde INMEDIATAMENTE
    "status": "ok",
    "uploaded_rows": created
})

# Los triggers ya se ejecutaron y enviaron pg_notify()
# PERO el sistema de WebSocket puede estar aún procesando y enviando eventos
```

**El Problema:**
- Frontend asume que cuando recibe respuesta 201, el upload está "completo"
- Llama `loadInitialTrips()` y `wsReconnect()` inmediatamente
- PERO los eventos WebSocket AÚN están siendo procesados por el backend y enviados
- No hay sincronización entre "commit exitoso" y "eventos WebSocket enviados"

---

## 🎯 Soluciones Propuestas

### Solución #1: Batching de Eventos WebSocket (RECOMENDADO) ⭐

**Implementar en Backend:**

```python
# features/trips/routes/trips_router.py

# DESPUÉS del commit, enviar UN SOLO evento batch
await session.commit()

# Publicar evento consolidado
batch_event = {
    "type": "batch_insert",
    "location_id": str(location.id),
    "airline": airline,
    "trips_count": created,
    "months_affected": [
        {"month": 2, "year": 2026, "count": 1000}  # Ejemplo: 1000 trips de Marzo
    ],
    "message": f"{created} trips uploaded successfully"
}

await redis.publish(
    f"loc:{location.id}",
    json.dumps(batch_event)
)

# NO enviar 1000 eventos individuales
```

**Ventajas:**
- ✅ UN solo evento en lugar de 1000
- ✅ Frontend puede reaccionar de forma atómica
- ✅ No hay race conditions
- ✅ Mucho más eficiente
- ✅ Estado consistente

**Cambio requerido en Database:**
```sql
-- Deshabilitar el trigger SOLO durante bulk inserts
-- O modificar el trigger para ignorar inserts en batch
```

---

### Solución #2: Nuevo Endpoint `/airlines` y `/months` (IMPLEMENTADO PARCIALMENTE) ⭐

**Ya implementamos `/airlines`**, ahora falta `/months`:

```python
@router.get("/v1/locations/{location_id}/months")
async def get_available_months(
    location_id: str,
    airline: Optional[str] = None,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager", "driver"]))
):
    """
    Retorna todos los meses disponibles para una location y airline.
    Mucho más eficiente que calcular client-side desde storeTrips.
    """
    from uuid import UUID

    try:
        location_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de location inválido")

    # Validar existencia de location
    location = await session.exec(
        Select(Location).Where(Location.id == location_uuid)
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location no encontrada")

    # Query SQL optimizada
    # Extrae DISTINCT year/month y cuenta trips
    query = """
        SELECT
            EXTRACT(YEAR FROM pick_up_date)::int AS year,
            EXTRACT(MONTH FROM pick_up_date)::int AS month,
            COUNT(*)::int AS trips_count
        FROM trips.trips
        WHERE location_id = :location_id
    """

    params = {"location_id": location_uuid}

    if airline:
        query += " AND airline ILIKE :airline"
        params["airline"] = f"%{airline}%"

    query += """
        GROUP BY year, month
        ORDER BY year DESC, month DESC
    """

    from sqlalchemy import text
    result = await session.execute(text(query), params)
    rows = result.fetchall()

    months = [
        {
            "year": row[0],
            "month": row[1] - 1,  # JavaScript usa 0-11
            "count": row[2]
        }
        for row in rows
    ]

    return {
        "location_id": location_id,
        "location_name": location.name,
        "airline": airline,
        "months": months,
        "total_months": len(months)
    }
```

**Ejemplo de Response:**
```json
{
  "location_id": "6d636fef-0a01-4126-87e5-2759f4ec4074",
  "location_name": "SDF",
  "airline": "WN",
  "months": [
    { "year": 2026, "month": 2, "count": 1341 },  // Marzo (month=2 en JS)
    { "year": 2026, "month": 1, "count": 890 },   // Febrero
    { "year": 2026, "month": 0, "count": 750 }    // Enero
  ],
  "total_months": 3
}
```

**Ventajas:**
- ✅ Source of truth = Backend (no WebSocket)
- ✅ Query SQL optimizada (GROUP BY)
- ✅ Respuesta pequeña (~1KB vs cargar todos los trips)
- ✅ No depende de snapshot del WebSocket
- ✅ Siempre actualizado

---

### Solución #3: Debounce y Mejores Loading States en Frontend

**Implementar en Frontend:**

```typescript
// schedule-dashboard-client.tsx

const handleUploaded = useCallback(async (detail: UploadedDetail) => {
  console.log('📤 Upload completed, syncing...')

  // 1. Mostrar loading overlay
  setIsUploadSyncing(true)

  // 2. Esperar un pequeño delay para que terminen eventos WebSocket
  await new Promise(resolve => setTimeout(resolve, 1000))  // 1 segundo

  // 3. Limpiar estado
  setRowsData([])
  setServerTotalTrips(null)
  setNextSkip(0)

  // 4. Desconectar WebSocket temporalmente para evitar eventos durante carga
  wsDisconnect()

  // 5. Esperar un poco más
  await new Promise(resolve => setTimeout(resolve, 500))

  // 6. Cargar datos frescos vía REST
  await loadInitialTrips()

  // 7. Reconectar WebSocket (recibirá snapshot limpio)
  await wsReconnect()

  // 8. Ocultar loading
  setIsUploadSyncing(false)

  console.log('✅ Sync complete')
}, [loadInitialTrips, wsReconnect, wsDisconnect])
```

**Ventajas:**
- ✅ Evita race conditions con delays estratégicos
- ✅ Desconecta WebSocket durante sincronización
- ✅ Estado más predecible
- ✅ Mejor UX con loading states claros

**Desventajas:**
- ⚠️ No resuelve la causa raíz (sigue habiendo 1000 eventos)
- ⚠️ Depende de timing (puede fallar si el upload es muy grande)

---

### Solución #4: Deshabilitar Trigger Durante Bulk Insert

**Implementar en Backend:**

```python
# features/trips/routes/trips_router.py

async def upload_trips(...):
    # ... código existente ...

    try:
        # DESHABILITAR trigger temporalmente
        await session.execute(text("""
            ALTER TABLE trips.trips DISABLE TRIGGER __sub_trips_insert_17b502
        """))

        # Hacer el bulk insert SIN notificaciones
        if trips_to_create:
            for i in range(0, len(trips_to_create), chunk_size):
                batch = trips_to_create[i : i + chunk_size]
                await session.BulkInsert(batch)

        # REACTIVAR trigger
        await session.execute(text("""
            ALTER TABLE trips.trips ENABLE TRIGGER __sub_trips_insert_17b502
        """))

        # Hacer commit
        await session.commit()

        # DESPUÉS del commit, enviar UN evento batch manualmente
        batch_event = {
            "type": "batch_insert",
            "location_id": str(location.id),
            "trips_count": created,
            # ... metadata ...
        }
        await redis.publish(f"loc:{location.id}", json.dumps(batch_event))

    except Exception as e:
        # Asegurarse de reactivar el trigger si hubo error
        await session.execute(text("""
            ALTER TABLE trips.trips ENABLE TRIGGER __sub_trips_insert_17b502
        """))
        await session.rollback()
        raise
```

**Ventajas:**
- ✅ Elimina completamente los 1000 eventos individuales
- ✅ Control total sobre cuándo notificar
- ✅ Un solo evento batch al final
- ✅ Sin race conditions

**Desventajas:**
- ⚠️ Requiere permisos de ALTER TABLE
- ⚠️ Más complejo de mantener
- ⚠️ Riesgo si el trigger no se reactiva por error

---

## 📊 Comparación de Soluciones

| Solución | Complejidad | Impacto | Riesgo | Tiempo impl. |
|----------|-------------|---------|--------|--------------|
| #1: Batching eventos WS | Media | Alto ✅ | Bajo | 2-3 horas |
| #2: Endpoint `/months` | Baja | Alto ✅ | Muy bajo | 1 hora |
| #3: Debounce frontend | Baja | Medio | Bajo | 1 hora |
| #4: Deshabilitar trigger | Alta | Alto ✅ | Medio | 3-4 horas |

---

## ✅ Recomendación Final

**Implementar en este orden:**

### Fase 1: Quick Wins (HOY) ⚡
1. ✅ **Endpoint `/months`** (ya tenemos `/airlines`)
   - Elimina cálculo client-side
   - Source of truth en backend
   - **1 hora de trabajo**

2. **Debounce en frontend**
   - Mejora temporal mientras implementamos batching
   - **1 hora de trabajo**

### Fase 2: Solución Definitiva (ESTA SEMANA) 🎯
3. **Batching de eventos WebSocket**
   - O deshabilitar trigger durante bulk insert
   - Enviar UN evento al final
   - **2-3 horas de trabajo**

### Fase 3: Optimizaciones (OPCIONAL)
4. Caché de `/months` endpoint (5 minutos TTL)
5. Cancelar requests pendientes al cambiar de mes/airline
6. Optimistic updates más inteligentes

---

## 🧪 Testing Plan

### Test 1: Upload Masivo
```
1. Subir Excel con 1000 trips de Marzo 2026
2. Verificar que:
   - ✅ Solo llega UN evento WebSocket (batch_insert)
   - ✅ Frontend no se "marea"
   - ✅ availableMonths se actualiza correctamente
   - ✅ No hay loading infinito
   - ✅ No hay "rastros de datos antiguos"
```

### Test 2: Cambio de Mes
```
1. Estar en Enero con 50 trips cargados
2. Cambiar a Febrero
3. Verificar que:
   - ✅ rowsData se limpia completamente
   - ✅ Carga 50 trips de Febrero (no más, no menos)
   - ✅ serverTotalTrips es correcto
   - ✅ No hay duplicados
```

### Test 3: Scroll Infinito
```
1. Location con 150 trips de Marzo
2. Cargar inicial (50 trips)
3. Scroll → Load more (50 más)
4. Scroll → Load more (50 más)
5. Verificar que:
   - ✅ Total = 150 trips
   - ✅ Sin duplicados
   - ✅ Orden correcto
   - ✅ No carga más después de llegar al final
```

---

## 📝 Próximos Pasos

1. **Desarrollador Backend:**
   - [ ] Implementar endpoint `/v1/locations/{id}/months`
   - [ ] Implementar batching de eventos WebSocket
   - [ ] Testing del nuevo endpoint

2. **Desarrollador Frontend:**
   - [ ] Consumir nuevo endpoint `/months` en lugar de calcular client-side
   - [ ] Implementar debounce en `handleUploaded()`
   - [ ] Manejar nuevo evento `batch_insert` del WebSocket
   - [ ] Testing de edge cases

3. **QA:**
   - [ ] Ejecutar testing plan completo
   - [ ] Verificar con archivos grandes (1000+ trips)
   - [ ] Verificar comportamiento con múltiples usuarios simultáneos

---

**Última actualización:** 2026-01-14
**Estado:** Análisis completo - Pendiente implementación
**Prioridad:** Alta
