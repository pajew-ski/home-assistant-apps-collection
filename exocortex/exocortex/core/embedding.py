"""Sentence-Transformer wrapper with caching."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import msgpack
import numpy as np

from exocortex.utils.hashing import text_hash

if TYPE_CHECKING:
    from exocortex.engines.redis_client import RedisEngine

logger = logging.getLogger(__name__)

# Module-level model cache
_model = None
_model_name = None


def get_model(model_name: str = "all-MiniLM-L6-v2", cache_folder: str = "/opt/exocortex/models"):
    """Load or return cached sentence-transformer model."""
    global _model, _model_name
    if _model is not None and _model_name == model_name:
        return _model

    from sentence_transformers import SentenceTransformer
    logger.info("Loading embedding model: %s", model_name)
    _model = SentenceTransformer(model_name, cache_folder=cache_folder)
    _model_name = model_name
    logger.info("Embedding model loaded. Dimension: %d", _model.get_sentence_embedding_dimension())
    return _model


class EmbeddingEngine:
    """Wrapper around sentence-transformers with Redis caching."""

    def __init__(self, model_name: str, cache_folder: str, redis: RedisEngine | None = None):
        self.model_name = model_name
        self.cache_folder = cache_folder
        self.redis = redis
        self._model = None

    @property
    def model(self):
        if self._model is None:
            self._model = get_model(self.model_name, self.cache_folder)
        return self._model

    @property
    def dimension(self) -> int:
        return self.model.get_sentence_embedding_dimension()

    async def encode(self, text: str) -> list[float]:
        """Encode text to embedding vector, using cache if available."""
        if self.redis:
            cache_key = f"cache:embedding:{text_hash(text)}"
            cached = await self.redis.get_raw(cache_key)
            if cached:
                return msgpack.unpackb(cached)

        vector = self.model.encode(text).tolist()

        if self.redis:
            await self.redis.set_raw(
                cache_key,
                msgpack.packb(vector),
                expire=86400 * 7,  # 7 day cache
            )

        return vector

    def encode_batch(self, texts: list[str], batch_size: int = 64) -> list[list[float]]:
        """Encode multiple texts in batch (sync, for reindexing)."""
        embeddings = self.model.encode(texts, batch_size=batch_size, show_progress_bar=False)
        return [emb.tolist() for emb in embeddings]

    async def encode_many(self, texts: list[str], batch_size: int = 64) -> list[list[float]]:
        """Encode multiple texts, using cache where possible."""
        results: list[list[float] | None] = [None] * len(texts)
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        # Check cache
        if self.redis:
            for i, text in enumerate(texts):
                cache_key = f"cache:embedding:{text_hash(text)}"
                cached = await self.redis.get_raw(cache_key)
                if cached:
                    results[i] = msgpack.unpackb(cached)
                else:
                    uncached_indices.append(i)
                    uncached_texts.append(text)
        else:
            uncached_indices = list(range(len(texts)))
            uncached_texts = texts

        # Encode uncached
        if uncached_texts:
            embeddings = self.encode_batch(uncached_texts, batch_size)
            for idx, emb in zip(uncached_indices, embeddings):
                results[idx] = emb
                # Store in cache
                if self.redis:
                    cache_key = f"cache:embedding:{text_hash(uncached_texts[uncached_indices.index(idx)])}"
                    await self.redis.set_raw(cache_key, msgpack.packb(emb), expire=86400 * 7)

        return results  # type: ignore[return-value]
