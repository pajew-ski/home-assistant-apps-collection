ARG BUILD_FROM
FROM ${BUILD_FROM}

ARG BUILD_ARCH
ARG EXOCORTEX_VERSION=1.0.0
ARG MEILISEARCH_VERSION=1.12.8
ARG QDRANT_VERSION=1.13.2
ARG OXIGRAPH_VERSION=0.4.9

# ── System Dependencies ──────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv python3-dev \
        build-essential \
        git \
        redis-server \
        nginx \
        curl \
        jq \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default

# ── MeiliSearch Binary ───────────────────────────────────────────────
RUN set -eux; \
    case "${BUILD_ARCH}" in \
        amd64)   MEILI_ARCH="amd64" ;; \
        aarch64) MEILI_ARCH="aarch64" ;; \
        *) echo "Unsupported BUILD_ARCH: ${BUILD_ARCH}" && exit 1 ;; \
    esac; \
    curl -fsSL \
        "https://github.com/meilisearch/meilisearch/releases/download/v${MEILISEARCH_VERSION}/meilisearch-linux-${MEILI_ARCH}" \
        -o /usr/local/bin/meilisearch && \
    chmod +x /usr/local/bin/meilisearch

# ── Qdrant Binary ───────────────────────────────────────────────────
RUN set -eux; \
    case "${BUILD_ARCH}" in \
        amd64)   QDRANT_ARCH="x86_64-unknown-linux-gnu" ;; \
        aarch64) QDRANT_ARCH="aarch64-unknown-linux-musl" ;; \
        *) echo "Unsupported BUILD_ARCH: ${BUILD_ARCH}" && exit 1 ;; \
    esac; \
    curl -fsSL \
        "https://github.com/qdrant/qdrant/releases/download/v${QDRANT_VERSION}/qdrant-${QDRANT_ARCH}.tar.gz" \
        | tar xz -C /usr/local/bin/ && \
    chmod +x /usr/local/bin/qdrant

# ── Oxigraph Binary ─────────────────────────────────────────────────
RUN set -eux; \
    case "${BUILD_ARCH}" in \
        amd64)   OX_ARCH="x86_64_linux_gnu" ;; \
        aarch64) OX_ARCH="aarch64_linux_gnu" ;; \
        *) echo "Unsupported BUILD_ARCH: ${BUILD_ARCH}" && exit 1 ;; \
    esac; \
    curl -fsSL \
        "https://github.com/oxigraph/oxigraph/releases/download/v${OXIGRAPH_VERSION}/oxigraph_v${OXIGRAPH_VERSION}_${OX_ARCH}" \
        -o /usr/local/bin/oxigraph && \
    chmod +x /usr/local/bin/oxigraph

# ── Python Virtual Environment ───────────────────────────────────────
RUN python3 -m venv /opt/exocortex

RUN /opt/exocortex/bin/pip install --no-cache-dir \
    "fastapi[standard]>=0.115,<1" \
    "uvicorn[standard]>=0.34,<1" \
    "meilisearch>=0.31,<1" \
    "qdrant-client>=1.12,<2" \
    "sentence-transformers>=3.3,<4" \
    "python-frontmatter>=1.1,<2" \
    "gitpython>=3.1,<4" \
    "redis[hiredis]>=5.2,<6" \
    "httpx>=0.28,<1" \
    "watchdog>=6,<7" \
    "msgpack>=1.1,<2" \
    "pyyaml>=6,<7" \
    "mcp>=1.0,<2" \
    "websockets>=14,<15"

# ── Pre-download Embedding Model (offline operation) ─────────────────
RUN /opt/exocortex/bin/python -c \
    "from sentence_transformers import SentenceTransformer; \
     SentenceTransformer('all-MiniLM-L6-v2', cache_folder='/opt/exocortex/models')"

# ── Copy S6 overlay services and scripts ─────────────────────────────
COPY rootfs /

# ── Copy Application Code ───────────────────────────────────────────
COPY exocortex/ /opt/exocortex/app/exocortex/

# ── Make all S6 scripts executable ───────────────────────────────────
RUN find /etc/s6-overlay/s6-rc.d -name "run" -exec chmod a+x {} \; 2>/dev/null || true && \
    find /etc/s6-overlay/s6-rc.d -name "up" -exec chmod a+x {} \; 2>/dev/null || true && \
    chmod a+x /etc/s6-overlay/scripts/*.sh 2>/dev/null || true

# ── Data Directories ────────────────────────────────────────────────
RUN mkdir -p /data/repo /data/meilisearch /data/qdrant /data/oxigraph \
    /data/redis /data/embeddings_cache /data/models

WORKDIR /opt/exocortex/app

VOLUME ["/data"]
