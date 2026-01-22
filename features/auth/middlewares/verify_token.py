from fastapi import  Request, FastAPI, Response
from fastapi.responses import JSONResponse
from shared.settings import settings
from starlette.middleware.base import BaseHTTPMiddleware

from features.auth.utils import get_token, decode_token

class VerifyToken(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response | JSONResponse:
        # Skip for WebSocket - they handle auth in the endpoint
        if request.scope.get("type") == "websocket":
            return await call_next(request)

        if request.method == "OPTIONS":
            return await call_next(request)

        if not request.url.path.startswith(tuple(settings.PUBLIC_PATHS)):
            try:
                token = get_token(request)
                payload = decode_token(token)
            except ValueError as e:
                # Crear respuesta 401 con headers CORS
                response = JSONResponse(status_code=401, content={"detail":str(e)})

                # Agregar headers CORS si el origin está permitido
                origin = request.headers.get("origin")
                allowed_origins = [
                    "https://www.gt360.com",
                    "https://gt360.com",
                    "https://web.gt360.app",
                    "https://charmaine-leadless-ryleigh.ngrok-free.dev"
                ]
                if origin in allowed_origins:
                    response.headers["Access-Control-Allow-Origin"] = origin
                    response.headers["Access-Control-Allow-Credentials"] = "true"

                return response

            request.state.user_data = payload.get("metadata") or {}
            request.state.user_data.update({"id": payload.get("sub")})
            print(request.state.user_data)


        response = await call_next(request)
        return response
