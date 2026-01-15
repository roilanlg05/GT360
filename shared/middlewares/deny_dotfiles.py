import logging
from datetime import datetime, timezone
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from fastapi.responses import PlainTextResponse


class DenyDotfileMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip for WebSocket connections
        if request.scope.get("type") == "websocket":
            return await call_next(request)

        if request.url.path.startswith('/.'):
            return PlainTextResponse('Not found', status_code=404)
        return await call_next(request)