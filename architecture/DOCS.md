# Architecture

Shows a C4 model written in [Structurizr DSL](https://docs.structurizr.com/dsl) as a sidebar panel, rendered by `structurizr local`.

## Where the model comes from

The add-on reads `workspace.dsl` from the folder below `/config` named in the option **folder** (default `architecture`, so `/config/architecture/workspace.dsl`), with `!include`, `!docs` and `!adrs` relative to it. It copies the folder into its own data directory every 30 seconds, so Structurizr never writes into `/config`. Without a model it shows a placeholder.

## Configuration

| Option | Default | Meaning |
|---|---|---|
| `folder` | `architecture` | Folder below `/config` with `workspace.dsl`; plain path segments only, no `..` |

The add-on configuration is labelled in English and German. Structurizr's own interface is English; the view picker on phones follows the browser language.

## Live state

A `!script` in the model (for example `live.groovy`) can read `SUPERVISOR_TOKEN` and ask `http://supervisor/core/api/states` and `http://supervisor/addons` while the DSL is parsed. Structurizr only parses again when a file changes, so the add-on compares the states of every entity named in a `"ha.entity"` property, and the add-on list, every 30 seconds; on a change it touches `live.groovy`, and open pages reload by themselves.

## Access

Ingress only, admin only. Structurizr runs read-only (`STRUCTURIZR_EDITABLE=false`) on `127.0.0.1:8080`; nginx on the ingress port puts the ingress prefix into Structurizr's absolute paths and adds pinch zoom and a view picker below 768 px.

## License

Structurizr is built in the image from its Apache-2.0 source ([structurizr/structurizr](https://github.com/structurizr/structurizr), commit in `Dockerfile`), not taken from the prebuilt `structurizr/structurizr` image: that one also contains Structurizr's closed server extensions, and nothing grants redistributing it. The license text is in the image at `/usr/local/share/doc/structurizr/LICENSE`. Only `local` runs here, never `server`.

## Updating Structurizr

Bump `STRUCTURIZR_COMMIT` in `Dockerfile` and `version` in `config.yaml` in the same commit, otherwise Home Assistant offers no update. Dependabot keeps the two Temurin base images current. The prefix rewriting depends on how Structurizr writes its paths: check the panel after every update.
