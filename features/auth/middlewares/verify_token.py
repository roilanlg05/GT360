from fastapi import  Request, FastAPI, Response
from fastapi.responses import JSONResponse
from shared.settings import settings
from starlette.middleware.base import BaseHTTPMiddleware

from features.auth.utils import get_token, decode_token

class VerifyToken(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response | JSONResponse:
        if request.method == "OPTIONS":
            return await call_next(request)

        if not request.url.path.startswith(tuple(settings.PUBLIC_PATHS)):
            try:
                token = get_token(request)
                payload = decode_token(token)
            except ValueError as e:
                return JSONResponse(status_code=401, content={"detail":str(e)})

            request.state.user_data = payload.get("metadata") or {}
            request.state.user_data.update({"id": payload.get("sub")})
            print(request.state.user_data)
        

        response = await call_next(request)
        return response
