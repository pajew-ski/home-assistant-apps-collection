"""Specialised domain agents for climate, security, lighting, and communication."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from exocortex.agents.ha_mcp_client import HaMcpClient
from exocortex.agents.llm_client import OllamaClient
from exocortex.agents.models import AgentDecision, AgentTask
from exocortex.engines.redis_client import RedisEngine

logger = logging.getLogger(__name__)


class BaseAgent:
    """Common plumbing shared by every domain agent."""

    name: str = "base"

    def __init__(
        self,
        name: str,
        llm: OllamaClient,
        mcp: HaMcpClient,
        redis: RedisEngine,
    ):
        self.name = name
        self.llm = llm
        self.mcp = mcp
        self.redis = redis

    async def execute(self, task: AgentTask) -> AgentDecision:
        """Evaluate *task* and return an ``AgentDecision``."""
        raise NotImplementedError

    # ── Helpers ──────────────────────────────────────────────────────

    def _decision(
        self,
        task: AgentTask,
        action: str = "none",
        reasoning: str = "",
        confidence: float = 0.0,
        success: bool = True,
    ) -> AgentDecision:
        return AgentDecision(
            agent=self.name,
            trigger_entity=task.trigger.event.entity_id,
            action_taken=action,
            reasoning=reasoning,
            confidence=confidence,
            timestamp=datetime.now(timezone.utc),
            success=success,
        )


# ── Climate ──────────────────────────────────────────────────────────


class ClimateAgent(BaseAgent):
    """Handles ``climate.*`` entities — HVAC analysis and adjustments."""

    async def execute(self, task: AgentTask) -> AgentDecision:
        ev = task.trigger.event
        system_prompt = (
            "You are a climate-control agent for a smart home.  "
            "Given the event and context, decide whether any HVAC action is needed. "
            "Respond with a JSON object: {\"action\": \"<service_call or none>\", "
            "\"reasoning\": \"<why>\", \"confidence\": <0-1>}. "
            "Only suggest actions when there is a clear need."
        )
        user_msg = (
            f"Entity {ev.entity_id} ({ev.friendly_name}) in {ev.area or 'unknown area'} "
            f"changed from '{ev.old_state}' to '{ev.new_state}'.\n"
            f"Context: {task.context}"
        )
        try:
            raw = await self.llm.chat(
                [{"role": "user", "content": user_msg}],
                system=system_prompt,
            )
            return self._parse_llm_response(task, raw)
        except Exception as exc:
            logger.error("ClimateAgent LLM call failed: %s", exc)
            return self._decision(task, reasoning=f"LLM error: {exc}", success=False)

    def _parse_llm_response(self, task: AgentTask, raw: str) -> AgentDecision:
        import json

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return self._decision(task, reasoning=raw[:300], confidence=0.1)

        action = data.get("action", "none")
        reasoning = data.get("reasoning", "")
        confidence = float(data.get("confidence", 0.0))
        return self._decision(task, action=action, reasoning=reasoning, confidence=confidence)


# ── Security ─────────────────────────────────────────────────────────


class SecurityAgent(BaseAgent):
    """Handles ``binary_sensor.*``, ``lock.*``, ``alarm_control_panel.*``."""

    async def execute(self, task: AgentTask) -> AgentDecision:
        ev = task.trigger.event
        system_prompt = (
            "You are a home-security agent.  Evaluate the sensor/alarm event and "
            "decide if an alert or lock action is warranted. "
            "Respond with JSON: {\"action\": \"<service_call or none>\", "
            "\"reasoning\": \"<why>\", \"confidence\": <0-1>}. "
            "Err on the side of caution — alerting is cheap, missing a threat is not."
        )
        user_msg = (
            f"Entity {ev.entity_id} ({ev.friendly_name}) in {ev.area or 'unknown area'} "
            f"changed from '{ev.old_state}' to '{ev.new_state}'.\n"
            f"Context: {task.context}"
        )
        try:
            raw = await self.llm.chat(
                [{"role": "user", "content": user_msg}],
                system=system_prompt,
            )
            return self._parse_llm_response(task, raw)
        except Exception as exc:
            logger.error("SecurityAgent LLM call failed: %s", exc)
            return self._decision(task, reasoning=f"LLM error: {exc}", success=False)

    def _parse_llm_response(self, task: AgentTask, raw: str) -> AgentDecision:
        import json

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return self._decision(task, reasoning=raw[:300], confidence=0.1)

        action = data.get("action", "none")
        reasoning = data.get("reasoning", "")
        confidence = float(data.get("confidence", 0.0))
        return self._decision(task, action=action, reasoning=reasoning, confidence=confidence)


# ── Lighting ─────────────────────────────────────────────────────────


class LightingAgent(BaseAgent):
    """Handles ``light.*`` and ``switch.*`` entities."""

    async def execute(self, task: AgentTask) -> AgentDecision:
        ev = task.trigger.event
        system_prompt = (
            "You are a lighting agent for a smart home. "
            "Given the event and context, decide whether any lighting action is needed. "
            "Respond with JSON: {\"action\": \"<service_call or none>\", "
            "\"reasoning\": \"<why>\", \"confidence\": <0-1>}."
        )
        user_msg = (
            f"Entity {ev.entity_id} ({ev.friendly_name}) in {ev.area or 'unknown area'} "
            f"changed from '{ev.old_state}' to '{ev.new_state}'.\n"
            f"Context: {task.context}"
        )
        try:
            raw = await self.llm.chat(
                [{"role": "user", "content": user_msg}],
                system=system_prompt,
            )
            return self._parse_llm_response(task, raw)
        except Exception as exc:
            logger.error("LightingAgent LLM call failed: %s", exc)
            return self._decision(task, reasoning=f"LLM error: {exc}", success=False)

    def _parse_llm_response(self, task: AgentTask, raw: str) -> AgentDecision:
        import json

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return self._decision(task, reasoning=raw[:300], confidence=0.1)

        action = data.get("action", "none")
        reasoning = data.get("reasoning", "")
        confidence = float(data.get("confidence", 0.0))
        return self._decision(task, action=action, reasoning=reasoning, confidence=confidence)


# ── Communication ────────────────────────────────────────────────────


class CommunicationAgent(BaseAgent):
    """Sends notifications via HA's ``notify`` service."""

    async def execute(self, task: AgentTask) -> AgentDecision:
        ev = task.trigger.event
        system_prompt = (
            "You are a communication agent.  Decide if this event warrants a "
            "user notification.  If so, compose a short, clear message. "
            "Respond with JSON: {\"action\": \"notify.notify\" or \"none\", "
            "\"message\": \"<text if notifying>\", \"reasoning\": \"<why>\", "
            "\"confidence\": <0-1>}."
        )
        user_msg = (
            f"Entity {ev.entity_id} ({ev.friendly_name}) in {ev.area or 'unknown area'} "
            f"changed from '{ev.old_state}' to '{ev.new_state}'.\n"
            f"Context: {task.context}"
        )
        try:
            raw = await self.llm.chat(
                [{"role": "user", "content": user_msg}],
                system=system_prompt,
            )
            return await self._handle_response(task, raw)
        except Exception as exc:
            logger.error("CommunicationAgent LLM call failed: %s", exc)
            return self._decision(task, reasoning=f"LLM error: {exc}", success=False)

    async def _handle_response(self, task: AgentTask, raw: str) -> AgentDecision:
        import json

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return self._decision(task, reasoning=raw[:300], confidence=0.1)

        action = data.get("action", "none")
        reasoning = data.get("reasoning", "")
        confidence = float(data.get("confidence", 0.0))
        message = data.get("message", "")

        if action != "none" and message:
            success = await self.mcp.call_service(
                "notify", "notify",
                entity_id="",
                data={"message": message},
            )
            return self._decision(
                task,
                action=f"notify.notify: {message[:80]}",
                reasoning=reasoning,
                confidence=confidence,
                success=success,
            )

        return self._decision(task, action="none", reasoning=reasoning, confidence=confidence)
