# Structurizr local behind nginx for Home Assistant ingress.
#
# Built from the Apache-2.0 source, not FROM structurizr/structurizr: that
# prebuilt image also carries Structurizr's closed server extensions, and
# nothing grants redistributing it, while this image is published on ghcr.io.
# The source build has no closed classes and runs the same `local` command.
#
# Base images are pinned by digest and kept current by Dependabot. The source
# commit is bumped by hand together with `version` in config.yaml.

# The war is architecture independent: build it once, natively.
FROM --platform=$BUILDPLATFORM eclipse-temurin:25-jdk-noble@sha256:589ff4cc3f71aab462e7048a47a0d10edf57fbccde3fceea2281e610bf5880b4 AS bau
ARG STRUCTURIZR_COMMIT=da99caf2f2857e5373f7b58569152274f1725ba3
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git init -q . \
    && git fetch -q --depth 1 https://github.com/structurizr/structurizr.git "$STRUCTURIZR_COMMIT" \
    && git checkout -q FETCH_HEAD \
    && ./mvnw -q -B -P 'exclude-playwright,!include-playwright' -pl structurizr-application -am package -DskipTests

FROM eclipse-temurin:25-jre-noble@sha256:d9a39a23634650173f1e2bbc176227af9728587ecf0f4b62d53e9355cd7a19ab

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx curl jq \
    && rm -rf /var/lib/apt/lists/*

COPY --from=bau /src/structurizr-application/target/structurizr-1.0.0.war /usr/local/structurizr.war
COPY --from=bau /src/structurizr-themes /usr/local/structurizr-themes
COPY --from=bau /src/LICENSE /usr/local/share/doc/structurizr/LICENSE
COPY rootfs/ /
RUN chmod +x /etc/architektur/run.sh

ENTRYPOINT ["/etc/architektur/run.sh"]
