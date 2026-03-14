"""Hybrid search engine with Reciprocal Rank Fusion (RRF)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from exocortex.core.embedding import EmbeddingEngine
from exocortex.engines.meilisearch import MeiliSearchEngine
from exocortex.engines.qdrant import QdrantEngine
from exocortex.models import MatchSource, SearchMode, SearchResult

logger = logging.getLogger(__name__)


class SearchEngine:
    """Unified search with mode switching and RRF fusion."""

    def __init__(
        self,
        meilisearch: MeiliSearchEngine,
        qdrant: QdrantEngine,
        embedding: EmbeddingEngine | None = None,
    ):
        self.meilisearch = meilisearch
        self.qdrant = qdrant
        self.embedding = embedding

    async def search(
        self,
        query: str,
        mode: SearchMode = SearchMode.hybrid,
        filters: dict[str, Any] | None = None,
        sort: str | None = None,
        sort_order: str = "desc",
        limit: int = 20,
        offset: int = 0,
        alpha: float = 0.5,
    ) -> dict[str, Any]:
        """Execute a search with the specified mode."""
        start = time.monotonic()
        filters = filters or {}

        # Fallback if semantic search not available
        if mode in (SearchMode.semantic, SearchMode.hybrid):
            if not self.embedding or not self.qdrant.enabled:
                mode = SearchMode.fulltext

        if mode == SearchMode.fulltext:
            result = await self._fulltext_search(query, filters, sort, sort_order, limit, offset)
        elif mode == SearchMode.semantic:
            result = await self._semantic_search(query, filters, limit, offset)
        elif mode == SearchMode.hybrid:
            result = await self._hybrid_search(query, filters, limit, offset, alpha)
        elif mode == SearchMode.graph:
            result = await self._fulltext_search(query, filters, sort, sort_order, limit, offset)
        else:
            result = await self._fulltext_search(query, filters, sort, sort_order, limit, offset)

        elapsed_ms = int((time.monotonic() - start) * 1000)

        return {
            "total_hits": result["total_hits"],
            "processing_time_ms": elapsed_ms,
            "mode_used": mode.value,
            "results": result["results"][offset:offset + limit] if mode == SearchMode.hybrid else result["results"],
        }

    async def _fulltext_search(
        self,
        query: str,
        filters: dict[str, Any],
        sort: str | None,
        sort_order: str,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        """Pure lexical search via MeiliSearch."""
        result = await self.meilisearch.search(
            query, filters, sort, sort_order, limit, offset
        )
        return {
            "total_hits": result["total_hits"],
            "results": [
                {
                    "path": hit["path"],
                    "title": hit.get("title", ""),
                    "snippet": hit.get("snippet", ""),
                    "tags": hit.get("tags", []),
                    "folder": hit.get("folder", ""),
                    "confidence": hit.get("confidence", 0),
                    "modified": hit.get("modified"),
                    "score": 1.0,
                    "match_source": "fulltext",
                }
                for hit in result["hits"]
            ],
        }

    async def _semantic_search(
        self,
        query: str,
        filters: dict[str, Any],
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        """Pure semantic search via Qdrant."""
        embedding = await self.embedding.encode(query)
        results = await self.qdrant.search(embedding, filters, limit=limit + offset)

        return {
            "total_hits": len(results),
            "results": [
                {
                    "path": hit["path"],
                    "title": hit.get("title", ""),
                    "snippet": "",
                    "tags": hit.get("tags", []),
                    "folder": hit.get("folder", ""),
                    "confidence": hit.get("confidence", 0),
                    "modified": hit.get("modified"),
                    "score": hit.get("score", 0.0),
                    "match_source": "semantic",
                }
                for hit in results[offset:]
            ],
        }

    async def _hybrid_search(
        self,
        query: str,
        filters: dict[str, Any],
        limit: int,
        offset: int,
        alpha: float = 0.5,
    ) -> dict[str, Any]:
        """Hybrid search with Reciprocal Rank Fusion."""
        fetch_limit = (limit + offset) * 2

        # Parallel query
        embedding = await self.embedding.encode(query)
        lexical_task = self.meilisearch.search(query, filters, limit=fetch_limit)
        semantic_task = self.qdrant.search(embedding, filters, limit=fetch_limit)

        lexical_result, semantic_hits = await asyncio.gather(lexical_task, semantic_task)
        lexical_hits = lexical_result["hits"]

        # RRF fusion
        k = 60
        scores: dict[str, dict[str, Any]] = {}

        lexical_paths = set()
        for rank, hit in enumerate(lexical_hits):
            path = hit["path"]
            lexical_paths.add(path)
            if path not in scores:
                scores[path] = {"doc": hit, "score": 0}
            scores[path]["score"] += (1 - alpha) * (1 / (k + rank + 1))

        semantic_paths = set()
        for rank, hit in enumerate(semantic_hits):
            path = hit["path"]
            semantic_paths.add(path)
            if path not in scores:
                scores[path] = {"doc": hit, "score": 0}
            scores[path]["score"] += alpha * (1 / (k + rank + 1))

        # Sort by fused score
        merged = sorted(scores.values(), key=lambda x: x["score"], reverse=True)

        results = []
        for item in merged:
            doc = item["doc"]
            path = doc["path"]
            in_lexical = path in lexical_paths
            in_semantic = path in semantic_paths

            if in_lexical and in_semantic:
                source = "both"
            elif in_lexical:
                source = "fulltext"
            else:
                source = "semantic"

            results.append({
                "path": path,
                "title": doc.get("title", ""),
                "snippet": doc.get("snippet", ""),
                "tags": doc.get("tags", []),
                "folder": doc.get("folder", ""),
                "confidence": doc.get("confidence", 0),
                "modified": doc.get("modified"),
                "score": round(item["score"], 4),
                "match_source": source,
            })

        total = max(lexical_result.get("total_hits", 0), len(results))
        return {"total_hits": total, "results": results}
