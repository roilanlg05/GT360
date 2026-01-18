# Ground Filters: Actualización de Formato de Hora

## Resumen de Cambios

Los endpoints de Ground Filters (`preview`, `apply`) ahora respetan la preferencia de formato de hora del usuario (24h vs 12h AM/PM).

---

## Endpoints Actualizados

### 1. POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/preview

**Cambios:**
- ✅ Los campos `original_time` y `new_time` ahora se formatean según preferencia del usuario
- ✅ NO requiere cambios en el request
- ✅ El backend obtiene automáticamente la preferencia desde el token de autenticación

**Request (Sin cambios):**
```json
{
  "reduce": {
    "enabled": true,
    "minutes_to_reduce": 30
  },
  "combine": {
    "enabled": true,
    "min_gap": 5,
    "max_gap": 15
  }
}
```

**Response ANTES (todos los usuarios veían formato ISO):**
```json
{
  "location_id": "uuid",
  "airline": "WN",
  "changes": [
    {
      "trip_id": "uuid",
      "original_time": "16:30:00",
      "new_time": "16:00:00",
      "filter_applied": "reduce",
      "hotel_name": "Holiday Inn",
      "pick_up_date": "2026-01-20",
      "airline": "WN"
    }
  ],
  "summary": {
    "reduce": 10,
    "combine": 5,
    "expand": 0
  }
}
```

**Response AHORA (Usuario con formato 24h):**
```json
{
  "location_id": "uuid",
  "airline": "WN",
  "changes": [
    {
      "trip_id": "uuid",
      "original_time": "16:30",
      "new_time": "16:00",
      "filter_applied": "reduce",
      "hotel_name": "Holiday Inn",
      "pick_up_date": "2026-01-20",
      "airline": "WN"
    }
  ],
  "summary": {
    "reduce": 10,
    "combine": 5,
    "expand": 0
  }
}
```

**Response AHORA (Usuario con formato 12h):**
```json
{
  "location_id": "uuid",
  "airline": "WN",
  "changes": [
    {
      "trip_id": "uuid",
      "original_time": "04:30 PM",
      "new_time": "04:00 PM",
      "filter_applied": "reduce",
      "hotel_name": "Holiday Inn",
      "pick_up_date": "2026-01-20",
      "airline": "WN"
    }
  ],
  "summary": {
    "reduce": 10,
    "combine": 5,
    "expand": 0
  }
}
```

---

### 2. POST /v1/locations/{location_id}/airlines/{airline}/trips/filters/apply

**Cambios:**
- ✅ Los campos en el log también se formatean según preferencia del usuario
- ✅ NO requiere cambios en el request
- ✅ El backend obtiene automáticamente la preferencia desde el token de autenticación

**Response ANTES:**
```json
{
  "batch_id": "uuid",
  "location_id": "uuid",
  "airline": "WN",
  "changes_applied": 15,
  "log": [
    {
      "trip_id": "uuid",
      "action": "modified",
      "filter": "reduce",
      "original_time": "16:30:00",
      "new_time": "16:00:00",
      "hotel": "Holiday Inn",
      "airline": "WN"
    }
  ],
  "summary": {
    "reduce": 10,
    "combine": 5,
    "expand": 0
  }
}
```

**Response AHORA (Usuario con formato 24h):**
```json
{
  "batch_id": "uuid",
  "location_id": "uuid",
  "airline": "WN",
  "changes_applied": 15,
  "log": [
    {
      "trip_id": "uuid",
      "action": "modified",
      "filter": "reduce",
      "original_time": "16:30",
      "new_time": "16:00",
      "hotel": "Holiday Inn",
      "airline": "WN"
    }
  ],
  "summary": {
    "reduce": 10,
    "combine": 5,
    "expand": 0
  }
}
```

**Response AHORA (Usuario con formato 12h):**
```json
{
  "batch_id": "uuid",
  "location_id": "uuid",
  "airline": "WN",
  "changes_applied": 15,
  "log": [
    {
      "trip_id": "uuid",
      "action": "modified",
      "filter": "reduce",
      "original_time": "04:30 PM",
      "new_time": "04:00 PM",
      "hotel": "Holiday Inn",
      "airline": "WN"
    }
  ],
  "summary": {
    "reduce": 10,
    "combine": 5,
    "expand": 0
  }
}
```

---

## Implementación Frontend

### ✅ NO Requiere Cambios en Request

El frontend NO necesita cambiar nada en cómo hace las requests. El backend detecta automáticamente la preferencia del usuario desde el token de autenticación.

```typescript
// Request SIGUE IGUAL - NO CAMBIAR
const previewFilters = async (locationId: string, airline: string) => {
  const response = await api.post(
    `/v1/locations/${locationId}/airlines/${airline}/trips/filters/preview`,
    {
      reduce: {
        enabled: true,
        minutes_to_reduce: 30
      },
      combine: {
        enabled: true,
        min_gap: 5,
        max_gap: 15
      }
    }
  );

  // La respuesta YA viene con formato correcto
  return response.data;
};
```

### ✅ Mostrar Datos (Solo Display)

El frontend solo necesita mostrar los strings tal como llegan:

```tsx
// components/FilterPreview.tsx
interface Change {
  trip_id: string;
  original_time: string;  // Ya viene formateado: "16:30" o "04:30 PM"
  new_time: string;       // Ya viene formateado: "16:00" o "04:00 PM"
  filter_applied: string;
  hotel_name: string;
  pick_up_date: string;
  airline: string;
}

export function FilterPreviewTable({ changes }: { changes: Change[] }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Hotel</th>
          <th>Original Time</th>
          <th>New Time</th>
          <th>Filter</th>
        </tr>
      </thead>
      <tbody>
        {changes.map((change) => (
          <tr key={change.trip_id}>
            <td>{change.hotel_name}</td>
            {/* NO convertir, solo mostrar */}
            <td className="time-display">{change.original_time}</td>
            <td className="time-display">{change.new_time}</td>
            <td>
              <span className={`badge badge-${change.filter_applied}`}>
                {change.filter_applied}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

### ✅ Comparación de Tiempos (Si Necesario)

Si el frontend necesita comparar o calcular diferencias:

```typescript
// utils/timeUtils.ts
function parseTimeToMinutes(timeStr: string): number {
  // Detectar formato
  const is12h = /AM|PM/i.test(timeStr);

  if (is12h) {
    // Parsear formato 12h: "04:30 PM"
    const match = timeStr.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/i);
    if (!match) return 0;

    let hours = parseInt(match[1]);
    const minutes = parseInt(match[2]);
    const period = match[3].toUpperCase();

    if (period === 'PM' && hours !== 12) hours += 12;
    if (period === 'AM' && hours === 12) hours = 0;

    return hours * 60 + minutes;
  } else {
    // Parsear formato 24h: "16:30"
    const [hours, minutes] = timeStr.split(':').map(Number);
    return hours * 60 + minutes;
  }
}

function calculateTimeDifference(time1: string, time2: string): number {
  const minutes1 = parseTimeToMinutes(time1);
  const minutes2 = parseTimeToMinutes(time2);
  return Math.abs(minutes2 - minutes1);
}

// Uso
const diff = calculateTimeDifference("04:30 PM", "04:00 PM");
console.log(`Diferencia: ${diff} minutos`); // 30 minutos
```

---

## Tabla de Formatos

| Formato Usuario | Ejemplo original_time | Ejemplo new_time |
|-----------------|----------------------|------------------|
| **24h (Militar)** | `"16:30"` | `"16:00"` |
| **24h (Militar)** | `"00:00"` | `"23:45"` |
| **24h (Militar)** | `"08:15"` | `"08:00"` |
| **12h (AM/PM)** | `"04:30 PM"` | `"04:00 PM"` |
| **12h (AM/PM)** | `"12:00 AM"` | `"11:45 PM"` |
| **12h (AM/PM)** | `"08:15 AM"` | `"08:00 AM"` |

---

## Notas Importantes

### 1. Tipo de Dato en Response

Los campos `original_time` y `new_time` ahora son **SIEMPRE strings**, no objetos time.

```typescript
// ❌ ANTES (NO FUNCIONA MÁS)
interface Change {
  original_time: Date;  // ❌ Era objeto
  new_time: Date;       // ❌ Era objeto
}

// ✅ AHORA (CORRECTO)
interface Change {
  original_time: string;  // ✅ Es string formateado
  new_time: string;       // ✅ Es string formateado
}
```

### 2. No Hacer Conversión

El frontend NO debe convertir las horas recibidas. Ya vienen en el formato correcto.

```typescript
// ❌ MAL - No hacer esto
const displayTime = (time: string) => {
  return convertTo12h(time); // ❌ NO convertir
};

// ✅ BIEN - Solo mostrar
const displayTime = (time: string) => {
  return time; // ✅ Mostrar directamente
};
```

### 3. Preferencia se Aplica Automáticamente

El usuario NO puede cambiar formato durante la preview. El formato se determina por su configuración en `/v1/profile/settings`.

Si el usuario cambia su preferencia:
1. Debe hacer logout/login O refrescar página
2. Las nuevas requests usarán el nuevo formato

### 4. Timezone NO Cambia

El formato de hora (24h vs 12h) NO afecta el timezone. Las horas siguen estando en el timezone de la location.

---

## Ejemplo Completo: Flow de Preview

```typescript
// 1. Usuario hace preview de filtros
const previewFilters = async () => {
  try {
    const response = await api.post(
      '/v1/locations/uuid/airlines/WN/trips/filters/preview',
      {
        reduce: { enabled: true, minutes_to_reduce: 30 },
        combine: { enabled: true, min_gap: 5, max_gap: 15 }
      }
    );

    // 2. Backend detecta que el usuario tiene formato "12h"
    // 3. Response viene con formato 12h
    const changes = response.data.changes;

    // 4. Mostrar en UI (sin conversión)
    changes.forEach(change => {
      console.log(`${change.original_time} → ${change.new_time}`);
      // Output: "04:30 PM → 04:00 PM"
    });

  } catch (error) {
    console.error('Error en preview:', error);
  }
};
```

---

## Testing

### Test 1: Usuario con formato 24h

```bash
# 1. Configurar usuario a 24h
curl -X PATCH http://localhost:8000/v1/profile/settings \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{"time_format": "24h"}'

# 2. Hacer preview
curl -X POST "http://localhost:8000/v1/locations/{location_id}/airlines/WN/trips/filters/preview" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "reduce": {"enabled": true, "minutes_to_reduce": 30}
  }'

# Esperado:
# "original_time": "16:30"
# "new_time": "16:00"
```

### Test 2: Usuario con formato 12h

```bash
# 1. Configurar usuario a 12h
curl -X PATCH http://localhost:8000/v1/profile/settings \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{"time_format": "12h"}'

# 2. Hacer preview (mismo request)
curl -X POST "http://localhost:8000/v1/locations/{location_id}/airlines/WN/trips/filters/preview" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "reduce": {"enabled": true, "minutes_to_reduce": 30}
  }'

# Esperado:
# "original_time": "04:30 PM"
# "new_time": "04:00 PM"
```

---

## Checklist de Implementación Frontend

- [ ] Actualizar interfaces TypeScript: `original_time` y `new_time` son `string`
- [ ] Remover lógica de conversión de hora si existe
- [ ] Mostrar strings directamente sin procesamiento
- [ ] Actualizar tests para soportar ambos formatos
- [ ] (Opcional) Agregar helper para parsear tiempos si se necesita calcular diferencias
- [ ] Testing E2E con usuario en formato 24h
- [ ] Testing E2E con usuario en formato 12h
- [ ] Testing de cambio de formato durante sesión

---

## FAQ

### ¿El frontend necesita enviar el formato en el request?

**NO.** El backend lo detecta automáticamente desde el token de autenticación.

### ¿Qué pasa si el usuario cambia formato durante preview?

El formato se aplica en el momento del request. Si cambia formato, debe refrescar la página o hacer logout/login para que se aplique en nuevos requests.

### ¿Los logs también usan el formato?

**SÍ.** Los logs en el endpoint `/apply` también formatean las horas según preferencia del usuario.

### ¿Puedo forzar un formato específico?

**NO.** El formato siempre se basa en la preferencia del usuario. No se puede override por request.

### ¿Revert también usa formato?

El endpoint `/revert` NO retorna campos de tiempo, solo contadores. No requiere actualización.

---

**Fecha de Actualización:** 2026-01-17
**Versión Backend:** 1.0.0 (con formateo de hora)
**Documentación Relacionada:** [FRONTEND_TIME_FORMAT_IMPLEMENTATION_GUIDE.md](./FRONTEND_TIME_FORMAT_IMPLEMENTATION_GUIDE.md)
