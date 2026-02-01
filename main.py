from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from shared.db.db_config import engine
from features.auth.routes.auth_router import router as auth_router
from features.trips.routes.trips_router import router as trips_router
from features.trips.websockets.trip_websockets import router as trip_websockets_router
from features.trips.websockets.org_websockets import router as org_websockets_router
from features.trips.webhooks.trip_webhooks import webhook as trip_webhooks_router
from features.flights.routes.tracking_router import router as tracking_router
from features.flights.websockets.push_websocket import router as flight_push_ws_router
from features.flights.websockets.tracking_websocket import router as flight_tracking_ws_router
from features.flights.push.webhook_handler import router as flight_webhook_router
from features.profile.routes.profile_router import router as profile_router
from features.profile.websockets.profile_websocket import router as profile_ws_router
from features.drivers.routes.drivers_router import router as drivers_router
from features.trips.routes.step_filter_router import router as step_filter_router
from features.trips.routes.filter_preset_router import router as filter_preset_router
from features.trips.routes.test_filter_router import router as test_filter_router
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
        "https://dev.gt360.app",
        "https://web.gt360.app",
	    "https://gt360.app",
        "https://charmaine-leadless-ryleigh.ngrok-free.dev"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(DenyDotfileMiddleware)
#app.add_middleware(HTTPErrorHandler)  # Maneja errores 500 con headers CORS
app.add_middleware(RateLimitMiddleware)
app.add_middleware(VerifyToken)
app.add_middleware(RequestLoggerMiddleware)


# Exception handler para asegurar CORS en todos los errores HTTP
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Maneja HTTPException y asegura que CORS headers estén presentes.
    Esto es necesario porque errores lanzados desde dependencies pueden
    no pasar por el CORSMiddleware correctamente.
    """
    origin = request.headers.get("origin")

    # Lista de orígenes permitidos (debe coincidir con CORSMiddleware)
    allowed_origins = [
        "https://www.gt360.com",
        "https://gt360.com",
        "https://web.gt360.app",
        "https://charmaine-leadless-ryleigh.ngrok-free.dev"
    ]

    # Crear respuesta con el detalle del error
    response = JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

    # Agregar headers CORS si el origin está permitido
    if origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"

    return response


app.include_router(auth_router)
app.include_router(trips_router)
app.include_router(trip_websockets_router)
app.include_router(org_websockets_router)
app.include_router(trip_webhooks_router)
app.include_router(tracking_router)
app.include_router(flight_push_ws_router)
app.include_router(flight_tracking_ws_router)
app.include_router(flight_webhook_router)
app.include_router(profile_router)
app.include_router(profile_ws_router)
app.include_router(drivers_router)
app.include_router(step_filter_router)
app.include_router(filter_preset_router)
app.include_router(test_filter_router)
#app.include_router(validation_router)
#app.include_router(geofence_router)