from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os
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
from features.drivers.routes.shifts_router import router as shifts_router
from features.drivers.routes.expenses_router import router as expenses_router
from features.drivers.routes.earnings_router import router as earnings_router
from features.drivers.routes.tax_router import router as tax_router
from features.drivers.routes.manager_shifts_router import router as manager_shifts_router
from features.drivers.routes.manager_expenses_router import router as manager_expenses_router
from features.drivers.routes.manager_1099_router import router as manager_1099_router
from features.drivers.routes.rating_router import router as rating_router
from features.drivers.websockets.location_websocket import router as driver_location_ws_router
from features.drivers.utils.location_ws_manager import driver_location_manager
from features.trips.routes.step_filter_router import router as step_filter_router
from features.trips.routes.filter_preset_router import router as filter_preset_router
from features.trips.routes.test_filter_router import router as test_filter_router
from features.support.routes.support_router import router as support_router
from features.trips.routes.review_router import router as review_router
from features.trips.routes.alarm_router import router as alarm_router
from features.billing.routes.billing_router import router as billing_router, admin_router as billing_admin_router
from features.billing.webhooks.stripe_webhook import router as stripe_webhook_router
from shared.settings import settings
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
from shared.db.triggers.trips_archive import ensure_trips_archive_trigger
from shared.db.triggers.driver_earnings_triggers import ensure_driver_earnings_triggers
from psqlmodel import AsyncSession

app = FastAPI()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await engine.startup_async()
    # Ensure schemas exist
    async with AsyncSession(engine) as _s:
        await _s.exec("CREATE SCHEMA IF NOT EXISTS reviews")
        await _s.exec("CREATE SCHEMA IF NOT EXISTS drivers")
        await _s.exec("CREATE SCHEMA IF NOT EXISTS ratings")
        await _s.commit()
     # Ensure archive trigger exists (drop-off -> history)
    async with AsyncSession(engine) as _s:
        await ensure_trips_archive_trigger(_s)
        await _s.commit()
    # Ensure driver earnings triggers exist (updated_at for all tables)
    async with AsyncSession(engine) as _s:
        await ensure_driver_earnings_triggers(_s)
        await _s.commit()
    # Start DWELL checker background job (runs every 60 seconds)
    #dwell_checker.start(interval_seconds=60)
    # Start stale driver location cleanup (removes entries >3 min old)
    driver_location_manager.start_cleanup_task()
    yield
    # Stop DWELL checker on shutdown
    #await dwell_checker.stop()
    driver_location_manager.stop_cleanup_task()
    await engine.dispose_async()

app = FastAPI(title="GT360", version="0.1.0", lifespan=lifespan)

# CORS debe ir primero para manejar OPTIONS preflight correctamente
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.gt360.com",
        "https://dev.gt360.app",
        "https://gt360.app",
        "https://charmaine-leadless-ryleigh.ngrok-free.dev"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(DenyDotfileMiddleware)
#app.add_middleware(HTTPErrorHandler)  # Maneja errores 500 con headers CORS
#app.add_middleware(RateLimitMiddleware)
app.add_middleware(VerifyToken)
app.add_middleware(RequestLoggerMiddleware)


# Exception handler para errores de validación 422
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Captura errores 422 y los loguea para debugging.
    """
    logger = logging.getLogger(__name__)
    logger.error(f"[VALIDATION_ERROR] Path: {request.url.path}")
    logger.error(f"[VALIDATION_ERROR] Errors: {exc.errors()}")
    logger.error(f"[VALIDATION_ERROR] Body: {exc.body}")
    logger.error(f"[VALIDATION_ERROR] Content-Type: {request.headers.get('content-type')}")
    logger.error(f"[VALIDATION_ERROR] Content-Length: {request.headers.get('content-length')}")

    origin = request.headers.get("origin")
    allowed_origins = [
        "https://www.gt360.com",
        "https://dev.gt360.app",
        "https://web.gt360.app",
        "https://gt360.app",
    ]

    response = JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )

    if origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"

    return response


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
        "https://dev.gt360.app",
        "https://web.gt360.app",
        "https://gt360.app",
        "https://charmaine-leadless-ryleigh.ngrok-free.dev",
        "http://192.168.1.101:3000/"
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


# Lightweight health endpoints used by Docker/ingress healthchecks.
# Must return 200 (not 404) so container can become healthy.
@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


@app.get("/ready", include_in_schema=False)
async def ready():
    return {"status": "ok"}


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
# Driver earnings system routers
app.include_router(shifts_router)
app.include_router(expenses_router)
app.include_router(earnings_router)
app.include_router(tax_router)
app.include_router(manager_shifts_router)
app.include_router(manager_expenses_router)
app.include_router(manager_1099_router)
app.include_router(step_filter_router)
app.include_router(filter_preset_router)
app.include_router(test_filter_router)
app.include_router(support_router)
app.include_router(review_router)
app.include_router(alarm_router)
app.include_router(rating_router)
app.include_router(driver_location_ws_router)
app.include_router(billing_router)
app.include_router(billing_admin_router)
app.include_router(stripe_webhook_router)
#app.include_router(validation_router)
#app.include_router(geofence_router)

# Mount static files for uploads (profile pictures, etc.)
# Create directory if it doesn't exist and we have permissions
try:
    if not os.path.exists(settings.UPLOAD_DIR):
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")
except PermissionError:
    # In Docker, uploads may be handled differently or mounted as volume
    pass
