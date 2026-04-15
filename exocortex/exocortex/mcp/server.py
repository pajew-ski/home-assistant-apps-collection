"""MCP (Model Context Protocol) server for AI agent integration."""

from __future__ import annotations

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

EXOCORTEX_API = "http://127.0.0.1:8000/api"

server = Server("exocortex-mcp")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=EXOCORTEX_API, timeout=30.0)


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_notes",
            description="Search the knowledge base using fulltext, semantic, or hybrid search",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "mode": {"type": "string", "enum": ["fulltext", "semantic", "hybrid"], "default": "hybrid"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Filter by tags"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="read_note",
            description="Read the full content of a note by path",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Note path (e.g. 'projects/my-project.md')"},
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="create_note",
            description="Create a new note in the knowledge base",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Note path"},
                    "title": {"type": "string", "description": "Note title"},
                    "body": {"type": "string", "description": "Markdown content"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "integer", "minimum": 1, "maximum": 5, "default": 1},
                    "template": {"type": "string", "description": "Template name (default, project, person, log, review)"},
                },
                "required": ["path", "title"],
            },
        ),
        Tool(
            name="update_note",
            description="Update an existing note's content",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string", "description": "Full markdown content including frontmatter"},
                    "commit_message": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        ),
        Tool(
            name="get_backlinks",
            description="Find all notes that link to a given note",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="store_fact",
            description="Store a fact in agent memory for later retrieval",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "Agent identifier"},
                    "fact": {"type": "string", "description": "The fact to remember"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.8},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["agent_id", "fact"],
            },
        ),
        Tool(
            name="recall_facts",
            description="Retrieve stored facts from agent memory",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string"},
                    "min_confidence": {"type": "number", "default": 0.0},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["agent_id"],
            },
        ),
        Tool(
            name="sparql_query",
            description="Execute a SPARQL query against the knowledge graph",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "SPARQL SELECT query"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="vault_stats",
            description="Get statistics about the knowledge base",
            inputSchema={"type": "object", "properties": {}},
        ),
        # ── Agent tools ──────────────────────────────────────────────
        Tool(
            name="get_ha_state",
            description="Query current Home Assistant entity state from Redis hot cache",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "Entity ID (e.g. 'light.living_room')"},
                },
                "required": ["entity_id"],
            },
        ),
        Tool(
            name="search_ha_events",
            description="Semantic search over recent Home Assistant events",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language search query"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_agent_decisions",
            description="Query recent agent decisions from the knowledge graph",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 20},
                },
            },
        ),
        Tool(
            name="trigger_agent",
            description="Manually trigger the agent system for a specific entity",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string"},
                    "new_state": {"type": "string"},
                    "old_state": {"type": "string", "default": ""},
                },
                "required": ["entity_id", "new_state"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    async with _client() as client:
        try:
            if name == "search_notes":
                params = {"q": arguments["query"], "mode": arguments.get("mode", "hybrid"), "limit": arguments.get("limit", 10)}
                if arguments.get("tags"):
                    params["tags"] = arguments["tags"]
                resp = await client.get("/search", params=params)
                resp.raise_for_status()
                data = resp.json()
                lines = [f"Found {data['total_hits']} results (mode: {data['mode_used']}):\n"]
                for r in data.get("results", []):
                    lines.append(f"- **{r['title']}** ({r['path']})")
                    if r.get("snippet"):
                        lines.append(f"  {r['snippet'][:200]}")
                    if r.get("tags"):
                        lines.append(f"  Tags: {', '.join(r['tags'])}")
                return [TextContent(type="text", text="\n".join(lines))]

            elif name == "read_note":
                resp = await client.get(f"/notes/{arguments['path']}")
                resp.raise_for_status()
                data = resp.json()
                parts = [f"# {data['title']}\n", f"Path: {data['path']}"]
                if data.get("frontmatter"):
                    parts.append(f"Frontmatter: {data['frontmatter']}")
                if data.get("backlinks"):
                    parts.append(f"Backlinks: {', '.join(b['title'] for b in data['backlinks'])}")
                parts.append(f"\n{data['body']}")
                return [TextContent(type="text", text="\n".join(parts))]

            elif name == "create_note":
                resp = await client.post("/notes/", json=arguments)
                resp.raise_for_status()
                data = resp.json()
                return [TextContent(type="text", text=f"Created note: {data['path']} (sha: {data['sha']})")]

            elif name == "update_note":
                path = arguments.pop("path")
                resp = await client.put(f"/notes/{path}", json=arguments)
                resp.raise_for_status()
                data = resp.json()
                return [TextContent(type="text", text=f"Updated note: {data['path']} (sha: {data['sha']})")]

            elif name == "get_backlinks":
                resp = await client.get(f"/graph/backlinks/{arguments['path']}")
                resp.raise_for_status()
                data = resp.json()
                backlinks = data.get("backlinks", [])
                if not backlinks:
                    return [TextContent(type="text", text="No backlinks found.")]
                lines = [f"Backlinks to {arguments['path']}:"]
                for b in backlinks:
                    lines.append(f"- {b['title']} ({b['path']})")
                return [TextContent(type="text", text="\n".join(lines))]

            elif name == "store_fact":
                resp = await client.post(f"/agent/{arguments['agent_id']}/facts", json={
                    "fact": arguments["fact"],
                    "confidence": arguments.get("confidence", 0.8),
                    "tags": arguments.get("tags", []),
                })
                resp.raise_for_status()
                return [TextContent(type="text", text="Fact stored successfully.")]

            elif name == "recall_facts":
                params = {
                    "limit": arguments.get("limit", 10),
                    "min_confidence": arguments.get("min_confidence", 0.0),
                }
                if arguments.get("tags"):
                    params["tags"] = arguments["tags"]
                resp = await client.get(f"/agent/{arguments['agent_id']}/facts", params=params)
                resp.raise_for_status()
                data = resp.json()
                facts = data.get("facts", [])
                if not facts:
                    return [TextContent(type="text", text="No facts found.")]
                lines = ["Recalled facts:"]
                for f in facts:
                    lines.append(f"- [{f['confidence']:.0%}] {f['fact']}")
                return [TextContent(type="text", text="\n".join(lines))]

            elif name == "sparql_query":
                resp = await client.post("/graph/sparql", json={"query": arguments["query"]})
                resp.raise_for_status()
                return [TextContent(type="text", text=str(resp.json()))]

            elif name == "vault_stats":
                resp = await client.get("/stats")
                resp.raise_for_status()
                data = resp.json()
                lines = [
                    "Knowledge Base Statistics:",
                    f"- Total notes: {data.get('total_notes', 0)}",
                    f"- Total tags: {data.get('total_tags', 0)}",
                    f"- Total words: {data.get('total_words', 0)}",
                    f"- Orphan notes: {data.get('orphan_count', 0)}",
                ]
                return [TextContent(type="text", text="\n".join(lines))]

            # ── Agent tools ──────────────────────────────────────────
            elif name == "get_ha_state":
                resp = await client.get(f"/agents/ha-state")
                resp.raise_for_status()
                data = resp.json()
                entity_id = arguments["entity_id"]
                match = next(
                    (e for e in data.get("entities", []) if e.get("entity_id") == entity_id),
                    None,
                )
                if match:
                    return [TextContent(type="text", text=f"State of {entity_id}: {match}")]
                return [TextContent(type="text", text=f"No cached state found for {entity_id}")]

            elif name == "search_ha_events":
                # Delegate to the agents API — we need a search endpoint.
                # For now use the internal event filter via the status endpoint
                # as a placeholder, or explain that semantic search requires
                # the agent system to be active.
                resp = await client.get("/agents/status")
                resp.raise_for_status()
                status = resp.json()
                if not status.get("enabled"):
                    return [TextContent(type="text", text="Agent system is not active.")]
                return [TextContent(
                    type="text",
                    text=f"HA event search for '{arguments['query']}' — use /api/agents/ha-state for now. "
                         f"Queue depth: {status.get('trigger_queue_depth', 0)}",
                )]

            elif name == "get_agent_decisions":
                limit = arguments.get("limit", 20)
                resp = await client.get("/agents/decisions", params={"limit": limit})
                resp.raise_for_status()
                data = resp.json()
                decisions = data.get("decisions", [])
                if not decisions:
                    return [TextContent(type="text", text="No agent decisions recorded yet.")]
                lines = [f"Recent agent decisions ({len(decisions)}):"]
                for d in decisions:
                    lines.append(
                        f"- [{d.get('agent')}] {d.get('entity')}: "
                        f"{d.get('action')} (confidence: {d.get('confidence', 0):.0%}) "
                        f"— {d.get('reasoning', '')[:120]}"
                    )
                return [TextContent(type="text", text="\n".join(lines))]

            elif name == "trigger_agent":
                resp = await client.post("/agents/trigger", json={
                    "entity_id": arguments["entity_id"],
                    "new_state": arguments["new_state"],
                    "old_state": arguments.get("old_state", ""),
                })
                resp.raise_for_status()
                data = resp.json()
                return [TextContent(type="text", text=f"Trigger queued. Queue depth: {data.get('queue_depth', 0)}")]

            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"API error: {e.response.status_code} {e.response.text}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {e}")]


async def run():
    """Run the MCP server over stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(run())
