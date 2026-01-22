# Proceso de Deploy - GT360 Backend

## 🐳 Arquitectura

El backend corre en un contenedor Docker administrado por `docker-compose`.

**Importante**: El código NO está montado como volumen, por lo que cualquier cambio requiere reconstruir la imagen Docker.

## 🔄 Pasos para Deploy

### 1. Hacer cambios en el código
```bash
# Editar archivos normalmente
vim features/trips/routes/trips_router.py
```

### 2. Reconstruir imagen Docker
```bash
cd /home/backend/GT360
docker-compose build app
```

### 3. Reiniciar contenedor
```bash
docker-compose up -d app
```

### 4. Verificar deploy
```bash
# Ver logs
docker logs gt360 --tail 50

# Verificar que el contenedor está corriendo
docker ps | grep gt360

# Probar endpoint
curl http://localhost:8000/openapi.json | python3 -m json.tool
```

## 📋 Comandos Útiles

### Ver estado de contenedores
```bash
docker-compose ps
```

### Ver logs en tiempo real
```bash
docker logs -f gt360
```

### Rebuild completo (si hay problemas)
```bash
docker-compose down
docker-compose build --no-cache app
docker-compose up -d
```

### Limpiar cache de Python en el contenedor
```bash
docker exec gt360 find /app -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
docker restart gt360
```

## ⚠️ Notas Importantes

1. **NO hay auto-reload**: Cualquier cambio en el código requiere rebuild + restart
2. **Cache de Python**: Si cambias código pero no ves resultados, rebuild con `--no-cache`
3. **Múltiples servicios**: El sistema tiene varios contenedores (app, streaming, redis, postgres)
4. **Verificar siempre**: Después de deploy, verificar el OpenAPI schema o hacer un test request

## 🧪 Verificar Cambios Específicos

Para verificar que un cambio específico está deployado:

```bash
# Ejemplo: Verificar límite de paginación
curl -s http://localhost:8000/openapi.json | \
python3 -c "
import json, sys
data = json.load(sys.stdin)
params = data['paths']['/v1/locations/{location_id}/trips']['get']['parameters']
limit = next(p for p in params if p['name'] == 'limit')
print(f\"Default: {limit['schema']['default']}\")
print(f\"Max: {limit['schema']['maximum']}\")
"
```

## 📝 Changelog de Deploys

### 2026-01-18 - Optimización de Paginación
- ✅ Cambio: `limit` default 20 → 100
- ✅ Cambio: `limit` máximo 50 → 200
- ✅ Objetivo: Optimizar para infinite scroll
- ✅ Archivo: `features/trips/routes/trips_router.py`

---

**Última actualización**: 2026-01-18 20:45 CET
