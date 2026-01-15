# 🐛 BUGFIX: Error Handling en Upload de Excel

**Fecha:** 2026-01-10
**Tipo:** Bugfix Crítico
**Afecta a:** POST `/v1/trips/upload-trips`
**Estado:** ✅ RESUELTO

---

## 📝 RESUMEN

Se corrigió un bug crítico en el procesamiento de archivos Excel que causaba errores genéricos de base de datos cuando:
1. El archivo Excel no contenía el código de aeropuerto (campo "CITY:")
2. El código de aeropuerto en el Excel no coincidía con el seleccionado

**Síntoma del Bug:**
```
Connection.cursor() missing 1 required positional argument: 'query'
```

**Causa Raíz:**
- El código intentaba hacer `.upper()` en un valor `None` cuando no se encontraba el código de ciudad
- Solo se capturaban excepciones de tipo `RuntimeError`, dejando pasar `ValueError` y `AttributeError`

---

## 🔧 CAMBIOS IMPLEMENTADOS

### 1. Validación Mejorada del Código de Aeropuerto

**Archivo:** [features/trips/utils/trip_importer.py:308-320](features/trips/utils/trip_importer.py#L308-L320)

**ANTES:**
```python
city_code = _find_city_code(ws)

if city_code.upper() != location.upper():  # ❌ Falla si city_code es None
    raise ValueError("Invalid Schedule")
```

**AHORA:**
```python
city_code = _find_city_code(ws)

# ✅ Validar que se encontró el código de ciudad en el Excel
if not city_code:
    raise ValueError(
        "No se encontró el código de aeropuerto en el archivo Excel. "
        "Por favor verifica que el archivo contenga 'CITY:' seguido del código del aeropuerto."
    )

# ✅ Validar que el código de ciudad coincida con el seleccionado
if city_code.upper() != location.upper():
    raise ValueError(
        f"El código de aeropuerto en el Excel ({city_code}) no coincide con el seleccionado ({location}). "
        "Por favor verifica que el archivo Excel sea del aeropuerto correcto."
    )
```

### 2. Manejo Completo de Excepciones

**Archivo:** [features/trips/routes/trips_router.py:63-76](features/trips/routes/trips_router.py#L63-L76)

**ANTES:**
```python
try:
    trips_import = await load_trips_from_bytes(content, ...)
except RuntimeError as e:  # ❌ Solo captura RuntimeError
    raise HTTPException(status_code=400, detail=str(e))
```

**AHORA:**
```python
try:
    trips_import = await load_trips_from_bytes(content, ...)
except ValueError as e:
    # ✅ Errores de validación (código incorrecto, múltiples aerolíneas, etc.)
    raise HTTPException(status_code=400, detail=str(e))
except RuntimeError as e:
    # ✅ Errores de formato (hoja no encontrada, encabezados incorrectos, etc.)
    raise HTTPException(status_code=400, detail=str(e))
except Exception as e:
    # ✅ Cualquier otro error inesperado
    raise HTTPException(status_code=400, detail=f"Error al procesar el archivo Excel: {str(e)}")
```

---

## 📊 NUEVOS MENSAJES DE ERROR

### Error 1: Código de Aeropuerto No Encontrado

**Cuando ocurre:** El archivo Excel no contiene el campo "CITY:" con el código del aeropuerto.

**Response (400 Bad Request):**
```json
{
  "detail": "No se encontró el código de aeropuerto en el archivo Excel. Por favor verifica que el archivo contenga 'CITY:' seguido del código del aeropuerto."
}
```

**Frontend debe mostrar:**
```
⚠️ Error en el archivo Excel

El archivo no contiene el código de aeropuerto requerido.

Verifica que el archivo Excel contenga:
- Una celda con el texto "CITY:" o "CITY"
- Seguido del código del aeropuerto (ej: "SDF", "LAX", "JFK")

Ejemplo correcto:
┌──────┬─────┐
│ CITY │ SDF │
└──────┴─────┘
```

### Error 2: Código de Aeropuerto No Coincide

**Cuando ocurre:** El código en el Excel es diferente al seleccionado en el dropdown.

**Response (400 Bad Request):**
```json
{
  "detail": "El código de aeropuerto en el Excel (LAX) no coincide con el seleccionado (SDF). Por favor verifica que el archivo Excel sea del aeropuerto correcto."
}
```

**Frontend debe mostrar:**
```
⚠️ Aeropuerto Incorrecto

El archivo Excel es para el aeropuerto LAX pero seleccionaste SDF.

Por favor:
1. Selecciona el aeropuerto correcto en el dropdown, o
2. Sube el archivo Excel correspondiente al aeropuerto SDF
```

### Error 3: Múltiples Aerolíneas (Plan Freemium)

**Cuando ocurre:** Se detectan múltiples aerolíneas en el archivo y la organización no tiene plan premium.

**Response (400 Bad Request):**
```json
{
  "detail": "Se ha detectado mas de una aerolinea en el archivo, necesitas una subscripcion para cargar mas de una aerolinea"
}
```

**Frontend debe mostrar:**
```
🔒 Plan Premium Requerido

Tu archivo contiene múltiples aerolíneas pero tu plan actual solo permite una aerolínea por archivo.

Opciones:
1. Actualiza a un plan premium para cargar múltiples aerolíneas
2. Filtra el Excel para incluir solo la aerolínea seleccionada
```

### Error 4: Hoja "Schedule" No Encontrada

**Cuando ocurre:** El archivo Excel no contiene una hoja llamada exactamente "Schedule".

**Response (400 Bad Request):**
```json
{
  "detail": "No se encontró la hoja 'Schedule' en el archivo de Excel."
}
```

**Frontend debe mostrar:**
```
⚠️ Formato de Archivo Incorrecto

El archivo Excel debe contener una hoja llamada exactamente "Schedule".

Verifica que:
- La hoja se llame "Schedule" (sin tildes, case-sensitive)
- No se llame "Schedules", "schedule", o "SCHEDULE"
```

### Error 5: Encabezados No Encontrados

**Cuando ocurre:** La hoja "Schedule" no contiene los encabezados esperados (DATE, PICK UP, DROP OFF).

**Response (400 Bad Request):**
```json
{
  "detail": "No se encontró la fila de encabezados (con DATE / PICK UP / DROP OFF) en la hoja Schedule."
}
```

**Frontend debe mostrar:**
```
⚠️ Formato de Encabezados Incorrecto

La hoja "Schedule" no contiene los encabezados requeridos.

Los encabezados deben incluir:
- DATE
- PICK UP (con subcabecera "From" y "Location")
- DROP OFF (con subcabecera "To" y "Location")

Ejemplo correcto:
┌──────┬────────────────┬────────────────┐
│ DATE │   PICK UP      │   DROP OFF     │
├──────┼────────┬───────┼────────┬───────┤
│      │  From  │ Loc   │   To   │  Loc  │
└──────┴────────┴───────┴────────┴───────┘
```

---

## 💻 CÓDIGO RECOMENDADO PARA EL FRONTEND

### 1. Parser de Errores Específicos

```typescript
function parseUploadError(errorDetail: string): {
  title: string;
  message: string;
  actions: string[];
} {
  // Error 1: Código no encontrado
  if (errorDetail.includes("No se encontró el código de aeropuerto")) {
    return {
      title: "Código de aeropuerto no encontrado",
      message:
        "El archivo Excel no contiene el campo requerido 'CITY:' con el código del aeropuerto.",
      actions: [
        "Verifica que el Excel contenga una celda con 'CITY:' seguido del código (ej: SDF)",
        "Asegúrate de usar la plantilla oficial de schedule"
      ]
    };
  }

  // Error 2: Código no coincide
  const mismatchMatch = errorDetail.match(/en el Excel \((\w+)\) no coincide con el seleccionado \((\w+)\)/);
  if (mismatchMatch) {
    const [, excelCode, selectedCode] = mismatchMatch;
    return {
      title: "Aeropuerto incorrecto",
      message:
        `El archivo es para ${excelCode} pero seleccionaste ${selectedCode}`,
      actions: [
        `Cambia el aeropuerto seleccionado a ${excelCode}, o`,
        `Sube el archivo correcto para ${selectedCode}`
      ]
    };
  }

  // Error 3: Múltiples aerolíneas
  if (errorDetail.includes("mas de una aerolinea")) {
    return {
      title: "Plan premium requerido",
      message:
        "Tu archivo contiene múltiples aerolíneas pero tu plan actual solo permite una.",
      actions: [
        "Actualiza a un plan premium",
        "Filtra el Excel para incluir solo una aerolínea"
      ]
    };
  }

  // Error 4: Hoja no encontrada
  if (errorDetail.includes("No se encontró la hoja 'Schedule'")) {
    return {
      title: "Hoja 'Schedule' no encontrada",
      message:
        "El archivo Excel debe contener una hoja llamada exactamente 'Schedule'.",
      actions: [
        "Verifica que la hoja se llame 'Schedule' (case-sensitive)",
        "No debe llamarse 'Schedules', 'schedule', o 'SCHEDULE'"
      ]
    };
  }

  // Error 5: Encabezados no encontrados
  if (errorDetail.includes("encabezados")) {
    return {
      title: "Formato de encabezados incorrecto",
      message:
        "La hoja 'Schedule' no tiene los encabezados requeridos (DATE, PICK UP, DROP OFF).",
      actions: [
        "Verifica que los encabezados incluyan: DATE, PICK UP, DROP OFF",
        "Asegúrate de usar la plantilla oficial de schedule"
      ]
    };
  }

  // Error genérico
  return {
    title: "Error al procesar el archivo",
    message: errorDetail,
    actions: [
      "Verifica que el archivo Excel tenga el formato correcto",
      "Contacta a soporte si el problema persiste"
    ]
  };
}
```

### 2. Componente de Error Mejorado

```typescript
function UploadErrorDisplay({ error }: { error: string }) {
  const parsed = parseUploadError(error);

  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4">
      <div className="flex items-start gap-3">
        <AlertCircle className="h-5 w-5 text-red-600 mt-0.5" />
        <div className="flex-1">
          <h3 className="font-semibold text-red-900 mb-1">
            {parsed.title}
          </h3>
          <p className="text-sm text-red-700 mb-3">
            {parsed.message}
          </p>
          {parsed.actions.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium text-red-900">
                Qué hacer:
              </p>
              <ul className="list-disc list-inside space-y-1">
                {parsed.actions.map((action, idx) => (
                  <li key={idx} className="text-sm text-red-700">
                    {action}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
```

### 3. Uso en el Upload Handler

```typescript
async function handleUpload(file: File, airport: string, airline: string) {
  try {
    const response = await uploadSchedule(file, airport, airline);

    // Success
    toast.success(`${response.tripsCount} trips cargados exitosamente`);

    // Si hay hoteles pendientes, mostrar wizard
    if (response.pendingHotels.length > 0) {
      showGeofencingWizard(response.locationId, response.pendingHotels);
    }

  } catch (error) {
    // Mostrar error específico
    setError(error.message);
  }
}
```

---

## ✅ VALIDACIÓN DEL FORMATO DEL EXCEL

El archivo Excel debe tener la siguiente estructura:

### 1. Campo CITY (Requerido)

```
┌──────┬─────┐
│ CITY │ SDF │  ← Debe estar en las primeras 40 filas
└──────┴─────┘
```

### 2. Hoja "Schedule" (Case-sensitive)

- Nombre exacto: `Schedule`
- ❌ No válido: `schedule`, `Schedules`, `SCHEDULE`

### 3. Estructura de Encabezados (Requerida)

```
┌──────────┬─────────────────────────┬─────────────────────────┬────────────┐
│   DATE   │       PICK UP           │       DROP OFF          │  RIDERS    │
├──────────┼────────────┬────────────┼────────────┬────────────┼────────────┤
│          │    From    │  Location  │     To     │  Location  │ Department │
├──────────┼────────────┼────────────┼────────────┼────────────┼────────────┤
│ 01-Nov   │ WN 123     │    SDF     │ Hotel      │            │ Flight(2)  │
│          │ Hotel      │            │ WN 456 ...│    SDF     │ InFlight(4)│
└──────────┴────────────┴────────────┴────────────┴────────────┴────────────┘
```

---

## 🧪 TESTING

### Casos de Prueba

1. **✅ Excel válido sin campo CITY**
   - Expected: Error específico "No se encontró el código de aeropuerto"
   - Antes: Error genérico de cursor

2. **✅ Excel con CITY incorrecto**
   - Expected: Error "código en Excel (LAX) no coincide con seleccionado (SDF)"
   - Antes: Error genérico de cursor

3. **✅ Excel con múltiples aerolíneas (plan freemium)**
   - Expected: Error "necesitas una subscripcion"
   - Antes: Se procesaban todas las aerolíneas

4. **✅ Excel sin hoja "Schedule"**
   - Expected: Error "No se encontró la hoja 'Schedule'"
   - Antes: RuntimeError genérico

5. **✅ Excel con formato incorrecto**
   - Expected: Error específico según el problema
   - Antes: Error genérico de cursor

---

## 📈 IMPACTO

### Antes del Fix
- ❌ Errores crípticos (`Connection.cursor()`)
- ❌ Difícil de debuggear para usuarios
- ❌ Soporte recibía muchos tickets
- ❌ Mala experiencia de usuario

### Después del Fix
- ✅ Mensajes de error claros y accionables
- ✅ Usuarios pueden auto-corregir errores
- ✅ Reducción de tickets de soporte
- ✅ Mejor experiencia de usuario
- ✅ Más fácil de debuggear

---

## 🔄 MIGRACIÓN (No Requerida)

Este es un fix de backend que mejora el manejo de errores. **No requiere migración** de datos ni cambios obligatorios en el frontend.

### Recomendaciones para el Frontend

1. **Opcional pero Recomendado:** Implementar el parser de errores específicos
2. **Opcional:** Mejorar el componente de display de errores
3. **No Requerido:** El frontend actual seguirá funcionando, solo mostrará mejores mensajes

---

## 📚 REFERENCIAS

- [FRONTEND_LOCATION_API_CHANGES.md](./FRONTEND_LOCATION_API_CHANGES.md) - Guía completa de cambios en API
- [WIZARD_TWO_STEP_FRONTEND_GUIDE.md](./WIZARD_TWO_STEP_FRONTEND_GUIDE.md) - Wizard de geofencing
- [BUGFIX_UUID_VALIDATION.md](./BUGFIX_UUID_VALIDATION.md) - Validación de UUIDs

---

**Última actualización:** 2026-01-10
**Commit:** (pending)
**Versión:** 2.0.1-bugfix
