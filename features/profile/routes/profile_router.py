"""
Profile Router - Endpoints for user profile management.
"""

from fastapi import APIRouter, HTTPException, Request, Depends, UploadFile, File
from psqlmodel import Select, Delete, AsyncSession
from uuid import UUID

from shared.db.db_config import get_db
from shared.db.schemas import User, Driver, Manager, UserSettings
from features.auth.utils import verify_role, verify_password
from features.profile.models import (
    ProfileResponse,
    ProfileUpdate,
    DeleteAccountRequest,
    UserSettingsResponse,
    UserSettingsUpdate,
    ManagerProfileResponse,
    ManagerProfileUpdate,
    ProfilePhotoUploadResponse,
)
from features.profile.services.manager_profile_service import ManagerProfileService
from shared.services.file_storage_service import file_storage_service
from features.profile.websockets.profile_websocket import publish_profile_update
from datetime import datetime, timezone


router = APIRouter(tags=["Profile"])


def _user_to_response(user: User, org_id: str = None) -> ProfileResponse:
    """Convert User model to ProfileResponse."""
    return ProfileResponse(
        id=str(user.id),
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        phone=user.phone,
        profile_pic=user.profile_pic,
        role=user.role,
        organization_id=org_id,
        email_verified_at=user.email_verified_at.isoformat() if user.email_verified_at else None,
        created_at=user.created_at.isoformat() if user.created_at else None,
        updated_at=user.updated_at.isoformat() if user.updated_at else None,
    )


@router.get("/v1/profile", response_model=ProfileResponse)
async def get_profile(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager", "driver", "crew"]))
):
    """
    Get current user's profile.
    """
    user_data = request.state.user_data
    user_id = user_data.get("id")
    org_id = user_data.get("organization_id")

    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de usuario inválido")

    user = await session.exec(
        Select(User).Where(User.id == user_uuid)
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    return _user_to_response(user, str(org_id) if org_id else None)


@router.patch("/v1/profile", response_model=ProfileResponse)
async def update_profile(
    request: Request,
    update_data: ProfileUpdate,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager", "driver", "crew"]))
):
    """
    Update current user's profile.

    Currently only profile_pic can be updated.
    For other changes (name, email, phone), contact support.
    """
    user_data = request.state.user_data
    user_id = user_data.get("id")
    org_id = user_data.get("organization_id")

    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de usuario inválido")

    user = await session.exec(
        Select(User).Where(User.id == user_uuid)
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Update allowed fields
    update_dict = update_data.model_dump(exclude_unset=True)

    if "profile_pic" in update_dict:
        user.profile_pic = update_dict["profile_pic"]

    session.add(user)
    await session.commit()
    await session.refresh(user)

    # Publish update to WebSocket
    response = _user_to_response(user, str(org_id) if org_id else None)
    await publish_profile_update(user_id, response.model_dump())

    return response


# =============================================================================
# USER SETTINGS ENDPOINTS
# =============================================================================

@router.get("/v1/profile/settings", response_model=UserSettingsResponse)
async def get_user_settings(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager", "driver", "crew"]))
):
    """
    Obtiene las preferencias del usuario actual.

    Si el usuario no tiene settings, retorna valores por defecto.
    """
    user_data = request.state.user_data
    user_id = user_data.get("id")

    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de usuario inválido")

    # Buscar settings existentes
    settings = await session.exec(
        Select(UserSettings).Where(UserSettings.user_id == user_uuid)
    ).first()

    if not settings:
        # Crear settings por defecto si no existen
        settings = UserSettings(
            user_id=user_uuid,
            time_format="24h"
        )
        session.add(settings)
        await session.commit()
        await session.refresh(settings)

    return UserSettingsResponse(
        user_id=str(settings.user_id),
        time_format=settings.time_format,
        created_at=settings.created_at.isoformat(),
        updated_at=settings.updated_at.isoformat()
    )


@router.patch("/v1/profile/settings", response_model=UserSettingsResponse)
async def update_user_settings(
    request: Request,
    update_data: UserSettingsUpdate,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager", "driver", "crew"]))
):
    """
    Actualiza las preferencias del usuario actual.

    Solo se permite actualizar time_format por ahora.
    """
    user_data = request.state.user_data
    user_id = user_data.get("id")

    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de usuario inválido")

    # Buscar settings existentes
    settings = await session.exec(
        Select(UserSettings).Where(UserSettings.user_id == user_uuid)
    ).first()

    if not settings:
        # Crear si no existe
        settings = UserSettings(
            user_id=user_uuid,
            time_format=update_data.time_format
        )
    else:
        # Actualizar existente
        settings.time_format = update_data.time_format
        settings.updated_at = datetime.now(timezone.utc)

    session.add(settings)
    await session.commit()
    await session.refresh(settings)

    return UserSettingsResponse(
        user_id=str(settings.user_id),
        time_format=settings.time_format,
        created_at=settings.created_at.isoformat(),
        updated_at=settings.updated_at.isoformat()
    )


# =============================================================================
# DELETE ACCOUNT ENDPOINT
# =============================================================================

@router.delete("/v1/profile")
async def delete_account(
    request: Request,
    delete_request: DeleteAccountRequest,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager", "driver", "crew"]))
):
    """
    Delete current user's account.

    Requires password confirmation for security.
    This action is irreversible.
    """
    user_data = request.state.user_data
    user_id = user_data.get("id")
    user_role = user_data.get("role")

    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de usuario inválido")

    user = await session.exec(
        Select(User).Where(User.id == user_uuid)
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Verify password
    if not verify_password(delete_request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")

    # Delete role-specific record first (due to foreign key)
    if user_role == "driver":
        await session.exec(
            Delete(Driver).Where(Driver.id == user_uuid)
        )
    elif user_role == "manager":
        await session.exec(
            Delete(Manager).Where(Manager.id == user_uuid)
        )

    # Delete user
    await session.exec(
        Delete(User).Where(User.id == user_uuid)
    )

    await session.commit()

    return {"status": "ok", "message": "Cuenta eliminada correctamente"}


# =============================================================================
# MANAGER PROFILE ENDPOINTS
# =============================================================================

@router.get("/v1/profile/manager", response_model=ManagerProfileResponse)
async def get_manager_profile(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Obtiene el perfil completo del manager autenticado.

    Retorna:
    - Datos personales (nombre, email, telefono, foto)
    - Datos de la organizacion (nombre, direccion, website, plan)
    - Lista de locations asociadas
    """
    user_data = request.state.user_data
    user_id = user_data.get("id")

    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de usuario invalido")

    service = ManagerProfileService(session)
    profile = await service.get_manager_profile(user_uuid)

    if not profile:
        raise HTTPException(
            status_code=404,
            detail="Perfil de manager no encontrado. Verifique que su cuenta este configurada correctamente."
        )

    return profile


@router.patch("/v1/profile/manager", response_model=ManagerProfileResponse)
async def update_manager_profile(
    request: Request,
    update_data: ManagerProfileUpdate,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """
    Actualiza campos del perfil del manager.

    Campos actualizables:
    - first_name, last_name, phone (datos personales)
    - organization_name, organization_address, organization_website (datos de org)

    Nota: Para cambiar email o password, use los endpoints especificos de auth.
    """
    user_data = request.state.user_data
    user_id = user_data.get("id")

    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de usuario invalido")

    service = ManagerProfileService(session)
    profile = await service.update_manager_profile(user_uuid, update_data)

    if not profile:
        raise HTTPException(status_code=404, detail="Perfil de manager no encontrado")

    # Publish update to WebSocket for real-time sync
    await publish_profile_update(user_id, {"type": "manager_profile_updated"})

    return profile


@router.post("/v1/profile/manager/upload-photo", response_model=ProfilePhotoUploadResponse)
async def upload_manager_photo(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"])),
    file: UploadFile = File(..., description="Imagen de perfil (JPG, PNG, WebP, GIF). Max 4MB.")
):
    """
    Sube una nueva foto de perfil.

    Requisitos:
    - Formatos permitidos: JPEG, PNG, WebP, GIF
    - Tamano maximo: 4 MB
    - Se recomienda imagen cuadrada de al menos 200x200 px

    Nota: La foto anterior se elimina automaticamente.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[UPLOAD] File received: {file.filename}, content_type: {file.content_type}, size: {file.size}")

    user_data = request.state.user_data
    user_id = user_data.get("id")

    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de usuario invalido")

    # Validate file exists
    if not file.filename:
        raise HTTPException(status_code=400, detail="No se proporciono archivo")

    try:
        # Get current profile pic URL to delete later
        current_user = await session.exec(
            Select(User).Where(User.id == user_uuid)
        ).first()
        old_profile_pic = current_user.profile_pic if current_user else None

        # Upload new photo to local storage
        profile_pic_url = await file_storage_service.upload_profile_image(file, user_id)

        if not profile_pic_url:
            raise HTTPException(status_code=500, detail="Error al subir la imagen")

        # Update user record
        service = ManagerProfileService(session)
        success = await service.update_profile_pic(user_uuid, profile_pic_url)

        if not success:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        # Delete old photo after successful upload and DB update
        if old_profile_pic:
            deleted = await file_storage_service.delete_file(old_profile_pic)
            if deleted:
                logger.info(f"[UPLOAD] Deleted old profile pic: {old_profile_pic}")
            else:
                logger.warning(f"[UPLOAD] Could not delete old profile pic: {old_profile_pic}")

        # Publish update to WebSocket
        await publish_profile_update(user_id, {
            "type": "profile_pic_updated",
            "profile_pic": profile_pic_url
        })

        return ProfilePhotoUploadResponse(
            profile_pic_url=profile_pic_url,
            message="Foto de perfil actualizada correctamente"
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))