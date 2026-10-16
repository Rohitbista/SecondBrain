"""Database access for notes.

Only queries live here. No business rules and no commits: the service layer
owns the transaction.

The (large) embedding column is deferred on reads so it is never loaded
unless explicitly needed.
"""
from typing import Any, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer, load_only

from secondbrain.database.models import Note


async def create_note(
    db: AsyncSession,
    *,
    user_id: int,
    title: str,
    content: str,
    embedding: list[float],
) -> Note:
    note = Note(user_id=user_id, title=title, content=content, embedding=embedding)
    db.add(note)
    await db.flush()  # assigns note.id
    return note


async def get_note(db: AsyncSession, note_id: int, user_id: int) -> Note | None:
    """Fetch a note only if it belongs to the user."""
    result = await db.execute(
        select(Note)
        .options(defer(Note.embedding))
        .where(Note.id == note_id, Note.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def list_notes(
    db: AsyncSession, user_id: int, *, limit: int, offset: int
) -> Sequence[Note]:
    result = await db.execute(
        select(Note)
        .options(defer(Note.embedding))
        .where(Note.user_id == user_id)
        .order_by(Note.created_at.desc(), Note.id.desc())  # id breaks ties
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


async def count_notes(db: AsyncSession, user_id: int) -> int:
    result = await db.execute(
        select(func.count()).select_from(Note).where(Note.user_id == user_id)
    )
    return result.scalar_one()


async def update_note(db: AsyncSession, note: Note, values: dict[str, Any]) -> Note:
    for key, value in values.items():
        setattr(note, key, value)
    await db.flush()
    return note


async def delete_note(db: AsyncSession, note_id: int, user_id: int) -> bool:
    """Delete a note owned by the user. Returns True if a row was deleted."""
    result = await db.execute(
        delete(Note)
        .where(Note.id == note_id, Note.user_id == user_id)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount > 0


async def get_notes_batch(
    db: AsyncSession, user_id: int, *, after_id: int, limit: int
) -> Sequence[Note]:
    """Keyset-paginated batch (id > after_id) with only the fields needed to embed."""
    result = await db.execute(
        select(Note)
        .options(load_only(Note.id, Note.title, Note.content))
        .where(Note.user_id == user_id, Note.id > after_id)
        .order_by(Note.id)
        .limit(limit)
    )
    return result.scalars().all()