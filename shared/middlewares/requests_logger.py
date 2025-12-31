import logging
from datetime import datetime, timezone
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request


logger = logging.getLogger(__name__) 

class RequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        method = request.method
        url = request.url.path
        user_agent = request.headers.get("user-agent", "unknown")
        referer = request.headers.get("referer", "unknown")
        origin = request.headers.get("origin", "unknown")
        
        logger.info(f"""
        📥 Incoming Request:
        - IP: {client_ip}
        - Method: {method}
        - Path: {url}
        - User-Agent: {user_agent}
        - Origin: {origin}
        - Referer: {referer}
        - Time: {datetime.now(timezone.utc)}
        """)
        
        response = await call_next(request)
        
        logger.info(f"📤 Response Status: {response.status_code}")
        
        return response