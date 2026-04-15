"""Semantic filter and vectorisation router for HA state_changed events."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from exocortex.agents.models import AgentTrigger, HAStateEvent
from exocortex.core.embedding import EmbeddingEngine
from exocortex.engines.oxigraph import OxigraphEngine
from exocortex.engines.qdrant import QdrantEngine, VECTOR_SIZE
from exocortex.engines.redis_client import RedisEngine

logger = logging.getLogger(__name__)

HA_EVENTS_COLLECTION = "ha_events"

# Trigger domains/patterns that force an orchestrator evaluation
_TRIGGER_DOMAINS = {"binary_sensor", "alarm_control_panel"}

EX = "http://exocortex.local/ontology#"
XSD = "http://www.w3.org/2001/XMLSchema#"


class EventFilter:
    """Receives raw ``state_changed`` JSON and routes significant events to
    storage backends and the orchestrator trigger queue."""

    def __init__(
        self,
        *,
        config: Any,
        redis: RedisEngine,
        qdrant: QdrantEngine,
        oxigraph: OxigraphEngine,
        embedding: EmbeddingEngine | None,
        trigger_queue: asyncio.Queue[AgentTrigger],
    ):
        self.config = config
        self.redis = redis
        self.qdrant = qdrant
        self.oxigraph = oxigraph
        self.embedding = embedding
        self.trigger_queue = trigger_queue

        self._allowed_domains: set[str] = set(
            getattr(config, "agent_filter_domains", [
                "light", "switch", "climate", "binary_sensor",
                "sensor", "cover", "lock", "alarm_control_panel",
            ])
        )
        self._min_interval: int = int(
            getattr(config, "agent_filter_min_change_interval_seconds", 5)
        )
        self._collection_ensured = False

    # ── Public entry point ───────────────────────────────────────────

    async def handle_event(self, event_data: dict[str, Any]) -> None:
        """Process a single ``state_changed`` event payload from the WS."""
        try:
            await self._process(event_data)
        except Exception as exc:
            logger.error("EventFilter error: %s", exc, exc_info=True)

    # ── Internal pipeline ────────────────────────────────────────────

    async def _process(self, data: dict[str, Any]) -> None:
        event = data.get("event", data)
        ed = event.get("data", event)

        entity_id: str = ed.get("entity_id", "")
        new_state_obj = ed.get("new_state") or {}
        old_state_obj = ed.get("old_state") or {}

        if not entity_id:
            return

        # 1. Domain filter
        domain = entity_id.split(".")[0]
        if domain not in self._allowed_domains:
            return

        old_state = old_state_obj.get("state", "")
        new_state = new_state_obj.get("state", "")
        attributes = new_state_obj.get("attributes", {})
        friendly_name = attributes.get("friendly_name", entity_id)
        area = attributes.get("area_id", "")

        # 2. Significance check — drop attribute-only changes
        if old_state == new_state:
            return

        # 3. Debounce
        debounce_key = f"ha:entity:last_change:{entity_id}"
        now = time.time()
        last_raw = await self.redis.get_raw(debounce_key)
        if last_raw:
            try:
                last_ts = float(last_raw)
                if now - last_ts < self._min_interval:
                    return
            except (ValueError, TypeError):
                pass
        await self.redis.set_raw(debounce_key, str(now).encode(), expire=3600)

        ts = datetime.now(timezone.utc)

        ha_event = HAStateEvent(
            entity_id=entity_id,
            old_state=old_state,
            new_state=new_state,
            attributes=attributes,
            timestamp=ts,
            area=area,
            friendly_name=friendly_name,
        )

        # 4. Route to storage (run concurrently)
        await asyncio.gather(
            self._store_hot_cache(ha_event),
            self._store_qdrant(ha_event),
            self._store_oxigraph(ha_event),
            return_exceptions=True,
        )

        # 5. Trigger evaluation
        if self._should_trigger(ha_event):
            trigger_type = "state_change"
            priority = 1 if domain in ("alarm_control_panel", "lock") else 0
            trigger = AgentTrigger(
                event=ha_event,
                trigger_type=trigger_type,
                priority=priority,
            )
            await self.trigger_queue.put(trigger)
            logger.debug("Trigger queued for %s", entity_id)

    # ── Storage helpers ──────────────────────────────────────────────

    async def _store_hot_cache(self, ev: HAStateEvent) -> None:
        """Write current state to the Redis hot cache with 1 h TTL."""
        payload = {
            "entity_id": ev.entity_id,
            "state": ev.new_state,
            "attributes": ev.attributes,
            "last_changed": ev.timestamp.isoformat(),
            "friendly_name": ev.friendly_name,
            "area": ev.area,
        }
        await self.redis.set_json(
            f"ha:state:{ev.entity_id}",
            payload,
            expire=3600,
        )

    async def _store_qdrant(self, ev: HAStateEvent) -> None:
        """Vectorise the event description and store in the ``ha_events`` collection."""
        if not self.embedding or not self.qdrant.enabled:
            return

        await self._ensure_collection()

        text = (
            f"{ev.friendly_name} in {ev.area or 'unknown area'} "
            f"changed from {ev.old_state} to {ev.new_state} "
            f"at {ev.timestamp.isoformat()}"
        )
        vector = await self.embedding.encode(text)

        from qdrant_client.http.models import PointStruct

        point_id = abs(hash(f"{ev.entity_id}:{ev.timestamp.isoformat()}")) % (2**63)
        point = PointStruct(
            id=point_id,
            vector=vector,
            payload={
                "entity_id": ev.entity_id,
                "old_state": ev.old_state,
                "new_state": ev.new_state,
                "friendly_name": ev.friendly_name,
                "area": ev.area,
                "timestamp": ev.timestamp.isoformat(),
                "text": text,
            },
        )
        try:
            self.qdrant.client.upsert(
                collection_name=HA_EVENTS_COLLECTION,
                points=[point],
            )
        except Exception as exc:
            logger.error("Qdrant ha_events upsert failed: %s", exc)

    async def _store_oxigraph(self, ev: HAStateEvent) -> None:
        """Emit an RDF triple for the entity's latest state."""
        entity_uri = f"<http://exocortex.local/entity/{quote(ev.entity_id, safe='')}>"
        ts = ev.timestamp.isoformat()

        # Delete old state triple, insert new one
        delete = f"DELETE WHERE {{ {entity_uri} <{EX}lastState> ?o . }}"
        insert_triples = "\n".join([
            f'{entity_uri} a <{EX}HAEntity> .',
            f'{entity_uri} <{EX}lastState> "{ev.new_state}" .',
            f'{entity_uri} <{EX}lastChanged> "{ts}"^^<{XSD}dateTime> .',
        ])
        insert = f"INSERT DATA {{\n{insert_triples}\n}}"

        await self.oxigraph.sparql_update(delete)
        await self.oxigraph.sparql_update(insert)

    # ── Qdrant collection management ─────────────────────────────────

    async def _ensure_collection(self) -> None:
        if self._collection_ensured:
            return
        try:
            self.qdrant.client.get_collection(HA_EVENTS_COLLECTION)
        except Exception:
            from qdrant_client.http.models import Distance, VectorParams

            self.qdrant.client.create_collection(
                collection_name=HA_EVENTS_COLLECTION,
                vectors_config=VectorParams(
                    size=VECTOR_SIZE,
                    distance=Distance.COSINE,
                ),
                on_disk_payload=True,
            )
            logger.info("Qdrant collection '%s' created", HA_EVENTS_COLLECTION)
        self._collection_ensured = True

    # ── Trigger logic ────────────────────────────────────────────────

    @staticmethod
    def _should_trigger(ev: HAStateEvent) -> bool:
        domain = ev.entity_id.split(".")[0]
        if domain in _TRIGGER_DOMAINS:
            if domain == "binary_sensor" and ev.new_state == "on":
                return True
            if domain == "alarm_control_panel":
                return True
        return False

    # ── Search helper (used by orchestrator) ─────────────────────────

    async def search_recent_events(
        self,
        query_text: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Semantic search over the ``ha_events`` collection."""
        if not self.embedding or not self.qdrant.enabled:
            return []

        await self._ensure_collection()
        vector = await self.embedding.encode(query_text)

        try:
            results = self.qdrant.client.query_points(
                collection_name=HA_EVENTS_COLLECTION,
                query=vector,
                limit=limit,
            )
            return [
                {
                    "entity_id": p.payload.get("entity_id", ""),
                    "old_state": p.payload.get("old_state", ""),
                    "new_state": p.payload.get("new_state", ""),
                    "friendly_name": p.payload.get("friendly_name", ""),
                    "area": p.payload.get("area", ""),
                    "timestamp": p.payload.get("timestamp", ""),
                    "text": p.payload.get("text", ""),
                    "score": p.score,
                }
                for p in results.points
            ]
        except Exception as exc:
            logger.error("ha_events search failed: %s", exc)
            return []
