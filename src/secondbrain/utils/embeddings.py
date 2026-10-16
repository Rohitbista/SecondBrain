"""Embedding helper using fastembed (ONNX, no PyTorch).

These functions are synchronous and CPU-heavy. Call them from async code
with `asyncio.to_thread(...)` so the event loop is never blocked.
"""
import os
from functools import lru_cache

# Windows without Developer Mode can't create symlinks; caching still works,
# so silence the (harmless) warning. Must be set before huggingface_hub loads.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from fastembed import TextEmbedding  # noqa: E402

MODEL_NAME = "BAAI/bge-small-en-v1.5"


@lru_cache(maxsize=1)
def _get_model() -> TextEmbedding:
    return TextEmbedding(
        model_name=MODEL_NAME,
        cache_dir="./models",  # keep the download; the default temp dir can be wiped
        threads=2,             # cap CPU use; raise if embedding feels slow
    )


def warmup() -> None:
    """Download (first run only) and load the model, then run one dummy
    embedding so the ONNX session is fully initialised. Call at server startup."""
    embed_text("warmup")


def build_note_text(title: str, content: str) -> str:
    return f"{title}\n\n{content}"


def embed_texts(texts: list[str]) -> list[list[float]]:
    # embed() returns a generator of numpy arrays; the bge vectors are already normalized
    return [v.tolist() for v in _get_model().embed(texts, batch_size=32)]


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]

BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

def embed_query(text: str) -> list[float]:
    return embed_text(BGE_QUERY_PREFIX + text)