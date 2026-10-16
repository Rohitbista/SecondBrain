"""Database access for search.

Only queries live here. No business rules and no commits.

Both queries select plain columns (never the whole Note entity), so the large
embedding vector is never loaded into Python. Every query filters by user_id.
"""
from typing import Sequence

from sqlalchemy import Row, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from secondbrain.database.models import Note


def _escape_like(term: str) -> str:
    """Escape LIKE wildcards so the user's text is matched literally."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def semantic_search(
    db: AsyncSession, user_id: int, *, query_embedding: list[float], limit: int
) -> Sequence[Row]:
    """Closest notes by cosine distance. Rows: id, title, content, distance."""
    distance = Note.embedding.cosine_distance(query_embedding).label("distance")
    result = await db.execute(
        select(Note.id, Note.title, Note.content, distance)
        .where(Note.user_id == user_id, Note.embedding.is_not(None))
        .order_by(distance)
        .limit(limit)
    )
    return result.all()


async def keyword_search(
    db: AsyncSession, user_id: int, *, term: str, limit: int
) -> Sequence[Row]:
    """Case-insensitive substring match on title or content.

    Title matches come first, then newest notes. Rows: id, title, content.
    """
    pattern = f"%{_escape_like(term)}%"
    title_match = Note.title.ilike(pattern, escape="\\")
    content_match = Note.content.ilike(pattern, escape="\\")
    result = await db.execute(
        select(Note.id, Note.title, Note.content)
        .where(Note.user_id == user_id, or_(title_match, content_match))
        .order_by(title_match.desc(), Note.created_at.desc(), Note.id.desc())
        .limit(limit)
    )
    return result.all()