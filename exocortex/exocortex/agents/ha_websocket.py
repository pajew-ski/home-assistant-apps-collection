"""Persistent WebSocket client for the Home Assistant Event Bus."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import TYPE_CHECKING, Any

import websockets
import websockets.asyncio.client

if TYPE_CHECKING:
    from exocortex.agents.event_filter import EventFilter

logger = logging.getLogger(__name__)

_INITIAL_BACKOFF = 1.0
_MAX_BACKOFF = 60.0
_MSG_ID_COUNTER_START = 1


async def run_ha_websocket(config: Any, event_filter: EventFilter) -> None:
    """Connect to the HA WebSocket API and stream ``state_changed`` events to
    *event_filter*.  Reconnects with exponential backoff on failure."""

    url: str = getattr(config, "ha_websocket_url", "ws://supervisor/core/websocket")
    token: str = (
        getattr(config, "ha_supervisor_token", "")
        or os.environ.get("SUPERVISOR_TOKEN", "")
    )

    backoff = _INITIAL_BACKOFF

    while True:
        try:
            await _ws_session(url, token, event_filter)
            # If _ws_session returns cleanly we still reconnect
            backoff = _INITIAL_BACKOFF
        except asyncio.CancelledError:
            logger.info("HA WebSocket task cancelled")
            return
        except Exception as exc:
            logger.warning("HA WebSocket error (%s), retrying in %.0fs", exc, backoff)

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, _MAX_BACKOFF)


async def _ws_session(url: str, token: str, event_filter: EventFilter) -> None:
    """Run a single WebSocket session end-to-end."""
    msg_id = _MSG_ID_COUNTER_START

    async with websockets.asyncio.client.connect(url) as ws:
        # 1. Wait for auth_required
        raw = await ws.recv()
        msg = json.loads(raw)
        if msg.get("type") != "auth_required":
            logger.error("Unexpected first message: %s", msg.get("type"))
            return

        # 2. Authenticate
        await ws.send(json.dumps({"type": "auth", "access_token": token}))
        raw = await ws.recv()
        msg = json.loads(raw)
        if msg.get("type") != "auth_ok":
            logger.error("HA auth failed: %s", msg)
            return
        logger.info("HA WebSocket authenticated (HA version %s)", msg.get("ha_version"))

        # 3. Declare supported features
        await ws.send(json.dumps({
            "id": msg_id,
            "type": "supported_features",
            "features": {"coalesce_messages": 1},
        }))
        msg_id += 1
        await ws.recv()  # ack

        # 4. Subscribe to state_changed events
        await ws.send(json.dumps({
            "id": msg_id,
            "type": "subscribe_events",
            "event_type": "state_changed",
        }))
        msg_id += 1
        raw = await ws.recv()
        sub_resp = json.loads(raw)
        if not sub_resp.get("success"):
            logger.error("subscribe_events failed: %s", sub_resp)
            return
        logger.info("Subscribed to state_changed events")

        # 5. Event loop
        async for raw in ws:
            try:
                msg = json.loads(raw)
                if msg.get("type") == "event":
                    await event_filter.handle_event(msg.get("event", {}))
            except Exception as exc:
                logger.error("Error processing WS message: %s", exc)
