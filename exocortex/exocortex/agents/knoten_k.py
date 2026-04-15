"""Knoten K \u2014 Meta-observation agent that audits every agent decision into the
knowledge graph (Oxigraph) and agent memory (Redis)."""

from __future__ import annotations

import logging
import uuid
from datetime import timezone
from urllib.parse import quote

from exocortex.agents.models import AgentDecision
from exocortex.engines.oxigraph import OxigraphEngine
from exocortex.engines.redis_client import RedisEngine

logger = logging.getLogger(__name__)

EX = "http://exocortex.local/ontology#"
XSD = "http://www.w3.org/2001/XMLSchema#"
DCTERMS = "http://purl.org/dc/terms/"


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")


class MetaObserver:
    """Logs every ``AgentDecision`` to Oxigraph and Redis for auditing."""

    def __init__(self, oxigraph: OxigraphEngine, redis: RedisEngine):
        self.oxigraph = oxigraph
        self.redis = redis

    async def record(self, decision: AgentDecision) -> None:
        """Persist a decision to both the RDF graph and agent memory."""
        try:
            await self._record_rdf(decision)
        except Exception as exc:
            logger.error("Knoten K RDF write failed: %s", exc)

        try:
            await self._record_redis(decision)
        except Exception as exc:
            logger.error("Knoten K Redis write failed: %s", exc)

    # ── RDF ───────────────────────────────────────────────────────────

    async def _record_rdf(self, d: AgentDecision) -> None:
        decision_id = uuid.uuid4().hex[:12]
        uri = f"<http://exocortex.local/decision/{decision_id}>"
        entity_uri = f"<http://exocortex.local/entity/{quote(d.trigger_entity, safe='')}>"
        ts = d.timestamp.astimezone(timezone.utc).isoformat()

        triples = "\n".join([
            f'{uri} a <{EX}AgentDecision> .',
            f'{uri} <{EX}agent> "{_escape(d.agent)}" .',
            f'{uri} <{EX}triggeredBy> {entity_uri} .',
            f'{uri} <{EX}decidedAction> "{_escape(d.action_taken)}" .',
            f'{uri} <{EX}decisionReasoning> "{_escape(d.reasoning)}" .',
            f'{uri} <{EX}confidence> "{d.confidence}"^^<{XSD}decimal> .',
            f'{uri} <{DCTERMS}created> "{ts}"^^<{XSD}dateTime> .',
        ])

        sparql = f"INSERT DATA {{\n{triples}\n}}"
        await self.oxigraph.sparql_update(sparql)

    # ── Redis (agent memory) ─────────────────────────────────────────

    async def _record_redis(self, d: AgentDecision) -> None:
        fact = (
            f"Agent '{d.agent}' decided '{d.action_taken}' for {d.trigger_entity} "
            f"(confidence {d.confidence:.0%}): {d.reasoning}"
        )
        await self.redis.store_fact(
            agent_id=d.agent,
            fact=fact,
            confidence=d.confidence,
            source="knoten_k",
            tags=["agent_decision", d.trigger_entity.split(".")[0]],
        )

    # ── Query helpers ────────────────────────────────────────────────

    async def get_recent_decisions(self, limit: int = 50) -> list[dict]:
        """Retrieve the most recent agent decisions from Oxigraph."""
        query = f"""
        SELECT ?d ?agent ?entity ?action ?reasoning ?confidence ?created
        WHERE {{
            ?d a <{EX}AgentDecision> ;
               <{EX}agent> ?agent ;
               <{EX}triggeredBy> ?entity ;
               <{EX}decidedAction> ?action ;
               <{EX}decisionReasoning> ?reasoning ;
               <{EX}confidence> ?confidence ;
               <{DCTERMS}created> ?created .
        }}
        ORDER BY DESC(?created)
        LIMIT {limit}
        """
        result = await self.oxigraph.sparql_query(query)
        bindings = result.get("results", {}).get("bindings", [])
        return [
            {
                "agent": b["agent"]["value"],
                "entity": b["entity"]["value"].replace("http://exocortex.local/entity/", ""),
                "action": b["action"]["value"],
                "reasoning": b["reasoning"]["value"],
                "confidence": float(b["confidence"]["value"]),
                "created": b["created"]["value"],
            }
            for b in bindings
        ]
