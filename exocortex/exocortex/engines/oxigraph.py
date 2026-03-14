"""Oxigraph SPARQL client via HTTP."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from exocortex.core.markdown_parser import ParsedNote
from exocortex.core.rdf_emitter import (
    ONTOLOGY_TURTLE,
    build_sparql_delete,
    build_sparql_insert,
    note_to_triples,
)

logger = logging.getLogger(__name__)


class OxigraphEngine:
    """Oxigraph SPARQL store client via HTTP."""

    def __init__(self, url: str = "http://127.0.0.1:7878"):
        self.url = url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def ensure_ontology(self):
        """Load the base ontology if not already present."""
        # Check if ontology exists
        result = await self.sparql_query(
            "ASK { <http://exocortex.local/ontology#Note> a <http://www.w3.org/2000/01/rdf-schema#Class> }"
        )
        if result and result.get("boolean") is True:
            return

        # Load ontology
        await self.load_turtle(ONTOLOGY_TURTLE)
        logger.info("Oxigraph ontology loaded")

    async def sparql_query(self, query: str) -> dict[str, Any]:
        """Execute a SPARQL SELECT/ASK query."""
        try:
            resp = await self.client.post(
                f"{self.url}/query",
                content=query,
                headers={
                    "Content-Type": "application/sparql-query",
                    "Accept": "application/sparql-results+json",
                },
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error("SPARQL query failed: %s", e)
            return {}

    async def sparql_update(self, update: str):
        """Execute a SPARQL UPDATE (INSERT/DELETE)."""
        try:
            resp = await self.client.post(
                f"{self.url}/update",
                content=update,
                headers={"Content-Type": "application/sparql-update"},
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error("SPARQL update failed: %s — query: %s", e, update[:200])

    async def load_turtle(self, turtle: str):
        """Load Turtle data into the store."""
        try:
            resp = await self.client.post(
                f"{self.url}/store",
                content=turtle,
                headers={"Content-Type": "text/turtle"},
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error("Turtle load failed: %s", e)

    async def upsert(self, path: str, note: ParsedNote):
        """Delete existing triples for a note and insert new ones."""
        await self.sparql_update(build_sparql_delete(path))
        await self.sparql_update(build_sparql_insert(path, note))

    async def delete(self, path: str):
        """Delete all triples for a note."""
        await self.sparql_update(build_sparql_delete(path))

    async def get_backlinks(self, path: str) -> list[dict[str, str]]:
        """Get all notes that link to the given path."""
        from urllib.parse import quote
        note_uri = f"http://exocortex.local/note/{quote(path, safe='/')}"
        query = f"""
        SELECT ?source ?title WHERE {{
            ?source <http://exocortex.local/ontology#linksTo> <{note_uri}> ;
                    <http://schema.org/name> ?title .
        }}
        """
        result = await self.sparql_query(query)
        bindings = result.get("results", {}).get("bindings", [])
        return [
            {
                "path": b["source"]["value"].replace("http://exocortex.local/note/", ""),
                "title": b["title"]["value"],
            }
            for b in bindings
        ]

    async def get_neighbors(self, path: str, depth: int = 2) -> dict[str, Any]:
        """Get local subgraph around a note."""
        from urllib.parse import quote
        note_uri = f"http://exocortex.local/note/{quote(path, safe='/')}"

        if depth <= 1:
            query = f"""
            SELECT DISTINCT ?s ?p ?o ?title WHERE {{
                {{
                    <{note_uri}> <http://exocortex.local/ontology#linksTo> ?o .
                    ?o <http://schema.org/name> ?title .
                    BIND(<{note_uri}> AS ?s)
                    BIND(<http://exocortex.local/ontology#linksTo> AS ?p)
                }} UNION {{
                    ?s <http://exocortex.local/ontology#linksTo> <{note_uri}> ;
                       <http://schema.org/name> ?title .
                    BIND(<{note_uri}> AS ?o)
                    BIND(<http://exocortex.local/ontology#linksTo> AS ?p)
                }}
            }}
            """
        else:
            query = f"""
            SELECT DISTINCT ?source ?target WHERE {{
                {{
                    <{note_uri}> <http://exocortex.local/ontology#linksTo> ?target .
                }} UNION {{
                    ?source <http://exocortex.local/ontology#linksTo> <{note_uri}> .
                    BIND(<{note_uri}> AS ?target)
                }} UNION {{
                    <{note_uri}> <http://exocortex.local/ontology#linksTo> ?mid .
                    ?mid <http://exocortex.local/ontology#linksTo> ?target .
                    BIND(?mid AS ?source)
                }}
            }}
            """

        result = await self.sparql_query(query)
        bindings = result.get("results", {}).get("bindings", [])

        nodes_set: set[str] = {path}
        edges: list[dict[str, str]] = []

        for b in bindings:
            if "source" in b and "target" in b:
                src = b["source"]["value"].replace("http://exocortex.local/note/", "")
                tgt = b["target"]["value"].replace("http://exocortex.local/note/", "")
                nodes_set.add(src)
                nodes_set.add(tgt)
                edges.append({"source": src, "target": tgt, "type": "wikilink"})
            elif "s" in b and "o" in b:
                src = b["s"]["value"].replace("http://exocortex.local/note/", "")
                tgt = b["o"]["value"].replace("http://exocortex.local/note/", "")
                nodes_set.add(src)
                nodes_set.add(tgt)
                edges.append({"source": src, "target": tgt, "type": "wikilink"})

        nodes = [{"id": n, "title": n} for n in nodes_set]
        return {"nodes": nodes, "edges": edges}

    async def get_full_graph(self) -> dict[str, Any]:
        """Get the entire link graph."""
        query = """
        SELECT ?source ?target WHERE {
            ?source <http://exocortex.local/ontology#linksTo> ?target .
        }
        """
        result = await self.sparql_query(query)
        bindings = result.get("results", {}).get("bindings", [])

        nodes_set: set[str] = set()
        edges: list[dict[str, str]] = []

        for b in bindings:
            src = b["source"]["value"].replace("http://exocortex.local/note/", "")
            tgt = b["target"]["value"].replace("http://exocortex.local/note/", "")
            nodes_set.add(src)
            nodes_set.add(tgt)
            edges.append({"source": src, "target": tgt, "type": "wikilink"})

        nodes = [{"id": n, "title": n} for n in nodes_set]
        return {"nodes": nodes, "edges": edges}

    async def get_orphans(self) -> list[dict[str, str]]:
        """Get notes with no incoming links."""
        query = """
        SELECT ?note ?title WHERE {
            ?note a <http://exocortex.local/ontology#Note> ;
                  <http://schema.org/name> ?title .
            FILTER NOT EXISTS { ?other <http://exocortex.local/ontology#linksTo> ?note }
        }
        """
        result = await self.sparql_query(query)
        bindings = result.get("results", {}).get("bindings", [])
        return [
            {
                "path": b["note"]["value"].replace("http://exocortex.local/note/", ""),
                "title": b["title"]["value"],
            }
            for b in bindings
        ]

    async def get_stats(self) -> dict[str, Any]:
        """Get graph statistics."""
        query = """
        SELECT
            (COUNT(DISTINCT ?note) AS ?notes)
            (COUNT(DISTINCT ?link) AS ?links)
        WHERE {
            { ?note a <http://exocortex.local/ontology#Note> }
            UNION
            { ?s <http://exocortex.local/ontology#linksTo> ?link }
        }
        """
        result = await self.sparql_query(query)
        bindings = result.get("results", {}).get("bindings", [])
        if bindings:
            return {
                "status": "ok",
                "triples": int(bindings[0].get("notes", {}).get("value", 0)),
            }
        return {"status": "ok", "triples": 0}

    async def drop_all(self):
        """Delete all triples from the store."""
        await self.sparql_update("DELETE WHERE { ?s ?p ?o }")

    async def health_check(self) -> bool:
        try:
            resp = await self.client.get(f"{self.url}/query", params={"query": "ASK { ?s ?p ?o }"})
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self):
        if self._client:
            await self._client.aclose()
