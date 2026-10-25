"""Business logic for notes. Owns the transaction (commits happen here)."""
import asyncio
import os
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from secondbrain.database import notes_db
from secondbrain.database.models import Note
from secondbrain.utils import llm
from secondbrain.utils.embeddings import build_note_text, embed_text, embed_texts
from secondbrain.utils.llm import LLMError

MAX_LIMIT = 100
REINDEX_BATCH_SIZE = 50

# Groq's speech-to-text file limit is 25 MB on the free tier.
MAX_AUDIO_BYTES = 25 * 1024 * 1024
ALLOWED_AUDIO_EXTENSIONS = {
    ".flac", ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".ogg", ".opus", ".wav", ".webm",
}
MAX_TITLE_LEN = 255

_TITLE_SYSTEM_PROMPT = (
    "You write short titles for voice notes. Reply with ONLY a title of at most "
    "8 words: no quotes, no trailing punctuation, same language as the note."
)

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


# ---------- voice notes ----------
def _llm_http_error(exc: LLMError) -> HTTPException:
    code = status.HTTP_429_TOO_MANY_REQUESTS if exc.rate_limited else status.HTTP_502_BAD_GATEWAY
    return HTTPException(code, exc.message)


async def transcribe_audio(
    audio_data: bytes, filename: str, language: str | None = None
) -> str:
    """Validate the audio and return its transcript. Raises HTTPException on bad input."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Unsupported audio format. Allowed: {', '.join(sorted(ALLOWED_AUDIO_EXTENSIONS))}",
        )
    if not audio_data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Audio file is empty")
    if len(audio_data) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Audio file too large (max {MAX_AUDIO_BYTES // (1024 * 1024)} MB)",
        )

    try:
        transcript = await llm.transcribe(audio_data, filename, language)
    except LLMError as exc:
        raise _llm_http_error(exc) from exc

    if not transcript:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No speech detected in the audio")
    return transcript


async def _generate_title(transcript: str) -> str:
    """Ask the LLM for a short title; fall back to the first few words."""
    title = ""
    try:
        raw = await llm.complete(
            [
                {"role": "system", "content": _TITLE_SYSTEM_PROMPT},
                {"role": "user", "content": transcript[:2000]},
            ]
        )
        lines = raw.strip().strip('"\'').splitlines()
        title = lines[0].strip() if lines else ""
    except LLMError:
        pass  # title generation is best-effort; never fail the note because of it

    if not title:
        words = transcript.split()
        title = " ".join(words[:8]) + ("…" if len(words) > 8 else "")
    return title[:MAX_TITLE_LEN]


async def create_note_from_audio(
    db: AsyncSession,
    user_id: int,
    audio_data: bytes,
    filename: str,
    title: str | None = None,
    language: str | None = None,
) -> Note:
    """Transcribe audio and save it exactly like a text note (same embed + insert path)."""
    transcript = await transcribe_audio(audio_data, filename, language)
    title = (title or "").strip() or await _generate_title(transcript)
    return await create_note(db, user_id, title=title, content=transcript)