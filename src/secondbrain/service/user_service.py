"""Business logic for the logged-in user's own account. Owns the DB transaction."""
import asyncio

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from secondbrain.database import auth_db, user_db
from secondbrain.database.models import User
from secondbrain.service import auth_service


async def _require_password(user: User, password: str) -> None:
    valid = await asyncio.to_thread(
        auth_service._verify_password, user.hashed_password, password
    )
    if not valid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Incorrect password")


# ---------- profile ----------
async def update_profile(
    db: AsyncSession,
    user: User,
    *,
    first_name: str | None = None,
    last_name: str | None = None,
    username: str | None = None,
) -> User:
    values: dict[str, str] = {}

    if first_name is not None:
        values["first_name"] = first_name.strip()
    if last_name is not None:
        values["last_name"] = last_name.strip()
    if username is not None:
        values["username"] = username.strip().lower()

    if not values:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")
    if any(v == "" for v in values.values()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Fields must not be blank")

    new_username = values.get("username")
    if new_username and new_username != user.username:
        existing = await auth_db.get_user_by_username(db, new_username)
        if existing and existing.id != user.id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")

    try:
        updated = await user_db.update_profile(db, user.id, values)
        await db.commit()
    except IntegrityError:  # lost a race with someone taking the same username
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")
    return updated


# ---------- password ----------
async def change_password(
    db: AsyncSession, user: User, current_password: str, new_password: str
) -> None:
    await _require_password(user, current_password)
    if current_password == new_password:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "New password must be different from the current one",
        )

    hashed = await auth_service._hash_password(new_password)
    await auth_db.set_password(db, user.id, hashed)
    # A pending reset link would let someone bypass the password just chosen
    await auth_db.delete_unused_tokens(db, user.id, auth_service.RESET_PASSWORD)
    await db.commit()


# ---------- delete account ----------
async def delete_account(db: AsyncSession, user: User, password: str) -> None:
    await _require_password(user, password)
    await user_db.delete_user(db, user.id)
    await db.commit()