"""System API endpoints: health, stats, reindex, templates."""

from __future__ import annotations

import time

from fastapi import APIRouter, Query

from exocortex.models import (
    HealthResponse,
    ReindexEngine,
    ReindexStartResponse,
    ReindexStatusResponse,
    ServiceHealth,
    StatsResponse,
    TemplateContent,
    TemplateItem,
)
from exocortex.utils.templates import TEMPLATES, render_template

router = APIRouter()

_start_time = time.monotonic()


def _get_state():
    from exocortex.main import app_state
    return app_state


@router.get("/health", response_model=HealthResponse)
async def health():
    """Health check for all services."""
    state = _get_state()

    services = {}

    # Redis
    redis_ok = await state.redis.health_check()
    services["redis"] = ServiceHealth(
        status="ok" if redis_ok else "error",
        details=await state.redis.get_stats() if redis_ok else {},
    )

    # MeiliSearch
    meili_ok = await state.meilisearch.health_check()
    services["meilisearch"] = ServiceHealth(
        status="ok" if meili_ok else "error",
        details=await state.meilisearch.get_stats() if meili_ok else {},
    )

    # Qdrant
    if state.qdrant.enabled:
        qdrant_ok = await state.qdrant.health_check()
        services["qdrant"] = ServiceHealth(
            status="ok" if qdrant_ok else "error",
            details=await state.qdrant.get_stats() if qdrant_ok else {},
        )
    else:
        services["qdrant"] = ServiceHealth(status="disabled")

    # Oxigraph
    oxigraph_ok = await state.oxigraph.health_check()
    services["oxigraph"] = ServiceHealth(
        status="ok" if oxigraph_ok else "error",
        details=await state.oxigraph.get_stats() if oxigraph_ok else {},
    )

    all_ok = all(
        s.status in ("ok", "disabled") for s in services.values()
    )

    return HealthResponse(
        status="ok" if all_ok else "degraded",
        services=services,
        uptime_seconds=int(time.monotonic() - _start_time),
    )


@router.get("/stats", response_model=StatsResponse)
async def stats():
    """Get vault statistics."""
    state = _get_state()

    # Count markdown files
    md_files = list(state.config.repo_path.rglob("*.md"))
    md_files = [
        f for f in md_files
        if not any(part.startswith(".") for part in f.relative_to(state.config.repo_path).parts)
    ]

    # Count by folder
    notes_by_folder: dict[str, int] = {}
    total_words = 0
    tags_set: set[str] = set()
    notes_by_tag: dict[str, int] = {}

    for f in md_files:
        rel = f.relative_to(state.config.repo_path)
        folder = str(rel.parent) if str(rel.parent) != "." else "/"
        notes_by_folder[folder] = notes_by_folder.get(folder, 0) + 1

        try:
            from exocortex.core.markdown_parser import parse_note
            raw = f.read_text(encoding="utf-8")
            note = parse_note(raw, str(rel))
            total_words += note.word_count
            for tag in note.tags:
                tags_set.add(tag)
                notes_by_tag[tag] = notes_by_tag.get(tag, 0) + 1
        except Exception:
            pass

    # Graph stats
    graph_stats = await state.oxigraph.get_stats()
    orphans = await state.oxigraph.get_orphans()

    return StatsResponse(
        total_notes=len(md_files),
        total_tags=len(tags_set),
        total_words=total_words,
        orphan_count=len(orphans),
        notes_by_folder=notes_by_folder,
        notes_by_tag=notes_by_tag,
    )


@router.post("/reindex", response_model=ReindexStartResponse)
async def start_reindex(engine: ReindexEngine = Query(ReindexEngine.all)):
    """Start a full reindex."""
    state = _get_state()
    task_id = await state.pipeline.full_reindex(engine.value)
    return ReindexStartResponse(task_id=task_id)


@router.get("/reindex/{task_id}", response_model=ReindexStatusResponse)
async def get_reindex_status(task_id: str):
    """Get reindex task status."""
    state = _get_state()
    task = state.pipeline.get_reindex_status(task_id)
    if not task:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Task not found")

    return ReindexStatusResponse(
        state=task.state,
        progress=task.progress,
        documents_processed=task.documents_processed,
        errors=task.errors[:20],
    )


@router.get("/templates")
async def list_templates():
    """List available note templates."""
    return {
        "templates": [
            TemplateItem(
                name=name,
                description=tmpl.get("description", ""),
                frontmatter_defaults=tmpl.get("frontmatter_defaults", {}),
            )
            for name, tmpl in TEMPLATES.items()
        ]
    }


@router.post("/templates/{name}/render", response_model=TemplateContent)
async def render_template_endpoint(
    name: str,
    title: str = Query("Untitled"),
    tags: list[str] | None = Query(None),
    confidence: int | None = Query(None),
):
    """Render a template with given parameters."""
    content = render_template(name, title, tags=tags, confidence=confidence)
    return TemplateContent(content=content)
