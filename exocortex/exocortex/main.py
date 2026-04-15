"""Exocortex — FastAPI application entry point."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from exocortex.config import Config, load_config
from exocortex.core.embedding import EmbeddingEngine
from exocortex.core.git_manager import GitManager
from exocortex.core.index_pipeline import IndexEvent, IndexPipeline
from exocortex.core.search_engine import SearchEngine
from exocortex.engines.meilisearch import MeiliSearchEngine
from exocortex.engines.oxigraph import OxigraphEngine
from exocortex.engines.qdrant import QdrantEngine
from exocortex.engines.redis_client import RedisEngine

logger = logging.getLogger(__name__)


@dataclass
class AppState:
    config: Config
    redis: RedisEngine
    meilisearch: MeiliSearchEngine
    qdrant: QdrantEngine
    oxigraph: OxigraphEngine
    embedding: EmbeddingEngine | None
    git: GitManager
    pipeline: IndexPipeline
    search_engine: SearchEngine
    agent_system: dict[str, Any] | None = None


app_state: AppState = None  # type: ignore[assignment]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize all services on startup, clean up on shutdown."""
    global app_state

    config = load_config()
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    logger.info("Starting Exocortex v1.0.0...")

    # Initialize engines
    redis = RedisEngine(config.redis_url)
    meilisearch = MeiliSearchEngine(config.meilisearch_url, config.meilisearch_master_key)
    qdrant = QdrantEngine(config.qdrant_url, enabled=config.enable_semantic_search)
    oxigraph = OxigraphEngine(config.oxigraph_url)

    # Embedding engine
    embedding = None
    if config.enable_semantic_search:
        embedding = EmbeddingEngine(
            config.embedding_model,
            str(config.models_path),
            redis=redis,
        )

    # Git manager
    git = GitManager(config.repo_path, config.github_branch, config.auto_push)

    # Index pipeline
    pipeline = IndexPipeline(
        repo_path=config.repo_path,
        meilisearch=meilisearch,
        qdrant=qdrant,
        oxigraph=oxigraph,
        redis=redis,
        embedding_engine=embedding,
    )

    # Search engine
    search_engine = SearchEngine(meilisearch, qdrant, embedding)

    app_state = AppState(
        config=config,
        redis=redis,
        meilisearch=meilisearch,
        qdrant=qdrant,
        oxigraph=oxigraph,
        embedding=embedding,
        git=git,
        pipeline=pipeline,
        search_engine=search_engine,
    )

    # Initialize engines
    try:
        await meilisearch.ensure_index()
        logger.info("MeiliSearch index ready")
    except Exception as e:
        logger.error("MeiliSearch init failed: %s", e)

    try:
        await qdrant.ensure_collection()
        logger.info("Qdrant collection ready")
    except Exception as e:
        logger.error("Qdrant init failed: %s", e)

    try:
        await oxigraph.ensure_ontology()
        logger.info("Oxigraph ontology ready")
    except Exception as e:
        logger.error("Oxigraph init failed: %s", e)

    logger.info("Exocortex ready. Repo: %s", config.repo_path)

    # ── Agent system ─────────────────────────────────────────────────
    agent_tasks: list[asyncio.Task] = []
    if config.enable_agents:
        try:
            from exocortex.agents.event_filter import EventFilter
            from exocortex.agents.ha_mcp_client import HaMcpClient
            from exocortex.agents.ha_websocket import run_ha_websocket
            from exocortex.agents.knoten_k import MetaObserver
            from exocortex.agents.llm_client import OllamaClient
            from exocortex.agents.orchestrator import Orchestrator

            llm = OllamaClient(
                config.ollama_url,
                config.ollama_model,
                config.agent_context_window_tokens,
            )
            mcp_client = HaMcpClient(config.ha_supervisor_token)
            meta_observer = MetaObserver(oxigraph, redis)

            trigger_queue: asyncio.Queue = asyncio.Queue()
            event_filter = EventFilter(
                config=config,
                redis=redis,
                qdrant=qdrant,
                oxigraph=oxigraph,
                embedding=embedding,
                trigger_queue=trigger_queue,
            )
            orchestrator = Orchestrator(
                config=config,
                llm=llm,
                mcp=mcp_client,
                redis=redis,
                qdrant=qdrant,
                oxigraph=oxigraph,
                embedding=embedding,
                event_filter=event_filter,
                meta_observer=meta_observer,
                trigger_queue=trigger_queue,
            )

            ws_task = asyncio.create_task(
                run_ha_websocket(config, event_filter), name="ha_websocket",
            )
            orch_task = asyncio.create_task(
                orchestrator.run(), name="orchestrator",
            )
            agent_tasks = [ws_task, orch_task]

            app_state.agent_system = {
                "ws_task": ws_task,
                "orch_task": orch_task,
                "orchestrator": orchestrator,
                "event_filter": event_filter,
                "meta_observer": meta_observer,
                "llm": llm,
                "mcp": mcp_client,
                "trigger_queue": trigger_queue,
            }
            logger.info("Agent system started")
        except Exception as exc:
            logger.error("Agent system init failed: %s", exc, exc_info=True)

    yield

    # Shutdown
    logger.info("Shutting down Exocortex...")
    for t in agent_tasks:
        t.cancel()
    if agent_tasks:
        await asyncio.gather(*agent_tasks, return_exceptions=True)
    await oxigraph.close()
    await redis.close()


app = FastAPI(
    title="Exocortex",
    version="1.0.0",
    description="Knowledge Operating System for Home Assistant",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
from exocortex.api import agents as agents_api
from exocortex.api import graph, memory, notes, search, sync, system

app.include_router(search.router, prefix="/api")
app.include_router(notes.router, prefix="/api")
app.include_router(graph.router, prefix="/api")
app.include_router(sync.router, prefix="/api")
app.include_router(memory.router, prefix="/api")
app.include_router(system.router, prefix="/api")
app.include_router(agents_api.router, prefix="/api")


@app.post("/api/internal/index-event")
async def internal_index_event(event: dict[str, Any]):
    """Internal endpoint for the sync daemon to trigger indexing."""
    await app_state.pipeline.process_event(
        IndexEvent(action=event["action"], path=event["path"])
    )
    return {"status": "ok"}


@app.get("/")
async def root():
    """Root endpoint — redirect to docs or return basic info."""
    return {"name": "Exocortex", "version": "1.0.0", "docs": "/docs"}
