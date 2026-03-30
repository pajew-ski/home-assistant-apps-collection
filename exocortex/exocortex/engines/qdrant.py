"""Qdrant client wrapper for semantic vector search."""

from __future__ import annotations

import logging
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    Range,
    VectorParams,
)

from exocortex.core.markdown_parser import ParsedNote
from exocortex.utils.hashing import path_hash_int

logger = logging.getLogger(__name__)

COLLECTION_NAME = "notes"
VECTOR_SIZE = 384  # all-MiniLM-L6-v2


class QdrantEngine:
    """Qdrant client for semantic vector search."""

    def __init__(self, url: str = "http://127.0.0.1:6333", enabled: bool = True):
        self.enabled = enabled
        self.url = url
        self._client: QdrantClient | None = None

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(url=self.url)
        return self._client

    async def ensure_collection(self):
        """Create collection if it doesn't exist."""
        if not self.enabled:
            return

        try:
            self.client.get_collection(COLLECTION_NAME)
        except Exception:
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=VECTOR_SIZE,
                    distance=Distance.COSINE,
                ),
                on_disk_payload=True,
            )
            logger.info("Qdrant collection '%s' created", COLLECTION_NAME)

    async def upsert(self, path: str, embedding: list[float], note: ParsedNote):
        """Add or update a point in Qdrant."""
        if not self.enabled:
            return

        folder = str(path).rsplit("/", 1)[0] if "/" in str(path) else ""

        payload: dict[str, Any] = {
            "path": path,
            "title": note.title,
            "tags": note.tags,
            "folder": folder,
            "confidence": note.confidence,
        }

        if note.modified:
            payload["modified"] = str(note.modified)

        point = PointStruct(
            id=path_hash_int(path),
            vector=embedding,
            payload=payload,
        )

        self.client.upsert(
            collection_name=COLLECTION_NAME,
            points=[point],
        )

    async def upsert_batch(self, points: list[PointStruct]):
        """Batch upsert points."""
        if not self.enabled or not points:
            return
        self.client.upsert(collection_name=COLLECTION_NAME, points=points)

    async def delete(self, path: str):
        """Delete a point from Qdrant."""
        if not self.enabled:
            return
        self.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=[path_hash_int(path)],
        )

    async def search(
        self,
        embedding: list[float],
        filters: dict[str, Any] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search by vector similarity."""
        if not self.enabled:
            return []

        # Build Qdrant filter
        conditions = []
        if filters:
            if filters.get("tags"):
                for tag in filters["tags"]:
                    conditions.append(FieldCondition(key="tags", match=MatchValue(value=tag)))
            if filters.get("folder"):
                conditions.append(FieldCondition(key="folder", match=MatchValue(value=filters["folder"])))
            if filters.get("confidence_min") is not None:
                conditions.append(FieldCondition(key="confidence", range=Range(gte=filters["confidence_min"])))

        query_filter = Filter(must=conditions) if conditions else None

        results = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=embedding,
            query_filter=query_filter,
            limit=limit,
        )

        return [
            {
                "path": point.payload.get("path", ""),
                "title": point.payload.get("title", ""),
                "tags": point.payload.get("tags", []),
                "folder": point.payload.get("folder", ""),
                "confidence": point.payload.get("confidence", 0),
                "modified": point.payload.get("modified"),
                "score": point.score,
            }
            for point in results.points
        ]

    async def find_similar(self, path: str, limit: int = 5) -> list[dict[str, Any]]:
        """Find notes similar to a given note by its stored vector."""
        if not self.enabled:
            return []

        try:
            points = self.client.retrieve(
                collection_name=COLLECTION_NAME,
                ids=[path_hash_int(path)],
                with_vectors=True,
            )
            if not points:
                return []

            vector = points[0].vector
            results = self.client.query_points(
                collection_name=COLLECTION_NAME,
                query=vector,
                limit=limit + 1,  # +1 to exclude self
            )

            return [
                {
                    "path": point.payload.get("path", ""),
                    "title": point.payload.get("title", ""),
                    "similarity": round(point.score, 4),
                }
                for point in results.points
                if point.payload.get("path") != path
            ][:limit]
        except Exception as e:
            logger.debug("find_similar failed for %s: %s", path, e)
            return []

    async def get_stats(self) -> dict[str, Any]:
        """Get collection statistics."""
        if not self.enabled:
            return {"status": "disabled"}
        try:
            info = self.client.get_collection(COLLECTION_NAME)
            return {
                "status": "ok",
                "points": info.points_count,
                "collection_size_mb": 0,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def drop_collection(self):
        """Delete all points."""
        if not self.enabled:
            return
        try:
            self.client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass

    async def health_check(self) -> bool:
        if not self.enabled:
            return True
        try:
            self.client.get_collections()
            return True
        except Exception:
            return False
