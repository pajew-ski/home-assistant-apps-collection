# Structurizr local behind nginx for Home Assistant ingress.
# Pinned by digest; Dependabot proposes updates (.github/dependabot.yml). Bump
# "version" in config.yaml in the same PR, or Home Assistant offers no update.
FROM structurizr/structurizr:2026.09.19-noble@sha256:a8f29550c60d1d03691f0dc474deabf31c1c1d72182c0bb02659b0b1d16dfd84

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx curl jq ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY rootfs/ /
RUN chmod +x /etc/architektur/run.sh

ENTRYPOINT ["/etc/architektur/run.sh"]
