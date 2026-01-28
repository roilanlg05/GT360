# Trip Search Endpoint - Guía Frontend

## Endpoint

```
GET /v1/organizations/{organization_id}/locations/{location_id}/trips/search
```

## Descripción

Busca un viaje específico por aerolínea, fecha, número de vuelo y tipo. Útil para localizar un viaje concreto cuando se conocen estos datos.

## Autenticación

- **Requiere token JWT** en header `Authorization: Bearer <token>`
- **Roles permitidos:** `manager`, `driver`, `crew`

## Autenticación para QR Codes

Para permitir que la tripulación acceda al endpoint escaneando un QR físico (sin login), se puede:

**Opción A: Token firmado de solo lectura** (Recomendado)
- El QR contiene un JWT con scope limitado: `orgId+locId`, expiración corta, solo lectura
- Backend valida el token firmado sin requerir sesión de usuario
- Ventajas: Más seguro, no requiere base de datos adicional
- Rate limiting recomendado por token

**Opción B: Public access via QR ID**
- El QR contiene un `qr_id` único registrado en la base de datos
- Backend valida que el `qr_id` corresponde a ese `orgId/locId`
- Ejemplo URL: `/crew-lookup?org={orgId}&loc={locId}&qr={qrId}`
- Ventajas: Más fácil de revocar/desactivar QRs individuales

**Implementación en backend:**

Para implementar esto, agregar la ruta a `PUBLIC_PATHS` en `settings.py`:
```python
"/v1/organizations/{organization_id}/locations/{location_id}/trips/search/qr",
```

Y crear un endpoint wrapper que valide el QR antes de llamar a la búsqueda estándar.

## Parámetros de Ruta

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `organization_id` | UUID | Sí | ID de la organización |
| `location_id` | UUID | Sí | ID de la location |

## Query Parameters

| Parámetro | Tipo | Requerido | Descripción | Ejemplo |
|-----------|------|-----------|-------------|---------|
| `airline` | string | Sí | Código de aerolínea (case insensitive) | `WN`, `AA`, `DL` |
| `date` | string | Sí | Fecha de pick up en formato `YYYY-MM-DD`. **Nota**: Para vuelos outbound temprano (madrugada), la fecha de pickup puede ser el día anterior al vuelo | `2026-01-15` |
| `flight` | string | Sí | Número de vuelo | `5468` |
| `type` | string | Sí | Tipo de viaje | `inbound`, `outbound`, `ground` |

## Tipos de Viaje

| Valor | Descripción |
|-------|-------------|
| `inbound` | Aeropuerto → Hotel |
| `outbound` | Hotel → Aeropuerto |
| `ground` | Hotel → Hotel |

## Ejemplo de Request

```javascript
const searchTrip = async (orgId, locationId, searchParams) => {
  const params = new URLSearchParams({
    airline: 'WN',
    date: '2026-01-15',
    flight: '5468',
    type: 'inbound'
  });

  const response = await fetch(
    `/v1/organizations/${orgId}/locations/${locationId}/trips/search?${params}`,
    {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    }
  );

  return response.json();
};
```

## Respuesta Exitosa (200)

```json
{
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "location_id": "123e4567-e89b-12d3-a456-426614174000",
    "pick_up_date": "2026-01-15",
    "pick_up_time": "14:30",
    "pick_up_location": "PHX Airport",
    "drop_off_location": "Hilton Hotel",
    "airline": "WN",
    "flight_number": "5468",
    "trip_type": "inbound",
    "status": "scheduled",
    "riders": {
      "pilots": 2,
      "flight_attendants": 5
    },
    "assigned_driver": null,
    "original_pick_up_time": null,
    "reduce_applied": false,
    "combine_applied": false,
    "expand_applied": false,
    "filter_batch_id": null,
    "filtered_at": null,
    "started_at": null,
    "picked_up_at": null,
    "dropped_off_at": null,
    "created_at": "2026-01-10T10:00:00Z",
    "updated_at": "2026-01-10T10:00:00Z"
  },
  "location": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "name": "Phoenix Operations"
  }
}
```

## Campos de Respuesta

### Objeto `data` (Trip)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | UUID | ID único del viaje |
| `location_id` | UUID | ID de la location |
| `pick_up_date` | string | Fecha de recogida (YYYY-MM-DD) |
| `pick_up_time` | string | Hora de recogida (formato según preferencia del usuario) |
| `pick_up_location` | string | Lugar de recogida |
| `drop_off_location` | string | Lugar de destino |
| `airline` | string | Código de aerolínea |
| `flight_number` | string | Número de vuelo |
| `trip_type` | string | Tipo: `inbound`, `outbound`, `ground` |
| `status` | string | Estado: `scheduled`, `en_route`, `completed`, `canceled` |
| `riders` | object | Conteo de tripulantes: `{pilots: number, flight_attendants: number}` |
| `assigned_driver` | UUID/null | ID del driver asignado |
| `original_pick_up_time` | string/null | Hora original antes de aplicar filtros |
| `reduce_applied` | boolean | Si se aplicó filtro reduce |
| `combine_applied` | boolean | Si se aplicó filtro combine |
| `expand_applied` | boolean | Si se aplicó filtro expand |
| `started_at` | timestamp/null | Cuándo inició el viaje |
| `picked_up_at` | timestamp/null | Cuándo se recogió al pasajero |
| `dropped_off_at` | timestamp/null | Cuándo se dejó al pasajero |

### Objeto `location`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | UUID | ID de la location |
| `name` | string | Nombre de la location |

## Errores

| Código | Mensaje | Causa |
|--------|---------|-------|
| 400 | `ID de organización inválido` | UUID de organización malformado |
| 400 | `ID de location inválido` | UUID de location malformado |
| 400 | `Tipo de viaje inválido` | type no es `inbound`, `outbound` o `ground` |
| 400 | `Formato de fecha inválido. Use YYYY-MM-DD` | Fecha en formato incorrecto |
| 403 | `No tiene acceso a esta organización` | Usuario no pertenece a la organización |
| 404 | `Location no encontrada en esta organización` | Location no existe o no pertenece a la org |
| 404 | `Viaje no encontrado` | No hay viaje con los criterios especificados |

## Ejemplo de Manejo de Errores

```javascript
const searchTrip = async (orgId, locationId, airline, date, flight, type) => {
  try {
    const params = new URLSearchParams({ airline, date, flight, type });

    const response = await fetch(
      `/v1/organizations/${orgId}/locations/${locationId}/trips/search?${params}`,
      {
        headers: { 'Authorization': `Bearer ${token}` }
      }
    );

    if (!response.ok) {
      const error = await response.json();

      switch (response.status) {
        case 400:
          console.error('Parámetros inválidos:', error.detail);
          break;
        case 403:
          console.error('Sin acceso a la organización');
          break;
        case 404:
          console.error('No encontrado:', error.detail);
          break;
      }
      return null;
    }

    return await response.json();
  } catch (error) {
    console.error('Error de red:', error);
    return null;
  }
};
```

## Notas

- El parámetro `airline` es **case insensitive** (WN = wn = Wn)
- Los espacios en `airline` y `flight` se eliminan automáticamente
- El formato de hora en la respuesta depende de la preferencia del usuario (12h/24h)

---

## Endpoint de Configuración (Requerido para UI de QR)

Para obtener las aerolíneas disponibles en una location y configuración del QR:

```
GET /v1/organizations/{organization_id}/locations/{location_id}/crew-lookup/config
```

### Parámetros de Ruta

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `organization_id` | UUID | Sí | ID de la organización |
| `location_id` | UUID | Sí | ID de la location |

### Query Parameters

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `qr_id` | string | No | ID del QR físico (para configuración específica por QR) |

### Respuesta Exitosa (200)

```json
{
  "organization_id": "550e8400-e29b-41d4-a716-446655440000",
  "location_id": "123e4567-e89b-12d3-a456-426614174000",
  "location_name": "Louisville Airport (SDF)",
  "airlines": ["WN", "AA", "DL"],
  "default_trip_type": "outbound",
  "timezone": "America/New_York",
  "ui": {
    "branding": {
      "logo_url": null,
      "primary_color": "#1E40AF"
    }
  }
}
```

### Campos de Respuesta

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `organization_id` | UUID | ID de la organización |
| `location_id` | UUID | ID de la location |
| `location_name` | string | Nombre descriptivo de la location |
| `airlines` | array | Lista de códigos de aerolíneas que operan en esta location |
| `default_trip_type` | string | Tipo de viaje por defecto (normalmente `outbound` para crew) |
| `timezone` | string | Zona horaria de la location |
| `ui` | object | Configuración de interfaz (branding, colores, etc.) |

### Ejemplo de uso

```javascript
const getQRConfig = async (orgId, locationId, qrId) => {
  const params = qrId ? `?qr_id=${qrId}` : '';

  const response = await fetch(
    `/v1/organizations/${orgId}/locations/${locationId}/crew-lookup/config${params}`
  );

  return response.json();
};
```

**✅ Estado**: Este endpoint está **IMPLEMENTADO** y listo para usar.
- Ubicación: [features/trips/routes/trips_router.py](../features/trips/routes/trips_router.py)
- Ruta agregada a `PUBLIC_PATHS` (no requiere autenticación)
- Schema QRCode implementado en [shared/db/schemas/entities/qr_codes.py](../shared/db/schemas/entities/qr_codes.py)

---

## Flujo Completo de Uso con QR

Este es el flujo end-to-end recomendado para la funcionalidad de QR para tripulación:

### 1. Usuario escanea QR
El QR contiene una URL tipo:
```
/crew-lookup?org={orgId}&loc={locId}&qr={qrId}
```

o con token firmado:
```
/crew-lookup?token={signedJWT}
```

### 2. Frontend carga configuración
La página de crew lookup llama al endpoint de configuración para obtener las aerolíneas disponibles:

```javascript
const config = await fetch(
  `/v1/organizations/${orgId}/locations/${locId}/crew-lookup/config?qr_id=${qrId}`
);

// Respuesta:
// {
//   "airlines": ["WN", "AA", "DL"],
//   "location_name": "Louisville Airport",
//   "default_trip_type": "outbound"
// }
```

### 3. UI muestra formulario de búsqueda
El formulario debe incluir:

- **Selector de aerolínea**: Poblado con `config.airlines`
  - Si solo hay 1 aerolínea, mostrarla fija (sin selector)
  - Si hay múltiples, mostrar dropdown o botones de switch
- **Campo de fecha**: Label "Pickup Date" o "Flight Date"
  - Formato: `YYYY-MM-DD` o date picker
  - Valor por defecto: fecha actual
- **Campo de número de vuelo**: Input numérico o text
- **Trip type**: Pre-seleccionado a `outbound` (o el valor de `config.default_trip_type`)
  - Puede estar oculto si siempre es el mismo tipo

### 4. Búsqueda de trip
Al hacer submit del formulario, llamar al endpoint de búsqueda:

```javascript
const result = await searchTrip(orgId, locId, {
  airline: 'WN',
  date: '2026-01-15',  // pickup date
  flight: '5468',
  type: 'outbound'
});
```

### 5. Mostrar resultado
Si se encuentra el trip (`200 OK`), mostrar:

**Información principal:**
- **Van time**: `result.data.pick_up_time` (ej: "14:30" o "2:30 PM")
- **Pickup location**: `result.data.pick_up_location` (ej: "PHX Airport")
- **Drop-off location**: `result.data.drop_off_location` (ej: "Hilton Hotel")

**Breakdown de tripulantes:**
- **Pilots**: `result.data.riders.pilots`
- **Flight Attendants**: `result.data.riders.flight_attendants`

**Estado del viaje:**
- `result.data.status` (scheduled, en_route, completed, canceled)

### 6. Manejo de errores

```javascript
if (response.status === 404) {
  // Trip no encontrado
  showMessage("No trip found for this flight. Please verify your information.");
}

if (response.status === 400) {
  // Parámetros inválidos
  showMessage("Invalid search parameters. Please check your input.");
}

if (response.status === 403) {
  // Sin acceso (si requiere autenticación)
  showMessage("Access denied. Please scan a valid QR code.");
}
```

### Ejemplo de UI sugerida

```
┌─────────────────────────────────────┐
│  CREW TRIP LOOKUP                   │
│  Louisville Airport (SDF)           │
├─────────────────────────────────────┤
│                                     │
│  Airline: [WN ▼] [AA] [DL]         │
│                                     │
│  Flight Date: [2026-01-15]          │
│                                     │
│  Flight Number: [____]              │
│                                     │
│  [   Search Van Time   ]            │
│                                     │
└─────────────────────────────────────┘

        ↓ (después de search exitoso)

┌─────────────────────────────────────┐
│  VAN PICKUP DETAILS                 │
├─────────────────────────────────────┤
│                                     │
│  🚐 Pickup Time: 2:30 PM            │
│                                     │
│  📍 Location: PHX Airport           │
│                                     │
│  👥 Passengers:                     │
│     • Pilots: 2                     │
│     • Flight Attendants: 5          │
│                                     │
│  Status: ✅ Scheduled               │
│                                     │
└─────────────────────────────────────┘
```

### Consideraciones adicionales

1. **Cache**: Considerar cachear el resultado de `/config` para evitar llamadas repetidas
2. **Rate limiting**: Implementar rate limiting por QR o por IP para prevenir abuso
3. **Analytics**: Registrar búsquedas exitosas/fallidas para mejorar UX
4. **Offline**: Considerar estrategia offline si el crew no tiene conexión
5. **Timezone**: Mostrar horarios en la timezone de la location (`config.timezone`)
6. **Fecha vs Pickup**: Clarificar en UI que para vuelos de madrugada, el pickup puede ser el día anterior
