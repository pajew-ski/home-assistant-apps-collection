"""Notes CRUD API endpoints."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from fastapi import APIRouter, HTTPException

from exocortex.core.index_pipeline import IndexEvent
from exocortex.core.markdown_parser import parse_note
from exocortex.models import (
    BacklinkItem,
    CommitItem,
    LinkItem,
    NoteCreateRequest,
    NoteDeleteResponse,
    NoteResponse,
    NoteSaveResponse,
    NoteUpdateRequest,
    SimilarItem,
)
from exocortex.utils.templates import render_template

router = APIRouter()


def _get_state():
    from exocortex.main import app_state
    return app_state


def _validate_path(path: str) -> str:
    """Validate note path to prevent traversal attacks."""
    normalized = PurePosixPath(path)
    if ".." in normalized.parts:
        raise HTTPException(status_code=400, detail="Path traversal not allowed")
    # Ensure it ends with .md
    path_str = str(normalized)
    if not path_str.endswith(".md"):
        path_str += ".md"
    return path_str


@router.get("/notes/{path:path}", response_model=NoteResponse)
async def get_note(path: str):
    """Get a note with metadata, backlinks, and similar notes."""
    state = _get_state()
    path = _validate_path(path)
    file_path = state.config.repo_path / path

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Note not found: {path}")

    raw = file_path.read_text(encoding="utf-8")
    note = parse_note(raw, path)

    # Backlinks from Oxigraph
    backlinks_raw = await state.oxigraph.get_backlinks(path)
    backlinks = [BacklinkItem(path=b["path"], title=b["title"]) for b in backlinks_raw]

    # Outgoing links
    outgoing = []
    for link in note.wikilinks:
        link_path = link if link.endswith(".md") else f"{link}.md"
        exists = (state.config.repo_path / link_path).exists()
        outgoing.append(LinkItem(path=link_path, title=link, exists=exists))

    # Similar notes from Qdrant
    similar = []
    if state.qdrant.enabled:
        similar_raw = await state.qdrant.find_similar(path, limit=5)
        similar = [SimilarItem(**s) for s in similar_raw]

    # Git history
    history_raw = await state.git.get_file_history(path, limit=10)
    history = [
        CommitItem(
            sha=c["sha"],
            message=c["message"],
            author=c.get("author", ""),
            date=c.get("date"),
            additions=c.get("additions", 0),
            deletions=c.get("deletions", 0),
        )
        for c in history_raw
    ]

    reading_time = max(1, note.word_count // 200)

    return NoteResponse(
        path=path,
        title=note.title,
        body=note.body,
        frontmatter=note.frontmatter,
        backlinks=backlinks,
        outgoing_links=outgoing,
        similar=similar,
        history=history,
        word_count=note.word_count,
        reading_time_minutes=reading_time,
    )


@router.put("/notes/{path:path}", response_model=NoteSaveResponse)
async def update_note(path: str, req: NoteUpdateRequest):
    """Update or create a note."""
    state = _get_state()
    path = _validate_path(path)
    file_path = state.config.repo_path / path

    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Write content
    file_path.write_text(req.content, encoding="utf-8")

    # Git commit
    message = req.commit_message or f"[exocortex] Update {path}"
    sha = await state.git.add_and_commit([path], message)

    # Push if auto_push enabled
    if state.config.auto_push:
        await state.git.push()

    # Index
    await state.pipeline.process_event(IndexEvent(action="upsert", path=path))

    return NoteSaveResponse(path=path, sha=sha, indexed=True)


@router.post("/notes/", response_model=NoteSaveResponse)
async def create_note(req: NoteCreateRequest):
    """Create a new note."""
    state = _get_state()
    path = _validate_path(req.path)
    file_path = state.config.repo_path / path

    if file_path.exists():
        raise HTTPException(status_code=409, detail=f"Note already exists: {path}")

    # Generate content from template
    if req.template:
        content = render_template(
            req.template,
            title=req.title,
            tags=req.tags,
            confidence=req.confidence,
        )
    else:
        content = render_template(
            "default",
            title=req.title,
            tags=req.tags,
            confidence=req.confidence,
        )

    # Append user body if provided
    if req.body:
        content += req.body + "\n"

    # Ensure directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")

    # Git commit
    message = f"[exocortex] Create {path}"
    sha = await state.git.add_and_commit([path], message)

    if state.config.auto_push:
        await state.git.push()

    # Index
    await state.pipeline.process_event(IndexEvent(action="upsert", path=path))

    return NoteSaveResponse(path=path, sha=sha, indexed=True)


@router.delete("/notes/{path:path}", response_model=NoteDeleteResponse)
async def delete_note(path: str):
    """Delete a note."""
    state = _get_state()
    path = _validate_path(path)
    file_path = state.config.repo_path / path

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Note not found: {path}")

    message = f"[exocortex] Delete {path}"
    sha = await state.git.delete_file(path, message)

    if state.config.auto_push:
        await state.git.push()

    # Remove from indices
    await state.pipeline.process_event(IndexEvent(action="delete", path=path))

    return NoteDeleteResponse(deleted=True, sha=sha)


@router.get("/notes/{path:path}/history")
async def get_note_history(path: str):
    """Get full git history of a note."""
    state = _get_state()
    path = _validate_path(path)
    commits = await state.git.get_file_history(path, limit=100)
    return {"commits": commits}


@router.get("/notes/{path:path}/diff/{sha}")
async def get_note_diff(path: str, sha: str):
    """Get diff of a note at a specific commit."""
    state = _get_state()
    path = _validate_path(path)
    diff = await state.git.get_diff(path, sha)
    return {"diff": diff}


@router.get("/notes/{path:path}/version/{sha}")
async def get_note_version(path: str, sha: str):
    """Get note content at a specific revision."""
    state = _get_state()
    path = _validate_path(path)
    content = await state.git.get_file_at_revision(path, sha)
    if not content:
        raise HTTPException(status_code=404, detail="Version not found")

    note = parse_note(content, path)
    return {"content": content, "frontmatter": note.frontmatter}
