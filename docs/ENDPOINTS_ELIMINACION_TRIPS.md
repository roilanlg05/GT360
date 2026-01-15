# Guía de Endpoints de Eliminación de Trips

## 📋 Tabla de Contenidos
- [Eliminar Trips Específicos](#eliminar-trips-específicos)
- [Eliminar Todos los Trips](#eliminar-todos-los-trips)
- [Códigos de Respuesta](#códigos-de-respuesta)
- [Manejo de Errores](#manejo-de-errores)

---

## 🎯 Eliminar Trips Específicos

### Endpoint
```
DELETE /v1/locations/{location_id}/trips
```

### Descripción
Elimina uno o varios trips específicos proporcionando sus IDs como query parameters.

### Parámetros

| Parámetro | Tipo | Ubicación | Requerido | Descripción |
|-----------|------|-----------|-----------|-------------|
| `location_id` | UUID | Path | ✅ Sí | ID de la location |
| `trip_ids` | UUID[] | Query | ✅ Sí | Lista de IDs de trips a eliminar |

### Headers Requeridos
```
Authorization: Bearer {token}
```

### Permisos
- Solo usuarios con rol `manager`

### Ejemplos de Uso

#### 🔹 Eliminar UN trip
```javascript
const locationId = "550e8400-e29b-41d4-a716-446655440000";
const tripId = "123e4567-e89b-12d3-a456-426614174000";

const response = await fetch(
  `https://api.example.com/v1/locations/${locationId}/trips?trip_ids=${tripId}`,
  {
    method: 'DELETE',
    headers: {
      'Authorization': `Bearer ${token}`
    }
  }
);

if (response.status === 204) {
  console.log('Trip eliminado exitosamente');
}
```

#### 🔹 Eliminar MÚLTIPLES trips
```javascript
const locationId = "550e8400-e29b-41d4-a716-446655440000";
const tripIds = [
  "123e4567-e89b-12d3-a456-426614174000",
  "987fcdeb-51a2-43f1-b456-426614174111",
  "456e7890-a12b-34c5-d678-426614174222"
];

// Construir query string con múltiples trip_ids
const queryString = tripIds.map(id => `trip_ids=${id}`).join('&');

const response = await fetch(
  `https://api.example.com/v1/locations/${locationId}/trips?${queryString}`,
  {
    method: 'DELETE',
    headers: {
      'Authorization': `Bearer ${token}`
    }
  }
);

if (response.status === 204) {
  console.log(`${tripIds.length} trips eliminados exitosamente`);
}
```

#### 🔹 Con axios
```javascript
import axios from 'axios';

const deleteTrips = async (locationId, tripIds) => {
  try {
    await axios.delete(`/v1/locations/${locationId}/trips`, {
      params: {
        trip_ids: tripIds // axios maneja arrays automáticamente
      },
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });
    
    return { success: true };
  } catch (error) {
    console.error('Error eliminando trips:', error.response?.data);
    return { success: false, error: error.response?.data };
  }
};

// Uso
await deleteTrips(locationId, [tripId1, tripId2, tripId3]);
```

---

## 🗑️ Eliminar Todos los Trips

### Endpoint
```
DELETE /v1/locations/{location_id}/trips/all
```

### ⚠️ ADVERTENCIA
Este endpoint elimina **TODOS** los trips de una location. Úsalo con extrema precaución.

### Descripción
Elimina todos los trips asociados a una location específica.

### Parámetros

| Parámetro | Tipo | Ubicación | Requerido | Descripción |
|-----------|------|-----------|-----------|-------------|
| `location_id` | UUID | Path | ✅ Sí | ID de la location |

### Headers Requeridos
```
Authorization: Bearer {token}
```

### Permisos
- Solo usuarios con rol `manager`

### Ejemplo de Uso

```javascript
const locationId = "550e8400-e29b-41d4-a716-446655440000";

// ⚠️ Mostrar confirmación al usuario ANTES de ejecutar
const confirmDelete = confirm(
  '¿Está seguro que desea eliminar TODOS los trips de esta location? ' +
  'Esta acción NO se puede deshacer.'
);

if (!confirmDelete) {
  return;
}

const response = await fetch(
  `https://api.example.com/v1/locations/${locationId}/trips/all`,
  {
    method: 'DELETE',
    headers: {
      'Authorization': `Bearer ${token}`
    }
  }
);

if (response.status === 204) {
  console.log('Todos los trips eliminados exitosamente');
}
```

### 🎨 Componente React Ejemplo

```jsx
import { useState } from 'react';

function DeleteAllTripsButton({ locationId }) {
  const [isDeleting, setIsDeleting] = useState(false);

  const handleDeleteAll = async () => {
    // Doble confirmación para seguridad
    const firstConfirm = window.confirm(
      '⚠️ ¿Eliminar TODOS los trips de esta location?'
    );
    
    if (!firstConfirm) return;

    const secondConfirm = window.confirm(
      '⚠️⚠️ ÚLTIMA ADVERTENCIA: Esta acción es IRREVERSIBLE. ¿Continuar?'
    );

    if (!secondConfirm) return;

    setIsDeleting(true);
    
    try {
      const response = await fetch(
        `/v1/locations/${locationId}/trips/all`,
        {
          method: 'DELETE',
          headers: {
            'Authorization': `Bearer ${token}`
          }
        }
      );

      if (response.status === 204) {
        alert('✅ Todos los trips eliminados');
        // Actualizar UI
      }
    } catch (error) {
      alert('❌ Error eliminando trips');
      console.error(error);
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <button 
      onClick={handleDeleteAll}
      disabled={isDeleting}
      className="btn-danger"
    >
      {isDeleting ? 'Eliminando...' : '🗑️ Eliminar Todos los Trips'}
    </button>
  );
}
```

---

## 📊 Códigos de Respuesta

| Código | Significado | Descripción |
|--------|-------------|-------------|
| `204` | No Content | ✅ Trips eliminados exitosamente |
| `400` | Bad Request | ❌ UUID inválido o parámetros incorrectos |
| `401` | Unauthorized | ❌ Token inválido o expirado |
| `403` | Forbidden | ❌ Usuario sin permisos (no es manager) |
| `404` | Not Found | ❌ Location o trips no encontrados |

---

## ⚠️ Manejo de Errores

### Errores Comunes

#### 1. UUID Inválido
```json
{
  "detail": "ID de location inválido"
}
```
**Solución**: Validar que el UUID tenga formato correcto antes de enviar.

#### 2. Trips No Encontrados
```json
{
  "detail": "No se encontraron trips para eliminar con los IDs proporcionados en la location especificada."
}
```
**Causa**: Los trip_ids no existen o no pertenecen a esa location.

#### 3. IDs Inválidos en Lista
```json
{
  "detail": "IDs de trip inválidos: abc-123, xyz-456"
}
```
**Solución**: Todos los IDs deben ser UUIDs válidos.

### Ejemplo de Manejo Completo

```javascript
async function deleteTripsWithErrorHandling(locationId, tripIds) {
  try {
    const queryString = tripIds.map(id => `trip_ids=${id}`).join('&');
    
    const response = await fetch(
      `/v1/locations/${locationId}/trips?${queryString}`,
      {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      }
    );

    if (response.status === 204) {
      return {
        success: true,
        message: `${tripIds.length} trip(s) eliminado(s)`
      };
    }

    const error = await response.json();
    
    switch (response.status) {
      case 400:
        return { 
          success: false, 
          message: 'IDs inválidos: ' + error.detail 
        };
      case 404:
        return { 
          success: false, 
          message: 'Trips no encontrados' 
        };
      case 403:
        return { 
          success: false, 
          message: 'No tienes permisos para eliminar trips' 
        };
      default:
        return { 
          success: false, 
          message: 'Error desconocido: ' + error.detail 
        };
    }
    
  } catch (error) {
    console.error('Error de red:', error);
    return { 
      success: false, 
      message: 'Error de conexión. Intenta nuevamente.' 
    };
  }
}
```

---

## 💡 Mejores Prácticas

### ✅ DO
- Siempre validar UUIDs antes de enviar
- Mostrar confirmación al usuario antes de eliminar
- Manejar todos los códigos de error posibles
- Actualizar la UI después de eliminaciones exitosas
- Usar doble confirmación para `/trips/all`

### ❌ DON'T
- No eliminar sin confirmación del usuario
- No asumir que la eliminación fue exitosa sin verificar status 204
- No exponer el botón "Eliminar Todos" sin restricciones
- No ignorar errores de validación de UUIDs

---

## 🔒 Consideraciones de Seguridad

1. **Validación Frontend**: Verificar permisos antes de mostrar botones de eliminación
2. **Confirmación Doble**: Especialmente para eliminación masiva
3. **Logging**: Registrar eliminaciones masivas para auditoría
4. **Rate Limiting**: Implementar throttling en el frontend para evitar clicks accidentales repetidos
