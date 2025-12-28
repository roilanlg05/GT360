from psqlmodel import AsyncSession, create_async_engine
from typing import AsyncGenerator
from features.auth.schemas import *
from shared.settings import settings

engine = create_async_engine(
    username=settings.POSTGRES_USER,
    password=settings.POSTGRES_PASSWORD,
    database=settings.POSTGRES_DB,
    ensure_database=False,
    ensure_tables=False,
    auto_startup=False,
    check_schema_drift=False,
    debug=True,
    max_pool_size=50,
    auto_adjust_pool_size=True,
    models_path=[
        "features/auth/schemas/auth_schemas.py", 
        "features/trips/schemas/trip_schemas.py"
    ],
    ignore_duplicates=True,
    pool_close_timeout=10.0
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides a database session for FastAPI routes.

    Yields:
        AsyncSession: An asynchronous SQLAlchemy session bound to the configured engine.

    Usage:
        Use as a dependency in your FastAPI endpoints to get a database session.
        The session is automatically closed after the request is processed.
    """
    async with AsyncSession(engine) as session:
        yield session