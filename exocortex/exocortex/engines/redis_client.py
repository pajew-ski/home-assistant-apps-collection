"""Redis client for agent memory, caching, and pub/sub."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class RedisEngine:
    """Redis client for caching, agent memory, and pub/sub."""

    def __init__(self, url: str = "redis://127.0.0.1:6379"):
        self.url = url
        self._client: aioredis.Redis | None = None

    @property
    def client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(self.url, decode_responses=False)
        return self._client

    def _text_client(self) -> aioredis.Redis:
        return aioredis.from_url(self.url, decode_responses=True)

    # ── Raw bytes operations (for embedding cache) ────────────────────

    async def get_raw(self, key: str) -> bytes | None:
        return await self.client.get(key)

    async def set_raw(self, key: str, value: bytes, expire: int | None = None):
        if expire:
            await self.client.setex(key, expire, value)
        else:
            await self.client.set(key, value)

    # ── JSON operations ──────────────────────────────────────────────

    async def get_json(self, key: str) -> Any:
        data = await self.client.get(key)
        if data:
            return json.loads(data)
        return None

    async def set_json(self, key: str, value: Any, expire: int | None = None):
        data = json.dumps(value)
        if expire:
            await self.client.setex(key, expire, data.encode())
        else:
            await self.client.set(key, data.encode())

    # ── Pub/Sub ──────────────────────────────────────────────────────

    async def publish(self, channel: str, data: dict[str, Any]):
        await self.client.publish(channel, json.dumps(data).encode())

    async def publish_note_change(self, action: str, path: str):
        await self.publish("channel:notes:changed", {
            "action": action,
            "path": path,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def publish_sync_status(self, state: str, sha: str = "", pending: int = 0):
        await self.publish("channel:sync:status", {
            "state": state,
            "sha": sha,
            "pending": pending,
        })

    def get_pubsub(self):
        return self.client.pubsub()

    # ── Agent Memory: Facts ──────────────────────────────────────────

    async def store_fact(
        self,
        agent_id: str,
        fact: str,
        confidence: float = 0.8,
        source: str = "",
        tags: list[str] | None = None,
        ttl_days: int | None = None,
    ):
        key = f"agent:memory:{agent_id}:facts"
        entry = json.dumps({
            "fact": fact,
            "confidence": confidence,
            "source": source,
            "tags": tags or [],
            "created": datetime.now(timezone.utc).isoformat(),
        })
        await self.client.zadd(key, {entry.encode(): confidence})
        if ttl_days:
            # Individual fact TTL via a separate expiry key
            fact_key = f"agent:memory:{agent_id}:fact_ttl:{hash(fact) & 0xFFFFFFFF}"
            await self.client.setex(fact_key, ttl_days * 86400, entry.encode())

    async def get_facts(
        self,
        agent_id: str,
        limit: int = 10,
        min_confidence: float = 0.0,
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        key = f"agent:memory:{agent_id}:facts"
        raw_facts = await self.client.zrangebyscore(
            key, min=min_confidence, max="+inf",
            start=0, num=limit * 3,  # Fetch extra for filtering
        )

        facts = []
        for raw in raw_facts:
            entry = json.loads(raw)
            if tags:
                if not any(t in entry.get("tags", []) for t in tags):
                    continue
            facts.append(entry)
            if len(facts) >= limit:
                break

        return facts

    async def delete_facts(self, agent_id: str, older_than: str | None = None):
        key = f"agent:memory:{agent_id}:facts"
        if older_than:
            cutoff = datetime.fromisoformat(older_than.replace("Z", "+00:00"))
            all_facts = await self.client.zrange(key, 0, -1)
            for raw in all_facts:
                entry = json.loads(raw)
                created = datetime.fromisoformat(entry["created"].replace("Z", "+00:00"))
                if created < cutoff:
                    await self.client.zrem(key, raw)
        else:
            await self.client.delete(key)

    # ── Agent Memory: Conversations ──────────────────────────────────

    async def store_conversation(self, agent_id: str, role: str, content: str, metadata: dict | None = None):
        key = f"agent:memory:{agent_id}:conversations"
        entry = json.dumps({
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        await self.client.rpush(key, entry.encode())
        # Trim to last 1000 messages
        await self.client.ltrim(key, -1000, -1)

    async def get_conversations(self, agent_id: str, limit: int = 50) -> list[dict[str, Any]]:
        key = f"agent:memory:{agent_id}:conversations"
        raw = await self.client.lrange(key, -limit, -1)
        return [json.loads(r) for r in raw]

    # ── Agent Memory: Working Memory ─────────────────────────────────

    async def set_working_memory(self, agent_id: str, session_id: str, data: dict):
        key = f"agent:working:{agent_id}:{session_id}"
        await self.client.setex(key, 86400, json.dumps(data).encode())  # 24h TTL

    async def get_working_memory(self, agent_id: str, session_id: str) -> dict | None:
        key = f"agent:working:{agent_id}:{session_id}"
        data = await self.client.get(key)
        return json.loads(data) if data else None

    # ── System State ─────────────────────────────────────────────────

    async def set_last_sync_sha(self, sha: str):
        await self.client.set(b"system:last_sync_sha", sha.encode())

    async def get_last_sync_sha(self) -> str:
        val = await self.client.get(b"system:last_sync_sha")
        return val.decode() if val else ""

    async def set_system_stats(self, stats: dict[str, Any]):
        tc = self._text_client()
        try:
            await tc.hset("system:stats", mapping={k: json.dumps(v) for k, v in stats.items()})
        finally:
            await tc.aclose()

    async def get_system_stats(self) -> dict[str, Any]:
        tc = self._text_client()
        try:
            raw = await tc.hgetall("system:stats")
            return {k: json.loads(v) for k, v in raw.items()}
        except Exception:
            return {}
        finally:
            await tc.aclose()

    # ── Health & Stats ───────────────────────────────────────────────

    async def get_stats(self) -> dict[str, Any]:
        try:
            info = await self.client.info("memory")
            return {
                "status": "ok",
                "used_memory_mb": round(info.get("used_memory", 0) / 1024 / 1024, 2),
                "keys": await self.client.dbsize(),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def health_check(self) -> bool:
        try:
            return await self.client.ping()
        except Exception:
            return False

    async def close(self):
        if self._client:
            await self._client.aclose()
