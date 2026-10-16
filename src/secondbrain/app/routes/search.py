from fastapi import APIRouter, Query
from pydantic import BaseModel

from secondbrain.app.routes.auth import DB, CurrentUser
from secondbrain.service import search_service

router = APIRouter(prefix="/search", tags=["search"])


# ---------- schemas ----------
class SemanticHit(BaseModel):
    id: int
    title: str
    snippet: str
    score: float  # cosine similarity (1 - distance); higher is more relevant


class KeywordHit(BaseModel):
    id: int
    title: str
    snippet: str


# ---------- routes ----------
@router.get("", response_model=list[SemanticHit])
async def semantic_search(
    db: DB,
    user: CurrentUser,
    q: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(5, ge=1, le=search_service.SEMANTIC_MAX_LIMIT),
):
    """Semantic search over the logged-in user's notes (no LLM involved)."""
    return await search_service.semantic_search(db, user.id, q, limit)


@router.get("/keyword", response_model=list[KeywordHit])
async def keyword_search(
    db: DB,
    user: CurrentUser,
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(20, ge=1, le=search_service.KEYWORD_MAX_LIMIT),
):
    """Plain text search on title/content. Good for exact words or names."""
    return await search_service.keyword_search(db, user.id, q, limit)