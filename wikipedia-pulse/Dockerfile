# Wikipedia Pulse: one Python process, standard library only.
ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM ${BUILD_FROM}

RUN apk add --no-cache python3

COPY pulse.py /app/pulse.py

# The base image starts s6 as /init; one process needs no supervisor, and
# Home Assistant restarts the container when it exits (config.yaml, init: false).
ENTRYPOINT []
CMD ["python3", "-u", "/app/pulse.py"]
