"""Text-to-speech via gTTS (free, no API key, uses Google Translate's TTS endpoint).

Keep this module's interface (`synthesize`) stable so the engine can be swapped
later (e.g. Groq/OpenAI/ElevenLabs) without touching the service layer.
"""
import asyncio
import io
import logging
import re

from gtts import gTTS

logger = logging.getLogger(__name__)

MAX_TTS_CHARS = 1500
_CITATION_RE = re.compile(r"\[\d+\]")
_MARKDOWN_RE = re.compile(r"[*_`#>]+")


class TTSError(Exception):
    pass


def clean_for_speech(text: str) -> str:
    """Remove things that sound bad when read aloud: [12] citations, markdown symbols."""
    text = _CITATION_RE.sub("", text)
    text = _MARKDOWN_RE.sub("", text)
    return " ".join(text.split())


def _synthesize_sync(text: str, lang: str) -> bytes:
    buf = io.BytesIO()
    gTTS(text=text, lang=lang).write_to_fp(buf)
    return buf.getvalue()


async def synthesize(text: str, language: str = "en") -> bytes:
    """Return MP3 bytes for `text`. Raises TTSError on any failure."""
    text = clean_for_speech(text)[:MAX_TTS_CHARS]
    if not text:
        raise TTSError("Nothing to speak")
    try:
        return await asyncio.to_thread(_synthesize_sync, text, language)
    except Exception as exc:  # gTTS raises gTTSError, AssertionError (bad lang), requests errors...
        logger.warning("gTTS failed: %s", exc)
        raise TTSError("Text-to-speech failed") from exc