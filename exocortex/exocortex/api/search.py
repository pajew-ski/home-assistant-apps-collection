"""Search API endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from exocortex.models import SearchMode, SearchResponse, SortField, SortOrder

router = APIRouter()


def get_search_engine():
    from exocortex.main import app_state
    return app_state.search_engine


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query("", description="Search query"),
    mode: SearchMode = Query(SearchMode.hybrid),
    tags: list[str] | None = Query(None),
    tags_or: list[str] | None = Query(None),
    folder: str | None = Query(None),
    confidence_min: int | None = Query(None, ge=1, le=5),
    confidence_max: int | None = Query(None, ge=1, le=5),
    status: str | None = Query(None),
    type: str | None = Query(None),
    geo_lat: float | None = Query(None),
    geo_lon: float | None = Query(None),
    geo_radius_km: float | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    sort: SortField = Query(SortField.relevance),
    sort_order: SortOrder = Query(SortOrder.desc),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Unified search with mode switching."""
    engine = get_search_engine()

    filters: dict[str, Any] = {}
    if tags:
        filters["tags"] = tags
    if tags_or:
        filters["tags_or"] = tags_or
    if folder:
        filters["folder"] = folder
    if confidence_min is not None:
        filters["confidence_min"] = confidence_min
    if confidence_max is not None:
        filters["confidence_max"] = confidence_max
    if status:
        filters["status"] = status
    if type:
        filters["type"] = type
    if date_from:
        filters["date_from"] = date_from.isoformat()
    if date_to:
        filters["date_to"] = date_to.isoformat()
    if geo_lat is not None and geo_lon is not None:
        filters["geo_lat"] = geo_lat
        filters["geo_lon"] = geo_lon
        filters["geo_radius_km"] = geo_radius_km or 10

    result = await engine.search(
        query=q,
        mode=mode,
        filters=filters,
        sort=sort.value if sort != SortField.relevance else None,
        sort_order=sort_order.value,
        limit=limit,
        offset=offset,
    )

    return SearchResponse(
        total_hits=result["total_hits"],
        processing_time_ms=result["processing_time_ms"],
        mode_used=result["mode_used"],
        results=result["results"],
    )
