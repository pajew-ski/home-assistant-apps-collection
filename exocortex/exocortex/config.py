"""Configuration management — loads from environment variables set by s6-overlay."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    # Git
    github_repo: str = ""
    github_token: str = ""
    github_branch: str = "main"
    auto_push: bool = True

    # Sync
    sync_interval_minutes: int = 5
    webhook_secret: str = ""

    # Search
    enable_semantic_search: bool = True
    embedding_model: str = "all-MiniLM-L6-v2"

    # Services
    meilisearch_url: str = "http://127.0.0.1:7700"
    meilisearch_master_key: str = ""
    qdrant_url: str = "http://127.0.0.1:6333"
    oxigraph_url: str = "http://127.0.0.1:7878"
    redis_url: str = "redis://127.0.0.1:6379"
    redis_password: str = ""

    # Paths
    repo_path: Path = field(default_factory=lambda: Path("/data/repo"))
    data_path: Path = field(default_factory=lambda: Path("/data"))
    models_path: Path = field(default_factory=lambda: Path("/opt/exocortex/models"))

    # Logging
    log_level: str = "info"

    # Home Assistant connection
    ha_websocket_url: str = "ws://supervisor/core/websocket"
    ha_supervisor_token: str = ""  # read from SUPERVISOR_TOKEN env var at runtime
    ollama_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "llama3.2"
    ha_mcp_url: str = ""

    # Agent system
    enable_agents: bool = True
    agent_filter_domains: list[str] = field(default_factory=lambda: [
        "light", "switch", "climate", "binary_sensor",
        "sensor", "cover", "lock", "alarm_control_panel",
    ])
    agent_filter_min_change_interval_seconds: int = 5
    agent_context_window_tokens: int = 4096

    @classmethod
    def from_env(cls) -> Config:
        """Load configuration from environment variables (set by init.sh)."""
        redis_password = os.environ.get("REDIS_PASSWORD", "")
        redis_url = "redis://127.0.0.1:6379"
        if redis_password:
            redis_url = f"redis://:{redis_password}@127.0.0.1:6379"

        # Agent filter domains
        domains_raw = os.environ.get("AGENT_FILTER_DOMAINS", "")
        agent_domains = (
            [d.strip() for d in domains_raw.split(",") if d.strip()]
            if domains_raw
            else [
                "light", "switch", "climate", "binary_sensor",
                "sensor", "cover", "lock", "alarm_control_panel",
            ]
        )

        return cls(
            github_repo=os.environ.get("GITHUB_REPO", ""),
            github_token=os.environ.get("GITHUB_TOKEN", ""),
            github_branch=os.environ.get("GITHUB_BRANCH", "main"),
            auto_push=os.environ.get("AUTO_PUSH", "true").lower() == "true",
            sync_interval_minutes=int(os.environ.get("SYNC_INTERVAL_MINUTES", "5")),
            webhook_secret=os.environ.get("WEBHOOK_SECRET", ""),
            enable_semantic_search=os.environ.get("ENABLE_SEMANTIC_SEARCH", "true").lower() == "true",
            embedding_model=os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
            meilisearch_master_key=os.environ.get("MEILI_MASTER_KEY", ""),
            redis_password=redis_password,
            redis_url=redis_url,
            log_level=os.environ.get("LOG_LEVEL", "info"),
            ha_websocket_url=os.environ.get("HA_WEBSOCKET_URL", "ws://supervisor/core/websocket"),
            ha_supervisor_token=os.environ.get("SUPERVISOR_TOKEN", ""),
            ollama_url=os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434"),
            ollama_model=os.environ.get("OLLAMA_MODEL", "llama3.2"),
            ha_mcp_url=os.environ.get("HA_MCP_URL", ""),
            enable_agents=os.environ.get("ENABLE_AGENTS", "true").lower() == "true",
            agent_filter_domains=agent_domains,
            agent_filter_min_change_interval_seconds=int(
                os.environ.get("AGENT_FILTER_MIN_CHANGE_INTERVAL_SECONDS", "5")
            ),
            agent_context_window_tokens=int(
                os.environ.get("AGENT_CONTEXT_WINDOW_TOKENS", "4096")
            ),
        )

    @classmethod
    def from_options_json(cls, path: str = "/data/options.json") -> Config:
        """Fallback: load directly from HA options.json."""
        try:
            with open(path) as f:
                opts = json.load(f)
        except FileNotFoundError:
            return cls.from_env()

        redis_password = opts.get("redis_password", "")
        redis_url = "redis://127.0.0.1:6379"
        if redis_password:
            redis_url = f"redis://:{redis_password}@127.0.0.1:6379"

        return cls(
            github_repo=opts.get("github_repo", ""),
            github_token=opts.get("github_token", ""),
            github_branch=opts.get("github_branch", "main"),
            auto_push=opts.get("auto_push", True),
            sync_interval_minutes=opts.get("sync_interval_minutes", 5),
            webhook_secret=opts.get("webhook_secret", ""),
            enable_semantic_search=opts.get("enable_semantic_search", True),
            embedding_model=opts.get("embedding_model", "all-MiniLM-L6-v2"),
            meilisearch_master_key=opts.get("meilisearch_master_key", ""),
            redis_password=redis_password,
            redis_url=redis_url,
            log_level=opts.get("log_level", "info"),
            ha_websocket_url=opts.get("ha_websocket_url", "ws://supervisor/core/websocket"),
            ha_supervisor_token=os.environ.get("SUPERVISOR_TOKEN", ""),
            ollama_url=opts.get("ollama_url", "http://host.docker.internal:11434"),
            ollama_model=opts.get("ollama_model", "llama3.2"),
            ha_mcp_url=opts.get("ha_mcp_url", ""),
            enable_agents=opts.get("enable_agents", True),
            agent_filter_domains=opts.get("agent_filter_domains", [
                "light", "switch", "climate", "binary_sensor",
                "sensor", "cover", "lock", "alarm_control_panel",
            ]),
            agent_filter_min_change_interval_seconds=opts.get(
                "agent_filter_min_change_interval_seconds", 5,
            ),
            agent_context_window_tokens=opts.get("agent_context_window_tokens", 4096),
        )


def load_config() -> Config:
    """Load config, preferring env vars (set by s6 init), falling back to options.json."""
    if os.environ.get("GITHUB_REPO"):
        return Config.from_env()
    return Config.from_options_json()
