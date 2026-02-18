# Guía Móvil: Contacto a Soporte para Drivers

**Plataformas:** Android & iOS
**Backend:** `https://api.gt360.app` (Prod) | `https://dev-api.gt360.app` (Dev)
**Versión:** 1.0
**Fecha:** 2026-02-07

---

## Resumen

Sistema de contacto directo a soporte para drivers. Envía mensajes por email a `admin@gt360.app` sin necesidad de autenticación.

**Características:**
- ✅ Sin autenticación requerida
- ✅ Email automático al equipo de soporte
- ✅ Categorización de mensajes
- ✅ Reply-to configurado al email del driver

---

## Endpoint

```
POST /v1/support/contact
```

**Autenticación:** No requerida
**Content-Type:** application/json

---

## Request

```json
{
  "name": "Juan González",
  "email": "juan.driver@example.com",
  "category": "bug",
  "subject": "Error al iniciar viaje",
  "message": "Cuando presiono el botón de iniciar viaje, la app se congela y no responde. He intentado reiniciar pero el problema persiste."
}
```

### Campos del Request

| Campo | Tipo | Requerido | Descripción | Ejemplo |
|-------|------|-----------|-------------|---------|
| `name` | string | **Sí** | Nombre completo | `"Juan González"` |
| `email` | string | **Sí** | Email válido | `"juan@example.com"` |
| `category` | enum | **Sí** | Categoría | `"bug"` |
| `subject` | string | **Sí** | Asunto | `"Error al iniciar viaje"` |
| `message` | string | **Sí** | Mensaje detallado | `"Descripción..."` |

---

## Categorías

| Código | Display | Icono | Cuándo usar |
|--------|---------|-------|-------------|
| `bug` | Reportar un error | 🐛 | Errores, crashes, bugs |
| `feature` | Solicitar función | ✨ | Nuevas funcionalidades |
| `question` | Hacer pregunta | ❓ | Dudas sobre el uso |
| `other` | Otro | 📝 | Otros temas |

---

## Response

### Success (200 OK)

```json
{
  "success": true,
  "message": "Your message has been sent successfully"
}
```

### Errors

| Código | Mensaje | Descripción |
|--------|---------|-------------|
| `422` | `"value is not a valid email address"` | Email inválido |
| `422` | `"field required"` | Falta campo obligatorio |
| `422` | `"value is not a valid enumeration member"` | Categoría inválida |
| `500` | `"Failed to send message. Please try again later."` | Error al enviar |

---

## Implementación

### Kotlin (Android)

```kotlin
// Modelos
enum class SupportCategory(val value: String, val display: String, val icon: String) {
    BUG("bug", "Reportar un error", "🐛"),
    FEATURE("feature", "Solicitar función", "✨"),
    QUESTION("question", "Hacer pregunta", "❓"),
    OTHER("other", "Otro", "📝")
}

data class SupportRequest(
    val name: String,
    val email: String,
    val category: String,
    val subject: String,
    val message: String
)

data class SupportResponse(
    val success: Boolean,
    val message: String
)

// API Call
suspend fun sendSupportMessage(request: SupportRequest): Result<String> {
    return try {
        val response = httpClient.post("$BASE_URL/v1/support/contact") {
            contentType(ContentType.Application.Json)
            setBody(request)
        }

        if (response.status == HttpStatusCode.OK) {
            val body = response.body<SupportResponse>()
            Result.success(body.message)
        } else {
            val error = response.body<ErrorResponse>()
            Result.failure(Exception(error.detail))
        }
    } catch (e: Exception) {
        Result.failure(e)
    }
}

// Validación
fun validateSupportForm(
    name: String,
    email: String,
    subject: String,
    message: String
): Map<String, String> {
    val errors = mutableMapOf<String, String>()

    if (name.isBlank()) {
        errors["name"] = "El nombre es requerido"
    }

    if (!android.util.Patterns.EMAIL_ADDRESS.matcher(email).matches()) {
        errors["email"] = "Email inválido"
    }

    if (subject.length < 5) {
        errors["subject"] = "El asunto debe tener al menos 5 caracteres"
    }

    if (message.length < 20) {
        errors["message"] = "El mensaje debe tener al menos 20 caracteres"
    }

    return errors
}

// Uso en ViewModel
class SupportViewModel : ViewModel() {
    var name by mutableStateOf("")
    var email by mutableStateOf("")
    var category by mutableStateOf(SupportCategory.QUESTION)
    var subject by mutableStateOf("")
    var message by mutableStateOf("")
    var isLoading by mutableStateOf(false)
    var showSuccess by mutableStateOf(false)
    var error by mutableStateOf<String?>(null)

    fun onSubmit() {
        viewModelScope.launch {
            val errors = validateSupportForm(name, email, subject, message)
            if (errors.isNotEmpty()) {
                error = errors.values.first()
                return@launch
            }

            isLoading = true
            error = null

            val result = sendSupportMessage(
                SupportRequest(
                    name = name.trim(),
                    email = email.trim(),
                    category = category.value,
                    subject = subject.trim(),
                    message = message.trim()
                )
            )

            isLoading = false

            result.fold(
                onSuccess = {
                    showSuccess = true
                    clearForm()
                },
                onFailure = { e ->
                    error = e.message ?: "Error al enviar"
                }
            )
        }
    }

    private fun clearForm() {
        name = ""
        email = ""
        category = SupportCategory.QUESTION
        subject = ""
        message = ""
    }
}
```

### Swift (iOS)

```swift
// Modelos
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

struct SupportRequest: Codable {
    let name: String
    let email: String
    let category: String
    let subject: String
    let message: String
}

struct SupportResponse: Codable {
    let success: Bool
    let message: String
}

// API Call
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

    let body = SupportRequest(
        name: name,
        email: email,
        category: category.rawValue,
        subject: subject,
        message: message
    )
    request.httpBody = try JSONEncoder().encode(body)

    let (data, response) = try await URLSession.shared.data(for: request)

    guard let httpResponse = response as? HTTPURLResponse else {
        throw SupportError.invalidResponse
    }

    if httpResponse.statusCode == 200 {
        let result = try JSONDecoder().decode(SupportResponse.self, from: data)
        return result.message
    } else if httpResponse.statusCode == 422 {
        let error = try JSONDecoder().decode(ErrorResponse.self, from: data)
        throw SupportError.validationError(error.detail)
    } else {
        throw SupportError.serverError
    }
}

// Validación
func validateSupportForm(
    name: String,
    email: String,
    subject: String,
    message: String
) -> [String: String] {
    var errors: [String: String] = [:]

    if name.isEmpty {
        errors["name"] = "El nombre es requerido"
    }

    let emailRegex = "[A-Z0-9a-z._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,64}"
    let emailPredicate = NSPredicate(format:"SELF MATCHES %@", emailRegex)
    if !emailPredicate.evaluate(with: email) {
        errors["email"] = "Email inválido"
    }

    if subject.count < 5 {
        errors["subject"] = "El asunto debe tener al menos 5 caracteres"
    }

    if message.count < 20 {
        errors["message"] = "El mensaje debe tener al menos 20 caracteres"
    }

    return errors
}

// ViewModel
@MainActor
class SupportViewModel: ObservableObject {
    @Published var name = ""
    @Published var email = ""
    @Published var category: SupportCategory = .question
    @Published var subject = ""
    @Published var message = ""
    @Published var isLoading = false
    @Published var showSuccess = false
    @Published var errorMessage: String?

    func submit() async {
        let errors = validateSupportForm(
            name: name,
            email: email,
            subject: subject,
            message: message
        )

        if !errors.isEmpty {
            errorMessage = errors.values.first
            return
        }

        isLoading = true
        errorMessage = nil

        do {
            let result = try await sendSupportMessage(
                name: name.trimmingCharacters(in: .whitespaces),
                email: email.trimmingCharacters(in: .whitespaces),
                category: category,
                subject: subject.trimmingCharacters(in: .whitespaces),
                message: message.trimmingCharacters(in: .whitespaces)
            )

            showSuccess = true
            clearForm()
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    private func clearForm() {
        name = ""
        email = ""
        category = .question
        subject = ""
        message = ""
    }
}
```

---

## UI Recomendada

### Pantalla de Soporte

```
┌─────────────────────────────────────┐
│  ←  Contactar a Soporte             │
├─────────────────────────────────────┤
│                                     │
│  Nombre *                           │
│  ┌───────────────────────────────┐ │
│  │ Juan González                 │ │
│  └───────────────────────────────┘ │
│                                     │
│  Email *                            │
│  ┌───────────────────────────────┐ │
│  │ juan@example.com              │ │
│  └───────────────────────────────┘ │
│                                     │
│  Categoría *                        │
│  ┌───────────────────────────────┐ │
│  │ ❓ Hacer una pregunta     ▼   │ │
│  └───────────────────────────────┘ │
│                                     │
│  Asunto *                           │
│  ┌───────────────────────────────┐ │
│  │                               │ │
│  └───────────────────────────────┘ │
│                                     │
│  Mensaje * (min 20 caracteres)      │
│  ┌───────────────────────────────┐ │
│  │                               │ │
│  │                               │ │
│  │                               │ │
│  │                               │ │
│  └───────────────────────────────┘ │
│  120 caracteres                     │
│                                     │
│  ┌───────────────────────────────┐ │
│  │      Enviar Mensaje           │ │
│  └───────────────────────────────┘ │
│                                     │
│  Cancelar                           │
│                                     │
└─────────────────────────────────────┘
```

### Dialog de Éxito

```
┌─────────────────────────────────────┐
│                                     │
│          ✅                          │
│                                     │
│    ¡Mensaje Enviado!                │
│                                     │
│  Tu mensaje fue enviado exitosa-    │
│  mente. El equipo de soporte se     │
│  pondrá en contacto contigo pronto. │
│                                     │
│  ┌───────────────────────────────┐ │
│  │          Aceptar              │ │
│  └───────────────────────────────┘ │
│                                     │
└─────────────────────────────────────┘
```

---

## Validaciones

### Client-Side

| Campo | Validación | Mensaje de Error |
|-------|------------|------------------|
| Nombre | No vacío | "El nombre es requerido" |
| Email | Formato válido | "Email inválido" |
| Categoría | Enum válido | "Selecciona una categoría" |
| Asunto | Min 5 caracteres | "Mínimo 5 caracteres" |
| Mensaje | Min 20 caracteres | "Mínimo 20 caracteres" |

### Ejemplo de Validación

```kotlin
// Kotlin
val errors = mutableMapOf<String, String>()

if (name.isBlank()) errors["name"] = "El nombre es requerido"
if (!Patterns.EMAIL_ADDRESS.matcher(email).matches()) errors["email"] = "Email inválido"
if (subject.length < 5) errors["subject"] = "Mínimo 5 caracteres"
if (message.length < 20) errors["message"] = "Mínimo 20 caracteres"

if (errors.isEmpty()) {
    // Enviar al backend
    sendSupportMessage()
} else {
    // Mostrar primer error
    showError(errors.values.first())
}
```

---

## Flujo Completo

```
1. MENÚ/SETTINGS
   └─ Tap "Ayuda y Soporte"
      │
      ▼
2. PANTALLA: CONTACTAR SOPORTE
   ├─ Pre-fill nombre (si está logueado)
   ├─ Pre-fill email (si está logueado)
   ├─ Seleccionar categoría
   ├─ Escribir asunto
   └─ Escribir mensaje
      │
      │ [Tap "Enviar Mensaje"]
      │
      ▼
3. VALIDACIÓN CLIENT-SIDE
   ├─ Nombre no vacío ✓
   ├─ Email válido ✓
   ├─ Asunto min 5 chars ✓
   └─ Mensaje min 20 chars ✓
      │
      │ [Si válido]
      │
      ▼
4. MOSTRAR LOADING
   └─ "Enviando tu mensaje..."
      │
      ▼
5. API CALL
   POST /v1/support/contact
   Body: { name, email, category, subject, message }
      │
      ▼
6. RESPONSE 200 OK
   { "success": true, "message": "..." }
      │
      ▼
7. OCULTAR LOADING
   └─ Mostrar Dialog de Éxito
      │
      ▼
8. BACKEND ENVÍA EMAIL
   ├─ From: GT 360 Support <no-reply@gt360.app>
   ├─ To: admin@gt360.app
   ├─ Reply-To: juan.driver@example.com
   └─ Subject: [BUG] Error al iniciar viaje
      │
      ▼
9. EQUIPO DE SOPORTE RECIBE
   └─ Puede responder directamente al email del driver
      │
      ▼
10. DRIVER RECIBE RESPUESTA
    └─ En su email juan.driver@example.com
```

---

## Código Completo

### Kotlin (Android)

```kotlin
// SupportRepository.kt
interface SupportRepository {
    suspend fun sendMessage(
        name: String,
        email: String,
        category: SupportCategory,
        subject: String,
        message: String
    ): Result<String>
}

class SupportRepositoryImpl(
    private val apiClient: ApiClient
) : SupportRepository {

    override suspend fun sendMessage(
        name: String,
        email: String,
        category: SupportCategory,
        subject: String,
        message: String
    ): Result<String> {
        return try {
            val request = SupportRequest(
                name = name,
                email = email,
                category = category.value,
                subject = subject,
                message = message
            )

            val response = apiClient.post<SupportResponse>(
                endpoint = "/v1/support/contact",
                body = request
            )

            if (response.success) {
                Result.success(response.message)
            } else {
                Result.failure(Exception("Error al enviar mensaje"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}

// SupportViewModel.kt
class SupportViewModel(
    private val repository: SupportRepository,
    private val userRepository: UserRepository
) : ViewModel() {

    var uiState by mutableStateOf(SupportUiState())
        private set

    init {
        // Pre-fill con datos del usuario si está logueado
        viewModelScope.launch {
            userRepository.getCurrentUser()?.let { user ->
                uiState = uiState.copy(
                    name = "${user.first_name} ${user.last_name}".trim(),
                    email = user.email
                )
            }
        }
    }

    fun onNameChanged(name: String) {
        uiState = uiState.copy(name = name, errors = uiState.errors - "name")
    }

    fun onEmailChanged(email: String) {
        uiState = uiState.copy(email = email, errors = uiState.errors - "email")
    }

    fun onCategoryChanged(category: SupportCategory) {
        uiState = uiState.copy(category = category)
    }

    fun onSubjectChanged(subject: String) {
        uiState = uiState.copy(subject = subject, errors = uiState.errors - "subject")
    }

    fun onMessageChanged(message: String) {
        uiState = uiState.copy(message = message, errors = uiState.errors - "message")
    }

    fun onSubmit() {
        val errors = validateSupportForm(
            uiState.name,
            uiState.email,
            uiState.subject,
            uiState.message
        )

        if (errors.isNotEmpty()) {
            uiState = uiState.copy(errors = errors)
            return
        }

        viewModelScope.launch {
            uiState = uiState.copy(isLoading = true, generalError = null)

            val result = repository.sendMessage(
                name = uiState.name.trim(),
                email = uiState.email.trim(),
                category = uiState.category,
                subject = uiState.subject.trim(),
                message = uiState.message.trim()
            )

            result.fold(
                onSuccess = { message ->
                    uiState = uiState.copy(
                        isLoading = false,
                        showSuccessDialog = true,
                        successMessage = message
                    )
                },
                onFailure = { error ->
                    uiState = uiState.copy(
                        isLoading = false,
                        generalError = error.message ?: "Error al enviar"
                    )
                }
            )
        }
    }

    fun onSuccessDialogDismiss() {
        uiState = SupportUiState()
    }
}

data class SupportUiState(
    val name: String = "",
    val email: String = "",
    val category: SupportCategory = SupportCategory.QUESTION,
    val subject: String = "",
    val message: String = "",
    val isLoading: Boolean = false,
    val errors: Map<String, String> = emptyMap(),
    val generalError: String? = null,
    val showSuccessDialog: Boolean = false,
    val successMessage: String = ""
)
```

### Swift (iOS)

```swift
// SupportRepository.swift
protocol SupportRepository {
    func sendMessage(
        name: String,
        email: String,
        category: SupportCategory,
        subject: String,
        message: String
    ) async throws -> String
}

class SupportRepositoryImpl: SupportRepository {

    private let apiClient: APIClient

    init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    func sendMessage(
        name: String,
        email: String,
        category: SupportCategory,
        subject: String,
        message: String
    ) async throws -> String {

        let request = SupportRequest(
            name: name,
            email: email,
            category: category.rawValue,
            subject: subject,
            message: message
        )

        let response: SupportResponse = try await apiClient.post(
            endpoint: "/v1/support/contact",
            body: request
        )

        if response.success {
            return response.message
        } else {
            throw SupportError.sendFailed
        }
    }
}

// SupportViewModel.swift
@MainActor
class SupportViewModel: ObservableObject {
    @Published var name = ""
    @Published var email = ""
    @Published var category: SupportCategory = .question
    @Published var subject = ""
    @Published var message = ""
    @Published var isLoading = false
    @Published var errors: [String: String] = [:]
    @Published var generalError: String?
    @Published var showSuccessDialog = false

    private let repository: SupportRepository
    private let userRepository: UserRepository

    init(repository: SupportRepository, userRepository: UserRepository) {
        self.repository = repository
        self.userRepository = userRepository

        // Pre-fill con datos del usuario
        Task {
            if let user = try? await userRepository.getCurrentUser() {
                name = "\(user.firstName ?? "") \(user.lastName ?? "")".trimmingCharacters(in: .whitespaces)
                email = user.email
            }
        }
    }

    func submit() async {
        let validationErrors = validateSupportForm(
            name: name,
            email: email,
            subject: subject,
            message: message
        )

        if !validationErrors.isEmpty {
            errors = validationErrors
            return
        }

        isLoading = true
        generalError = nil
        errors = [:]

        do {
            let _ = try await repository.sendMessage(
                name: name.trimmingCharacters(in: .whitespaces),
                email: email.trimmingCharacters(in: .whitespaces),
                category: category,
                subject: subject.trimmingCharacters(in: .whitespaces),
                message: message.trimmingCharacters(in: .whitespaces)
            )

            showSuccessDialog = true
            clearForm()
        } catch {
            generalError = error.localizedDescription
        }

        isLoading = false
    }

    private func clearForm() {
        name = ""
        email = ""
        category = .question
        subject = ""
        message = ""
    }
}
```

---

## Casos de Prueba

| # | Caso | Input | Resultado Esperado |
|---|------|-------|-------------------|
| 1 | Todos los campos válidos | Datos completos | 200 OK, mensaje enviado |
| 2 | Email inválido | `invalidemail` | Error: "Email inválido" |
| 3 | Nombre vacío | `""` | Error: "Nombre requerido" |
| 4 | Asunto corto | `"Hola"` | Error: "Mínimo 5 chars" |
| 5 | Mensaje corto | `"Test"` | Error: "Mínimo 20 chars" |
| 6 | Categoría inválida | `"invalid"` | 422 Error |
| 7 | Sin internet | - | Error de conexión |
| 8 | Pre-fill con usuario logueado | - | Nombre y email pre-filled |

---

## Ejemplo CURL

```bash
curl -X POST "https://api.gt360.app/v1/support/contact" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Juan González",
    "email": "juan@example.com",
    "category": "bug",
    "subject": "Error al iniciar viaje",
    "message": "Descripción detallada del problema que estoy experimentando en la aplicación móvil."
  }'
```

**Response:**
```json
{
  "success": true,
  "message": "Your message has been sent successfully"
}
```

---

## Checklist de Implementación

### UI/UX
- [ ] Pantalla "Contactar Soporte"
- [ ] Input: Nombre
- [ ] Input: Email
- [ ] Selector: Categoría (4 opciones)
- [ ] Input: Asunto
- [ ] TextArea: Mensaje (multiline)
- [ ] Contador de caracteres en mensaje
- [ ] Botón "Enviar Mensaje"
- [ ] Botón "Cancelar"
- [ ] Loading indicator
- [ ] Dialog de éxito
- [ ] Manejo de errores inline

### Lógica
- [ ] Repository implementado
- [ ] ViewModel/Presenter implementado
- [ ] Pre-fill con datos del usuario (si está logueado)
- [ ] Validación de email
- [ ] Validación de longitud de campos
- [ ] API call con error handling
- [ ] Limpiar formulario después de éxito

### Navegación
- [ ] Opción en Menú/Settings
- [ ] Label: "Ayuda y Soporte"
- [ ] Icono apropiado
- [ ] Navega a SupportScreen

### Testing
- [ ] Unit tests para validaciones
- [ ] Unit tests para ViewModel
- [ ] Integration test para API call
- [ ] UI test para flujo completo
- [ ] Test sin conexión
- [ ] Test con campos vacíos

---

## Ejemplo de Uso Completo

### Kotlin (Jetpack Compose)

```kotlin
@Composable
fun SupportScreen(
    viewModel: SupportViewModel = hiltViewModel(),
    onNavigateBack: () -> Unit
) {
    val uiState = viewModel.uiState

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Contactar a Soporte") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.Default.ArrowBack, "Volver")
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState())
        ) {
            // Nombre
            OutlinedTextField(
                value = uiState.name,
                onValueChange = viewModel::onNameChanged,
                label = { Text("Nombre *") },
                isError = uiState.errors.containsKey("name"),
                supportingText = uiState.errors["name"]?.let { { Text(it) } },
                modifier = Modifier.fillMaxWidth()
            )

            Spacer(modifier = Modifier.height(16.dp))

            // Email
            OutlinedTextField(
                value = uiState.email,
                onValueChange = viewModel::onEmailChanged,
                label = { Text("Email *") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                isError = uiState.errors.containsKey("email"),
                supportingText = uiState.errors["email"]?.let { { Text(it) } },
                modifier = Modifier.fillMaxWidth()
            )

            Spacer(modifier = Modifier.height(16.dp))

            // Categoría
            Text("Categoría *", style = MaterialTheme.typography.labelLarge)
            Spacer(modifier = Modifier.height(8.dp))
            SupportCategory.values().forEach { category ->
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { viewModel.onCategoryChanged(category) }
                        .padding(vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    RadioButton(
                        selected = uiState.category == category,
                        onClick = { viewModel.onCategoryChanged(category) }
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text("${category.icon} ${category.display}")
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // Asunto
            OutlinedTextField(
                value = uiState.subject,
                onValueChange = viewModel::onSubjectChanged,
                label = { Text("Asunto *") },
                isError = uiState.errors.containsKey("subject"),
                supportingText = uiState.errors["subject"]?.let { { Text(it) } },
                modifier = Modifier.fillMaxWidth()
            )

            Spacer(modifier = Modifier.height(16.dp))

            // Mensaje
            OutlinedTextField(
                value = uiState.message,
                onValueChange = viewModel::onMessageChanged,
                label = { Text("Mensaje *") },
                minLines = 5,
                maxLines = 10,
                isError = uiState.errors.containsKey("message"),
                supportingText = {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(uiState.errors["message"] ?: "Mínimo 20 caracteres")
                        Text("${uiState.message.length} caracteres")
                    }
                },
                modifier = Modifier.fillMaxWidth()
            )

            Spacer(modifier = Modifier.height(24.dp))

            // Error general
            if (uiState.generalError != null) {
                Card(
                    colors = CardDefaults.cardColors(containerColor = Color.Red.copy(alpha = 0.1f)),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(
                        text = uiState.generalError!!,
                        color = Color.Red,
                        modifier = Modifier.padding(12.dp)
                    )
                }
                Spacer(modifier = Modifier.height(16.dp))
            }

            // Botón Enviar
            Button(
                onClick = { viewModel.onSubmit() },
                enabled = !uiState.isLoading,
                modifier = Modifier.fillMaxWidth()
            ) {
                if (uiState.isLoading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(20.dp),
                        color = Color.White
                    )
                } else {
                    Text("Enviar Mensaje")
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Botón Cancelar
            OutlinedButton(
                onClick = onNavigateBack,
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("Cancelar")
            }
        }
    }

    // Success Dialog
    if (uiState.showSuccessDialog) {
        AlertDialog(
            onDismissRequest = {
                viewModel.onSuccessDialogDismiss()
                onNavigateBack()
            },
            icon = {
                Icon(
                    imageVector = Icons.Default.Check,
                    contentDescription = null,
                    tint = Color.Green,
                    modifier = Modifier.size(48.dp)
                )
            },
            title = { Text("¡Mensaje Enviado!") },
            text = {
                Text("Tu mensaje fue enviado exitosamente. El equipo de soporte se pondrá en contacto contigo pronto.")
            },
            confirmButton = {
                Button(
                    onClick = {
                        viewModel.onSuccessDialogDismiss()
                        onNavigateBack()
                    }
                ) {
                    Text("Aceptar")
                }
            }
        )
    }
}
```

### Swift (SwiftUI)

```swift
// SupportView.swift
struct SupportView: View {
    @StateObject private var viewModel: SupportViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationView {
            Form {
                Section {
                    TextField("Nombre *", text: $viewModel.name)
                        .autocapitalization(.words)

                    if let error = viewModel.errors["name"] {
                        Text(error)
                            .foregroundColor(.red)
                            .font(.caption)
                    }

                    TextField("Email *", text: $viewModel.email)
                        .keyboardType(.emailAddress)
                        .autocapitalization(.none)

                    if let error = viewModel.errors["email"] {
                        Text(error)
                            .foregroundColor(.red)
                            .font(.caption)
                    }
                }

                Section(header: Text("Categoría")) {
                    Picker("Selecciona una categoría", selection: $viewModel.category) {
                        ForEach(SupportCategory.allCases, id: \.self) { category in
                            Text(category.displayName).tag(category)
                        }
                    }
                    .pickerStyle(.menu)
                }

                Section {
                    TextField("Asunto *", text: $viewModel.subject)

                    if let error = viewModel.errors["subject"] {
                        Text(error)
                            .foregroundColor(.red)
                            .font(.caption)
                    }
                }

                Section(header: Text("Mensaje")) {
                    TextEditor(text: $viewModel.message)
                        .frame(minHeight: 100)

                    HStack {
                        if let error = viewModel.errors["message"] {
                            Text(error)
                                .foregroundColor(.red)
                                .font(.caption)
                        }
                        Spacer()
                        Text("\(viewModel.message.count) caracteres")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }

                if let error = viewModel.generalError {
                    Section {
                        Text(error)
                            .foregroundColor(.red)
                    }
                }

                Section {
                    Button(action: {
                        Task {
                            await viewModel.submit()
                        }
                    }) {
                        if viewModel.isLoading {
                            ProgressView()
                        } else {
                            Text("Enviar Mensaje")
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .disabled(viewModel.isLoading)

                    Button("Cancelar", role: .cancel) {
                        dismiss()
                    }
                }
            }
            .navigationTitle("Contactar a Soporte")
            .alert("¡Mensaje Enviado!", isPresented: $viewModel.showSuccessDialog) {
                Button("Aceptar") {
                    dismiss()
                }
            } message: {
                Text("Tu mensaje fue enviado exitosamente. El equipo de soporte se pondrá en contacto contigo pronto.")
            }
        }
    }
}
```

---

## Resumen

### Backend (Ya funcional ✅)
- Endpoint público `/v1/support/contact`
- Envío automático de emails
- Validación de datos
- Sin autenticación requerida

### Mobile App (Por implementar)
- 1 pantalla con formulario
- 5 campos de entrada
- Validaciones client-side
- 1 API call
- Manejo de errores
- Dialog de éxito

---

**Email de Soporte:** admin@gt360.app
**Última actualización:** 2026-02-07