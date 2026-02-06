import logging
from datetime import datetime, timezone
from starlette.types import ASGIApp, Receive, Scope, Send


logger = logging.getLogger(__name__)


class RequestLoggerMiddleware:
    """
    Pure ASGI middleware for request logging.

    Uses ASGI directly instead of BaseHTTPMiddleware to avoid
    issues with file uploads and streaming request bodies.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        # Skip non-HTTP requests (websockets, lifespan, etc.)
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract request info from scope
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"
        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "/")

        # Get headers
        headers = dict(scope.get("headers", []))
        user_agent = headers.get(b"user-agent", b"unknown").decode("utf-8", errors="ignore")
        referer = headers.get(b"referer", b"unknown").decode("utf-8", errors="ignore")
        origin = headers.get(b"origin", b"unknown").decode("utf-8", errors="ignore")

        logger.info(f"""
        📥 Incoming Request:
        - IP: {client_ip}
        - Method: {method}
        - Path: {path}
        - User-Agent: {user_agent}
        - Origin: {origin}
        - Referer: {referer}
        - Time: {datetime.now(timezone.utc)}
        """)

        # Track response status
        response_status = None

        async def send_wrapper(message):
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = message.get("status")
            await send(message)

        await self.app(scope, receive, send_wrapper)

        if response_status:
            logger.info(f"📤 Response Status: {response_status}")