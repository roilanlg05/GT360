# 🚨 Diagnóstico: Error 500 en web.gt360.app

**Error**: `GET https://web.gt360.app/ 500 (Internal Server Error)`
**Fecha**: 2026-01-10
**Status**: ⚠️ Error en Frontend (Next.js), **NO en Backend**

---

## ✅ Confirmación: Backend Funcionando

### Tests Realizados:

```bash
# 1. Container Status
✓ Container: gt360 - UP (6 minutes)
✓ Port: 8000 - Listening
✓ Health: Responding to requests

# 2. Import Check
✓ trips_router importa correctamente
✓ 11 rutas registradas

# 3. Log Analysis
✓ No errores 500 en los últimos 10 minutos
✓ Endpoints respondiendo correctamente
✓ WebSocket connections: Active

# 4. Syntax Validation
✓ Python syntax: OK
✓ No import errors
```

**Conclusión**: El backend API está completamente funcional.

---

## 🔍 Análisis del Error 500

### ¿Qué es un Error 500 en el Frontend?

Cuando ves `GET https://web.gt360.app/ 500`, significa:

1. **Next.js Server** está fallando al hacer Server-Side Rendering (SSR)
2. El error ocurre **ANTES** de que la página llegue al navegador
3. El servidor de Next.js está devolviendo un error interno

### NO es un error del Browser

```
❌ NO es: fetch() del cliente fallando
❌ NO es: CORS error
❌ NO es: JavaScript error en el cliente
✅ SÍ es: Next.js server crash durante SSR
```

---

## 🎯 Posibles Causas (Ordenadas por Probabilidad)

### 1. Error en `page.tsx` o `layout.tsx` durante SSR

**Síntoma**: El servidor Next.js falla al renderizar la página inicial

**Causa común**:
```typescript
// En app/page.tsx o app/layout.tsx
export default async function Page() {
  // Si esto falla, causa 500
  const data = await fetch(`${process.env.API_URL}/v1/locations`);

  // ¿El fetch está fallando?
  // ¿Está el env var configurado?
  // ¿Timeout?
}
```

**Cómo verificar**:
```bash
# Ver logs del servidor Next.js
vercel logs <deployment-url>
# o
pm2 logs nextjs
# o
docker logs <next-container>
```

**Buscar**:
- `Error: fetch failed`
- `TypeError: Cannot read property`
- `ECONNREFUSED`
- `ETIMEDOUT`

---

### 2. Variable de Entorno Faltante o Incorrecta

**Síntoma**: `process.env.API_URL` es `undefined`

**Verificar en el servidor Next.js**:
```bash
# En el servidor donde corre Next.js
echo $NEXT_PUBLIC_API_URL
echo $API_URL

# Debe mostrar:
# https://api.gt360.app
```

**Fix**:
```bash
# En .env.production
API_URL=https://api.gt360.app
NEXT_PUBLIC_API_URL=https://api.gt360.app

# Luego redeploy
npm run build
pm2 restart nextjs
```

---

### 3. Timeout en llamadas al Backend durante SSR

**Síntoma**: El backend tarda demasiado en responder durante el SSR

**Causa**: Next.js tiene un timeout por defecto (10-30 segundos)

**Verificar**:
```typescript
// En tu código
const controller = new AbortController();
const timeoutId = setTimeout(() => controller.abort(), 5000);

try {
  const response = await fetch(url, {
    signal: controller.signal,
  });
} catch (error) {
  if (error.name === 'AbortError') {
    console.log('Timeout!'); // 👈 Esto causa 500
  }
}
```

**Fix**:
```typescript
// Aumentar timeout o agregar retry
const response = await fetch(url, {
  next: { revalidate: 60 }, // Cache por 60s
  // o
  cache: 'no-store', // No cache
});
```

---

### 4. Error en Middleware de Next.js

**Síntoma**: `middleware.ts` está fallando

**Verificar**:
```typescript
// middleware.ts
export function middleware(request: NextRequest) {
  // ¿Hay algún error aquí?
  const token = request.cookies.get('token');

  // Si esto falla, causa 500 en TODAS las páginas
  if (!token) {
    throw new Error('No token'); // 👈 Esto causa 500
  }
}
```

**Fix**:
```typescript
// Siempre usar try-catch en middleware
export function middleware(request: NextRequest) {
  try {
    // tu código
  } catch (error) {
    console.error('Middleware error:', error);
    // No throw, solo log y continuar
    return NextResponse.next();
  }
}
```

---

### 5. Incompatibilidad de Node.js

**Síntoma**: Features de Node.js 20+ usadas en Node 18

**Verificar**:
```bash
# En el servidor Next.js
node --version

# Debe ser >= 18.17.0
```

**Fix**:
```bash
nvm install 20
nvm use 20
npm run build
```

---

### 6. Dependencias Faltantes después del Deploy

**Síntoma**: `node_modules` incompleto

**Verificar**:
```bash
# En el servidor
cd /path/to/nextjs
npm list

# ¿Hay warnings de missing dependencies?
```

**Fix**:
```bash
rm -rf node_modules package-lock.json
npm install
npm run build
```

---

## 🔧 Diagnóstico Paso a Paso

### Paso 1: Verificar Logs del Servidor Next.js

```bash
# Opción A: Vercel
vercel logs <your-deployment>

# Opción B: PM2
pm2 logs nextjs --lines 100

# Opción C: Docker
docker logs nextjs-container --tail 100

# Opción D: Archivo de log
tail -f /var/log/nextjs/error.log
```

**Buscar estos patrones**:
```
Error: fetch failed at [URL]
TypeError: Cannot read property 'X' of undefined
ECONNREFUSED 127.0.0.1:8000
ETIMEDOUT
Unhandled Runtime Error
```

---

### Paso 2: Probar Endpoints del Backend Manualmente

```bash
# 1. Endpoint de locations (usado en la carga inicial)
curl -i https://api.gt360.app/v1/locations \
  -H "Authorization: Bearer <token>"

# ¿Devuelve 200? → Backend OK
# ¿Devuelve 401? → Token expirado (normal)
# ¿Devuelve 500? → Problema en backend
# ¿No responde? → Problema de red

# 2. Health check básico
curl -i https://api.gt360.app/

# Debe devolver 404 (es normal, no hay ruta /)
# Si no responde → Backend down
```

---

### Paso 3: Verificar Variables de Entorno

```bash
# En el servidor Next.js
printenv | grep API

# Debe mostrar:
# API_URL=https://api.gt360.app
# NEXT_PUBLIC_API_URL=https://api.gt360.app
```

Si no aparecen:
```bash
# Agregar a .env.production
echo "API_URL=https://api.gt360.app" >> .env.production
echo "NEXT_PUBLIC_API_URL=https://api.gt360.app" >> .env.production

# Rebuild
npm run build
pm2 restart nextjs
```

---

### Paso 4: Test de SSR Local

```bash
# En tu máquina de desarrollo
cd frontend
npm run build
npm run start

# Abre http://localhost:3000
# ¿Funciona localmente?
# → SÍ: Problema en deployment/servidor
# → NO: Problema en el código
```

---

### Paso 5: Revisar Cambios Recientes en Frontend

```bash
# Ver últimos commits
git log --oneline -10

# Ver qué cambió en page.tsx y layout.tsx
git diff HEAD~5 app/page.tsx
git diff HEAD~5 app/layout.tsx
```

**Buscar**:
- Nuevas llamadas a fetch()
- Nuevos `await` en componentes Server
- Cambios en middleware.ts
- Nuevas dependencias en package.json

---

## 🎯 Pruebas Específicas

### Test 1: Simular SSR Request

```bash
# Desde el servidor Next.js, probar fetch interno
node -e "
  fetch('https://api.gt360.app/v1/locations', {
    headers: {
      'Authorization': 'Bearer test-token'
    }
  })
  .then(r => console.log('Status:', r.status))
  .catch(e => console.error('Error:', e.message))
"

# ¿Funciona?
# → SÍ: El problema es en el código SSR de Next.js
# → NO: Problema de red/DNS en el servidor
```

### Test 2: Verificar DNS Resolution

```bash
# En el servidor Next.js
nslookup api.gt360.app
ping api.gt360.app

# ¿Resuelve correctamente?
# → SÍ: OK
# → NO: Problema de DNS
```

### Test 3: Verificar Firewall

```bash
# En el servidor Next.js
telnet api.gt360.app 443

# ¿Se conecta?
# → SÍ: OK
# → NO: Firewall bloqueando
```

---

## 🚀 Fixes Rápidos Temporales

### Fix 1: Desactivar SSR Temporalmente

```typescript
// En page.tsx
export const dynamic = 'force-dynamic';
export const revalidate = 0;

// O hacer el componente Client-Side
'use client';

export default function Page() {
  // Ahora corre en el cliente
  useEffect(() => {
    fetch('/api/locations').then(/*...*/);
  }, []);
}
```

### Fix 2: Agregar Fallback

```typescript
// En page.tsx
export default async function Page() {
  try {
    const data = await fetch(url);
    return <Component data={data} />;
  } catch (error) {
    console.error('SSR Error:', error);
    // Fallback en lugar de 500
    return <ErrorBoundary error={error} />;
  }
}
```

### Fix 3: Usar API Routes

```typescript
// En lugar de fetch directo al backend en SSR:
// app/api/locations/route.ts
export async function GET() {
  const data = await fetch('https://api.gt360.app/v1/locations');
  return Response.json(data);
}

// En page.tsx
const data = await fetch('/api/locations'); // ✅ Ruta local
```

---

## 📋 Checklist de Verificación

- [ ] Logs del servidor Next.js revisados
- [ ] Stack trace identificado
- [ ] Variables de entorno verificadas
- [ ] Backend endpoints probados manualmente
- [ ] Cambios recientes en frontend revisados
- [ ] Tests SSR ejecutados
- [ ] DNS/network verificados
- [ ] Hard refresh en navegador (`Ctrl+Shift+R`)
- [ ] Modo incógnito probado
- [ ] Deploy exitoso confirmado

---

## 📞 Información Adicional Necesaria

Para ayudar mejor, necesito:

1. **Logs completos del servidor Next.js**
   ```bash
   # Últimas 200 líneas
   vercel logs | tail -200
   ```

2. **Stack trace específico del error 500**
   ```
   Error: ...
   at ...
   at ...
   ```

3. **Variables de entorno del servidor Next.js** (sin tokens)
   ```bash
   printenv | grep -E "(API|NEXT_PUBLIC)"
   ```

4. **Últimos commits en el frontend**
   ```bash
   git log --oneline -10
   ```

5. **¿Cuándo empezó el error?**
   - Después de un deploy del frontend?
   - Después del cambio en el backend?
   - De repente sin cambios?

---

## 🎯 Conclusión Preliminar

Basado en la evidencia:

1. ✅ **Backend está OK**: No hay errores 500 en los logs
2. ✅ **Endpoints funcionan**: Responden correctamente
3. ❌ **Error es del Frontend**: Next.js SSR failing
4. 🔍 **Causa más probable**:
   - Error en SSR al cargar datos iniciales
   - Variable de entorno faltante
   - Timeout en fetch() durante SSR

**Próximo paso**: Revisar logs del servidor Next.js para ver el stack trace exacto.

---

**Última actualización**: 2026-01-10 12:20 UTC
