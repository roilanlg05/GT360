from fastapi import HTTPException
from features.auth.schemas import User, Manager, Crew, Token
from psqlmodel import Select
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from datetime import timedelta, datetime, timezone
from jose import jwt, JWTError
from shared.settings import settings
from shared.redis.redis_client import redis_client
import secrets
import hashlib

ph = PasswordHasher()

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
            domain="192.168.0.133",
            path="/",
            max_age=30 * 24 * 60 * 60,  # 30 días
            expires = None,
            partitioned = False
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
            secure=False,        # Descomentar con HTTPS
            samesite="lax",
            domain="192.168.0.133",
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
        
    await session.commit()
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

    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        raise ValueError("Missing authentication token")
    
    token = auth_header.split(" ", 1)[1].strip()

    if not token:
        raise ValueError("Missing authentication token")
    return token

async def blacklist_token(token: str, exp_seconds: int = 300):
    if await redis_client.exists(f"blacklist:{token}"):
        raise ValueError("Token revoked")
    
    await redis_client.setex(f"blacklist:{token}", exp_seconds, "blacklisted")