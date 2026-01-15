# Fix Frontend: Airlines Parseadas como {W: 'N'}

**Fecha:** 2026-01-14 02:50 UTC
**Archivo:** `use-location-airlines.ts`
**Severidad:** Critica

---

## El Problema

El log muestra:
```
[useLocationAirlines] API result: {success: true, status: 200, data: {…}, airlines: Array(1)}
[useLocationAirlines] airline is object without code: {W: 'N'}
```

El string `"WN"` se convierte en `{W: 'N'}` (objeto con caracteres como keys).

---

## Diagnostico

Esto ocurre cuando se itera sobre un STRING como si fuera un ARRAY:

```javascript
// Si airline = "WN" (string)
const result = {};
for (const [index, char] of Object.entries(airline)) {
  result[index] = char;
}
// result = { "0": "W", "1": "N" }

// O peor, con spread en objeto:
const obj = { ...airline };  // Si airline es "WN"
// obj = { 0: "W", 1: "N" }
```

---

## Donde Buscar el Bug

### 1. Revisar linea 68-76 de `use-location-airlines.ts`

El codigo actual parece hacer algo como:
```tsx
// INCORRECTO - iterando el string
const validatedAirlines = airlines.map((airline) => {
  if (typeof airline === 'object') {
    // Llega aqui porque "WN" fue convertido a {W: 'N'}
  }
});
```

### 2. Buscar donde se extrae `airlines` de la respuesta

```tsx
// POSIBLE BUG - spread operator en string
const result = response.data;
const airlines = [...result.airlines[0]];  // ["W", "N"] no ["WN"]!

// O acceso incorrecto
const airlines = Object.values(result.airlines[0]);  // ['W', 'N']
```

---

## Solucion

### Paso 1: Verificar la extraccion de airlines

En `use-location-airlines.ts`, buscar donde se lee la respuesta:

```tsx
// INCORRECTO (posible causa del bug)
const fetchAirlines = async () => {
  const response = await api.get(...);
  const data = response.data;

  // BUG: Si airlines es un string en vez de array
  const airlines = data.airlines.map(a => ({...a}));  // Convierte "WN" a {W:'N'}

  // O BUG: Spread en string
  const airlines = [...data.airlines[0]];  // ["W", "N"]
};

// CORRECTO
const fetchAirlines = async () => {
  const response = await api.get(...);
  const data = response.data;

  // Verificar que es un array de strings
  if (Array.isArray(data.airlines)) {
    const airlines = data.airlines.filter(a => typeof a === 'string');
    setAirlines(airlines);  // ["WN", "AA"]
  }
};
```

### Paso 2: Agregar validacion robusta

```tsx
const parseAirlines = (responseData: unknown): string[] => {
  // Validar estructura
  if (!responseData || typeof responseData !== 'object') {
    console.error('[parseAirlines] Invalid response data');
    return [];
  }

  const data = responseData as { airlines?: unknown };

  // Verificar que airlines existe y es array
  if (!Array.isArray(data.airlines)) {
    console.error('[parseAirlines] airlines is not an array:', data.airlines);
    return [];
  }

  // Filtrar solo strings validos
  const validAirlines = data.airlines.filter((a): a is string => {
    if (typeof a !== 'string') {
      console.error('[parseAirlines] Invalid airline (not string):', a);
      return false;
    }
    return a.length > 0;
  });

  console.log('[parseAirlines] Valid airlines:', validAirlines);
  return validAirlines;
};
```

### Paso 3: Debug - agregar logging detallado

```tsx
const fetchAirlines = async (locationId: string) => {
  try {
    const response = await api.get(`/v1/locations/${locationId}/airlines`);

    // Debug completo
    console.log('[fetchAirlines] Raw response:', response);
    console.log('[fetchAirlines] response.data:', response.data);
    console.log('[fetchAirlines] response.data.airlines:', response.data.airlines);
    console.log('[fetchAirlines] airlines[0]:', response.data.airlines?.[0]);
    console.log('[fetchAirlines] typeof airlines[0]:', typeof response.data.airlines?.[0]);

    // Si el primer elemento es string, todo bien
    // Si es objeto como {W:'N'}, hay bug en el parseo

    const airlines = parseAirlines(response.data);
    setAirlines(airlines);
  } catch (error) {
    console.error('[fetchAirlines] Error:', error);
  }
};
```

---

## Verificacion

Despues del fix, la consola debe mostrar:

```
[fetchAirlines] response.data.airlines: ["WN"]
[fetchAirlines] airlines[0]: "WN"
[fetchAirlines] typeof airlines[0]: string
[parseAirlines] Valid airlines: ["WN"]
```

**NO debe mostrar:**
```
{W: 'N'}
typeof airlines[0]: object
```

---

## Backend Reference

El backend retorna exactamente esto:

```json
{
  "location_id": "uuid",
  "location_name": "SDF",
  "airlines": ["WN"],
  "total": 1
}
```

- `airlines` es `Array<string>`
- Cada elemento es un string como `"WN"`, `"AA"`, `"DL"`
- NO son objetos

---

## Posibles Causas del Bug

1. **Spread operator en string:**
   ```tsx
   const arr = [..."WN"];  // ["W", "N"]
   ```

2. **Object.entries en string:**
   ```tsx
   Object.entries("WN")  // [["0", "W"], ["1", "N"]]
   ```

3. **Object.fromEntries mal usado:**
   ```tsx
   Object.fromEntries(Object.entries("WN"))  // {"0": "W", "1": "N"}
   ```

4. **Mapear y hacer spread:**
   ```tsx
   airlines.map(a => ({...a}))  // Si a="WN", result={0:"W",1:"N"}
   ```

---

## Archivos a Revisar

1. `src/hooks/use-location-airlines.ts` - Lineas 52-92
2. `src/lib/api/client.ts` - El cliente HTTP (por si transforma responses)
3. Cualquier middleware que procese responses

---

## Quick Fix

Si necesitan un fix rapido mientras investigan:

```tsx
// En use-location-airlines.ts, donde se mapean las airlines
const validatedAirlines = airlines
  .map((airline) => {
    // Si es string, usarlo directamente
    if (typeof airline === 'string') {
      return airline;
    }
    // Si es objeto con valores, unir los valores
    if (typeof airline === 'object' && airline !== null) {
      const values = Object.values(airline);
      if (values.every(v => typeof v === 'string')) {
        return values.join('');  // {W:'N'} -> "WN"
      }
    }
    return null;
  })
  .filter((a): a is string => a !== null && a.length > 0);
```
