import json
import logging
import redis.asyncio as redis
from starlette.types import ASGIApp, Receive, Scope, Send
from shared.redis.redis_client import redis_client

logger = logging.getLogger(__name__)


class RateLimitMiddleware:
    """
    Pure ASGI middleware for rate limiting with Redis.

    Uses ASGI directly instead of BaseHTTPMiddleware to avoid
    issues with file uploads and streaming request bodies.
    """

    def __init__(
        self,
        app: ASGIApp,
        default_limit: int = 1000,
        default_window: int = 3600
    ):
        self.app = app
        self.default_limit = default_limit
        self.default_window = default_window
        self.route_limits = {}

    def _get_limit_for_path(self, path: str) -> tuple[int, int]:
        """Get rate limit and window for a specific path."""
        if path in self.route_limits:
            return self.route_limits[path]

        for route_pattern, limits in self.route_limits.items():
            if path.startswith(route_pattern.rstrip("/")):
                return limits

        return self.default_limit, self.default_window

    def _get_client_ip(self, scope: Scope) -> str:
        """Get real client IP from headers or connection."""
        headers = dict(scope.get("headers", []))

        forwarded = headers.get(b"x-forwarded-for", b"").decode("utf-8", errors="ignore")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = headers.get(b"x-real-ip", b"").decode("utf-8", errors="ignore")
        if real_ip:
            return real_ip

        client = scope.get("client")
        return client[0] if client else "unknown"

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        # Skip non-HTTP requests
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")

        # Skip OPTIONS requests
        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        client_ip = self._get_client_ip(scope)
        path = scope.get("path", "/")

        key = f"ratelimit:{client_ip}:{method}:{path}"
        limit, window = self._get_limit_for_path(path)

        try:
            r = redis_client
            current = await r.incr(key)

            if current == 1:
                await r.expire(key, window)

            ttl = await r.ttl(key)

            if current > limit:
                await self._send_rate_limit_response(send, ttl, scope)
                return

            await self.app(scope, receive, send)

        except redis.ConnectionError:
            logger.warning("Redis unavailable for rate limiting, allowing request")
            await self.app(scope, receive, send)
        except Exception as e:
            logger.error(f"Rate limit error: {e}")
            await self.app(scope, receive, send)

    async def _send_rate_limit_response(self, send: Send, retry_after: int, scope: Scope = None):
        """Send a 429 Too Many Requests response with CORS headers."""
        body = json.dumps({
            "detail": "Too many requests. Try again later.",
            "retry_after": retry_after
        }).encode()

        headers = [
            (b"content-type", b"application/json"),
            (b"retry-after", str(retry_after).encode()),
        ]

        # Add CORS headers so the browser can read the 429 response
        if scope:
            request_headers = dict(scope.get("headers", []))
            origin = request_headers.get(b"origin", b"").decode("utf-8", errors="ignore")
            allowed_origins = [
                "https://www.gt360.com",
                "https://dev.gt360.app",
                "https://gt360.app",
            ]
            if origin in allowed_origins:
                headers.extend([
                    (b"access-control-allow-origin", origin.encode()),
                    (b"access-control-allow-credentials", b"true"),
                ])

        await send({
            "type": "http.response.start",
            "status": 429,
            "headers": headers,
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })