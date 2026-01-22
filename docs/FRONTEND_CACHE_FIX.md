# 🔴 SOLUCIÓN: Error 500 Cacheado en Frontend

## ❗ Problema Confirmado

El backend está funcionando correctamente:
- ✅ Endpoint `/filters/current` existe y responde
- ✅ CORS está configurado correctamente para `https://web.gt360.app`
- ✅ Headers CORS presentes en todas las respuestas
- ✅ Retorna 401 para tokens inválidos (comportamiento correcto)

**El problema es que el navegador/frontend tiene cacheadas respuestas 500 de cuando el endpoint estaba en desarrollo.**

---

## ✅ SOLUCIONES (En orden de prioridad)

### 1️⃣ Hard Refresh en el Navegador (URGENTE)

**Para usuarios finales:**
- **Mac**: `Cmd + Shift + R` o `Cmd + Option + R`
- **Windows/Linux**: `Ctrl + Shift + R` o `Ctrl + F5`

**O alternativamente:**
1. Abrir DevTools (F12)
2. Network tab
3. Click derecho → "Clear browser cache"
4. Refrescar la página

---

### 2️⃣ Limpiar React Query Cache (Para Desarrolladores)

**Opción A: Desde la consola del navegador**

```javascript
// Ejecutar esto en la consola del navegador:
import { useQueryClient } from '@tanstack/react-query'
const queryClient = useQueryClient()

// Limpiar TODO el cache
queryClient.clear()

// O solo el cache de filters:
queryClient.removeQueries({ queryKey: ['filterConfig'] })
queryClient.removeQueries({ queryKey: ['filters'] })

// Luego refrescar:
location.reload()
```

**Opción B: En el código (temporal para debugging)**

```typescript
// En use-filter-backend-sync.ts o similar:
useQuery({
  queryKey: ['filterConfig', locationId, airline],
  queryFn: () => getFilterConfig(locationId, airline),
  retry: 3,
  staleTime: 0,        // ← Agregar temporalmente
  cacheTime: 0,        // ← Agregar temporalmente
  refetchOnMount: true,  // ← Agregar temporalmente
})
```

---

### 3️⃣ Desregistrar Service Workers (Si existen)

```javascript
// En la consola del navegador:
navigator.serviceWorker.getRegistrations().then(registrations => {
  registrations.forEach(registration => {
    console.log('Unregistering service worker:', registration)
    registration.unregister()
  })
})

// Luego refrescar con Hard Reload
location.reload()
```

---

### 4️⃣ Limpiar Cache HTTP del Navegador

**Chrome/Edge/Brave:**
1. Abrir DevTools (F12)
2. Ir a "Application" tab
3. Sidebar izquierdo → "Storage"
4. Click en "Clear site data"
5. Marcar todas las opciones
6. Click "Clear site data"

**Safari:**
1. Safari → Settings → Privacy
2. "Manage Website Data"
3. Buscar "gt360.app"
4. Remove

**Firefox:**
1. DevTools (F12) → Storage tab
2. Right-click en el dominio → "Delete All"

---

### 5️⃣ Verificar Axios Interceptors (Para Desarrolladores)

Buscar en el código si hay interceptores que estén cacheando respuestas:

```typescript
// Revisar en client.ts o api.ts
axiosInstance.interceptors.response.use(
  response => {
    // ¿Hay alguna lógica de cache aquí?
    return response
  },
  error => {
    // ¿Está guardando errores en cache?
    return Promise.reject(error)
  }
)
```

---

### 6️⃣ Verificar React Query DevTools (Para Desarrolladores)

Si tienen React Query DevTools instalado:

1. Abrir la aplicación
2. Presionar React Query DevTools (ícono en la esquina)
3. Buscar queries con key "filterConfig" o "filters"
4. Ver el status de cada query
5. Click en cada una → "Remove" o "Invalidate"

---

### 7️⃣ Modo Incógnito / Private (Test Rápido)

Para verificar que es un problema de cache:

1. Abrir ventana incógnito/privada
2. Ir a `https://web.gt360.app`
3. Hacer login
4. Probar el endpoint de filters

**Si funciona en incógnito → Confirma que es cache**

---

## 🧪 Verificación que el Backend Funciona

Ejecutar esto desde la terminal del servidor o cualquier máquina:

```bash
# Test 1: Verificar que endpoint existe
curl -I https://api.gt360.app/v1/locations/36e9faa1-4812-4bc4-a0ce-dcf4511d8b94/airlines/WN/trips/filters/current \
  -H "Authorization: Bearer test"

# Debería devolver: HTTP/2 401 (correcto - token inválido)

# Test 2: Verificar CORS headers
curl -i -X OPTIONS https://api.gt360.app/v1/locations/36e9faa1-4812-4bc4-a0ce-dcf4511d8b94/airlines/WN/trips/filters/current \
  -H "Origin: https://web.gt360.app" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization,content-type"

# Debería mostrar headers:
# access-control-allow-origin: https://web.gt360.app
# access-control-allow-credentials: true
```

Ambos tests confirman que el backend está funcionando.

---

## 🔍 Debug: Ver qué está pasando

**En el navegador, abrir DevTools → Network:**

1. Marcar "Disable cache"
2. Hacer la petición
3. Click en la petición `/filters/current`
4. Ver la pestaña "Headers"
5. Verificar:
   - **Request Headers**: ¿Está enviando `Authorization: Bearer ...`?
   - **Response Headers**: ¿Tiene `access-control-allow-origin`?
   - **Status Code**: ¿Es 200/401 o aún 500?

Si el Status Code sigue siendo 500 con "Disable cache" marcado, entonces:
- React Query está cacheando (ver solución 2️⃣)
- O hay un Service Worker (ver solución 3️⃣)

---

## ⚠️ Posibles Causas Restantes

Si después de hacer todo lo anterior el error persiste:

### A. React Query con gcTime infinito

```typescript
// Buscar en el código configuración global de React Query:
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      gcTime: Infinity,  // ← ESTO es malo, nunca libera cache
      staleTime: Infinity,  // ← ESTO también
    }
  }
})

// Cambiar temporalmente a:
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      gcTime: 5 * 60 * 1000,  // 5 minutos
      staleTime: 0,  // Siempre marca como stale
    }
  }
})
```

### B. localStorage con respuesta cacheada

```javascript
// Ejecutar en consola del navegador:
console.log('localStorage keys:', Object.keys(localStorage))

// Buscar keys relacionadas con "filter" o "cache"
// Si encuentran algo sospechoso:
localStorage.removeItem('REACT_QUERY_OFFLINE_CACHE')
localStorage.clear()  // Nuclear option
```

### C. IndexedDB con cache persistente

```javascript
// Ejecutar en consola:
indexedDB.databases().then(dbs => {
  console.log('IndexedDB databases:', dbs)
  dbs.forEach(db => {
    console.log('Deleting:', db.name)
    indexedDB.deleteDatabase(db.name)
  })
})
```

---

## 📞 Si Nada Funciona

Contactar al equipo de backend con:

1. **Screenshot de Network tab** mostrando:
   - URL completa de la petición
   - Request headers (especialmente `Authorization`)
   - Response headers (especialmente `access-control-*`)
   - Status code

2. **Información del navegador**:
   - Navegador y versión (Chrome 131, Safari 18, etc.)
   - Sistema operativo
   - ¿Funciona en incógnito?

3. **Logs de React Query**:
   - Estado de la query en React Query DevTools
   - `queryKey` usado
   - Configuración de retry/staleTime/gcTime

---

## ✅ Resumen

**El backend está funcionando correctamente desde 2026-01-19 01:23 UTC.**

El problema es cache en el frontend. La solución más rápida:

1. Hard refresh: `Cmd+Shift+R` o `Ctrl+Shift+R`
2. Clear React Query cache desde consola
3. Probar en modo incógnito

Si persiste, revisar configuración de React Query y Service Workers.
