from starlette.middleware.base import BaseHTTPMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.responses import JSONResponse, Response
import logging
import traceback

logger = logging.getLogger(__name__)


class HTTPErrorHandler(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response | JSONResponse:
        # Skip middleware for WebSocket connections - BaseHTTPMiddleware doesn't handle them well
        if request.scope.get("type") == "websocket":
            return await call_next(request)

        try:
            return await call_next(request)
        except (HTTPException, StarletteHTTPException):
            # Re-raise HTTPException so FastAPI's default handler processes it
            raise
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            tb = traceback.format_exc()
            logger.error(f"Unhandled error on {request.method} {request.url.path}: {error_msg}")
            logger.error(tb)
            # Include error details for debugging
            response = JSONResponse(
                content={
                    "detail": "Internal server error",
                    "error": error_msg,
                    "traceback": tb.split('\n')[-5:]  # Last 5 lines of traceback
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

            # Add CORS headers to error response
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