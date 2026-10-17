"""Thin async wrapper around Groq's chat API (openai/gpt-oss-120b by default).

Install with: pip install groq

All failures are converted to `LLMError` so the service layer doesn't need to
know about the SDK's exception types.
"""
import logging
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any

import groq
from groq import AsyncGroq

from secondbrain.config.settings import settings

logger = logging.getLogger(__name__)

MAX_COMPLETION_TOKENS = 1024
TEMPERATURE = 0.2  # low: we want answers grounded in the notes, not creative ones


class LLMError(Exception):
    def __init__(self, message: str, *, rate_limited: bool = False):
        super().__init__(message)
        self.message = message
        self.rate_limited = rate_limited


@lru_cache(maxsize=1)
def _client() -> AsyncGroq:
    return AsyncGroq(api_key=settings.groq_api_key, timeout=60.0, max_retries=2)


def _params(messages: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "model": settings.groq_model,
        "messages": messages,
        "temperature": TEMPERATURE,
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
        # gpt-oss is a reasoning model; "low" keeps answers fast and cheap on the
        # free tier. Passed via extra_body so older SDK versions accept it too.
        "extra_body": {"reasoning_effort": "low"},
    }


def _convert(exc: groq.APIError) -> LLMError:
    if isinstance(exc, groq.RateLimitError):
        return LLMError("The AI model is rate-limited right now.", rate_limited=True)
    logger.exception("Groq request failed")
    return LLMError("The AI model is unavailable right now.")


async def complete(messages: list[dict[str, str]]) -> str:
    """Return the full answer text."""
    try:
        response = await _client().chat.completions.create(**_params(messages))
    except groq.APIError as exc:
        raise _convert(exc) from exc

    text = (response.choices[0].message.content or "").strip()
    if not text:
        raise LLMError("The AI model returned an empty answer.")
    return text


async def stream(messages: list[dict[str, str]]) -> AsyncIterator[str]:
    """Yield the answer text chunk by chunk (reasoning tokens are skipped)."""
    produced = False
    try:
        response = await _client().chat.completions.create(**_params(messages), stream=True)
        async for chunk in response:
            if not chunk.choices:
                continue
            piece = chunk.choices[0].delta.content
            if piece:
                produced = True
                yield piece
    except groq.APIError as exc:
        raise _convert(exc) from exc

    if not produced:
        raise LLMError("The AI model returned an empty answer.")