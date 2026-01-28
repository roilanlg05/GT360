# Fix: "QR code not found" Error

## 🐛 Error

```
QR code not found. The QR needs to be created in the database first.
QR ID: c743011f...
```

**Causa**: El QR code UUID generado por el frontend no existe en la base de datos.

---

## ✅ Solución 1: Ejecutar SQL (Rápido - 2 minutos)

### Step 1: Obtener el UUID completo del frontend

Abre la consola del navegador (F12) y ejecuta:
```javascript
localStorage.getItem('crew-qr-id')
```

Copia el UUID completo (ej: `c743011f-cc55-416b-ba08-8ea903bdfc0e`)

### Step 2: Obtener tus UUIDs de org y location

```sql
-- Obtener tu organization ID
SELECT id, name FROM entities.organizations LIMIT 1;

-- Obtener tu location ID
SELECT id, name FROM entities.locations
WHERE organization_id = 'tu-org-uuid'
LIMIT 1;
```

### Step 3: Ejecutar INSERT con el UUID del frontend

```sql
-- Reemplaza los valores:
-- - 'c743011f-...' con el UUID del localStorage (Step 1)
-- - '{org-uuid}' con tu organization_id (Step 2)
-- - '{location-uuid}' con tu location_id (Step 2)

INSERT INTO entities.qr_codes (
    id,
    organization_id,
    location_id,
    name,
    airlines,
    status
) VALUES (
    'c743011f-cc55-416b-ba08-8ea903bdfc0e',  -- ← UUID del frontend (Step 1)
    '550e8400-e29b-41d4-a716-446655440000',  -- ← Tu org UUID (Step 2)
    '123e4567-e89b-12d3-a456-426614174000',  -- ← Tu location UUID (Step 2)
    'Van 1 - Louisville',
    '["WN", "AA"]'::jsonb,  -- o NULL para todas las airlines
    'active'
);
```

### Step 4: Verificar que se creó

```sql
SELECT id, name, status FROM entities.qr_codes
WHERE id = 'c743011f-cc55-416b-ba08-8ea903bdfc0e';
```

### Step 5: Recargar página del frontend

El error debería desaparecer y el QR debería funcionar.

---

## ✅ Solución 2: Usar Management Endpoints (Automático)

Si tienes acceso al dashboard de manager:

### Step 1: Abrir dashboard de crew members

```
http://localhost:3000/dashboard/crew-members
```

### Step 2: Frontend auto-crea el QR

El frontend debería:
1. Llamar `GET /v1/organizations/{org}/locations/{loc}/qr-codes`
2. Si retorna `total: 0` (no hay QRs)
3. Llamar `POST /v1/organizations/{org}/locations/{loc}/qr-codes` con el UUID generado
4. QR se crea automáticamente ✅

**Nota**: Esto requiere que el usuario esté logueado con rol `manager`.

---

## ✅ Solución 3: Verificar UUID Mismatch

Si ejecutaste el SQL pero sigue fallando:

### Verificar que el UUID coincide

```sql
-- Ver todos los QR codes en tu DB
SELECT id, name, status FROM entities.qr_codes;
```

```javascript
// Ver el UUID que el frontend está usando
console.log(localStorage.getItem('crew-qr-id'));
```

**Si son diferentes**:

**Opción A**: Actualizar localStorage con el UUID de la DB
```javascript
localStorage.setItem('crew-qr-id', 'uuid-from-database');
location.reload();
```

**Opción B**: Ejecutar SQL con el UUID del localStorage (Solución 1)

---

## 🔍 Debugging

### Verificar que el backend recibe la request

```bash
# En terminal del backend, debería ver logs tipo:
# GET /v1/crew-lookup/config?qr_id=c743011f-...

# Si no ves logs, el frontend no está llamando el endpoint
# Si ves logs con 404, el QR no existe en DB
```

### Verificar conexión a base de datos

```bash
# Test directo al endpoint público
curl "http://localhost:8000/v1/crew-lookup/config?qr_id=c743011f-cc55-416b-ba08-8ea903bdfc0e"

# Si retorna 404:
# {
#   "detail": "QR code not found"
# }

# El QR no está en la DB, ejecuta el SQL (Solución 1)
```

---

## 🎯 Quick Fix (Copy-Paste)

**Para resolver en 2 minutos**:

1. Abre consola del navegador (F12)
2. Ejecuta:
   ```javascript
   console.log(localStorage.getItem('crew-qr-id'));
   ```
3. Copia el UUID
4. Ejecuta este SQL (reemplaza los UUIDs):
   ```sql
   INSERT INTO entities.qr_codes (id, organization_id, location_id, name, status)
   VALUES (
     'PEGA-UUID-AQUI',     -- UUID del step 3
     'TU-ORG-UUID',        -- SELECT id FROM entities.organizations;
     'TU-LOCATION-UUID',   -- SELECT id FROM entities.locations;
     'Van 1',
     'active'
   );
   ```
5. Recarga página (F5)
6. ✅ Debería funcionar

---

## ⚡ Flujo Ideal (Una Vez Configurado)

Después de ejecutar el SQL una vez:

1. Frontend genera UUID y lo guarda en localStorage
2. Frontend llama `/crew-lookup/config`
3. Backend encuentra el QR → Retorna config ✅
4. Todo funciona automáticamente

**El SQL solo se ejecuta UNA VEZ** por location/QR.

---

## 📚 Documentación Relacionada

- [QR_CODE_SETUP_GUIDE.md](./QR_CODE_SETUP_GUIDE.md) - Setup completo
- [BACKEND_QR_INTEGRATION.md](./BACKEND_QR_INTEGRATION.md) - Cómo funciona
- [FRONTEND_GENERATES_QR_ID.md](./FRONTEND_GENERATES_QR_ID.md) - Arquitectura

---

**TL;DR**: Ejecuta el SQL con el UUID del localStorage (usa consola del navegador para obtenerlo). Recarga página. Listo.
