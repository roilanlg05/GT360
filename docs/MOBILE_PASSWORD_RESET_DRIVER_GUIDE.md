# Guía de Integración Móvil: Password Reset para Drivers

**Versión:** 1.0
**Fecha:** 2026-02-07
**Plataformas:** Android & iOS
**Usuario:** Driver Role
**Backend Base URL:** `https://dev-api.gt360.app` (Dev) | `https://api.gt360.app` (Prod)

---

## Tabla de Contenidos

1. [Resumen del Sistema](#resumen-del-sistema)
2. [Endpoints de API](#endpoints-de-api)
3. [Flujo Completo del Usuario](#flujo-completo-del-usuario)
4. [Implementación Técnica](#implementación-técnica)
5. [Manejo de Errores](#manejo-de-errores)
6. [Deep Linking](#deep-linking)
7. [Validaciones](#validaciones)
8. [Casos de Prueba](#casos-de-prueba)
9. [Checklist de Implementación](#checklist-de-implementación)

---

## Resumen del Sistema

El sistema de restablecimiento de contraseña para drivers consta de **2 endpoints principales**:

1. **Forgot Password** - El driver solicita un link de reset
2. **Reset Password** - El driver establece su nueva contraseña

**Características:**
- ✅ Link de reset expira en 30 minutos
- ✅ Link de un solo uso (no reutilizable)
- ✅ Email enviado automáticamente por el backend
- ✅ Validación de fortaleza de contraseña
- ✅ Revocación automática de sesiones previas

---

## Endpoints de API

### 1. Solicitar Reset de Contraseña

**Endpoint:** `POST /v1/auth/forgot-password`
**Autenticación:** No requerida
**Rate Limit:** Implícito por nonce único

#### Request

```http
POST https://dev-api.gt360.app/v1/auth/forgot-password
Content-Type: application/json

{
  "email": "driver@example.com"
}
```

#### Request Body Schema

```json
{
  "email": "string (EmailStr, required)"
}
```

#### Response Success (200 OK)

```json
{
  "content": "If the email exists, you will receive a password reset link",
  "status_code": 200
}
```

**⚠️ IMPORTANTE:** El endpoint **SIEMPRE retorna 200** incluso si el email no existe. Esto previene que atacantes enumeren usuarios válidos.

#### Response Errors

| Código | Body | Descripción |
|--------|------|-------------|
| `400` | `{"detail": "Invalid email format"}` | Email con formato inválido |
| `500` | `{"detail": "Internal server error"}` | Error del servidor |

#### Ejemplo de Request (Pseudocódigo)

```kotlin
// Android/Kotlin
suspend fun requestPasswordReset(email: String): Result<String> {
    return try {
        val response = httpClient.post("$BASE_URL/v1/auth/forgot-password") {
            contentType(ContentType.Application.Json)
            setBody(mapOf("email" to email))
        }

        if (response.status == HttpStatusCode.OK) {
            val body = response.body<ForgotPasswordResponse>()
            Result.success(body.content)
        } else {
            Result.failure(Exception("Error ${response.status}"))
        }
    } catch (e: Exception) {
        Result.failure(e)
    }
}
```

```swift
// iOS/Swift
func requestPasswordReset(email: String) async throws -> String {
    let url = URL(string: "\(baseURL)/v1/auth/forgot-password")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")

    let body = ["email": email]
    request.httpBody = try JSONSerialization.data(withJSONObject: body)

    let (data, response) = try await URLSession.shared.data(for: request)

    guard let httpResponse = response as? HTTPURLResponse,
          httpResponse.statusCode == 200 else {
        throw PasswordResetError.requestFailed
    }

    let result = try JSONDecoder().decode(ForgotPasswordResponse.self, from: data)
    return result.content
}
```

---

### 2. Confirmar Nueva Contraseña

**Endpoint:** `POST /v1/auth/reset-password`
**Autenticación:** No requerida (token en body)
**Rate Limit:** Implícito por token de un solo uso

#### Request

```http
POST https://dev-api.gt360.app/v1/auth/reset-password
Content-Type: application/json

{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI5YzNlZjQyZC0xMjM0LTU2NzgtOTBhYi1jZGVmMTIzNDU2NzgiLCJpYXQiOjE3MDcyNjg4MDAsImV4cCI6MTcwNzI3MDYwMCwibWV0YWRhdGEiOnsiZW1haWwiOiJkcml2ZXJAZXhhbXBsZS5jb20iLCJwdXJwb3NlIjoicGFzc3dvcmRfcmVzZXQiLCJub25jZSI6ImFiY2RlZjEyMzQ1Njc4In19.signature",
  "password": {
    "new_password": "NewSecurePassword123!"
  }
}
```

#### Request Body Schema

```json
{
  "token": "string (JWT Token, required)",
  "password": {
    "new_password": "string (min 8 chars, required)"
  }
}
```

#### Response Success (200 OK)

```json
{
  "message": "Password updated. Sign in again."
}
```

#### Response Errors

| Código | Body | Descripción |
|--------|------|-------------|
| `400` | `{"detail": "Token already used or invalid"}` | Token ya fue utilizado |
| `400` | `{"detail": "Password must contain at least 8 characters, one uppercase, one lowercase, one number, and one special character"}` | Contraseña débil |
| `403` | `{"detail": "Invalid or expired token"}` | Token inválido o expirado |
| `409` | `{"detail": "The new password must be different from your current password."}` | Nueva contraseña igual a la anterior |
| `500` | `{"detail": "Internal server error"}` | Error del servidor |

#### Ejemplo de Request (Pseudocódigo)

```kotlin
// Android/Kotlin
data class ResetPasswordRequest(
    val token: String,
    val password: PasswordData
)

data class PasswordData(
    val new_password: String
)

suspend fun resetPassword(token: String, newPassword: String): Result<String> {
    return try {
        val response = httpClient.post("$BASE_URL/v1/auth/reset-password") {
            contentType(ContentType.Application.Json)
            setBody(ResetPasswordRequest(
                token = token,
                password = PasswordData(new_password = newPassword)
            ))
        }

        when (response.status) {
            HttpStatusCode.OK -> {
                val body = response.body<ResetPasswordResponse>()
                Result.success(body.message)
            }
            HttpStatusCode.BadRequest -> {
                val error = response.body<ErrorResponse>()
                Result.failure(Exception(error.detail))
            }
            HttpStatusCode.Forbidden -> {
                Result.failure(Exception("Token inválido o expirado"))
            }
            HttpStatusCode.Conflict -> {
                Result.failure(Exception("La contraseña debe ser diferente a la anterior"))
            }
            else -> {
                Result.failure(Exception("Error ${response.status}"))
            }
        }
    } catch (e: Exception) {
        Result.failure(e)
    }
}
```

```swift
// iOS/Swift
struct ResetPasswordRequest: Codable {
    let token: String
    let password: PasswordData

    struct PasswordData: Codable {
        let new_password: String
    }
}

func resetPassword(token: String, newPassword: String) async throws -> String {
    let url = URL(string: "\(baseURL)/v1/auth/reset-password")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")

    let body = ResetPasswordRequest(
        token: token,
        password: ResetPasswordRequest.PasswordData(new_password: newPassword)
    )
    request.httpBody = try JSONEncoder().encode(body)

    let (data, response) = try await URLSession.shared.data(for: request)

    guard let httpResponse = response as? HTTPURLResponse else {
        throw PasswordResetError.invalidResponse
    }

    switch httpResponse.statusCode {
    case 200:
        let result = try JSONDecoder().decode(ResetPasswordResponse.self, from: data)
        return result.message
    case 400:
        let error = try JSONDecoder().decode(ErrorResponse.self, from: data)
        throw PasswordResetError.badRequest(error.detail)
    case 403:
        throw PasswordResetError.invalidToken
    case 409:
        throw PasswordResetError.samePassword
    default:
        throw PasswordResetError.unknown
    }
}
```

---

## Flujo Completo del Usuario

```
┌─────────────────────────────────────────────────────────────┐
│                    DRIVER MOBILE APP                         │
└─────────────────────────────────────────────────────────────┘

1. PANTALLA DE LOGIN
   ├─ Input: Email
   ├─ Input: Password
   ├─ Button: "Login"
   └─ Link: "¿Olvidaste tu contraseña?" ──┐
                                          │
                                          ▼
2. PANTALLA: FORGOT PASSWORD
   ├─ Título: "Recuperar Contraseña"
   ├─ Input: Email (placeholder: "tu-email@example.com")
   ├─ Button: "Enviar Link de Recuperación"
   └─ Link: "Volver al Login"
   │
   │ [User taps "Enviar Link"]
   │
   ▼
3. API CALL: POST /v1/auth/forgot-password
   ├─ Body: { "email": "driver@example.com" }
   └─ Response: 200 OK
   │
   ▼
4. MOSTRAR MENSAJE
   ├─ Título: "¡Revisa tu Email!"
   ├─ Mensaje: "Si el email existe, recibirás un link para restablecer tu contraseña"
   ├─ Subtítulo: "El link expira en 30 minutos"
   └─ Button: "Volver al Login"
   │
   │ [Driver abre su email]
   │
   ▼
5. EMAIL RECIBIDO (Enviado por Backend)
   ├─ Subject: "Reset Your GT 360 Password"
   ├─ Contenido HTML profesional
   ├─ Botón: "Reset Password"
   └─ Link: gt360://reset-password?token=<JWT_TOKEN>
      └─ Alternativa Web: https://app.gt360.app/reset?token=<JWT_TOKEN>
   │
   │ [Driver hace click en el link]
   │
   ▼
6. DEEP LINK CAPTURADO
   ├─ Esquema: gt360://reset-password?token=xxxxx
   ├─ App se abre (si está instalada)
   └─ Navega a ResetPasswordScreen con token
   │
   ▼
7. PANTALLA: RESET PASSWORD
   ├─ Título: "Nueva Contraseña"
   ├─ Input: Nueva Contraseña (secure, placeholder: "Mínimo 8 caracteres")
   ├─ Input: Confirmar Contraseña (secure)
   ├─ Validación en tiempo real:
   │  ├─ ✓ Al menos 8 caracteres
   │  ├─ ✓ Una mayúscula
   │  ├─ ✓ Una minúscula
   │  ├─ ✓ Un número
   │  └─ ✓ Un carácter especial
   ├─ Button: "Restablecer Contraseña" (disabled hasta validar)
   └─ Link: "Volver al Login"
   │
   │ [User ingresa contraseña válida y taps "Restablecer"]
   │
   ▼
8. API CALL: POST /v1/auth/reset-password
   ├─ Body: {
   │    "token": "<JWT_FROM_DEEP_LINK>",
   │    "password": { "new_password": "NewPass123!" }
   │  }
   └─ Response: 200 OK
   │
   ▼
9. ÉXITO
   ├─ Mostrar Alert/Dialog:
   │  ├─ Título: "¡Contraseña Actualizada!"
   │  ├─ Mensaje: "Tu contraseña ha sido restablecida exitosamente"
   │  └─ Button: "Iniciar Sesión"
   └─ Navegar a Login Screen
   │
   ▼
10. DRIVER HACE LOGIN
    ├─ Email: driver@example.com
    ├─ Password: NewPass123!
    └─ POST /v1/auth/sign-in
    │
    ▼
11. LOGIN EXITOSO
    └─ Navega a Home/Dashboard
```

---

## Implementación Técnica

### Arquitectura Recomendada

```
┌─────────────────────────────────────────────────────────┐
│                     PRESENTATION LAYER                   │
│  ┌──────────────────┐  ┌──────────────────┐            │
│  │ ForgotPassword   │  │ ResetPassword    │            │
│  │ Screen/Activity  │  │ Screen/Activity  │            │
│  └──────────────────┘  └──────────────────┘            │
│           │                      │                       │
│           ▼                      ▼                       │
│  ┌─────────────────────────────────────────┐            │
│  │      ViewModel/Presenter/Controller     │            │
│  └─────────────────────────────────────────┘            │
│           │                                              │
│           ▼                                              │
│  ┌─────────────────────────────────────────┐            │
│  │         Password Reset Use Cases        │            │
│  │  - RequestPasswordResetUseCase          │            │
│  │  - ResetPasswordUseCase                 │            │
│  │  - ValidatePasswordUseCase              │            │
│  └─────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│                      DATA LAYER                         │
│  ┌─────────────────────────────────────────┐            │
│  │       PasswordResetRepository           │            │
│  └─────────────────────────────────────────┘            │
│           │                                              │
│           ▼                                              │
│  ┌─────────────────────────────────────────┐            │
│  │         API Client / Network Layer      │            │
│  │  - HttpClient (Ktor/Retrofit/URLSession)│            │
│  │  - Request/Response Models              │            │
│  │  - Error Handling                       │            │
│  └─────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────┘
                       │
                       ▼
              ┌────────────────┐
              │  GT360 Backend │
              │  REST API      │
              └────────────────┘
```

### Modelos de Datos

```kotlin
// Android/Kotlin - Data Models

// Request Models
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

// Response Models
data class ForgotPasswordResponse(
    val content: String,
    val status_code: Int
)

data class ResetPasswordResponse(
    val message: String
)

data class ErrorResponse(
    val detail: String
)

// Domain Models
sealed class PasswordResetResult {
    data class Success(val message: String) : PasswordResetResult()
    data class Error(val message: String, val code: ErrorCode) : PasswordResetResult()
}

enum class ErrorCode {
    INVALID_TOKEN,
    EXPIRED_TOKEN,
    WEAK_PASSWORD,
    SAME_PASSWORD,
    NETWORK_ERROR,
    UNKNOWN
}
```

```swift
// iOS/Swift - Data Models

// Request Models
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

// Response Models
struct ForgotPasswordResponse: Codable {
    let content: String
    let status_code: Int
}

struct ResetPasswordResponse: Codable {
    let message: String
}

struct ErrorResponse: Codable {
    let detail: String
}

// Domain Models
enum PasswordResetResult {
    case success(message: String)
    case failure(error: PasswordResetError)
}

enum PasswordResetError: Error {
    case invalidToken
    case expiredToken
    case weakPassword
    case samePassword
    case networkError
    case invalidResponse
    case unknown

    var localizedDescription: String {
        switch self {
        case .invalidToken:
            return "El link de recuperación es inválido"
        case .expiredToken:
            return "El link de recuperación ha expirado (30 min)"
        case .weakPassword:
            return "La contraseña debe tener al menos 8 caracteres, una mayúscula, una minúscula, un número y un carácter especial"
        case .samePassword:
            return "La nueva contraseña debe ser diferente a la anterior"
        case .networkError:
            return "Error de conexión. Verifica tu internet"
        case .invalidResponse:
            return "Respuesta inválida del servidor"
        case .unknown:
            return "Error desconocido. Intenta de nuevo"
        }
    }
}
```

### Repository Pattern (Kotlin Example)

```kotlin
// Android/Kotlin - Repository

interface PasswordResetRepository {
    suspend fun requestPasswordReset(email: String): Result<String>
    suspend fun resetPassword(token: String, newPassword: String): Result<String>
}

class PasswordResetRepositoryImpl(
    private val apiClient: ApiClient
) : PasswordResetRepository {

    override suspend fun requestPasswordReset(email: String): Result<String> {
        return try {
            val request = ForgotPasswordRequest(email = email)
            val response = apiClient.post<ForgotPasswordResponse>(
                endpoint = "/v1/auth/forgot-password",
                body = request
            )
            Result.success(response.content)
        } catch (e: HttpException) {
            Result.failure(e)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    override suspend fun resetPassword(token: String, newPassword: String): Result<String> {
        return try {
            val request = ResetPasswordRequest(
                token = token,
                password = ResetPasswordRequest.PasswordData(new_password = newPassword)
            )
            val response = apiClient.post<ResetPasswordResponse>(
                endpoint = "/v1/auth/reset-password",
                body = request
            )
            Result.success(response.message)
        } catch (e: HttpException) {
            when (e.code()) {
                400 -> Result.failure(Exception("Token inválido o ya utilizado"))
                403 -> Result.failure(Exception("Token expirado"))
                409 -> Result.failure(Exception("La contraseña debe ser diferente"))
                else -> Result.failure(e)
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
```

### Repository Pattern (Swift Example)

```swift
// iOS/Swift - Repository

protocol PasswordResetRepository {
    func requestPasswordReset(email: String) async throws -> String
    func resetPassword(token: String, newPassword: String) async throws -> String
}

class PasswordResetRepositoryImpl: PasswordResetRepository {

    private let apiClient: APIClient

    init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    func requestPasswordReset(email: String) async throws -> String {
        let request = ForgotPasswordRequest(email: email)
        let response: ForgotPasswordResponse = try await apiClient.post(
            endpoint: "/v1/auth/forgot-password",
            body: request
        )
        return response.content
    }

    func resetPassword(token: String, newPassword: String) async throws -> String {
        let request = ResetPasswordRequest(
            token: token,
            password: ResetPasswordRequest.PasswordData(new_password: newPassword)
        )

        do {
            let response: ResetPasswordResponse = try await apiClient.post(
                endpoint: "/v1/auth/reset-password",
                body: request
            )
            return response.message
        } catch let error as APIError {
            switch error.statusCode {
            case 400:
                throw PasswordResetError.invalidToken
            case 403:
                throw PasswordResetError.expiredToken
            case 409:
                throw PasswordResetError.samePassword
            default:
                throw PasswordResetError.unknown
            }
        }
    }
}
```

### Use Cases

```kotlin
// Android/Kotlin - Use Cases

class RequestPasswordResetUseCase(
    private val repository: PasswordResetRepository
) {
    suspend operator fun invoke(email: String): PasswordResetResult {
        if (!isValidEmail(email)) {
            return PasswordResetResult.Error(
                message = "Email inválido",
                code = ErrorCode.INVALID_EMAIL
            )
        }

        return repository.requestPasswordReset(email).fold(
            onSuccess = { message ->
                PasswordResetResult.Success(message)
            },
            onFailure = { error ->
                PasswordResetResult.Error(
                    message = error.message ?: "Error desconocido",
                    code = ErrorCode.NETWORK_ERROR
                )
            }
        )
    }

    private fun isValidEmail(email: String): Boolean {
        return android.util.Patterns.EMAIL_ADDRESS.matcher(email).matches()
    }
}

class ResetPasswordUseCase(
    private val repository: PasswordResetRepository,
    private val validatePasswordUseCase: ValidatePasswordUseCase
) {
    suspend operator fun invoke(
        token: String,
        newPassword: String,
        confirmPassword: String
    ): PasswordResetResult {

        // Validate passwords match
        if (newPassword != confirmPassword) {
            return PasswordResetResult.Error(
                message = "Las contraseñas no coinciden",
                code = ErrorCode.PASSWORDS_DONT_MATCH
            )
        }

        // Validate password strength
        val validationResult = validatePasswordUseCase(newPassword)
        if (validationResult is PasswordValidationResult.Invalid) {
            return PasswordResetResult.Error(
                message = validationResult.message,
                code = ErrorCode.WEAK_PASSWORD
            )
        }

        // Make API call
        return repository.resetPassword(token, newPassword).fold(
            onSuccess = { message ->
                PasswordResetResult.Success(message)
            },
            onFailure = { error ->
                val errorCode = when {
                    error.message?.contains("inválido") == true -> ErrorCode.INVALID_TOKEN
                    error.message?.contains("expirado") == true -> ErrorCode.EXPIRED_TOKEN
                    error.message?.contains("diferente") == true -> ErrorCode.SAME_PASSWORD
                    else -> ErrorCode.UNKNOWN
                }
                PasswordResetResult.Error(
                    message = error.message ?: "Error al restablecer contraseña",
                    code = errorCode
                )
            }
        )
    }
}

class ValidatePasswordUseCase {
    operator fun invoke(password: String): PasswordValidationResult {
        val errors = mutableListOf<String>()

        if (password.length < 8) {
            errors.add("Mínimo 8 caracteres")
        }
        if (!password.any { it.isUpperCase() }) {
            errors.add("Al menos una mayúscula")
        }
        if (!password.any { it.isLowerCase() }) {
            errors.add("Al menos una minúscula")
        }
        if (!password.any { it.isDigit() }) {
            errors.add("Al menos un número")
        }
        if (!password.any { !it.isLetterOrDigit() }) {
            errors.add("Al menos un carácter especial")
        }

        return if (errors.isEmpty()) {
            PasswordValidationResult.Valid
        } else {
            PasswordValidationResult.Invalid(errors.joinToString(", "))
        }
    }
}

sealed class PasswordValidationResult {
    object Valid : PasswordValidationResult()
    data class Invalid(val message: String) : PasswordValidationResult()
}
```

---

## Manejo de Errores

### Tabla de Errores y Mensajes para el Usuario

| Código HTTP | Error Backend | Mensaje para Usuario (ES) | Mensaje para Usuario (EN) |
|-------------|---------------|---------------------------|---------------------------|
| `400` | `Token already used or invalid` | "Este link ya fue utilizado o es inválido. Solicita uno nuevo" | "This link was already used or is invalid. Request a new one" |
| `400` | `Password must contain...` | "La contraseña debe tener al menos 8 caracteres, una mayúscula, una minúscula, un número y un carácter especial" | "Password must contain at least 8 characters, one uppercase, one lowercase, one number, and one special character" |
| `403` | `Invalid or expired token` | "El link ha expirado (30 min). Solicita uno nuevo" | "The link has expired (30 min). Request a new one" |
| `409` | `The new password must be different...` | "La nueva contraseña debe ser diferente a la anterior" | "The new password must be different from your current password" |
| `500` | `Internal server error` | "Error del servidor. Intenta de nuevo más tarde" | "Server error. Try again later" |
| Network | Connection timeout/error | "Error de conexión. Verifica tu internet" | "Connection error. Check your internet" |

### Ejemplo de Error Handler

```kotlin
// Android/Kotlin - Error Handler

object PasswordResetErrorHandler {
    fun handleError(error: Throwable): String {
        return when (error) {
            is HttpException -> {
                when (error.code()) {
                    400 -> "Link inválido o ya utilizado"
                    403 -> "El link ha expirado (30 min)"
                    409 -> "La nueva contraseña debe ser diferente"
                    500 -> "Error del servidor. Intenta más tarde"
                    else -> "Error ${error.code()}: ${error.message()}"
                }
            }
            is IOException -> "Error de conexión. Verifica tu internet"
            is SocketTimeoutException -> "Tiempo de espera agotado. Intenta de nuevo"
            else -> error.message ?: "Error desconocido"
        }
    }
}
```

---

## Deep Linking

### Configuración de Deep Links

#### Android (AndroidManifest.xml)

```xml
<activity
    android:name=".presentation.auth.ResetPasswordActivity"
    android:exported="true">

    <!-- Deep Link para reset password -->
    <intent-filter android:autoVerify="true">
        <action android:name="android.intent.action.VIEW" />
        <category android:name="android.intent.category.DEFAULT" />
        <category android:name="android.intent.category.BROWSABLE" />

        <!-- Esquema personalizado -->
        <data
            android:scheme="gt360"
            android:host="reset-password" />

        <!-- Universal Link (HTTPS) -->
        <data
            android:scheme="https"
            android:host="app.gt360.app"
            android:pathPrefix="/reset" />
    </intent-filter>
</activity>
```

#### iOS (Info.plist)

```xml
<!-- Custom URL Scheme -->
<key>CFBundleURLTypes</key>
<array>
    <dict>
        <key>CFBundleURLSchemes</key>
        <array>
            <string>gt360</string>
        </array>
        <key>CFBundleURLName</key>
        <string>com.gt360.app</string>
    </dict>
</array>

<!-- Universal Links -->
<key>com.apple.developer.associated-domains</key>
<array>
    <string>applinks:app.gt360.app</string>
</array>
```

### Manejo del Deep Link

#### Android (Kotlin)

```kotlin
// ResetPasswordActivity.kt

class ResetPasswordActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Capturar el token del deep link
        val token = when {
            // Desde deep link: gt360://reset-password?token=xxx
            intent?.data?.scheme == "gt360" -> {
                intent.data?.getQueryParameter("token")
            }
            // Desde universal link: https://app.gt360.app/reset?token=xxx
            intent?.data?.scheme == "https" -> {
                intent.data?.getQueryParameter("token")
            }
            else -> null
        }

        if (token.isNullOrBlank()) {
            // Mostrar error: Link inválido
            showError("Link de reset inválido")
            navigateToLogin()
        } else {
            // Continuar con el flujo normal
            viewModel.setResetToken(token)
        }
    }
}
```

#### iOS (Swift)

```swift
// AppDelegate.swift or SceneDelegate.swift

// Para Custom URL Scheme
func application(
    _ app: UIApplication,
    open url: URL,
    options: [UIApplication.OpenURLOptionsKey : Any] = [:]
) -> Bool {
    // gt360://reset-password?token=xxx
    guard url.scheme == "gt360",
          url.host == "reset-password",
          let components = URLComponents(url: url, resolvingAgainstBaseURL: true),
          let token = components.queryItems?.first(where: { $0.name == "token" })?.value else {
        return false
    }

    // Navegar a ResetPasswordScreen con el token
    navigateToResetPassword(token: token)
    return true
}

// Para Universal Links
func application(
    _ application: UIApplication,
    continue userActivity: NSUserActivity,
    restorationHandler: @escaping ([UIUserActivityRestoring]?) -> Void
) -> Bool {
    // https://app.gt360.app/reset?token=xxx
    guard userActivity.activityType == NSUserActivityTypeBrowsingWeb,
          let url = userActivity.webpageURL,
          url.host == "app.gt360.app",
          url.path == "/reset",
          let components = URLComponents(url: url, resolvingAgainstBaseURL: true),
          let token = components.queryItems?.first(where: { $0.name == "token" })?.value else {
        return false
    }

    // Navegar a ResetPasswordScreen con el token
    navigateToResetPassword(token: token)
    return true
}

private func navigateToResetPassword(token: String) {
    let resetVC = ResetPasswordViewController(token: token)
    if let window = UIApplication.shared.windows.first,
       let rootVC = window.rootViewController {
        rootVC.present(resetVC, animated: true)
    }
}
```

---

## Validaciones

### Validación de Email (Client-Side)

```kotlin
// Android/Kotlin
fun isValidEmail(email: String): Boolean {
    return android.util.Patterns.EMAIL_ADDRESS.matcher(email).matches()
}
```

```swift
// iOS/Swift
func isValidEmail(_ email: String) -> Bool {
    let emailRegex = "[A-Z0-9a-z._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,64}"
    let emailPredicate = NSPredicate(format:"SELF MATCHES %@", emailRegex)
    return emailPredicate.evaluate(with: email)
}
```

### Validación de Contraseña (Client-Side)

#### Requisitos:
- ✅ Mínimo 8 caracteres
- ✅ Al menos 1 letra mayúscula (A-Z)
- ✅ Al menos 1 letra minúscula (a-z)
- ✅ Al menos 1 número (0-9)
- ✅ Al menos 1 carácter especial (!@#$%^&*()_+-=[]{}|;:,.<>?)

```kotlin
// Android/Kotlin
data class PasswordStrength(
    val isValid: Boolean,
    val hasMinLength: Boolean,
    val hasUppercase: Boolean,
    val hasLowercase: Boolean,
    val hasNumber: Boolean,
    val hasSpecialChar: Boolean
)

fun validatePassword(password: String): PasswordStrength {
    val hasMinLength = password.length >= 8
    val hasUppercase = password.any { it.isUpperCase() }
    val hasLowercase = password.any { it.isLowerCase() }
    val hasNumber = password.any { it.isDigit() }
    val hasSpecialChar = password.any { !it.isLetterOrDigit() }

    val isValid = hasMinLength && hasUppercase && hasLowercase && hasNumber && hasSpecialChar

    return PasswordStrength(
        isValid = isValid,
        hasMinLength = hasMinLength,
        hasUppercase = hasUppercase,
        hasLowercase = hasLowercase,
        hasNumber = hasNumber,
        hasSpecialChar = hasSpecialChar
    )
}
```

```swift
// iOS/Swift
struct PasswordStrength {
    let isValid: Bool
    let hasMinLength: Bool
    let hasUppercase: Bool
    let hasLowercase: Bool
    let hasNumber: Bool
    let hasSpecialChar: Bool
}

func validatePassword(_ password: String) -> PasswordStrength {
    let hasMinLength = password.count >= 8
    let hasUppercase = password.range(of: "[A-Z]", options: .regularExpression) != nil
    let hasLowercase = password.range(of: "[a-z]", options: .regularExpression) != nil
    let hasNumber = password.range(of: "[0-9]", options: .regularExpression) != nil
    let hasSpecialChar = password.range(of: "[^A-Za-z0-9]", options: .regularExpression) != nil

    let isValid = hasMinLength && hasUppercase && hasLowercase && hasNumber && hasSpecialChar

    return PasswordStrength(
        isValid: isValid,
        hasMinLength: hasMinLength,
        hasUppercase: hasUppercase,
        hasLowercase: hasLowercase,
        hasNumber: hasNumber,
        hasSpecialChar: hasSpecialChar
    )
}
```

### UI de Validación en Tiempo Real

```kotlin
// Android/Kotlin - Composable Example
@Composable
fun PasswordStrengthIndicator(password: String) {
    val strength = validatePassword(password)

    Column {
        Text("Requisitos de contraseña:")
        PasswordRequirement("Mínimo 8 caracteres", strength.hasMinLength)
        PasswordRequirement("Una letra mayúscula", strength.hasUppercase)
        PasswordRequirement("Una letra minúscula", strength.hasLowercase)
        PasswordRequirement("Un número", strength.hasNumber)
        PasswordRequirement("Un carácter especial", strength.hasSpecialChar)
    }
}

@Composable
fun PasswordRequirement(text: String, isMet: Boolean) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(
            imageVector = if (isMet) Icons.Default.Check else Icons.Default.Close,
            contentDescription = null,
            tint = if (isMet) Color.Green else Color.Red
        )
        Spacer(modifier = Modifier.width(8.dp))
        Text(
            text = text,
            color = if (isMet) Color.Green else Color.Gray
        )
    }
}
```

---

## Casos de Prueba

### Test Cases para QA

| # | Caso de Prueba | Input | Resultado Esperado |
|---|----------------|-------|-------------------|
| 1 | Email válido existente | `driver@example.com` | Recibe email con link |
| 2 | Email válido NO existente | `noexiste@example.com` | Mensaje genérico (sin revelar) |
| 3 | Email inválido | `invalidemail` | Error 400: formato inválido |
| 4 | Token válido + contraseña válida | Token correcto + `Pass123!` | 200 OK, password actualizado |
| 5 | Token expirado (>30 min) | Token viejo | 403: Token expirado |
| 6 | Token ya utilizado | Token reutilizado | 400: Token ya usado |
| 7 | Contraseña débil (sin mayúscula) | `password123!` | 400: Password requirements |
| 8 | Contraseña débil (sin número) | `Password!` | 400: Password requirements |
| 9 | Contraseña débil (sin especial) | `Password123` | 400: Password requirements |
| 10 | Contraseña débil (< 8 chars) | `Pass1!` | 400: Password requirements |
| 11 | Nueva contraseña igual a actual | Misma password | 409: Must be different |
| 12 | Contraseñas no coinciden | Pass1 ≠ Pass2 | Error en UI antes de enviar |
| 13 | Sin conexión a internet | Cualquier request | Error de red |
| 14 | Deep link con token inválido | `gt360://reset-password?token=abc` | UI muestra "Link inválido" |
| 15 | Deep link sin token | `gt360://reset-password` | UI muestra "Link inválido" |

---

## Checklist de Implementación

### Backend (Ya está listo ✅)
- [x] Endpoint `/forgot-password` funcional
- [x] Endpoint `/reset-password` funcional
- [x] Generación de tokens JWT
- [x] Envío de emails automático
- [x] Validación de contraseñas
- [x] Expiración de tokens (30 min)
- [x] One-time use tokens

### Frontend Móvil (Por implementar)

#### Pantallas
- [ ] Pantalla "Forgot Password"
  - [ ] Input de email
  - [ ] Validación de email en tiempo real
  - [ ] Botón "Enviar Link"
  - [ ] Manejo de loading state
  - [ ] Mensaje de éxito
- [ ] Pantalla "Reset Password"
  - [ ] Input de nueva contraseña (secure)
  - [ ] Input de confirmar contraseña (secure)
  - [ ] Validación de fortaleza en tiempo real
  - [ ] Indicadores visuales de requisitos
  - [ ] Botón "Restablecer" (disabled hasta validar)
  - [ ] Manejo de loading state
  - [ ] Manejo de errores

#### Navegación
- [ ] Link "¿Olvidaste tu contraseña?" en Login
- [ ] Navegación desde Forgot Password a éxito
- [ ] Navegación desde Reset Password a Login
- [ ] Deep link handling configurado
  - [ ] Custom URL Scheme: `gt360://reset-password`
  - [ ] Universal Links: `https://app.gt360.app/reset`

#### API Integration
- [ ] Servicio/Cliente HTTP configurado
  - [ ] Base URL configurada
  - [ ] Content-Type headers
  - [ ] Timeout configurado (30s recomendado)
- [ ] Repository implementado
  - [ ] `requestPasswordReset(email)`
  - [ ] `resetPassword(token, newPassword)`
- [ ] Use Cases implementados
  - [ ] `RequestPasswordResetUseCase`
  - [ ] `ResetPasswordUseCase`
  - [ ] `ValidatePasswordUseCase`

#### Validaciones
- [ ] Validación de email (regex)
- [ ] Validación de contraseña
  - [ ] Mínimo 8 caracteres
  - [ ] Una mayúscula
  - [ ] Una minúscula
  - [ ] Un número
  - [ ] Un carácter especial
- [ ] Validación de "passwords match"

#### Error Handling
- [ ] Manejo de errores HTTP
  - [ ] 400: Token inválido/usado
  - [ ] 403: Token expirado
  - [ ] 409: Password igual a anterior
  - [ ] 500: Error de servidor
- [ ] Manejo de errores de red
  - [ ] Sin conexión
  - [ ] Timeout
- [ ] Mensajes de error user-friendly (localizados)

#### Testing
- [ ] Unit tests para validaciones
- [ ] Unit tests para use cases
- [ ] Integration tests para API calls
- [ ] UI tests para flujo completo
- [ ] Test de deep linking
- [ ] Test con token expirado
- [ ] Test con token inválido
- [ ] Test sin conexión

#### Extras (Opcional)
- [ ] Analítica de eventos
  - [ ] "forgot_password_clicked"
  - [ ] "reset_password_requested"
  - [ ] "reset_password_success"
  - [ ] "reset_password_failed"
- [ ] Localización (i18n)
  - [ ] Español
  - [ ] Inglés
- [ ] Accessibility
  - [ ] Screen reader support
  - [ ] Content descriptions
  - [ ] Minimum touch targets
- [ ] Dark mode support

---

## Resumen Final

### Lo que el Backend ya tiene ✅

1. **Endpoint de Forgot Password** (`POST /v1/auth/forgot-password`)
   - Genera token JWT
   - Envía email automáticamente
   - Seguro contra enumeración

2. **Endpoint de Reset Password** (`POST /v1/auth/reset-password`)
   - Valida token
   - Valida fortaleza de contraseña
   - One-time use
   - Expira en 30 minutos

3. **Email Template profesional**
   - HTML responsive
   - Link clickeable
   - Instrucciones claras

### Lo que necesitas implementar en Mobile 📱

1. **2 Pantallas**:
   - Forgot Password (input de email)
   - Reset Password (inputs de contraseña)

2. **2 API Calls**:
   - POST `/v1/auth/forgot-password`
   - POST `/v1/auth/reset-password`

3. **Deep Linking**:
   - Capturar `gt360://reset-password?token=xxx`
   - O `https://app.gt360.app/reset?token=xxx`

4. **Validaciones Client-Side**:
   - Email válido
   - Contraseña fuerte (8+ chars, mayús, minús, número, especial)
   - Passwords match

5. **Error Handling**:
   - Token expirado
   - Token inválido
   - Contraseña débil
   - Errores de red

---

**¿Listo para implementar?** Con este documento tienes todo lo necesario para integrar el password reset en tu app móvil. 🚀

---

**Soporte:**
- Backend: `https://dev-api.gt360.app` (Dev) | `https://api.gt360.app` (Prod)
- Documentación adicional: `/home/backend/GT360/docs/`
- Contact: GT360 Backend Team

**Última actualización:** 2026-02-07
