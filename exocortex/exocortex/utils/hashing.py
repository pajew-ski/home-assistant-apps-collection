"""Deterministic path hashing for stable IDs across reindexes."""

from __future__ import annotations

import hashlib


def path_hash(path: str) -> str:
    """Generate a deterministic hash for a file path, usable as a Qdrant point ID."""
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]


def path_hash_int(path: str) -> int:
    """Generate a deterministic integer hash for Qdrant (requires unsigned 64-bit)."""
    h = hashlib.sha256(path.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") & 0x7FFFFFFFFFFFFFFF


def text_hash(text: str) -> str:
    """Hash text content for embedding cache keys."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
