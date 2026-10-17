"""Business logic for admin features. Owns the DB transaction.

Authorisation (is the caller an admin?) is enforced by the `require_admin`
dependency in the routes layer; the rules here are about *what* an admin may do.
"""
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from secondbrain.database import admin_db, user_db
from secondbrain.database.models import User

_NOT_FOUND = "User not found"


async def list_users(
    db: AsyncSession,
    *,
    limit: int,
    offset: int,
    is_verified: bool | None,
    is_admin: bool | None,
    search: str | None,
) -> dict[str, Any]:
    search = search.strip() if search else None
    users, total = await admin_db.list_users(
        db,
        limit=limit,
        offset=offset,
        is_verified=is_verified,
        is_admin=is_admin,
        search=search or None,
    )
    return {"items": users, "total": total, "limit": limit, "offset": offset}


async def get_user(db: AsyncSession, user_id: int) -> tuple[User, int]:
    row = await admin_db.get_user_with_note_count(db, user_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)
    user, notes_count = row
    return user, notes_count


async def update_user(
    db: AsyncSession,
    admin: User,
    user_id: int,
    *,
    is_admin: bool | None = None,
    is_verified: bool | None = None,
) -> User:
    values: dict[str, bool] = {}
    if is_admin is not None:
        values["is_admin"] = is_admin
    if is_verified is not None:
        values["is_verified"] = is_verified

    if not values:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")
    if user_id == admin.id and values.get("is_admin") is False:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "You can't remove your own admin rights"
        )

    user = await admin_db.update_flags(db, user_id, values)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)
    await db.commit()
    return user


async def delete_user(db: AsyncSession, admin: User, user_id: int) -> None:
    if user_id == admin.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "You can't delete your own account here; use DELETE /users/me",
        )
    if not await user_db.delete_user(db, user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)
    await db.commit()


async def get_stats(db: AsyncSession) -> dict[str, Any]:
    total_users, verified_users, total_notes = await admin_db.get_stats(db)
    avg = round(total_notes / total_users, 2) if total_users else 0.0
    return {
        "total_users": total_users,
        "verified_users": verified_users,
        "total_notes": total_notes,
        "avg_notes_per_user": avg,
    }