ARG BUILD_FROM
FROM ${BUILD_FROM}

ARG BUILD_ARCH
ARG KAFKA_VERSION=3.7.1
ARG SPARK_VERSION=3.5.3
ARG NEO4J_VERSION=5.26.0
ARG OPA_VERSION=1.3.0

# ---------------------------------------------------------------------------
# System dependencies
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        # JDK for Kafka, Neo4j, Spark
        openjdk-21-jre-headless \
        # Python
        python3 python3-pip python3-venv python3-dev \
        # Build tools for native Python packages
        gcc g++ make cmake \
        # OpenCV system dependencies
        libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
        # Networking & tools
        nginx apache2-utils curl wget netcat-openbsd procps jq \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME="/usr/lib/jvm/java-21-openjdk-${BUILD_ARCH}" \
    PATH="/usr/lib/jvm/java-21-openjdk-${BUILD_ARCH}/bin:${PATH}"

# ---------------------------------------------------------------------------
# Apache Kafka (KRaft mode – no ZooKeeper)
# ---------------------------------------------------------------------------
RUN KAFKA_SCALA_VERSION=2.13 && \
    wget -qO /tmp/kafka.tgz \
      "https://downloads.apache.org/kafka/${KAFKA_VERSION}/kafka_${KAFKA_SCALA_VERSION}-${KAFKA_VERSION}.tgz" && \
    mkdir -p /opt/kafka && \
    tar -xzf /tmp/kafka.tgz --strip-components=1 -C /opt/kafka && \
    rm /tmp/kafka.tgz

ENV KAFKA_HOME="/opt/kafka" \
    PATH="/opt/kafka/bin:${PATH}"

# ---------------------------------------------------------------------------
# Neo4j Community Edition
# ---------------------------------------------------------------------------
RUN wget -qO /tmp/neo4j.tar.gz \
      "https://dist.neo4j.org/neo4j-community-${NEO4J_VERSION}-unix.tar.gz" && \
    mkdir -p /opt/neo4j && \
    tar -xzf /tmp/neo4j.tar.gz --strip-components=1 -C /opt/neo4j && \
    rm /tmp/neo4j.tar.gz

ENV NEO4J_HOME="/opt/neo4j" \
    PATH="/opt/neo4j/bin:${PATH}"

# ---------------------------------------------------------------------------
# Open Policy Agent
# ---------------------------------------------------------------------------
RUN OPA_ARCH=$([ "$BUILD_ARCH" = "aarch64" ] && echo "arm64" || echo "amd64") && \
    wget -qO /usr/local/bin/opa \
      "https://github.com/open-policy-agent/opa/releases/download/v${OPA_VERSION}/opa_linux_${OPA_ARCH}_static" && \
    chmod +x /usr/local/bin/opa

# ---------------------------------------------------------------------------
# Python virtualenv: PySpark, OpenCV, Kafka client, Neo4j driver, FastAPI,
# MCP SDK, LLM client libraries
# ---------------------------------------------------------------------------
RUN python3 -m venv /opt/netops-venv && \
    /opt/netops-venv/bin/pip install --no-cache-dir \
        "pyspark==${SPARK_VERSION}" \
        opencv-python-headless \
        confluent-kafka \
        neo4j \
        fastapi \
        uvicorn[standard] \
        httpx \
        opa-python-client \
        anthropic \
        mcp \
        pydantic \
        jinja2

ENV PATH="/opt/netops-venv/bin:${PATH}" \
    SPARK_HOME="/opt/netops-venv/lib/python3.12/dist-packages/pyspark" \
    PYSPARK_PYTHON="/opt/netops-venv/bin/python3"

# ---------------------------------------------------------------------------
# Application code
# ---------------------------------------------------------------------------
COPY rootfs /

# Ensure s6 scripts are executable
RUN find /etc/s6-overlay/s6-rc.d -name run -exec chmod a+x {} +

# Persistent storage for Kafka logs, Neo4j data, OPA bundles
VOLUME ["/data"]
