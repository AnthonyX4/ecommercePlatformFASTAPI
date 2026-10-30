import secrets
from typing import Annotated
from datetime import datetime, UTC, timedelta

# Fastapi
from fastapi import BackgroundTasks, Depends, status, HTTPException, APIRouter, UploadFile
from fastapi.security import OAuth2PasswordRequestForm
from starlette.concurrency import run_in_threadpool # runs a sync function in a worker thread so it doesn't block the event loop

# Images
from PIL import UnidentifiedImageError
from image_utils import delete_profile_image, process_profile_image

from database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy import delete as sql_delete # bulk DELETE statement, aliased so it isn't confused with db.delete(obj)
import models

# Schemas
from schemas import (
    UserPublic, UserCreate, UserUpdate, UserPrivate, Token,
    ForgotPasswordRequest, ResetPasswordRequest, ChangePasswordRequest, MessageResponse,
)

# Authentication
from auth import (
    create_access_token, hash_password, verify_password, CurrentUser,
    generate_reset_token, hash_reset_token,
)
from config import settings

# Email
from email_utils import send_password_reset_email


router = APIRouter()


# Ownership check: the {user_id} in the path must be the user the token belongs to
async def get_owned_user(user_id: int, user: CurrentUser) -> models.User:
    if user.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this user",
        )
    return user

OwnedUser = Annotated[models.User, Depends(get_owned_user)]


# case-insensitive, so "Anthony" and "anthony" can't both exist, exclude_user_id lets a user keep their own name
async def username_taken(db: AsyncSession, username: str, exclude_user_id: int | None = None) -> bool:
    query = select(models.User.user_id).where(func.lower(models.User.username) == username.lower())
    if exclude_user_id is not None:
        query = query.where(models.User.user_id != exclude_user_id)
    result = await db.execute(query.limit(1))
    return result.first() is not None

# POST, create user
@router.post(
    "",
    response_model=UserPrivate,
    status_code=status.HTTP_201_CREATED
)
async def create_user(user: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):

    result = await db.execute(
        select(models.User).where(func.lower(models.User.email) == user.email.lower())
    )

    existing_user = result.scalars().first()

    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

    if await username_taken(db, user.username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    new_user = models.User(
        username=user.username,
        email=user.email.lower(),
        password_hash=hash_password(user.password)
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return new_user

## login_for_access_token
@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Look up user by email (case-insensitive)
    # Note: OAuth2PasswordRequestForm uses "username" field, but we treat it as email
    # soft-deleted users are excluded, matching get_current_user (their credentials are also scrubbed in delete_user)
    result = await db.execute(
        select(models.User).where(
            func.lower(models.User.email) == form_data.username.lower(),
            models.User.deleted_at.is_(None),
        ),
    )
    user = result.scalars().first()

    # Verify user exists and password is correct
    # Don't reveal which one failed (security best practice)
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token with user id as subject
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": str(user.user_id)},
        expires_delta=access_token_expires,
    )
    return Token(access_token=access_token, token_type="bearer")


def invalid_reset_token() -> HTTPException:
    """Same 400 for a missing, used, expired or orphaned token, so callers can't tell which check failed."""
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired reset token",
    )

# POST, request a password reset email
# the response is the same whether or not the email has an account, so this can't be used to find out who's registered
@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED, # accepted: the email is sent after the response, not before
)
async def forgot_password(
    request_data: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # soft-deleted users are excluded, their rows are anonymized and the account can't be recovered
    result = await db.execute(
        select(models.User).where(
            func.lower(models.User.email) == request_data.email.lower(),
            models.User.deleted_at.is_(None),
        ),
    )
    user = result.scalars().first()

    if user:
        # only the newest link works, asking again invalidates any earlier one
        await db.execute(
            sql_delete(models.PasswordResetToken).where(
                models.PasswordResetToken.user_id == user.user_id,
            ),
        )

        token = generate_reset_token() # the raw token only ever goes in the email, the db gets its hash
        reset_token = models.PasswordResetToken(
            user_id=user.user_id,
            token_hash=hash_reset_token(token),
            expires_at=datetime.now(UTC) + timedelta(minutes=settings.reset_token_expire_minutes),
        )
        db.add(reset_token)
        await db.commit()

        # runs after the response is sent: the client doesn't wait on the smtp server,
        # and a slow send can't give away that this email has an account
        background_tasks.add_task(send_password_reset_email, to_email=user.email, username=user.username, token=token)

    return MessageResponse(
        message="If an account exists with this email, you will receive password reset instructions.",
    )

# POST, set a new password using the token from the emailed link
@router.post(
    "/reset-password",
    response_model=MessageResponse,
)
async def reset_password(
    request_data: ResetPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # the db only has hashes, so hash what we were given and look that up
    result = await db.execute(
        select(models.PasswordResetToken).where(
            models.PasswordResetToken.token_hash == hash_reset_token(request_data.token),
        ),
    )
    reset_token = result.scalars().first()

    if not reset_token:
        raise invalid_reset_token()

    # sqlite doesn't store the timezone, so expires_at comes back naive, it was saved in utc
    if reset_token.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        await db.delete(reset_token)
        await db.commit()
        raise invalid_reset_token()

    result = await db.execute(
        select(models.User)
        .where(models.User.user_id == reset_token.user_id)
        .where(models.User.deleted_at.is_(None)),
    )
    user = result.scalars().first()

    if not user:
        raise invalid_reset_token()

    user.password_hash = hash_password(request_data.new_password)

    # links are single use, this one and any other pending ones for the user are gone after a reset
    await db.execute(
        sql_delete(models.PasswordResetToken).where(
            models.PasswordResetToken.user_id == user.user_id,
        ),
    )
    await db.commit()

    return MessageResponse(
        message="Password reset successfully. You can now log in with your new password.",
    )

## get_current_user
# declared before /{user_id} so "me" is not parsed as a user id
@router.get("/me", response_model=UserPrivate)
async def read_current_user(user: CurrentUser):
    """Get the currently authenticated user."""
    return user

# PATCH, change the logged in user's password
# also declared before /{user_id}, the path is /me/password so there's no id to match
@router.patch(
    "/me/password",
    response_model=MessageResponse,
)
async def change_password(
    request_data: ChangePasswordRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # proving you know the current password means a stolen token alone can't lock the owner out
    if not verify_password(request_data.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    user.password_hash = hash_password(request_data.new_password)

    # a pending reset link was issued for the old password, so it stops working
    await db.execute(
        sql_delete(models.PasswordResetToken).where(
            models.PasswordResetToken.user_id == user.user_id,
        ),
    )
    await db.commit()

    return MessageResponse(message="Password changed successfully.")

# GET, get user
@router.get(
    "/{user_id}",
    response_model=UserPublic,
)
async def get_user(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):

    # soft-deleted users are hidden, to the outside they no longer exist
    result = await db.execute(
        select(models.User)
        .where(models.User.user_id == user_id)
        .where(models.User.deleted_at.is_(None))
    )
    existing_user = result.scalars().first()

    if not existing_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return existing_user


# PATCH, update user
@router.patch(
    "/{user_id}",
    response_model=UserPrivate,
)
async def update_user(user_update: UserUpdate, user: OwnedUser, db: Annotated[AsyncSession, Depends(get_db)]):

    update_data = user_update.model_dump(exclude_unset=True, exclude_none=True) # converted into dictionary, explicit nulls are ignored instead of crashing on None.lower()
    current_password = update_data.pop("current_password", None)
    changes_email = "email" in update_data

    # changing the email requires proving you know the current password,
    # so a stolen token alone cannot lock the owner out of their account
    if changes_email:
        if not current_password or not verify_password(current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Current password is incorrect",
            )

    # if email is changing, make sure no other user already has it
    if changes_email:
        result = await db.execute(
            select(models.User).where(
                func.lower(models.User.email) == update_data["email"].lower(),
                models.User.user_id != user.user_id,
            )
        )
        email_taken = result.scalars().first()

        if email_taken:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    # a username isn't a credential, so changing it doesn't need current_password
    if "username" in update_data:
        if await username_taken(db, update_data["username"], exclude_user_id=user.user_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    for field, value in update_data.items():
        if field == "email":
            user.email = value.lower()
        else:
            setattr(user, field, value)

    # a pending reset link may have been sent to the old email, so it stops working
    if changes_email:
        await db.execute(
            sql_delete(models.PasswordResetToken).where(
                models.PasswordResetToken.user_id == user.user_id,
            ),
        )

    await db.commit()
    await db.refresh(user)

    return user

# DELETE, delete user
# will cascade delete all cart items too
# users with no orders are hard deleted
# users with orders are soft deleted + anonymized so order history is kept
@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_user(user: OwnedUser, db: Annotated[AsyncSession, Depends(get_db)]):

    result = await db.execute(
        select(models.Order.order_id).where(models.Order.user_id == user.user_id).limit(1)
    )
    has_orders = result.first()

    old_filename = user.image_file

    if has_orders:
        # scrub personal data, the row stays so Order.user_id still points at something
        user.username = f"[deleted-{user.user_id}]" # brackets fail USERNAME_PATTERN, so no real user can already have it
        user.email = f"deleted-{user.user_id}@invalid.example" # .example is reserved (RFC 2606) and, unlike .invalid, passes EmailStr
        user.password_hash = hash_password(secrets.token_urlsafe(32)) # destroy the old hash, leave a well-formed one nothing can match
        user.image_file = None # the picture is personal data too
        user.deleted_at = datetime.now(UTC)
        await db.refresh(user, attribute_names=["cart_items", "reset_tokens"]) # load both up front, async can't lazy load them on access
        user.cart_items.clear() # delete-orphan cascade removes the cart rows
        user.reset_tokens.clear() # and any pending reset links
    else:
        await db.delete(user) # awaited because the cascade may need to load cart_items/reset_tokens before deleting them
    await db.commit()

    # file is removed only after the commit succeeds, if the commit failed the user would still point at it
    delete_profile_image(old_filename)


# PATCH, upload/replace profile picture
# multipart/form-data with the image in a field named "file", not json
@router.patch(
    "/{user_id}/picture",
    response_model=UserPrivate,
)
async def upload_profile_picture(file: UploadFile, user: OwnedUser, db: Annotated[AsyncSession, Depends(get_db)]):

    content = await file.read()

    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is {settings.max_upload_size_bytes // (1024 * 1024)}MB",
        )

    # image processing is CPU bound, so it runs in a thread instead of on the event loop
    try:
        new_filename = await run_in_threadpool(process_profile_image, content)
    except UnidentifiedImageError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file. Please upload a valid image (JPEG, PNG, GIF, WebP).",
        ) from err

    old_filename = user.image_file

    user.image_file = new_filename
    await db.commit()
    await db.refresh(user)

    # old file is deleted after the commit, deleting first would leave the user pointing at a missing file if the commit failed
    delete_profile_image(old_filename)

    return user


# DELETE, remove profile picture (falls back to the default one)
@router.delete(
    "/{user_id}/picture",
    response_model=UserPrivate,
)
async def delete_profile_picture(user: OwnedUser, db: Annotated[AsyncSession, Depends(get_db)]):

    old_filename = user.image_file

    if old_filename is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No profile picture to delete",
        )

    user.image_file = None
    await db.commit()
    await db.refresh(user)

    delete_profile_image(old_filename)

    return user

