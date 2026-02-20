# GT360 Auth & Token Management - Frontend Implementation Guide

Complete backend reference for implementing token lifecycle management, session recovery, and authentication error handling in the frontend.

---

## 1. Token Architecture

### Token Pair

| Token | Type | Duration | Storage | Transport |
|-------|------|----------|---------|-----------|
| **Access Token** | JWT (HS256) | 60 minutes | Client memory (never localStorage) | `Authorization: Bearer <token>` header |
| **Refresh Token** | Opaque (`secrets.token_urlsafe(64)`) | 30 days | HTTP-only cookie (auto-sent) + response body | Cookie auto-sent on same-domain requests |

### Authentication Flow Diagram

```mermaid
sequenceDiagram
    participant C as Frontend
    participant B as Backend

    C->>B: POST /v1/auth/sign-in {email, password}
    B-->>C: 200 {data: {session, refresh_token, user_data}}
    Note over C: Store access_token in memory<br/>Cookie refresh_token set automatically

    loop Every API Request
        C->>B: GET /v1/... (Authorization: Bearer <access_token>)
        B-->>C: 200 {data: ...}
    end

    Note over C: Token expires after 60 min
    C->>B: GET /v1/... (Authorization: Bearer <expired_token>)
    B-->>C: 401 {detail: "Invalid token"}

    C->>B: POST /v1/auth/refresh (cookie sent automatically)
    B-->>C: 200 {data: {session, refresh_token, user_data}}
    Note over C: Update access_token in memory<br/>New cookie set automatically

    C->>B: Retry original request with new token
    B-->>C: 200 {data: ...}
```

---

## 2. API Response Formats

### Sign-In Response (`POST /v1/auth/sign-in`)

```json
{
  "data": {
    "session": {
      "access_token": "eyJhbGciOiJIUzI1NiIs...",
      "expires_at": 1740000000,
      "type": "Bearer"
    },
    "refresh_token": {
      "refresh": "abc123...",
      "expires_at": "2026-03-21T15:30:00+00:00"
    },
    "user_data": {
      "id": "uuid-here",
      "email": "user@example.com",
      "phone": "+1234567890",
      "role": "manager",
      "first_name": "John",
      "last_name": "Doe",
      "profile_pic": "url-or-null",
      "organization_id": "org-uuid"
    }
  }
}
```

> **Note:** `session.expires_at` is a **Unix timestamp in seconds** (not milliseconds). Convert with `expires_at * 1000` for JavaScript `Date`.

### Refresh Response (`POST /v1/auth/refresh`)

Identical format to sign-in:

```json
{
  "data": {
    "session": {
      "access_token": "eyJhbGciOiJIUzI1NiIs...",
      "expires_at": 1740003600,
      "type": "Bearer"
    },
    "refresh_token": {
      "refresh": "new-token-abc...",
      "expires_at": "2026-03-21T15:30:00+00:00"
    },
    "user_data": {
      "id": "uuid-here",
      "email": "user@example.com",
      "role": "manager",
      ...
    }
  }
}
```

### Sign-Out Response (`POST /v1/auth/sign-out/`)

```json
{
  "message": "All cookies revoked"
}
```

Effects:
- Access token blacklisted in Redis for 5 minutes
- ALL refresh tokens for the user revoked in database
- Cookies `refresh_token` and `expires_at` deleted

### Roles in `user_data`

| Role | Extra fields in `user_data` |
|------|----------------------------|
| `manager` | `organization_id` |
| `driver` | `organization_id`, `location_id` |
| `crew` | (none extra) |

---

## 3. Auth Error Catalog

### HTTP Errors from Protected Endpoints (middleware)

These are returned by the `VerifyToken` middleware when accessing any protected endpoint:

| Status | `detail` value | Cause | Frontend Action |
|--------|---------------|-------|-----------------|
| **401** | `"Missing authentication token"` | No `Authorization` header or empty Bearer | **Silent refresh** |
| **401** | `"Invalid token"` | JWT expired, malformed, or bad signature | **Silent refresh** |
| **401** | `"Token revoked"` | Token blacklisted after sign-out | **Redirect to login** (do NOT refresh) |

### HTTP Errors from Refresh Endpoint (`POST /v1/auth/refresh`)

| Status | `detail` value | Cause | Frontend Action |
|--------|---------------|-------|-----------------|
| **401** | `"Missing refresh token"` | No cookie and no body field | **Redirect to login** |
| **401** | `"Invalid refresh token"` | Token hash not found in DB | **Redirect to login** |
| **401** | `"Refresh token expired or revoked"` | Token revoked flag is true | **Redirect to login** |
| **401** | `"Expired refresh"` | Token expired (>30 days) | **Redirect to login** |

### Authorization Errors (role-based)

| Status | `detail` value | Cause | Frontend Action |
|--------|---------------|-------|-----------------|
| **403** | `"Not Authorized: We couldn't validate the role"` | User role not allowed for endpoint | **Show permission error** (no refresh/redirect) |
| **401** | `"Missing or invalid authentication"` | No user data in request state | **Silent refresh** |

### Other Auth Errors

| Status | `detail` value | Cause |
|--------|---------------|-------|
| **401** | `"Invalid credentials"` | Wrong email/password on sign-in |
| **401** | `"Email not verified"` | User hasn't verified email |
| **409** | `"Email already in use"` | Registration with existing email |
| **429** | `"Too many requests. Try again later."` | Rate limit exceeded (1000 req/hour) |

### Decision Rule

```
Is it a 401 from /v1/auth/refresh?
  YES → Session is dead → Redirect to login

Is the detail "Token revoked"?
  YES → User signed out → Redirect to login immediately

Is it a 403?
  YES → Permission error → Show error message, do NOT refresh

Is it any other 401?
  YES → Token expired → Attempt silent refresh
```

---

## 4. Silent Refresh Flow

### Decision Flowchart

```mermaid
flowchart TD
    A[API request returns 401] --> B{Is it from /v1/auth/refresh?}
    B -->|YES| C[Redirect to login]
    B -->|NO| D{Is detail 'Token revoked'?}
    D -->|YES| C
    D -->|NO| E{Is refresh already in progress?}
    E -->|YES| F[Queue this request, wait for refresh result]
    E -->|NO| G[Start refresh: POST /v1/auth/refresh]
    G --> H{Refresh succeeded?}
    H -->|YES| I[Update access_token + expires_at in memory]
    I --> J[Retry original request + all queued requests]
    H -->|NO| C
    F --> K{Refresh resolved?}
    K -->|Success| J
    K -->|Failure| C
```

### TypeScript Implementation Pattern (Axios)

```typescript
// auth-interceptor.ts
import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL,
  withCredentials: true, // CRITICAL: sends cookies with every request
});

// --- State ---
let accessToken: string | null = null;
let expiresAt: number | null = null; // Unix timestamp in SECONDS
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (error: unknown) => void;
}> = [];

// --- Helpers ---
function setTokens(session: { access_token: string; expires_at: number }) {
  accessToken = session.access_token;
  expiresAt = session.expires_at;
}

function clearAuth() {
  accessToken = null;
  expiresAt = null;
}

function redirectToLogin() {
  clearAuth();
  // Save current URL for post-login redirect
  sessionStorage.setItem('redirectAfterLogin', window.location.pathname + window.location.search);
  window.location.href = '/login';
}

function processQueue(error: unknown, token: string | null) {
  failedQueue.forEach(({ resolve, reject }) => {
    if (token) resolve(token);
    else reject(error);
  });
  failedQueue = [];
}

// --- Request Interceptor ---
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

// --- Response Interceptor ---
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<{ detail: string }>) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    const status = error.response?.status;
    const detail = error.response?.data?.detail;

    // Only handle 401s (not 403s, not other errors)
    if (status !== 401 || originalRequest._retry) {
      return Promise.reject(error);
    }

    // If token was explicitly revoked (user signed out elsewhere), go to login
    if (detail === 'Token revoked') {
      redirectToLogin();
      return Promise.reject(error);
    }

    // If this 401 came from the refresh endpoint itself, session is dead
    if (originalRequest.url?.includes('/v1/auth/refresh')) {
      redirectToLogin();
      return Promise.reject(error);
    }

    // If a refresh is already in progress, queue this request
    if (isRefreshing) {
      return new Promise((resolve, reject) => {
        failedQueue.push({
          resolve: (token: string) => {
            originalRequest.headers.Authorization = `Bearer ${token}`;
            originalRequest._retry = true;
            resolve(api(originalRequest));
          },
          reject,
        });
      });
    }

    // Start refresh
    isRefreshing = true;
    originalRequest._retry = true;

    try {
      // Cookie is sent automatically due to withCredentials: true
      const { data } = await api.post('/v1/auth/refresh');
      const newToken = data.data.session.access_token;

      setTokens(data.data.session);
      processQueue(null, newToken);

      // Retry the original request
      originalRequest.headers.Authorization = `Bearer ${newToken}`;
      return api(originalRequest);
    } catch (refreshError) {
      processQueue(refreshError, null);
      redirectToLogin();
      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  }
);

export { api, setTokens, clearAuth, redirectToLogin };
```

### Sign-In Integration

```typescript
async function signIn(email: string, password: string) {
  const { data } = await api.post('/v1/auth/sign-in', { email, password });

  setTokens(data.data.session);
  // user_data available at data.data.user_data
  // refresh_token cookie set automatically by the browser

  // Check for saved redirect
  const redirect = sessionStorage.getItem('redirectAfterLogin');
  if (redirect) {
    sessionStorage.removeItem('redirectAfterLogin');
    window.location.href = redirect;
  }

  return data.data;
}
```

### Sign-Out Integration

```typescript
async function signOut() {
  try {
    await api.post('/v1/auth/sign-out/');
  } finally {
    clearAuth();
    // Close all WebSocket connections
    closeAllWebSockets();
    window.location.href = '/login';
  }
}
```

---

## 5. Proactive Token Refresh

Refresh the token BEFORE it expires so users never see a 401.

### Implementation

```typescript
let refreshTimer: ReturnType<typeof setTimeout> | null = null;

function scheduleProactiveRefresh(expiresAtSeconds: number) {
  // Clear any existing timer
  if (refreshTimer) clearTimeout(refreshTimer);

  // Calculate time until 5 minutes before expiry
  const now = Date.now();
  const expiresAtMs = expiresAtSeconds * 1000;
  const refreshAtMs = expiresAtMs - (5 * 60 * 1000); // 5 min before expiry
  const delay = refreshAtMs - now;

  if (delay <= 0) {
    // Token already expired or about to expire, refresh immediately
    silentRefresh();
    return;
  }

  refreshTimer = setTimeout(silentRefresh, delay);
}

async function silentRefresh() {
  try {
    const { data } = await api.post('/v1/auth/refresh');
    setTokens(data.data.session);
    scheduleProactiveRefresh(data.data.session.expires_at);
  } catch {
    // Refresh failed - will be caught by interceptor on next API call
  }
}

// Handle tab visibility changes
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && expiresAt) {
    const now = Date.now();
    const expiresAtMs = expiresAt * 1000;
    const timeLeft = expiresAtMs - now;

    if (timeLeft <= 0) {
      // Token expired while tab was in background
      silentRefresh();
    } else if (timeLeft <= 5 * 60 * 1000) {
      // Less than 5 min left, refresh now
      silentRefresh();
    }
    // Otherwise, timer is still running
  }
});
```

### When to Schedule

Call `scheduleProactiveRefresh(session.expires_at)` after:
- Successful sign-in
- Successful token refresh (reactive or proactive)

---

## 6. WebSocket Auth & Reconnection

### Three WebSocket Connections

| Endpoint | Query Params | Purpose |
|----------|-------------|---------|
| `ws/trips` | `location_id`, `token` | Real-time trip updates |
| `ws/flights/push` | `location_id`, `flight_numbers`, `token` | Flight push notifications |
| `ws/flights/tracking` | `token` | Live flight position tracking |

### Authentication Pattern (identical for all three)

1. **Connect:** Token passed as query parameter (NOT header - WebSocket limitation)
2. **On connect:** Backend validates JWT. If invalid → close code `1008` immediately
3. **Keep-alive ping:** Client sends `{"action": "ping", "token": "<current_token>"}` every 30 seconds
4. **Ping response:**
   - Valid token: `{"type": "pong"}`
   - Invalid/expired: `{"type": "error", "code": 401, "detail": "Invalid or expired token"}` → then close `1008`

### On Successful Connection

Each WebSocket sends an initial snapshot:
- **Trips WS:** `{"type": "snapshot", "location_id": "...", "location_info": {...}, "trips": [...]}`
- **Flight push WS:** Snapshot of recent notifications
- **Tracking WS:** Requires explicit `{"action": "track", "flights": [...]}` to start receiving positions

### Token Ref Pattern (Critical)

The ping interval must always use the LATEST access token, even after a refresh:

```typescript
const tokenRef = useRef(accessToken);

// Update ref whenever token changes
useEffect(() => {
  tokenRef.current = accessToken;
}, [accessToken]);

// Ping interval uses the ref, not a stale closure
useEffect(() => {
  const interval = setInterval(() => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({
        action: 'ping',
        token: tokenRef.current, // Always the latest token
      }));
    }
  }, 30_000);

  return () => clearInterval(interval);
}, []);
```

### Reconnection Strategy

```mermaid
flowchart TD
    A[WS receives error code=401 OR close code=1008] --> B[Stop ping interval]
    B --> C[Attempt token refresh via HTTP]
    C --> D{Refresh succeeded?}
    D -->|YES| E[Reconnect WS with new token in query param]
    E --> F[Resume ping with tokenRef.current]
    E --> G[WS sends initial snapshot automatically]
    D -->|NO| H[Redirect to login]
```

### Reconnection with Exponential Backoff

```typescript
const BACKOFF = [1000, 2000, 5000, 10000, 30000]; // ms
let reconnectAttempt = 0;

function reconnectWebSocket() {
  const delay = BACKOFF[Math.min(reconnectAttempt, BACKOFF.length - 1)];
  reconnectAttempt++;

  setTimeout(() => {
    connectWebSocket(tokenRef.current);
  }, delay);
}

// Reset on successful connection
function onWebSocketOpen() {
  reconnectAttempt = 0;
}

// Do NOT reconnect on intentional close (code 1000)
function onWebSocketClose(event: CloseEvent) {
  if (event.code === 1000) return; // Intentional close
  if (event.code === 1008) {
    // Auth failure - try refresh first
    silentRefresh()
      .then(() => reconnectWebSocket())
      .catch(() => redirectToLogin());
  } else {
    // Other error - reconnect with backoff
    reconnectWebSocket();
  }
}
```

### Post-Reconnection State Recovery

| WebSocket | What happens on reconnect |
|-----------|--------------------------|
| **Trips** | Automatic snapshot with all current trips - no manual re-subscription needed |
| **Flight Push** | Automatic snapshot of recent notifications |
| **Flight Tracking** | Must re-send `{"action": "track", "flights": [...]}` for each tracked flight |

---

## 7. Login Redirect Flow

### When to Redirect

| Condition | Redirect? |
|-----------|-----------|
| Refresh endpoint returns 401 (any detail) | YES |
| Refresh endpoint network error (after 1 retry) | YES |
| Protected endpoint returns 401 with `"Token revoked"` | YES (skip refresh) |
| Protected endpoint returns 401 (other details) | NO - try refresh first |
| Any endpoint returns 403 | NO - show permission error |

### Pre-Redirect Cleanup

```typescript
function redirectToLogin() {
  // 1. Save current URL for post-login redirect
  sessionStorage.setItem('redirectAfterLogin',
    window.location.pathname + window.location.search
  );

  // 2. Clear auth state
  clearAuth();

  // 3. Clear proactive refresh timer
  if (refreshTimer) clearTimeout(refreshTimer);

  // 4. Close all WebSocket connections (code 1000 = intentional)
  closeAllWebSockets(1000);

  // 5. Redirect
  window.location.href = '/login';
}
```

### Post-Login Restoration

```typescript
async function onSignInSuccess(data: SignInResponse) {
  setTokens(data.session);
  scheduleProactiveRefresh(data.session.expires_at);

  // Reconnect all active WebSocket connections
  reconnectAllWebSockets(data.session.access_token);

  // Redirect to saved URL or default
  const savedUrl = sessionStorage.getItem('redirectAfterLogin');
  if (savedUrl) {
    sessionStorage.removeItem('redirectAfterLogin');
    router.push(savedUrl);
  } else {
    router.push('/dashboard');
  }
}
```

---

## 8. Session State Recovery (No Data Loss)

### What persists server-side (NOT lost on token expiration)

| Data | Storage | Retrieval after re-auth |
|------|---------|------------------------|
| **Filter Steps** | PostgreSQL (`trips.filter_steps`) | `GET /v2/locations/{id}/airlines/{airline}/filters/stack?pick_up_date=YYYY-MM-DD` |
| **Filter Presets** | PostgreSQL (`trips.filter_presets`) | `GET /v2/locations/{id}/airlines/{airline}/filters/preset` |
| **Trip Data** | PostgreSQL + Redis cache | WebSocket snapshot on reconnect, or `GET /v1/locations/{id}/trips` |
| **User Settings** | PostgreSQL (`settings.user_settings`) | `GET /v1/profile/settings` |
| **Organization Data** | PostgreSQL | Included in `user_data` on sign-in/refresh |

### What IS lost (client-side only)

- Unsaved form inputs
- In-flight optimistic UI updates
- Local UI state (selected tabs, scroll position, etc.)

With the silent refresh pattern implemented correctly, even these should rarely be lost since the request just retries transparently.

### Filter Rehydration Example

After re-authentication, the frontend can fully restore filter state:

```typescript
// 1. Get current filter stack for a specific day
const stack = await api.get(
  `/v2/locations/${locationId}/airlines/${airline}/filters/stack`,
  { params: { pick_up_date: '2026-02-19' } }
);

// 2. Get the preset (auto-apply template) if it exists
const preset = await api.get(
  `/v2/locations/${locationId}/airlines/${airline}/filters/preset`
);

// Both endpoints return the full current state - no data is lost
```

---

## 9. Multi-Tab Coordination

### Problem

If the user has multiple tabs open:
- Tab A refreshes the token → Tab B still has the old access token
- Tab A signs out → Tab B doesn't know and keeps making requests

### Solution: localStorage Event Sync

```typescript
const TOKEN_STORAGE_KEY = 'gt360_token_sync';
const SIGNOUT_KEY = 'gt360_signout';

// --- After refresh or sign-in, notify other tabs ---
function broadcastTokenUpdate(accessToken: string, expiresAt: number) {
  localStorage.setItem(TOKEN_STORAGE_KEY, JSON.stringify({
    accessToken,
    expiresAt,
    timestamp: Date.now(),
  }));
}

// --- After sign-out, notify other tabs ---
function broadcastSignOut() {
  localStorage.setItem(SIGNOUT_KEY, Date.now().toString());
}

// --- Listen for updates from other tabs ---
window.addEventListener('storage', (event) => {
  if (event.key === TOKEN_STORAGE_KEY && event.newValue) {
    const { accessToken: newToken, expiresAt: newExp } = JSON.parse(event.newValue);
    setTokens({ access_token: newToken, expires_at: newExp });
    scheduleProactiveRefresh(newExp);
    // Update WebSocket tokenRef
    tokenRef.current = newToken;
  }

  if (event.key === SIGNOUT_KEY) {
    // Another tab signed out - the backend revokes ALL refresh tokens,
    // so this tab's refresh will fail anyway
    redirectToLogin();
  }
});
```

> **Backend behavior on sign-out:** The backend calls `revoke_all_user_refresh()` which revokes ALL refresh tokens for the user across all sessions. This means if one tab signs out, all other tabs will fail their next refresh attempt.

---

## 10. Public Paths (No Auth Required)

These endpoints do NOT require authentication (the middleware skips them):

```
/v1/auth/sign-in
/v1/auth/refresh
/v1/auth/register
/v1/auth/register/organization
/v1/auth/verify-email
/v1/auth/verify-data
/v1/auth/forgot-password
/v1/auth/reset-password
/docs
/redoc
/openapi.json
/health
/ready
/v1/webhooks/trips
/v1/webhooks/flights
/v1/crew-lookup/config
/v1/crew-lookup/health
/v1/trips/search/qr
/v1/support/contact
/uploads
```

The frontend should NOT attach `Authorization` headers or trigger refresh logic for these endpoints.

---

## 11. CORS Configuration

### Allowed Origins

```
https://www.gt360.com
https://dev.gt360.app
https://gt360.app
https://charmaine-leadless-ryleigh.ngrok-free.dev
```

### Cookie Domain

Cookies are set with `domain=".gt360.app"` which means they are sent to all subdomains: `dev.gt360.app`, `web.gt360.app`, etc.

### Critical Axios Setting

```typescript
const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL,
  withCredentials: true, // REQUIRED: sends cookies cross-origin
});
```

Without `withCredentials: true`, the browser will NOT send the `refresh_token` cookie, and the refresh endpoint will return 401 `"Missing refresh token"`.

---

## 12. Testing Checklist

1. **Normal token expiry**: Wait 60 min (or set short `TOKEN_DURATION` in backend) → verify silent refresh works, no visible error
2. **Refresh token expiry**: Revoke all refresh tokens in DB → verify redirect to login
3. **Sign-out on another tab**: Sign out in Tab A → verify Tab B redirects to login
4. **Network interruption during refresh**: Disconnect network briefly during refresh → verify retry, then redirect
5. **WebSocket close 1008**: Let access token expire → verify WS reconnects with new token after refresh
6. **WebSocket ping with expired token**: Verify error response → reconnect flow
7. **Multiple concurrent 401s**: Fire 5+ API calls simultaneously with expired token → verify only ONE refresh call, all requests retry
8. **Tab backgrounded >60 min**: Background tab, wait, foreground → verify `visibilitychange` triggers refresh
9. **POST/PUT in-flight**: Start a mutation, let token expire during → verify it completes after refresh
10. **403 role error**: Access manager endpoint as driver → verify NO redirect, shows permission error
11. **Filters persist**: Apply filters → let token expire → re-auth → verify filters still present via GET stack
12. **Post-login redirect**: Navigate to `/dashboard/locations/SDF/WN` → token expires → login → verify redirect back to same page

---

## 13. JWT Payload Reference

For debugging, the access token JWT payload contains:

```json
{
  "sub": "user-uuid",
  "iat": 1740000000,
  "exp": 1740003600,
  "metadata": {
    "email": "user@example.com",
    "phone": "+1234567890",
    "role": "manager",
    "first_name": "John",
    "last_name": "Doe",
    "profile_pic": "url-or-null",
    "organization_id": "org-uuid",
    "location_id": "loc-uuid"
  }
}
```

> **Warning:** Never decode the JWT on the client for auth decisions. Always rely on the `expires_at` field from the API response for expiration timing.
