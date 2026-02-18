# Manager Profile - Frontend Implementation Guide

**Fecha:** 2026-02-03
**Backend Version:** dev
**Base URL (dev):** `https://dev.gt360.app` (puerto 8001)
**Base URL (prod):** `https://api.gt360.app` (puerto 8000)

---

## Resumen

Esta guía documenta los endpoints para implementar la pantalla de **Settings/Profile** del manager en el frontend. Permite al manager ver y editar su perfil, subir foto, y ver información de su organización.

---

## Endpoints Disponibles

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/v1/profile/manager` | Obtener perfil completo |
| PATCH | `/v1/profile/manager` | Actualizar campos del perfil |
| POST | `/v1/profile/manager/upload-photo` | Subir foto de perfil |
| PUT | `/v1/auth/change-password` | Cambiar contraseña (existente) |

---

## 1. Obtener Perfil del Manager

### Request

```http
GET /v1/profile/manager
Authorization: Bearer <access_token>
```

### Response (200 OK)

```typescript
interface ManagerProfileResponse {
  // Datos del usuario
  id: string;                        // UUID del manager
  profile_pic: string | null;        // URL de la foto de perfil
  manager_name: string;              // "John Doe" (first_name + last_name)
  email: string;                     // "john@company.com"
  phone: string | null;              // "+1234567890"
  created_at: string;                // ISO 8601: "2024-01-15T10:30:00Z"

  // Datos de la organización
  organization_id: string;           // UUID de la organización
  organization_name: string;         // "Acme Transport"
  organization_address: string | null; // "123 Main St, NYC"
  organization_website: string | null; // "https://acmetransport.com"
  membership_status: string;         // "freemium" | "pro" | "enterprise"

  // Locations asociadas
  locations: LocationInfo[];
}

interface LocationInfo {
  id: string;                        // UUID de la location
  name: string;                      // "JFK Airport"
  address: string | null;            // "JFK, Queens, NY"
  timezone: string;                  // "America/New_York"
}
```

### Ejemplo de Response

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "profile_pic": "https://api.gt360.app/uploads/profiles/550e8400.../20240115_abc123.jpg",
  "manager_name": "John Doe",
  "email": "john@acmetransport.com",
  "phone": "+15551234567",
  "created_at": "2024-01-15T10:30:00Z",
  "organization_id": "660e8400-e29b-41d4-a716-446655440001",
  "organization_name": "Acme Transport",
  "organization_address": "123 Main St, New York, NY 10001",
  "organization_website": "https://acmetransport.com",
  "membership_status": "pro",
  "locations": [
    {
      "id": "770e8400-e29b-41d4-a716-446655440002",
      "name": "JFK International Airport",
      "address": "JFK Access Rd, Queens, NY 11430",
      "timezone": "America/New_York"
    },
    {
      "id": "880e8400-e29b-41d4-a716-446655440003",
      "name": "LaGuardia Airport",
      "address": "LaGuardia Rd, Queens, NY 11371",
      "timezone": "America/New_York"
    }
  ]
}
```

### Errores

| Status | Detalle | Causa |
|--------|---------|-------|
| 401 | "Missing authentication token" | No se envió el token |
| 401 | "Token expired" | Token expirado |
| 403 | "Access denied" | Usuario no es manager |
| 404 | "Perfil de manager no encontrado..." | Cuenta mal configurada |

---

## 2. Actualizar Perfil del Manager

### Request

```http
PATCH /v1/profile/manager
Authorization: Bearer <access_token>
Content-Type: application/json
```

### Body (solo enviar campos a actualizar)

```typescript
interface ManagerProfileUpdate {
  // Campos personales
  first_name?: string;              // min 1, max 100 caracteres
  last_name?: string;               // min 1, max 100 caracteres
  phone?: string;                   // formato: +1XXXXXXXXXX (8-15 dígitos)

  // Campos de organización
  organization_name?: string;       // min 1, max 200 caracteres
  organization_address?: string;    // max 500 caracteres
  organization_website?: string;    // debe comenzar con http:// o https://
}
```

### Ejemplos de Request

**Actualizar nombre:**
```json
{
  "first_name": "Jonathan",
  "last_name": "Smith"
}
```

**Actualizar teléfono:**
```json
{
  "phone": "+15559876543"
}
```

**Actualizar datos de organización:**
```json
{
  "organization_name": "Acme Transport LLC",
  "organization_address": "456 Broadway, New York, NY 10013",
  "organization_website": "https://www.acmetransport.com"
}
```

**Actualizar múltiples campos:**
```json
{
  "first_name": "Jonathan",
  "phone": "+15559876543",
  "organization_website": "https://newsite.com"
}
```

### Response (200 OK)

Retorna el perfil completo actualizado (mismo formato que GET).

### Validaciones

| Campo | Validación | Error |
|-------|------------|-------|
| `first_name` | 1-100 caracteres | "String should have at least 1 character" |
| `last_name` | 1-100 caracteres | "String should have at least 1 character" |
| `phone` | 8-15 dígitos, formato E.164 | "Telefono debe tener entre 8 y 15 digitos" |
| `organization_name` | 1-200 caracteres | "String should have at least 1 character" |
| `organization_address` | max 500 caracteres | "String should have at most 500 characters" |
| `organization_website` | debe empezar con http(s):// | "Website debe comenzar con http:// o https://" |

### Errores

| Status | Detalle | Causa |
|--------|---------|-------|
| 400 | "ID de usuario invalido" | Token corrupto |
| 404 | "Perfil de manager no encontrado" | Usuario no existe |
| 422 | Validation Error | Campos inválidos |

---

## 3. Subir Foto de Perfil

### Request

```http
POST /v1/profile/manager/upload-photo
Authorization: Bearer <access_token>
Content-Type: multipart/form-data
```

### Form Data

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `file` | File | Sí | Imagen de perfil |

### Restricciones

| Restricción | Valor |
|-------------|-------|
| Formatos permitidos | JPEG, PNG, WebP, GIF |
| Tamaño máximo | **4 MB** |
| Content-Types | `image/jpeg`, `image/png`, `image/webp`, `image/gif` |

### Response (200 OK)

```typescript
interface ProfilePhotoUploadResponse {
  profile_pic_url: string;  // URL pública de la imagen
  message: string;          // "Foto de perfil actualizada correctamente"
}
```

### Ejemplo de Response

```json
{
  "profile_pic_url": "https://api.gt360.app/uploads/profiles/550e8400.../20240203_abc12345.jpg",
  "message": "Foto de perfil actualizada correctamente"
}
```

### Errores

| Status | Detalle | Causa |
|--------|---------|-------|
| 400 | "No se proporciono archivo" | Campo `file` vacío |
| 400 | "Tipo de archivo no permitido..." | Formato no soportado |
| 400 | "El archivo excede el tamano maximo de 4 MB" | Archivo muy grande |
| 500 | "Error al subir la imagen" | Error interno |

---

## 4. Cambiar Contraseña

Este endpoint ya existe en el sistema de auth.

### Request

```http
PUT /v1/auth/change-password
Authorization: Bearer <access_token>
Content-Type: application/json
```

### Body

```typescript
interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}
```

### Validaciones de Contraseña

La nueva contraseña debe cumplir:
- Mínimo 8 caracteres
- Al menos 1 letra mayúscula
- Al menos 1 letra minúscula
- Al menos 1 dígito
- Al menos 1 carácter especial: `!@#$%^&*()_=+[]{};:,.<>?/\|~\`-'"`

### Response (200 OK)

```json
{
  "message": "Contraseña actualizada correctamente"
}
```

### Errores

| Status | Detalle | Causa |
|--------|---------|-------|
| 400 | "Contraseña actual incorrecta" | Password incorrecto |
| 422 | "Password must contain..." | No cumple requisitos |

---

## Implementación React/TypeScript

### Types

```typescript
// types/profile.ts

export interface LocationInfo {
  id: string;
  name: string;
  address: string | null;
  timezone: string;
}

export interface ManagerProfile {
  id: string;
  profile_pic: string | null;
  manager_name: string;
  email: string;
  phone: string | null;
  created_at: string;
  organization_id: string;
  organization_name: string;
  organization_address: string | null;
  organization_website: string | null;
  membership_status: 'freemium' | 'pro' | 'enterprise';
  locations: LocationInfo[];
}

export interface ManagerProfileUpdate {
  first_name?: string;
  last_name?: string;
  phone?: string;
  organization_name?: string;
  organization_address?: string;
  organization_website?: string;
}

export interface PhotoUploadResponse {
  profile_pic_url: string;
  message: string;
}
```

### API Service

```typescript
// services/profileApi.ts

import { api } from './api'; // tu instancia de axios/fetch
import type {
  ManagerProfile,
  ManagerProfileUpdate,
  PhotoUploadResponse
} from '../types/profile';

export const profileApi = {
  /**
   * Obtener perfil completo del manager
   */
  getManagerProfile: async (): Promise<ManagerProfile> => {
    const response = await api.get('/v1/profile/manager');
    return response.data;
  },

  /**
   * Actualizar campos del perfil
   * Solo enviar campos que se quieren actualizar
   */
  updateManagerProfile: async (
    data: ManagerProfileUpdate
  ): Promise<ManagerProfile> => {
    const response = await api.patch('/v1/profile/manager', data);
    return response.data;
  },

  /**
   * Subir foto de perfil
   * @param file - Archivo de imagen (max 4MB, formatos: jpg, png, webp, gif)
   */
  uploadProfilePhoto: async (file: File): Promise<PhotoUploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await api.post('/v1/profile/manager/upload-photo', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  /**
   * Cambiar contraseña
   */
  changePassword: async (
    currentPassword: string,
    newPassword: string
  ): Promise<void> => {
    await api.put('/v1/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
  },
};
```

### React Query Hooks

```typescript
// hooks/useManagerProfile.ts

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { profileApi } from '../services/profileApi';
import type { ManagerProfileUpdate } from '../types/profile';

const PROFILE_KEY = ['manager-profile'];

/**
 * Hook para obtener el perfil del manager
 */
export function useManagerProfile() {
  return useQuery({
    queryKey: PROFILE_KEY,
    queryFn: profileApi.getManagerProfile,
    staleTime: 5 * 60 * 1000, // 5 minutos
  });
}

/**
 * Hook para actualizar el perfil
 */
export function useUpdateProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ManagerProfileUpdate) =>
      profileApi.updateManagerProfile(data),
    onSuccess: (updatedProfile) => {
      // Actualizar cache inmediatamente
      queryClient.setQueryData(PROFILE_KEY, updatedProfile);
    },
  });
}

/**
 * Hook para subir foto de perfil
 */
export function useUploadProfilePhoto() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (file: File) => profileApi.uploadProfilePhoto(file),
    onSuccess: (response) => {
      // Actualizar la URL de la foto en el cache
      queryClient.setQueryData(PROFILE_KEY, (old: any) => ({
        ...old,
        profile_pic: response.profile_pic_url,
      }));
    },
  });
}

/**
 * Hook para cambiar contraseña
 */
export function useChangePassword() {
  return useMutation({
    mutationFn: ({ currentPassword, newPassword }: {
      currentPassword: string;
      newPassword: string;
    }) => profileApi.changePassword(currentPassword, newPassword),
  });
}
```

### Componente de Ejemplo

```tsx
// components/ManagerSettings.tsx

import { useState } from 'react';
import {
  useManagerProfile,
  useUpdateProfile,
  useUploadProfilePhoto,
  useChangePassword
} from '../hooks/useManagerProfile';

export function ManagerSettings() {
  const { data: profile, isLoading, error } = useManagerProfile();
  const updateProfile = useUpdateProfile();
  const uploadPhoto = useUploadProfilePhoto();
  const changePassword = useChangePassword();

  const [isEditing, setIsEditing] = useState(false);
  const [formData, setFormData] = useState({
    first_name: '',
    last_name: '',
    phone: '',
    organization_name: '',
    organization_address: '',
    organization_website: '',
  });

  if (isLoading) return <div>Cargando perfil...</div>;
  if (error) return <div>Error al cargar perfil</div>;
  if (!profile) return null;

  // Inicializar form cuando se abre edición
  const startEditing = () => {
    const [firstName, ...lastNameParts] = profile.manager_name.split(' ');
    setFormData({
      first_name: firstName || '',
      last_name: lastNameParts.join(' ') || '',
      phone: profile.phone || '',
      organization_name: profile.organization_name,
      organization_address: profile.organization_address || '',
      organization_website: profile.organization_website || '',
    });
    setIsEditing(true);
  };

  const handleSave = async () => {
    try {
      await updateProfile.mutateAsync(formData);
      setIsEditing(false);
    } catch (err) {
      console.error('Error updating profile:', err);
    }
  };

  const handlePhotoChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Validar tamaño (4MB)
    if (file.size > 4 * 1024 * 1024) {
      alert('La imagen no puede superar 4MB');
      return;
    }

    // Validar tipo
    const allowedTypes = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];
    if (!allowedTypes.includes(file.type)) {
      alert('Formato no permitido. Use JPG, PNG, WebP o GIF');
      return;
    }

    try {
      await uploadPhoto.mutateAsync(file);
    } catch (err) {
      console.error('Error uploading photo:', err);
    }
  };

  return (
    <div className="manager-settings">
      {/* Header con foto */}
      <div className="profile-header">
        <div className="avatar-container">
          {profile.profile_pic ? (
            <img
              src={profile.profile_pic}
              alt="Profile"
              className="avatar"
            />
          ) : (
            <div className="avatar-placeholder">
              {profile.manager_name.charAt(0).toUpperCase()}
            </div>
          )}
          <label className="upload-btn">
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              onChange={handlePhotoChange}
              hidden
            />
            {uploadPhoto.isPending ? 'Subiendo...' : 'Cambiar foto'}
          </label>
        </div>
        <div className="profile-info">
          <h1>{profile.manager_name}</h1>
          <p className="email">{profile.email}</p>
          <span className={`badge badge-${profile.membership_status}`}>
            {profile.membership_status.toUpperCase()}
          </span>
        </div>
      </div>

      {/* Datos personales */}
      <section className="section">
        <h2>Datos Personales</h2>
        {isEditing ? (
          <div className="form-grid">
            <div className="form-group">
              <label>Nombre</label>
              <input
                type="text"
                value={formData.first_name}
                onChange={e => setFormData(f => ({...f, first_name: e.target.value}))}
              />
            </div>
            <div className="form-group">
              <label>Apellido</label>
              <input
                type="text"
                value={formData.last_name}
                onChange={e => setFormData(f => ({...f, last_name: e.target.value}))}
              />
            </div>
            <div className="form-group">
              <label>Teléfono</label>
              <input
                type="tel"
                value={formData.phone}
                onChange={e => setFormData(f => ({...f, phone: e.target.value}))}
                placeholder="+1 (555) 123-4567"
              />
            </div>
          </div>
        ) : (
          <div className="info-grid">
            <div className="info-item">
              <span className="label">Nombre</span>
              <span className="value">{profile.manager_name}</span>
            </div>
            <div className="info-item">
              <span className="label">Email</span>
              <span className="value">{profile.email}</span>
            </div>
            <div className="info-item">
              <span className="label">Teléfono</span>
              <span className="value">{profile.phone || 'No especificado'}</span>
            </div>
            <div className="info-item">
              <span className="label">Miembro desde</span>
              <span className="value">
                {new Date(profile.created_at).toLocaleDateString()}
              </span>
            </div>
          </div>
        )}
      </section>

      {/* Datos de organización */}
      <section className="section">
        <h2>Organización</h2>
        {isEditing ? (
          <div className="form-grid">
            <div className="form-group">
              <label>Nombre de la organización</label>
              <input
                type="text"
                value={formData.organization_name}
                onChange={e => setFormData(f => ({...f, organization_name: e.target.value}))}
              />
            </div>
            <div className="form-group">
              <label>Dirección</label>
              <input
                type="text"
                value={formData.organization_address}
                onChange={e => setFormData(f => ({...f, organization_address: e.target.value}))}
              />
            </div>
            <div className="form-group">
              <label>Website</label>
              <input
                type="url"
                value={formData.organization_website}
                onChange={e => setFormData(f => ({...f, organization_website: e.target.value}))}
                placeholder="https://example.com"
              />
            </div>
          </div>
        ) : (
          <div className="info-grid">
            <div className="info-item">
              <span className="label">Nombre</span>
              <span className="value">{profile.organization_name}</span>
            </div>
            <div className="info-item">
              <span className="label">Dirección</span>
              <span className="value">{profile.organization_address || 'No especificada'}</span>
            </div>
            <div className="info-item">
              <span className="label">Website</span>
              <span className="value">
                {profile.organization_website ? (
                  <a href={profile.organization_website} target="_blank" rel="noopener">
                    {profile.organization_website}
                  </a>
                ) : 'No especificado'}
              </span>
            </div>
            <div className="info-item">
              <span className="label">Plan</span>
              <span className="value">{profile.membership_status}</span>
            </div>
          </div>
        )}
      </section>

      {/* Locations */}
      <section className="section">
        <h2>Locations ({profile.locations.length})</h2>
        <div className="locations-list">
          {profile.locations.map(location => (
            <div key={location.id} className="location-card">
              <h3>{location.name}</h3>
              {location.address && <p>{location.address}</p>}
              <span className="timezone">{location.timezone}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Botones de acción */}
      <div className="actions">
        {isEditing ? (
          <>
            <button
              onClick={handleSave}
              disabled={updateProfile.isPending}
              className="btn-primary"
            >
              {updateProfile.isPending ? 'Guardando...' : 'Guardar cambios'}
            </button>
            <button onClick={() => setIsEditing(false)} className="btn-secondary">
              Cancelar
            </button>
          </>
        ) : (
          <button onClick={startEditing} className="btn-primary">
            Editar perfil
          </button>
        )}
      </div>

      {/* Sección de seguridad */}
      <section className="section">
        <h2>Seguridad</h2>
        <button
          onClick={() => {/* abrir modal de cambio de contraseña */}}
          className="btn-secondary"
        >
          Cambiar contraseña
        </button>
      </section>
    </div>
  );
}
```

### Modal de Cambio de Contraseña

```tsx
// components/ChangePasswordModal.tsx

import { useState } from 'react';
import { useChangePassword } from '../hooks/useManagerProfile';

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

export function ChangePasswordModal({ isOpen, onClose }: Props) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');

  const changePassword = useChangePassword();

  const validatePassword = (password: string): string | null => {
    if (password.length < 8) return 'Mínimo 8 caracteres';
    if (!/[A-Z]/.test(password)) return 'Debe contener mayúscula';
    if (!/[a-z]/.test(password)) return 'Debe contener minúscula';
    if (!/[0-9]/.test(password)) return 'Debe contener número';
    if (!/[!@#$%^&*()_=+\[\]{};:,.<>?/\\|~`\-'"]/.test(password)) {
      return 'Debe contener carácter especial';
    }
    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    // Validar coincidencia
    if (newPassword !== confirmPassword) {
      setError('Las contraseñas no coinciden');
      return;
    }

    // Validar requisitos
    const validationError = validatePassword(newPassword);
    if (validationError) {
      setError(validationError);
      return;
    }

    try {
      await changePassword.mutateAsync({ currentPassword, newPassword });
      onClose();
      // Mostrar toast de éxito
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Error al cambiar contraseña');
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay">
      <div className="modal">
        <h2>Cambiar Contraseña</h2>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Contraseña actual</label>
            <input
              type="password"
              value={currentPassword}
              onChange={e => setCurrentPassword(e.target.value)}
              required
            />
          </div>
          <div className="form-group">
            <label>Nueva contraseña</label>
            <input
              type="password"
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
              required
            />
            <small>
              Mínimo 8 caracteres, mayúscula, minúscula, número y símbolo
            </small>
          </div>
          <div className="form-group">
            <label>Confirmar nueva contraseña</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              required
            />
          </div>

          {error && <p className="error">{error}</p>}

          <div className="modal-actions">
            <button type="button" onClick={onClose} className="btn-secondary">
              Cancelar
            </button>
            <button
              type="submit"
              disabled={changePassword.isPending}
              className="btn-primary"
            >
              {changePassword.isPending ? 'Guardando...' : 'Cambiar contraseña'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

---

## Sincronización en Tiempo Real (WebSocket)

El backend envía eventos WebSocket cuando el perfil se actualiza. Útil para sincronización multi-tab.

### Eventos

```typescript
// Cuando se actualiza el perfil
{
  type: 'manager_profile_updated'
}

// Cuando se actualiza la foto
{
  type: 'profile_pic_updated',
  profile_pic: 'https://...'
}
```

### Manejo en Frontend

```typescript
// En tu hook de WebSocket
ws.onmessage = (event) => {
  const message = JSON.parse(event.data);

  if (message.type === 'manager_profile_updated') {
    // Refrescar perfil
    queryClient.invalidateQueries(['manager-profile']);
  }

  if (message.type === 'profile_pic_updated') {
    // Actualizar foto directamente
    queryClient.setQueryData(['manager-profile'], (old: any) => ({
      ...old,
      profile_pic: message.profile_pic,
    }));
  }
};
```

---

## Campos de Solo Lectura

Los siguientes campos **NO son editables** por el manager:

| Campo | Razón |
|-------|-------|
| `email` | Requiere verificación. Contactar soporte. |
| `organization_id` | Vinculado al registro del manager |
| `membership_status` | Gestionado por sistema de pagos |
| `locations` | Se crean/gestionan en otra sección |
| `created_at` | Fecha de registro (histórico) |

---

## Consideraciones de UX

### Foto de Perfil
- Mostrar preview antes de subir
- Indicar límite de 4MB
- Mostrar progreso de upload
- Crop/resize opcional antes de subir

### Validación de Teléfono
- Aceptar varios formatos: `+1 (555) 123-4567`, `555-123-4567`, etc.
- Normalizar a E.164 antes de enviar: `+15551234567`

### Membership Status Badges
```css
.badge-freemium { background: #6b7280; }
.badge-pro { background: #3b82f6; }
.badge-enterprise { background: #8b5cf6; }
```

### Manejo de Errores
- Mostrar errores de validación inline
- Toast para errores de servidor
- Retry automático en fallos de red

---

## Testing

### Endpoints de Prueba (dev)

```bash
# Obtener perfil
curl -X GET "http://localhost:8001/v1/profile/manager" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Actualizar nombre
curl -X PATCH "http://localhost:8001/v1/profile/manager" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"first_name": "Test", "last_name": "User"}'

# Subir foto
curl -X POST "http://localhost:8001/v1/profile/manager/upload-photo" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@/path/to/photo.jpg"
```

---

## Changelog

| Fecha | Versión | Cambios |
|-------|---------|---------|
| 2026-02-03 | 1.0.0 | Implementación inicial |

---

**Contacto Backend:** Para dudas o problemas, crear issue en el repo.
