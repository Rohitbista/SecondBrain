"""Database access for chat sessions and messages.

Only queries live here. No business rules and no commits: the service layer
owns the transaction. Ownership is always enforced through user_id on the
session; messages are only reachable after the session has been verified.
"""
from typing import Any, Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from secondbrain.database.models import ChatMessage, ChatSession


async def create_session(db: AsyncSession, *, user_id: int, title: str) -> ChatSession:
    session = ChatSession(user_id=user_id, title=title)
    db.add(session)
    await db.flush()  # assigns session.id
    return session


async def get_session(
    db: AsyncSession, session_id: int, user_id: int
) -> ChatSession | None:
    """Fetch a session only if it belongs to the user."""
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id, ChatSession.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def add_message(
    db: AsyncSession,
    *,
    session_id: int,
    role: str,
    content: str,
    sources: list[dict[str, Any]] | None = None,
) -> ChatMessage:
    message = ChatMessage(
        session_id=session_id, role=role, content=content, sources=sources
    )
    db.add(message)
    await db.flush()
    return message


async def touch_session(db: AsyncSession, session_id: int) -> None:
    """Bump updated_at so the session moves to the top of the history list."""
    await db.execute(
        update(ChatSession)
        .where(ChatSession.id == session_id)
        .values(updated_at=func.now())
        .execution_options(synchronize_session=False)
    )


async def get_recent_messages(
    db: AsyncSession, session_id: int, *, limit: int
) -> Sequence[ChatMessage]:
    """The last `limit` messages, NEWEST first (caller reverses for prompts)."""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.desc())
        .limit(limit)
    )
    return result.scalars().all()


async def get_messages(db: AsyncSession, session_id: int) -> Sequence[ChatMessage]:
    """All messages of a session, oldest first."""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id)
    )
    return result.scalars().all()


async def list_sessions(
    db: AsyncSession, user_id: int, *, limit: int, offset: int
) -> Sequence[ChatSession]:
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


async def count_sessions(db: AsyncSession, user_id: int) -> int:
    result = await db.execute(
        select(func.count()).select_from(ChatSession).where(ChatSession.user_id == user_id)
    )
    return result.scalar_one()


async def delete_session(db: AsyncSession, session_id: int, user_id: int) -> bool:
    """Delete one session owned by the user (messages go via ON DELETE CASCADE)."""
    result = await db.execute(
        delete(ChatSession)
        .where(ChatSession.id == session_id, ChatSession.user_id == user_id)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount > 0


async def delete_all_sessions(db: AsyncSession, user_id: int) -> int:
    """Delete every session of the user. Returns how many were deleted."""
    result = await db.execute(
        delete(ChatSession)
        .where(ChatSession.user_id == user_id)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount