"""Database access for authentication.

Only queries live here. No business rules and no commits: the service layer
owns the transaction.
"""
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from secondbrain.database.models import User, UserToken


# ---------- users ----------
async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    return await db.get(User, user_id)


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_login(db: AsyncSession, identifier: str) -> User | None:
    """Look a user up by email OR username (usernames can't contain '@')."""
    result = await db.execute(
        select(User).where(or_(User.email == identifier, User.username == identifier))
    )
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    *,
    email: str,
    first_name: str,
    last_name: str,
    username: str,
    hashed_password: str,
) -> User:
    user = User(
        email=email,
        first_name=first_name,
        last_name=last_name,
        username=username,
        hashed_password=hashed_password,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)  # load server defaults (created_at, is_admin, ...)
    return user


async def mark_verified(db: AsyncSession, user_id: int) -> None:
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(is_verified=True)
        .execution_options(synchronize_session=False)
    )


async def set_password(db: AsyncSession, user_id: int, hashed_password: str) -> None:
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(hashed_password=hashed_password)
        .execution_options(synchronize_session=False)
    )


# ---------- tokens ----------
async def create_token(
    db: AsyncSession, *, user_id: int, purpose: str, token_hash: str, expires_at
) -> None:
    db.add(
        UserToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=token_hash,
            expires_at=expires_at,
        )
    )
    await db.flush()


async def delete_unused_tokens(db: AsyncSession, user_id: int, purpose: str) -> None:
    await db.execute(
        delete(UserToken)
        .where(
            UserToken.user_id == user_id,
            UserToken.purpose == purpose,
            UserToken.used_at.is_(None),
        )
        .execution_options(synchronize_session=False)
    )


async def consume_token(db: AsyncSession, token_hash: str, purpose: str) -> int | None:
    """Atomically mark a valid token as used and return its user_id.

    A single UPDATE ... WHERE used_at IS NULL means two simultaneous requests
    can never both succeed with the same token.
    """
    result = await db.execute(
        update(UserToken)
        .where(
            UserToken.token_hash == token_hash,
            UserToken.purpose == purpose,
            UserToken.used_at.is_(None),
            UserToken.expires_at > func.now(),
        )
        .values(used_at=func.now())
        .returning(UserToken.user_id)
        .execution_options(synchronize_session=False)
    )
    return result.scalar_one_or_none()