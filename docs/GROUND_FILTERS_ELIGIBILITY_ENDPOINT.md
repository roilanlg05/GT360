# 🔍 Ground Filters Eligibility Diagnostic Endpoint

**Fecha:** 2026-01-20
**Status:** ✅ Implementado
**Endpoint:** `GET /v1/locations/{location_id}/airlines/{airline}/trips/filters/eligibility`

---

## 🎯 Propósito

Este endpoint resuelve la confusión cuando `/filters/preview` devuelve 0 trips elegibles aunque la tabla muestra cientos de trips.

**Problema común:**
- Frontend llama `/trips` → 674 trips
- Frontend llama `/filters/preview` → 0 trips elegibles
- Usuario confundido: "¿Por qué no funciona?"

**Solución:**
Este endpoint explica **exactamente por qué** los trips NO son elegibles.

---

## ⚠️ Aclaración Importante: "Ground Filters" vs Trips "ground"

### ❌ Confusión Común

**"Ground Filters"** ≠ Filtros para trips tipo `ground`

### ✅ Clarificación

| Término | Significado Real |
|---------|------------------|
| **"Ground Filters"** | Filtros para optimizar **transporte terrestre** (ground transportation) de trips **OUTBOUND** al aeropuerto |
| **Trip tipo `ground`** | Trips que van de **Hotel → Hotel** (NO van al aeropuerto) |

**Ground Filters** fueron diseñados **exclusivamente** para trips tipo **OUTBOUND** (Hotel → Airport).

**NO aplican** a trips tipo `ground` (Hotel → Hotel) ni `inbound` (Airport → Hotel).

---

## 📊 Criterios de Elegibilidad

Ground Filters **SOLO** aplican a trips que cumplan **TODOS** estos criterios:

```
✅ trip_type = 'outbound'        (Hotel → Airport)
✅ status = 'scheduled'           (No completados, no cancelados)
✅ filter_applied IS NULL         (Sin filtros previos)
✅ location_id = {el solicitado}
✅ airline = {el solicitado}
✅ pick_up_date en rango de fechas
```

**Trips excluidos:**
```
❌ trip_type = 'inbound'          (Airport → Hotel)
❌ trip_type = 'ground'           (Hotel → Hotel)
❌ status = 'completed'
❌ status = 'cancelled'
❌ status = 'en_route'
❌ filter_applied = 'reduce'      (Ya tiene filtros)
❌ filter_applied = 'combine'     (Ya tiene filtros)
❌ filter_applied = 'expand'      (Ya tiene filtros)
```

---

## 🔌 Uso del Endpoint

### Request

```typescript
GET /v1/locations/{location_id}/airlines/{airline}/trips/filters/eligibility?pick_up_date_from=2025-12-01&pick_up_date_to=2025-12-31

Headers:
Authorization: Bearer {token}
```

### Query Parameters

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `location_id` | UUID | ✅ | ID de la location |
| `airline` | string | ✅ | Código de aerolínea (ej: "WN") |
| `pick_up_date_from` | string | ❌ | Fecha inicio (YYYY-MM-DD) |
| `pick_up_date_to` | string | ❌ | Fecha fin (YYYY-MM-DD) |

### Response

```typescript
interface FilterEligibilityResponse {
  total_trips: number;
  eligible_trips: number;
  by_trip_type: {
    [trip_type: string]: number;
  };
  by_status: {
    [status: string]: number;
  };
  eligible_breakdown: {
    outbound_scheduled_no_filter: number;
    outbound_scheduled_with_filter: number;
    outbound_other_status: number;
  };
  reason: string | null;
  criteria: {
    info: string;
    required: {
      trip_type: string;
      status: string;
      filter_applied: null;
    };
    excluded: {
      trip_types: string[];
      statuses: string[];
      with_filters: string[];
    };
  };
}
```

---

## 📋 Ejemplos de Respuesta

### Ejemplo 1: Ningún Trip Outbound

**Escenario:** Todos los trips son tipo `inbound` o `ground`

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
  "eligible_breakdown": {
    "outbound_scheduled_no_filter": 0,
    "outbound_scheduled_with_filter": 0,
    "outbound_other_status": 0
  },
  "reason": "No trips with trip_type='outbound' found. All 674 trips are type: inbound, ground",
  "criteria": {
    "info": "Ground Filters only apply to trips matching ALL criteria below",
    "required": {
      "trip_type": "outbound",
      "status": "scheduled",
      "filter_applied": null
    },
    "excluded": {
      "trip_types": ["inbound", "ground"],
      "statuses": ["completed", "cancelled", "en_route"],
      "with_filters": ["reduce", "combine", "expand"]
    }
  }
}
```

### Ejemplo 2: Todos los Outbound Ya Tienen Filtros

**Escenario:** Hay trips outbound pero todos ya tienen filtros aplicados

```json
{
  "total_trips": 500,
  "eligible_trips": 0,
  "by_trip_type": {
    "outbound": 500
  },
  "by_status": {
    "scheduled": 500
  },
  "eligible_breakdown": {
    "outbound_scheduled_no_filter": 0,
    "outbound_scheduled_with_filter": 500,
    "outbound_other_status": 0
  },
  "reason": "All 500 outbound trips already have filters applied. Use /revert to clear filters first.",
  "criteria": {
    "info": "Ground Filters only apply to trips matching ALL criteria below",
    "required": {
      "trip_type": "outbound",
      "status": "scheduled",
      "filter_applied": null
    },
    "excluded": {
      "trip_types": ["inbound", "ground"],
      "statuses": ["completed", "cancelled", "en_route"],
      "with_filters": ["reduce", "combine", "expand"]
    }
  }
}
```

### Ejemplo 3: Trips Outbound Disponibles

**Escenario:** Hay trips outbound + scheduled + sin filtros

```json
{
  "total_trips": 800,
  "eligible_trips": 250,
  "by_trip_type": {
    "outbound": 400,
    "inbound": 400
  },
  "by_status": {
    "scheduled": 800
  },
  "eligible_breakdown": {
    "outbound_scheduled_no_filter": 250,
    "outbound_scheduled_with_filter": 150,
    "outbound_other_status": 0
  },
  "reason": null,
  "criteria": {
    "info": "Ground Filters only apply to trips matching ALL criteria below",
    "required": {
      "trip_type": "outbound",
      "status": "scheduled",
      "filter_applied": null
    },
    "excluded": {
      "trip_types": ["inbound", "ground"],
      "statuses": ["completed", "cancelled", "en_route"],
      "with_filters": ["reduce", "combine", "expand"]
    }
  }
}
```

---

## 🎨 Integración en el Frontend

### TypeScript Hook

```typescript
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
  criteria: {
    info: string;
    required: {
      trip_type: string;
      status: string;
      filter_applied: null;
    };
    excluded: {
      trip_types: string[];
      statuses: string[];
      with_filters: string[];
    };
  };
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

### Componente de Diagnóstico

```tsx
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';
import { InfoIcon } from 'lucide-react';

export const FilterEligibilityAlert = () => {
  const { locationId, airline, dateFrom, dateTo } = useFilterContext();
  const { data: eligibility, isLoading } = useFilterEligibility(
    locationId,
    airline,
    dateFrom,
    dateTo
  );

  if (isLoading) return null;
  if (!eligibility || eligibility.eligible_trips > 0) return null;

  return (
    <Alert variant="info" className="mb-4">
      <InfoIcon className="h-4 w-4" />
      <AlertTitle>No hay trips elegibles para Ground Filters</AlertTitle>
      <AlertDescription>
        <div className="mt-2 space-y-2">
          <p className="text-sm">
            <strong>Trips encontrados:</strong> {eligibility.total_trips}
          </p>
          <p className="text-sm">
            <strong>Trips elegibles:</strong> {eligibility.eligible_trips}
          </p>

          {/* Reason */}
          {eligibility.reason && (
            <p className="text-sm text-amber-600 dark:text-amber-400 mt-2">
              {eligibility.reason}
            </p>
          )}

          {/* Breakdown by trip_type */}
          <div className="mt-3">
            <p className="text-sm font-semibold mb-1">Desglose por tipo:</p>
            <ul className="text-sm space-y-1">
              {Object.entries(eligibility.by_trip_type).map(([type, count]) => (
                <li key={type}>
                  {type === 'outbound' ? '✅' : '❌'} {type}: {count}
                </li>
              ))}
            </ul>
          </div>

          {/* Criteria info */}
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

          {/* Action buttons */}
          {eligibility.eligible_breakdown.outbound_scheduled_with_filter > 0 && (
            <div className="mt-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  // Navigate to revert filters
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

### Uso en el Drawer de Ground Filters

```tsx
import { FilterEligibilityAlert } from './FilterEligibilityAlert';

export const GroundFiltersDrawer = () => {
  const { preview } = useFilterPreview();

  return (
    <Drawer>
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle>Ground Filters - {airline}</DrawerTitle>
          <DrawerDescription>
            Optimiza tiempos de pickup para trips OUTBOUND (Hotel → Airport)
          </DrawerDescription>
        </DrawerHeader>

        {/* Show eligibility alert when preview returns 0 */}
        {preview?.eligible_trips === 0 && <FilterEligibilityAlert />}

        {/* Rest of the drawer content */}
        <FilterConfigurationForm />
        <FilterPreviewResults />
      </DrawerContent>
    </Drawer>
  );
};
```

---

## 🔄 Flujo de Usuario Mejorado

### Antes (Confuso)

```
1. Usuario abre "Ground Filters"
2. Usuario configura filtros
3. Usuario hace clic en "Preview Changes"
4. Backend devuelve: eligible_trips: 0
5. Frontend muestra: "No changes to preview"
6. Usuario confundido: "¿Por qué no funciona?"
```

### Después (Claro)

```
1. Usuario abre "Ground Filters"
2. Frontend llama /eligibility automáticamente
3. Si eligible_trips === 0:
   → Muestra alert con razón específica
   → Muestra desglose de trip_types
   → Explica criterios de elegibilidad
4. Usuario entiende inmediatamente el problema
5. Usuario puede tomar acción:
   - Si todos son "ground" → No puede aplicar filtros (por diseño)
   - Si tienen filtros → Usar "Revert" primero
   - Si están completed → Esperar próximos trips scheduled
```

---

## 🛠️ Casos de Uso

### Caso 1: Debugging Durante Desarrollo

**Frontend Developer:**
```bash
curl "http://localhost:8000/api/v1/locations/{id}/airlines/WN/trips/filters/eligibility?pick_up_date_from=2025-12-01&pick_up_date_to=2025-12-31" \
  -H "Authorization: Bearer {token}"
```

**Backend Developer:**
```python
# En un script de testing
from features.trips.routes.trips_router import check_filter_eligibility

result = await check_filter_eligibility(
    location_id="...",
    airline="WN",
    pick_up_date_from="2025-12-01",
    pick_up_date_to="2025-12-31",
    session=session,
    _role=None
)

print(f"Total: {result['total_trips']}")
print(f"Eligible: {result['eligible_trips']}")
print(f"Reason: {result['reason']}")
```

### Caso 2: Soporte al Usuario

**Usuario reporta:** "Los filtros no funcionan"

**Soporte:**
1. Abre el drawer de Ground Filters
2. Ve el alert de elegibilidad
3. Lee la razón específica
4. Responde al usuario con información precisa

---

## 📎 Archivos Relacionados

1. **Endpoint implementado:** `/home/backend/GT360/features/trips/routes/trips_router.py:1233-1388`
2. **Documentación de análisis:** `/home/backend/GT360/docs/FILTER_PREVIEW_QUERY_ANALYSIS.md`
3. **Respuestas frontend:** `/home/backend/GT360/docs/RESPUESTAS_FRONTEND_PREVIEW_ZERO.md`
4. **Script SQL diagnóstico:** `/home/backend/GT360/diagnose_preview_zero_trips.sql`

---

## ✅ Beneficios

1. ✅ **Transparencia:** Usuario entiende por qué no hay trips elegibles
2. ✅ **Debugging:** Desarrolladores pueden diagnosticar rápidamente
3. ✅ **UX mejorado:** Mensajes claros en lugar de pantallas vacías
4. ✅ **Reduce tickets de soporte:** Usuario ve el problema y la solución
5. ✅ **Educación:** Usuario aprende qué son "Ground Filters" realmente

---

## 🎓 Educación al Usuario

### Mensaje en la UI

```
💡 ¿Qué son "Ground Filters"?

Los "Ground Filters" optimizan los tiempos de recogida (pickup times)
para el TRANSPORTE TERRESTRE de trips tipo OUTBOUND (Hotel → Airport).

NO se aplican a:
• Trips tipo "inbound" (Airport → Hotel)
• Trips tipo "ground" (Hotel → Hotel)

Esto es por diseño, ya que estos tipos de trips tienen
diferentes requerimientos de logística.
```

---

**Última actualización:** 2026-01-20
**Status:** ✅ Endpoint implementado y listo para uso
