"""Graph API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from exocortex.models import GraphResponse, GraphStats, OrphanItem

router = APIRouter()


def _get_state():
    from exocortex.main import app_state
    return app_state


@router.get("/graph/neighbors/{path:path}")
async def get_neighbors(path: str, depth: int = Query(2, ge=1, le=4)):
    """Get local subgraph around a note."""
    state = _get_state()
    result = await state.oxigraph.get_neighbors(path, depth=depth)
    return result


@router.get("/graph/backlinks/{path:path}")
async def get_backlinks(path: str):
    """Get backlinks for a note."""
    state = _get_state()
    backlinks = await state.oxigraph.get_backlinks(path)
    return {"backlinks": backlinks}


@router.get("/graph/full", response_model=GraphResponse)
async def get_full_graph(
    cluster: bool = Query(False),
    min_connections: int = Query(0, ge=0),
):
    """Get the full knowledge graph."""
    state = _get_state()
    result = await state.oxigraph.get_full_graph()

    # Filter by min connections if specified
    if min_connections > 0:
        connection_count: dict[str, int] = {}
        for edge in result["edges"]:
            connection_count[edge["source"]] = connection_count.get(edge["source"], 0) + 1
            connection_count[edge["target"]] = connection_count.get(edge["target"], 0) + 1

        connected_nodes = {n for n, c in connection_count.items() if c >= min_connections}
        result["nodes"] = [n for n in result["nodes"] if n["id"] in connected_nodes]
        result["edges"] = [
            e for e in result["edges"]
            if e["source"] in connected_nodes and e["target"] in connected_nodes
        ]

    return GraphResponse(
        nodes=result["nodes"],
        edges=result["edges"],
        clusters=[],
    )


@router.get("/graph/orphans")
async def get_orphans():
    """Get notes with no incoming links."""
    state = _get_state()
    orphans = await state.oxigraph.get_orphans()
    return {"orphans": orphans}


@router.get("/graph/stats", response_model=GraphStats)
async def get_graph_stats():
    """Get graph statistics."""
    state = _get_state()
    graph = await state.oxigraph.get_full_graph()

    connection_count: dict[str, int] = {}
    for edge in graph["edges"]:
        connection_count[edge["source"]] = connection_count.get(edge["source"], 0) + 1
        connection_count[edge["target"]] = connection_count.get(edge["target"], 0) + 1

    total_nodes = len(graph["nodes"])
    total_edges = len(graph["edges"])
    avg = sum(connection_count.values()) / max(len(connection_count), 1) if connection_count else 0

    most_connected = sorted(
        [{"path": k, "title": k, "connection_count": v} for k, v in connection_count.items()],
        key=lambda x: x["connection_count"],
        reverse=True,
    )[:10]

    return GraphStats(
        total_nodes=total_nodes,
        total_edges=total_edges,
        avg_connections=round(avg, 2),
        most_connected=most_connected,
    )
