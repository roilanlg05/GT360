from psqlmodel import AsyncSession, create_async_engine
from typing import AsyncGenerator
from features.auth.schemas import *

engine = create_async_engine(
    username="hashdown",
    password="Rlg*020305",
    database="gt360",
    ensure_database=False,
    ensure_tables=False,
    auto_startup=False,
    check_schema_drift=False,
    debug=True,
    models_path=[
        "features/auth/schemas/auth_schemas.py", 
        "features/trips/schemas/trip_schemas.py"
        ]
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(engine) as session:
        yield session