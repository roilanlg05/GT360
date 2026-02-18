# Drivers Endpoint - Frontend Integration Guide

## Overview

Este endpoint permite obtener la lista de drivers de una organizacion con filtros opcionales.

---

## Endpoint

```
GET /v1/organizations/{organization_id}/drivers
```

### Autenticacion
- Requiere token JWT valido
- Solo usuarios con rol `manager` pueden acceder

---

## Parametros

### Path Parameters

| Parametro | Tipo | Requerido | Descripcion |
|-----------|------|-----------|-------------|
| `organization_id` | UUID | **Si** | ID de la organizacion |

### Query Parameters

| Parametro | Tipo | Requerido | Valores | Descripcion |
|-----------|------|-----------|---------|-------------|
| `location_id` | UUID | No | - | Filtrar drivers por location |
| `pay_type` | string | No | `day`, `hour`, `trip` | Filtrar por tipo de pago |
| `driver_id` | UUID | No | - | Obtener info completa de un driver especifico |
| `name` | string | No | - | Buscar por nombre (case-insensitive, partial match) |
| `is_active` | boolean | No | `true`, `false` | Filtrar por estado activo/inactivo |

---

## Response

### Success Response (200)

```json
{
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "first_name": "John",
      "last_name": "Doe",
      "email": "john.doe@example.com",
      "phone": "+15028306579",
      "profile_pic": "https://example.com/pic.jpg",
      "is_active": true,
      "pay_type": "day",
      "pay_frequency": "weekly",
      "rate": 120.00,
      "location_id": "660e8400-e29b-41d4-a716-446655440001",
      "organization_id": "770e8400-e29b-41d4-a716-446655440002",
      "shift_start_time": "08:00",
      "shift_end_time": "20:00",
      "work_days": ["mon", "tue", "wed", "thu", "fri"],
      "created_at": "2026-01-23T10:30:00"
    }
  ],
  "total": 1
}
```

### Response Fields

| Campo | Tipo | Nullable | Descripcion |
|-------|------|----------|-------------|
| `data` | array | No | Array de drivers |
| `total` | integer | No | Total de drivers retornados |

### Driver Object Fields

| Campo | Tipo | Nullable | Descripcion |
|-------|------|----------|-------------|
| `id` | string (UUID) | No | ID unico del driver |
| `first_name` | string | Si | Nombre del driver |
| `last_name` | string | Si | Apellido del driver |
| `email` | string | No | Email del driver |
| `phone` | string | Si | Telefono del driver |
| `profile_pic` | string | Si | URL de la foto de perfil |
| `is_active` | boolean | No | Estado activo/inactivo |
| `pay_type` | string | Si | Tipo de pago: `day`, `hour`, `trip` |
| `pay_frequency` | string | Si | Frecuencia de pago: `daily`, `weekly`, `biweekly` |
| `rate` | number | Si | Tarifa de pago |
| `location_id` | string (UUID) | Si | ID de la location asignada |
| `organization_id` | string (UUID) | Si | ID de la organizacion |
| `shift_start_time` | string (HH:MM) | Si | Hora de inicio del turno programado |
| `shift_end_time` | string (HH:MM) | Si | Hora de fin del turno programado |
| `work_days` | array of strings | Si | Dias de la semana que trabaja |
| `created_at` | string (ISO 8601) | Si | Fecha de creacion |

---

## Error Responses

### 400 Bad Request
```json
{
  "detail": "Invalid pay_type. Must be one of: day, hour, trip"
}
```

### 401 Unauthorized
```json
{
  "detail": "Missing or invalid authentication"
}
```

### 403 Forbidden
```json
{
  "detail": "You don't have permission to access this organization's drivers"
}
```

### 404 Not Found
```json
{
  "detail": "Organization not found"
}
```

---

## Frontend Implementation

### TypeScript Interfaces

```typescript
interface Driver {
  id: string;
  first_name: string | null;
  last_name: string | null;
  email: string;
  phone: string | null;
  profile_pic: string | null;
  is_active: boolean;
  pay_type: 'day' | 'hour' | 'trip' | null;
  pay_frequency: 'daily' | 'weekly' | 'biweekly' | null;
  rate: number | null;
  location_id: string | null;
  organization_id: string | null;
  shift_start_time: string | null;  // "HH:MM" or null
  shift_end_time: string | null;    // "HH:MM" or null
  work_days: string[] | null;       // e.g. ["mon","tue","wed","thu","fri"]
  created_at: string | null;
}

interface DriversResponse {
  data: Driver[];
  total: number;
}

interface DriversFilters {
  location_id?: string;
  pay_type?: 'day' | 'hour' | 'trip';
  driver_id?: string;
  name?: string;
  is_active?: boolean;
}
```

### API Service

```typescript
const API_BASE = 'https://api.gt360.app';

async function getDrivers(
  organizationId: string,
  filters: DriversFilters = {},
  token: string
): Promise<DriversResponse> {
  const params = new URLSearchParams();

  if (filters.location_id) params.append('location_id', filters.location_id);
  if (filters.pay_type) params.append('pay_type', filters.pay_type);
  if (filters.driver_id) params.append('driver_id', filters.driver_id);
  if (filters.name) params.append('name', filters.name);
  if (filters.is_active !== undefined) params.append('is_active', String(filters.is_active));

  const queryString = params.toString();
  const url = `${API_BASE}/v1/organizations/${organizationId}/drivers${queryString ? `?${queryString}` : ''}`;

  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to fetch drivers');
  }

  return response.json();
}
```

### React Hook Example

```typescript
import { useState, useEffect, useCallback } from 'react';
import { useDebounce } from '@/hooks/useDebounce';

interface UseDriversOptions {
  organizationId: string;
  token: string;
  initialFilters?: DriversFilters;
}

function useDrivers({ organizationId, token, initialFilters = {} }: UseDriversOptions) {
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<DriversFilters>(initialFilters);

  // Debounce name search to avoid excessive API calls
  const debouncedName = useDebounce(filters.name, 300);

  const fetchDrivers = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const filtersWithDebouncedName = {
        ...filters,
        name: debouncedName,
      };

      const response = await getDrivers(organizationId, filtersWithDebouncedName, token);
      setDrivers(response.data);
      setTotal(response.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [organizationId, token, filters, debouncedName]);

  useEffect(() => {
    fetchDrivers();
  }, [fetchDrivers]);

  const updateFilter = (key: keyof DriversFilters, value: any) => {
    setFilters(prev => ({ ...prev, [key]: value }));
  };

  const clearFilters = () => {
    setFilters({});
  };

  return {
    drivers,
    total,
    loading,
    error,
    filters,
    updateFilter,
    clearFilters,
    refetch: fetchDrivers,
  };
}
```

### Component Example

```tsx
function DriversPage() {
  const { organizationId } = useAuth();
  const token = getAccessToken();

  const {
    drivers,
    total,
    loading,
    error,
    filters,
    updateFilter,
    clearFilters,
  } = useDrivers({ organizationId, token });

  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold mb-4">Drivers ({total})</h1>

      {/* Filters */}
      <div className="flex gap-4 mb-4">
        {/* Name Search with Debounce */}
        <input
          type="text"
          placeholder="Search by name..."
          value={filters.name || ''}
          onChange={(e) => updateFilter('name', e.target.value)}
          className="border rounded px-3 py-2"
        />

        {/* Pay Type Filter */}
        <select
          value={filters.pay_type || ''}
          onChange={(e) => updateFilter('pay_type', e.target.value || undefined)}
          className="border rounded px-3 py-2"
        >
          <option value="">All Pay Types</option>
          <option value="day">Day</option>
          <option value="hour">Hour</option>
          <option value="trip">Trip</option>
        </select>

        {/* Active/Inactive Filter */}
        <select
          value={filters.is_active === undefined ? '' : String(filters.is_active)}
          onChange={(e) => {
            const value = e.target.value;
            updateFilter('is_active', value === '' ? undefined : value === 'true');
          }}
          className="border rounded px-3 py-2"
        >
          <option value="">All Status</option>
          <option value="true">Active</option>
          <option value="false">Inactive</option>
        </select>

        <button onClick={clearFilters} className="px-4 py-2 bg-gray-200 rounded">
          Clear Filters
        </button>
      </div>

      {/* Loading State */}
      {loading && <div>Loading...</div>}

      {/* Error State */}
      {error && <div className="text-red-500">{error}</div>}

      {/* Drivers Table */}
      {!loading && !error && (
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-gray-100">
              <th className="border p-2 text-left">Name</th>
              <th className="border p-2 text-left">Email</th>
              <th className="border p-2 text-left">Phone</th>
              <th className="border p-2 text-left">Pay Type</th>
              <th className="border p-2 text-left">Status</th>
            </tr>
          </thead>
          <tbody>
            {drivers.map((driver) => (
              <tr key={driver.id}>
                <td className="border p-2">
                  {driver.first_name} {driver.last_name}
                </td>
                <td className="border p-2">{driver.email}</td>
                <td className="border p-2">{driver.phone || '-'}</td>
                <td className="border p-2">
                  {driver.pay_type ? driver.pay_type.toUpperCase() : '-'}
                </td>
                <td className="border p-2">
                  <span className={driver.is_active ? 'text-green-600' : 'text-red-600'}>
                    {driver.is_active ? 'Active' : 'Inactive'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Empty State */}
      {!loading && !error && drivers.length === 0 && (
        <div className="text-gray-500 text-center py-8">
          No drivers found
        </div>
      )}
    </div>
  );
}
```

---

## Usage Examples

### Get all active drivers
```bash
curl -X GET "https://api.gt360.app/v1/organizations/{org_id}/drivers?is_active=true" \
  -H "Authorization: Bearer {token}"
```

### Filter by pay type
```bash
curl -X GET "https://api.gt360.app/v1/organizations/{org_id}/drivers?pay_type=day" \
  -H "Authorization: Bearer {token}"
```

### Search by name
```bash
curl -X GET "https://api.gt360.app/v1/organizations/{org_id}/drivers?name=john" \
  -H "Authorization: Bearer {token}"
```

### Get specific driver
```bash
curl -X GET "https://api.gt360.app/v1/organizations/{org_id}/drivers?driver_id={driver_uuid}" \
  -H "Authorization: Bearer {token}"
```

### Combine multiple filters
```bash
curl -X GET "https://api.gt360.app/v1/organizations/{org_id}/drivers?is_active=true&pay_type=hour&location_id={loc_id}" \
  -H "Authorization: Bearer {token}"
```

---

## Database Schema

### Table: `entities.drivers`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | UUID | No | PK, FK to `entities.users.id` |
| `is_active` | boolean | No | Default: false |
| `point` | JSONB | Yes | GPS location |
| `location_id` | UUID | Yes | FK to `entities.locations.id` |
| `organization_id` | UUID | Yes | FK to `entities.organizations.id` |
| `pay_type` | VARCHAR(10) | Yes | Values: day, hour, trip |
| `pay_frequency` | VARCHAR(20) | Yes | Values: daily, weekly, biweekly |
| `rate` | DECIMAL | Yes | Pay rate |
| `profile_pic_url` | VARCHAR | Yes | Profile picture URL |
| `shift_start_time` | TIME | Yes | Scheduled shift start time |
| `shift_end_time` | TIME | Yes | Scheduled shift end time |
| `work_days` | JSONB | Yes | Array of day abbreviations, e.g. ["mon","tue","wed","thu","fri"] |

### Migration SQL

```sql
-- Add pay_type column if not exists
ALTER TABLE entities.drivers
ADD COLUMN IF NOT EXISTS pay_type VARCHAR(10) DEFAULT NULL;

-- Create index for better query performance
CREATE INDEX IF NOT EXISTS idx_drivers_pay_type ON entities.drivers(pay_type);
```

---

## Notes

1. **Name Search**: El parametro `name` usa ILIKE para busqueda case-insensitive y partial match
2. **Debouncing**: Se recomienda implementar debouncing (300ms) en el frontend para el campo de busqueda por nombre
3. **Performance**: Los resultados estan ordenados por `created_at` descendente (mas recientes primero)
4. **Authorization**: El endpoint verifica que el usuario pertenezca a la organizacion solicitada

---

# Sistema de Restablecimiento de Contraseña (Password Reset)

## Overview

Sistema completo de password reset para drivers. Permite a los drivers restablecer su contraseña mediante un link enviado por email.

---

## Endpoints

### 1. Solicitar Reset de Contraseña

```
POST /v1/auth/forgot-password
```

**Autenticación:** No requerida (público)

#### Query Parameters

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `email` | string | **Sí** | Email del usuario |

#### Ejemplo de Request

```bash
POST /v1/auth/forgot-password?email=driver@example.com
```

#### Response Success (200 OK)

```json
{
  "content": "If the email exists, you will receive a password reset link",
  "status_code": 200
}
```

**Nota de Seguridad:** Siempre retorna 200 incluso si el email no existe (previene enumeración de usuarios).

#### Comportamiento

1. Backend valida que el email exista y esté verificado
2. Genera un token JWT que expira en 30 minutos
3. Envía email automáticamente con link de reset
4. Link formato: `https://dev.gt360.app/reset?token=<JWT_TOKEN>`

---

### 2. Confirmar Nueva Contraseña

```
POST /v1/auth/reset-password
```

**Autenticación:** No requerida (token en body)

#### Request Body

```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "password": {
    "new_password": "NewSecurePassword123!"
  }
}
```

#### Response Success (200 OK)

```json
{
  "message": "Password updated. Sign in again."
}
```

#### Error Responses

| Código | Descripción | Mensaje |
|--------|-------------|---------|
| `400` | Token ya utilizado | `"Token already used or invalid"` |
| `400` | Contraseña débil | `"Password must contain at least 8 characters..."` |
| `403` | Token inválido/expirado | `"Invalid or expired token"` |
| `409` | Password igual a anterior | `"The new password must be different..."` |

---

### 3. Cambiar Contraseña (Usuarios Autenticados)

```
PUT /v1/auth/change-password
```

**Autenticación:** Requerida (Access Token)

#### Request Headers

```
Authorization: Bearer {access_token}
Content-Type: application/json
```

#### Request Body

```json
{
  "current_password": "CurrentPassword123!",
  "new_password": "NewPassword123!"
}
```

#### Response Success (200 OK)

```json
{
  "message": "Password reset successful. Please sign in again with your new password."
}
```

#### Error Responses

| Código | Descripción | Mensaje |
|--------|-------------|---------|
| `403` | Contraseña actual incorrecta | `"Incorrect current password"` |
| `409` | Password igual a anterior | `"The new password must be different..."` |

---

## Requisitos de Contraseña

**La contraseña debe contener:**
- ✅ Mínimo 8 caracteres
- ✅ Al menos 1 letra mayúscula (A-Z)
- ✅ Al menos 1 letra minúscula (a-z)
- ✅ Al menos 1 número (0-9)
- ✅ Al menos 1 carácter especial (!@#$%^&*()_+-=[]{}|;:,.<>?)

---

## Implementación Móvil - Password Reset

### TypeScript/Kotlin/Swift Types

```typescript
// TypeScript
interface ForgotPasswordRequest {
  email: string;
}

interface ResetPasswordRequest {
  token: string;
  password: {
    new_password: string;
  };
}

interface PasswordResetResponse {
  message: string;
}
```

```kotlin
// Kotlin
data class ForgotPasswordRequest(
    val email: String
)

data class ResetPasswordRequest(
    val token: String,
    val password: PasswordData
) {
    data class PasswordData(
        val new_password: String
    )
}

data class PasswordResetResponse(
    val message: String
)
```

```swift
// Swift
struct ForgotPasswordRequest: Codable {
    let email: String
}

struct ResetPasswordRequest: Codable {
    let token: String
    let password: PasswordData

    struct PasswordData: Codable {
        let new_password: String
    }
}

struct PasswordResetResponse: Codable {
    let message: String
}
```

### Validación de Contraseña (Client-Side)

```kotlin
// Kotlin
fun validatePassword(password: String): PasswordValidation {
    val hasMinLength = password.length >= 8
    val hasUppercase = password.any { it.isUpperCase() }
    val hasLowercase = password.any { it.isLowerCase() }
    val hasNumber = password.any { it.isDigit() }
    val hasSpecialChar = password.any { !it.isLetterOrDigit() }

    return PasswordValidation(
        isValid = hasMinLength && hasUppercase && hasLowercase && hasNumber && hasSpecialChar,
        errors = buildList {
            if (!hasMinLength) add("Mínimo 8 caracteres")
            if (!hasUppercase) add("Al menos una mayúscula")
            if (!hasLowercase) add("Al menos una minúscula")
            if (!hasNumber) add("Al menos un número")
            if (!hasSpecialChar) add("Al menos un carácter especial")
        }
    )
}
```

```swift
// Swift
func validatePassword(_ password: String) -> PasswordValidation {
    let hasMinLength = password.count >= 8
    let hasUppercase = password.range(of: "[A-Z]", options: .regularExpression) != nil
    let hasLowercase = password.range(of: "[a-z]", options: .regularExpression) != nil
    let hasNumber = password.range(of: "[0-9]", options: .regularExpression) != nil
    let hasSpecialChar = password.range(of: "[^A-Za-z0-9]", options: .regularExpression) != nil

    var errors: [String] = []
    if !hasMinLength { errors.append("Mínimo 8 caracteres") }
    if !hasUppercase { errors.append("Al menos una mayúscula") }
    if !hasLowercase { errors.append("Al menos una minúscula") }
    if !hasNumber { errors.append("Al menos un número") }
    if !hasSpecialChar { errors.append("Al menos un carácter especial") }

    return PasswordValidation(
        isValid: errors.isEmpty,
        errors: errors
    )
}
```

### Deep Linking para Reset Password

#### Android (AndroidManifest.xml)

```xml
<activity android:name=".ResetPasswordActivity">
    <intent-filter android:autoVerify="true">
        <action android:name="android.intent.action.VIEW" />
        <category android:name="android.intent.category.DEFAULT" />
        <category android:name="android.intent.category.BROWSABLE" />

        <!-- Custom Scheme -->
        <data android:scheme="gt360" android:host="reset-password" />

        <!-- Universal Link -->
        <data android:scheme="https" android:host="dev.gt360.app" android:pathPrefix="/reset" />
    </intent-filter>
</activity>
```

#### iOS (Info.plist)

```xml
<key>CFBundleURLTypes</key>
<array>
    <dict>
        <key>CFBundleURLSchemes</key>
        <array>
            <string>gt360</string>
        </array>
    </dict>
</array>

<key>com.apple.developer.associated-domains</key>
<array>
    <string>applinks:dev.gt360.app</string>
</array>
```

### Flujo Completo

```
1. Driver toca "¿Olvidaste tu contraseña?" en Login
   ↓
2. Ingresa su email → POST /v1/auth/forgot-password
   ↓
3. Mensaje: "Revisa tu email"
   ↓
4. Driver recibe email con link (expira en 30 min)
   ↓
5. Click en link → App captura deep link con token
   ↓
6. Pantalla de reset: ingresa nueva contraseña
   ↓
7. POST /v1/auth/reset-password con token + password
   ↓
8. Éxito → Redirect a Login
   ↓
9. Driver hace login con nueva contraseña
```

---

# Sistema de Contacto a Soporte

## Overview

Sistema para que drivers contacten al equipo de soporte. Envía emails automáticamente a `admin@gt360.app`.

---

## Endpoint

```
POST /v1/support/contact
```

**Autenticación:** No requerida (público)

---

## Request Body

```json
{
  "name": "Juan González",
  "email": "juan.driver@example.com",
  "category": "bug",
  "subject": "Error al crear viaje",
  "message": "Cuando intento crear un viaje desde la app, obtengo un error 500. Esto ocurre cuando selecciono el aeropuerto de Louisville."
}
```

### Request Schema

| Campo | Tipo | Requerido | Descripción | Ejemplo |
|-------|------|-----------|-------------|---------|
| `name` | string | Sí | Nombre del driver | `"Juan González"` |
| `email` | string | Sí | Email válido | `"juan@example.com"` |
| `category` | enum | Sí | Categoría del mensaje | `"bug"` |
| `subject` | string | Sí | Asunto | `"Error al crear viaje"` |
| `message` | string | Sí | Mensaje detallado | `"Descripción..."` |

### Categorías Disponibles

| Código | Display | Icono | Descripción |
|--------|---------|-------|-------------|
| `bug` | Reportar un error | 🐛 | Para reportar bugs |
| `feature` | Solicitar función | ✨ | Para solicitar features |
| `question` | Hacer pregunta | ❓ | Para preguntas |
| `other` | Otro | 📝 | Otros temas |

---

## Response Success (200 OK)

```json
{
  "success": true,
  "message": "Your message has been sent successfully"
}
```

---

## Error Responses

| Código | Descripción | Mensaje |
|--------|-------------|---------|
| `422` | Email inválido | `"value is not a valid email address"` |
| `422` | Campo faltante | `"field required"` |
| `422` | Categoría inválida | `"value is not a valid enumeration member"` |
| `500` | Error al enviar | `"Failed to send message. Please try again later."` |

---

## Implementación Móvil - Soporte

### TypeScript/Kotlin/Swift Types

```typescript
// TypeScript
interface SupportContactRequest {
  name: string;
  email: string;
  category: 'bug' | 'feature' | 'question' | 'other';
  subject: string;
  message: string;
}

interface SupportContactResponse {
  success: boolean;
  message: string;
}
```

```kotlin
// Kotlin
enum class SupportCategory(val value: String) {
    BUG("bug"),
    FEATURE("feature"),
    QUESTION("question"),
    OTHER("other")
}

data class SupportContactRequest(
    val name: String,
    val email: String,
    val category: String,
    val subject: String,
    val message: String
)

data class SupportContactResponse(
    val success: Boolean,
    val message: String
)
```

```swift
// Swift
enum SupportCategory: String, CaseIterable {
    case bug = "bug"
    case feature = "feature"
    case question = "question"
    case other = "other"

    var displayName: String {
        switch self {
        case .bug: return "🐛 Reportar un error"
        case .feature: return "✨ Solicitar una función"
        case .question: return "❓ Hacer una pregunta"
        case .other: return "📝 Otro"
        }
    }
}

struct SupportContactRequest: Codable {
    let name: String
    let email: String
    let category: String
    let subject: String
    let message: String
}

struct SupportContactResponse: Codable {
    let success: Bool
    let message: String
}
```

### API Call Example (Kotlin)

```kotlin
suspend fun sendSupportMessage(
    name: String,
    email: String,
    category: SupportCategory,
    subject: String,
    message: String
): Result<String> {
    return try {
        val request = SupportContactRequest(
            name = name,
            email = email,
            category = category.value,
            subject = subject,
            message = message
        )

        val response = httpClient.post("$BASE_URL/v1/support/contact") {
            contentType(ContentType.Application.Json)
            setBody(request)
        }

        if (response.status == HttpStatusCode.OK) {
            val body = response.body<SupportContactResponse>()
            Result.success(body.message)
        } else {
            Result.failure(Exception("Error ${response.status}"))
        }
    } catch (e: Exception) {
        Result.failure(e)
    }
}
```

### API Call Example (Swift)

```swift
func sendSupportMessage(
    name: String,
    email: String,
    category: SupportCategory,
    subject: String,
    message: String
) async throws -> String {
    let url = URL(string: "\(baseURL)/v1/support/contact")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")

    let body = SupportContactRequest(
        name: name,
        email: email,
        category: category.rawValue,
        subject: subject,
        message: message
    )
    request.httpBody = try JSONEncoder().encode(body)

    let (data, response) = try await URLSession.shared.data(for: request)

    guard let httpResponse = response as? HTTPURLResponse,
          httpResponse.statusCode == 200 else {
        throw SupportError.sendFailed
    }

    let result = try JSONDecoder().decode(SupportContactResponse.self, from: data)
    return result.message
}
```

### Validaciones Client-Side

```kotlin
// Kotlin
fun validateSupportForm(
    name: String,
    email: String,
    subject: String,
    message: String
): Map<String, String> {
    val errors = mutableMapOf<String, String>()

    if (name.isBlank()) errors["name"] = "El nombre es requerido"
    if (!isValidEmail(email)) errors["email"] = "Email inválido"
    if (subject.length < 5) errors["subject"] = "Mínimo 5 caracteres"
    if (message.length < 20) errors["message"] = "Mínimo 20 caracteres"

    return errors
}
```

```swift
// Swift
func validateSupportForm(
    name: String,
    email: String,
    subject: String,
    message: String
) -> [String: String] {
    var errors: [String: String] = [:]

    if name.isEmpty { errors["name"] = "El nombre es requerido" }
    if !isValidEmail(email) { errors["email"] = "Email inválido" }
    if subject.count < 5 { errors["subject"] = "Mínimo 5 caracteres" }
    if message.count < 20 { errors["message"] = "Mínimo 20 caracteres" }

    return errors
}
```

### Flujo UX Recomendado

```
1. Menú/Settings → "Ayuda y Soporte"
   ↓
2. Pantalla de Soporte:
   - Input: Nombre (pre-fill si está logueado)
   - Input: Email (pre-fill si está logueado)
   - Selector: Categoría (bug/feature/question/other)
   - Input: Asunto
   - TextArea: Mensaje
   - Botón: "Enviar Mensaje"
   ↓
3. Validar campos client-side
   ↓
4. POST /v1/support/contact
   ↓
5. Mostrar éxito: "¡Mensaje enviado!"
   ↓
6. Limpiar formulario o volver atrás
   ↓
7. Email enviado automáticamente a admin@gt360.app
   ↓
8. Equipo responde por email directo al driver
```

---

## Ejemplo CURL

### Forgot Password
```bash
curl -X POST "https://api.gt360.app/v1/auth/forgot-password?email=driver@example.com"
```

### Reset Password
```bash
curl -X POST "https://api.gt360.app/v1/auth/reset-password" \
  -H "Content-Type: application/json" \
  -d '{
    "token": "eyJhbGci...",
    "password": {"new_password": "NewPass123!"}
  }'
```

### Contact Support
```bash
curl -X POST "https://api.gt360.app/v1/support/contact" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Juan González",
    "email": "juan@example.com",
    "category": "bug",
    "subject": "Error en la app",
    "message": "Descripción detallada del problema..."
  }'
```

---

## Notas Importantes

### Password Reset
- Token de reset expira en **30 minutos**
- Token es de **un solo uso** (no reutilizable)
- Todos los refresh tokens se revocan al cambiar password
- Solo usuarios con **email verificado** pueden hacer reset

### Support Contact
- Endpoint es **público** (no requiere login)
- Email enviado a `admin@gt360.app`
- Reply-to configurado al email del driver
- Sin límite de caracteres en mensaje (pero recomienda min 20)

---

**Última actualización:** 2026-02-07
