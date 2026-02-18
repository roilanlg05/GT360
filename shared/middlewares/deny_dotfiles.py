from starlette.types import ASGIApp, Receive, Scope, Send


class DenyDotfileMiddleware:
    """
    Pure ASGI middleware to deny access to dotfiles.

    Uses ASGI directly instead of BaseHTTPMiddleware to avoid
    issues with file uploads and streaming request bodies.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        # Skip non-HTTP requests
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        if path.startswith("/."):
            # Send 404 response
            await send({
                "type": "http.response.start",
                "status": 404,
                "headers": [(b"content-type", b"text/plain")],
            })
            await send({
                "type": "http.response.body",
                "body": b"Not found",
            })
            return

        await self.app(scope, receive, send)