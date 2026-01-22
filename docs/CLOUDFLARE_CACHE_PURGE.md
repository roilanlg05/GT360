# 🔥 CLOUDFLARE CACHE PURGE - Solución Definitiva

## 🎯 Problema Identificado

**Cloudflare está cacheando respuestas 500 antiguas en su CDN.**

Evidencia en los headers de respuesta:
```
server: cloudflare
cf-cache-status: DYNAMIC
```

Aunque el backend está funcionando correctamente (verificado con curl), Cloudflare está sirviendo respuestas cacheadas del error 500 que ocurrió cuando el endpoint estaba en desarrollo.

---

## ✅ SOLUCIÓN: Purgar Cache de Cloudflare

### Opción 1: Purge via Dashboard (Más Fácil)

1. **Login a Cloudflare Dashboard**
   - Ir a: https://dash.cloudflare.com/
   - Login con credenciales de la cuenta GT360

2. **Seleccionar el dominio**
   - Click en `gt360.app` o el dominio correspondiente

3. **Ir a Caching**
   - Sidebar izquierdo → "Caching"
   - Tab "Configuration"

4. **Purge Cache**

   **Opción A - Purge Everything (Nuclear, pero efectivo)**
   - Scroll hasta "Purge Cache"
   - Click "Purge Everything"
   - Confirmar
   - ⚠️ NOTA: Esto purga TODO el cache del dominio

   **Opción B - Purge by URL (Recomendado - Solo el endpoint afectado)**
   - Click "Custom Purge" → "Purge by URL"
   - Ingresar:
     ```
     https://api.gt360.app/v1/locations/36e9faa1-4812-4bc4-a0ce-dcf4511d8b94/airlines/WN/trips/filters/current
     ```
   - Click "Purge"

---

### Opción 2: Purge via API (Más Rápido)

**Requisitos:**
- Cloudflare API Token con permisos de "Cache Purge"
- Zone ID del dominio `gt360.app`

#### Paso 1: Obtener Zone ID

```bash
# Listar zones para encontrar el ID de gt360.app
curl -X GET "https://api.cloudflare.com/client/v4/zones" \
  -H "Authorization: Bearer YOUR_CLOUDFLARE_API_TOKEN" \
  -H "Content-Type: application/json" | jq '.result[] | select(.name=="gt360.app") | {id, name}'
```

#### Paso 2: Purgar Cache por URL

```bash
# Reemplazar:
# - ZONE_ID: con el ID obtenido en paso 1
# - YOUR_CLOUDFLARE_API_TOKEN: con tu token de API

curl -X POST "https://api.cloudflare.com/client/v4/zones/ZONE_ID/purge_cache" \
  -H "Authorization: Bearer YOUR_CLOUDFLARE_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{
    "files": [
      "https://api.gt360.app/v1/locations/36e9faa1-4812-4bc4-a0ce-dcf4511d8b94/airlines/WN/trips/filters/current"
    ]
  }'
```

**Respuesta esperada:**
```json
{
  "success": true,
  "errors": [],
  "messages": [],
  "result": {
    "id": "purge-job-id"
  }
}
```

#### Paso 3: Purgar TODOS los endpoints de filters (Recomendado)

```bash
curl -X POST "https://api.cloudflare.com/client/v4/zones/ZONE_ID/purge_cache" \
  -H "Authorization: Bearer YOUR_CLOUDFLARE_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{
    "files": [
      "https://api.gt360.app/v1/locations/*/airlines/*/trips/filters/current",
      "https://api.gt360.app/v1/locations/*/airlines/*/trips/filters/history"
    ]
  }'
```

---

### Opción 3: Purge Everything via API (Nuclear)

```bash
# Purgar TODO el cache del dominio
curl -X POST "https://api.cloudflare.com/client/v4/zones/ZONE_ID/purge_cache" \
  -H "Authorization: Bearer YOUR_CLOUDFLARE_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"purge_everything": true}'
```

⚠️ **ADVERTENCIA**: Esto purgará TODO el cache de `gt360.app`, incluyendo imágenes, CSS, JS, etc. El sitio puede estar más lento temporalmente.

---

## 🔑 Obtener Cloudflare API Token

Si no tienes un API token:

1. **Ir a Cloudflare Dashboard**
   - https://dash.cloudflare.com/profile/api-tokens

2. **Create Token**
   - Click "Create Token"
   - Template: "Custom token"

3. **Configurar permisos**
   - Permissions:
     - Zone → Cache Purge → Purge
     - Zone → Zone → Read
   - Zone Resources:
     - Include → Specific zone → `gt360.app`

4. **Create Token**
   - Copiar el token (solo se muestra una vez)
   - Guardar en lugar seguro (1Password, .env, etc.)

---

## 🧪 Verificar que el Purge Funcionó

### Test 1: Verificar Cache Status

```bash
# El header "cf-cache-status" debería ser "MISS" después del purge
curl -I https://api.gt360.app/v1/locations/36e9faa1-4812-4bc4-a0ce-dcf4511d8b94/airlines/WN/trips/filters/current \
  -H "Authorization: Bearer test" | grep -i "cf-cache"
```

**Antes del purge:**
```
cf-cache-status: HIT
```

**Después del purge (primera request):**
```
cf-cache-status: MISS
```

**Después del purge (segunda request):**
```
cf-cache-status: HIT
```

### Test 2: Verificar Response Code

```bash
# Debería devolver 401 (no 500)
curl -w "\nHTTP Status: %{http_code}\n" \
  https://api.gt360.app/v1/locations/36e9faa1-4812-4bc4-a0ce-dcf4511d8b94/airlines/WN/trips/filters/current \
  -H "Authorization: Bearer test"
```

**Esperado:**
```
{"detail":"Invalid token"}
HTTP Status: 401
```

### Test 3: Frontend Test

```javascript
// Ejecutar en consola del navegador DESPUÉS del purge:
window.testFilterEndpoint('36e9faa1-4812-4bc4-a0ce-dcf4511d8b94', 'WN')
```

**Esperado:** Debería recibir 401 o 200 (no 500).

---

## 🛠️ Script Automatizado de Purge

Crear este script para futuros purges:

```bash
#!/bin/bash
# purge_cloudflare_filters.sh

set -e

# Configuración
ZONE_ID="YOUR_ZONE_ID_HERE"  # Obtener de Cloudflare Dashboard
CF_TOKEN="YOUR_API_TOKEN_HERE"  # Obtener de API Tokens

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🔥 Purging Cloudflare cache for filter endpoints...${NC}"

# Purge endpoints
response=$(curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/purge_cache" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{
    "files": [
      "https://api.gt360.app/v1/locations/*/airlines/*/trips/filters/current",
      "https://api.gt360.app/v1/locations/*/airlines/*/trips/filters/history"
    ]
  }')

# Check if successful
if echo "$response" | jq -e '.success == true' > /dev/null 2>&1; then
  echo -e "${GREEN}✅ Cache purged successfully!${NC}"
  echo ""
  echo "Verify with:"
  echo "  curl -I https://api.gt360.app/v1/locations/.../trips/filters/current | grep cf-cache"
else
  echo -e "${RED}❌ Purge failed!${NC}"
  echo "Response: $response"
  exit 1
fi
```

**Uso:**
```bash
chmod +x purge_cloudflare_filters.sh
./purge_cloudflare_filters.sh
```

---

## 🚨 Prevenir Cache de Errores 5xx en el Futuro

### Opción 1: Cache Rules en Cloudflare

1. Ir a Cloudflare Dashboard → Rules → Page Rules
2. Create Page Rule:
   - URL: `api.gt360.app/v1/locations/*/airlines/*/trips/filters/*`
   - Settings:
     - Cache Level: Standard
     - Origin Cache Control: On
     - **Bypass Cache on Cookie**: `*` (o el cookie de auth específico)
     - **Cache TTL by Status Code**:
       - 200-299: 1 hour
       - 300-399: 5 minutes
       - 400-499: 1 minute
       - **500-599: 0 seconds (no cache)**

### Opción 2: Cache-Control Headers en Backend

Agregar headers en FastAPI para controlar cache de Cloudflare:

```python
# En trips_router.py, agregar middleware o headers a respuestas:

from fastapi import Response

@router.get("/v1/locations/{location_id}/airlines/{airline}/trips/filters/current")
async def get_current_filters(
    location_id: str,
    airline: str,
    response: Response,  # ← Agregar este parámetro
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> FilterCurrentResponse:
    # ... código existente ...

    # Agregar headers para controlar cache
    response.headers["Cache-Control"] = "private, no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    # Para Cloudflare específicamente:
    response.headers["CDN-Cache-Control"] = "no-cache"

    return result
```

**O crear un middleware global para endpoints protegidos:**

```python
# En main.py o shared/middlewares/

@app.middleware("http")
async def disable_cache_for_authenticated_endpoints(request: Request, call_next):
    response = await call_next(request)

    # Si el endpoint requiere auth, no cachear
    if "authorization" in request.headers:
        response.headers["Cache-Control"] = "private, no-cache"
        response.headers["CDN-Cache-Control"] = "no-cache"

    return response
```

---

## 📋 Checklist de Resolución

- [ ] 1. Purgar cache de Cloudflare (Dashboard o API)
- [ ] 2. Verificar con curl que devuelve 401 (no 500)
- [ ] 3. Verificar `cf-cache-status: MISS` en primera request
- [ ] 4. Probar desde frontend con hard refresh
- [ ] 5. Configurar Page Rule en Cloudflare para no cachear 5xx
- [ ] 6. Agregar headers `Cache-Control` en backend para endpoints auth
- [ ] 7. Crear script de purge para futuros deploys

---

## 🔍 Debug: ¿Por qué Cloudflare cachea 500s?

Por defecto, Cloudflare **NO debería** cachear respuestas 5xx, pero puede ocurrir si:

1. **Cache Everything** está habilitado en Page Rules
2. **Origin Cache Control** está deshabilitado
3. El backend envió headers incorrectos durante el error
4. Cache anterior de un 200 → 500 fue "degraded" pero no expiró

---

## 📞 Si el Problema Persiste

Si después de purgar Cloudflare el problema continúa:

### 1. Verificar que NO hay múltiples zonas

```bash
curl -X GET "https://api.cloudflare.com/client/v4/zones" \
  -H "Authorization: Bearer $CF_TOKEN" | jq '.result[] | select(.name | contains("gt360"))'
```

### 2. Verificar Page Rules activas

```bash
curl -X GET "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/pagerules" \
  -H "Authorization: Bearer $CF_TOKEN" | jq '.result[]'
```

### 3. Verificar Cache Rules (nuevo sistema)

En Dashboard:
- Rules → Cache Rules
- Verificar si hay reglas que afecten `/v1/locations/*/trips/filters/*`

### 4. Bypass Cloudflare temporalmente (Debug)

Para confirmar que es Cloudflare:

```bash
# Obtener IP real del origen (sin Cloudflare)
host api.gt360.app

# Hacer request directa a la IP del origen
curl -I http://ORIGIN_IP/v1/locations/.../trips/filters/current \
  -H "Host: api.gt360.app" \
  -H "Authorization: Bearer test"
```

Si la IP directa funciona pero el dominio no → Confirma que es Cloudflare.

---

## 🎯 Resumen Ejecutivo

**Problema:** Cloudflare cachea respuestas 500 antiguas del endpoint `/filters/current`

**Solución:**
1. Purgar cache de Cloudflare (Dashboard o API)
2. Configurar Page Rule para no cachear 5xx
3. Agregar headers `Cache-Control` en backend

**Tiempo estimado:** 5-10 minutos

**Recursos necesarios:**
- Acceso a Cloudflare Dashboard de `gt360.app`
- O API Token con permisos de Cache Purge

---

## 📚 Referencias

- [Cloudflare Cache Purge API](https://developers.cloudflare.com/api/operations/zone-purge)
- [Cache by Status Code](https://developers.cloudflare.com/cache/how-to/edge-browser-cache-ttl/cache-by-status-code/)
- [Understanding cf-cache-status](https://developers.cloudflare.com/cache/concepts/cache-responses/)
