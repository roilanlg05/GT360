from fastapi import FastAPI
from contextlib import asynccontextmanager
from shared.db import engine
from features.auth.routes.auth_router import router as auth_router
from features.trips.routes.trips_router import router as trips_router
from features.trips.websockets.trip_websockets import router as trip_websockets_router
from features.trips.webhooks.trip_webhooks import webhook as trip_webhooks_router
from features.auth.middlewares.verify_token import VerifyToken
from shared.middlewares.requests_logger import RequestLoggerMiddleware
from shared.middlewares.rate_limiter import RateLimitMiddleware
from shared.middlewares.exceptions_handler import HTTPErrorHandler
from fastapi.middleware.cors import CORSMiddleware

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://192.168.0.133:3000",
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)
app.include_router(trips_router)
app.include_router(trip_websockets_router)
app.include_router(trip_webhooks_router)