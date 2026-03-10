ARG BUILD_FROM
ARG METABASE_VERSION=0.52.8

# --- Stage 1: grab the Metabase JAR (platform-independent) ----------------
FROM --platform=linux/amd64 docker.io/metabase/metabase:v${METABASE_VERSION} AS metabase-src

# --- Stage 2: final HA add-on image ----------------------------------------
FROM ${BUILD_FROM}

ARG BUILD_ARCH

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        nginx \
        openjdk-17-jre-headless \
        python3 \
        curl \
        jq \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default

# Copy Metabase JAR from stage 1 (Java bytecode is arch-independent)
COPY --from=metabase-src /app/metabase.jar /opt/metabase/metabase.jar

# Copy S6 overlay services and helper scripts
COPY rootfs /

# Make all run scripts and helper binaries executable
RUN find /etc/s6-overlay/s6-rc.d -name "run" -exec chmod a+x {} \; \
    && chmod +x /usr/bin/bootstrap.sh /usr/bin/theme_sync.py

VOLUME ["/data"]
