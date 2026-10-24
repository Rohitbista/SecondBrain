from datetime import datetime

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from secondbrain.app.routes.auth import DB, CurrentUser
from secondbrain.service import notes_service

router = APIRouter(prefix="/notes", tags=["notes"])


# ---------- schemas ----------
def _strip_non_empty(value: str | None) -> str | None:
    if value is None:
        return value
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value


class NoteCreate(BaseModel):
    title: str = Field(max_length=255)
    content: str

    _clean = field_validator("title", "content")(_strip_non_empty)


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    content: str | None = None

    _clean = field_validator("title", "content")(_strip_non_empty)


class NoteOut(BaseModel):
    """Note as returned to the client. The embedding vector is never exposed."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str
    created_at: datetime
    updated_at: datetime


class NoteList(BaseModel):
    items: list[NoteOut]
    total: int
    limit: int
    offset: int


class TranscriptOut(BaseModel):
    text: str


class ReindexOut(BaseModel):
    reindexed: int


# ---------- routes ----------
@router.post("", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def create_note(payload: NoteCreate, db: DB, user: CurrentUser):
    """Create a note for the logged-in user and embed title + content."""
    return await notes_service.create_note(
        db, user.id, title=payload.title, content=payload.content
    )


@router.get("", response_model=NoteList)
async def list_notes(
    db: DB,
    user: CurrentUser,
    limit: int = Query(20, ge=1, le=notes_service.MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    """List the user's notes, newest first, with the total count for pagination."""
    items, total = await notes_service.list_notes(db, user.id, limit, offset)
    return NoteList(items=items, total=total, limit=limit, offset=offset)


@router.post("/reindex", response_model=ReindexOut)
async def reindex_notes(db: DB, user: CurrentUser):
    """Re-generate embeddings for all of the user's notes (in batches)."""
    count = await notes_service.reindex_notes(db, user.id)
    return ReindexOut(reindexed=count)


@router.post("/voice", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def create_voice_note(
    db: DB,
    user: CurrentUser,
    audio: UploadFile = File(..., description="Audio recording (webm, m4a, mp3, wav, ogg, ...)"),
    title: str | None = Form(None, max_length=255, description="Optional; auto-generated if omitted"),
    language: str | None = Form(None, min_length=2, max_length=5, description="e.g. 'en'; auto-detect if omitted"),
):
    """Transcribe an audio recording and save the transcript as a note."""
    data = await audio.read(notes_service.MAX_AUDIO_BYTES + 1)
    return await notes_service.create_note_from_audio(
        db, user.id, data, audio.filename or "", title=title, language=language
    )


@router.post("/voice/transcribe", response_model=TranscriptOut)
async def transcribe_voice(
    user: CurrentUser,
    audio: UploadFile = File(...),
    language: str | None = Form(None, min_length=2, max_length=5),
):
    """Transcribe only (nothing saved) so the client can review/edit before POST /notes."""
    data = await audio.read(notes_service.MAX_AUDIO_BYTES + 1)
    text = await notes_service.transcribe_audio(data, audio.filename or "", language)
    return TranscriptOut(text=text)


@router.get("/{note_id}", response_model=NoteOut)
async def get_note(note_id: int, db: DB, user: CurrentUser):
    """Get one note. 404 if it doesn't exist or isn't the user's."""
    return await notes_service.get_note(db, user.id, note_id)


@router.patch("/{note_id}", response_model=NoteOut)
async def update_note(note_id: int, payload: NoteUpdate, db: DB, user: CurrentUser):
    """Partial update. Re-embeds only if title or content actually changed."""
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    return await notes_service.update_note(db, user.id, note_id, data)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: int, db: DB, user: CurrentUser):
    """Delete a note. 404 if it isn't the user's. Returns 204 with no body."""
    await notes_service.delete_note(db, user.id, note_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)