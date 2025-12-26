from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, Response
import logging

logger = logging.getLogger(__name__)


class HTTPErrorHandler(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response | JSONResponse:
        try:
            return await call_next(request)
        except Exception as e:
            logger.error(f"Unhandled error: {str(e)}")
            return JSONResponse(
                content={"detail": "Internal server error"},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )