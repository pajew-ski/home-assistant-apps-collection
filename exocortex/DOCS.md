# Exocortex – Knowledge Operating System

Exocortex is a complete knowledge management system that runs as a Home Assistant add-on.
It turns a Git-backed folder of Markdown files into a searchable, interlinked
knowledge graph with AI-powered semantic search and agent memory.

## Features

- **Hybrid Search** — Full-text (MeiliSearch) + semantic vector search (Qdrant) + SPARQL graph queries (Oxigraph), fused with Reciprocal Rank Fusion
- **Bidirectional Git Sync** — Automatic pull/push with conflict detection; works with GitHub, GitLab, or any Git remote
- **Knowledge Graph** — Every `[[wikilink]]`, tag, and metadata field becomes a SPARQL-queryable triple
- **AI Agent Memory** — Structured fact storage, conversation history, and working memory for LLM agents
- **MCP Server** — Model Context Protocol interface so Claude, GPT, or any MCP-compatible agent can search, read, and write notes
- **File Watcher** — Real-time indexing of changes via filesystem events
- **Templates** — Pre-built note templates (default, project, person, log, review)

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `github_repo` | *(required)* | Repository URL (e.g. `https://github.com/you/vault`) |
| `github_token` | *(required)* | Personal access token with repo scope |
| `github_branch` | `main` | Branch to sync |
| `sync_interval_minutes` | `5` | How often to pull/push (1–60) |
| `webhook_secret` | *(empty)* | GitHub webhook secret for push-triggered sync |
| `embedding_model` | `all-MiniLM-L6-v2` | Sentence-transformer model name |
| `meilisearch_master_key` | *(required)* | MeiliSearch API key |
| `redis_password` | *(empty)* | Redis password |
| `auto_push` | `true` | Automatically push after edits |
| `auto_create_on_conflict` | `true` | Create conflict copies instead of failing |
| `enable_semantic_search` | `true` | Enable Qdrant vector search |
| `log_level` | `info` | Logging level |

## Architecture

Exocortex runs six services inside a single container, managed by s6-overlay:

```
┌────────────────────────────────────────────────────────┐
│  nginx (port 8080 → ingress)                           │
│    ↓                                                   │
│  FastAPI (port 8000) ← Sync Daemon (file watcher)      │
│    ↓           ↓           ↓           ↓               │
│  Redis      MeiliSearch   Qdrant     Oxigraph           │
│  (6379)     (7700)        (6333)     (7878)             │
└────────────────────────────────────────────────────────┘
```

## API Endpoints

### Search
- `GET /api/search?q=...&mode=hybrid` — Unified search

### Notes
- `GET /api/notes/{path}` — Read note with backlinks and similar notes
- `PUT /api/notes/{path}` — Update or create a note
- `POST /api/notes/` — Create from template
- `DELETE /api/notes/{path}` — Delete a note

### Graph
- `GET /api/graph/full` — Full knowledge graph
- `GET /api/graph/neighbors/{path}` — Local subgraph
- `GET /api/graph/backlinks/{path}` — Backlinks
- `GET /api/graph/orphans` — Unlinked notes
- `GET /api/graph/stats` — Graph statistics

### Sync
- `GET /api/sync/status` — Current sync status
- `POST /api/sync/pull` — Pull from remote
- `POST /api/sync/push` — Push to remote
- `POST /api/sync/webhook` — GitHub webhook receiver

### Agent Memory
- `POST /api/agent/{id}/facts` — Store a fact
- `GET /api/agent/{id}/facts` — Recall facts
- `POST /api/agent/{id}/conversations` — Append to conversation
- `GET /api/agent/{id}/conversations` — Get conversation history
- `PUT /api/agent/{id}/working/{session}` — Set working memory

### System
- `GET /api/health` — Health check
- `GET /api/stats` — Vault statistics
- `POST /api/reindex` — Trigger full reindex
- `GET /api/templates` — List note templates

## MCP Integration

Exocortex ships an MCP server that AI agents can connect to. The server exposes
these tools: `search_notes`, `read_note`, `create_note`, `update_note`,
`get_backlinks`, `store_fact`, `recall_facts`, `sparql_query`, `vault_stats`.

## Markdown Format

Notes use standard Markdown with YAML frontmatter:

```markdown
---
title: Example Note
tags: [ai, knowledge]
confidence: 3
status: active
type: note
created: 2025-01-01T00:00:00Z
---

# Example Note

This note links to [[another-note]] and [[projects/my-project]].
```

### Frontmatter Fields

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Note title (falls back to H1 or filename) |
| `tags` | list | Tags for filtering and graph |
| `confidence` | int (1-5) | How confident/verified the information is |
| `status` | string | draft, active, archived, etc. |
| `type` | string | note, project, person, log, review |
| `aliases` | list | Alternative names for backlink resolution |
| `location` | [lat, lon] | Geo coordinates for spatial queries |
| `links` | list | Explicit link targets (in addition to wikilinks) |

## Supported Architectures

- `amd64` (x86_64)
- `aarch64` (ARM64 / Raspberry Pi 4+)
