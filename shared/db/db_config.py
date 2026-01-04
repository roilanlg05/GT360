from psqlmodel import AsyncSession, create_async_engine
from typing import AsyncGenerator
from shared.settings import settings

engine = create_async_engine(
    username=settings.POSTGRES_USER,
    password=settings.POSTGRES_PASSWORD,
    database=settings.POSTGRES_DB,
    host=settings.POSTGRES_SERVER,
    ensure_database=True,
    ensure_tables=False,
    auto_startup=False,
    check_schema_drift=False,
    debug=True,
    max_pool_size=50,
    auto_adjust_pool_size=True,
    models_path=
        "shared/db/schemas/",
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
