# Configuración de Archivos .well-known para Universal Links

**Dominio Frontend:** `https://dev.gt360.app`
**Fecha:** 2026-02-07

---

## Resumen

Para que los Universal Links funcionen y la app móvil capture los links del email, necesitas crear 2 archivos en tu frontend.

---

## 1. iOS - apple-app-site-association

**Ubicación en tu frontend:**
```
/public/.well-known/apple-app-site-association
```

**Contenido del archivo:**

```json
{
  "applinks": {
    "apps": [],
    "details": [
      {
        "appID": "TEAM_ID.com.gt360.driver",
        "paths": ["/reset", "/reset/*"]
      }
    ]
  }
}
```

**⚠️ IMPORTANTE:**
- Reemplaza `TEAM_ID` con tu Apple Team ID (lo encuentras en Apple Developer Console)
- Reemplaza `com.gt360.driver` con tu Bundle ID real
- **NO agregues extensión** al archivo (sin `.json`)
- El archivo debe servirse sin extensión

**URL final:**
```
https://dev.gt360.app/.well-known/apple-app-site-association
```

**Content-Type requerido:**
```
application/json
```

---

## 2. Android - assetlinks.json

**Ubicación en tu frontend:**
```
/public/.well-known/assetlinks.json
```

**Contenido del archivo:**

```json
[{
  "relation": ["delegate_permission/common.handle_all_urls"],
  "target": {
    "namespace": "android_app",
    "package_name": "com.gt360.driver",
    "sha256_cert_fingerprints": [
      "TU_SHA256_FINGERPRINT_AQUI"
    ]
  }
}]
```

**⚠️ IMPORTANTE:**
- Reemplaza `com.gt360.driver` con tu Package Name real
- Reemplaza `TU_SHA256_FINGERPRINT_AQUI` con tu SHA256 Fingerprint

**URL final:**
```
https://dev.gt360.app/.well-known/assetlinks.json
```

**Content-Type requerido:**
```
application/json
```

---

## Cómo Obtener los Valores

### iOS - Team ID

1. Ve a [Apple Developer](https://developer.apple.com/account)
2. Log in
3. Ve a "Membership"
4. Copia tu "Team ID" (ej: `ABC123DEF4`)

### Android - SHA256 Fingerprint

**Para Debug (desarrollo):**
```bash
keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey -storepass android -keypass android | grep SHA256
```

**Para Release (producción):**
```bash
keytool -list -v -keystore /path/to/your/release.keystore -alias your_alias | grep SHA256
```

**Output esperado:**
```
SHA256: AB:CD:EF:12:34:56:78:90:AB:CD:EF:12:34:56:78:90:AB:CD:EF:12:34:56:78:90:AB:CD:EF:12:34:56:78:90
```

**⚠️ Importante:** Copia el SHA256 CON los dos puntos (`:`) - ejemplo:
```
"AB:CD:EF:12:34:56:78:90:AB:CD:EF:12:34:56:78:90:AB:CD:EF:12:34:56:78:90:AB:CD:EF:12:34:56:78:90"
```

---

## Configuración en la App Móvil

### Android - AndroidManifest.xml

```xml
<activity android:name=".MainActivity">
    <intent-filter android:autoVerify="true">
        <action android:name="android.intent.action.VIEW" />
        <category android:name="android.intent.category.DEFAULT" />
        <category android:name="android.intent.category.BROWSABLE" />

        <!-- Universal Link para dev.gt360.app -->
        <data
            android:scheme="https"
            android:host="dev.gt360.app"
            android:pathPrefix="/reset" />
    </intent-filter>
</activity>
```

### iOS - Info.plist

```xml
<!-- Associated Domains -->
<key>com.apple.developer.associated-domains</key>
<array>
    <string>applinks:dev.gt360.app</string>
</array>

<!-- Custom URL Scheme (opcional, para gt360://) -->
<key>CFBundleURLTypes</key>
<array>
    <dict>
        <key>CFBundleURLSchemes</key>
        <array>
            <string>gt360</string>
        </array>
    </dict>
</array>
```

---

## Estructura del Frontend

Si tu frontend es Next.js/React:

```
tu-frontend/
├── public/
│   └── .well-known/
│       ├── apple-app-site-association  (sin extensión)
│       └── assetlinks.json
├── src/
├── package.json
└── ...
```

**Next.js automáticamente sirve archivos de `/public`:**
- `public/.well-known/file` → `https://dev.gt360.app/.well-known/file`

---

## Verificación

### Después de desplegar, verifica que los archivos sean accesibles:

**iOS:**
```bash
curl https://dev.gt360.app/.well-known/apple-app-site-association
```

Debe retornar:
```json
{
  "applinks": {
    "apps": [],
    "details": [...]
  }
}
```

**Android:**
```bash
curl https://dev.gt360.app/.well-known/assetlinks.json
```

Debe retornar:
```json
[{
  "relation": ["delegate_permission/common.handle_all_urls"],
  "target": {...}
}]
```

**Headers importantes:**
```
Content-Type: application/json
Status: 200 OK
```

---

## Testing de Universal Links

### iOS

**Validador de Apple:**
```
https://search.developer.apple.com/appsearch-validation-tool/
```
- Ingresa: `https://dev.gt360.app/.well-known/apple-app-site-association`
- Debe pasar la validación

**Test en Simulator:**
```bash
xcrun simctl openurl booted "https://dev.gt360.app/reset?token=TEST123"
```

### Android

**Test con adb:**
```bash
adb shell am start -a android.intent.action.VIEW \
  -d "https://dev.gt360.app/reset?token=TEST123" \
  com.gt360.driver
```

**Verificar configuración:**
```bash
adb shell dumpsys package domain-preferred-apps | grep -A 10 "com.gt360.driver"
```

---

## Checklist de Implementación

### Frontend (dev.gt360.app)
- [ ] Crear carpeta `/public/.well-known/`
- [ ] Crear archivo `apple-app-site-association` (sin extensión)
  - [ ] Reemplazar `TEAM_ID` con tu Apple Team ID
  - [ ] Reemplazar `com.gt360.driver` con tu Bundle ID
- [ ] Crear archivo `assetlinks.json`
  - [ ] Reemplazar `com.gt360.driver` con tu Package Name
  - [ ] Reemplazar SHA256 fingerprint (debug + release)
- [ ] Desplegar frontend
- [ ] Verificar con curl que los archivos sean accesibles

### Mobile App
- [ ] Android: Actualizar `AndroidManifest.xml`
  - [ ] Cambiar `app.gt360.app` → `dev.gt360.app`
  - [ ] Agregar `android:autoVerify="true"`
- [ ] iOS: Actualizar `Info.plist`
  - [ ] Cambiar `applinks:app.gt360.app` → `applinks:dev.gt360.app`
  - [ ] Configurar en Apple Developer Console
- [ ] Test con simulador/emulador
- [ ] Test en dispositivo real

### Testing
- [ ] iOS: Validar con Apple's tool
- [ ] Android: Verificar con adb dumpsys
- [ ] Test funcional: Click en link del email
- [ ] Verificar que abre la app (no el navegador)
- [ ] Verificar que extrae el token correctamente

---

## Ejemplo Completo para dev.gt360.app

### apple-app-site-association

```json
{
  "applinks": {
    "apps": [],
    "details": [
      {
        "appID": "ABC123DEF4.com.gt360.driver",
        "paths": ["/reset", "/reset/*"]
      }
    ]
  }
}
```

### assetlinks.json

```json
[{
  "relation": ["delegate_permission/common.handle_all_urls"],
  "target": {
    "namespace": "android_app",
    "package_name": "com.gt360.driver",
    "sha256_cert_fingerprints": [
      "AB:CD:EF:12:34:56:78:90:AB:CD:EF:12:34:56:78:90:AB:CD:EF:12:34:56:78:90:AB:CD:EF:12:34:56:78:90"
    ]
  }
}]
```

---

## Notas Finales

1. **Los archivos deben ser accesibles públicamente** (sin autenticación)
2. **Content-Type debe ser `application/json`**
3. **No usar cache** (o cache corto) para estos archivos
4. **HTTPS es obligatorio** (no funciona con HTTP)
5. **El dominio debe coincidir exactamente** (`dev.gt360.app`)

---

**¿Listo para crear los archivos?** Solo necesitas:
1. Tu Apple Team ID
2. Tu Android SHA256 Fingerprint
3. Copiar los archivos a `/public/.well-known/` en tu frontend
4. Desplegar

---

**Última actualización:** 2026-02-07
