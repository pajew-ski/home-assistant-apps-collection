"""Pydantic models for API request/response schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────

class SearchMode(str, Enum):
    fulltext = "fulltext"
    semantic = "semantic"
    hybrid = "hybrid"
    graph = "graph"


class MatchSource(str, Enum):
    fulltext = "fulltext"
    semantic = "semantic"
    both = "both"


class SortField(str, Enum):
    relevance = "relevance"
    modified = "modified"
    created = "created"
    confidence = "confidence"
    title = "title"


class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


class SyncDirection(str, Enum):
    pull = "pull"
    push = "push"
    both = "both"


class SyncState(str, Enum):
    idle = "idle"
    syncing = "syncing"
    conflict = "conflict"
    error = "error"


class ReindexEngine(str, Enum):
    all = "all"
    meilisearch = "meilisearch"
    qdrant = "qdrant"
    oxigraph = "oxigraph"


class ReindexState(str, Enum):
    running = "running"
    completed = "completed"
    failed = "failed"


class TimelineGranularity(str, Enum):
    day = "day"
    week = "week"
    month = "month"


# ── Search ───────────────────────────────────────────────────────────

class SearchResult(BaseModel):
    path: str
    title: str
    snippet: str = ""
    tags: list[str] = []
    folder: str = ""
    confidence: int = 0
    modified: datetime | None = None
    score: float = 0.0
    match_source: MatchSource = MatchSource.fulltext


class SearchResponse(BaseModel):
    total_hits: int
    processing_time_ms: int
    mode_used: str
    results: list[SearchResult]


# ── Notes ────────────────────────────────────────────────────────────

class BacklinkItem(BaseModel):
    path: str
    title: str
    context: str = ""


class LinkItem(BaseModel):
    path: str
    title: str
    exists: bool = True


class SimilarItem(BaseModel):
    path: str
    title: str
    similarity: float


class CommitItem(BaseModel):
    sha: str
    message: str
    date: datetime | None = None
    diff_summary: str = ""
    author: str = ""
    additions: int = 0
    deletions: int = 0


class NoteResponse(BaseModel):
    path: str
    title: str
    body: str
    frontmatter: dict[str, Any] = {}
    backlinks: list[BacklinkItem] = []
    outgoing_links: list[LinkItem] = []
    similar: list[SimilarItem] = []
    history: list[CommitItem] = []
    word_count: int = 0
    reading_time_minutes: int = 0


class NoteCreateRequest(BaseModel):
    path: str
    title: str
    body: str = ""
    tags: list[str] = []
    confidence: int = 1
    template: str | None = None


class NoteUpdateRequest(BaseModel):
    content: str
    commit_message: str | None = None


class NoteSaveResponse(BaseModel):
    path: str
    sha: str = ""
    indexed: bool = False


class NoteDeleteResponse(BaseModel):
    deleted: bool
    sha: str = ""


# ── Graph ────────────────────────────────────────────────────────────

class GraphNode(BaseModel):
    id: str
    title: str
    tags: list[str] = []
    confidence: int = 0
    backlinks_count: int = 0
    folder: str = ""


class GraphEdge(BaseModel):
    source: str
    target: str
    type: str = "wikilink"


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    clusters: list[dict[str, Any]] = []


class OrphanItem(BaseModel):
    path: str
    title: str
    tags: list[str] = []


class GraphStats(BaseModel):
    total_nodes: int
    total_edges: int
    avg_connections: float
    most_connected: list[dict[str, Any]] = []
    tag_distribution: dict[str, int] = {}
    folder_distribution: dict[str, int] = {}


# ── Timeline ─────────────────────────────────────────────────────────

class TimelineEvent(BaseModel):
    date: datetime
    notes_modified: list[dict[str, Any]]


class TimelineResponse(BaseModel):
    events: list[TimelineEvent]
    stats: dict[str, Any] = {}


# ── Sync ─────────────────────────────────────────────────────────────

class SyncStatusResponse(BaseModel):
    local_sha: str = ""
    remote_sha: str = ""
    pending_changes: list[str] = []
    last_sync: datetime | None = None
    sync_state: SyncState = SyncState.idle
    auto_sync_enabled: bool = True


class SyncResult(BaseModel):
    status: str
    sha: str = ""
    files_changed: list[str] = []
    conflicts: list[str] = []
    pushed_commits: int = 0


# ── Reindex ──────────────────────────────────────────────────────────

class ReindexStartResponse(BaseModel):
    status: str = "started"
    task_id: str


class ReindexStatusResponse(BaseModel):
    state: ReindexState
    progress: float = 0.0
    documents_processed: int = 0
    errors: list[str] = []


# ── Agent Memory ─────────────────────────────────────────────────────

class FactCreateRequest(BaseModel):
    fact: str
    confidence: float = 0.8
    source: str = ""
    tags: list[str] = []
    ttl_days: int | None = None


class FactItem(BaseModel):
    fact: str
    confidence: float
    source: str = ""
    created: datetime | None = None
    tags: list[str] = []


class ConversationMessage(BaseModel):
    role: str
    content: str
    metadata: dict[str, Any] = {}
    timestamp: datetime | None = None


class WorkingMemory(BaseModel):
    current_task: str = ""
    context_notes: list[str] = []
    intermediate_results: dict[str, Any] = {}


# ── System ───────────────────────────────────────────────────────────

class ServiceHealth(BaseModel):
    status: str
    details: dict[str, Any] = {}


class HealthResponse(BaseModel):
    status: str
    services: dict[str, ServiceHealth]
    uptime_seconds: int = 0


class StatsResponse(BaseModel):
    total_notes: int = 0
    total_tags: int = 0
    total_wikilinks: int = 0
    total_backlinks: int = 0
    total_words: int = 0
    orphan_count: int = 0
    avg_confidence: float = 0.0
    notes_by_folder: dict[str, int] = {}
    notes_by_tag: dict[str, int] = {}
    recent_activity: list[dict[str, Any]] = []


# ── Templates ────────────────────────────────────────────────────────

class TemplateItem(BaseModel):
    name: str
    description: str = ""
    frontmatter_defaults: dict[str, Any] = {}


class TemplateContent(BaseModel):
    content: str
