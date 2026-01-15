# Bug Frontend: Airlines Parseadas como Objetos

**Fecha:** 2026-01-14 02:45 UTC
**Archivo afectado:** `use-location-airlines.ts:68-76`
**Severidad:** Alta

---

## Error Exacto

```
[useLocationAirlines] airline is object without code: {W: 'N'}
```

El string `"WN"` se convierte en objeto `{W: 'N'}` (cada caracter como key/value).

---

## Causa Raiz

El string `"WN"` esta siendo iterado como si fuera un array, convirtiendo cada caracter en un par key-value.

```tsx
// INCORRECTO - airline es un objeto
<Link href={`/dashboard/locations/${location}/${airline}`}>
// Resultado: /dashboard/locations/SDF/[object Object]

// CORRECTO - airline es un string
<Link href={`/dashboard/locations/${location}/${airline}`}>
// Resultado: /dashboard/locations/SDF/WN
```

---

## Respuesta del Backend

El endpoint `GET /v1/locations/{location_id}/airlines` retorna:

```json
{
  "location_id": "72a1543b-5366-4096-b5d6-94fc9987e3e0",
  "location_name": "SDF",
  "airlines": ["WN"],
  "total": 1
}
```

**Nota:** `airlines` es un array de **strings**, no de objetos.

---

## Problema en el Frontend

El frontend esta parseando incorrectamente la respuesta. Posibles causas:

### Causa 1: Usando el objeto completo en vez del array

```tsx
// INCORRECTO
const airlines = response.data;  // { location_id: ..., airlines: [...] }
airlines.map(a => <Link href={`.../${a}`} />)  // a es un objeto!

// CORRECTO
const airlines = response.data.airlines;  // ["WN", "AA"]
airlines.map(a => <Link href={`.../${a}`} />)  // a es "WN"
```

### Causa 2: El estado guarda objetos en vez de strings

```tsx
// INCORRECTO
const [airlines, setAirlines] = useState([]);
// Si se guarda { code: "WN" } en vez de "WN"
airlines.map(a => <Link href={`.../${a}`} />)  // [object Object]

// CORRECTO
airlines.map(a => <Link href={`.../${a.code || a}`} />)
// O mejor, guardar strings directamente
```

### Causa 3: Hook retorna estructura incorrecta

Revisar `use-location-airlines.ts`:

```tsx
// Verificar que el hook retorne strings
const { airlines } = useLocationAirlines(locationId);

// Debug: verificar tipo
console.log('Airlines type:', typeof airlines[0]);
console.log('Airlines[0]:', airlines[0]);
```

---

## Solucion Recomendada

### Paso 1: Verificar parseo en `use-location-airlines.ts`

```tsx
// Asegurar que se extraen solo los strings
const parseAirlines = (response: ApiResponse): string[] => {
  if (response?.data?.airlines && Array.isArray(response.data.airlines)) {
    return response.data.airlines;  // ["WN", "AA", "DL"]
  }
  return [];
};
```

### Paso 2: Validar antes de usar en Link

En `nav-main.tsx:1185`:

```tsx
{airlines.map((airline) => {
  // Validar que airline es string
  const airlineCode = typeof airline === 'string'
    ? airline
    : airline?.code || String(airline);

  return (
    <Link
      key={airlineCode}
      href={`/dashboard/locations/${locationName}/${airlineCode}`}
    >
      {airlineCode}
    </Link>
  );
})}
```

### Paso 3: Agregar logging para debug

```tsx
// En use-location-airlines.ts
console.log('[useLocationAirlines] Raw response:', response);
console.log('[useLocationAirlines] response.data:', response.data);
console.log('[useLocationAirlines] airlines array:', response.data?.airlines);
console.log('[useLocationAirlines] First airline type:', typeof response.data?.airlines?.[0]);
```

---

## Verificacion

Despues de aplicar el fix, la consola debe mostrar:

```
[useLocationAirlines] airlines array: ["WN"]
[useLocationAirlines] First airline type: string
```

Y el Link debe generar:

```
/dashboard/locations/SDF/WN
```

---

## Archivos a Revisar

1. `src/hooks/use-location-airlines.ts` - Parseo de respuesta
2. `src/components/nav-main.tsx:1185` - Uso en Link
3. `src/lib/api/locations.ts` - Llamada al endpoint (si existe)

---

## Estructura Esperada del Estado

```typescript
interface LocationAirlinesState {
  airlines: string[];  // ["WN", "AA", "DL"] - NO objetos
  isLoading: boolean;
  error: string | null;
}
```

---

## Contacto Backend

El backend esta funcionando correctamente. El endpoint retorna:
- Status: 200 OK
- Body: `{ airlines: ["WN"], total: 1, ... }`

El problema es 100% del parseo en el frontend.
