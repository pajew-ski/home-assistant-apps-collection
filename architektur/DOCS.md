# Architektur

Shows a C4 model written in [Structurizr DSL](https://docs.structurizr.com/dsl) as a sidebar panel, rendered by `structurizr local`.

## Where the model comes from

The add-on reads `/config/architektur/workspace.dsl` (with `!include`, `!docs` and `!adrs` relative to it) and copies the folder into its own data directory every 30 seconds, so Structurizr never writes into `/config`. Without a model it shows a placeholder.

## Live state

A `!script` in the model (for example `live.groovy`) can read `SUPERVISOR_TOKEN` and ask `http://supervisor/core/api/states` and `http://supervisor/addons` while the DSL is parsed. Structurizr only parses again when a file changes, so the add-on compares the states of every entity named in a `"ha.entity"` property, and the add-on list, every 30 seconds; on a change it touches `live.groovy`, and open pages reload by themselves.

## Access

Ingress only, admin only. Structurizr runs read-only (`STRUCTURIZR_EDITABLE=false`) on `127.0.0.1:8080`; nginx on the ingress port puts the ingress prefix into Structurizr's absolute paths and adds pinch zoom and a view picker below 768 px.

## Updating Structurizr

The base image is pinned by digest in `Dockerfile`. A Dependabot update of it also bumps `version` in `config.yaml`, otherwise Home Assistant offers no update. The prefix rewriting depends on how Structurizr writes its paths: check the panel after every update.
