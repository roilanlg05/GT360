import json
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.requests import Request
from starlette.datastructures import State
from shared.settings import settings

from features.auth.utils import get_token, decode_token


class VerifyToken:
    """
    Pure ASGI middleware for JWT token verification.

    Uses ASGI directly instead of BaseHTTPMiddleware to avoid
    issues with file uploads and streaming request bodies.
    """

    ALLOWED_ORIGINS = [
        "https://www.gt360.com",
        "https://gt360.com",
        "https://web.gt360.app",
        "https://dev.gt360.app",
        "https://charmaine-leadless-ryleigh.ngrok-free.dev"
    ]

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        # Skip non-HTTP requests (websockets, lifespan, etc.)
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Always initialize state dict for HTTP requests
        if "state" not in scope:
            scope["state"] = {}

        method = scope.get("method", "")
        path = scope.get("path", "")

        # Skip OPTIONS requests
        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        # Check if path is public
        is_public = path.startswith(tuple(settings.PUBLIC_PATHS))

        if not is_public:
            # Create a minimal request object to extract token
            request = Request(scope)

            try:
                token = get_token(request)
                payload = decode_token(token)
            except ValueError as e:
                # Send 401 response with CORS headers
                await self._send_error_response(scope, send, 401, str(e))
                return

            # Store user data in scope state
            user_data = payload.get("metadata") or {}
            user_data["id"] = payload.get("sub")
            scope["state"]["user_data"] = user_data

        await self.app(scope, receive, send)

    async def _send_error_response(self, scope: Scope, send: Send, status: int, detail: str):
        """Send an error response with CORS headers."""
        headers = dict(scope.get("headers", []))
        origin = headers.get(b"origin", b"").decode("utf-8", errors="ignore")

        response_headers = [
            (b"content-type", b"application/json"),
        ]

        if origin in self.ALLOWED_ORIGINS:
            response_headers.extend([
                (b"access-control-allow-origin", origin.encode()),
                (b"access-control-allow-credentials", b"true"),
            ])

        body = json.dumps({"detail": detail}).encode()

        await send({
            "type": "http.response.start",
            "status": status,
            "headers": response_headers,
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })
