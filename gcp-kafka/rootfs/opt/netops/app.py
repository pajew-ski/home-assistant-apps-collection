"""
Telecom NetOps Platform – FastAPI Dashboard & API

Integrates all platform components:
- Apache Kafka: telemetry ingestion and event streaming
- Apache Spark: stream processing and analytics
- OpenCV: visual infrastructure inspection (cell tower, cable plant)
- Neo4j: network topology graph / digital twin
- OPA: policy enforcement and governance
- LLM + MCP: autonomous network optimization
"""

import os
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime

import cv2
import httpx
import numpy as np
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("netops")

# ---------------------------------------------------------------------------
# Configuration from environment (set by s6 run script from HA options)
# ---------------------------------------------------------------------------
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "127.0.0.1:9092")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j")
OPA_URL = os.getenv("OPA_URL", "http://127.0.0.1:8181")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_API_URL = os.getenv("LLM_API_URL", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")

# ---------------------------------------------------------------------------
# Lazy-loaded clients (initialized after services are ready)
# ---------------------------------------------------------------------------
kafka_producer = None
neo4j_driver = None


def get_kafka_producer():
    global kafka_producer
    if kafka_producer is None:
        try:
            from confluent_kafka import Producer
            kafka_producer = Producer({"bootstrap.servers": KAFKA_BROKER})
        except Exception as e:
            logger.warning("Kafka producer init failed: %s", e)
    return kafka_producer


def get_neo4j_driver():
    global neo4j_driver
    if neo4j_driver is None:
        try:
            from neo4j import GraphDatabase
            neo4j_driver = GraphDatabase.driver(
                NEO4J_URI, auth=("neo4j", NEO4J_PASSWORD)
            )
        except Exception as e:
            logger.warning("Neo4j driver init failed: %s", e)
    return neo4j_driver


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("NetOps API starting...")
    yield
    if neo4j_driver:
        neo4j_driver.close()
    logger.info("NetOps API stopped.")


app = FastAPI(title="Telecom NetOps Platform", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Dashboard (served at ingress root)
# ---------------------------------------------------------------------------
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Telecom NetOps Platform</title>
<style>
  :root { --bg: #0f172a; --card: #1e293b; --accent: #38bdf8; --text: #e2e8f0;
          --green: #22c55e; --red: #ef4444; --yellow: #eab308; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: var(--bg); color: var(--text); }
  .header { padding: 1.5rem 2rem; border-bottom: 1px solid #334155;
            display: flex; align-items: center; gap: 1rem; }
  .header h1 { font-size: 1.5rem; font-weight: 600; }
  .header .subtitle { color: #94a3b8; font-size: 0.875rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
          gap: 1.25rem; padding: 1.5rem 2rem; }
  .card { background: var(--card); border-radius: 12px; padding: 1.25rem;
          border: 1px solid #334155; }
  .card h2 { font-size: 1rem; font-weight: 600; margin-bottom: 0.75rem;
             display: flex; align-items: center; gap: 0.5rem; }
  .card h2 .icon { font-size: 1.25rem; }
  .status-row { display: flex; justify-content: space-between; align-items: center;
                padding: 0.4rem 0; border-bottom: 1px solid #334155; font-size: 0.875rem; }
  .status-row:last-child { border-bottom: none; }
  .badge { padding: 0.15rem 0.6rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; }
  .badge-green { background: rgba(34,197,94,0.15); color: var(--green); }
  .badge-red { background: rgba(239,68,68,0.15); color: var(--red); }
  .badge-yellow { background: rgba(234,179,8,0.15); color: var(--yellow); }
  .metric { text-align: center; padding: 0.75rem; }
  .metric .value { font-size: 2rem; font-weight: 700; color: var(--accent); }
  .metric .label { font-size: 0.75rem; color: #94a3b8; margin-top: 0.25rem; }
  .metrics-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5rem; }
  #log-output { background: #0f172a; border: 1px solid #334155; border-radius: 8px;
                padding: 0.75rem; font-family: monospace; font-size: 0.8rem;
                max-height: 200px; overflow-y: auto; color: #94a3b8; }
  button { background: var(--accent); color: var(--bg); border: none; padding: 0.5rem 1rem;
           border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 0.85rem; }
  button:hover { opacity: 0.9; }
  .btn-row { display: flex; gap: 0.5rem; margin-top: 0.75rem; }
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>Telecom NetOps Platform</h1>
    <div class="subtitle">Real-time network operations &middot; Graph-based digital twin &middot; AI-powered optimization</div>
  </div>
</div>
<div class="grid">
  <div class="card">
    <h2><span class="icon">&#9881;</span> Service Status</h2>
    <div id="services">Loading...</div>
  </div>
  <div class="card">
    <h2><span class="icon">&#128202;</span> Platform Metrics</h2>
    <div class="metrics-row" id="metrics">
      <div class="metric"><div class="value">--</div><div class="label">Kafka Topics</div></div>
      <div class="metric"><div class="value">--</div><div class="label">Neo4j Nodes</div></div>
      <div class="metric"><div class="value">--</div><div class="label">OPA Policies</div></div>
    </div>
  </div>
  <div class="card">
    <h2><span class="icon">&#128268;</span> Network Topology</h2>
    <p style="font-size:0.875rem;color:#94a3b8;">Graph-based digital twin of network infrastructure.</p>
    <div class="btn-row">
      <button onclick="loadTopology()">Load Topology</button>
      <button onclick="seedDemo()">Seed Demo Data</button>
    </div>
    <div id="topology-info" style="margin-top:0.75rem;font-size:0.85rem;"></div>
  </div>
  <div class="card">
    <h2><span class="icon">&#129302;</span> AI Agent (MCP + LLM)</h2>
    <p style="font-size:0.875rem;color:#94a3b8;margin-bottom:0.5rem;">
      Context-aware autonomous network optimization.</p>
    <input id="agent-input" type="text" placeholder="Ask the agent..."
           style="width:100%;padding:0.5rem;border-radius:6px;border:1px solid #334155;
                  background:#0f172a;color:var(--text);font-size:0.85rem;">
    <div class="btn-row">
      <button onclick="askAgent()">Send</button>
    </div>
    <div id="agent-output" style="margin-top:0.75rem;font-size:0.85rem;color:#94a3b8;"></div>
  </div>
  <div class="card" style="grid-column: 1 / -1;">
    <h2><span class="icon">&#128220;</span> Event Log</h2>
    <div id="log-output">Waiting for events...</div>
  </div>
</div>
<script>
const BASE = window.location.pathname.replace(/\\/$/, '');
async function api(path, opts) {
  const res = await fetch(BASE + path, opts);
  return res.json();
}
async function refreshStatus() {
  try {
    const data = await api('/api/status');
    const el = document.getElementById('services');
    el.innerHTML = Object.entries(data.services).map(([k, v]) =>
      `<div class="status-row"><span>${k}</span>` +
      `<span class="badge ${v === 'healthy' ? 'badge-green' : v === 'degraded' ? 'badge-yellow' : 'badge-red'}">${v}</span></div>`
    ).join('');
    const m = document.getElementById('metrics');
    m.innerHTML = `
      <div class="metric"><div class="value">${data.metrics.kafka_topics}</div><div class="label">Kafka Topics</div></div>
      <div class="metric"><div class="value">${data.metrics.neo4j_nodes}</div><div class="label">Neo4j Nodes</div></div>
      <div class="metric"><div class="value">${data.metrics.opa_policies}</div><div class="label">OPA Policies</div></div>`;
  } catch(e) { console.error(e); }
}
async function loadTopology() {
  try {
    const data = await api('/api/topology');
    document.getElementById('topology-info').innerText = JSON.stringify(data, null, 2);
  } catch(e) { document.getElementById('topology-info').innerText = 'Error: ' + e; }
}
async function seedDemo() {
  try {
    const data = await api('/api/topology/seed', { method: 'POST' });
    document.getElementById('topology-info').innerText = JSON.stringify(data, null, 2);
    refreshStatus();
  } catch(e) { document.getElementById('topology-info').innerText = 'Error: ' + e; }
}
async function askAgent() {
  const input = document.getElementById('agent-input');
  const output = document.getElementById('agent-output');
  if (!input.value.trim()) return;
  output.innerText = 'Thinking...';
  try {
    const data = await api('/api/agent/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ query: input.value })
    });
    output.innerText = data.response || JSON.stringify(data);
  } catch(e) { output.innerText = 'Error: ' + e; }
}
refreshStatus();
setInterval(refreshStatus, 10000);
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML


# ---------------------------------------------------------------------------
# Status API
# ---------------------------------------------------------------------------
@app.get("/api/status")
async def status():
    services = {}

    # Kafka
    try:
        p = get_kafka_producer()
        if p:
            p.list_topics(timeout=3)
            services["Kafka"] = "healthy"
        else:
            services["Kafka"] = "unavailable"
    except Exception:
        services["Kafka"] = "unavailable"

    # Neo4j
    try:
        d = get_neo4j_driver()
        if d:
            d.verify_connectivity()
            services["Neo4j"] = "healthy"
        else:
            services["Neo4j"] = "unavailable"
    except Exception:
        services["Neo4j"] = "unavailable"

    # OPA
    try:
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{OPA_URL}/health", timeout=3)
            services["OPA"] = "healthy" if r.status_code == 200 else "degraded"
    except Exception:
        services["OPA"] = "unavailable"

    # Spark (local mode – always available if pyspark is installed)
    try:
        import pyspark  # noqa: F401
        services["Spark"] = "healthy"
    except ImportError:
        services["Spark"] = "unavailable"

    # OpenCV
    try:
        services["OpenCV"] = "healthy" if cv2.__version__ else "unavailable"
    except Exception:
        services["OpenCV"] = "unavailable"

    # LLM
    services["LLM Agent"] = "configured" if LLM_API_KEY else "not configured"

    # Metrics
    metrics = {"kafka_topics": 0, "neo4j_nodes": 0, "opa_policies": 0}
    try:
        p = get_kafka_producer()
        if p:
            topics = p.list_topics(timeout=3)
            metrics["kafka_topics"] = len(
                [t for t in topics.topics if not t.startswith("__")]
            )
    except Exception:
        pass

    try:
        d = get_neo4j_driver()
        if d:
            with d.session() as s:
                result = s.run("MATCH (n) RETURN count(n) AS cnt")
                metrics["neo4j_nodes"] = result.single()["cnt"]
    except Exception:
        pass

    try:
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{OPA_URL}/v1/policies", timeout=3)
            if r.status_code == 200:
                policies = r.json().get("result", [])
                metrics["opa_policies"] = len(policies)
    except Exception:
        pass

    return {"services": services, "metrics": metrics, "timestamp": datetime.utcnow().isoformat()}


# ---------------------------------------------------------------------------
# Kafka API
# ---------------------------------------------------------------------------
class KafkaMessage(BaseModel):
    topic: str
    key: str | None = None
    value: dict


@app.post("/api/kafka/produce")
async def kafka_produce(msg: KafkaMessage):
    p = get_kafka_producer()
    if not p:
        raise HTTPException(503, "Kafka not available")
    p.produce(
        msg.topic,
        key=msg.key.encode() if msg.key else None,
        value=json.dumps(msg.value).encode(),
    )
    p.flush(timeout=5)
    return {"status": "produced", "topic": msg.topic}


@app.get("/api/kafka/topics")
async def kafka_topics():
    p = get_kafka_producer()
    if not p:
        raise HTTPException(503, "Kafka not available")
    meta = p.list_topics(timeout=5)
    return {
        "topics": [
            {"name": t, "partitions": len(meta.topics[t].partitions)}
            for t in meta.topics
            if not t.startswith("__")
        ]
    }


# ---------------------------------------------------------------------------
# Neo4j Topology API
# ---------------------------------------------------------------------------
@app.get("/api/topology")
async def get_topology():
    d = get_neo4j_driver()
    if not d:
        raise HTTPException(503, "Neo4j not available")
    with d.session() as s:
        nodes = s.run(
            "MATCH (n) RETURN id(n) AS id, labels(n) AS labels, "
            "properties(n) AS props LIMIT 100"
        ).data()
        edges = s.run(
            "MATCH (a)-[r]->(b) RETURN id(a) AS source, id(b) AS target, "
            "type(r) AS type, properties(r) AS props LIMIT 200"
        ).data()
    return {"nodes": nodes, "edges": edges}


@app.post("/api/topology/seed")
async def seed_topology():
    """Seed demo telecom network topology into Neo4j."""
    d = get_neo4j_driver()
    if not d:
        raise HTTPException(503, "Neo4j not available")

    with d.session() as s:
        s.run("MATCH (n) DETACH DELETE n")
        s.run("""
            CREATE (dc1:DataCenter {name: 'DC-Frankfurt', location: 'Frankfurt', tier: 3})
            CREATE (dc2:DataCenter {name: 'DC-Berlin', location: 'Berlin', tier: 2})
            CREATE (r1:Router {name: 'core-rtr-01', model: 'NCS-5500', ip: '10.0.0.1'})
            CREATE (r2:Router {name: 'core-rtr-02', model: 'NCS-5500', ip: '10.0.0.2'})
            CREATE (r3:Router {name: 'edge-rtr-01', model: 'ASR-9000', ip: '10.1.0.1'})
            CREATE (sw1:Switch {name: 'agg-sw-01', model: 'Nexus-9000', ip: '10.0.1.1'})
            CREATE (sw2:Switch {name: 'agg-sw-02', model: 'Nexus-9000', ip: '10.0.1.2'})
            CREATE (ct1:CellTower {name: 'Tower-FFM-01', lat: 50.1109, lon: 8.6821, band: '5G-NR'})
            CREATE (ct2:CellTower {name: 'Tower-BER-01', lat: 52.5200, lon: 13.4050, band: '5G-NR'})
            CREATE (ct3:CellTower {name: 'Tower-FFM-02', lat: 50.1205, lon: 8.6724, band: 'LTE'})
            CREATE (ep1:Endpoint {name: 'IoT-Gateway-01', type: 'iot', protocol: 'MQTT'})
            CREATE (ep2:Endpoint {name: 'CPE-Customer-01', type: 'cpe', protocol: 'TR-069'})
            CREATE (dc1)-[:HOSTS]->(r1)
            CREATE (dc2)-[:HOSTS]->(r2)
            CREATE (r1)-[:CONNECTS_TO {bandwidth: '100Gbps', latency_ms: 2}]->(r2)
            CREATE (r1)-[:CONNECTS_TO {bandwidth: '40Gbps', latency_ms: 1}]->(sw1)
            CREATE (r2)-[:CONNECTS_TO {bandwidth: '40Gbps', latency_ms: 1}]->(sw2)
            CREATE (r1)-[:CONNECTS_TO {bandwidth: '10Gbps', latency_ms: 5}]->(r3)
            CREATE (r3)-[:SERVES]->(ct1)
            CREATE (r3)-[:SERVES]->(ct3)
            CREATE (sw2)-[:SERVES]->(ct2)
            CREATE (ct1)-[:CONNECTS_TO {signal: '-65dBm'}]->(ep1)
            CREATE (ct2)-[:CONNECTS_TO {signal: '-72dBm'}]->(ep2)
        """)

    # Also create a Kafka topic for telemetry
    try:
        p = get_kafka_producer()
        if p:
            p.produce("network-telemetry", value=json.dumps({
                "event": "topology_seeded",
                "timestamp": datetime.utcnow().isoformat(),
                "nodes_created": 11,
                "edges_created": 10,
            }).encode())
            p.flush(timeout=5)
    except Exception:
        pass

    return {"status": "seeded", "nodes": 11, "edges": 10}


# ---------------------------------------------------------------------------
# OPA Policy API
# ---------------------------------------------------------------------------
class PolicyCheck(BaseModel):
    action: str
    resource: str
    user: dict = {}
    maintenance_mode: bool = False


@app.post("/api/policy/check")
async def check_policy(req: PolicyCheck):
    async with httpx.AsyncClient() as c:
        r = await c.post(
            f"{OPA_URL}/v1/data/telecom/network/allow",
            json={"input": req.model_dump()},
            timeout=5,
        )
        if r.status_code != 200:
            raise HTTPException(502, "OPA query failed")
        return r.json()


# ---------------------------------------------------------------------------
# OpenCV Infrastructure Inspection API
# ---------------------------------------------------------------------------
@app.post("/api/vision/inspect")
async def inspect_infrastructure(file: UploadFile = File(...)):
    """Analyze uploaded infrastructure image using OpenCV."""
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "Invalid image")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    h, w = img.shape[:2]
    analysis = {
        "filename": file.filename,
        "dimensions": {"width": w, "height": h},
        "edge_density": float(np.count_nonzero(edges)) / (h * w),
        "contours_detected": len(contours),
        "mean_intensity": float(np.mean(gray)),
        "std_intensity": float(np.std(gray)),
    }

    # Classify condition based on edge density and intensity variance
    if analysis["edge_density"] > 0.15 and analysis["std_intensity"] > 60:
        analysis["condition"] = "anomaly_detected"
        analysis["recommendation"] = "High edge density and variance suggest structural irregularities. Schedule physical inspection."
    elif analysis["edge_density"] < 0.02:
        analysis["condition"] = "low_visibility"
        analysis["recommendation"] = "Image quality too low for reliable analysis. Retake with better lighting."
    else:
        analysis["condition"] = "normal"
        analysis["recommendation"] = "No anomalies detected in visual inspection."

    return analysis


# ---------------------------------------------------------------------------
# LLM Agent API (MCP-aware)
# ---------------------------------------------------------------------------
class AgentQuery(BaseModel):
    query: str


@app.post("/api/agent/ask")
async def ask_agent(req: AgentQuery):
    if not LLM_API_KEY:
        return {"response": "LLM agent not configured. Set llm_api_key and llm_api_url in add-on options."}

    # Gather context from all platform components
    context_parts = []

    # Neo4j topology summary
    try:
        d = get_neo4j_driver()
        if d:
            with d.session() as s:
                node_count = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
                edge_count = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
                labels = s.run("CALL db.labels() YIELD label RETURN collect(label) AS l").single()["l"]
                context_parts.append(
                    f"Network topology: {node_count} nodes, {edge_count} edges. "
                    f"Node types: {', '.join(labels)}."
                )
    except Exception:
        pass

    # Kafka topics
    try:
        p = get_kafka_producer()
        if p:
            topics = p.list_topics(timeout=3)
            topic_names = [t for t in topics.topics if not t.startswith("__")]
            context_parts.append(f"Kafka topics: {', '.join(topic_names) or 'none'}.")
    except Exception:
        pass

    # OPA policies
    try:
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{OPA_URL}/v1/policies", timeout=3)
            if r.status_code == 200:
                policies = r.json().get("result", [])
                context_parts.append(f"OPA policies loaded: {len(policies)}.")
    except Exception:
        pass

    context = "\n".join(context_parts) if context_parts else "No platform data available yet."

    # Call LLM
    try:
        import anthropic
        client = anthropic.Anthropic(
            api_key=LLM_API_KEY,
            base_url=LLM_API_URL if LLM_API_URL else None,
        )
        message = client.messages.create(
            model=LLM_MODEL,
            max_tokens=1024,
            system=(
                "You are an autonomous telecom network operations agent. "
                "You have access to a real-time platform with Kafka event streaming, "
                "Neo4j graph topology, Spark analytics, OpenCV vision inspection, "
                "and OPA policy enforcement. Use the provided context to answer "
                "questions about the network and suggest optimizations.\n\n"
                f"CURRENT PLATFORM STATE:\n{context}"
            ),
            messages=[{"role": "user", "content": req.query}],
        )
        return {"response": message.content[0].text, "context_used": context}
    except Exception as e:
        return {"response": f"LLM call failed: {e}", "context_used": context}


# ---------------------------------------------------------------------------
# Spark Analytics API
# ---------------------------------------------------------------------------
@app.post("/api/spark/analyze-telemetry")
async def analyze_telemetry():
    """Run a Spark job to analyze telemetry data from Kafka/Neo4j."""
    try:
        from pyspark.sql import SparkSession

        spark = SparkSession.builder \
            .master("local[*]") \
            .appName("NetOps-Telemetry") \
            .config("spark.driver.memory", "512m") \
            .getOrCreate()

        # Example: analyze network topology data from Neo4j
        d = get_neo4j_driver()
        if not d:
            return {"status": "error", "message": "Neo4j not available"}

        with d.session() as s:
            records = s.run(
                "MATCH (a)-[r:CONNECTS_TO]->(b) "
                "RETURN a.name AS source, b.name AS target, "
                "r.bandwidth AS bandwidth, r.latency_ms AS latency"
            ).data()

        if not records:
            spark.stop()
            return {"status": "ok", "message": "No connection data to analyze", "results": {}}

        df = spark.createDataFrame(records)
        stats = {
            "total_connections": df.count(),
            "unique_sources": df.select("source").distinct().count(),
            "unique_targets": df.select("target").distinct().count(),
        }
        spark.stop()
        return {"status": "ok", "results": stats}
    except Exception as e:
        return {"status": "error", "message": str(e)}
