from fastapi import HTTPException, Request
from shared.db.schemas import User, Manager, Crew, Token
from psqlmodel import Select
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from datetime import timedelta, datetime, timezone
from jose import jwt, JWTError
from shared.settings import settings
from shared.redis.redis_client import redis_client
import secrets
import hashlib
from features.trips.utils import get_locations_by_org_id

ph = PasswordHasher()

WEBHOOK_SECRET=settings.WEBHOOK_SECRET

def now() -> datetime:
    """
    Returns the current UTC date and time.

    return -> The current datetime in UTC.
    """
    return datetime.now(timezone.utc)

def require_user(request):

    """
    Ensures that the request contains authenticated user data.

    Args:
        request: The incoming request object.

    raises: 
        HTTPException (401) if user data is not present in the request.

    return -> The user data from the request state.
    """

    user = request.state.user_data

    if not user:
        raise HTTPException(status_code=401, detail="not authorized")
    
    return user["id"]

async def get_current_user(session, user_id) -> User:

    """
    Retrieves a user from the database by user ID.

    Args:
        session: The database session to use for the query.
        user_id: The ID of the user to retrieve.

    return -> The User object if found, otherwise None.
    """

    user = await session.get(User, user_id)
    return user


async def verify_if_exist(
    session, 
    email: str | None = None, 
    phone: str | None = None
    ) -> None:

    """
    Checks if a user with the given email or phone already exists.

    Args:
        session: The database session to use for the query.
        email: The email address to check for existence (optional).
        phone: The phone number to check for existence (optional).

    raises: 
        ValueError if the email or phone is already in use.

    return -> None if no user exists with the given email or phone.
    """   

    conds = [(User.email == email.lower())]
    if phone:
        conds.append((User.phone == phone))

    combined = conds[0]
    for c in conds[1:]:
        combined = combined | c

    stmt = Select(User.email, User.phone).Where(combined)
    row = await session.exec(stmt).first()

    if not row:
        return

    if row["email"] and row["email"].lower() == email.lower():
        raise ValueError("Email already in use")
    if phone and row["phone"] == phone:
        raise ValueError("Phone already in use")


def hash_pwd(plain) -> str:

    """
    Hashes a plain password using Argon2 and a secret pepper.

    Args:
        plain: The plain text password to hash.

    return -> The hashed password string.
    """

    return ph.hash(plain + settings.PEPPER)

def encode_token(sub: str, 
        metadata: dict | None = None,
        expires_in: timedelta = timedelta(minutes=int(settings.TOKEN_DURATION)),
        type:str | None = "access"
        ) -> dict:
        
        """
        Generates a JWT access token.

        Args:
            sub: Unique identifier for the subject (e.g., user ID).
            metadata: Additional information to include in the token payload (optional).
            expires_in: Token validity duration (default is settings.TOKEN_DURATION in minutes).
            
        return -> Dictionary with the access token and its expiration timestamp. 
        """

        now = datetime.now(timezone.utc)
        iat = int(now.timestamp())
        exp = int((now + expires_in).timestamp())

        payload = {
            "sub": sub,
            "iat": iat,
            "exp": exp
        }

        if metadata:
            payload["metadata"] = metadata

        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.ALGORITHM)
        
        return {
            f"{type}_token": token,
            "exp": exp
        }

def decode_token(token: str) -> dict:

    """
    Decodes a JWT token and returns its payload.

    Args:
        token: The JWT token string to decode.

    raises:
        ValueError: If the token is invalid or cannot be decoded.

    return -> The decoded payload as a dictionary.
    """

    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload 
    except JWTError:
        raise ValueError("Invalid token")

async def get_user_by_email(session, email: str) -> User: 

    """
    Retrieves a user by email, including related Manager and Crew data.

    Args:
        session: The database session to use for the query.
        email: The email address of the user to retrieve.

    return -> The User object if found, otherwise None.
    """

    user = await session.exec(
        Select(User)
        .Include(Manager)
        .Include(Crew)
        .Where(User.email == email)
    ).first()

    return user

async def verify_password(session, plain: str, hashed: str,  user_id: str | None = None) -> bool:

    """
    Verifies a plain password against its Argon2 hash and rehashes if needed.

    Args:
        session: The database session to use for updating the hash if rehash is needed.
        plain: The plain text password to verify.
        hashed: The stored Argon2 hashed password.
        user_id: The ID of the user (used for updating the hash if needed).

    return -> True if the password is correct, False otherwise.
    """

    try:
        ph.verify(hashed, plain + settings.PEPPER)
        
        if ph.check_needs_rehash(hashed):
            new_hash = ph.hash(plain + settings.PEPPER)
            
            if user_id:
                user = await session.get(User, user_id)
                user.password_hash = new_hash
                await session.commit()
            return True
        
        return True  
        
    except VerifyMismatchError:
        return False

def gen_refresh_token() -> tuple[str, str, datetime]:
    
    """
    Generates a secure refresh token, its hash, and expiration date.

    return -> (raw_token:str, token_hash:str, exp:datetime)
        raw_token: The plain refresh token to send to the client.
        token_hash: The SHA-256 hash of the token to store securely.
        exp: The expiration datetime for the refresh token.
    """

    raw = secrets.token_urlsafe(64)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    exp = datetime.now(timezone.utc) + timedelta(days=30)
    
    return raw, token_hash, exp

async def save_refresh_in_db(
    session, 
    user_id: str, 
    token_hash: str, 
    exp: datetime
    ) -> Token:

    """
    Saves a refresh token in the database.

    Args:
        session: The database session to use for saving the token.
        user_id: The ID of the user to associate with the refresh token.
        token_hash: The SHA-256 hash of the refresh token.
        exp: The expiration datetime for the refresh token.

    return -> The created Token object.
    """

    refresh_token = Token(
        user_id=user_id,
        token_hash=token_hash,  
        expires_at=exp,        
        revoked=False,
        token_type="refresh"
    )
    session.add(refresh_token) 
    await session.commit()

    return refresh_token

def set_cookies(response, data:dict):

    """
    Sets multiple HTTP-only cookies in the response.

    Args:
        response: The FastAPI Response object to set cookies on.
        data: Dictionary where keys are cookie names and values are cookie values.

    return -> None
    """

    for k, v in data.items():
        response.set_cookie(
            key=k,
            value=v, 
            httponly=True, 
            secure=False,  
            samesite="lax",
            #domain="192.168.0.133",
            path="/",
            max_age=30 * 24 * 60 * 60,  # 30 días
        )


def delete_cookies(response, cookies:list[str]):
        
    """
    Deletes multiple cookies from the response.

    Args:
        response: The FastAPI Response object to delete cookies from.
        cookies: List of cookie names to delete.

    return -> None
    """

    for cookie in cookies:
        response.delete_cookie(
            key=cookie,
            path="/",
            httponly=True,
            secure=False,  # Cambia a True si usas HTTPS en producción
            samesite="lax", 
            #domain="192.168.0.133", # Descomenta y ajusta el dominio si lo usas en set_cookies
        )


async def revoke_all_user_refresh(session, user_id: str):
        
    """
    Revokes all active refresh tokens for a user.

    Args:
        session: The database session to use for the query and update.
        user_id: The ID of the user whose refresh tokens will be revoked.

    return -> The number of tokens revoked (int).
    """

    rows = await session.exec(
        Select(Token)
        .Where(
            (Token.user_id == user_id) & 
            (Token.revoked == False) & 
            (Token.token_type=="refresh")
        )
    ).all()

    for r in rows:
        r.revoked = True
        session.add(r)
        
    await session.flush()
    return len(rows)

async def get_refresh_by_hash(session, refresh_token: str) -> Token | None:
        
    """
    Retrieves a refresh token from the database by its hash.

    Args:
        session: The database session to use for the query.
        refresh_token: The raw refresh token string to look up.

    return -> The Token object if found, otherwise None.
    """

    refresh_token = hashlib.sha256(refresh_token.encode()).hexdigest()  # Calcula hash del valor recibido

    token = await session.exec(
        Select(Token)
        .Where(Token.token_hash == refresh_token)
    ).first()

    return token

async def revoke_refresh(session, refresh_id) -> Token:

    """
    Revokes a specific refresh token by its ID.

    Args:
        session: The database session to use for the update.
        refresh_id: The ID of the refresh token to revoke.

    return -> The updated Token object.
    """

    refresh = await session.get(Token, refresh_id)  
    if refresh and not refresh.revoked:
        refresh.revoked = True
        session.add(refresh)
        await session.commit()
        await session.refresh(refresh)
    return refresh

async def validate_refresh(session, refresh_token) -> Token:

    """
    Validates a refresh token by checking its existence, revocation status, and expiration.

    Args:
        session: The database session to use for the query.
        refresh_token: The raw refresh token string to validate.

    raises:
        HTTPException (401): If the token is invalid, expired, or revoked.

    return -> The valid Token object.
    """

    refresh = await get_refresh_by_hash(session, refresh_token)

    if not refresh:                                           
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if refresh.revoked == True:
        raise HTTPException(status_code=401, detail="Refresh token expired or revoked")
    
    if refresh.expires_at <= now():
        await revoke_refresh(session, refresh.id)
        raise HTTPException(status_code=401, detail="Expired refresh")
    
    return refresh
    

def get_token(request):

    """
    Extracts the Bearer token from the Authorization header in a standard HTTP request.

    Args:
        request: The incoming HTTP request object.

    Raises:
        ValueError: If the Authorization header is missing or does not contain a Bearer token.

    Returns:
        str: The extracted Bearer token.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise ValueError("Missing authentication token")
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise ValueError("Missing authentication token")
    return token

async def blacklist_token(token: str, exp_seconds: int = 300):
    """
    Blacklists a JWT token by storing it in Redis with an expiration time.

    Args:
        token (str): The JWT token to blacklist.
        exp_seconds (int, optional): Expiration time in seconds for the blacklist entry. Default is 300 seconds.

    Raises:
        ValueError: If the token is already blacklisted.

    Returns:
        None
    """
    if await redis_client.exists(f"blacklist:{token}"):
        raise ValueError("Token revoked")
    await redis_client.setex(f"blacklist:{token}", exp_seconds, "blacklisted")

def verify_role(roles: list):
        
    """
    Checks if the current user has at least one of the required roles.

    Args:
        roles: List of roles to check against the user's assigned roles.

    Raises:
        HTTPException: If the user does not have any of the required roles.

    Returns:
        None. Proceeds if the user has the required role(s).
    """

    def _dep(request: Request):
        user_data = request.state.user_data
        print(f"USER DATA: {user_data}")
        if not user_data:
            raise HTTPException(status_code=401, detail="Missing or invalid authentication")
        #
        role = None
        if user_data:
            role = user_data.get("role")
            print(f"USER ROLE: {role}")
        if not role or role not in roles:
            raise HTTPException(
                status_code=403,
                detail="Not Authorized: We couldn't validate the role"
            )
        return user_data
    return _dep

#===================================================================================
# Webhook Auth
#===================================================================================

import hmac
import hashlib
import time
from typing import Tuple, Optional

def _parse_signature_header(signature: str) -> Tuple[Optional[int], Optional[str]]:
    """
    Parses a signature header for webhook verification.

    Accepts:
        - "t=1700000000,v1=abcdef..." (with timestamp)
        - "v1=abcdef..." (without timestamp)
        - "abcdef..." (raw hex signature)

    Args:
        signature (str): The signature header value.

    Returns:
        tuple: (timestamp as int or None, hex signature as str or None)
    """
    if not signature:
        return None, None

    sig = signature.strip()

    # Case: "t=...,v1=..."
    if "t=" in sig and "v1=" in sig:
        parts = [p.strip() for p in sig.split(",")]
        t_val = None
        v1_val = None
        for p in parts:
            if p.startswith("t="):
                try:
                    t_val = int(p.split("=", 1)[1].strip())
                except Exception:
                    t_val = None
            elif p.startswith("v1="):
                v1_val = p.split("=", 1)[1].strip()
        return t_val, v1_val

    # Case: "v1=..."
    if sig.startswith("v1="):
        return None, sig.split("=", 1)[1].strip()

    # Case: raw hex
    return None, sig


def verify_webhook_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    """
    Verifies an HMAC SHA256 signature for webhook requests using a timing-safe comparison.

    Recommended usage: signature header "t=<unix>,v1=<hex>"
    Anti-replay: rejects if timestamp is outside a 5-minute window.

    Args:
        raw_body (bytes): The raw request body.
        signature (str): The signature header value.
        secret (str): The shared secret for HMAC.

    Returns:
        bool: True if the signature is valid, False otherwise.
    """
    if not secret or not isinstance(secret, str):
        return False

    ts, provided_hex = _parse_signature_header(signature)
    if not provided_hex:
        return False

    # Anti-replay (if timestamp is present)
    if ts is not None:
        now = int(time.time())
        # 5-minute window (adjust if needed)
        if abs(now - ts) > 300:
            return False
        msg = f"{ts}.".encode("utf-8") + raw_body
    else:
        # Less secure fallback (no timestamp)
        msg = raw_body

    expected_hex = hmac.new(
        key=secret.encode("utf-8"),
        msg=msg,
        digestmod=hashlib.sha256
    ).hexdigest()

    # compare_digest requires same type/format
    return hmac.compare_digest(expected_hex, provided_hex)


async def user_can_access_location(session, org_id, location_id):
    """
    Checks if a user (by org_id) can access a specific location_id.

    Args:
        org_id (str): The organization ID.
        location_id (str): The location ID to check.

    Returns:
        bool: True if the user can access the location, False otherwise.
    """

    locations = await get_locations_by_org_id(session, org_id)
    location_ids = [loc["id"] for loc in locations]  # Ajusta según la estructura de tu objeto location

    return location_id in location_ids