# 🚫 Guía: Mostrar Trips Excluidos en el Frontend

## 📋 Tabla de Contenidos

1. [Estructura de Datos](#estructura-de-datos)
2. [Cómo Mostrar Exclusiones](#cómo-mostrar-exclusiones)
3. [Ejemplos de UI](#ejemplos-de-ui)
4. [Casos de Uso](#casos-de-uso)

---

## 🏗️ Estructura de Datos

### Nuevo Modelo: `TripExclusionInfo`

```typescript
interface TripExclusionInfo {
  trip_id: string;                    // UUID
  airline: string;                    // "WN"
  flight_number: string | null;       // "1326"
  hotel_name: string;                 // "The Galt House"
  pick_up_date: string | null;        // "2024-12-31"
  pick_up_time: string | null;        // "13:25" - Current time (may be modified)
  original_pick_up_time: string | null;  // "13:45" - Original time before filters (if modified)
}
```

### Modelo Actualizado: `FilterExclusion`

```typescript
interface FilterExclusion {
  operation: string;        // "expand(uuid1, uuid2)"
  trip_ids: string[];       // [uuid1, uuid2]
  reason: string;           // "Collision: gap with next trip would enter Combine range (15 min)"
  gap_before: number;       // 25 (minutos)
  gap_after: number;        // 15 (minutos)
  trips_info: TripExclusionInfo[];  // ✅ NUEVO - Información detallada de los trips
}
```

---

## 📊 Response del Backend

### Endpoint: `POST /filters/preview`

```typescript
interface FilterPreviewResult {
  location_id: string;
  airline: string;
  changes: TripChange[];
  exclusions: FilterExclusion[];  // ← Aquí están las exclusiones
  summary: {
    reduce: number;
    combine: number;
    expand: number;
    excluded: number;
  };
  total_trips_evaluated: number;
  eligible_trips: number;
}
```

### Ejemplo de Response:

```json
{
  "exclusions": [
    {
      "operation": "expand(348f4d93-1ff1-4f1b-a848-6749535bc951, c3e4a695-9f39-44ca-bfca-b756e024a3d1)",
      "trip_ids": [
        "348f4d93-1ff1-4f1b-a848-6749535bc951",
        "c3e4a695-9f39-44ca-bfca-b756e024a3d1"
      ],
      "reason": "Collision: gap with next trip would enter Combine range (15 min)",
      "gap_before": 25,
      "gap_after": 15,
      "trips_info": [
        {
          "trip_id": "348f4d93-1ff1-4f1b-a848-6749535bc951",
          "airline": "WN",
          "flight_number": "1326",
          "hotel_name": "The Galt House",
          "pick_up_date": "2024-12-31",
          "pick_up_time": "13:25",
          "original_pick_up_time": null
        },
        {
          "trip_id": "c3e4a695-9f39-44ca-bfca-b756e024a3d1",
          "airline": "WN",
          "flight_number": "1327",
          "hotel_name": "The Galt House",
          "pick_up_date": "2024-12-31",
          "pick_up_time": "13:50",
          "original_pick_up_time": null
        }
      ]
    }
  ]
}
```

---

## 🎨 Cómo Mostrar Exclusiones

### Opción 1: Lista Simple

```tsx
const ExclusionsList = ({ exclusions }: { exclusions: FilterExclusion[] }) => {
  return (
    <div className="exclusions-list">
      <h3>⚠️ Operations Excluded ({exclusions.length})</h3>

      {exclusions.map((exclusion, idx) => (
        <div key={idx} className="exclusion-item">
          {/* Mostrar trips involucrados */}
          <div className="trips-involved">
            {exclusion.trips_info.map((trip, tripIdx) => (
              <div key={tripIdx} className="trip-badge">
                <span className="airline">{trip.airline}</span>
                <span className="flight">{trip.flight_number}</span>
                <span className="hotel">{trip.hotel_name}</span>
                {trip.pick_up_time && (
                  <span className="time">
                    ⏰ {trip.pick_up_time}
                    {trip.original_pick_up_time && (
                      <span className="original-time" title="Original time">
                        (was {trip.original_pick_up_time})
                      </span>
                    )}
                  </span>
                )}
              </div>
            ))}
          </div>

          {/* Razón de exclusión */}
          <div className="exclusion-reason">
            {exclusion.reason}
          </div>

          {/* Gap info */}
          <div className="gap-info">
            <span>Gap before: {exclusion.gap_before} min</span>
            <span>Gap after: {exclusion.gap_after} min</span>
          </div>
        </div>
      ))}
    </div>
  );
};
```

---

### Opción 2: Card con Detalles Expandibles

```tsx
const ExclusionCard = ({ exclusion }: { exclusion: FilterExclusion }) => {
  const [expanded, setExpanded] = useState(false);

  return (
    <Card className="exclusion-card">
      <CardHeader onClick={() => setExpanded(!expanded)}>
        <div className="trips-summary">
          {exclusion.trips_info.map((trip, idx) => (
            <Chip
              key={idx}
              label={`${trip.airline} ${trip.flight_number}`}
              icon={<FlightIcon />}
            />
          ))}
        </div>
        <IconButton>
          {expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
        </IconButton>
      </CardHeader>

      <Collapse in={expanded}>
        <CardContent>
          {/* Detalles completos */}
          <div className="exclusion-details">
            <Typography variant="body2" color="text.secondary">
              {exclusion.reason}
            </Typography>

            <div className="trips-details">
              {exclusion.trips_info.map((trip, idx) => (
                <div key={idx} className="trip-detail">
                  <Typography variant="h6">
                    Trip {idx + 1}
                  </Typography>
                  <Table size="small">
                    <TableBody>
                      <TableRow>
                        <TableCell>Airline</TableCell>
                        <TableCell>{trip.airline}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>Flight</TableCell>
                        <TableCell>{trip.flight_number}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>Hotel</TableCell>
                        <TableCell>{trip.hotel_name}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>Date</TableCell>
                        <TableCell>{trip.pick_up_date}</TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </div>
              ))}
            </div>

            <div className="gap-visualization">
              <Typography variant="caption">
                Gap before: {exclusion.gap_before} min →
                Gap after: {exclusion.gap_after} min
              </Typography>
            </div>
          </div>
        </CardContent>
      </Collapse>
    </Card>
  );
};
```

---

### Opción 3: Modal de Detalles (como en la imagen)

```tsx
const ExclusionsModal = ({
  exclusions,
  open,
  onClose
}: {
  exclusions: FilterExclusion[];
  open: boolean;
  onClose: () => void;
}) => {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        ⚠️ {exclusions.length} operations excluded
      </DialogTitle>

      <DialogContent>
        {exclusions.map((exclusion, idx) => (
          <div key={idx} className="exclusion-item">
            {/* Header con operation */}
            <div className="exclusion-header">
              <Typography variant="caption" color="text.secondary">
                {exclusion.operation}
              </Typography>
            </div>

            {/* Trips involucrados */}
            <div className="trips-row">
              {exclusion.trips_info.map((trip, tripIdx) => (
                <div key={tripIdx} className="trip-info">
                  <Typography variant="h6">
                    {trip.airline} {trip.flight_number}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {trip.hotel_name}
                  </Typography>
                </div>
              ))}
            </div>

            {/* Razón de exclusión */}
            <Alert severity="warning" sx={{ mt: 1 }}>
              {exclusion.reason}
            </Alert>

            {/* Gap info */}
            <div className="gap-info">
              <Chip
                label={`Gap before: ${exclusion.gap_before} min`}
                size="small"
              />
              <Chip
                label={`Gap after: ${exclusion.gap_after} min`}
                size="small"
              />
            </div>

            {/* Trip IDs (opcional, para debugging) */}
            {exclusion.trip_ids.map((tripId, idIdx) => (
              <Chip
                key={idIdx}
                label={tripId.substring(0, 8)}
                size="small"
                variant="outlined"
              />
            ))}
          </div>
        ))}
      </DialogContent>

      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
};
```

---

## 🎯 Casos de Uso

### Caso 1: Mostrar Exclusiones en Preview

```tsx
const FilterPreview = () => {
  const [previewResult, setPreviewResult] = useState<FilterPreviewResult | null>(null);

  const handlePreview = async () => {
    const result = await previewFilters(config);
    setPreviewResult(result);
  };

  return (
    <div>
      <Button onClick={handlePreview}>Preview Changes</Button>

      {previewResult && (
        <div className="preview-results">
          {/* Mostrar cambios */}
          <div className="changes">
            <Typography variant="h6">
              Changes: {previewResult.changes.length}
            </Typography>
            {/* ... render changes ... */}
          </div>

          {/* ✅ Mostrar exclusiones */}
          {previewResult.exclusions.length > 0 && (
            <Alert severity="warning" sx={{ mt: 2 }}>
              <AlertTitle>
                ⚠️ {previewResult.exclusions.length} operations excluded
              </AlertTitle>
              <ExclusionsList exclusions={previewResult.exclusions} />
            </Alert>
          )}
        </div>
      )}
    </div>
  );
};
```

---

### Caso 2: Badge con Contador de Exclusiones

```tsx
const PreviewButton = ({ config }: { config: FilterConfig }) => {
  const [exclusionsCount, setExclusionsCount] = useState(0);

  const handlePreview = async () => {
    const result = await previewFilters(config);
    setExclusionsCount(result.exclusions.length);
  };

  return (
    <Badge badgeContent={exclusionsCount} color="warning">
      <Button onClick={handlePreview}>
        Preview Changes
      </Button>
    </Badge>
  );
};
```

---

### Caso 3: Agrupar Exclusiones por Fecha

```tsx
const ExclusionsByDate = ({ exclusions }: { exclusions: FilterExclusion[] }) => {
  // Agrupar por fecha
  const groupedByDate = exclusions.reduce((acc, exclusion) => {
    const date = exclusion.trips_info[0]?.pick_up_date || 'Unknown';
    if (!acc[date]) {
      acc[date] = [];
    }
    acc[date].push(exclusion);
    return acc;
  }, {} as Record<string, FilterExclusion[]>);

  return (
    <div className="exclusions-by-date">
      {Object.entries(groupedByDate).map(([date, exclusions]) => (
        <div key={date} className="date-group">
          <Typography variant="h6">
            📅 {new Date(date).toLocaleDateString()}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {exclusions.length} operations excluded
          </Typography>

          <div className="exclusions-list">
            {exclusions.map((exclusion, idx) => (
              <ExclusionCard key={idx} exclusion={exclusion} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};
```

---

## 📱 Ejemplo de UI (como en la imagen)

Para replicar la UI de la imagen que compartiste:

```tsx
const PreviewChangesModal = ({
  previewResult,
  open,
  onClose,
  onApply
}: PreviewChangesModalProps) => {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        Preview Changes
        <Typography variant="caption" color="text.secondary">
          Review changes before applying
        </Typography>
      </DialogTitle>

      <DialogContent>
        {/* Fecha y airline */}
        <div className="preview-header">
          <CalendarIcon />
          <Typography variant="h6">Wed, Dec 31</Typography>
          <Typography variant="body2">12 changes</Typography>
        </div>

        {/* Cambios */}
        <div className="changes-list">
          {previewResult.changes.map((change, idx) => (
            <div key={idx} className="change-item">
              <Typography>
                {change.airline} {change.flight_number} {change.hotel_name}
              </Typography>
              <Typography>
                {change.original_time} → {change.new_time}
              </Typography>
            </div>
          ))}
        </div>

        {/* ✅ Exclusiones */}
        {previewResult.exclusions.length > 0 && (
          <div className="exclusions-section">
            <Alert severity="warning" icon={<WarningIcon />}>
              <AlertTitle>
                {previewResult.exclusions.length} operations excluded
              </AlertTitle>
            </Alert>

            <Accordion>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography>View excluded operations</Typography>
              </AccordionSummary>
              <AccordionDetails>
                {previewResult.exclusions.map((exclusion, idx) => (
                  <div key={idx} className="exclusion-detail">
                    {/* Operation */}
                    <Typography variant="caption" color="text.secondary">
                      {exclusion.operation}
                    </Typography>

                    {/* Trips */}
                    <div className="trips-involved">
                      {exclusion.trips_info.map((trip, tripIdx) => (
                        <div key={tripIdx} className="trip-info">
                          <Typography variant="h6">
                            {trip.airline} {trip.flight_number} {trip.hotel_name}
                          </Typography>
                        </div>
                      ))}
                    </div>

                    {/* Razón */}
                    <Alert severity="warning">
                      {exclusion.reason}
                    </Alert>

                    {/* Gaps */}
                    <div className="gap-info">
                      <Typography variant="caption">
                        Gap before: {exclusion.gap_before} min
                      </Typography>
                      <Typography variant="caption">
                        Gap after: {exclusion.gap_after} min
                      </Typography>
                    </div>

                    {/* Trip IDs */}
                    <div className="trip-ids">
                      <Typography variant="caption">Trip IDs:</Typography>
                      {exclusion.trip_ids.map((id, idIdx) => (
                        <Chip
                          key={idIdx}
                          label={id.substring(0, 8) + '...'}
                          size="small"
                        />
                      ))}
                    </div>
                  </div>
                ))}
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
        <Button onClick={onApply} variant="contained">
          Apply Changes
        </Button>
      </DialogActions>
    </Dialog>
  );
};
```

---

## 🎨 CSS Sugerido

```css
.exclusion-item {
  border: 1px solid #ff9800;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
  background-color: #fff3e0;
}

.trips-involved {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.trip-badge {
  display: flex;
  gap: 4px;
  align-items: center;
  padding: 8px 12px;
  background-color: white;
  border-radius: 4px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.trip-badge .airline {
  font-weight: bold;
  color: #1976d2;
}

.trip-badge .flight {
  font-weight: 500;
}

.trip-badge .hotel {
  color: #666;
  font-size: 0.9em;
}

.exclusion-reason {
  color: #d32f2f;
  font-size: 0.95em;
  margin-bottom: 8px;
}

.gap-info {
  display: flex;
  gap: 12px;
  font-size: 0.85em;
  color: #666;
}
```

---

## 📊 Summary del Cambio

### Antes (sin `trips_info`):

```json
{
  "operation": "expand(...)",
  "trip_ids": ["uuid1", "uuid2"],
  "reason": "Collision...",
  "gap_before": 25,
  "gap_after": 15
}
```

**Frontend tenía que:**
- Buscar los trips en el array local usando los UUIDs
- Si el trip no estaba cargado, no podía mostrar los detalles

### Después (con `trips_info`):

```json
{
  "operation": "expand(...)",
  "trip_ids": ["uuid1", "uuid2"],
  "reason": "Collision...",
  "gap_before": 25,
  "gap_after": 15,
  "trips_info": [
    {
      "trip_id": "uuid1",
      "airline": "WN",
      "flight_number": "1326",
      "hotel_name": "The Galt House",
      "pick_up_date": "2024-12-31"
    },
    {
      "trip_id": "uuid2",
      "airline": "WN",
      "flight_number": "1327",
      "hotel_name": "The Galt House",
      "pick_up_date": "2024-12-31"
    }
  ]
}
```

**Frontend ahora:**
- ✅ Tiene todos los datos directamente
- ✅ No necesita buscar en arrays locales
- ✅ Funciona incluso si los trips no están cargados en memoria

---

## ✅ Checklist de Implementación

- [x] Backend: Agregar modelo `TripExclusionInfo`
- [x] Backend: Actualizar modelo `FilterExclusion` con campo `trips_info`
- [x] Backend: Modificar `_record_exclusion` para incluir trip details
- [x] Backend: Actualizar llamadas a `_record_exclusion`
- [ ] Frontend: Actualizar tipo TypeScript `FilterExclusion`
- [ ] Frontend: Agregar tipo TypeScript `TripExclusionInfo`
- [ ] Frontend: Crear componente `ExclusionsList`
- [ ] Frontend: Integrar componente en modal de preview
- [ ] Frontend: Agregar estilos CSS
- [ ] Testing: Verificar que los datos se muestran correctamente

---

## 🚀 Próximos Pasos

1. **Actualizar tipos TypeScript** en el frontend
2. **Crear componente de visualización** (usar uno de los ejemplos)
3. **Integrar en el flujo de preview**
4. **Agregar estilos** según tu design system
5. **Testing** con datos reales

---

**Última actualización:** 2026-01-19
**Backend version:** Con soporte para `trips_info` en exclusiones
