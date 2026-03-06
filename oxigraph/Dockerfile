ARG BUILD_FROM
FROM ${BUILD_FROM}

ARG BUILD_ARCH
ARG OXIGRAPH_VERSION=0.5.5

# Install nginx and apache2-utils (htpasswd for Basic auth)
RUN apk add --no-cache nginx apache2-utils curl

# Download the statically-linked oxigraph binary for the target architecture
RUN set -eux; \
    case "${BUILD_ARCH}" in \
        amd64)   OX_ARCH="x86_64-unknown-linux-musl" ;; \
        aarch64) OX_ARCH="aarch64-unknown-linux-musl" ;; \
        *) echo "Unsupported BUILD_ARCH: ${BUILD_ARCH}" && exit 1 ;; \
    esac; \
    curl -fsSL \
        "https://github.com/oxigraph/oxigraph/releases/download/v${OXIGRAPH_VERSION}/oxigraph_${OX_ARCH}" \
        -o /usr/local/bin/oxigraph; \
    chmod +x /usr/local/bin/oxigraph

# Copy S6 overlay services and helper files
COPY rootfs /

# Make all S6 run scripts executable
RUN find /etc/s6-overlay/s6-rc.d -name "run" -exec chmod a+x {} \;

VOLUME ["/data"]
