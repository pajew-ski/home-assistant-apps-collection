"""Agent memory API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from exocortex.models import ConversationMessage, FactCreateRequest, FactItem, WorkingMemory

router = APIRouter()


def _get_state():
    from exocortex.main import app_state
    return app_state


@router.post("/agent/{agent_id}/facts")
async def store_fact(agent_id: str, req: FactCreateRequest):
    """Store a fact in agent memory."""
    state = _get_state()
    await state.redis.store_fact(
        agent_id=agent_id,
        fact=req.fact,
        confidence=req.confidence,
        source=req.source,
        tags=req.tags,
        ttl_days=req.ttl_days,
    )
    return {"status": "stored"}


@router.get("/agent/{agent_id}/facts")
async def get_facts(
    agent_id: str,
    limit: int = Query(10, ge=1, le=100),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    tags: list[str] | None = Query(None),
):
    """Retrieve facts from agent memory."""
    state = _get_state()
    facts = await state.redis.get_facts(
        agent_id=agent_id,
        limit=limit,
        min_confidence=min_confidence,
        tags=tags,
    )
    return {"facts": facts}


@router.delete("/agent/{agent_id}/facts")
async def delete_facts(agent_id: str, older_than: str | None = Query(None)):
    """Delete facts from agent memory."""
    state = _get_state()
    await state.redis.delete_facts(agent_id, older_than=older_than)
    return {"status": "deleted"}


@router.post("/agent/{agent_id}/conversations")
async def store_conversation(agent_id: str, msg: ConversationMessage):
    """Append a message to conversation history."""
    state = _get_state()
    await state.redis.store_conversation(
        agent_id=agent_id,
        role=msg.role,
        content=msg.content,
        metadata=msg.metadata,
    )
    return {"status": "stored"}


@router.get("/agent/{agent_id}/conversations")
async def get_conversations(agent_id: str, limit: int = Query(50, ge=1, le=1000)):
    """Get conversation history for an agent."""
    state = _get_state()
    messages = await state.redis.get_conversations(agent_id, limit=limit)
    return {"messages": messages}


@router.put("/agent/{agent_id}/working/{session_id}")
async def set_working_memory(agent_id: str, session_id: str, memory: WorkingMemory):
    """Set working memory for a session."""
    state = _get_state()
    await state.redis.set_working_memory(agent_id, session_id, memory.model_dump())
    return {"status": "stored"}


@router.get("/agent/{agent_id}/working/{session_id}")
async def get_working_memory(agent_id: str, session_id: str):
    """Get working memory for a session."""
    state = _get_state()
    data = await state.redis.get_working_memory(agent_id, session_id)
    return data or {"current_task": "", "context_notes": [], "intermediate_results": {}}
