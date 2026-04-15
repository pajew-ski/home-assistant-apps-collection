"""GoT Dispatcher \u2014 central orchestrator that consumes trigger events, builds
context via RAG, calls the LLM, and delegates to domain agents."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from exocortex.agents.domain_agents import (
    BaseAgent,
    ClimateAgent,
    CommunicationAgent,
    LightingAgent,
    SecurityAgent,
)
from exocortex.agents.ha_mcp_client import HaMcpClient
from exocortex.agents.knoten_k import MetaObserver
from exocortex.agents.llm_client import OllamaClient
from exocortex.agents.models import AgentDecision, AgentTask, AgentTrigger
from exocortex.engines.oxigraph import OxigraphEngine
from exocortex.engines.qdrant import QdrantEngine
from exocortex.engines.redis_client import RedisEngine

logger = logging.getLogger(__name__)

# Map HA domain prefixes to agent classes
_DOMAIN_AGENT_MAP: dict[str, type[BaseAgent]] = {
    "light": LightingAgent,
    "switch": LightingAgent,
    "climate": ClimateAgent,
    "binary_sensor": SecurityAgent,
    "lock": SecurityAgent,
    "alarm_control_panel": SecurityAgent,
}

EX = "http://exocortex.local/ontology#"


class Orchestrator:
    """Consumes ``AgentTrigger`` objects from the queue, builds RAG context,
    calls the LLM, and dispatches to the appropriate domain agent."""

    def __init__(
        self,
        *,
        config: Any,
        llm: OllamaClient,
        mcp: HaMcpClient,
        redis: RedisEngine,
        qdrant: QdrantEngine,
        oxigraph: OxigraphEngine,
        embedding: Any,
        event_filter: Any,
        meta_observer: MetaObserver,
        trigger_queue: asyncio.Queue[AgentTrigger],
    ):
        self.config = config
        self.llm = llm
        self.mcp = mcp
        self.redis = redis
        self.qdrant = qdrant
        self.oxigraph = oxigraph
        self.embedding = embedding
        self.event_filter = event_filter
        self.meta_observer = meta_observer
        self.trigger_queue = trigger_queue
        self._max_tokens: int = int(
            getattr(config, "agent_context_window_tokens", 4096)
        )

        # Instantiate domain agents once
        self._agents: dict[str, BaseAgent] = {}
        for domain, cls in _DOMAIN_AGENT_MAP.items():
            if domain not in self._agents:
                self._agents[domain] = cls(
                    name=cls.__name__,
                    llm=llm,
                    mcp=mcp,
                    redis=redis,
                )
        self._comm_agent = CommunicationAgent(
            name="CommunicationAgent", llm=llm, mcp=mcp, redis=redis,
        )

    # ── Main loop ────────────────────────────────────────────────────

    async def run(self) -> None:
        """Run forever, pulling triggers from the queue."""
        logger.info("Orchestrator started — waiting for triggers")
        while True:
            try:
                trigger = await self.trigger_queue.get()
                await self._handle_trigger(trigger)
                self.trigger_queue.task_done()
            except asyncio.CancelledError:
                logger.info("Orchestrator cancelled")
                return
            except Exception as exc:
                logger.error("Orchestrator error: %s", exc, exc_info=True)

    # ── Trigger handling ─────────────────────────────────────────────

    async def _handle_trigger(self, trigger: AgentTrigger) -> None:
        ev = trigger.event
        logger.info(
            "Processing trigger: %s  %s -> %s",
            ev.entity_id, ev.old_state, ev.new_state,
        )

        # 1. Build context via RAG
        context = await self._build_context(trigger)

        # 2. Ask the orchestrator LLM what to do
        decision = await self._evaluate(trigger, context)

        # 3. Delegate to domain agent if the LLM suggested an action
        if decision.action_taken and decision.action_taken != "none":
            domain = ev.entity_id.split(".")[0]
            agent = self._agents.get(domain)
            if agent:
                task = AgentTask(
                    trigger=trigger,
                    target_entity=ev.entity_id,
                    desired_action=decision.action_taken,
                    context=context,
                    reasoning=decision.reasoning,
                )
                domain_decision = await agent.execute(task)
                await self.meta_observer.record(domain_decision)

                # Execute the service call if the domain agent is confident
                if (
                    domain_decision.action_taken != "none"
                    and domain_decision.confidence >= 0.5
                ):
                    await self._execute_action(domain_decision)
            else:
                # No dedicated agent — orchestrator handles directly
                await self.meta_observer.record(decision)
        else:
            # No action — still log the decision
            await self.meta_observer.record(decision)

    # ── RAG context assembly ─────────────────────────────────────────

    async def _build_context(self, trigger: AgentTrigger) -> dict[str, Any]:
        ev = trigger.event
        context: dict[str, Any] = {}

        # 1. Redis hot cache — entities in the same area
        if ev.area:
            area_states = await self._get_area_states(ev.area)
            context["area_entities"] = area_states

        # 2. Qdrant semantic search — similar recent events
        query = (
            f"{ev.friendly_name} in {ev.area or 'unknown'} "
            f"changed from {ev.old_state} to {ev.new_state}"
        )
        similar = await self.event_filter.search_recent_events(query, limit=5)
        context["similar_events"] = similar

        # 3. Oxigraph SPARQL — entity relationships
        sparql_context = await self._get_entity_context(ev.entity_id)
        context["graph_context"] = sparql_context

        return context

    async def _get_area_states(self, area: str) -> list[dict[str, Any]]:
        """Scan Redis for entities sharing the same area."""
        states: list[dict[str, Any]] = []
        try:
            tc = self.redis._text_client()
            try:
                cursor = "0"
                while True:
                    cursor, keys = await tc.scan(
                        cursor=cursor, match="ha:state:*", count=100,
                    )
                    for key in keys:
                        raw = await tc.get(key)
                        if raw:
                            data = json.loads(raw)
                            if data.get("area") == area:
                                states.append(data)
                    if cursor == "0":
                        break
            finally:
                await tc.aclose()
        except Exception as exc:
            logger.error("Area state scan failed: %s", exc)
        return states

    async def _get_entity_context(self, entity_id: str) -> list[dict[str, str]]:
        """Retrieve known facts about the entity from the knowledge graph."""
        from urllib.parse import quote

        entity_uri = f"http://exocortex.local/entity/{quote(entity_id, safe='')}"
        query = f"""
        SELECT ?p ?o WHERE {{
            <{entity_uri}> ?p ?o .
        }} LIMIT 20
        """
        result = await self.oxigraph.sparql_query(query)
        bindings = result.get("results", {}).get("bindings", [])
        return [
            {"predicate": b["p"]["value"], "object": b["o"]["value"]}
            for b in bindings
        ]

    # ── LLM evaluation ───────────────────────────────────────────────

    async def _evaluate(
        self, trigger: AgentTrigger, context: dict[str, Any],
    ) -> AgentDecision:
        ev = trigger.event
        system_prompt = (
            "You are the central orchestrator of a smart-home AI system. "
            "Evaluate the following sensor event and context, then decide if "
            "any action should be taken. Respond with JSON:\n"
            '{"action": "<HA service call like light.turn_on or none>", '
            '"reasoning": "<brief explanation>", "confidence": <0.0-1.0>}\n\n'
            "Be conservative — only suggest actions when clearly beneficial."
        )

        # Truncate context to fit token budget (rough heuristic: 4 chars ≈ 1 token)
        ctx_str = json.dumps(context, default=str)
        max_chars = self._max_tokens * 4
        if len(ctx_str) > max_chars:
            ctx_str = ctx_str[:max_chars] + "..."

        user_msg = (
            f"Event: {ev.entity_id} ({ev.friendly_name}) in {ev.area or 'unknown'} "
            f"changed from '{ev.old_state}' to '{ev.new_state}' at {ev.timestamp.isoformat()}\n\n"
            f"Context:\n{ctx_str}"
        )

        try:
            raw = await self.llm.chat(
                [{"role": "user", "content": user_msg}],
                system=system_prompt,
            )
            return self._parse_llm_response(ev.entity_id, raw)
        except Exception as exc:
            logger.error("Orchestrator LLM evaluation failed: %s", exc)
            return AgentDecision(
                agent="orchestrator",
                trigger_entity=ev.entity_id,
                action_taken="none",
                reasoning=f"LLM error: {exc}",
                confidence=0.0,
                timestamp=datetime.now(timezone.utc),
                success=False,
            )

    def _parse_llm_response(self, entity_id: str, raw: str) -> AgentDecision:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return AgentDecision(
                agent="orchestrator",
                trigger_entity=entity_id,
                action_taken="none",
                reasoning=raw[:300],
                confidence=0.1,
                timestamp=datetime.now(timezone.utc),
            )

        return AgentDecision(
            agent="orchestrator",
            trigger_entity=entity_id,
            action_taken=data.get("action", "none"),
            reasoning=data.get("reasoning", ""),
            confidence=float(data.get("confidence", 0.0)),
            timestamp=datetime.now(timezone.utc),
        )

    # ── Action execution ─────────────────────────────────────────────

    async def _execute_action(self, decision: AgentDecision) -> None:
        """Parse a service-call string like ``light.turn_on`` and call HA."""
        action = decision.action_taken
        if not action or action == "none":
            return

        parts = action.split(".", 1)
        if len(parts) != 2:
            logger.warning("Cannot parse action '%s' as domain.service", action)
            return

        domain, service = parts
        entity_id = decision.trigger_entity

        success = await self.mcp.call_service(domain, service, entity_id)
        if not success:
            logger.warning(
                "Action %s.%s failed for %s", domain, service, entity_id,
            )

    # ── Status ───────────────────────────────────────────────────────

    @property
    def queue_depth(self) -> int:
        return self.trigger_queue.qsize()
