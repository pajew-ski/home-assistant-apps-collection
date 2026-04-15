"""Pydantic models for the agent event/state pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class HAStateEvent(BaseModel):
    """A single Home Assistant state_changed event."""

    entity_id: str
    old_state: str
    new_state: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    area: str = ""
    friendly_name: str = ""


class AgentTrigger(BaseModel):
    """An event that has passed filtering and should be evaluated by the orchestrator."""

    event: HAStateEvent
    trigger_type: str = "state_change"  # "state_change", "intent", "schedule"
    priority: int = 0


class AgentTask(BaseModel):
    """A concrete task dispatched from the orchestrator to a domain agent."""

    trigger: AgentTrigger
    target_entity: str
    desired_action: str
    context: dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""


class AgentDecision(BaseModel):
    """The outcome of an agent's evaluation — logged by Knoten K."""

    agent: str
    trigger_entity: str
    action_taken: str = "none"  # "none", service call description, etc.
    reasoning: str = ""
    confidence: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    success: bool = True
