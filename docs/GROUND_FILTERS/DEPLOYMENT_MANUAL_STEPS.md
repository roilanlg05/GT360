# Ground Filters WebSocket Fix - Deployment Manual

**Commit:** 576682c8d297c0552d75e8edb3fe82a61bffc1d3
**Fecha:** 2026-01-26
**Requiere:** Restart del servidor FastAPI

---

## ⚠️ ACCIÓN REQUERIDA

El fix del WebSocket **YA ESTÁ APLICADO** en el código:
- ✅ Commit creado: 576682c
- ✅ Archivo modificado: `features/trips/utils/ws_manager.py`
- ✅ Documentación completa creada

**PENDIENTE:** Reiniciar el servidor para activar los cambios

---

## Opciones de Deployment

### Opción 1: Restart con Usuario Deploy (Recomendado)

```bash
# Cambiar a usuario deploy
sudo su - deploy

# Ir al directorio del proyecto
cd /home/backend/GT360

# Verificar el commit actual
git log -1 --oneline
# Debe mostrar: 576682c fix: Forward filter step events...

# Matar proceso actual
kill 3252268

# Reiniciar servidor
nohup .venv/bin/uvicorn main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --proxy-headers \
  --forwarded-allow-ips 127.0.0.1 \
  > /var/log/gt360/backend.log 2>&1 &

# Anotar el nuevo PID
echo $! > /tmp/gt360_backend.pid

# Verificar que esté corriendo
ps aux | grep uvicorn | grep -v grep
```

### Opción 2: Restart con Systemd (Si está configurado)

```bash
sudo systemctl restart gt360-backend
sudo systemctl status gt360-backend
```

### Opción 3: Restart con Docker (Si el backend está dockerizado)

```bash
docker-compose restart app
docker-compose logs -f app
```

---

## Verificación Post-Restart

### 1. Verificar Proceso

```bash
# Ver proceso nuevo
ps aux | grep uvicorn | grep -v grep

# El PID debe ser DIFERENTE de 3252268
# El timestamp debe ser POSTERIOR a: 2026-01-26 01:51:16
```

### 2. Test HTTP Básico

```bash
curl http://localhost:8000/health
# Debe responder con éxito
```

### 3. Verificar Logs

```bash
# Ver logs en tiempo real
tail -f /var/log/gt360/backend.log

# Buscar errores
grep -i error /var/log/gt360/backend.log | tail -20
```

### 4. Test del Fix WebSocket

**Desde Redis CLI (dentro del container):**

```bash
# Entrar al container Redis
docker exec -it redis-service redis-cli

# Suscribirse a eventos de prueba
SUBSCRIBE loc:test-location-123

# En otra terminal, publicar evento de prueba:
docker exec -it redis-service redis-cli
> PUBLISH loc:test-location-123 '{"type":"step_applied","filter_type":"reduce"}'
```

**Desde Frontend (navegador):**

```javascript
// Abrir consola DevTools
const ws = new WebSocket('ws://localhost:8000/ws/trips?location_id=YOUR_LOCATION_ID&token=YOUR_JWT');

ws.onopen = () => console.log('✅ Connected');
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  console.log('[WebSocket]', msg.type, msg);
};

// Luego aplicar un filtro desde la UI
// Deberías ver: [WebSocket] step_applied { filter_type: "reduce", ... }
```

---

## Impacto del Fix

### ANTES del restart:
```
✅ Servidor funcionando (PID 3252268, iniciado Jan 25)
✅ Commit aplicado (576682c)
❌ Fix NO activo (servidor con código antiguo)
❌ Eventos step_applied/step_reverted NO llegan al frontend
```

### DESPUÉS del restart:
```
✅ Servidor funcionando (PID nuevo, iniciado después de Jan 26 01:51:16)
✅ Commit aplicado (576682c)
✅ Fix ACTIVO (servidor con código nuevo)
✅ Eventos step_applied/step_reverted SÍ llegan al frontend
```

---

## Timeline de Cambios

```
2026-01-26 01:51:16  - Archivo ws_manager.py modificado
2026-01-26 01:58:30  - Commit 576682c creado
2026-01-26 02:XX:XX  - Servidor reiniciado (PENDIENTE)
2026-01-26 02:XX:XX  - Fix activo y funcional
```

---

## Troubleshooting

### Si el servidor no inicia:

```bash
# Verificar logs
tail -100 /var/log/gt360/backend.log

# Verificar puertos
lsof -i :8000
netstat -tlnp | grep 8000

# Verificar dependencias
cd /home/backend/GT360
.venv/bin/python -c "import redis.asyncio; print('Redis OK')"
```

### Si hay errores de conexión Redis:

```bash
# Verificar container Redis
docker ps | grep redis

# Verificar conectividad
docker exec redis-service redis-cli ping
# Debe responder: PONG
```

### Si el WebSocket no funciona:

```bash
# Verificar que el fix esté en el código activo
curl http://localhost:8000/ 2>&1 | head -5

# Verificar timestamp del servidor
ps -p $(pgrep -f "uvicorn main:app") -o lstart=
# Debe ser POSTERIOR a 2026-01-26 01:51:16
```

---

## Comando de Restart Recomendado

**Para ejecutar como root o con sudo:**

```bash
#!/bin/bash
set -e

echo "🔄 GT360 Backend Deployment - WebSocket Fix"
echo "==========================================="

# Variables
OLD_PID=3252268
PROJECT_DIR="/home/backend/GT360"
LOG_FILE="/var/log/gt360/backend.log"

# Verificar commit
cd $PROJECT_DIR
CURRENT_COMMIT=$(git log -1 --oneline | awk '{print $1}')
echo "📝 Current commit: $CURRENT_COMMIT"

if [ "$CURRENT_COMMIT" != "576682c" ]; then
    echo "⚠️  Warning: Expected commit 576682c, got $CURRENT_COMMIT"
fi

# Matar proceso antiguo
echo "🛑 Stopping old server (PID: $OLD_PID)..."
sudo kill $OLD_PID || echo "Process already stopped"
sleep 3

# Verificar que terminó
if ps -p $OLD_PID > /dev/null 2>&1; then
    echo "⚠️  Process still running, force killing..."
    sudo kill -9 $OLD_PID
    sleep 2
fi

# Limpiar logs antiguos (opcional)
echo "🧹 Rotating logs..."
sudo mv $LOG_FILE $LOG_FILE.$(date +%Y%m%d_%H%M%S) 2>/dev/null || true

# Iniciar servidor nuevo
echo "🚀 Starting new server..."
cd $PROJECT_DIR
sudo -u deploy nohup $PROJECT_DIR/.venv/bin/uvicorn main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --proxy-headers \
  --forwarded-allow-ips 127.0.0.1 \
  > $LOG_FILE 2>&1 &

NEW_PID=$!
echo "✅ New server started (PID: $NEW_PID)"

# Esperar a que el servidor esté listo
echo "⏳ Waiting for server to be ready..."
sleep 5

# Verificar salud
echo "🏥 Health check..."
HEALTH=$(curl -s http://localhost:8000/ 2>&1 | head -1)
if [ -n "$HEALTH" ]; then
    echo "✅ Server is responding"
    echo "Response: $HEALTH"
else
    echo "❌ Server is not responding"
    tail -20 $LOG_FILE
    exit 1
fi

# Verificar WebSocket fix
echo "🔍 Verifying WebSocket fix is active..."
TIMESTAMP=$(stat -c %y $PROJECT_DIR/features/trips/utils/ws_manager.py | cut -d. -f1)
SERVER_START=$(ps -p $NEW_PID -o lstart= 2>/dev/null | xargs -I{} date -d "{}" +%Y-%m-%d\ %H:%M:%S)

echo "File modified: $TIMESTAMP"
echo "Server started: $SERVER_START"

if [[ "$SERVER_START" > "$TIMESTAMP" ]] || [[ "$SERVER_START" == "$TIMESTAMP" ]]; then
    echo "✅ Server has latest code"
else
    echo "⚠️  Warning: Server might not have latest code"
fi

echo ""
echo "=========================================="
echo "✅ Deployment completed successfully!"
echo "New PID: $NEW_PID"
echo "Logs: $LOG_FILE"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Monitor logs: tail -f $LOG_FILE"
echo "2. Test WebSocket from frontend"
echo "3. Verify events: step_applied, step_reverted"
```

**Guardar como:** `/home/backend/GT360/scripts/restart_backend.sh`

**Ejecutar:**
```bash
chmod +x /home/backend/GT360/scripts/restart_backend.sh
sudo /home/backend/GT360/scripts/restart_backend.sh
```

---

## Estado Actual

```
✅ Fix aplicado en código
✅ Commit creado (576682c)
✅ Documentación completa
❌ Servidor NO reiniciado (requiere privilegios de usuario deploy o sudo)
```

**Siguiente acción:** Ejecutar el script de restart o contactar al administrador del servidor.

---

## Alternativa Sin Restart

Si el restart no es posible inmediatamente, el sistema continuará funcionando con el código antiguo:

- ✅ API endpoints funcionan normalmente
- ✅ Filtros se aplican correctamente en DB
- ❌ WebSocket NO envía eventos step_applied/step_reverted
- ⚠️  Frontend NO recibirá notificaciones en tiempo real

**Workaround temporal:** El frontend puede usar polling en lugar de eventos WebSocket hasta que se reinicie el servidor.
