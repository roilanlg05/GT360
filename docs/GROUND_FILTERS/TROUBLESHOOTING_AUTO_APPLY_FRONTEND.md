# Troubleshooting: Auto-Aplicación de Filtros No Funciona

**Para:** Equipo Frontend
**Fecha:** 2026-01-26
**Síntoma:** Los trips nuevos NO tienen filtros aplicados automáticamente después de usar el botón "Update"

---

## 🎯 Sistema Esperado vs Realidad

### ✅ **Lo que DEBERÍA pasar:**

```
1. Usuario configura preset para ONT/WN
   → Preset guardado en backend

2. Usuario presiona "Update" → Llegan trips de Marzo 2026
   → Backend detecta fechas nuevas
   → Backend auto-aplica preset
   → Trips YA vienen con filtros

3. Frontend hace refetch
   → Trips muestran reduce_applied: true
   → Columna Ground muestra tiempos modificados
```

### ❌ **Lo que ESTÁ pasando:**

```
1. Usuario presiona "Update"
   → Llegan trips nuevos

2. Backend (no sabemos qué hace)
   → ???

3. Frontend hace refetch
   → Trips NO tienen filtros
   → reduce_applied: false
   → Columna Ground muestra "—"
```

---

## 🔍 **Diagnóstico Paso a Paso**

### **Paso 1: Verificar que el Preset Existe**

#### En el Backend (PostgreSQL)

```sql
-- Conectar a PostgreSQL y ejecutar:
SELECT
    id,
    location_id,
    airline,
    stack_template,
    created_at
FROM trips.filter_presets
WHERE airline = 'WN';

-- Resultado esperado:
-- Si retorna 0 rows → ❌ NO hay preset configurado
-- Si retorna 1+ rows → ✅ Preset existe
```

#### Desde el Frontend (API)

```javascript
// Test en consola del navegador
const response = await fetch(
  '/v2/locations/YOUR_LOCATION_ID/airlines/WN/filters/preset',
  {
    headers: {
      'Authorization': `Bearer ${yourToken}`
    }
  }
);

const preset = await response.json();
console.log('Preset:', preset);

// Resultado esperado:
// Status 200 + data → ✅ Preset existe
// Status 404 → ❌ NO hay preset (este es el problema más común)
```

**Si NO hay preset:**
- ✅ Solución: Crear preset con `POST /preset`
- Ver sección "Crear Preset" más abajo

---

### **Paso 2: Verificar Logs del Backend Durante Import**

Cuando presionas "Update", el backend debe mostrar estos logs:

```
[AUTO_PRESET] Existing dates for {location}/{airline}: X days
[AUTO_PRESET] Detected Y new dates (out of Z total)
[AUTO_PRESET] Preset found for location=..., airline=WN. Processing Y dates
[AUTO_PRESET] Cloning preset to 2026-03-01
[AUTO_PRESET] Applied reduce to 2026-03-01: 25 trips modified
[AUTO_PRESET] Completed. Processed Y days, skipped 0 days, affected N trips
```

**Cómo ver los logs:**

```bash
# SSH al servidor backend
tail -f /var/log/gt360/backend.log | grep -E "AUTO_PRESET|AUTO_FILTER"

# Mientras presionas "Update" en el frontend
```

**Escenarios posibles:**

| Log que Ves | Diagnóstico | Solución |
|-------------|-------------|----------|
| `[AUTO_PRESET] No preset found` | ❌ No hay preset configurado | Crear preset |
| `[AUTO_PRESET] No new dates` | ⚠️ Todas las fechas ya existían | Verificar que sean fechas nuevas |
| `[AUTO_PRESET] Applied preset to X days` | ✅ Funcionó correctamente | Verificar por qué frontend no ve los cambios |
| Sin logs de AUTO_PRESET | ❌ El código no se está ejecutando | Verificar versión del backend |

---

### **Paso 3: Verificar la Respuesta del Endpoint de Import**

El endpoint `POST /v1/trips/upload-trips` debería retornar información de auto-apply.

#### Request

```javascript
// Cuando haces import/update
const formData = new FormData();
formData.append('file', excelFile);

const response = await axios.post(
  `/v1/trips/upload-trips?airport=ONT&provider=amadeus&airline=WN`,
  formData
);

console.log('Import response:', response.data);
```

#### Response Esperado

```json
{
  "created": 150,
  "trips": [...],
  "hotels": [...],

  // ← BUSCA ESTE CAMPO (puede no existir en response actual)
  "auto_preset_result": {
    "applied": true,
    "days_processed": 3,
    "trips_affected": 150,
    "message": "Filtros aplicados automáticamente"
  }
}
```

**Verificar:**

```javascript
// Después de import
if (response.data.auto_preset_result) {
  console.log('✅ Auto-apply ejecutado:', response.data.auto_preset_result);
} else {
  console.warn('⚠️ Campo auto_preset_result NO existe en response');
  console.warn('Posible causa: Backend no retorna este campo o auto-apply no se ejecutó');
}
```

---

### **Paso 4: Verificar que los Trips Tengan Filtros Después del Import**

Inmediatamente después de hacer Update:

```javascript
// 1. Refetch trips
await queryClient.invalidateQueries(['trips']);

// 2. Ver trips en consola
const trips = await GET('/v1/locations/ONT/trips?airline=WN');

// 3. Verificar flags de filtros
const tripsWithFilters = trips.filter(t =>
  t.reduce_applied ||
  t.combine_applied ||
  t.expand_applied
);

console.log('Trips con filtros:', tripsWithFilters.length);
console.log('Trips sin filtros:', trips.length - tripsWithFilters.length);

// 4. Verificar un trip específico
const sampleTrip = trips[0];
console.log('Sample trip:', {
  id: sampleTrip.id,
  pick_up_date: sampleTrip.pick_up_date,
  pick_up_time: sampleTrip.pick_up_time,
  original_pick_up_time: sampleTrip.original_pick_up_time,
  reduce_applied: sampleTrip.reduce_applied,
  filtered_at: sampleTrip.filtered_at
});

// Resultado esperado:
// reduce_applied: true ✅
// original_pick_up_time: "08:30" ✅
// pick_up_time: "08:20" ✅
```

**Si reduce_applied es false:**
- ❌ El auto-apply NO funcionó
- Continuar con siguiente paso

---

### **Paso 5: Verificar que el Backend Tiene el Código de Auto-Apply**

#### Verificar versión del backend

```bash
# SSH al servidor
cd /home/backend/GT360

# Ver commit actual
git log -1 --oneline

# Buscar código de auto-apply
grep -n "AUTO-APPLY PRESET" features/trips/routes/trips_router.py

# Debe mostrar líneas 316-363
# Si NO muestra nada → Backend NO tiene el código
```

#### Verificar que el servicio existe

```bash
# Verificar que existe FilterPresetService
ls -la features/trips/services/filter_preset_service.py

# Debe existir ✅
# Si NO existe → Backend desactualizado
```

---

### **Paso 6: Verificar FilterSteps en la DB Después del Import**

```sql
-- Inmediatamente después de hacer Update
-- Conectar a PostgreSQL

SELECT
    pick_up_date,
    filter_type,
    is_active,
    trips_affected,
    created_at
FROM trips.filter_steps
WHERE location_id = 'YOUR_LOCATION_ID'
  AND airline = 'WN'
  AND pick_up_date >= '2026-03-01'
ORDER BY pick_up_date, created_at;

-- Resultado esperado:
-- Si las fechas importadas NO aparecen → ❌ Auto-apply no se ejecutó
-- Si las fechas aparecen con is_active=true → ✅ Auto-apply funcionó
```

---

## 🐛 **Problemas Comunes y Soluciones**

### Problema 1: NO Hay Preset Configurado

**Síntoma:**
```
Logs: "[AUTO_PRESET] No preset found for location=..., airline=WN"
```

**Causa:** No se ha creado un preset para esa location+airline.

**Solución:**

```bash
# 1. Crear preset
POST /v2/locations/{location_id}/airlines/WN/filters/preset
{
  "stack_template": [
    {
      "filter_type": "reduce",
      "windows": [
        {
          "start": "00:00",
          "end": "24:00",
          "enabled": true,
          "minutes_to_reduce": 10
        }
      ]
    }
  ]
}

# 2. Verificar creación
GET /v2/locations/{location_id}/airlines/WN/filters/preset

# Debe retornar 200 con el preset ✅
```

---

### Problema 2: Backend NO Retorna auto_preset_result

**Síntoma:**
```javascript
response.data.auto_preset_result === undefined
```

**Causa:** El backend no está retornando este campo en el response.

**Verificación:**

Ver el código en `trips_router.py:365-435` para confirmar que retorna el campo.

**Workaround temporal:**

```javascript
// Después de import, verificar manualmente
setTimeout(async () => {
  // Esperar 2 segundos para que auto-apply termine
  await new Promise(resolve => setTimeout(resolve, 2000));

  // Verificar stack
  const stack = await GET(`/stack?pick_up_date=${firstImportedDate}`);

  if (stack.steps.length > 0) {
    console.log('✅ Auto-apply funcionó (stack tiene steps)');
  } else {
    console.warn('❌ Auto-apply NO funcionó (stack vacío)');
  }
}, 2000);
```

---

### Problema 3: Las Fechas Ya Existían

**Síntoma:**
```
Logs: "[AUTO_PRESET] No new dates to process (all X dates already existed)"
```

**Causa:** Las fechas que importaste ya tenían trips en la tabla.

**Verificación:**

```sql
-- Ver qué fechas existen para esa airline
SELECT DISTINCT pick_up_date
FROM trips.trips
WHERE location_id = 'YOUR_LOCATION_ID'
  AND airline = 'WN'
ORDER BY pick_up_date;

-- Si las fechas de tu import aparecen aquí → Ya existían
```

**Solución:**

Si realmente quieres re-importar:
1. Eliminar trips viejos de esas fechas
2. Hacer import nuevamente
3. O aplicar filtros manualmente desde la UI

---

### Problema 4: Backend Tiene Error en Auto-Apply

**Síntoma:**
```
Logs: "[AUTO_PRESET] ⚠️ Auto-apply failed: {error}"
```

**Causa:** El preset tiene configuración inválida o hay error en el código.

**Verificación:**

```javascript
// Test el preset antes de usar
POST /v2/locations/{loc}/airlines/WN/filters/preset/test?pick_up_date=2026-03-01

// Si retorna error → Preset tiene config incorrecta
// Si retorna success → Preset está OK
```

**Solución:**

Ver logs completos del backend para identificar el error específico.

---

### Problema 5: Auto-Apply Se Ejecuta DESPUÉS del Refetch del Frontend

**Síntoma:**
```
- Import completo ✅
- Frontend hace refetch inmediatamente
- Trips NO tienen filtros
- 2 segundos después, SÍ tienen filtros
```

**Causa:** Auto-apply corre después del commit, puede tener latencia.

**Solución:**

```javascript
// Después de import exitoso
const response = await importTrips(file);

// Esperar 1-2 segundos antes de refetch
await new Promise(resolve => setTimeout(resolve, 2000));

// Ahora refetch
await queryClient.invalidateQueries(['trips']);

// O mejor: Escuchar evento WebSocket step_applied
```

---

## 📋 **Checklist de Diagnóstico**

### Frontend: Verificaciones Básicas

- [ ] **1. ¿Hay preset configurado?**
  ```javascript
  GET /v2/locations/{loc}/airlines/WN/filters/preset
  // Debe retornar 200, no 404
  ```

- [ ] **2. ¿El import fue exitoso?**
  ```javascript
  response.status === 200
  response.data.created > 0
  ```

- [ ] **3. ¿Las fechas son realmente nuevas?**
  ```javascript
  // Ver qué fechas importaste
  const importedDates = getImportedDates(excelFile);
  console.log('Fechas importadas:', importedDates);

  // Ver qué fechas ya existen
  const existingDates = await GET('/v1/locations/{loc}/days?airline=WN');
  console.log('Fechas existentes:', existingDates);

  // Comparar
  const newDates = importedDates.filter(d => !existingDates.includes(d));
  console.log('Fechas NUEVAS:', newDates);

  // Si newDates.length === 0 → ❌ Todas ya existían
  ```

- [ ] **4. ¿El response incluye auto_preset_result?**
  ```javascript
  console.log('auto_preset_result:', response.data.auto_preset_result);
  // Si es undefined → Backend no retorna este campo
  ```

- [ ] **5. ¿Los trips refetcheados tienen filtros?**
  ```javascript
  const trips = await GET('/trips');
  const withFilters = trips.filter(t => t.reduce_applied).length;
  console.log(`${withFilters} de ${trips.length} trips con filtros`);
  ```

---

## 🧪 **Test Completo End-to-End**

### Test desde la Consola del Navegador

```javascript
// ====================================================
// TEST: Auto-Aplicación de Filtros
// ====================================================

async function testAutoApply() {
  console.group('🧪 Test Auto-Apply');

  const locationId = 'YOUR_LOCATION_ID';
  const airline = 'WN';

  try {
    // 1. Verificar preset
    console.log('📋 Paso 1: Verificar preset...');
    const presetResponse = await fetch(
      `/v2/locations/${locationId}/airlines/${airline}/filters/preset`,
      { headers: { 'Authorization': `Bearer ${yourToken}` } }
    );

    if (presetResponse.status === 404) {
      console.error('❌ NO hay preset configurado');
      console.log('Solución: Crear preset con POST /preset');
      return;
    }

    const preset = await presetResponse.json();
    console.log('✅ Preset encontrado:', {
      stack_template: preset.stack_template,
      created_at: preset.created_at
    });

    // 2. Ver fechas existentes ANTES del import
    console.log('\n📅 Paso 2: Fechas existentes antes del import...');
    const existingDatesResponse = await fetch(
      `/v1/locations/${locationId}/days?airline=${airline}`,
      { headers: { 'Authorization': `Bearer ${yourToken}` } }
    );
    const existingDates = await existingDatesResponse.json();
    console.log('Fechas existentes:', existingDates);

    // 3. Hacer import
    console.log('\n📤 Paso 3: Simulación de import...');
    console.log('(Presiona Update button ahora y observa)');

    // 4. Después del import, verificar FilterSteps
    console.log('\n🔍 Paso 4: Después del import, ejecuta:');
    console.log(`
      const stack = await fetch(
        '/v2/locations/${locationId}/airlines/${airline}/filters/stack?pick_up_date=FECHA_IMPORTADA',
        { headers: { 'Authorization': 'Bearer ${yourToken}' } }
      ).then(r => r.json());

      console.log('Stack:', stack);

      // Si stack.steps.length > 0 → ✅ Auto-apply funcionó
      // Si stack.steps.length === 0 → ❌ Auto-apply NO funcionó
    `);

    // 5. Verificar trips
    console.log('\n📊 Paso 5: Verificar trips:');
    console.log(`
      const trips = await fetch(
        '/v1/locations/${locationId}/trips?airline=${airline}',
        { headers: { 'Authorization': 'Bearer ${yourToken}' } }
      ).then(r => r.json());

      const withFilters = trips.filter(t => t.reduce_applied);
      console.log('Trips con filtros:', withFilters.length, 'de', trips.length);

      // Si withFilters.length > 0 → ✅ Filtros aplicados
      // Si withFilters.length === 0 → ❌ Sin filtros
    `);

  } catch (error) {
    console.error('❌ Error:', error);
  }

  console.groupEnd();
}

// Ejecutar test
testAutoApply();
```

---

## 🔧 **Soluciones a Problemas Comunes**

### Solución 1: Crear Preset (Si No Existe)

```javascript
// Crear preset para location+airline
const createPreset = async () => {
  const response = await axios.post(
    `/v2/locations/${locationId}/airlines/WN/filters/preset`,
    {
      stack_template: [
        {
          filter_type: 'reduce',
          windows: [
            {
              start: '00:00',
              end: '24:00',
              enabled: true,
              minutes_to_reduce: 10
            }
          ]
        }
      ]
    },
    {
      headers: { 'Authorization': `Bearer ${token}` }
    }
  );

  console.log('✅ Preset creado:', response.data);

  // Ahora los siguientes imports auto-aplicarán filtros
};

createPreset();
```

### Solución 2: Aplicar Manualmente Si Auto-Apply Falló

```javascript
// Si después de import los trips NO tienen filtros
// Aplicar manualmente:

const applyManually = async (pickUpDate) => {
  // Obtener config del preset
  const preset = await GET(`/v2/locations/${locationId}/airlines/WN/filters/preset`);

  // Aplicar cada step del template
  for (const template of preset.stack_template) {
    await POST('/v2/locations/${locationId}/airlines/WN/filters/step/apply', {
      filter_type: template.filter_type,
      pick_up_date: pickUpDate,
      windows: template.windows
    });
  }

  // Refetch trips
  await queryClient.invalidateQueries(['trips']);

  console.log('✅ Filtros aplicados manualmente');
};

applyManually('2026-03-01');
```

### Solución 3: Verificar Timing (Auto-Apply Async)

```javascript
// Si auto-apply corre asíncronamente después del commit
// Agregar delay antes de refetch

const handleImport = async (file) => {
  // 1. Import
  const response = await importTrips(file);

  // 2. Esperar a que auto-apply termine (2 segundos)
  await new Promise(resolve => setTimeout(resolve, 2000));

  // 3. Ahora refetch
  await queryClient.invalidateQueries(['trips']);

  console.log('✅ Import y auto-apply completados');
};
```

---

## 📊 **Diagrama de Flujo de Debugging**

```
┌─────────────────────────────────────────┐
│ Usuario presiona "Update"                │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│ ¿Hay preset configurado?                 │
│ GET /preset → Status?                   │
└─────────────────────────────────────────┘
        ↓ 404                  ↓ 200
     ❌ NO                   ✅ SÍ
        ↓                      ↓
┌──────────────┐    ┌─────────────────────┐
│ Crear preset │    │ ¿Fechas son nuevas? │
│ POST /preset │    │ (no en existing)    │
└──────────────┘    └─────────────────────┘
                     ↓ NO        ↓ SÍ
                  ❌ Skip     ✅ Continúa
                               ↓
                    ┌─────────────────────┐
                    │ Backend auto-aplica │
                    │ (ver logs)          │
                    └─────────────────────┘
                               ↓
                    ┌─────────────────────┐
                    │ ¿FilterSteps creados│
                    │ en DB?              │
                    └─────────────────────┘
                     ↓ NO        ↓ SÍ
                  ❌ Error    ✅ OK
                               ↓
                    ┌─────────────────────┐
                    │ ¿Trips tienen flags?│
                    │ reduce_applied=true │
                    └─────────────────────┘
                     ↓ NO        ↓ SÍ
                  ❌ Bug      ✅ Funciona
```

---

## 🔍 **Debugging Avanzado**

### Verificar Código del Backend en Producción

```bash
# SSH al servidor
cd /home/backend/GT360

# Ver línea específica que hace auto-apply
sed -n '316,363p' features/trips/routes/trips_router.py

# Debe mostrar:
# if trips_to_create and airline:
#     from features.trips.services.filter_preset_service import FilterPresetService
#     ...
#     auto_apply_result = await preset_service.auto_apply_preset(...)

# Si NO muestra esto → Backend desactualizado
```

### Verificar Logs en Tiempo Real

```bash
# Terminal 1: Ver logs
tail -f /var/log/gt360/backend.log

# Terminal 2: Desde frontend, presionar "Update"

# Logs esperados:
# [AUTO_PRESET] Existing dates for {location}/{airline}: X days
# [AUTO_PRESET] Detected Y new dates
# [AUTO_PRESET] Preset found for location=...
# [AUTO_PRESET] Cloning preset to 2026-03-01
# [AUTO_PRESET] Applied reduce to 2026-03-01: 25 trips modified
# [AUTO_PRESET] ✅ Applied preset to Y days, affected N trips
```

### Network Tab (DevTools)

```
1. Abrir DevTools → Network → XHR
2. Presionar "Update" button
3. Buscar request: POST /v1/trips/upload-trips
4. Ver Response tab
5. Buscar campo: auto_preset_result
```

**Si NO aparece:**
- Backend no retorna ese campo
- Verificar versión del backend

---

## 📝 **Preguntas Clave para Diagnosticar**

### Pregunta 1: ¿Existe el Preset?

```bash
GET /v2/locations/{loc}/airlines/WN/filters/preset
```

- ❌ 404 → **NO hay preset** (crear uno)
- ✅ 200 → Preset existe (continuar)

### Pregunta 2: ¿Las Fechas Son Nuevas?

```sql
SELECT DISTINCT pick_up_date FROM trips
WHERE location_id = 'X' AND airline = 'WN';
```

- Si fechas importadas aparecen aquí → ❌ NO son nuevas
- Si NO aparecen → ✅ Son nuevas

### Pregunta 3: ¿Backend Ejecutó Auto-Apply?

```bash
grep "AUTO_PRESET" /var/log/gt360/backend.log | tail -20
```

- Si NO hay logs → ❌ Código no se ejecutó
- Si hay logs con "Applied preset" → ✅ Se ejecutó

### Pregunta 4: ¿FilterSteps Se Crearon?

```sql
SELECT * FROM trips.filter_steps
WHERE pick_up_date = '2026-03-01'
  AND airline = 'WN';
```

- Si retorna 0 rows → ❌ Auto-apply no creó steps
- Si retorna steps → ✅ Steps creados

### Pregunta 5: ¿Trips Tienen Filtros?

```sql
SELECT
    COUNT(*) as total,
    COUNT(CASE WHEN reduce_applied THEN 1 END) as with_filters
FROM trips.trips
WHERE pick_up_date = '2026-03-01' AND airline = 'WN';
```

- Si with_filters = 0 → ❌ Filtros no se aplicaron
- Si with_filters > 0 → ✅ Filtros aplicados

---

## 📚 **Documentación de Referencia**

### Endpoints Importantes

| Endpoint | Qué Hace |
|----------|----------|
| `POST /preset` | Crear/actualizar preset |
| `GET /preset` | Verificar preset actual |
| `POST /preset/test?pick_up_date=X` | Test dry-run de auto-apply |
| `GET /stack?pick_up_date=X` | Ver filtros activos para un día |
| `POST /upload-trips` | Import que dispara auto-apply |

### Estructura del Preset

```typescript
interface FilterPreset {
  id: string;
  location_id: string;
  airline: string;
  stack_template: Array<{
    filter_type: 'reduce' | 'combine' | 'expand';
    windows: Array<{
      start: string;          // "00:00"
      end: string;            // "24:00"
      enabled: boolean;
      minutes_to_reduce?: number;  // Para reduce
      min_gap?: number;            // Para combine/expand
      max_gap?: number;            // Para combine/expand
      max_shift?: number;          // Para expand
    }>;
  }>;
  created_at: string;
}
```

---

## 🚨 **Si Nada Funciona**

### Último Recurso: Aplicar Filtros Manualmente Después de Cada Import

```javascript
// Workaround temporal hasta identificar el problema

const handleUpdate = async (file) => {
  // 1. Import trips
  const importResponse = await importTrips(file);

  if (importResponse.created > 0) {
    // 2. Obtener fechas importadas
    const importedDates = getUniqueDates(importResponse.trips);

    // 3. Verificar si hay preset
    const preset = await GET(`/v2/locations/${locationId}/airlines/${airline}/filters/preset`);

    if (preset) {
      // 4. Aplicar filtros manualmente a cada fecha
      for (const pickUpDate of importedDates) {
        // Aplicar cada step del template
        for (const template of preset.stack_template) {
          await POST(`/v2/locations/${locationId}/airlines/${airline}/filters/step/apply`, {
            filter_type: template.filter_type,
            pick_up_date: pickUpDate,
            windows: template.windows
          });
        }
      }

      console.log('✅ Filtros aplicados manualmente');
    }
  }

  // 5. Refetch
  await queryClient.invalidateQueries(['trips']);
};
```

---

## 📞 **Información para Reportar al Backend**

Si después de todas las verificaciones el problema persiste, reportar al backend:

```
📋 Información a Incluir:

1. ¿Hay preset configurado?
   → GET /preset: {status, data}

2. ¿Qué fechas se importaron?
   → Fechas: [2026-03-01, 2026-03-02, ...]

3. ¿Son fechas nuevas?
   → Ver query de existing_dates

4. ¿Qué dicen los logs del backend?
   → Copiar logs con grep AUTO_PRESET

5. ¿FilterSteps se crearon?
   → Ver query de filter_steps

6. ¿Trips tienen filtros?
   → Ver query de trips con reduce_applied

7. ¿Qué version del backend?
   → git log -1 --oneline
```

---

## ✅ **Resumen de Verificación**

```
Checklist Rápido:

□ Preset existe (GET /preset → 200)
□ Fechas son nuevas (no en existing_dates)
□ Backend ejecutó auto-apply (logs muestran AUTO_PRESET)
□ FilterSteps se crearon (query de filter_steps)
□ Trips tienen filtros (reduce_applied=true)

Si TODOS son ✅ → Sistema funciona
Si alguno es ❌ → Ese es el problema
```

---

**Con esta guía, el frontend puede identificar exactamente dónde está fallando el auto-apply y reportar el problema específico.**
