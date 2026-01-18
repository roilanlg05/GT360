from fastapi import Request, Depends
from psqlmodel import AsyncSession
from shared.db.db_config import get_db
from shared.middlewares.user_context import get_user_time_format


async def get_current_time_format(
    request: Request,
    session: AsyncSession = Depends(get_db)
) -> str:
    """
    Dependency para obtener el formato de hora preferido del usuario actual.

    Usage:
        @router.get("/endpoint")
        async def endpoint(time_format: str = Depends(get_current_time_format)):
            # Use time_format for formatting
    """
    return await get_user_time_format(request, session)
