"""Database access for admin features.

Only queries live here. No business rules and no commits: the service layer
owns the transaction. Callers must already have checked that the requester is
an admin.
"""
from typing import Sequence

from sqlalchemy import Row, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from secondbrain.database.models import Note, User
from secondbrain.database.search_db import _escape_like


def _user_filters(
    is_verified: bool | None, is_admin: bool | None, search: str | None
) -> list:
    conditions = []
    if is_verified is not None:
        conditions.append(User.is_verified.is_(is_verified))
    if is_admin is not None:
        conditions.append(User.is_admin.is_(is_admin))
    if search:
        pattern = f"%{_escape_like(search)}%"
        conditions.append(
            or_(
                User.email.ilike(pattern, escape="\\"),
                User.username.ilike(pattern, escape="\\"),
            )
        )
    return conditions


async def list_users(
    db: AsyncSession,
    *,
    limit: int,
    offset: int,
    is_verified: bool | None = None,
    is_admin: bool | None = None,
    search: str | None = None,
) -> tuple[Sequence[User], int]:
    """One page of users (oldest first) plus the total number matching the filters."""
    conditions = _user_filters(is_verified, is_admin, search)

    total = await db.scalar(select(func.count(User.id)).where(*conditions))
    result = await db.execute(
        select(User).where(*conditions).order_by(User.id).limit(limit).offset(offset)
    )
    return result.scalars().all(), total or 0


async def get_user_with_note_count(db: AsyncSession, user_id: int) -> Row | None:
    """Row of (User, notes_count), or None if the user doesn't exist."""
    result = await db.execute(
        select(User, func.count(Note.id))
        .outerjoin(Note, Note.user_id == User.id)
        .where(User.id == user_id)
        .group_by(User.id)
    )
    return result.one_or_none()


async def update_flags(
    db: AsyncSession, user_id: int, values: dict[str, bool]
) -> User | None:
    """Update is_admin / is_verified. Returns the refreshed user, or None if not found."""
    result = await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(**values)
        .returning(User.id)
        .execution_options(synchronize_session=False)
    )
    if result.scalar_one_or_none() is None:
        return None
    user = await db.get(User, user_id)
    await db.refresh(user)
    return user


async def get_stats(db: AsyncSession) -> tuple[int, int, int]:
    """(total_users, verified_users, total_notes) in a single round trip."""
    total_users = select(func.count(User.id)).scalar_subquery()
    verified_users = (
        select(func.count(User.id)).where(User.is_verified.is_(True)).scalar_subquery()
    )
    total_notes = select(func.count(Note.id)).scalar_subquery()

    result = await db.execute(select(total_users, verified_users, total_notes))
    row = result.one()
    return row[0], row[1], row[2]