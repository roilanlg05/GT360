from fastapi import FastAPI
from contextlib import asynccontextmanager
from shared.db.db_config import engine
from features.auth.routes.auth_router import router as auth_router
from features.trips.routes.trips_router import router as trips_router
from features.trips.websockets.trip_websockets import router as trip_websockets_router
from features.trips.websockets.org_websockets import router as org_websockets_router
from features.trips.webhooks.trip_webhooks import webhook as trip_webhooks_router
"""from features.geofencing.routes.validation_router import router as validation_router
from features.geofencing.routes.geofence_router import router as geofence_router
from features.geofencing.jobs import dwell_checker
"""
from features.auth.middlewares.verify_token import VerifyToken
from shared.middlewares.requests_logger import RequestLoggerMiddleware
from shared.middlewares.rate_limiter import RateLimitMiddleware
from shared.middlewares.exceptions_handler import HTTPErrorHandler
from shared.middlewares.deny_dotfiles import DenyDotfileMiddleware
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await engine.startup_async()
    # Start DWELL checker background job (runs every 60 seconds)
    #dwell_checker.start(interval_seconds=60)
    yield
    # Stop DWELL checker on shutdown
    #await dwell_checker.stop()
    await engine.dispose_async()

app = FastAPI(title="GT360", version="0.1.0", lifespan=lifespan)

# CORS debe ir primero para manejar OPTIONS preflight correctamente
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.gt360.com",
        "https://gt360.com",
	    "https://web.gt360.app",
        "http://192.168.1.182:3000",
        "http://172.20.10.7:3000",
        "https://charmaine-leadless-ryleigh.ngrok-free.dev"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(DenyDotfileMiddleware)
app.add_middleware(HTTPErrorHandler)  # Maneja errores 500 con headers CORS
app.add_middleware(RateLimitMiddleware)
app.add_middleware(VerifyToken)
app.add_middleware(RequestLoggerMiddleware)

app.include_router(auth_router)
app.include_router(trips_router)
app.include_router(trip_websockets_router)
app.include_router(org_websockets_router)
app.include_router(trip_webhooks_router)
#app.include_router(validation_router)
#app.include_router(geofence_router)