"""Client for executing Home Assistant actions via the Supervisor REST API."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

HA_SUPERVISOR_BASE = "http://supervisor/core/api"


class HaMcpClient:
    """Calls Home Assistant services through the Supervisor proxy.

    If ``ha_mcp_url`` were configured we could speak MCP, but for now we fall
    back to the well-documented REST API available inside the add-on container.
    """

    def __init__(self, token: str = ""):
        self.token = token or os.environ.get("SUPERVISOR_TOKEN", "")
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=HA_SUPERVISOR_BASE,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(30.0, connect=10.0),
            )
        return self._client

    # ── Service calls ────────────────────────────────────────────────

    async def call_service(
        self,
        domain: str,
        service: str,
        entity_id: str,
        data: dict[str, Any] | None = None,
    ) -> bool:
        """Call a Home Assistant service.  Returns ``True`` on success."""
        payload: dict[str, Any] = {"entity_id": entity_id}
        if data:
            payload.update(data)

        try:
            resp = await self.client.post(
                f"/services/{domain}/{service}",
                json=payload,
            )
            resp.raise_for_status()
            logger.info("HA service %s.%s called for %s", domain, service, entity_id)
            return True
        except httpx.HTTPStatusError as exc:
            logger.error(
                "HA service call failed (%s): %s",
                exc.response.status_code,
                exc.response.text[:300],
            )
            return False
        except Exception as exc:
            logger.error("HA service call error: %s", exc)
            return False

    # ── State queries ────────────────────────────────────────────────

    async def get_state(self, entity_id: str) -> dict[str, Any]:
        """Get current state of an entity via the REST API."""
        try:
            resp = await self.client.get(f"/states/{entity_id}")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error("get_state(%s) failed: %s", entity_id, exc)
            return {}

    async def get_area_entities(self, area_id: str) -> list[dict[str, Any]]:
        """Get all entities in a given area.

        The REST API does not expose a direct area→entities endpoint so we
        fetch all states and filter client-side by the ``area_id`` attribute
        that the Supervisor injects.
        """
        try:
            resp = await self.client.get("/states")
            resp.raise_for_status()
            states: list[dict[str, Any]] = resp.json()
            return [
                s
                for s in states
                if s.get("attributes", {}).get("area_id") == area_id
            ]
        except Exception as exc:
            logger.error("get_area_entities(%s) failed: %s", area_id, exc)
            return []

    # ── Health ───────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Return ``True`` if the HA API is reachable."""
        try:
            resp = await self.client.get("/")
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
