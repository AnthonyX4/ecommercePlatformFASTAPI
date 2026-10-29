import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from typing import Annotated

# Fastapi
from fastapi import Depends, status, HTTPException

# Database
from database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import models

import jwt
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash

from config import settings

password_hash = PasswordHash.recommended()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/users/token") # token url must match 
                                                                 # login endpoint path
                                                                 # purpose is to extract the token from the authorization header
                                                                 # note that tokenUrl is purely for docs

def hash_password(password: str) -> str:
    return password_hash.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)

# Password reset tokens
def generate_reset_token() -> str:
    # 32 random bytes from the os's cryptographic rng, url safe so it fits in ?token= without encoding
    return secrets.token_urlsafe(32)

def hash_reset_token(token: str) -> str:
    # sha256 instead of argon2: the token is random, not guessable like a password, so a slow hash adds nothing,
    # and unlike argon2 (salted) the same token always gives the same hash, so we can look the row up by it
    return hashlib.sha256(token.encode()).hexdigest()

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta: # expires_delta is an optional field
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            minutes=settings.access_token_expire_minutes,
        )
    to_encode.update({"exp": expire}) # appends to dictionary
    encoded_jwt = jwt.encode(
        payload=to_encode, # payload first
        key=settings.secret_key.get_secret_value(), # key second
        algorithm=settings.algorithm,
    )
    return encoded_jwt

# verify_access_token
def verify_access_token(token: str) -> str | None:
    """Verify a JWT access token and return the subject (user id) if valid."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.InvalidTokenError:
        return None
    else:
        return payload.get("sub") # returns user id

def credentials_exception() -> HTTPException:
    """Same 401 for every auth failure, so callers can't tell which check failed."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], # oauth2_scheme pulls token string out of Auhtorization header
    db: Annotated[AsyncSession, Depends(get_db)]
    ) -> models.User:

    # verify access token
    # convert string to int user_id
    # if timed_out or invalid user, return error
    # else query datebase for user and return existing user

    user_id = verify_access_token(token)
    if user_id is None:
        raise credentials_exception()

    # Validate user_id is a valid integer (defense against malformed JWT)
    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        raise credentials_exception()

    # soft-deleted users are excluded: their tokens stay signed and unexpired after deletion
    result = await db.execute(
        select(models.User)
        .where(models.User.user_id == user_id_int)
        .where(models.User.deleted_at.is_(None)),
    )
    user = result.scalars().first()
    if not user:
        raise credentials_exception()
    return user


CurrentUser = Annotated[models.User, Depends(get_current_user)]


# builds on get_current_user, so an admin still needs a valid, unexpired token for a non-deleted user
async def get_current_admin(user: CurrentUser) -> models.User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


AdminUser = Annotated[models.User, Depends(get_current_admin)]
