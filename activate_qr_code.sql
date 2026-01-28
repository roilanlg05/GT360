-- ============================================================================
-- ACTIVAR QR CODE - Script SQL
-- ============================================================================
--
-- Este script activa el QR code generado por el frontend.
-- UUID del QR: c743011f-cc55-416b-ba08-8ea903bdfc0e
--
-- ANTES DE EJECUTAR: Reemplaza {org-uuid} y {location-uuid} con tus UUIDs reales
--
-- Para obtener tus UUIDs, ejecuta primero:
--   SELECT id, name FROM entities.organizations;
--   SELECT id, name FROM entities.locations;
--
-- ============================================================================

-- Paso 1: Ver tus organizations y locations actuales
SELECT '=== ORGANIZATIONS ===' as info;
SELECT id, name FROM entities.organizations;

SELECT '=== LOCATIONS ===' as info;
SELECT id, name FROM entities.locations;

-- Paso 2: Reemplaza los UUIDs abajo y ejecuta el INSERT
-- (Comenta las líneas anteriores después de obtener los UUIDs)

INSERT INTO entities.qr_codes (
    id,
    organization_id,
    location_id,
    name,
    airlines,
    status,
    scan_count,
    created_at,
    updated_at
) VALUES (
    'c743011f-cc55-416b-ba08-8ea903bdfc0e',  -- ← UUID del frontend (NO CAMBIAR)
    '{org-uuid}',                             -- ← REEMPLAZAR con tu organization ID
    '{location-uuid}',                        -- ← REEMPLAZAR con tu location ID
    'Van 1 - Louisville',                     -- ← Personalizar si quieres
    NULL,                                     -- ← NULL = todas las airlines, o '["WN", "AA"]'::jsonb
    'active',
    0,
    NOW(),
    NOW()
);

-- Paso 3: Verificar que se creó correctamente
SELECT
    id,
    organization_id,
    location_id,
    name,
    airlines,
    status,
    scan_count,
    created_at
FROM entities.qr_codes
WHERE id = 'c743011f-cc55-416b-ba08-8ea903bdfc0e';

-- Deberías ver 1 fila con status = 'active'

-- ============================================================================
-- VERIFICACIÓN FINAL
-- ============================================================================

-- Después de ejecutar, prueba el endpoint público:
-- curl "http://localhost:8000/v1/crew-lookup/config?qr_id=c743011f-cc55-416b-ba08-8ea903bdfc0e"
--
-- Debería retornar 200 con:
-- {
--   "qr_id": "c743011f-cc55-416b-ba08-8ea903bdfc0e",
--   "location_name": "...",
--   "airlines": [...],
--   "status": "active"
-- }
--
-- Si funciona, el QR está activado ✅
-- ============================================================================
