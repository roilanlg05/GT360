from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse
import redis.asyncio as redis
from shared.redis.redis_client import redis_client 
import logging

logger = logging.getLogger(__name__)

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware de rate limiting con Redis.
    """
    
    def __init__(
        self, 
        app, 
        default_limit: int = 100, 
        default_window: int = 3600
    ):
        super().__init__(app)
        self.default_limit = default_limit
        self.default_window = default_window
        self.route_limits = {}

        """
        
            "/v1/auth/register/crew-member": (3, 60),
            "/v1/auth/register/manager": (1000, 60),
            "/v1/auth/sign-in": (5, 60),
            "/v1/auth/forgot-password": (1, 60),
            "/v1/auth/reset-password": (3, 60),
            "/v1/auth/refresh": (10, 60),
            "/v1/auth/verify-email": (5, 60),
            "/v1/auth/verify-data": (3, 60),
            "/health": (1000, 60),
        
        """
    
    def _get_limit_for_path(self, path: str) -> tuple[int, int]:
        """Obtiene el límite y ventana para una ruta específica."""
        if hasattr(self, "route_limits") and path in self.route_limits:
            return self.route_limits[path]
        
        if hasattr(self, "route_limits"):
            for route_pattern, limits in self.route_limits.items():
                if path.startswith(route_pattern.rstrip("/")):
                    return limits
        
        return self.default_limit, self.default_window
    
    def _get_client_ip(self, request: Request) -> str:
        """Obtiene la IP real del cliente."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else "unknown"
    
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        
        client_ip = self._get_client_ip(request)
        path = request.url.path
        method = request.method
        
        key = f"ratelimit:{client_ip}:{method}:{path}"
        limit, window = self._get_limit_for_path(path)
        
        try:
            r = redis_client  # Usa la instancia global
            current = await r.incr(key)
            
            if current == 1:
                await r.expire(key, window)
            
            ttl = await r.ttl(key)
            
            if current > limit:
                return JSONResponse(
                    {
                        "detail": "Too many requests. Try again later.",
                        "retry_after": ttl
                    },
                    status_code=429
                )
            
            response = await call_next(request)

            return response
            
        except redis.ConnectionError:
            logger.warning("Redis unavailable for rate limiting, allowing request")
            return await call_next(request)
        except Exception as e:
            logger.error(f"Rate limit error: {e}")
            return await call_next(request)