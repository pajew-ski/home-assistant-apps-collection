# Telecom NetOps Platform

Real-time telecom network operations platform running entirely on your Home Assistant instance.

## Architecture

This add-on runs six integrated services in a single container:

| Service | Port (internal) | Purpose |
|---------|----------------|---------|
| **Apache Kafka** | 9092 | Event streaming and telemetry ingestion (KRaft mode, no ZooKeeper) |
| **Neo4j** | 7474/7687 | Graph database for network topology digital twin |
| **Open Policy Agent** | 8181 | Policy enforcement and governance |
| **Apache Spark** | local mode | Stream processing and analytics |
| **OpenCV** | via API | Computer vision for infrastructure inspection |
| **NetOps API** | 8080 | FastAPI dashboard integrating all components |
| **nginx** | 8099/9080 | Ingress proxy and optional external access |

## Data Flow

1. **Ingestion:** Kafka receives telemetry, router logs, and IoT sensor data
2. **Processing:** Spark transforms raw streams; OpenCV analyzes infrastructure images
3. **Modeling:** Neo4j maintains a digital twin graph (nodes = hardware, edges = connections)
4. **Governance:** OPA validates access and enforces network security policies
5. **AI Operations:** LLM agents (via MCP) query the graph and optimize the network

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `auth_type` | `none` | Authentication for external access: `none`, `basic`, or `bearer` |
| `username` | | Username for HTTP Basic auth |
| `password` | | Password for HTTP Basic auth |
| `bearer_token` | | Token for Bearer auth |
| `network_access` | `false` | Expose dashboard on port 9080 |
| `kafka_external` | `false` | Expose Kafka broker on port 9092 |
| `neo4j_external` | `false` | Expose Neo4j on ports 7474/7687 |
| `neo4j_password` | `neo4j` | Neo4j database password |
| `llm_api_key` | | API key for LLM provider (e.g. Anthropic) |
| `llm_api_url` | | Custom LLM API base URL (optional) |
| `llm_model` | `claude-sonnet-4-20250514` | LLM model identifier |

## API Endpoints

- `GET /api/status` – Service health and platform metrics
- `GET /api/kafka/topics` – List Kafka topics
- `POST /api/kafka/produce` – Produce message to Kafka topic
- `GET /api/topology` – Get Neo4j network topology graph
- `POST /api/topology/seed` – Seed demo telecom topology
- `POST /api/policy/check` – Check OPA policy
- `POST /api/vision/inspect` – Analyze infrastructure image with OpenCV
- `POST /api/agent/ask` – Query the LLM agent with network context
- `POST /api/spark/analyze-telemetry` – Run Spark analytics on topology data

## Resource Requirements

This add-on runs multiple JVM-based services (Kafka, Neo4j, Spark). Recommended minimum:

- **RAM:** 4 GB
- **CPU:** 4 cores
- **Disk:** 10 GB free
- **Architecture:** amd64 or aarch64 only
