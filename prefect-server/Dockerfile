ARG BUILD_FROM
FROM ${BUILD_FROM}

ARG BUILD_ARCH
ARG PREFECT_VERSION=3.6.21

# Install Python, pip, nginx, and build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        nginx \
        apache2-utils \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Create virtualenv and install prefect
RUN python3 -m venv /opt/prefect && \
    /opt/prefect/bin/pip install --no-cache-dir "prefect[server]==${PREFECT_VERSION}"

# Add virtualenv to PATH
ENV PATH="/opt/prefect/bin:${PATH}"

# Prefect configuration – server listens on internal port 4201;
# nginx exposes 8099 (ingress) and optionally 4200 (external).
ENV PREFECT_HOME="/data/prefect" \
    PREFECT_SERVER_API_HOST="127.0.0.1" \
    PREFECT_SERVER_API_PORT="4201" \
    PREFECT_API_URL="http://127.0.0.1:4201/api" \
    PREFECT_SERVER_DATABASE_CONNECTION_URL="sqlite+aiosqlite:////data/prefect/prefect.db" \
    PREFECT_UI_ENABLED="true" \
    PREFECT_SERVER_CSRF_PROTECTION_ENABLED="false" \
    PREFECT_SERVER_ANALYTICS_ENABLED="false"

# Copy rootfs (s6-overlay services)
COPY rootfs /

# Ensure s6 scripts are executable
RUN chmod a+x /etc/s6-overlay/s6-rc.d/prefect-server/run \
    && chmod a+x /etc/s6-overlay/s6-rc.d/nginx/run

# Persistent storage
VOLUME ["/data"]
