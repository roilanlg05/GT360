# Guia Frontend: QR Codes para Multiples Locations

## Resumen

El backend ahora soporta **un QR code por cada location** dentro de una organizacion. Este documento explica como implementar la UI para mostrar y gestionar multiples QR codes.

## Arquitectura

```
Organization
    |
    +-- Location 1 (Louisville) --> QR Code 1
    |
    +-- Location 2 (Nashville)  --> QR Code 2
    |
    +-- Location 3 (Memphis)    --> QR Code 3 (o null si no existe)
```

**Regla clave**: Cada location tiene **exactamente 1 QR code** (relacion 1:1).

---

## Nuevo Endpoint: Listar QR Codes de la Organizacion

### Request

```http
GET /v1/organizations/{organization_id}/qr-codes
Authorization: Bearer {token}
```

### Response (200 OK)

```json
{
  "organization_id": "69238257-0c05-4630-b67f-72429294863a",
  "total_locations": 3,
  "total_qr_codes": 2,
  "locations": [
    {
      "location_id": "83ce964e-a42c-4b3a-9cad-b314128160cc",
      "location_name": "Louisville",
      "qr_code": {
        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "name": "QR - Louisville",
        "airlines": ["WN", "AA"],
        "status": "active",
        "qr_url": "https://web.gt360.app/crew-lookup?qr=a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "scan_count": 145,
        "last_scanned_at": "2026-01-24T10:30:00Z",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-24T10:30:00Z"
      }
    },
    {
      "location_id": "94df075f-b53d-4c4e-8e1f-c425169e71de",
      "location_name": "Nashville",
      "qr_code": {
        "id": "b2c3d4e5-f6a7-8901-bcde-f23456789012",
        "name": "QR - Nashville",
        "airlines": null,
        "status": "active",
        "qr_url": "https://web.gt360.app/crew-lookup?qr=b2c3d4e5-f6a7-8901-bcde-f23456789012",
        "scan_count": 87,
        "last_scanned_at": "2026-01-23T15:45:00Z",
        "created_at": "2026-01-05T00:00:00Z",
        "updated_at": "2026-01-23T15:45:00Z"
      }
    },
    {
      "location_id": "05e1f086-c64e-4d5f-9f20-d536270e82ef",
      "location_name": "Memphis",
      "qr_code": null
    }
  ]
}
```

---

## Flujo de Implementacion Frontend

### 1. Fetch de QR Codes

```typescript
interface QRCode {
  id: string;
  name: string;
  airlines: string[] | null;
  status: 'active' | 'disabled';
  qr_url: string;
  scan_count: number;
  last_scanned_at: string | null;
  created_at: string;
  updated_at: string;
}

interface LocationWithQR {
  location_id: string;
  location_name: string;
  qr_code: QRCode | null;
}

interface QRCodesResponse {
  organization_id: string;
  total_locations: number;
  total_qr_codes: number;
  locations: LocationWithQR[];
}

// Fetch all QR codes for the organization
async function fetchOrganizationQRCodes(orgId: string): Promise<QRCodesResponse> {
  const response = await fetch(`/v1/organizations/${orgId}/qr-codes`, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  return response.json();
}
```

### 2. Crear QR Code para Location sin QR

Cuando `qr_code` es `null`, el frontend debe crear uno:

```typescript
interface CreateQRCodeRequest {
  id: string;  // UUID generado por frontend
  name?: string;
  airlines?: string[];
  metadata?: Record<string, any>;
}

async function createQRCode(
  orgId: string,
  locationId: string,
  locationName: string
): Promise<QRCode> {
  // IMPORTANTE: El frontend genera el UUID
  const qrId = crypto.randomUUID();

  const response = await fetch(
    `/v1/organizations/${orgId}/locations/${locationId}/qr-code`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        id: qrId,
        name: `QR - ${locationName}`
      })
    }
  );

  return response.json();
}
```

### 3. Componente UI Sugerido

```tsx
function QRCodeManager() {
  const [data, setData] = useState<QRCodesResponse | null>(null);
  const [selectedLocation, setSelectedLocation] = useState<string | null>(null);

  useEffect(() => {
    fetchOrganizationQRCodes(organizationId).then(setData);
  }, [organizationId]);

  if (!data) return <Loading />;

  return (
    <div className="qr-manager">
      <h2>QR Codes ({data.total_qr_codes}/{data.total_locations})</h2>

      {/* Selector de Location */}
      <select
        value={selectedLocation || ''}
        onChange={(e) => setSelectedLocation(e.target.value)}
      >
        <option value="">Seleccionar location...</option>
        {data.locations.map(loc => (
          <option key={loc.location_id} value={loc.location_id}>
            {loc.location_name} {loc.qr_code ? '(QR activo)' : '(Sin QR)'}
          </option>
        ))}
      </select>

      {/* Mostrar QR de la location seleccionada */}
      {selectedLocation && (
        <QRCodeDisplay
          location={data.locations.find(l => l.location_id === selectedLocation)!}
          onQRCreated={() => fetchOrganizationQRCodes(organizationId).then(setData)}
        />
      )}

      {/* O mostrar todos los QR codes en grid */}
      <div className="qr-grid">
        {data.locations.map(loc => (
          <QRCodeCard
            key={loc.location_id}
            location={loc}
            onQRCreated={() => fetchOrganizationQRCodes(organizationId).then(setData)}
          />
        ))}
      </div>
    </div>
  );
}

function QRCodeCard({ location, onQRCreated }: {
  location: LocationWithQR;
  onQRCreated: () => void;
}) {
  const [creating, setCreating] = useState(false);

  const handleCreateQR = async () => {
    setCreating(true);
    try {
      await createQRCode(organizationId, location.location_id, location.location_name);
      onQRCreated();
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="qr-card">
      <h3>{location.location_name}</h3>

      {location.qr_code ? (
        <>
          {/* Renderizar QR code usando libreria como qrcode.react */}
          <QRCodeSVG value={location.qr_code.qr_url} size={200} />

          <div className="qr-stats">
            <span>Escaneos: {location.qr_code.scan_count}</span>
            <span>Status: {location.qr_code.status}</span>
          </div>

          <div className="qr-actions">
            <button onClick={() => downloadQR(location.qr_code!.qr_url, location.location_name)}>
              Descargar PNG
            </button>
            <button onClick={() => printQR(location.qr_code!.qr_url)}>
              Imprimir
            </button>
          </div>
        </>
      ) : (
        <div className="no-qr">
          <p>Esta location no tiene QR code</p>
          <button onClick={handleCreateQR} disabled={creating}>
            {creating ? 'Creando...' : 'Crear QR Code'}
          </button>
        </div>
      )}
    </div>
  );
}
```

---

## Estados y Casos Edge

### Caso 1: Location sin QR Code

```json
{
  "location_id": "...",
  "location_name": "Memphis",
  "qr_code": null  // <-- Mostrar boton "Crear QR"
}
```

**Accion**: Mostrar boton para crear QR. Al hacer clic, llamar POST con UUID generado por frontend.

### Caso 2: QR Code Deshabilitado

```json
{
  "qr_code": {
    "status": "disabled",
    ...
  }
}
```

**Accion**: Mostrar QR en gris con badge "Deshabilitado". Opcionalmente permitir reactivar.

### Caso 3: Multiples Locations

El endpoint siempre devuelve TODAS las locations de la organizacion, cada una con su QR (o null).

**Accion**: Renderizar grid/lista con todas las locations y sus QR codes.

---

## Endpoints Existentes (Referencia)

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/v1/organizations/{org}/qr-codes` | **NUEVO** - Lista todos los QR de la org |
| GET | `/v1/organizations/{org}/locations/{loc}/qr-code` | Obtiene QR de una location |
| POST | `/v1/organizations/{org}/locations/{loc}/qr-code` | Crea QR para una location |

---

## Notas Importantes

1. **UUID generado por frontend**: El `id` del QR code viene del frontend (`crypto.randomUUID()`), NO del backend.

2. **Idempotencia**: El POST es idempotente. Si el QR ya existe, retorna el existente (200), si no existe lo crea (201).

3. **1 QR por Location**: No se pueden crear multiples QR codes para la misma location. El constraint de BD lo impide.

4. **airlines: null**: Si `airlines` es null, significa que el QR acepta TODAS las aerolineas.

5. **qr_url**: La URL esta lista para usar. Ejemplo: `https://web.gt360.app/crew-lookup?qr={uuid}`

---

## Ejemplo de Request/Response Completo

### Listar QR Codes

```bash
curl -X GET "https://api.gt360.app/v1/organizations/69238257-0c05-4630-b67f-72429294863a/qr-codes" \
  -H "Authorization: Bearer eyJ..."
```

### Crear QR Code para Location sin QR

```bash
curl -X POST "https://api.gt360.app/v1/organizations/69238257-0c05-4630-b67f-72429294863a/locations/05e1f086-c64e-4d5f-9f20-d536270e82ef/qr-code" \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{
    "id": "c3d4e5f6-a7b8-9012-cdef-345678901234",
    "name": "QR - Memphis"
  }'
```

---

**Ultima actualizacion**: 2026-01-24
