# ⏰ Ejemplo: Mostrar Horas en Exclusiones del Preview

## 🎯 Objetivo

Mostrar la hora actual de cada trip excluido en el modal de "Preview Changes", replicando el diseño de la imagen.

---

## 📊 Datos del Backend (Actualizados)

### Response con Horas Incluidas:

```json
{
  "exclusions": [
    {
      "operation": "expand(1903, 4287)",
      "trip_ids": ["uuid1", "uuid2"],
      "reason": "Collision: gap with next trip would enter Combine range (15 min)",
      "gap_before": 25,
      "gap_after": 15,
      "trips_info": [
        {
          "trip_id": "uuid1",
          "airline": "WN",
          "flight_number": "1903",
          "hotel_name": "Hyatt Regency Louisville",
          "pick_up_date": "2025-12-13",
          "pick_up_time": "13:25",           // ✅ NUEVO
          "original_pick_up_time": null      // ✅ NUEVO
        },
        {
          "trip_id": "uuid2",
          "airline": "WN",
          "flight_number": "4287",
          "hotel_name": "Hyatt Regency Louisville",
          "pick_up_date": "2025-12-13",
          "pick_up_time": "13:50",           // ✅ NUEVO
          "original_pick_up_time": "14:10"   // ✅ Si fue modificado por otro filtro
        }
      ]
    }
  ]
}
```

---

## 🎨 Componente para el Preview Modal

### Componente Completo (Replicando tu diseño):

```tsx
const ExclusionItem = ({ exclusion }: { exclusion: FilterExclusion }) => {
  return (
    <div className="exclusion-card">
      {/* Header: Tipo de exclusión */}
      <div className="exclusion-header">
        <WarningIcon className="warning-icon" />
        <Typography variant="subtitle2" fontWeight="bold">
          Expand excluded
        </Typography>
      </div>

      {/* Trips involucrados con HORA */}
      <div className="trips-row">
        {exclusion.trips_info.map((trip, idx) => (
          <div key={idx} className="trip-info">
            {/* Airline + Flight */}
            <div className="trip-id">
              <Typography variant="body2" fontWeight="bold">
                {trip.airline} {trip.flight_number}
              </Typography>
            </div>

            {/* Hotel */}
            <div className="trip-location">
              <Typography variant="body2" color="text.secondary">
                {trip.hotel_name}
              </Typography>
            </div>

            {/* ✅ HORA ACTUAL */}
            {trip.pick_up_time && (
              <div className="trip-time">
                <AccessTimeIcon fontSize="small" />
                <Typography variant="body2">
                  {trip.pick_up_time}
                </Typography>

                {/* Mostrar hora original si fue modificada */}
                {trip.original_pick_up_time && (
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ textDecoration: 'line-through', ml: 1 }}
                  >
                    {trip.original_pick_up_time}
                  </Typography>
                )}
              </div>
            )}

            {/* Fecha */}
            <div className="trip-date">
              <CalendarIcon fontSize="small" />
              <Typography variant="caption" color="text.secondary">
                {new Date(trip.pick_up_date).toLocaleDateString('en-US', {
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric'
                })}
              </Typography>
            </div>
          </div>
        ))}
      </div>

      {/* Razón de exclusión (amarillo) */}
      <div className="collision-reason">
        <Typography variant="body2" color="warning.main">
          {exclusion.reason}
        </Typography>
      </div>

      {/* Gap info */}
      <div className="gap-info">
        <Typography variant="caption">
          Gap: <strong>{exclusion.gap_before}</strong> → <strong>{exclusion.gap_after}</strong> min
        </Typography>
      </div>
    </div>
  );
};
```

---

## 🎨 CSS / Styled Components

```css
.exclusion-card {
  border: 1px solid #ff9800;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
  background-color: #fff8e1;
}

.exclusion-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.warning-icon {
  color: #ff9800;
}

.trips-row {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
}

.trip-info {
  flex: 1;
  background-color: white;
  border-radius: 8px;
  padding: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.trip-id {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 4px;
}

.trip-location {
  margin-bottom: 8px;
}

/* ✅ ESTILOS PARA LA HORA */
.trip-time {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 4px;
  padding: 4px 8px;
  background-color: #e3f2fd;
  border-radius: 4px;
  width: fit-content;
}

.trip-date {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
}

.collision-reason {
  background-color: #fff3e0;
  border-left: 4px solid #ff9800;
  padding: 8px 12px;
  margin-bottom: 8px;
  border-radius: 4px;
}

.gap-info {
  display: flex;
  justify-content: space-between;
  padding: 8px;
  background-color: #f5f5f5;
  border-radius: 4px;
}
```

---

## 📱 Ejemplo Visual (como en tu imagen)

```
┌─────────────────────────────────────────────────┐
│ ⚠️  Expand excluded                             │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌──────────────────┐  ┌──────────────────┐   │
│  │ WN 1903          │  │ WN 4287          │   │
│  │ Hyatt Regency Lo...│ │ Hyatt Regency Lo...│ │
│  │ ⏰ 13:25          │  │ ⏰ 13:50  ̶1̶4̶:̶1̶0̶  │   │
│  │ 📅 Dec 13, 2025  │  │ 📅 Dec 13, 2025  │   │
│  └──────────────────┘  └──────────────────┘   │
│                                                 │
│  ⚠️  Collision: gap with next trip would       │
│      enter Combine range (15 min)              │
│                                                 │
│  Gap: 25 → 15 min                               │
└─────────────────────────────────────────────────┘
```

---

## 🎯 Variante Compacta (Lista)

Si prefieres una lista más compacta:

```tsx
const ExclusionCompact = ({ exclusion }: { exclusion: FilterExclusion }) => {
  return (
    <div className="exclusion-compact">
      <div className="trips-inline">
        {exclusion.trips_info.map((trip, idx) => (
          <React.Fragment key={idx}>
            <span className="trip-summary">
              {trip.airline} {trip.flight_number} {trip.hotel_name}
              {trip.pick_up_time && (
                <strong className="time"> @ {trip.pick_up_time}</strong>
              )}
            </span>
            {idx < exclusion.trips_info.length - 1 && (
              <span className="separator"> ↔ </span>
            )}
          </React.Fragment>
        ))}
      </div>

      <div className="reason-compact">
        <WarningIcon fontSize="small" />
        <Typography variant="caption">{exclusion.reason}</Typography>
      </div>

      <div className="gap-compact">
        Gap: {exclusion.gap_before} → {exclusion.gap_after} min
      </div>
    </div>
  );
};
```

**Output:**
```
⚠️ WN 1903 Hyatt Regency Lo... @ 13:25 ↔ WN 4287 Hyatt Regency Lo... @ 13:50
   Collision: gap with next trip would enter Combine range (15 min)
   Gap: 25 → 15 min
```

---

## 🔄 Integración en tu Modal Existente

Basándome en tu código actual, aquí está cómo integrarlo:

```tsx
const PreviewChangesModal = ({ open, onClose, previewResult }) => {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        Preview Changes
        <Typography variant="caption">Review changes before applying</Typography>
      </DialogTitle>

      <DialogContent>
        {/* ... tu código existente de cambios ... */}

        {/* ✅ EXCLUSIONES CON HORAS */}
        {previewResult.exclusions && previewResult.exclusions.length > 0 && (
          <div className="exclusions-section">
            <Alert severity="warning" icon={false}>
              <div className="exclusions-header">
                <WarningIcon />
                <Typography variant="subtitle2">
                  {previewResult.exclusions.length} trips excluded
                  ({previewResult.exclusions.length} operations)
                </Typography>
              </div>
            </Alert>

            <Accordion defaultExpanded>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography>View excluded operations</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <div className="exclusions-list">
                  {previewResult.exclusions.map((exclusion, idx) => (
                    <ExclusionItem key={idx} exclusion={exclusion} />
                  ))}
                </div>
              </AccordionDetails>
            </Accordion>
          </div>
        )}
      </DialogContent>

      <DialogActions>
        <Typography variant="body2" sx={{ flex: 1 }}>
          {previewResult.changes.length} trips will be modified
        </Typography>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={handleApply}>
          Apply Changes
        </Button>
      </DialogActions>
    </Dialog>
  );
};
```

---

## 💡 Tips Adicionales

### 1. **Formato de Hora Personalizado**

```typescript
const formatTime = (time: string | null) => {
  if (!time) return null;

  // Si viene como "HH:MM:SS", convertir a "HH:MM"
  if (time.includes(':')) {
    const [hours, minutes] = time.split(':');
    return `${hours}:${minutes}`;
  }

  return time;
};

// Uso:
<Typography>{formatTime(trip.pick_up_time)}</Typography>
```

### 2. **Mostrar Diferencia de Tiempo**

```typescript
const getTimeDifference = (time1: string, time2: string): number => {
  const [h1, m1] = time1.split(':').map(Number);
  const [h2, m2] = time2.split(':').map(Number);

  const minutes1 = h1 * 60 + m1;
  const minutes2 = h2 * 60 + m2;

  return Math.abs(minutes2 - minutes1);
};

// Uso:
const gap = getTimeDifference(
  exclusion.trips_info[0].pick_up_time,
  exclusion.trips_info[1].pick_up_time
);

<Typography>Gap: {gap} minutes</Typography>
```

### 3. **Highlight si fue modificado**

```tsx
{trip.pick_up_time && (
  <div className={`trip-time ${trip.original_pick_up_time ? 'modified' : ''}`}>
    <AccessTimeIcon />
    <Typography>{trip.pick_up_time}</Typography>

    {trip.original_pick_up_time && (
      <>
        <ArrowForwardIcon fontSize="small" />
        <Typography className="original">
          {trip.original_pick_up_time}
        </Typography>
      </>
    )}
  </div>
)}
```

---

## ✅ Resumen de Cambios

### Backend (Ya implementado):
- ✅ Agregado campo `pick_up_time` a `TripExclusionInfo`
- ✅ Agregado campo `original_pick_up_time` a `TripExclusionInfo`
- ✅ Servicio actualizado para incluir estos campos automáticamente

### Frontend (Por hacer):
1. **Actualizar tipo TypeScript** `TripExclusionInfo` con los 2 nuevos campos
2. **Agregar componente** `ExclusionItem` (usar el ejemplo de arriba)
3. **Integrar** en el modal de Preview Changes
4. **Agregar estilos** CSS para las horas

---

## 🚀 Código Listo para Copy-Paste

```tsx
// types.ts
interface TripExclusionInfo {
  trip_id: string;
  airline: string;
  flight_number: string | null;
  hotel_name: string;
  pick_up_date: string | null;
  pick_up_time: string | null;              // ✅ NUEVO
  original_pick_up_time: string | null;     // ✅ NUEVO
}

// ExclusionItem.tsx
export const ExclusionItem = ({ exclusion }: { exclusion: FilterExclusion }) => {
  return (
    <Box
      sx={{
        border: '1px solid',
        borderColor: 'warning.main',
        borderRadius: 2,
        p: 2,
        mb: 1.5,
        bgcolor: 'warning.lighter'
      }}
    >
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
        <WarningIcon color="warning" />
        <Typography variant="subtitle2" fontWeight="bold">
          Expand excluded
        </Typography>
      </Box>

      {/* Trips con HORA */}
      <Box sx={{ display: 'flex', gap: 2, mb: 1.5 }}>
        {exclusion.trips_info.map((trip, idx) => (
          <Box
            key={idx}
            sx={{
              flex: 1,
              bgcolor: 'background.paper',
              borderRadius: 1,
              p: 1.5,
              boxShadow: 1
            }}
          >
            <Typography variant="body2" fontWeight="bold">
              {trip.airline} {trip.flight_number}
            </Typography>

            <Typography variant="body2" color="text.secondary">
              {trip.hotel_name}
            </Typography>

            {/* ✅ HORA */}
            {trip.pick_up_time && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 1 }}>
                <AccessTimeIcon fontSize="small" color="primary" />
                <Typography variant="body2">
                  {trip.pick_up_time}
                </Typography>
                {trip.original_pick_up_time && (
                  <Typography
                    variant="caption"
                    sx={{ textDecoration: 'line-through', ml: 1 }}
                  >
                    {trip.original_pick_up_time}
                  </Typography>
                )}
              </Box>
            )}

            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.5 }}>
              <CalendarIcon fontSize="small" />
              <Typography variant="caption" color="text.secondary">
                {trip.pick_up_date}
              </Typography>
            </Box>
          </Box>
        ))}
      </Box>

      {/* Razón */}
      <Alert severity="warning" sx={{ mb: 1 }}>
        {exclusion.reason}
      </Alert>

      {/* Gap */}
      <Typography variant="caption">
        Gap: <strong>{exclusion.gap_before}</strong> → <strong>{exclusion.gap_after}</strong> min
      </Typography>
    </Box>
  );
};
```

---

**Última actualización:** 2026-01-19
**Backend:** ✅ Implementado con campos `pick_up_time` y `original_pick_up_time`
