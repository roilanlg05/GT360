# 🔄 Guía Completa: Sincronización de Filtros Frontend-Backend

## 📋 Tabla de Contenidos

1. [Estructura de Datos del Backend](#estructura-de-datos-del-backend)
2. [Lógica de Sincronización](#lógica-de-sincronización)
3. [Casos de Uso](#casos-de-uso)
4. [Implementación Paso a Paso](#implementación-paso-a-paso)
5. [Troubleshooting](#troubleshooting)

---

## 🏗️ Estructura de Datos del Backend

### Endpoint: `GET /filters/current`

```typescript
interface FilterCurrentResponse {
  has_active_filters: boolean;
  batch_id: string | null;
  applied_at: string | null;          // ISO 8601 timestamp
  filters_active: string[];           // ["reduce", "combine", "expand"]
  config: FilterConfig | null;
  trips_affected: number;
  summary: FilterSummary | null;      // ✅ NUEVO campo
}

interface FilterSummary {
  reduced: number;   // Trips afectados por reduce
  combined: number;  // Trips afectados por combine
  expanded: number;  // Trips afectados por expand
}

interface FilterConfig {
  pick_up_date_from?: string | null;
  pick_up_date_to?: string | null;
  rounding_mode?: "multiple_of_5" | "odd_minutes";

  // ⚠️ IMPORTANTE: Estos pueden ser NULL si el filtro nunca se configuró
  reduce: ReduceConfig | null;
  combine: CombineConfig | null;
  expand: ExpandConfig | null;
}

interface ReduceConfig {
  enabled: boolean;                // ⚠️ NO usar este campo directamente!
  minutes_to_reduce: number;
  hotel_names: string[] | null;
  time_range: TimeRange | null;
}

interface CombineConfig {
  enabled: boolean;                // ⚠️ NO usar este campo directamente!
  min_gap: number;
  max_gap: number;
  hotel_names: string[] | null;
  time_range: TimeRange | null;
}

interface ExpandConfig {
  enabled: boolean;                // ⚠️ NO usar este campo directamente!
  min_gap: number;
  max_gap: number;
  max_shift: number;
  hotel_names: string[] | null;
  time_range: TimeRange | null;
}

interface TimeRange {
  start: string;  // "HH:MM:SS"
  end: string;    // "HH:MM:SS"
}
```

---

## 🎯 Lógica de Sincronización

### ⚠️ REGLA CRÍTICA #1: Source of Truth para `enabled`

**NUNCA uses `config.reduce.enabled` directamente del backend.**

```typescript
// ❌ INCORRECTO
const reduceEnabled = backendData.config?.reduce?.enabled;

// ✅ CORRECTO
const reduceEnabled = backendData.filters_active.includes('reduce');
```

**¿Por qué?**
- `filters_active` es el único source of truth de qué filtros están actualmente aplicados
- `config.reduce.enabled` puede estar desincronizado si se hizo un revert parcial
- El backend actualiza `filters_active` pero NO actualiza `config.reduce.enabled` en reverts parciales

---

### ⚠️ REGLA CRÍTICA #2: Manejo de Filtros NULL

Cuando el backend devuelve `config.reduce = null`, significa que ese filtro **nunca se configuró** en el batch.

```typescript
// ❌ INCORRECTO - No maneja NULL
const reduceConfig = {
  ...backendData.config.reduce,  // ← Explota si es null
  enabled: backendData.filters_active.includes('reduce')
};

// ✅ CORRECTO - Maneja NULL con defaults
const reduceConfig = backendData.config?.reduce
  ? {
      ...backendData.config.reduce,
      enabled: backendData.filters_active.includes('reduce')
    }
  : {
      ...DEFAULT_REDUCE_CONFIG,
      enabled: false  // ← Si es null, está deshabilitado
    };
```

---

### ⚠️ REGLA CRÍTICA #3: Sincronización Completa

Debes sincronizar **3 cosas**:

1. **Estado de aplicación** (`lastBatchId`, `appliedAt`, `appliedFilters`)
2. **Configuraciones de filtros** (`reduce`, `combine`, `expand`)
3. **Summary** (trips afectados por cada filtro)

```typescript
// ✅ EJEMPLO COMPLETO
const syncWithBackend = (backendData: FilterCurrentResponse) => {
  // 1. Estado de aplicación
  const appliedState = {
    lastBatchId: backendData.batch_id,
    appliedAt: backendData.applied_at,
    appliedFilters: backendData.filters_active,
    lastSummary: backendData.summary || { reduced: 0, combined: 0, expanded: 0 }
  };

  // 2. Configuraciones de filtros
  const reduceConfig = backendData.config?.reduce
    ? {
        ...backendData.config.reduce,
        enabled: backendData.filters_active.includes('reduce')
      }
    : {
        ...DEFAULT_REDUCE_CONFIG,
        enabled: false
      };

  const combineConfig = backendData.config?.combine
    ? {
        ...backendData.config.combine,
        enabled: backendData.filters_active.includes('combine')
      }
    : {
        ...DEFAULT_COMBINE_CONFIG,
        enabled: false
      };

  const expandConfig = backendData.config?.expand
    ? {
        ...backendData.config.expand,
        enabled: backendData.filters_active.includes('expand')
      }
    : {
        ...DEFAULT_EXPAND_CONFIG,
        enabled: false
      };

  // 3. Update state
  setState({
    ...appliedState,
    reduce: reduceConfig,
    combine: combineConfig,
    expand: expandConfig,
  });

  // 4. Save to localStorage (IMPORTANTE)
  saveConfig({
    reduce: reduceConfig,
    combine: combineConfig,
    expand: expandConfig,
  });
};
```

---

## 📚 Casos de Uso

### Caso 1: Filtros Activos (Escenario Normal)

**Backend Response:**
```json
{
  "has_active_filters": true,
  "batch_id": "uuid-123",
  "applied_at": "2026-01-19T15:17:15Z",
  "filters_active": ["reduce", "combine"],
  "config": {
    "reduce": {
      "enabled": true,
      "minutes_to_reduce": 20,
      "hotel_names": ["Marriott", "Hilton"],
      "time_range": null
    },
    "combine": {
      "enabled": true,
      "min_gap": 10,
      "max_gap": 20,
      "hotel_names": null,
      "time_range": null
    },
    "expand": null
  },
  "trips_affected": 543,
  "summary": {
    "reduced": 320,
    "combined": 223,
    "expanded": 0
  }
}
```

**Frontend debe mostrar:**
- ✅ Switch Reduce: **ON** (porque está en `filters_active`)
- ✅ Switch Combine: **ON** (porque está en `filters_active`)
- ✅ Switch Expand: **OFF** (porque NO está en `filters_active` y config es null)
- ✅ minutes_to_reduce: **20**
- ✅ min_gap: **10**, max_gap: **20**
- ✅ Current Status Card: **"Applied - 543 trips affected"**

---

### Caso 2: Solo Reduce Activo

**Backend Response:**
```json
{
  "has_active_filters": true,
  "filters_active": ["reduce"],
  "config": {
    "reduce": {
      "enabled": true,
      "minutes_to_reduce": 10,
      "hotel_names": null,
      "time_range": null
    },
    "combine": null,
    "expand": null
  },
  "summary": {
    "reduced": 354,
    "combined": 0,
    "expanded": 0
  }
}
```

**Frontend debe mostrar:**
- ✅ Switch Reduce: **ON**
- ✅ Switch Combine: **OFF** (config es null → usar defaults con enabled: false)
- ✅ Switch Expand: **OFF** (config es null → usar defaults con enabled: false)
- ✅ minutes_to_reduce: **10**
- ✅ Current Status: **"Applied - 354 trips affected"**

---

### Caso 3: Revert Parcial

**Situación:** Se aplicaron reduce + combine, luego se hizo revert parcial de combine.

**Backend Response:**
```json
{
  "has_active_filters": true,
  "filters_active": ["reduce"],  // ← Combine fue revertido
  "config": {
    "reduce": {
      "enabled": true,
      "minutes_to_reduce": 20,
      "hotel_names": null,
      "time_range": null
    },
    "combine": {
      "enabled": true,  // ⚠️ Sigue como true en config, pero NO está en filters_active
      "min_gap": 10,
      "max_gap": 20,
      "hotel_names": null,
      "time_range": null
    },
    "expand": null
  },
  "summary": {
    "reduced": 320,
    "combined": 0,      // ← 0 porque fue revertido
    "expanded": 0
  }
}
```

**Frontend debe mostrar:**
- ✅ Switch Reduce: **ON** (está en `filters_active`)
- ✅ Switch Combine: **OFF** (NO está en `filters_active`, aunque config.combine.enabled = true)
- ✅ Switch Expand: **OFF**
- ✅ Combine conserva sus valores (min_gap: 10, max_gap: 20) pero está **deshabilitado**

**Este es el caso que demuestra por qué NO puedes confiar en `config.combine.enabled`.**

---

### Caso 4: Sin Filtros Activos

**Backend Response:**
```json
{
  "has_active_filters": false,
  "batch_id": null,
  "applied_at": null,
  "filters_active": [],
  "config": null,
  "trips_affected": 0,
  "summary": null
}
```

**Frontend debe mostrar:**
- ✅ Switch Reduce: **OFF** (usar DEFAULT_REDUCE_CONFIG con enabled: false)
- ✅ Switch Combine: **OFF** (usar DEFAULT_COMBINE_CONFIG con enabled: false)
- ✅ Switch Expand: **OFF** (usar DEFAULT_EXPAND_CONFIG con enabled: false)
- ✅ Current Status: **"No filters applied"**

---

## 🛠️ Implementación Paso a Paso

### Paso 1: Definir Defaults

```typescript
const DEFAULT_REDUCE_CONFIG: ReduceConfig = {
  enabled: false,
  minutes_to_reduce: 10,
  hotel_names: null,
  time_range: null,
};

const DEFAULT_COMBINE_CONFIG: CombineConfig = {
  enabled: false,
  min_gap: 10,
  max_gap: 20,
  hotel_names: null,
  time_range: null,
};

const DEFAULT_EXPAND_CONFIG: ExpandConfig = {
  enabled: false,
  min_gap: 21,
  max_gap: 30,
  max_shift: 10,
  hotel_names: null,
  time_range: null,
};
```

---

### Paso 2: Función de Sincronización

```typescript
const syncFiltersFromBackend = async (locationId: string, airline: string) => {
  try {
    // 1. Fetch current filter state
    const response = await fetch(
      `/v1/locations/${locationId}/airlines/${airline}/trips/filters/current`,
      {
        headers: {
          Authorization: `Bearer ${getAuthToken()}`,
        },
      }
    );

    if (!response.ok) {
      console.error('Failed to fetch filters:', response.status);
      return;
    }

    const backendData: FilterCurrentResponse = await response.json();

    // 2. Si no hay filtros activos, resetear todo
    if (!backendData.has_active_filters) {
      setState({
        lastBatchId: null,
        appliedAt: null,
        appliedFilters: [],
        lastSummary: { reduced: 0, combined: 0, expanded: 0 },
        reduce: { ...DEFAULT_REDUCE_CONFIG, enabled: false },
        combine: { ...DEFAULT_COMBINE_CONFIG, enabled: false },
        expand: { ...DEFAULT_EXPAND_CONFIG, enabled: false },
      });

      saveConfig({
        reduce: { ...DEFAULT_REDUCE_CONFIG, enabled: false },
        combine: { ...DEFAULT_COMBINE_CONFIG, enabled: false },
        expand: { ...DEFAULT_EXPAND_CONFIG, enabled: false },
      });

      return;
    }

    // 3. Restaurar configuraciones (usando filters_active como source of truth)
    const reduceConfig: ReduceConfig = backendData.config?.reduce
      ? {
          ...backendData.config.reduce,
          enabled: backendData.filters_active.includes('reduce'),
        }
      : {
          ...DEFAULT_REDUCE_CONFIG,
          enabled: false,
        };

    const combineConfig: CombineConfig = backendData.config?.combine
      ? {
          ...backendData.config.combine,
          enabled: backendData.filters_active.includes('combine'),
        }
      : {
          ...DEFAULT_COMBINE_CONFIG,
          enabled: false,
        };

    const expandConfig: ExpandConfig = backendData.config?.expand
      ? {
          ...backendData.config.expand,
          enabled: backendData.filters_active.includes('expand'),
        }
      : {
          ...DEFAULT_EXPAND_CONFIG,
          enabled: false,
        };

    // 4. Update state
    setState({
      lastBatchId: backendData.batch_id,
      appliedAt: backendData.applied_at,
      appliedFilters: backendData.filters_active,
      lastSummary: backendData.summary || { reduced: 0, combined: 0, expanded: 0 },
      reduce: reduceConfig,
      combine: combineConfig,
      expand: expandConfig,
    });

    // 5. Save to localStorage
    saveConfig({
      reduce: reduceConfig,
      combine: combineConfig,
      expand: expandConfig,
    });

    console.log('✅ Filters synced successfully:', {
      filters_active: backendData.filters_active,
      trips_affected: backendData.trips_affected,
      summary: backendData.summary,
    });
  } catch (error) {
    console.error('❌ Failed to sync filters:', error);
  }
};
```

---

### Paso 3: Cuándo Llamar a la Sincronización

```typescript
// 1. Al cargar la página (useEffect)
useEffect(() => {
  if (locationId && airline) {
    syncFiltersFromBackend(locationId, airline);
  }
}, [locationId, airline]);

// 2. Después de aplicar filtros (en el success callback)
const handleApplyFilters = async () => {
  try {
    const response = await applyFilters(locationId, airline, config);

    if (response.ok) {
      // Sincronizar desde el backend para obtener el batch_id y summary
      await syncFiltersFromBackend(locationId, airline);

      toast.success('Filters applied successfully!');
    }
  } catch (error) {
    toast.error('Failed to apply filters');
  }
};

// 3. Después de revertir filtros
const handleRevertFilters = async () => {
  try {
    const response = await revertFilters(locationId, airline);

    if (response.ok) {
      // Sincronizar desde el backend
      await syncFiltersFromBackend(locationId, airline);

      toast.success('Filters reverted successfully!');
    }
  } catch (error) {
    toast.error('Failed to revert filters');
  }
};

// 4. Con polling (opcional, para multi-dispositivo en tiempo real)
useEffect(() => {
  const interval = setInterval(() => {
    syncFiltersFromBackend(locationId, airline);
  }, 30000); // Cada 30 segundos

  return () => clearInterval(interval);
}, [locationId, airline]);
```

---

### Paso 4: Mostrar el Estado Actual

```typescript
const FilterStatusCard = () => {
  const { lastBatchId, appliedAt, appliedFilters, lastSummary } = useFilterStore();

  if (!lastBatchId) {
    return (
      <Card>
        <CardContent>
          <Typography variant="h6">Current Status</Typography>
          <Chip label="Not Applied" color="default" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent>
        <Typography variant="h6">Current Status</Typography>
        <Chip label="Applied" color="success" />

        <Typography variant="body2" sx={{ mt: 2 }}>
          Applied at: {new Date(appliedAt!).toLocaleString()}
        </Typography>

        <Typography variant="body2">
          Active filters: {appliedFilters.join(', ')}
        </Typography>

        <Typography variant="body2" sx={{ mt: 1 }}>
          <strong>Impact:</strong>
        </Typography>
        <ul>
          {lastSummary.reduced > 0 && (
            <li>Reduced: {lastSummary.reduced} trips</li>
          )}
          {lastSummary.combined > 0 && (
            <li>Combined: {lastSummary.combined} trips</li>
          )}
          {lastSummary.expanded > 0 && (
            <li>Expanded: {lastSummary.expanded} trips</li>
          )}
        </ul>

        <Typography variant="body2" color="text.secondary">
          Batch ID: {lastBatchId}
        </Typography>
      </CardContent>
    </Card>
  );
};
```

---

## 🐛 Troubleshooting

### Problema 1: Los switches no se encienden después de aplicar filtros

**Síntoma:** Aplicas reduce, pero el switch sigue apagado.

**Causa:** No estás sincronizando después de aplicar.

**Solución:**
```typescript
const handleApplyFilters = async () => {
  const response = await applyFilters(...);

  if (response.ok) {
    // ✅ CRÍTICO: Sincronizar después de aplicar
    await syncFiltersFromBackend(locationId, airline);
  }
};
```

---

### Problema 2: Valores incorrectos en campos (ej: minutes_to_reduce)

**Síntoma:** Aplicaste con 20 minutos, pero el campo muestra 10.

**Causa:** Estás usando defaults en lugar de los valores del backend.

**Solución:**
```typescript
// ❌ INCORRECTO
const reduceConfig = {
  ...DEFAULT_REDUCE_CONFIG,
  enabled: backendData.filters_active.includes('reduce'),
};

// ✅ CORRECTO
const reduceConfig = backendData.config?.reduce
  ? {
      ...backendData.config.reduce,  // ← Usa los valores del backend
      enabled: backendData.filters_active.includes('reduce'),
    }
  : {
      ...DEFAULT_REDUCE_CONFIG,
      enabled: false,
    };
```

---

### Problema 3: Current Status Card no se actualiza

**Síntoma:** El card sigue mostrando "Not Applied" aunque hay filtros activos.

**Causa:** No estás actualizando `lastBatchId` y `appliedAt`.

**Solución:**
```typescript
setState({
  lastBatchId: backendData.batch_id,        // ✅
  appliedAt: backendData.applied_at,        // ✅
  appliedFilters: backendData.filters_active, // ✅
  // ... resto del state
});
```

---

### Problema 4: Multi-dispositivo no sincroniza

**Síntoma:** Aplicas desde laptop, pero iPhone no lo ve.

**Causa:** No hay polling o WebSocket.

**Solución (Opción 1 - Polling):**
```typescript
useEffect(() => {
  const interval = setInterval(() => {
    syncFiltersFromBackend(locationId, airline);
  }, 30000); // Poll cada 30 segundos

  return () => clearInterval(interval);
}, [locationId, airline]);
```

**Solución (Opción 2 - WebSocket):**
```typescript
useEffect(() => {
  const socket = io('wss://api.gt360.app');

  socket.on('filter:applied', (data) => {
    if (data.locationId === locationId && data.airline === airline) {
      syncFiltersFromBackend(locationId, airline);
      toast.info('Filters updated by another device');
    }
  });

  return () => socket.disconnect();
}, [locationId, airline]);
```

---

### Problema 5: TypeError: Cannot read property 'reduce' of null

**Síntoma:** Error en consola al intentar acceder a `backendData.config.reduce`.

**Causa:** `config` es `null` cuando no hay filtros activos.

**Solución:**
```typescript
// ❌ INCORRECTO
const reduceConfig = {
  ...backendData.config.reduce,  // ← Error si config es null
  enabled: true,
};

// ✅ CORRECTO - Usa optional chaining
const reduceConfig = backendData.config?.reduce
  ? {
      ...backendData.config.reduce,
      enabled: backendData.filters_active.includes('reduce'),
    }
  : {
      ...DEFAULT_REDUCE_CONFIG,
      enabled: false,
    };
```

---

## ✅ Checklist de Implementación

Antes de deployar, verifica:

- [ ] Definiste `DEFAULT_REDUCE_CONFIG`, `DEFAULT_COMBINE_CONFIG`, `DEFAULT_EXPAND_CONFIG`
- [ ] Implementaste `syncFiltersFromBackend()`
- [ ] Llamas a `syncFiltersFromBackend()` en `useEffect` al cargar la página
- [ ] Llamas a `syncFiltersFromBackend()` después de aplicar filtros
- [ ] Llamas a `syncFiltersFromBackend()` después de revertir filtros
- [ ] Usas `filters_active` como source of truth para `enabled` (NO uses `config.reduce.enabled`)
- [ ] Manejas el caso `config.reduce = null` con defaults
- [ ] Actualizas `lastBatchId`, `appliedAt`, `appliedFilters`, `lastSummary`
- [ ] Guardas en `localStorage` después de sincronizar
- [ ] Implementaste polling o WebSocket para multi-dispositivo (opcional pero recomendado)
- [ ] El Current Status Card muestra "Applied" cuando hay filtros activos
- [ ] Los switches se encienden/apagan según `filters_active`
- [ ] Los valores de los campos (minutes_to_reduce, min_gap, etc.) vienen del backend

---

## 📊 Tabla de Referencia Rápida

| Campo Backend | ¿Qué Representa? | ¿Cómo Usar? |
|--------------|------------------|-------------|
| `has_active_filters` | ¿Hay algún filtro activo? | Mostrar "Applied" o "Not Applied" |
| `batch_id` | ID del batch activo | Guardar en state, mostrar en UI |
| `applied_at` | Timestamp de aplicación | Mostrar en formato legible |
| `filters_active` | **SOURCE OF TRUTH** de qué filtros están ON | Usar para `enabled` de cada filtro |
| `config.reduce` | Configuración de reduce | Usar para valores (minutes_to_reduce, etc.) |
| `config.reduce.enabled` | ⚠️ **NO USAR** | Puede estar desincronizado |
| `summary.reduced` | Trips afectados por reduce | Mostrar en UI |
| `summary.combined` | Trips afectados por combine | Mostrar en UI |
| `summary.expanded` | Trips afectados por expand | Mostrar en UI |

---

## 🎯 Ejemplo Completo de Zustand Store

```typescript
import create from 'zustand';
import { persist } from 'zustand/middleware';

interface FilterStore {
  // Estado de aplicación
  lastBatchId: string | null;
  appliedAt: string | null;
  appliedFilters: string[];
  lastSummary: { reduced: number; combined: number; expanded: number };

  // Configuraciones de filtros
  reduce: ReduceConfig;
  combine: CombineConfig;
  expand: ExpandConfig;

  // Actions
  syncFromBackend: (data: FilterCurrentResponse) => void;
  updateReduce: (config: Partial<ReduceConfig>) => void;
  updateCombine: (config: Partial<CombineConfig>) => void;
  updateExpand: (config: Partial<ExpandConfig>) => void;
}

const useFilterStore = create<FilterStore>()(
  persist(
    (set) => ({
      // Initial state
      lastBatchId: null,
      appliedAt: null,
      appliedFilters: [],
      lastSummary: { reduced: 0, combined: 0, expanded: 0 },
      reduce: DEFAULT_REDUCE_CONFIG,
      combine: DEFAULT_COMBINE_CONFIG,
      expand: DEFAULT_EXPAND_CONFIG,

      // Sync from backend
      syncFromBackend: (data: FilterCurrentResponse) => {
        if (!data.has_active_filters) {
          set({
            lastBatchId: null,
            appliedAt: null,
            appliedFilters: [],
            lastSummary: { reduced: 0, combined: 0, expanded: 0 },
            reduce: { ...DEFAULT_REDUCE_CONFIG, enabled: false },
            combine: { ...DEFAULT_COMBINE_CONFIG, enabled: false },
            expand: { ...DEFAULT_EXPAND_CONFIG, enabled: false },
          });
          return;
        }

        const reduceConfig = data.config?.reduce
          ? { ...data.config.reduce, enabled: data.filters_active.includes('reduce') }
          : { ...DEFAULT_REDUCE_CONFIG, enabled: false };

        const combineConfig = data.config?.combine
          ? { ...data.config.combine, enabled: data.filters_active.includes('combine') }
          : { ...DEFAULT_COMBINE_CONFIG, enabled: false };

        const expandConfig = data.config?.expand
          ? { ...data.config.expand, enabled: data.filters_active.includes('expand') }
          : { ...DEFAULT_EXPAND_CONFIG, enabled: false };

        set({
          lastBatchId: data.batch_id,
          appliedAt: data.applied_at,
          appliedFilters: data.filters_active,
          lastSummary: data.summary || { reduced: 0, combined: 0, expanded: 0 },
          reduce: reduceConfig,
          combine: combineConfig,
          expand: expandConfig,
        });
      },

      // Update individual filters (for UI changes before applying)
      updateReduce: (config) => set((state) => ({
        reduce: { ...state.reduce, ...config }
      })),

      updateCombine: (config) => set((state) => ({
        combine: { ...state.combine, ...config }
      })),

      updateExpand: (config) => set((state) => ({
        expand: { ...state.expand, ...config }
      })),
    }),
    {
      name: 'filter-store', // localStorage key
    }
  )
);

export default useFilterStore;
```

---

## 🚀 Quick Start Example

```typescript
// En tu componente principal de filters
const FiltersPage = () => {
  const { syncFromBackend, reduce, combine, expand } = useFilterStore();
  const { locationId, airline } = useParams();

  // 1. Sincronizar al cargar
  useEffect(() => {
    const fetchFilters = async () => {
      try {
        const response = await fetch(
          `/v1/locations/${locationId}/airlines/${airline}/trips/filters/current`,
          {
            headers: {
              Authorization: `Bearer ${getAuthToken()}`,
            },
          }
        );

        if (response.ok) {
          const data = await response.json();
          syncFromBackend(data);
        }
      } catch (error) {
        console.error('Failed to fetch filters:', error);
      }
    };

    fetchFilters();
  }, [locationId, airline, syncFromBackend]);

  return (
    <div>
      <FilterStatusCard />

      <ReduceFilter
        config={reduce}
        onUpdate={(newConfig) => updateReduce(newConfig)}
      />

      <CombineFilter
        config={combine}
        onUpdate={(newConfig) => updateCombine(newConfig)}
      />

      <ExpandFilter
        config={expand}
        onUpdate={(newConfig) => updateExpand(newConfig)}
      />

      <Button onClick={handleApplyFilters}>
        Apply Filters
      </Button>
    </div>
  );
};
```

---

## 📞 Soporte

Si después de seguir esta guía sigues teniendo problemas:

1. Verifica que el backend devuelve los datos correctos usando:
   ```bash
   curl -H "Authorization: Bearer YOUR_TOKEN" \
     https://api.gt360.app/v1/locations/LOCATION_ID/airlines/AIRLINE/trips/filters/current
   ```

2. Revisa la consola del navegador para errores de JavaScript

3. Verifica que `localStorage` no esté corrupto (bórralo y recarga)

4. Asegúrate de usar la última versión del backend con el campo `summary`

---

**Última actualización:** 2026-01-19
**Versión del backend:** Con soporte para `summary` en FilterCurrentResponse
