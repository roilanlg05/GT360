# Ground Filters WebSocket Fix - Deployment Guide

**Fecha:** 2026-01-26
**Commit:** 576682c8d297c0552d75e8edb3fe82a61bffc1d3
**Severidad:** CRÍTICA - Los eventos de filtros no llegaban al frontend

---

## Resumen del Fix

### Problema Encontrado

El `WSManager` estaba ignorando eventos `step_applied` y `step_reverted` publicados por `step_filter_service`, causando que el frontend NUNCA recibiera notificaciones cuando se aplicaban o revertían filtros.

### Solución Aplicada

**Archivo modificado:** `features/trips/utils/ws_manager.py`

**Cambios:**
```python
# Agregado en _location_listener() líneas 144-147:

# Handle filter step events - forward to clients
if event_type in ("step_applied", "step_reverted"):
    await self.route_location_event(location_id, ev)
    continue
```

---

## Estado Actual del Servidor

```bash
Proceso: PID 3252268
Usuario: deploy
Comando: /usr/local/bin/python3.14 /usr/local/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1
Iniciado: Sun Jan 25 18:32:45 2026
Estado: Running (UP 2 days)
```

**Redis Container:**
```
Container ID: efbe1a9ac00d
Image: redis:7
Status: Up 2 days
Port: 0.0.0.0:6379->6379/tcp
```

---

## Deployment Necesario

### ⚠️ IMPORTANTE: El servidor NECESITA reiniciarse

El proceso de uvicorn **NO tiene** el flag `--reload`, por lo tanto:
- ❌ Los cambios en `ws_manager.py` NO se cargarán automáticamente
- ❌ El fix NO estará activo hasta reiniciar
- ✅ El commit ya está creado (576682c)

### Opciones de Deployment

#### Opción 1: Graceful Restart (Recomendado para Producción)

```bash
# Si usas supervisor/systemd
sudo systemctl restart gt360-backend

# O si usas docker-compose
docker-compose restart app

# O si usas un script de deploy
./scripts/deploy.sh
```

#### Opción 2: Restart Manual (Solo Development)

```bash
# Matar proceso actual
kill 3252268

# Iniciar nuevamente (en screen/tmux o como daemon)
cd /home/backend/GT360
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1
```

#### Opción 3: Hot Reload (Si está disponible)

```bash
# Algunos deployment tools soportan reload sin downtime
# Ejemplo: Gunicorn con worker reload
kill -HUP 3252268  # Enviar señal HUP
```

---

## Verificación Post-Deployment

### 1. Verificar que el servidor reinició

```bash
# Ver logs del servidor
tail -f /var/log/gt360/backend.log  # o donde estén los logs

# Verificar proceso
ps aux | grep uvicorn | grep -v grep

# Verificar que responda
curl http://localhost:8000/health
```

### 2. Verificar que el fix esté activo

```bash
# Hacer un grep del código cargado (si tienes acceso a logs)
# Debería mostrar el nuevo handler de step_applied/step_reverted

# O verificar la versión del commit
cd /home/backend/GT360
git log -1 --oneline
# Debería mostrar: 576682c fix: Forward filter step events...
```

### 3. Test del WebSocket con eventos de filtros

**Test desde consola del navegador:**

```javascript
// Conectar WebSocket
const ws = new WebSocket('wss://api.gt360.app/ws/trips?location_id=YOUR_LOCATION_ID&token=YOUR_JWT_TOKEN');

ws.onopen = () => console.log('✅ WebSocket Connected');

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('[WebSocket]', message.type, message);

  // Después de aplicar un filtro desde la UI, deberías ver:
  // [WebSocket] step_applied { filter_type: "reduce", trips_affected: 25, ... }
};

ws.onerror = (e) => console.error('❌ WebSocket Error:', e);
```

**Test aplicando un filtro:**

1. Conectar WebSocket desde frontend
2. Aplicar un filtro (ej: Reduce con 15 minutos)
3. Verificar en consola del navegador:
   ```
   [WebSocket] step_applied
   {
     type: "step_applied",
     filter_type: "reduce",
     trips_affected: 25,
     ...
   }
   ```

### 4. Verificar Redis PubSub (Desde dentro del container)

```bash
# Entrar al container de Redis
docker exec -it redis-service redis-cli

# Suscribirse a eventos de una location
SUBSCRIBE loc:123e4567-e89b-12d3-a456-426614174000

# En otra terminal, aplicar un filtro desde la UI
# Deberías ver el evento publicado:
# 1) "message"
# 2) "loc:123e4567-..."
# 3) "{\"type\":\"step_applied\",\"filter_type\":\"reduce\",...}"
```

---

## Impacto del Fix

### ANTES del deployment:
- ❌ Frontend NUNCA recibe eventos step_applied/step_reverted
- ❌ Sincronización multi-tab NO funciona
- ❌ Notificaciones de filtros NO aparecen
- ❌ Console NO muestra: `[WebSocket] Filter applied: reduce`

### DESPUÉS del deployment:
- ✅ Frontend recibe eventos en tiempo real
- ✅ Sincronización multi-tab funciona
- ✅ Notificaciones toast aparecen automáticamente
- ✅ Console muestra: `[WebSocket] Filter applied: reduce`

---

## Rollback Plan

Si hay problemas después del deployment:

```bash
# 1. Revertir el commit
git revert 576682c

# 2. Reiniciar servidor
systemctl restart gt360-backend

# 3. El sistema volverá al comportamiento anterior
# (sin eventos de filtros vía WebSocket, pero funcional)
```

**Nota:** El rollback es seguro porque:
- El fix es aditivo (no modifica lógica existente)
- Solo agrega reenvío de eventos adicionales
- No afecta la funcionalidad de trips_batch

---

## Checklist de Deployment

- [x] Commit creado (576682c)
- [x] Código verificado (git diff)
- [x] Servidor identificado (PID 3252268)
- [x] Redis verificado (container efbe1a9ac00d running)
- [ ] **Servidor reiniciado** ⬅️ PENDIENTE
- [ ] WebSocket testeado desde frontend
- [ ] Eventos step_applied/step_reverted confirmados

---

## Siguientes Pasos

1. **Reiniciar el servidor** para cargar el fix
2. **Testear** aplicando un filtro desde el frontend
3. **Verificar** en consola del navegador que llegan los eventos
4. **Confirmar** que la sincronización multi-tab funciona
5. **Deploy** del frontend (Phases 3-5 del plan de implementación)

---

## Contacto y Soporte

Si hay problemas después del deployment:
1. Revisar logs del servidor: `/var/log/gt360/backend.log`
2. Verificar Redis: `docker logs redis-service`
3. Rollback si es necesario (ver sección anterior)

**Estado:** ✅ Fix aplicado, commit creado, **esperando restart del servidor**
