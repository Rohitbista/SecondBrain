from datetime import datetime

from fastapi import APIRouter, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from secondbrain.app.routes.auth import DB, CurrentUser
from secondbrain.service import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


# ---------- schemas ----------
class AskIn(BaseModel):
    question: str = Field(max_length=2000)
    session_id: int | None = Field(
        default=None,
        description="Continue an existing chat session. Omit to start a new one.",
    )

    @field_validator("question")
    @classmethod
    def _clean_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class SourceOut(BaseModel):
    id: int
    title: str
    score: float


class AskOut(BaseModel):
    answer: str
    sources: list[SourceOut]
    session_id: int


class ChatSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class ChatSessionList(BaseModel):
    items: list[ChatSessionOut]
    total: int
    limit: int
    offset: int


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    sources: list[SourceOut] | None = None
    created_at: datetime


class ChatSessionDetail(ChatSessionOut):
    messages: list[ChatMessageOut]


# ---------- routes ----------
@router.post("/ask", response_model=AskOut)
async def ask(payload: AskIn, db: DB, user: CurrentUser):
    """Ask the second-brain bot a question (RAG over the user's own notes).

    Answers only from the user's notes and says so when they don't contain
    the answer. `sources` lists the notes the answer actually cites.
    """
    return await chat_service.ask(db, user.id, payload.question, payload.session_id)


@router.post("/ask/stream")
async def ask_stream(payload: AskIn, db: DB, user: CurrentUser):
    """Same as /ask but streamed as server-sent events.

    Events: `token` ({"text"}) many times, then `sources` ({"sources"}),
    then `done` ({"session_id"}). On failure an `error` event is sent instead.
    """
    prep = await chat_service.prepare_stream(
        db, user.id, payload.question, payload.session_id
    )
    return StreamingResponse(
        chat_service.stream_events(prep),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # stop nginx from buffering the stream
        },
    )


# --- conversation history ---
@router.get("/history", response_model=ChatSessionList)
async def list_history(
    db: DB,
    user: CurrentUser,
    limit: int = Query(20, ge=1, le=chat_service.MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    """List the user's chat sessions, most recently active first."""
    items, total = await chat_service.list_history(db, user.id, limit, offset)
    return ChatSessionList(items=items, total=total, limit=limit, offset=offset)


@router.get("/history/{session_id}", response_model=ChatSessionDetail)
async def get_history_session(session_id: int, db: DB, user: CurrentUser):
    """One session with all its messages. 404 if it isn't the user's."""
    session, messages = await chat_service.get_history_session(db, user.id, session_id)
    return ChatSessionDetail(
        **ChatSessionOut.model_validate(session).model_dump(),
        messages=[ChatMessageOut.model_validate(m) for m in messages],
    )


@router.delete("/history/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_history_session(session_id: int, db: DB, user: CurrentUser):
    """Delete one chat session. 404 if it isn't the user's."""
    await chat_service.delete_history_session(db, user.id, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/history", status_code=status.HTTP_204_NO_CONTENT)
async def clear_history(db: DB, user: CurrentUser):
    """Delete all of the user's saved chat history."""
    await chat_service.clear_history(db, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)