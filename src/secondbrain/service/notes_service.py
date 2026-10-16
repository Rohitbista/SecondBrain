"""Business logic for notes. Owns the transaction (commits happen here)."""
import asyncio
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from secondbrain.database import notes_db
from secondbrain.database.models import Note
from secondbrain.utils.embeddings import build_note_text, embed_text, embed_texts

MAX_LIMIT = 100
REINDEX_BATCH_SIZE = 50

# Columns returned to the client (everything except the embedding vector).
_OUT_ATTRS = ["id", "user_id", "title", "content", "created_at", "updated_at"]


def _not_found() -> HTTPException:
    # 404 (not 403) so we never reveal that another user's note exists.
    return HTTPException(status.HTTP_404_NOT_FOUND, "Note not found")


async def _reload(db: AsyncSession, note: Note) -> Note:
    """Re-read server-generated/expired columns after a commit (no embedding)."""
    await db.refresh(note, _OUT_ATTRS)
    return note


async def create_note(db: AsyncSession, user_id: int, title: str, content: str) -> Note:
    embedding = await asyncio.to_thread(embed_text, build_note_text(title, content))
    note = await notes_db.create_note(
        db, user_id=user_id, title=title, content=content, embedding=embedding
    )
    await db.commit()
    return await _reload(db, note)


async def list_notes(
    db: AsyncSession, user_id: int, limit: int, offset: int
) -> tuple[list[Note], int]:
    limit = max(1, min(limit, MAX_LIMIT))
    offset = max(0, offset)
    items = await notes_db.list_notes(db, user_id, limit=limit, offset=offset)
    total = await notes_db.count_notes(db, user_id)
    return list(items), total


async def get_note(db: AsyncSession, user_id: int, note_id: int) -> Note:
    note = await notes_db.get_note(db, note_id, user_id)
    if note is None:
        raise _not_found()
    return note


async def update_note(
    db: AsyncSession, user_id: int, note_id: int, data: dict[str, Any]
) -> Note:
    note = await get_note(db, user_id, note_id)

    # Keep only fields whose value actually differs.
    changed = {k: v for k, v in data.items() if getattr(note, k) != v}
    if not changed:
        return note  # nothing to save, nothing to re-embed

    new_title = changed.get("title", note.title)
    new_content = changed.get("content", note.content)
    changed["embedding"] = await asyncio.to_thread(
        embed_text, build_note_text(new_title, new_content)
    )

    await notes_db.update_note(db, note, changed)
    await db.commit()
    return await _reload(db, note)


async def delete_note(db: AsyncSession, user_id: int, note_id: int) -> None:
    deleted = await notes_db.delete_note(db, note_id, user_id)
    if not deleted:
        raise _not_found()
    await db.commit()


async def reindex_notes(db: AsyncSession, user_id: int) -> int:
    """Re-embed every note of the user in batches. Returns how many were re-embedded.

    Each batch is committed on its own, so progress is kept if something fails
    part-way and a re-run simply continues the work.
    """
    last_id = 0
    total = 0
    while True:
        batch = await notes_db.get_notes_batch(
            db, user_id, after_id=last_id, limit=REINDEX_BATCH_SIZE
        )
        if not batch:
            break

        texts = [build_note_text(n.title, n.content) for n in batch]
        vectors = await asyncio.to_thread(embed_texts, texts)

        last_id = batch[-1].id  # read before commit expires the objects
        for note, vector in zip(batch, vectors):
            note.embedding = vector
        await db.commit()
        total += len(batch)
    return total