# 🎯 Integración Frontend: Endpoint de Elegibilidad

**Para:** Frontend Developer
**Fecha:** 2026-01-20
**Status:** ✅ Endpoint deployed y listo para usar

---

## TL;DR

Nuevo endpoint para diagnosticar por qué `/filters/preview` devuelve 0 trips:

```
GET /v1/locations/{id}/airlines/{airline}/trips/filters/eligibility
```

**Úsalo para mostrar mensajes informativos cuando no hay trips elegibles.**

---

## 🚀 Quick Start

### 1. Llamar el endpoint

```typescript
const response = await fetch(
  `/api/v1/locations/${locationId}/airlines/${airline}/trips/filters/eligibility?pick_up_date_from=2025-12-01&pick_up_date_to=2025-12-31`,
  {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  }
);

const data = await response.json();
```

### 2. Respuesta típica

```json
{
  "total_trips": 674,
  "eligible_trips": 0,
  "by_trip_type": {
    "inbound": 337,
    "ground": 337,
    "outbound": 0
  },
  "by_status": {
    "scheduled": 674
  },
  "reason": "No trips with trip_type='outbound' found. All 674 trips are type: inbound, ground"
}
```

### 3. Mostrar al usuario

```tsx
{eligible_trips === 0 && (
  <Alert variant="info">
    <AlertTitle>No hay trips elegibles</AlertTitle>
    <AlertDescription>
      <p>{data.reason}</p>
      <p className="text-sm mt-2">
        Trips encontrados: {data.total_trips}<br/>
        Trips elegibles: {data.eligible_trips}
      </p>
    </AlertDescription>
  </Alert>
)}
```

---

## 🎨 React Query Hook (Recomendado)

```typescript
// hooks/use-filter-eligibility.ts
import { useQuery } from '@tanstack/react-query';

interface FilterEligibilityResponse {
  total_trips: number;
  eligible_trips: number;
  by_trip_type: Record<string, number>;
  by_status: Record<string, number>;
  eligible_breakdown: {
    outbound_scheduled_no_filter: number;
    outbound_scheduled_with_filter: number;
    outbound_other_status: number;
  };
  reason: string | null;
}

export const useFilterEligibility = (
  locationId: string,
  airline: string,
  dateFrom?: string,
  dateTo?: string
) => {
  return useQuery({
    queryKey: ['filter-eligibility', locationId, airline, dateFrom, dateTo],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (dateFrom) params.set('pick_up_date_from', dateFrom);
      if (dateTo) params.set('pick_up_date_to', dateTo);

      const response = await fetch(
        `/api/v1/locations/${locationId}/airlines/${airline}/trips/filters/eligibility?${params}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error('Failed to check eligibility');
      }

      return response.json() as Promise<FilterEligibilityResponse>;
    },
    enabled: !!locationId && !!airline,
  });
};
```

---

## 📱 Componente UI Completo

```tsx
// components/filter-eligibility-alert.tsx
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';
import { InfoIcon } from 'lucide-react';
import { useFilterEligibility } from '@/hooks/use-filter-eligibility';

interface FilterEligibilityAlertProps {
  locationId: string;
  airline: string;
  dateFrom?: string;
  dateTo?: string;
}

export const FilterEligibilityAlert = ({
  locationId,
  airline,
  dateFrom,
  dateTo,
}: FilterEligibilityAlertProps) => {
  const { data, isLoading } = useFilterEligibility(
    locationId,
    airline,
    dateFrom,
    dateTo
  );

  if (isLoading) return null;
  if (!data || data.eligible_trips > 0) return null;

  return (
    <Alert variant="info" className="mb-4">
      <InfoIcon className="h-4 w-4" />
      <AlertTitle>No hay trips elegibles para Ground Filters</AlertTitle>
      <AlertDescription>
        <div className="mt-2 space-y-2">
          {/* Summary */}
          <p className="text-sm">
            <strong>Trips encontrados:</strong> {data.total_trips}
          </p>
          <p className="text-sm">
            <strong>Trips elegibles:</strong> {data.eligible_trips}
          </p>

          {/* Reason */}
          {data.reason && (
            <p className="text-sm text-amber-600 dark:text-amber-400 mt-2">
              {data.reason}
            </p>
          )}

          {/* Breakdown by trip_type */}
          <div className="mt-3">
            <p className="text-sm font-semibold mb-1">Desglose por tipo:</p>
            <ul className="text-sm space-y-1">
              {Object.entries(data.by_trip_type).map(([type, count]) => (
                <li key={type}>
                  {type === 'outbound' ? '✅' : '❌'} {type}: {count}
                </li>
              ))}
            </ul>
          </div>

          {/* Criteria explanation */}
          <div className="mt-3 p-3 bg-muted rounded-md">
            <p className="text-xs font-semibold mb-2">
              Ground Filters solo aplican a trips con:
            </p>
            <ul className="text-xs space-y-1">
              <li>✓ Tipo: <strong>OUTBOUND</strong> (Hotel → Airport)</li>
              <li>✓ Status: <strong>SCHEDULED</strong></li>
              <li>✓ Sin filtros aplicados previamente</li>
            </ul>
          </div>

          {/* Action buttons if applicable */}
          {data.eligible_breakdown.outbound_scheduled_with_filter > 0 && (
            <div className="mt-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  // Navigate to revert filters or call revert API
                }}
              >
                Revertir Filtros Existentes
              </Button>
            </div>
          )}
        </div>
      </AlertDescription>
    </Alert>
  );
};
```

---

## 🎭 Uso en el Drawer de Ground Filters

```tsx
// components/ground-filters-drawer.tsx
import { FilterEligibilityAlert } from './filter-eligibility-alert';

export const GroundFiltersDrawer = () => {
  const { locationId, airline, dateFrom, dateTo } = useParams();
  const { data: preview } = useFilterPreview();
  const { data: eligibility } = useFilterEligibility(
    locationId,
    airline,
    dateFrom,
    dateTo
  );

  return (
    <Drawer>
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle>Ground Filters - {airline}</DrawerTitle>
          <DrawerDescription>
            Optimiza tiempos de pickup para trips OUTBOUND (Hotel → Airport)
          </DrawerDescription>
        </DrawerHeader>

        {/* Show eligibility alert when no eligible trips */}
        {eligibility?.eligible_trips === 0 && (
          <FilterEligibilityAlert
            locationId={locationId}
            airline={airline}
            dateFrom={dateFrom}
            dateTo={dateTo}
          />
        )}

        {/* Only show form if there are eligible trips */}
        {eligibility?.eligible_trips > 0 && (
          <>
            <FilterConfigurationForm />
            <FilterPreviewResults />
          </>
        )}
      </DrawerContent>
    </Drawer>
  );
};
```

---

## 📊 Escenarios y Mensajes

### Escenario 1: No hay trips outbound

```json
{
  "eligible_trips": 0,
  "by_trip_type": { "ground": 337, "inbound": 337, "outbound": 0 },
  "reason": "No trips with trip_type='outbound' found. All 674 trips are type: inbound, ground"
}
```

**Mensaje:**
```
⚠️ No hay trips elegibles

Todos los 674 trips encontrados son de tipo "ground" o "inbound".

Ground Filters solo funcionan con trips tipo "outbound" (Hotel → Airport).
```

### Escenario 2: Todos los outbound ya tienen filtros

```json
{
  "eligible_trips": 0,
  "eligible_breakdown": {
    "outbound_scheduled_with_filter": 500
  },
  "reason": "All 500 outbound trips already have filters applied. Use /revert to clear filters first."
}
```

**Mensaje:**
```
⚠️ No hay trips elegibles

Los 500 trips outbound ya tienen filtros aplicados.

[Botón: Revertir Filtros]
```

### Escenario 3: Trips outbound no están scheduled

```json
{
  "eligible_trips": 0,
  "by_status": { "completed": 150, "cancelled": 50 },
  "reason": "All 200 outbound trips have status other than 'scheduled'"
}
```

**Mensaje:**
```
⚠️ No hay trips elegibles

Los trips outbound encontrados no están en status "scheduled".

Status actual:
• Completed: 150
• Cancelled: 50
```

---

## ⚡ Optimización: Llamar Proactivamente

En lugar de esperar a que el usuario haga clic en "Preview", llama el endpoint al abrir el drawer:

```tsx
export const GroundFiltersDrawer = ({ open }) => {
  const { data: eligibility } = useFilterEligibility(
    locationId,
    airline,
    dateFrom,
    dateTo
  );

  // Show warning immediately if no eligible trips
  useEffect(() => {
    if (open && eligibility?.eligible_trips === 0) {
      toast.warning('No hay trips elegibles para aplicar filtros');
    }
  }, [open, eligibility?.eligible_trips]);

  return (
    <Drawer open={open}>
      {/* ... */}
    </Drawer>
  );
};
```

---

## 🧪 Testing

### Manual Test

1. Abrir el drawer de Ground Filters
2. Verificar que el alert aparece si `eligible_trips === 0`
3. Verificar que muestra la razón específica
4. Verificar que muestra el desglose de trip_types

### Postman/Thunder Client

```bash
GET http://localhost:8000/api/v1/locations/{location_id}/airlines/WN/trips/filters/eligibility?pick_up_date_from=2025-12-01&pick_up_date_to=2025-12-31
Authorization: Bearer {token}
```

### cURL

```bash
curl "http://localhost:8000/api/v1/locations/{id}/airlines/WN/trips/filters/eligibility?pick_up_date_from=2025-12-01&pick_up_date_to=2025-12-31" \
  -H "Authorization: Bearer {token}"
```

---

## ❓ FAQ

### ¿Cuándo debo llamar este endpoint?

**R:** Al abrir el drawer de Ground Filters, antes de que el usuario configure los filtros. Esto previene frustración.

### ¿Debo llamarlo cada vez que cambian las fechas?

**R:** Sí, el hook de React Query se encargará de cachear y refrescar automáticamente.

### ¿Qué hago si `eligible_trips > 0` pero el preview sigue devolviendo 0?

**R:** Esto puede pasar si los filtros configurados excluyen todos los trips (ej: hotel_names no coincide). En ese caso, el mensaje debería ser diferente ("Los filtros excluyen todos los trips").

### ¿El endpoint es rápido?

**R:** Sí, solo cuenta registros en memoria. No realiza operaciones pesadas.

---

## 📎 Documentación Completa

- **Documentación del endpoint:** [docs/GROUND_FILTERS_ELIGIBILITY_ENDPOINT.md](docs/GROUND_FILTERS_ELIGIBILITY_ENDPOINT.md)
- **Análisis técnico:** [docs/FILTER_PREVIEW_QUERY_ANALYSIS.md](docs/FILTER_PREVIEW_QUERY_ANALYSIS.md)
- **Respuestas a preguntas:** [docs/RESPUESTAS_FRONTEND_PREVIEW_ZERO.md](docs/RESPUESTAS_FRONTEND_PREVIEW_ZERO.md)
- **Solución completa:** [docs/SOLUCION_PREVIEW_ZERO_TRIPS.md](docs/SOLUCION_PREVIEW_ZERO_TRIPS.md)

---

## ✅ Checklist de Integración

- [ ] Agregar hook `useFilterEligibility`
- [ ] Crear componente `FilterEligibilityAlert`
- [ ] Integrar en el drawer de Ground Filters
- [ ] Agregar test manual
- [ ] Actualizar documentación del frontend
- [ ] Testing E2E

---

**Última actualización:** 2026-01-20
**Status:** ✅ Backend deployed, listo para integración frontend
