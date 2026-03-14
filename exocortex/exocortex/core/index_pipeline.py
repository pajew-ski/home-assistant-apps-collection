"""Index pipeline: parse markdown, generate embeddings, route to all engines."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from exocortex.core.embedding import EmbeddingEngine
from exocortex.core.markdown_parser import ParsedNote, parse_note
from exocortex.engines.meilisearch import MeiliSearchEngine
from exocortex.engines.oxigraph import OxigraphEngine
from exocortex.engines.qdrant import QdrantEngine
from exocortex.engines.redis_client import RedisEngine

logger = logging.getLogger(__name__)


@dataclass
class IndexEvent:
    action: str  # "upsert" or "delete"
    path: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ReindexTask:
    task_id: str
    state: str = "running"
    progress: float = 0.0
    documents_processed: int = 0
    total_documents: int = 0
    errors: list[str] = field(default_factory=list)


class IndexPipeline:
    """Central indexing pipeline that routes parsed notes to all search engines."""

    def __init__(
        self,
        repo_path: Path,
        meilisearch: MeiliSearchEngine,
        qdrant: QdrantEngine,
        oxigraph: OxigraphEngine,
        redis: RedisEngine,
        embedding_engine: EmbeddingEngine | None = None,
    ):
        self.repo_path = repo_path
        self.meilisearch = meilisearch
        self.qdrant = qdrant
        self.oxigraph = oxigraph
        self.redis = redis
        self.embedding = embedding_engine
        self._reindex_tasks: dict[str, ReindexTask] = {}

    async def process_event(self, event: IndexEvent):
        """Process a single index event (file change)."""
        if event.action == "delete":
            await self._delete_from_all(event.path)
            await self.redis.publish_note_change("delete", event.path)
            return

        file_path = self.repo_path / event.path
        if not file_path.exists() or not file_path.suffix == ".md":
            return

        try:
            raw = file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error("Failed to read %s: %s", event.path, e)
            return

        note = parse_note(raw, event.path)
        await self._upsert_to_all(event.path, note)
        await self.redis.publish_note_change("upsert", event.path)

    async def _upsert_to_all(self, path: str, note: ParsedNote):
        """Upsert a note to all engines in parallel."""
        tasks = [
            self.meilisearch.upsert(path, note),
            self.oxigraph.upsert(path, note),
        ]

        # Semantic search (Qdrant + embedding)
        if self.embedding and self.qdrant.enabled:
            try:
                embedding = await self.embedding.encode(note.plain_text)
                tasks.append(self.qdrant.upsert(path, embedding, note))
            except Exception as e:
                logger.error("Embedding failed for %s: %s", path, e)

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _delete_from_all(self, path: str):
        """Delete a note from all engines."""
        await asyncio.gather(
            self.meilisearch.delete(path),
            self.qdrant.delete(path),
            self.oxigraph.delete(path),
            return_exceptions=True,
        )

    async def full_reindex(self, engine: str = "all") -> str:
        """Start a full reindex. Returns task_id."""
        task_id = str(uuid.uuid4())[:8]
        task = ReindexTask(task_id=task_id)
        self._reindex_tasks[task_id] = task

        asyncio.create_task(self._run_full_reindex(task, engine))
        return task_id

    async def _run_full_reindex(self, task: ReindexTask, engine: str):
        """Run full reindex in background."""
        try:
            md_files = list(self.repo_path.rglob("*.md"))
            # Filter out hidden files and .conflicts
            md_files = [
                f for f in md_files
                if not any(part.startswith(".") for part in f.relative_to(self.repo_path).parts)
            ]
            task.total_documents = len(md_files)
            logger.info("Full reindex started: %d files, engine=%s", len(md_files), engine)

            # Drop existing data
            if engine in ("all", "meilisearch"):
                await self.meilisearch.drop_index()
                await self.meilisearch.ensure_index()
            if engine in ("all", "qdrant"):
                await self.qdrant.drop_collection()
                await self.qdrant.ensure_collection()
            if engine in ("all", "oxigraph"):
                await self.oxigraph.drop_all()
                await self.oxigraph.ensure_ontology()

            # Parse all files
            notes: list[tuple[str, ParsedNote]] = []
            for f in md_files:
                try:
                    raw = f.read_text(encoding="utf-8")
                    rel_path = str(f.relative_to(self.repo_path))
                    note = parse_note(raw, rel_path)
                    notes.append((rel_path, note))
                except Exception as e:
                    task.errors.append(f"{f}: {e}")

            # Batch embed if semantic search enabled
            embeddings: list[list[float]] | None = None
            if self.embedding and self.qdrant.enabled and engine in ("all", "qdrant"):
                texts = [note.plain_text for _, note in notes]
                try:
                    embeddings = self.embedding.encode_batch(texts, batch_size=64)
                except Exception as e:
                    task.errors.append(f"Embedding batch failed: {e}")
                    embeddings = None

            # Index in batches
            batch_size = 100
            for i in range(0, len(notes), batch_size):
                batch = notes[i:i + batch_size]

                for j, (path, note) in enumerate(batch):
                    try:
                        index_tasks = []
                        if engine in ("all", "meilisearch"):
                            index_tasks.append(self.meilisearch.upsert(path, note))
                        if engine in ("all", "oxigraph"):
                            index_tasks.append(self.oxigraph.upsert(path, note))
                        if engine in ("all", "qdrant") and embeddings and self.qdrant.enabled:
                            emb_idx = i + j
                            if emb_idx < len(embeddings):
                                index_tasks.append(
                                    self.qdrant.upsert(path, embeddings[emb_idx], note)
                                )

                        await asyncio.gather(*index_tasks, return_exceptions=True)
                        task.documents_processed += 1
                        task.progress = task.documents_processed / max(task.total_documents, 1)
                    except Exception as e:
                        task.errors.append(f"{path}: {e}")

            task.state = "completed"
            task.progress = 1.0
            logger.info(
                "Full reindex completed: %d/%d documents, %d errors",
                task.documents_processed, task.total_documents, len(task.errors),
            )

            # Remove reindex flag
            flag = self.repo_path.parent / ".needs_full_reindex"
            if flag.exists():
                flag.unlink()

        except Exception as e:
            task.state = "failed"
            task.errors.append(str(e))
            logger.error("Full reindex failed: %s", e)

    def get_reindex_status(self, task_id: str) -> ReindexTask | None:
        return self._reindex_tasks.get(task_id)
