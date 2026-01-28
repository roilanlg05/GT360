# Guía de Autenticación para App React Native - Drivers

Esta guía contiene toda la información necesaria para implementar el **Login** y **Sign Out** en tu aplicación React Native para drivers.

## Índice
1. [Información General](#información-general)
2. [Flujo de Autenticación](#flujo-de-autenticación)
3. [Login (Sign In)](#login-sign-in)
4. [Sign Out](#sign-out)
5. [Refresh Token](#refresh-token)
6. [Ejemplos de Implementación React Native](#ejemplos-de-implementación-react-native)
7. [Manejo de Errores](#manejo-de-errores)
8. [Consideraciones Importantes](#consideraciones-importantes)

---

## Información General

### URL Base del Backend
```
https://web.gt360.app
```

### Sistema de Autenticación
El backend utiliza un sistema dual de tokens:
- **Access Token (JWT)**: Token de corta duración enviado en el header `Authorization`
- **Refresh Token**: Token opaco de larga duración (30 días) almacenado en cookies HTTP-only

### Nota Importante sobre Sign Up
**Los drivers NO pueden registrarse por sí mismos**. Las cuentas de driver son creadas por el Manager de la organización, quien les proporciona el email y ellos reciben un email de verificación.

---

## Flujo de Autenticación

```
1. Manager crea cuenta de driver
   ↓
2. Driver recibe email de verificación
   ↓
3. Driver verifica su email (click en el link)
   ↓
4. Driver puede hacer login en la app
   ↓
5. Backend devuelve access_token + refresh_token
   ↓
6. App almacena access_token y cookies de refresh
   ↓
7. App usa access_token en cada request
   ↓
8. Cuando access_token expira, usa refresh para obtener nuevo access_token
```

---

## Login (Sign In)

### Endpoint
```
POST /v1/auth/sign-in
```

### Request Body
```json
{
  "email": "driver@example.com",
  "password": "DriverPassword123!"
}
```

### Headers
```
Content-Type: application/json
```

### Response Exitosa (200 OK)
```json
{
  "data": {
    "session": {
      "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "expires_at": 1706140800,
      "type": "Bearer"
    },
    "user_data": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "email": "driver@example.com",
      "phone": "+1234567890",
      "role": "driver",
      "organization_id": "660e8400-e29b-41d4-a716-446655440000",
      "location_id": "770e8400-e29b-41d4-a716-446655440000"
    }
  }
}
```

### Cookies Recibidas (Automáticas)
El backend establece estas cookies en la response:
- `refresh_token`: Token opaco para renovar el access token
- `expires_at`: Fecha de expiración del refresh token

### Campos del User Data

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | string (UUID) | ID único del driver |
| `email` | string | Email del driver |
| `phone` | string | Teléfono del driver |
| `role` | string | Siempre será `"driver"` |
| `organization_id` | string (UUID) | ID de la organización a la que pertenece |
| `location_id` | string (UUID) | ID de la ubicación asignada al driver |

### Errores Posibles

#### 401 Unauthorized - Credenciales Inválidas
```json
{
  "detail": "Invalid credentials"
}
```
**Razones:**
- Email o contraseña incorrectos
- Usuario no existe

#### 401 Unauthorized - Email No Verificado
```json
{
  "detail": "Email not verified"
}
```
**Razón:** El driver no ha verificado su email mediante el link enviado por correo.

---

## Sign Out

### Endpoint
```
POST /v1/auth/sign-out/
```

### Headers
```
Authorization: Bearer {access_token}
Content-Type: application/json
```

### Request Body
No requiere body (puede ser vacío `{}`).

### Response Exitosa (200 OK)
```json
{
  "message": "All cookies revoked"
}
```

### Qué Hace el Endpoint
1. Añade el access token a una blacklist (Redis) por 5 minutos
2. Revoca todos los refresh tokens del usuario en la base de datos
3. Elimina las cookies `refresh_token` y `expires_at`

### Errores Posibles

#### 401 Unauthorized
```json
{
  "detail": "Missing or invalid authentication"
}
```
**Razón:** No se envió el token o el token es inválido.

#### 403 Forbidden
```json
{
  "detail": "Token revoked"
}
```
**Razón:** El token ya fue usado para sign out previamente.

---

## Refresh Token

### Endpoint
```
POST /v1/auth/refresh
```

### Headers
```
Content-Type: application/json
Cookie: refresh_token={token}; expires_at={timestamp}
```

### Request Body
No requiere body. El refresh token se envía automáticamente en las cookies.

### Response Exitosa (200 OK)
```json
{
  "data": {
    "session": {
      "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "exp": 1706140800,
      "type": "bearer"
    },
    "user_data": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "email": "driver@example.com",
      "phone": "+1234567890",
      "role": "driver",
      "organization_id": "660e8400-e29b-41d4-a716-446655440000",
      "location_id": "770e8400-e29b-41d4-a716-446655440000"
    }
  }
}
```

### Cookies Actualizadas
El backend envía un nuevo `refresh_token` y `expires_at` que reemplazan los anteriores.

### Errores Posibles

#### 401 Unauthorized
```json
{
  "detail": "Missing refresh token"
}
```
**Razón:** No se envió el refresh token en las cookies.

```json
{
  "detail": "Invalid refresh token"
}
```
**Razón:** El refresh token no existe o es inválido.

```json
{
  "detail": "Refresh token expired or revoked"
}
```
**Razón:** El refresh token fue revocado o expiró.

---

## Ejemplos de Implementación React Native

### 1. Configuración de Cliente HTTP con Axios

```javascript
import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';

const API_BASE_URL = 'https://web.gt360.app';

// Crear instancia de axios
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true, // Importante para cookies
});

// Interceptor para agregar token a cada request
apiClient.interceptors.request.use(
  async (config) => {
    const token = await AsyncStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Interceptor para manejar errores 401 y refrescar token
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Si es 401 y no hemos intentado refrescar aún
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        // Intentar refrescar el token
        const refreshResponse = await axios.post(
          `${API_BASE_URL}/v1/auth/refresh`,
          {},
          { withCredentials: true }
        );

        const newToken = refreshResponse.data.data.session.access_token;
        await AsyncStorage.setItem('access_token', newToken);

        // Reintentar request original con nuevo token
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        // Si falla el refresh, hacer logout
        await AsyncStorage.removeItem('access_token');
        await AsyncStorage.removeItem('user_data');
        // Navegar a login
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

export default apiClient;
```

### 2. Servicio de Autenticación

```javascript
// services/authService.js
import apiClient from './apiClient';
import AsyncStorage from '@react-native-async-storage/async-storage';

export const authService = {
  /**
   * Login del driver
   * @param {string} email
   * @param {string} password
   * @returns {Promise<Object>} User data y session
   */
  async login(email, password) {
    try {
      const response = await apiClient.post('/v1/auth/sign-in', {
        email: email.toLowerCase().trim(),
        password,
      });

      const { session, user_data } = response.data.data;

      // Guardar token y datos de usuario
      await AsyncStorage.setItem('access_token', session.access_token);
      await AsyncStorage.setItem('user_data', JSON.stringify(user_data));

      return { session, user_data };
    } catch (error) {
      // Manejar errores específicos
      if (error.response?.status === 401) {
        const detail = error.response.data.detail;
        if (detail === 'Email not verified') {
          throw new Error('Por favor verifica tu email antes de iniciar sesión');
        } else {
          throw new Error('Email o contraseña incorrectos');
        }
      }
      throw new Error('Error al iniciar sesión. Intenta de nuevo.');
    }
  },

  /**
   * Sign out del driver
   * @returns {Promise<void>}
   */
  async signOut() {
    try {
      await apiClient.post('/v1/auth/sign-out/');
    } catch (error) {
      console.error('Error during sign out:', error);
    } finally {
      // Limpiar storage local
      await AsyncStorage.removeItem('access_token');
      await AsyncStorage.removeItem('user_data');
    }
  },

  /**
   * Refresh access token
   * @returns {Promise<Object>} Nuevo session y user_data
   */
  async refreshToken() {
    try {
      const response = await apiClient.post('/v1/auth/refresh');
      const { session, user_data } = response.data.data;

      await AsyncStorage.setItem('access_token', session.access_token);
      await AsyncStorage.setItem('user_data', JSON.stringify(user_data));

      return { session, user_data };
    } catch (error) {
      // Si falla el refresh, limpiar storage
      await AsyncStorage.removeItem('access_token');
      await AsyncStorage.removeItem('user_data');
      throw error;
    }
  },

  /**
   * Obtener datos del usuario guardados localmente
   * @returns {Promise<Object|null>}
   */
  async getUserData() {
    const userData = await AsyncStorage.getItem('user_data');
    return userData ? JSON.parse(userData) : null;
  },

  /**
   * Verificar si el usuario está autenticado
   * @returns {Promise<boolean>}
   */
  async isAuthenticated() {
    const token = await AsyncStorage.getItem('access_token');
    return !!token;
  },
};
```

### 3. Componente de Login

```javascript
// screens/LoginScreen.js
import React, { useState } from 'react';
import { View, TextInput, Button, Text, StyleSheet, Alert } from 'react-native';
import { authService } from '../services/authService';

export default function LoginScreen({ navigation }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    if (!email || !password) {
      Alert.alert('Error', 'Por favor ingresa email y contraseña');
      return;
    }

    setLoading(true);
    try {
      const { user_data } = await authService.login(email, password);

      Alert.alert(
        'Bienvenido',
        `Hola ${user_data.email}`,
        [{ text: 'OK', onPress: () => navigation.replace('Home') }]
      );
    } catch (error) {
      Alert.alert('Error', error.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Driver Login</Text>

      <TextInput
        style={styles.input}
        placeholder="Email"
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        keyboardType="email-address"
        editable={!loading}
      />

      <TextInput
        style={styles.input}
        placeholder="Contraseña"
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        editable={!loading}
      />

      <Button
        title={loading ? 'Iniciando sesión...' : 'Iniciar Sesión'}
        onPress={handleLogin}
        disabled={loading}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    padding: 20,
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    marginBottom: 20,
    textAlign: 'center',
  },
  input: {
    borderWidth: 1,
    borderColor: '#ccc',
    borderRadius: 5,
    padding: 10,
    marginBottom: 15,
  },
});
```

### 4. Componente con Sign Out

```javascript
// screens/HomeScreen.js
import React, { useEffect, useState } from 'react';
import { View, Text, Button, StyleSheet, Alert } from 'react-native';
import { authService } from '../services/authService';

export default function HomeScreen({ navigation }) {
  const [userData, setUserData] = useState(null);

  useEffect(() => {
    loadUserData();
  }, []);

  const loadUserData = async () => {
    const data = await authService.getUserData();
    setUserData(data);
  };

  const handleSignOut = async () => {
    Alert.alert(
      'Cerrar Sesión',
      '¿Estás seguro que deseas cerrar sesión?',
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Cerrar Sesión',
          style: 'destructive',
          onPress: async () => {
            try {
              await authService.signOut();
              navigation.replace('Login');
            } catch (error) {
              Alert.alert('Error', 'Hubo un problema al cerrar sesión');
            }
          },
        },
      ]
    );
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Bienvenido Driver</Text>

      {userData && (
        <View style={styles.userInfo}>
          <Text>Email: {userData.email}</Text>
          <Text>Teléfono: {userData.phone}</Text>
          <Text>Location ID: {userData.location_id}</Text>
        </View>
      )}

      <Button title="Cerrar Sesión" onPress={handleSignOut} color="red" />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    padding: 20,
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    marginBottom: 20,
    textAlign: 'center',
  },
  userInfo: {
    marginBottom: 20,
    padding: 15,
    backgroundColor: '#f0f0f0',
    borderRadius: 5,
  },
});
```

### 5. Context Provider para Autenticación Global

```javascript
// contexts/AuthContext.js
import React, { createContext, useState, useEffect, useContext } from 'react';
import { authService } from '../services/authService';

const AuthContext = createContext();

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    try {
      const userData = await authService.getUserData();
      setUser(userData);
    } catch (error) {
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  const login = async (email, password) => {
    const { user_data } = await authService.login(email, password);
    setUser(user_data);
    return user_data;
  };

  const signOut = async () => {
    await authService.signOut();
    setUser(null);
  };

  const value = {
    user,
    loading,
    login,
    signOut,
    isAuthenticated: !!user,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
```

### 6. App.js con Navegación

```javascript
// App.js
import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import LoginScreen from './screens/LoginScreen';
import HomeScreen from './screens/HomeScreen';
import { ActivityIndicator, View } from 'react-native';

const Stack = createNativeStackNavigator();

function Navigation() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  return (
    <Stack.Navigator>
      {user ? (
        <Stack.Screen
          name="Home"
          component={HomeScreen}
          options={{ title: 'GT360 Driver' }}
        />
      ) : (
        <Stack.Screen
          name="Login"
          component={LoginScreen}
          options={{ headerShown: false }}
        />
      )}
    </Stack.Navigator>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <NavigationContainer>
        <Navigation />
      </NavigationContainer>
    </AuthProvider>
  );
}
```

---

## Manejo de Errores

### Tabla de Códigos de Error

| Código | Mensaje | Acción Recomendada |
|--------|---------|-------------------|
| 401 | Invalid credentials | Mostrar "Email o contraseña incorrectos" |
| 401 | Email not verified | Mostrar "Por favor verifica tu email" |
| 401 | Missing refresh token | Redirigir a login |
| 401 | Invalid refresh token | Redirigir a login |
| 401 | Refresh token expired or revoked | Redirigir a login |
| 403 | Token revoked | Redirigir a login |
| 403 | Not Authorized | Redirigir a login |

### Ejemplo de Manejo Global de Errores

```javascript
const handleApiError = (error) => {
  if (error.response) {
    const { status, data } = error.response;

    switch (status) {
      case 401:
        if (data.detail === 'Email not verified') {
          return 'Por favor verifica tu email antes de continuar';
        }
        return 'Sesión expirada. Por favor inicia sesión nuevamente';

      case 403:
        return 'No tienes permisos para realizar esta acción';

      case 404:
        return 'Recurso no encontrado';

      case 409:
        return 'Conflicto con los datos existentes';

      case 500:
        return 'Error del servidor. Intenta de nuevo más tarde';

      default:
        return 'Ocurrió un error inesperado';
    }
  } else if (error.request) {
    return 'No se pudo conectar al servidor. Verifica tu conexión';
  } else {
    return 'Error al procesar la solicitud';
  }
};
```

---

## Consideraciones Importantes

### 1. Manejo de Cookies en React Native

React Native no maneja cookies HTTP-only de forma nativa como los navegadores web. Para esto necesitas:

**Opción A: Usar una librería que soporte cookies**
```bash
npm install @react-native-cookies/cookies
```

```javascript
import CookieManager from '@react-native-cookies/cookies';

// Habilitar cookies en axios
import axios from 'axios';

const apiClient = axios.create({
  baseURL: 'https://web.gt360.app',
  withCredentials: true, // Importante!
});
```

**Opción B: Usar un WebView para login (si tienes problemas con cookies)**
```javascript
import { WebView } from 'react-native-webview';

// Hacer login en WebView y extraer el token
```

### 2. Persistencia de Sesión

Usa `AsyncStorage` para mantener la sesión entre reinicios de la app:

```javascript
import AsyncStorage from '@react-native-async-storage/async-storage';

// Guardar
await AsyncStorage.setItem('access_token', token);

// Recuperar
const token = await AsyncStorage.getItem('access_token');

// Eliminar
await AsyncStorage.removeItem('access_token');
```

### 3. Seguridad

1. **Nunca guardes el password**: Solo guarda el access token
2. **Limpia el storage al hacer sign out**: Elimina todos los datos sensibles
3. **Valida el token antes de navegar**: Verifica que existe un token válido
4. **Maneja 401 globalmente**: Redirige a login automáticamente en errores 401

### 4. Duración de Tokens

- **Access Token**: ~15 minutos (configurable en `TOKEN_DURATION`)
- **Refresh Token**: 30 días

### 5. Refresh Automático

Implementa un interceptor que automáticamente refresque el token cuando expire:

```javascript
// Ver ejemplo en "Configuración de Cliente HTTP con Axios"
```

### 6. Testing

Para probar los endpoints puedes usar:

```bash
# Login
curl -X POST https://web.gt360.app/v1/auth/sign-in \
  -H "Content-Type: application/json" \
  -d '{"email":"driver@example.com","password":"password123"}' \
  -c cookies.txt

# Sign Out
curl -X POST https://web.gt360.app/v1/auth/sign-out/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -b cookies.txt
```

### 7. Email Verification

Si el driver intenta hacer login sin haber verificado su email, recibirá:
```json
{
  "detail": "Email not verified"
}
```

El driver debe:
1. Revisar su correo
2. Hacer click en el link de verificación
3. Volver a intentar el login

---

## Resumen de Endpoints

| Método | Endpoint | Descripción | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/v1/auth/sign-in` | Login de driver | No |
| POST | `/v1/auth/sign-out/` | Cerrar sesión | Sí |
| POST | `/v1/auth/refresh` | Renovar access token | Sí (cookie) |

---

## Soporte

Si tienes problemas con la autenticación:
1. Verifica que el email esté verificado
2. Confirma que estás enviando las cookies correctamente
3. Revisa que el access token no haya expirado
4. Usa el refresh endpoint para obtener un nuevo token

---

## Changelog

- **v1.0** (2025-01-25): Documentación inicial para drivers
