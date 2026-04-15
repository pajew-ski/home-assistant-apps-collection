"""REST API endpoints for the multi-agent orchestration layer."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/agents", tags=["agents"])
logger = logging.getLogger(__name__)


def _state() -> Any:
    """Return the global ``app_state``.  Deferred import avoids circular deps."""
    from exocortex.main import app_state

    return app_state


# ── Request / Response models ────────────────────────────────────────


class ManualTriggerRequest(BaseModel):
    entity_id: str
    new_state: str
    old_state: str = ""
    trigger_type: str = "manual"


# ── Endpoints ────────────────────────────────────────────────────────


@router.get("/status")
async def agent_status():
    """Agent system health: WS connected, LLM reachable, queue depth."""
    st = _state()
    agent_sys = getattr(st, "agent_system", None)
    if agent_sys is None:
        return {"enabled": False, "reason": "agent system not initialised"}

    llm_ok = False
    try:
        llm_ok = await agent_sys["llm"].health_check()
    except Exception:
        pass

    ha_ok = False
    try:
        ha_ok = await agent_sys["mcp"].health_check()
    except Exception:
        pass

    ws_task = agent_sys.get("ws_task")
    ws_running = ws_task is not None and not ws_task.done()

    orch = agent_sys.get("orchestrator")
    queue_depth = orch.queue_depth if orch else 0

    return {
        "enabled": True,
        "websocket_connected": ws_running,
        "llm_reachable": llm_ok,
        "ha_api_reachable": ha_ok,
        "trigger_queue_depth": queue_depth,
    }


@router.get("/decisions")
async def agent_decisions(limit: int = 50):
    """Recent agent decisions from Knoten K."""
    st = _state()
    agent_sys = getattr(st, "agent_system", None)
    if agent_sys is None:
        raise HTTPException(status_code=503, detail="Agent system not active")

    observer = agent_sys.get("meta_observer")
    if observer is None:
        return {"decisions": []}

    decisions = await observer.get_recent_decisions(limit=limit)
    return {"decisions": decisions, "count": len(decisions)}


@router.get("/ha-state")
async def ha_state():
    """Dump the Redis hot cache of current HA entity states."""
    st = _state()
    redis = st.redis

    states: list[dict[str, Any]] = []
    tc = redis._text_client()
    try:
        cursor = "0"
        while True:
            cursor, keys = await tc.scan(cursor=cursor, match="ha:state:*", count=200)
            for key in keys:
                raw = await tc.get(key)
                if raw:
                    states.append(json.loads(raw))
            if cursor == "0":
                break
    finally:
        await tc.aclose()

    return {"entities": states, "count": len(states)}


@router.post("/trigger")
async def manual_trigger(req: ManualTriggerRequest):
    """Manually inject a trigger into the orchestrator queue (for testing)."""
    import asyncio

    from exocortex.agents.models import AgentTrigger, HAStateEvent

    st = _state()
    agent_sys = getattr(st, "agent_system", None)
    if agent_sys is None:
        raise HTTPException(status_code=503, detail="Agent system not active")

    queue: asyncio.Queue = agent_sys.get("trigger_queue")
    if queue is None:
        raise HTTPException(status_code=503, detail="Trigger queue not available")

    event = HAStateEvent(
        entity_id=req.entity_id,
        old_state=req.old_state,
        new_state=req.new_state,
        timestamp=datetime.now(timezone.utc),
    )
    trigger = AgentTrigger(event=event, trigger_type=req.trigger_type)
    await queue.put(trigger)
    return {"status": "queued", "queue_depth": queue.qsize()}


@router.get("/config")
async def agent_config():
    """Return the current agent-related configuration values."""
    st = _state()
    config = st.config
    return {
        "enable_agents": getattr(config, "enable_agents", False),
        "ha_websocket_url": getattr(config, "ha_websocket_url", ""),
        "ollama_url": getattr(config, "ollama_url", ""),
        "ollama_model": getattr(config, "ollama_model", ""),
        "ha_mcp_url": getattr(config, "ha_mcp_url", ""),
        "agent_filter_domains": getattr(config, "agent_filter_domains", []),
        "agent_filter_min_change_interval_seconds": getattr(
            config, "agent_filter_min_change_interval_seconds", 5,
        ),
        "agent_context_window_tokens": getattr(
            config, "agent_context_window_tokens", 4096,
        ),
    }
