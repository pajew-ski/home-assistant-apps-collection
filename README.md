# pajew-ski Home Assistant Apps Collection

A single-link Home Assistant add-on repository that aggregates multiple add-ons.

## Installation

1. Open Home Assistant → **Settings** → **Add-ons** → **Add-on Store**
2. Click the three-dot menu (⋮) → **Repositories**
3. Add this URL:
   ```
   https://github.com/pajew-ski/home-assistant-apps-collection
   ```
4. All add-ons from this collection will appear in the store.

## Included Add-ons

| Add-on | Description | Source |
|--------|-------------|--------|
| [Prompts](./prompts/) | A hundred prompting strategies for language models in English and German, plus skills and agent instructions. | [pajew-ski/prompts](https://github.com/pajew-ski/prompts) |
| [Open Entrainer](./open-entrainer/) | A binaural beat generator with a plan you set and pink noise underneath. | [pajew-ski/open-entrainer](https://github.com/pajew-ski/open-entrainer) |
| [Open Desensitizer](./open-desensitizer/) | Bilateral stimulation with a moving dot, an optional tone and a grounding exercise. | [pajew-ski/open-desensitizer](https://github.com/pajew-ski/open-desensitizer) |
| [Open Helix](./open-helix/) | A Shepard-Risset glissando, every parameter adjustable, with a live spectrogram. | [pajew-ski/open-helix](https://github.com/pajew-ski/open-helix) |
| [Open Workspace](./open-workspace/) | AI workspace with an RDF graph core, SPARQL, MCP server and federation (amd64, aarch64). | [pajew-ski/open-workspace](https://github.com/pajew-ski/open-workspace) |
| [Exocortex](./exocortex/) | Knowledge operating system with hybrid search, SPARQL graph, AI agent memory, MCP server and multi-agent orchestration. | [pajew-ski/home-assistant-apps-collection](https://github.com/pajew-ski/home-assistant-apps-collection) |

The store shows the current version of each add-on.

## How It Works

The [sync workflow](./.github/workflows/sync-addons.yml) builds every add-on's Docker images, pushes them to `ghcr.io/pajew-ski/home-assistant-apps-collection/`, and commits the new version into the add-on's `config.yaml` only after all of its images are pushed. It runs right after a merge in a source repository (that repository's notify workflow sends a `repository_dispatch`), every hour as a fallback, and by hand.

- **Static apps** (Prompts, Open Entrainer, Open Desensitizer, Open Helix): the upstream is one `index.html`, served by nginx from a shared [Dockerfile](./static-app/Dockerfile) for amd64, aarch64 and armv7. Every commit that changes `index.html` on `main` becomes a version `YYYY.M.D.HHMM` from its commit time. The last built commit is kept in `<slug>/.upstream-sha`.
- **Open Workspace** has no per-change version upstream. It is mirrored from every green `main` commit that touches the image or the add-on manifest, versioned as `{upstream version}.{commit time YYYYMMDDHHMM}`, and built natively for amd64 and aarch64.
- **Exocortex** lives in this repository; a forced run rebuilds it with the next packaging version.

## Adding a New Add-on

See [CLAUDE.md](./CLAUDE.md) for the step-by-step instructions used when
extending this collection programmatically.

## License

Each add-on retains the license of its upstream source repository.
