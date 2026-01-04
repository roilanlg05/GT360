from fastapi import FastAPI
from contextlib import asynccontextmanager
from shared.db.db_config import engine
from features.auth.routes.auth_router import router as auth_router
from features.trips.routes.trips_router import router as trips_router
from features.trips.websockets.trip_websockets import router as trip_websockets_router
from features.trips.webhooks.trip_webhooks import webhook as trip_webhooks_router
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
    yield
    await engine.dispose_async()

app = FastAPI(title="GT360", version="0.1.0", lifespan=lifespan)

#app.add_middleware(HTTPErrorHandler)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(VerifyToken)
app.add_middleware(RequestLoggerMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.gt360.com",
        "https://gt360.com",
	    "https://web.gt360.app",
        "http://192.168.1.182:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(DenyDotfileMiddleware)

app.include_router(auth_router)
app.include_router(trips_router)
app.include_router(trip_websockets_router)
app.include_router(trip_webhooks_router)
