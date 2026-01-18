from fastapi import Request
from psqlmodel import AsyncSession, Select
from shared.db.schemas import UserSettings
from uuid import UUID
import logging

logger = logging.getLogger(__name__)


async def get_user_time_format(request: Request, session: AsyncSession) -> str:
    """
    Obtiene la preferencia de formato de hora del usuario actual.

    Returns:
        "24h" o "12h" (default: "24h")
    """
    try:
        # El middleware verify_token ya pone user_data en request.state
        user_data = getattr(request.state, "user_data", None)
        if not user_data:
            return "24h"  # Default si no hay usuario autenticado

        user_id = user_data.get("id")
        if not user_id:
            return "24h"

        user_uuid = UUID(user_id)

        # Buscar settings del usuario
        settings = await session.exec(
            Select(UserSettings).Where(UserSettings.user_id == user_uuid)
        ).first()

        if settings and settings.time_format:
            return settings.time_format

        # Default si no tiene settings
        return "24h"

    except Exception as e:
        logger.error(f"Error getting user time format: {e}")
        return "24h"  # Fallback seguro
