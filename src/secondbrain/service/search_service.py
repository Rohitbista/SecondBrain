"""Business logic for search. Read-only, so no commits happen here.

`retrieve` is also used by the chat (RAG) service to fetch context notes.
"""
import asyncio
import re
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from secondbrain.database import search_db
from secondbrain.utils.embeddings import embed_query

SEMANTIC_MAX_LIMIT = 20
KEYWORD_MAX_LIMIT = 100
SNIPPET_LENGTH = 200


@dataclass(frozen=True)
class ScoredNote:
    id: int
    title: str
    content: str
    score: float  # cosine similarity, 1 - distance (higher = closer)


def _clean_query(q: str) -> str:
    q = q.strip()
    if not q:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Query must not be blank")
    return q


def make_snippet(content: str, term: str | None = None) -> str:
    """Short single-line preview. If `term` occurs, centre the snippet on it."""
    text = re.sub(r"\s+", " ", content).strip()
    if len(text) <= SNIPPET_LENGTH:
        return text

    start = 0
    if term:
        idx = text.lower().find(term.lower())
        if idx > 60:
            start = idx - 60
    end = start + SNIPPET_LENGTH

    snippet = text[start:end].strip()
    return ("…" if start > 0 else "") + snippet + ("…" if end < len(text) else "")


async def retrieve(
    db: AsyncSession, user_id: int, query: str, k: int
) -> list[ScoredNote]:
    """Embed the query (bge query prefix) and return the user's k closest notes."""
    embedding = await asyncio.to_thread(embed_query, query)
    rows = await search_db.semantic_search(
        db, user_id, query_embedding=embedding, limit=k
    )
    return [
        ScoredNote(r.id, r.title, r.content, round(1 - float(r.distance), 4))
        for r in rows
    ]


async def semantic_search(
    db: AsyncSession, user_id: int, q: str, limit: int
) -> list[dict[str, Any]]:
    q = _clean_query(q)
    limit = max(1, min(limit, SEMANTIC_MAX_LIMIT))
    notes = await retrieve(db, user_id, q, limit)
    return [
        {"id": n.id, "title": n.title, "snippet": make_snippet(n.content), "score": n.score}
        for n in notes
    ]


async def keyword_search(
    db: AsyncSession, user_id: int, q: str, limit: int
) -> list[dict[str, Any]]:
    q = _clean_query(q)
    limit = max(1, min(limit, KEYWORD_MAX_LIMIT))
    rows = await search_db.keyword_search(db, user_id, term=q, limit=limit)
    return [
        {"id": r.id, "title": r.title, "snippet": make_snippet(r.content, q)}
        for r in rows
    ]