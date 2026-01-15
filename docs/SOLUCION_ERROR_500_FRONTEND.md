# 🎯 SOLUCIÓN: Error 500 en web.gt360.app

**Problema Identificado**: ✅ Variables de entorno faltantes + Fallback incorrecto
**Causa Raíz**: Frontend usando IP local `192.168.0.133:8080` en producción
**Severidad**: 🔴 CRÍTICO - Frontend completamente caído

---

## 🔍 Problema Encontrado

### Código Problemático en `config.ts`

```typescript
// lib/config.ts (líneas 3-6)
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://192.168.0.133:8080"  // ← ❌ PROBLEMA AQUÍ
```

### ¿Por Qué Causa Error 500?

1. **En producción**, las variables de entorno NO están configuradas:
   - `process.env.NEXT_PUBLIC_API_BASE_URL` → `undefined`
   - `process.env.NEXT_PUBLIC_API_URL` → `undefined`

2. **El código usa el fallback**: `http://192.168.0.133:8080`

3. **Durante SSR**, el servidor Next.js intenta conectarse:
   ```typescript
   // lib/actions/server/getUserFromCookies.ts (línea 42-49)
   const response = await fetch(AUTH_ENDPOINTS.refresh, {
     method: "POST",
     headers: { Cookie: cookieHeader },
     credentials: "include",
     cache: "no-store",
   })
   // AUTH_ENDPOINTS.refresh = http://192.168.0.133:8080/v1/auth/refresh
   ```

4. **El fetch falla** porque:
   - `192.168.0.133` es una IP privada (red local de desarrollo)
   - No es accesible desde el servidor de producción
   - Causa `ECONNREFUSED` o `ETIMEDOUT`

5. **Next.js retorna 500** porque el error ocurre durante SSR

---

## ✅ Solución Inmediata

### Opción 1: Configurar Variables de Entorno (RECOMENDADO)

#### Para Vercel:

```bash
# En el dashboard de Vercel
# Project Settings > Environment Variables

# Agregar:
NEXT_PUBLIC_API_URL=https://api.gt360.app
NEXT_PUBLIC_API_BASE_URL=https://api.gt360.app

# Luego redeploy:
vercel --prod
```

#### Para Servidor Propio con PM2:

```bash
# 1. Editar .env.production
nano .env.production

# Agregar estas líneas:
NEXT_PUBLIC_API_URL=https://api.gt360.app
NEXT_PUBLIC_API_BASE_URL=https://api.gt360.app

# 2. Rebuild
npm run build

# 3. Restart
pm2 restart nextjs
```

#### Para Docker:

```bash
# Editar docker-compose.yml o docker run command
docker run -e NEXT_PUBLIC_API_URL=https://api.gt360.app \
           -e NEXT_PUBLIC_API_BASE_URL=https://api.gt360.app \
           nextjs-image
```

---

### Opción 2: Cambiar el Fallback (FIX TEMPORAL)

**⚠️ Temporal - Use solo si no puede cambiar env vars inmediatamente**

```typescript
// lib/config.ts
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "https://api.gt360.app"  // ✅ Cambiar a URL de producción
```

**Luego**:
```bash
npm run build
pm2 restart nextjs
# o
vercel --prod
```

---

## 🔧 Verificación Post-Fix

### Test 1: Verificar Variables de Entorno

```bash
# En el servidor Next.js
printenv | grep NEXT_PUBLIC_API

# Debe mostrar:
# NEXT_PUBLIC_API_URL=https://api.gt360.app
# NEXT_PUBLIC_API_BASE_URL=https://api.gt360.app
```

### Test 2: Verificar Build

```bash
# Debe ver las variables en el build
npm run build

# Buscar en la salida:
# ✓ Creating an optimized production build
# ...
# Environment Variables:
#   NEXT_PUBLIC_API_URL: https://api.gt360.app
```

### Test 3: Test Manual de SSR

```bash
# Desde el servidor Next.js
node -e "
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://192.168.0.133:8080';
console.log('API URL:', API_URL);

fetch(API_URL + '/v1/auth/refresh', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' }
})
.then(r => console.log('Status:', r.status))
.catch(e => console.error('Error:', e.message));
"

# Debe mostrar:
# API URL: https://api.gt360.app
# Status: 400 (o 401, es normal sin cookies)
```

### Test 4: Verificar Frontend

```bash
# En el navegador
curl -I https://web.gt360.app/

# Debe devolver:
# HTTP/2 200  ← ✅ En lugar de 500
```

---

## 📋 Checklist de Implementación

**Antes del fix**:
- [ ] Backup del código actual
- [ ] Confirmar que tienes acceso al servidor/Vercel

**Durante el fix**:
- [ ] Configurar `NEXT_PUBLIC_API_URL` en variables de entorno
- [ ] Configurar `NEXT_PUBLIC_API_BASE_URL` en variables de entorno
- [ ] Rebuild del frontend (`npm run build`)
- [ ] Redeploy a producción

**Después del fix**:
- [ ] Verificar variables con `printenv`
- [ ] Test en navegador: `https://web.gt360.app/`
- [ ] Verificar que no hay error 500
- [ ] Verificar que la aplicación carga correctamente
- [ ] Hacer login de prueba

---

## 🎓 Explicación Técnica

### ¿Por Qué Funcionaba en Desarrollo?

En desarrollo local:

1. El servidor Next.js corre en la misma red que `192.168.0.133:8080`
2. Puede conectarse al backend local
3. No hay error

### ¿Por Qué Falla en Producción?

En producción:

1. El servidor Next.js está en Vercel/otro servidor
2. `192.168.0.133` es una IP privada inaccesible
3. Causa `ECONNREFUSED`
4. SSR falla → 500

### Diagrama del Flujo

```
Usuario → https://web.gt360.app/
    ↓
Next.js Server (SSR)
    ↓
getUserFromCookies()
    ↓
fetch(AUTH_ENDPOINTS.refresh)
    ↓
AUTH_ENDPOINTS.refresh = API_BASE_URL + "/v1/auth/refresh"
    ↓
API_BASE_URL = "http://192.168.0.133:8080"  ← ❌ No accesible
    ↓
ECONNREFUSED / ETIMEDOUT
    ↓
Error en SSR
    ↓
500 Internal Server Error
```

### Flujo Correcto (Después del Fix)

```
Usuario → https://web.gt360.app/
    ↓
Next.js Server (SSR)
    ↓
getUserFromCookies()
    ↓
fetch(AUTH_ENDPOINTS.refresh)
    ↓
AUTH_ENDPOINTS.refresh = "https://api.gt360.app/v1/auth/refresh"  ← ✅
    ↓
Backend responde (200, 401, etc.)
    ↓
SSR exitoso
    ↓
200 OK
```

---

## 🚨 Prevención Futura

### 1. Validar Variables de Entorno al Inicio

```typescript
// lib/config.ts
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  (() => {
    if (process.env.NODE_ENV === 'production') {
      throw new Error(
        'NEXT_PUBLIC_API_URL is required in production. ' +
        'Please configure it in environment variables.'
      );
    }
    return "http://localhost:8000"; // OK para dev local
  })();
```

### 2. Agregar Validación en CI/CD

```yaml
# .github/workflows/deploy.yml
- name: Validate Environment Variables
  run: |
    if [ -z "$NEXT_PUBLIC_API_URL" ]; then
      echo "Error: NEXT_PUBLIC_API_URL is not set"
      exit 1
    fi
    echo "✓ NEXT_PUBLIC_API_URL is set"
```

### 3. Documentar Variables Requeridas

```markdown
# .env.example
# API Configuration (REQUIRED in production)
NEXT_PUBLIC_API_URL=https://api.gt360.app
NEXT_PUBLIC_API_BASE_URL=https://api.gt360.app

# For local development
# NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## 💡 Tips Adicionales

### Usar Different Configs por Entorno

```typescript
// lib/config.ts
const configs = {
  development: {
    apiUrl: "http://localhost:8000",
  },
  production: {
    apiUrl: "https://api.gt360.app",
  },
  test: {
    apiUrl: "http://localhost:8000",
  },
};

const env = process.env.NODE_ENV || "development";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  configs[env].apiUrl;
```

### Logging para Debug

```typescript
// lib/config.ts
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "https://api.gt360.app";

// Log en server-side (visible en logs del servidor)
if (typeof window === 'undefined') {
  console.log('[CONFIG] API_BASE_URL:', API_BASE_URL);
  console.log('[CONFIG] NODE_ENV:', process.env.NODE_ENV);
}
```

---

## 📞 Soporte

Si después de aplicar el fix el problema persiste:

1. **Compartir**:
   - Output de `printenv | grep NEXT_PUBLIC`
   - Output de `npm run build`
   - Logs del servidor Next.js

2. **Verificar**:
   - ¿El deploy se completó correctamente?
   - ¿Se reinició el servidor después del cambio?
   - ¿Las variables están en el ambiente correcto? (production, no development)

3. **Test adicional**:
   ```bash
   # En el servidor Next.js
   curl -v https://api.gt360.app/v1/auth/refresh -X POST

   # Debe devolver 400/401 (no 500, no timeout)
   ```

---

## 🎉 Resumen

**Problema**: Frontend usando IP local en producción
**Causa**: Variables de entorno no configuradas
**Solución**: Configurar `NEXT_PUBLIC_API_URL=https://api.gt360.app`
**Tiempo estimado**: 5 minutos
**Dificultad**: ⭐ Muy fácil

**Pasos**:
1. Configurar variable de entorno
2. Rebuild
3. Redeploy
4. ✅ Listo

---

**Última actualización**: 2026-01-10 12:25 UTC
**Status**: 🟢 Solución identificada y documentada
