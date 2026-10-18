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

A `!script` in the model (for example `live.groovy`) can read `SUPERVISOR_TOKEN` and ask `http://supervisor/core/api/states` and `http://supervisor/addons/<slug>/info` while the DSL is parsed. Structurizr only parses again when a file changes, so the add-on compares the states of every entity named in a `"ha.entity"` property, and state and version of every add-on named in a `"ha.addon"` property, every 30 seconds; on a change it touches `live.groovy`, and open pages reload by themselves.

The add-on has the Supervisor's default role, which reads `*/info` but not the list `/addons` (that takes the role `manager`, which can also stop, install and remove add-ons). So the model only knows the add-ons it names: a newly installed add-on appears once someone adds it to the model with a `"ha.addon"` property.

## Access

Ingress only, admin only. Structurizr runs read-only (`STRUCTURIZR_EDITABLE=false`) on `127.0.0.1:8080`; nginx on the ingress port puts the ingress prefix into Structurizr's absolute paths and opens the panel on the diagrams.

## Theme and phone

The panel follows the Home Assistant theme: background, cards, text, accent colour and font come from the theme's CSS variables, light or dark from the theme's dark mode, and both change with it. Structurizr's own light/dark switch is hidden. Opened outside Home Assistant, the system setting decides. The diagram elements keep the colours of the model's `styles`, with its `dark` block in dark mode.

On a phone: one finger pans, two fingers zoom, a double tap zooms in threefold up to 1:1 and then back to the whole diagram, and a picker at the top chooses the view. The summary, documentation and decisions pages stack their columns at 360 px without sideways scrolling.

A model that overrides a style in `dark` must define the same tag in `light` too, with every attribute. Structurizr otherwise writes the dark values into the unscoped definition once it renders in dark mode (the dark thumbnails do), and the light view stays dark afterwards.

## License

Structurizr is built in the image from its Apache-2.0 source ([structurizr/structurizr](https://github.com/structurizr/structurizr), commit in `Dockerfile`), not taken from the prebuilt `structurizr/structurizr` image: that one also contains Structurizr's closed server extensions, and nothing grants redistributing it. The license text is in the image at `/usr/local/share/doc/structurizr/LICENSE`. Only `local` runs here, never `server`.

## Updating Structurizr

Bump `STRUCTURIZR_COMMIT` in `Dockerfile` and `version` in `config.yaml` in the same commit, otherwise Home Assistant offers no update. Dependabot keeps the two Temurin base images current. The prefix rewriting depends on how Structurizr writes its paths: check the panel after every update.
