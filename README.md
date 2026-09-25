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
| [Prompts](./prompts/) | Hundert Prompting-Strategien für Sprachmodelle auf Deutsch: suchen, aufklappen, kopieren. | [pajew-ski/prompts](https://github.com/pajew-ski/prompts) |
| [Open Entrainer](./open-entrainer/) | Binaural beat generator: two tones a few hertz apart, ramped along a plan you set, pink noise underneath. | [pajew-ski/open-entrainer](https://github.com/pajew-ski/open-entrainer) |
| [Open Desensitizer](./open-desensitizer/) | Bilateral stimulation: a dot moves from side to side, an optional tone pans with it, grounding is one key away. | [pajew-ski/open-desensitizer](https://github.com/pajew-ski/open-desensitizer) |
| [Open Workspace](./open-workspace/) | AI-Workspace mit RDF-Graph-Kern, SPARQL, MCP-Server und Föderation (amd64, aarch64). | [pajew-ski/open-workspace](https://github.com/pajew-ski/open-workspace) |
| [Exocortex](./exocortex/) | Knowledge operating system with hybrid search, SPARQL graph, AI agent memory, MCP server, and multi-agent orchestration. | [pajew-ski/home-assistant-apps-collection](https://github.com/pajew-ski/home-assistant-apps-collection) |

The current version of each add-on is the `version` field of its
`config.yaml`; the sync workflow bumps it, so the table does not repeat it.

Prompts, Open Entrainer, Open Desensitizer and Open Workspace share one
design: the achromatic token scale of
[temet-nosce](https://github.com/pajew-ski/temet-nosce), Fibonacci spacing,
a type scale in powers of φ, dark and light following the system. The three
single-file apps are one `index.html` each, with no build step and no
external resource; the add-on image is that file behind nginx.

## How It Works

Each add-on in this collection is mirrored from its upstream source repository.
The `config.yaml` and `build.yaml` files are synced automatically. Pre-built
Docker images are published to the GitHub Container Registry (ghcr.io) and
referenced from each add-on's `config.yaml` via the `image` field.

The [sync workflow](./.github/workflows/sync-addons.yml) runs daily and:
- Detects changes upstream: a new commit to `index.html` for the single-file
  apps (their version is that commit's date, `YYYY.M.D`), a version bump for
  add-ons that carry one
- Rebuilds multi-arch Docker images (amd64, aarch64, armv7; Open Workspace
  and Exocortex amd64 and aarch64)
- Pushes images to `ghcr.io/pajew-ski/home-assistant-apps-collection/`
- Updates the add-on's `config.yaml` and commits the change

Open Workspace has no per-change version upstream. It is mirrored from every
green `main` commit that touches the image or the add-on manifest, versioned
as `{upstream version}.{commit time YYYYMMDDHHMM}`, and built natively for
amd64 and aarch64.

## Adding a New Add-on

See [CLAUDE.md](./CLAUDE.md) for the step-by-step instructions used when
extending this collection programmatically.

## License

Each add-on retains the license of its upstream source repository.
