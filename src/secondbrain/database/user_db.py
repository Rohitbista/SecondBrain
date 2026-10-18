"""Database access for the logged-in user's own account.

Only queries live here. No business rules and no commits: the service layer
owns the transaction.
"""
from typing import Any

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from secondbrain.database.models import User


async def update_profile(db: AsyncSession, user_id: int, values: dict[str, Any]) -> User:
    """Apply a partial update and return the refreshed user."""
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    user = await db.get(User, user_id)
    await db.refresh(user)  # pick up updated_at set by the DB trigger
    return user


async def delete_user(db: AsyncSession, user_id: int) -> bool:
    """Delete a user. Notes, chats and tokens go with it via ON DELETE CASCADE.

    Returns False when no such user existed.
    """
    result = await db.execute(
        delete(User)
        .where(User.id == user_id)
        .returning(User.id)
        .execution_options(synchronize_session=False)
    )
    return result.scalar_one_or_none() is not None