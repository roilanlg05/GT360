from fastapi import FastAPI
from contextlib import asynccontextmanager
from shared.db import engine
from features.auth.routes.auth_router import router as auth_router
from features.auth.middlewares.verify_token import VerifyToken
from shared.middlewares.requests_logger import RequestLoggerMiddleware
from shared.middlewares.rate_limiter import RateLimitMiddleware
from shared.middlewares.exceptions_handler import HTTPErrorHandler

@asynccontextmanager
async def lifespan(app: FastAPI):
    await engine.startup_async()
    yield
    # Opcional pero recomendado:
    if engine._async_pool:
        await engine._async_pool.close()

app = FastAPI(title="GT360", version="0.1.0", lifespan=lifespan)

app.add_middleware(HTTPErrorHandler)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(VerifyToken)
app.add_middleware(RequestLoggerMiddleware)


app.include_router(auth_router)