# Structurizr local behind nginx for Home Assistant ingress.
# Pinned by digest; Dependabot proposes updates (.github/dependabot.yml). Bump
# "version" in config.yaml in the same PR, or Home Assistant offers no update.
FROM structurizr/structurizr:2026.09.19-noble@sha256:19337d1abe5ab39c94b7a23f5b76b2a0d5c80b28c3e58209c867725479b8d876

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx curl jq ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY rootfs/ /
RUN chmod +x /etc/architektur/run.sh

ENTRYPOINT ["/etc/architektur/run.sh"]
