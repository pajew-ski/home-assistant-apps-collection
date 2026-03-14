"""MeiliSearch client wrapper for lexical search."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import meilisearch

from exocortex.core.markdown_parser import ParsedNote

logger = logging.getLogger(__name__)

INDEX_UID = "notes"
INDEX_CONFIG = {
    "searchableAttributes": ["title", "body", "tags", "aliases"],
    "filterableAttributes": [
        "tags", "folder", "confidence", "status", "type",
        "modified", "created", "_geo",
    ],
    "sortableAttributes": ["modified", "created", "confidence", "title"],
    "displayedAttributes": [
        "path", "title", "snippet", "tags", "folder", "confidence",
        "status", "modified", "created", "_geo", "backlinks_count", "word_count",
    ],
    "typoTolerance": {
        "enabled": True,
        "minWordSizeForTypos": {"oneTypo": 4, "twoTypos": 8},
    },
    "pagination": {"maxTotalHits": 10000},
}


class MeiliSearchEngine:
    """MeiliSearch client for full-text search."""

    def __init__(self, url: str = "http://127.0.0.1:7700", master_key: str = ""):
        self.client = meilisearch.Client(url, master_key or None)
        self._index = None

    async def ensure_index(self):
        """Create and configure the notes index if it doesn't exist."""
        try:
            self.client.create_index(INDEX_UID, {"primaryKey": "path"})
        except meilisearch.errors.MeilisearchApiError:
            pass  # Already exists

        index = self.client.index(INDEX_UID)
        index.update_settings(INDEX_CONFIG)
        self._index = index
        logger.info("MeiliSearch index '%s' configured", INDEX_UID)

    @property
    def index(self):
        if self._index is None:
            self._index = self.client.index(INDEX_UID)
        return self._index

    def _note_to_document(self, path: str, note: ParsedNote) -> dict[str, Any]:
        """Convert a parsed note to a MeiliSearch document."""
        folder = str(path).rsplit("/", 1)[0] if "/" in str(path) else ""

        doc: dict[str, Any] = {
            "path": path,
            "title": note.title,
            "body": note.plain_text,
            "snippet": note.snippet,
            "tags": note.tags,
            "aliases": note.aliases,
            "folder": folder,
            "confidence": note.confidence,
            "status": note.status,
            "type": note.note_type,
            "word_count": note.word_count,
            "backlinks_count": 0,  # Updated separately
        }

        # Timestamps as Unix epoch
        if note.modified:
            try:
                dt = datetime.fromisoformat(str(note.modified).replace("Z", "+00:00"))
                doc["modified"] = int(dt.timestamp())
            except (ValueError, TypeError):
                pass
        if note.created:
            try:
                dt = datetime.fromisoformat(str(note.created).replace("Z", "+00:00"))
                doc["created"] = int(dt.timestamp())
            except (ValueError, TypeError):
                pass

        # Geo coordinates
        if note.location:
            doc["_geo"] = {"lat": note.location[0], "lng": note.location[1]}

        return doc

    async def upsert(self, path: str, note: ParsedNote):
        """Add or update a document in MeiliSearch."""
        doc = self._note_to_document(path, note)
        self.index.add_documents([doc], primary_key="path")

    async def upsert_batch(self, docs: list[dict[str, Any]]):
        """Batch upsert documents."""
        if docs:
            self.index.add_documents(docs, primary_key="path")

    async def delete(self, path: str):
        """Delete a document from MeiliSearch."""
        self.index.delete_document(path)

    async def search(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        sort: str | None = None,
        sort_order: str = "desc",
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Execute a search query."""
        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "attributesToHighlight": ["title", "body"],
            "highlightPreTag": "<mark>",
            "highlightPostTag": "</mark>",
            "attributesToCrop": ["body"],
            "cropLength": 200,
        }

        # Build filter string
        filter_parts: list[str] = []
        if filters:
            if filters.get("tags"):
                for tag in filters["tags"]:
                    filter_parts.append(f'tags = "{tag}"')
            if filters.get("tags_or"):
                or_parts = [f'tags = "{tag}"' for tag in filters["tags_or"]]
                filter_parts.append(f"({' OR '.join(or_parts)})")
            if filters.get("folder"):
                filter_parts.append(f'folder = "{filters["folder"]}"')
            if filters.get("confidence_min") is not None:
                filter_parts.append(f"confidence >= {filters['confidence_min']}")
            if filters.get("confidence_max") is not None:
                filter_parts.append(f"confidence <= {filters['confidence_max']}")
            if filters.get("status"):
                filter_parts.append(f'status = "{filters["status"]}"')
            if filters.get("type"):
                filter_parts.append(f'type = "{filters["type"]}"')
            if filters.get("date_from"):
                ts = int(datetime.fromisoformat(str(filters["date_from"]).replace("Z", "+00:00")).timestamp())
                filter_parts.append(f"modified >= {ts}")
            if filters.get("date_to"):
                ts = int(datetime.fromisoformat(str(filters["date_to"]).replace("Z", "+00:00")).timestamp())
                filter_parts.append(f"modified <= {ts}")
            if filters.get("geo_lat") is not None and filters.get("geo_lon") is not None:
                radius_m = int((filters.get("geo_radius_km", 10)) * 1000)
                params["filter"] = ""  # geo filter handled separately

        if filter_parts:
            params["filter"] = " AND ".join(filter_parts)

        # Sort
        if sort and sort != "relevance":
            direction = "asc" if sort_order == "asc" else "desc"
            params["sort"] = [f"{sort}:{direction}"]

        result = self.index.search(query, params)

        return {
            "total_hits": result.get("estimatedTotalHits", 0),
            "processing_time_ms": result.get("processingTimeMs", 0),
            "hits": [
                {
                    "path": hit["path"],
                    "title": hit.get("title", ""),
                    "snippet": hit.get("_formatted", {}).get("body", hit.get("snippet", "")),
                    "tags": hit.get("tags", []),
                    "folder": hit.get("folder", ""),
                    "confidence": hit.get("confidence", 0),
                    "modified": hit.get("modified"),
                    "created": hit.get("created"),
                    "word_count": hit.get("word_count", 0),
                }
                for hit in result.get("hits", [])
            ],
        }

    async def get_stats(self) -> dict[str, Any]:
        """Get index statistics."""
        try:
            stats = self.index.get_stats()
            return {
                "status": "ok",
                "documents": stats.get("numberOfDocuments", 0),
                "index_size_mb": 0,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def drop_index(self):
        """Delete all documents from the index."""
        try:
            self.index.delete_all_documents()
        except Exception:
            pass

    async def health_check(self) -> bool:
        try:
            self.client.health()
            return True
        except Exception:
            return False
