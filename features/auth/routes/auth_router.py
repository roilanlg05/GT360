from fastapi import APIRouter, HTTPException, Depends, Response, Cookie, Request
from fastapi.responses import JSONResponse
from psqlmodel import Select, AsyncSession
from features.auth.models.user_model import CreateCrewMember, UserData, CreateManager
from features.auth.models.auth_model import EmailPasswordRequestForm, PasswordUpdate, NewPassword
from shared.db.schemas import User, Crew, Manager, Organization
from shared.db.db_config import get_db
from shared.settings import settings
from datetime import timedelta
from features.auth.utils import(
    verify_if_exist, hash_pwd, encode_token, 
    decode_token, get_user_by_email, verify_password,
    gen_refresh_token, save_refresh_in_db, set_cookies,
    revoke_all_user_refresh, get_current_user, validate_refresh,
    now, delete_cookies, blacklist_token, get_token
)
from ..utils.smtp import send_email, get_confirmation_email_template, get_password_reset_email_template
import secrets
from pydantic import EmailStr
from ..utils.validators import validators


router = APIRouter(prefix="/v1/auth", tags=["Auth"])

@router.post("/register/crew-member", status_code=201)
async def register_crew_member(
    user_data: CreateCrewMember, 
    session: AsyncSession = Depends(get_db)
    ) -> dict:

    try: 
        await verify_if_exist(session, user_data.email)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    hashed_pass = hash_pwd(user_data.password)

    try:
        user = User(
            email=user_data.email.lower(),
            password_hash=hashed_pass,
            role="crew"
        )
        session.add(user)
        await session.flush()

        crew = Crew(id=user.id, airline=user_data.airline)
        session.add(crew)

        # Rotar nonce
        user.password_reset_nonce = secrets.token_urlsafe(16)
        session.add(user)

        await session.commit()
            
        metadata = {
            "email": user.email,
            "purpose" : "email_verification",
            "nonce": user.password_reset_nonce
        }
        
            
        token = encode_token(str(user.id), metadata, expires_in=timedelta(hours=24)) 
        confirmation_url = f"{settings.BASE_URL}/auth/verify-email/?token={token['access_token']}"
        html_content = get_confirmation_email_template(confirmation_url)

        await send_email(
            user.email,
            "Confirm Your Api360 Account",
            html_content,
            confirmation_url
        )

        return {"message": "User registred succefull. Check  your email for  confirmation!"}
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=f"Registration failed: {str(e)}")

@router.post("/register/manager", status_code=201)
async def register_manager(
    user_data: CreateManager, 
    session: AsyncSession = Depends(get_db)
    ) -> dict:

    hashed_pass = hash_pwd(user_data.password)

    try:
        user = User(
            email=user_data.email.lower(),
            password_hash=hashed_pass,
            phone=user_data.phone,
            role="manager"
        )

        session.add(user)
        await session.flush()

        manager = Manager(id=user.id)
        session.add(manager)
        await session.flush()

        org = await session.exec(
            Select(Organization)
            .Where(Organization.name == user_data.organization.name)
        ).first()

        if org:
            raise HTTPException(status_code=409, detail="Organization name already exist")
  
        organization = Organization(
            manager_id = manager.id,
            name = user_data.organization.name,
            address = user_data.organization.address,
            website = user_data.organization.website,
            status="active"
        )
        
        session.add(organization)
        await session.flush()

        manager.organization_id = organization.id
        session.add(manager)

        # Rotar nonce
        user.password_reset_nonce = secrets.token_urlsafe(16)
        session.add(user)
        await session.commit()

        metadata = {
            "email": user.email,
            "purpose": "email_verification",
            "nonce": user.password_reset_nonce
        }
            
        token = encode_token(str(user.id), metadata, expires_in=timedelta(hours=24), type="verification") 
        confirmation_url = f"{settings.BASE_URL}/auth/verify-email/?token={token['verification_token']}"
        html_content = get_confirmation_email_template(confirmation_url)

        await send_email(
            user.email,
            "Confirm Your Api360 Account",
            html_content,
            confirmation_url
        )

        return{"message": "User registred succefull. Check  your email for  confirmation!"}
    except HTTPException as e:
        await session.rollback()
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=f"Registration failed: {str(e)}")

@router.post("/verify-data", status_code=200)
async def verify_data(
    user_data: UserData, 
    session: AsyncSession = Depends(get_db)
    ) -> dict:

    try: 
        await verify_if_exist(session, user_data.email, user_data.phone)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"message": "Ok"}
    
@router.post("/sign-in")
async def sign_in(
    user_data: EmailPasswordRequestForm, 
    response: Response,
    session: AsyncSession = Depends(get_db),
    ) -> dict:

    
    user = await get_user_by_email(session, user_data.email)
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not await verify_password(session, user_data.password, user.password_hash, user.id):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not user.email_verified_at:
        raise HTTPException(status_code=401, detail="Email not verified")
    
    metadata = {
        "email": user.email,
        "phone": user.phone,
        "role": user.role
    }

    if user.role == "manager":
        org_row = await session.exec(Select(Manager.organization_id).Where(Manager.id == user.id)).first()
        if org_row[0] and org_row.organization_id:
            metadata["organization_id"] = str(org_row.organization_id)
    elif user.role == "crew":
        airline_row = await session.exec(Select(Crew.airline).Where(Crew.id == user.id)).first()
        if airline_row[0] and airline_row.airline:
            metadata["airline"] = airline_row.airline

    access_token = encode_token(str(user.id), metadata)
    raw, token_hash, exp = gen_refresh_token()

    await save_refresh_in_db(session, user.id, token_hash, exp)

    set_cookies(response, {
        "refresh_token": raw,
        "expires_at": exp
    })

    metadata.update({"id": user.id})

    return {
        "data": {
            "session": {
                "access_token": access_token["access_token"],
                "expires_at": access_token["exp"],  
                "type": "Bearer"
            },
            "user_data": metadata
        }
    }
    
@router.post("/sign-out/", status_code=200)
async def sign_out(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db)
    ):

    token = get_token(request)

    try:
        await blacklist_token(token, exp_seconds=300)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    user_id = request.state.user_data.get("id")

    await revoke_all_user_refresh(session, user_id)

    delete_cookies(
        response, 
        ["refresh_token", "expires_at"])

    return JSONResponse({"message": "All cookies revoked"}, status_code=200)

@router.post("/refresh")
async def refresh_token(
    response: Response,
    session: AsyncSession = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias="refresh_token")
    ) -> dict:

    if not refresh_token:                          
        raise HTTPException(status_code=401, detail="Missing refresh token")

    refresh = await validate_refresh(session, refresh_token)
    
    # Creamos un nuevo refresh opaco para el mismo usuario
    new_raw, new_h, new_exp = gen_refresh_token()
    await save_refresh_in_db(session, user_id=refresh.user_id, token_hash=new_h, exp=new_exp)

    # Emitimos un nuevo access para ese user
    user = await get_current_user(session, refresh.user_id) 

    metadata = {
        "email": user.email,
        "phone": user.phone,
        "role": user.role
    }

    # Agregar campos específicos del rol
    if user.role == "manager":
        org_row = await session.exec(Select(Manager.organization_id).Where(Manager.id == user.id)).first()
        if org_row[0] and org_row.organization_id:
            metadata["organization_id"] = str(org_row.organization_id)
    elif user.role == "crew":
        airline_row = await session.exec(Select(Crew.airline).Where(Crew.id == user.id)).first()
        if airline_row[0] and airline_row.airline:
            metadata["airline"] = airline_row.airline
               

    access_token = encode_token(str(user.id), metadata)
    access_token.update({"type": "bearer"})

    metadata.update({"id": user.id})

    resp = {"data":{ 
                "session": access_token,
                "user_data": metadata 
                }}
    
    await session.commit()
    
    set_cookies(
        response,
        {
            "refresh_token": new_raw, 
            "expires_at": new_exp
        }
    )
    return resp

@router.put("/change-password")
async def change_password(
    data: PasswordUpdate, 
    user_id: str,
    response: Response,
    session: AsyncSession = Depends(get_db), 
    ) -> dict:

    if data.current_password == data.new_password:
        raise HTTPException(status_code=400, detail="The new password must be different from your current password.")
    
    try:
        user = await get_current_user(session, user_id)
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    
    if not await verify_password(session, data.current_password, user.password_hash, user_id):
        raise HTTPException(status_code=403, detail="Incorrect current password")
    
    if await verify_password(session, data.new_password, user.password_hash, user_id):
        raise HTTPException(status_code=409, detail="The new password must be different from your current password.")

    user.password_hash = hash_pwd(data.new_password)
    session.add(user)

    # Revocar todos los refresh tokens
    await revoke_all_user_refresh(session, user_id)

    await session.commit()

    delete_cookies(
        response, 
        ["refresh_token", "expires_at"])

    return JSONResponse({"message":"Password reset successful. Please sign in again with your new password."}, status_code=200)
    
@router.get("/verify-email")
async def verify_email(
    token: str, 
    session: AsyncSession = Depends(get_db)
    ) -> dict: 
    
    """Verifica el email del usuario con el token enviado por correo"""

    try:
        # Decodificar directamente el token del query param
        payload = decode_token(token)

        meta = payload.get("metadata")
        print(meta)
        
        # Verificar que sea un token de verificación
        if meta.get("purpose") != "email_verification":
            raise HTTPException(
                status_code=400,
                detail="Invalid verification token"
            )
        
        user = await get_current_user(session, payload.get("sub")) 

        print(f"User:", user)  

        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )
                
        # Validar nonce
        if not user.password_reset_nonce or user.password_reset_nonce != meta.get("nonce"):
            raise HTTPException(status_code=400, detail="Token already used or invalid")
            

        if user.email_verified_at:
            raise HTTPException(status_code=304, detail="Email already verified")
        
        
        # Marcar email como verificado y invalidar nonce
        user.email_verified_at = now()
        user.password_reset_nonce = None
        session.add(user)
        await session.commit()

        resp = JSONResponse(content="Email verified successfully", status_code=200)
        return resp
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid or expired token: {str(e)}"
        )

@router.post("/forgot-password")
async def forgot_password(
    email: EmailStr, 
    session: AsyncSession = Depends(get_db)
    ) -> dict:

    jresp = JSONResponse(
        content="If the email exists, you will receive a password reset link",
        status_code=200)
    try:
        user = await get_user_by_email(session, email=email)
    except Exception as e:
        print("Exception: ", e)
        return jresp
    
    if not user or user.email_verified_at is None:
        return jresp

    # Rotar nonce
    user.password_reset_nonce = secrets.token_urlsafe(16)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    metadata = {
        "email": user.email,
        "purpose": "password_reset",
        "nonce": user.password_reset_nonce
    }
    token = encode_token(sub=str(user.id), metadata=metadata, expires_in=timedelta(minutes=30), type="reset")

    reset_url = f"{settings.BASE_URL}/reset-password/?token={token['reset_token']}"
    html_content = get_password_reset_email_template(reset_url)
    await send_email(user.email, "Reset Your Password - Api360", html_content, reset_url)
    return jresp

@router.post("/reset-password")
async def reset_password(
    token: str,
    response: Response,
    password: NewPassword,
    session: AsyncSession = Depends(get_db),   
    ) -> dict:

    new_password = password.new_password

    try:
        payload = decode_token(token)
    except ValueError as e:
        raise HTTPException(status_code=403, detail="Invalid or expired token")
    
    meta = payload.get("metadata") or {}
    if meta.get("purpose") != "password_reset":
        raise HTTPException(status_code=400, detail="Invalid reset token")

    user = await get_current_user(session, payload["sub"])
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Validar nonce
    if not user.password_reset_nonce or user.password_reset_nonce != meta.get("nonce"):
        raise HTTPException(status_code=400, detail="Token already used or invalid")

    # Validar contraseña
    try:
        validators.validate_password(new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    if await verify_password(session, new_password, user.password_hash, user.id):
        raise HTTPException(status_code=409, detail="The new password must be different from your current password.")
    
    user.password_hash = hash_pwd(new_password)
    user.updated_at = now()

    await revoke_all_user_refresh(session, user.id)

    # Invalidar el token (rotar nonce)
    user.password_reset_nonce = None
    session.add(user)
    await session.commit()
    
    delete_cookies(
        response, 
        ["refresh_token", "expires_at"])

    return {"message": "Password updated. Sign in again."}



"""@router.get("/verify-token")
async def verify_token_route(
    request: Request
    ) -> dict:

    try:
        payload = verify_token(request)
        payload.update({"valid": True})
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    
    jsonr = JSONResponse(payload, status_code=200)
    return jsonr"""