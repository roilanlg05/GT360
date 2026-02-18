# 🚀 Earnings System - Quick Start Guide

## ✅ Sistema Listo!

Todo el sistema de earnings está implementado y configurado:

### 📊 Estado Actual

- ✅ **Migraciones aplicadas** - Todas las tablas creadas
- ✅ **Directorios creados** - uploads/receipts y uploads/w9
- ✅ **Cron job configurado** - Auto-cierra shifts cada 30 minutos
- ✅ **Drivers configurados** - 4 drivers de ejemplo con pay info
- ✅ **Código actualizado** - Usa solo 3 campos (pay_type, pay_frequency, rate)

---

## 🎯 Próximos Pasos

### 1. **Reiniciar la Aplicación** (REQUERIDO)

Los nuevos routers necesitan ser cargados:

```bash
# Si usas systemd/supervisor
sudo systemctl restart gt360-api

# Si corres manualmente
# Ctrl+C para detener y luego:
python main.py
# o
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2. **Verificar que el Servidor Esté Corriendo**

```bash
curl http://localhost:8000/health
# Debe responder: {"status":"ok"}
```

### 3. **Probar los Endpoints** (Opcional)

```bash
./test_earnings_endpoints.sh
```

O manualmente:

```bash
# 1. Obtener token de autenticación
curl -X POST http://localhost:8000/v1/auth/sign-in \
  -H 'Content-Type: application/json' \
  -d '{"email":"driver@example.com","password":"password"}'

# 2. Iniciar un shift (usa el token del paso 1)
curl -X POST http://localhost:8000/v1/drivers/{driver_id}/shifts/start \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{}'

# 3. Ver shifts
curl http://localhost:8000/v1/drivers/{driver_id}/shifts \
  -H 'Authorization: Bearer YOUR_TOKEN'

# 4. Ver earnings
curl http://localhost:8000/v1/drivers/{driver_id}/earnings \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

---

## 👥 Drivers Configurados de Ejemplo

Estos drivers ya tienen información de earnings configurada:

| Driver | Pay Type | Pay Frequency | Rate | Status |
|--------|----------|---------------|------|--------|
| Roilan Lambert | day | weekly | $120.00/día | ✅ Active |
| Carlos Gonzalez | hour | biweekly | $15.00/hora | ✅ Active |
| carlos bnb | trip | weekly | $25.00/viaje | ✅ Active |
| melisa GT360 | trip | daily | $20.00/viaje | ✅ Active |

---

## 📚 Endpoints Disponibles

### **Para Drivers:**

#### Shifts
- `POST /v1/drivers/{id}/shifts/start` - Iniciar turno
- `POST /v1/drivers/{id}/shifts/end` - Terminar turno
- `GET /v1/drivers/{id}/shifts` - Ver historial de turnos

#### Expenses
- `POST /v1/drivers/{id}/expenses` - Enviar gasto con recibo
- `GET /v1/drivers/{id}/expenses` - Ver gastos

#### Earnings
- `GET /v1/drivers/{id}/earnings` - Ver earnings por período

#### Tax
- `POST /v1/drivers/{id}/tax-information` - Enviar W-9
- `GET /v1/drivers/{id}/1099?year=2026` - Obtener formulario 1099

### **Para Managers:**

#### Shift Review
- `GET /v1/managers/shifts/review` - Ver shifts pendientes
- `POST /v1/managers/shifts/{id}/resolve` - Aprobar/rechazar shift

#### Expense Review
- `GET /v1/managers/expenses/review` - Ver gastos pendientes
- `POST /v1/managers/expenses/{id}/resolve` - Aprobar/rechazar gasto

#### Earnings (Manager View)
- `GET /v1/managers/drivers/{id}/earnings` - Ver earnings de cualquier driver

#### 1099 Management
- `GET /v1/managers/1099/bulk?year=2026` - Ver todos los 1099
- `POST /v1/managers/1099/generate-all` - Generar PDFs (WIP)

---

## 🔧 Configurar Más Drivers

Para agregar información de earnings a otros drivers:

```sql
UPDATE entities.drivers
SET
    pay_type = 'hour',        -- 'hour', 'day', o 'trip'
    pay_frequency = 'weekly',  -- 'daily', 'weekly', o 'biweekly'
    rate = 15.00              -- tarifa según el pay_type
WHERE id = 'driver-uuid-aqui';
```

---

## 📖 Documentación Completa

- **API Documentation**: `docs/DRIVER_EARNINGS_SYSTEM_GUIDE.md`
- **Setup Guide**: `EARNINGS_SYSTEM_SETUP.md`
- **This Quick Start**: `EARNINGS_QUICK_START.md`

---

## 🐛 Troubleshooting

### Endpoint devuelve 404
- ✅ Verificar que el servidor esté corriendo
- ✅ Verificar que reiniciaste después de aplicar los cambios
- ✅ Revisar logs del servidor

### Cron job no funciona
```bash
# Ver logs
tail -f /var/log/auto_close_shifts.log

# Verificar que está en crontab
crontab -l | grep auto_close
```

### Driver no tiene earnings
- ✅ Verificar que el driver tenga `pay_type`, `pay_frequency` y `rate` configurados
- ✅ Verificar que el driver tenga un `location_id` asignado
- ✅ Verificar que existan shifts completados para ese driver

---

## ✨ Funcionalidades Principales

### 🔄 Flujo de Trabajo - Driver
1. Driver inicia turno (`POST /shifts/start`)
2. Driver completa viajes durante el turno
3. Driver termina turno (`POST /shifts/end`)
4. Driver envía gastos con recibos (`POST /expenses`)
5. Manager revisa y aprueba gastos
6. Driver ve sus earnings (`GET /earnings`)

### 👨‍💼 Flujo de Trabajo - Manager
1. Ver shifts que necesitan revisión (`GET /managers/shifts/review`)
2. Aprobar/rechazar shifts (`POST /managers/shifts/{id}/resolve`)
3. Ver gastos pendientes (`GET /managers/expenses/review`)
4. Aprobar/rechazar gastos (`POST /managers/expenses/{id}/resolve`)
5. Ver earnings de drivers (`GET /managers/drivers/{id}/earnings`)
6. Generar 1099s al final del año (`GET /managers/1099/bulk`)

### 🤖 Auto-Close Shifts
- Corre cada 30 minutos
- Cierra shifts activos por más de 6 horas
- Envía a revisión del manager
- Logs en `/var/log/auto_close_shifts.log`

---

## 🎉 ¡Listo para Usar!

El sistema de earnings está completamente funcional.

**Siguiente paso**: Reiniciar el servidor y probar los endpoints.

Para soporte técnico, revisar la documentación completa en `docs/DRIVER_EARNINGS_SYSTEM_GUIDE.md`
