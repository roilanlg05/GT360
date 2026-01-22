# 🐛 Bug Fix: Error en Sincronización de Filtros

## ❌ Código con Bug (Lo que implementaste)

```typescript
const reduceConfig = backendData.config?.reduce
  ? { ...backendData.config.reduce, enabled: backendData.filters_active.includes('reduce') }
  : { ...DEFAULT_REDUCE_CONFIG, enabled: backendData.filters_active.includes('reduce') }
  //                             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  //                             🐛 BUG: Si config.reduce es null, enabled debería ser false
```

## 🔍 ¿Cuál es el Problema?

Cuando `backendData.config.reduce` es `null`, estás usando:

```typescript
enabled: backendData.filters_active.includes('reduce')
```

**Pero esto está mal porque:**

1. Si `config.reduce` es `null`, significa que el filtro **NUNCA** se configuró en el batch
2. Si nunca se configuró, entonces **NUNCA** debería estar en `filters_active`
3. Por lo tanto, `enabled` debería ser **SIEMPRE `false`** cuando `config.reduce` es `null`

## ✅ Código Correcto

```typescript
const reduceConfig = backendData.config?.reduce
  ? { ...backendData.config.reduce, enabled: backendData.filters_active.includes('reduce') }
  : { ...DEFAULT_REDUCE_CONFIG, enabled: false }
  //                             ^^^^^^^^^^^^^^^^
  //                             ✅ CORRECTO: Siempre false si config es null
```

Lo mismo aplica para `combine` y `expand`:

```typescript
const combineConfig = backendData.config?.combine
  ? { ...backendData.config.combine, enabled: backendData.filters_active.includes('combine') }
  : { ...DEFAULT_COMBINE_CONFIG, enabled: false };  // ✅

const expandConfig = backendData.config?.expand
  ? { ...backendData.config.expand, enabled: backendData.filters_active.includes('expand') }
  : { ...DEFAULT_EXPAND_CONFIG, enabled: false };  // ✅
```

---

## 📊 Ejemplo del Bug en Acción

### Escenario: Backend devuelve esto

```json
{
  "has_active_filters": false,
  "filters_active": [],
  "config": null
}
```

### Con el Bug

```typescript
const reduceConfig = null?.reduce  // null
  ? { ...null, enabled: [].includes('reduce') }
  : { ...DEFAULT_REDUCE_CONFIG, enabled: [].includes('reduce') };
  //                                      ^^^^^^^^^^^^^^^^^^^^
  //                                      false (pero por suerte)

// Resultado: enabled: false (funciona por casualidad)
```

Parece que funciona, pero...

### Otro Escenario: Backend devuelve esto

```json
{
  "has_active_filters": true,
  "filters_active": ["reduce"],  // ← Solo reduce está activo
  "config": {
    "reduce": {
      "enabled": true,
      "minutes_to_reduce": 10
    },
    "combine": null,  // ← Combine nunca se configuró
    "expand": null    // ← Expand nunca se configuró
  }
}
```

### Con el Bug

```typescript
// Reduce (funciona bien)
const reduceConfig = {
  enabled: true,  // ✅ Correcto
  minutes_to_reduce: 10
};

// Combine (BUG!)
const combineConfig = null  // config.combine es null
  ? { ...null, enabled: ['reduce'].includes('combine') }
  : { ...DEFAULT_COMBINE_CONFIG, enabled: ['reduce'].includes('combine') };
  //                                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  //                                      false (funciona por suerte otra vez)

// Resultado: enabled: false (funciona por casualidad)
```

**¿Por qué funciona por casualidad?** Porque `['reduce'].includes('combine')` es `false`, entonces el bug no se nota.

### Pero aquí está el VERDADERO BUG

Imagina que alguien modifica `filters_active` en el backend para incluir un filtro que no tiene config (lo cual sería un bug del backend, pero igual tu frontend debe ser robusto):

```json
{
  "has_active_filters": true,
  "filters_active": ["reduce", "combine"],  // ← Backend tiene un bug y dice que combine está activo
  "config": {
    "reduce": { "enabled": true, "minutes_to_reduce": 10 },
    "combine": null,  // ← Pero combine es null!
    "expand": null
  }
}
```

### Con el Bug

```typescript
const combineConfig = null  // config.combine es null
  ? { ...null, enabled: ['reduce', 'combine'].includes('combine') }
  : { ...DEFAULT_COMBINE_CONFIG, enabled: ['reduce', 'combine'].includes('combine') };
  //                                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  //                                      true ← 🐛 AQUÍ ESTÁ EL BUG!

// Resultado: enabled: true ← INCORRECTO!
// Estás activando un filtro que no tiene configuración!
```

**El switch de Combine se enciende, pero no tienes configuración!** Esto puede causar que envíes `combine.enabled = true` con valores por defecto al backend cuando el usuario intente aplicar filtros.

---

## 💡 La Regla Correcta

**REGLA SIMPLE:**

```
Si config.FILTRO es null → enabled SIEMPRE debe ser false
```

**¿Por qué?**

Porque si el backend no tiene configuración para ese filtro, significa que **NUNCA** se configuró, por lo tanto, **NUNCA** debería estar activo.

---

## ✅ Solución Completa

```typescript
const syncFiltersFromBackend = (backendData: FilterCurrentResponse) => {
  // 1. Si no hay filtros activos, resetear todo
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

  // 2. Restaurar configuraciones
  // ✅ CORRECTO: enabled es false si config es null
  const reduceConfig = backendData.config?.reduce
    ? {
        ...backendData.config.reduce,
        enabled: backendData.filters_active.includes('reduce'),
      }
    : {
        ...DEFAULT_REDUCE_CONFIG,
        enabled: false,  // ✅ Siempre false si config es null
      };

  const combineConfig = backendData.config?.combine
    ? {
        ...backendData.config.combine,
        enabled: backendData.filters_active.includes('combine'),
      }
    : {
        ...DEFAULT_COMBINE_CONFIG,
        enabled: false,  // ✅ Siempre false si config es null
      };

  const expandConfig = backendData.config?.expand
    ? {
        ...backendData.config.expand,
        enabled: backendData.filters_active.includes('expand'),
      }
    : {
        ...DEFAULT_EXPAND_CONFIG,
        enabled: false,  // ✅ Siempre false si config es null
      };

  // 3. Update state
  setState({
    lastBatchId: backendData.batch_id,
    appliedAt: backendData.applied_at,
    appliedFilters: backendData.filters_active,
    lastSummary: backendData.summary || { reduced: 0, combined: 0, expanded: 0 },
    reduce: reduceConfig,
    combine: combineConfig,
    expand: expandConfig,
  });

  // 4. Save to localStorage
  saveConfig({
    reduce: reduceConfig,
    combine: combineConfig,
    expand: expandConfig,
  });
};
```

---

## 🧪 Casos de Prueba

### Test 1: Sin filtros activos

```typescript
const backendData = {
  has_active_filters: false,
  filters_active: [],
  config: null,
  summary: null,
};

syncFiltersFromBackend(backendData);

// ✅ Esperado:
// reduce.enabled = false
// combine.enabled = false
// expand.enabled = false
```

### Test 2: Solo reduce activo

```typescript
const backendData = {
  has_active_filters: true,
  filters_active: ['reduce'],
  config: {
    reduce: { enabled: true, minutes_to_reduce: 10 },
    combine: null,
    expand: null,
  },
  summary: { reduced: 354, combined: 0, expanded: 0 },
};

syncFiltersFromBackend(backendData);

// ✅ Esperado:
// reduce.enabled = true
// reduce.minutes_to_reduce = 10
// combine.enabled = false  ← Importante: false porque config es null
// expand.enabled = false   ← Importante: false porque config es null
```

### Test 3: Reduce + Combine activos

```typescript
const backendData = {
  has_active_filters: true,
  filters_active: ['reduce', 'combine'],
  config: {
    reduce: { enabled: true, minutes_to_reduce: 20 },
    combine: { enabled: true, min_gap: 10, max_gap: 20 },
    expand: null,
  },
  summary: { reduced: 320, combined: 223, expanded: 0 },
};

syncFiltersFromBackend(backendData);

// ✅ Esperado:
// reduce.enabled = true
// reduce.minutes_to_reduce = 20
// combine.enabled = true
// combine.min_gap = 10
// combine.max_gap = 20
// expand.enabled = false  ← Importante: false porque config es null
```

### Test 4: Revert parcial

```typescript
const backendData = {
  has_active_filters: true,
  filters_active: ['reduce'],  // ← Combine fue revertido
  config: {
    reduce: { enabled: true, minutes_to_reduce: 20 },
    combine: { enabled: true, min_gap: 10, max_gap: 20 },  // ← Sigue en config
    expand: null,
  },
  summary: { reduced: 320, combined: 0, expanded: 0 },
};

syncFiltersFromBackend(backendData);

// ✅ Esperado:
// reduce.enabled = true
// reduce.minutes_to_reduce = 20
// combine.enabled = false  ← Importante: false porque NO está en filters_active
// combine.min_gap = 10     ← Pero conserva los valores
// combine.max_gap = 20
// expand.enabled = false
```

---

## 🎯 Resumen del Fix

**Cambio a hacer:**

```diff
  const reduceConfig = backendData.config?.reduce
    ? { ...backendData.config.reduce, enabled: backendData.filters_active.includes('reduce') }
-   : { ...DEFAULT_REDUCE_CONFIG, enabled: backendData.filters_active.includes('reduce') }
+   : { ...DEFAULT_REDUCE_CONFIG, enabled: false }

  const combineConfig = backendData.config?.combine
    ? { ...backendData.config.combine, enabled: backendData.filters_active.includes('combine') }
-   : { ...DEFAULT_COMBINE_CONFIG, enabled: backendData.filters_active.includes('combine') }
+   : { ...DEFAULT_COMBINE_CONFIG, enabled: false }

  const expandConfig = backendData.config?.expand
    ? { ...backendData.config.expand, enabled: backendData.filters_active.includes('expand') }
-   : { ...DEFAULT_EXPAND_CONFIG, enabled: backendData.filters_active.includes('expand') }
+   : { ...DEFAULT_EXPAND_CONFIG, enabled: false }
```

**Razón:**

Si `config` es `null`, el filtro nunca se configuró, por lo tanto `enabled` debe ser `false`.

---

## ✅ Checklist Post-Fix

Después de aplicar el fix, verifica:

- [ ] Los switches de filtros que nunca se configuraron están **OFF**
- [ ] Los switches de filtros configurados pero revertidos están **OFF**
- [ ] Los switches de filtros activos están **ON**
- [ ] Los valores de configuración (minutes_to_reduce, min_gap, etc.) se conservan correctamente
- [ ] El Current Status Card muestra el estado correcto
- [ ] La sincronización multi-dispositivo funciona
- [ ] Los filtros se pueden aplicar/revertir correctamente

---

**Última actualización:** 2026-01-19
