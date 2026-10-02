# CLAUDE.md – Home Assistant Apps Collection

This file gives Claude Code the context and instructions needed to maintain and
extend this repository autonomously.

---

## Purpose

This is a **Home Assistant add-on meta-repository**. Users add the single URL
`https://github.com/pajew-ski/home-assistant-apps-collection` to Home Assistant
and get access to every add-on listed here.

The repository does **not** contain full add-on source code. It contains:
- `repository.json` – HA repository descriptor (required at root)
- `addons-registry.json` – machine-readable registry of all add-ons
- One subdirectory per add-on with `config.yaml` (+ `icon.png`, other assets as needed)
- `.github/workflows/sync-addons.yml` – automation that keeps everything in sync
- `static-app/Dockerfile` and `.github/scripts/` – the shared image and helpers of the static apps

Pre-built Docker images live in
`ghcr.io/pajew-ski/home-assistant-apps-collection/` and are referenced via the
`image` field in each add-on's `config.yaml`.

---

## Repository Structure

```
home-assistant-apps-collection/
├── repository.json            # HA repository descriptor
├── addons-registry.json       # Registry of all add-ons; the static-app path reads it
├── README.md
├── CLAUDE.md                  # This file
├── .github/
│   ├── workflows/
│   │   └── sync-addons.yml    # Build, version and publish every add-on
│   └── scripts/
│       ├── static_apps.py     # Static apps: check (what to build) and publish (write versions)
│       └── check-public.sh    # Warns when an image cannot be pulled anonymously
├── static-app/
│   └── Dockerfile             # Shared image for every static app: index.html behind nginx
├── prompts/                   # Static app
│   ├── config.yaml            #   written here, never synced from upstream
│   ├── icon.png
│   └── .upstream-sha          #   last built upstream commit (written by the workflow)
├── open-entrainer/            # Static app (same files)
├── open-desensitizer/         # Static app (same files)
├── open-helix/                # Static app (same files)
├── open-workspace/            # Upstream mirror (commit-versioned, CI-gated)
│   ├── config.yaml            #   from deploy/ha-addon/ upstream
│   ├── DOCS.md
│   ├── icon.png
│   └── .upstream-sha
└── exocortex/                 # Custom add-on (self-contained in this repo)
    ├── Dockerfile
    ├── build.yaml
    ├── config.yaml
    ├── DOCS.md
    ├── rootfs/                # s6-overlay service definitions
    └── exocortex/             # Python/FastAPI application
```

### Key files explained

| File | Purpose |
|------|---------|
| `repository.json` | Identifies the repo to Home Assistant (name, url, maintainer) |
| `addons-registry.json` | Source of truth for which add-ons are present and from where; `"static_app": true` puts an add-on on the static path |
| `<slug>/config.yaml` | HA add-on manifest; must include `image:` pointing to ghcr.io. For static apps the workflow reads `ingress_port` and `arch` from it and writes only `version` |
| `<slug>/.upstream-sha` | The upstream commit the published version was built from |
| `static-app/Dockerfile` | The image of every static app, built with `BUILD_FROM`, `PORT`, `BUILD_ARCH`, `BUILD_VERSION` |
| `.github/workflows/sync-addons.yml` | Checks upstreams, builds images, commits versions |

---

## Current Add-ons

| Slug | Type | Source |
|------|------|--------|
| `prompts` | static app | https://github.com/pajew-ski/prompts |
| `open-entrainer` | static app | https://github.com/pajew-ski/open-entrainer |
| `open-desensitizer` | static app | https://github.com/pajew-ski/open-desensitizer |
| `open-helix` | static app | https://github.com/pajew-ski/open-helix |
| `open-workspace` | upstream mirror (commit-versioned, CI-gated) | https://github.com/pajew-ski/open-workspace |
| `exocortex` | custom dockerfile | self-contained in this repo |

Ingress ports: prompts 8099, open-entrainer 8100, open-desensitizer 8101, open-helix 8102.

---

## When the Workflow Runs

- **`repository_dispatch` of type `upstream-changed`**, payload `{"slug": "<slug>"}`: sent by the notify workflow of a source repository (`.github/workflows/notify-addon.yml` in each static app's repo) after every push to `main` that changes `index.html`. The run looks only at that add-on. The source repo needs the secret `APPS_COLLECTION_TOKEN`, a fine-grained personal access token with "Contents: Read and write" on this repository (that is what `repository_dispatch` requires).
- **Hourly schedule** (minute 23): the fallback. It checks every add-on and builds only what changed, so a source repo without the secret still gets every merge within the hour.
- **By hand**: Actions → Sync Add-ons → Run workflow, with an optional slug and *Force rebuild*.

The workflow has one concurrency group, so runs queue instead of interleaving, and every job that pushes rebases and retries.

---

## Adding a New Add-on

### A static app (one `index.html` upstream)

This is the usual case for the family of single-file apps. No workflow code is needed; the static path reads the registry. The same steps, written for an agent, are in the prompts collection: `agents/home-assistant-addon/AGENTS.md` in https://github.com/pajew-ski/prompts.

1. Add an entry to `addons-registry.json`:

   ```json
   {
     "slug": "<repo name>",
     "name": "<Human-readable name>",
     "source": "https://github.com/pajew-ski/<repo name>",
     "branch": "main",
     "sync_files": ["index.html"],
     "image_prefix": "ghcr.io/pajew-ski/home-assistant-apps-collection/{arch}-<slug>",
     "static_app": true
   }
   ```

2. Write `<slug>/config.yaml` by hand, like `open-helix/config.yaml`: English description, the next free ingress port in `ingress_port` and `ports`, `arch` amd64, aarch64, armv7, `version: "0.0.0"` as a placeholder, and the `image:` field.
3. Add `<slug>/icon.png`, 128×128, in the family style (dark rounded square `#0b0b0b`, radius 21, light glyph `#ececec`, no color).
4. Add a row to the table in `README.md` (no version column).
5. In the source repository, copy `.github/workflows/notify-addon.yml` from a sibling and set the secret `APPS_COLLECTION_TOKEN`.
6. Commit. The next run builds the first version.
7. After that first build, set each new package to public once (see Known Issues); the run's warnings link to the settings pages.

### Any other add-on

The upstream must be a valid Home Assistant add-on (a `config.yaml` with `name`, `version`, `slug`, `arch`, `startup`, `boot`, and a `Dockerfile` that accepts `ARG BUILD_FROM`). Register it in `addons-registry.json`, create `<slug>/config.yaml` with the `image:` field, and add its own jobs to `sync-addons.yml` following the `open-workspace` jobs: a check job that decides from the upstream commit, a build job, and a publish job that commits `config.yaml` only after the images are pushed, pushes with rebase and retry, and runs `check-public.sh`.

---

## Workflow Permissions and Secrets

| Permission | Reason |
|------------|--------|
| `contents: write` | Commit updated config files |
| `packages: write` | Push images to ghcr.io |

This repository needs no secret beyond the automatic `GITHUB_TOKEN`. Each source repository of a static app may hold `APPS_COLLECTION_TOKEN` for the immediate dispatch; without it, the hourly check covers it.

---

## Known Issues & Lessons Learned

### New ghcr.io packages are private, and no API changes that

Home Assistant pulls images anonymously, so every image must be public. A package that a workflow pushes for the first time starts out private, and GitHub has no REST endpoint to change a package's visibility. (The workflow used to call `PATCH /user/packages/container/...` for that; the endpoint does not exist, every call returned 404, and the error was swallowed.) After the first build of a new add-on, set each `{arch}-<slug>` package to public once under the package's settings, Danger Zone, Change visibility. `.github/scripts/check-public.sh` runs after every publish, requests an anonymous pull token, and prints a warning with the settings link for every image that is not public.

### Upstream repositories without add-on files

The static apps' repositories carry no `config.yaml`, `build.yaml` or `Dockerfile`; prompts dropped them in October 2026, and the old mirror step, which downloaded them, failed with a 404 from then on. Everything add-on related for a static app lives here. Do not reintroduce a sync of manifest files from these upstreams.

### Versions must change with every merge

The static apps used to take the date of the last upstream commit as version (`YYYY.M.D`). Two merges on one day produced the same version, and Home Assistant offered no update for the second. The version is now the commit time to the minute, `YYYY.M.D.HHMM`, and the decision to build compares commits (`.upstream-sha`), not versions. If a computed version would not be higher than the published one (an older commit merged late, or a forced rebuild), the current time is used instead.

### node:22-alpine does not support all HA architectures

`node:22-alpine` (and Node.js 22 in general) only publishes images for:

| Docker platform | HA arch |
|-----------------|---------|
| `linux/amd64`   | `amd64` |
| `linux/arm64`   | `aarch64` |
| `linux/arm/v7`  | `armv7` |

**`armhf` (`linux/arm/v6`) and `i386` (`linux/386`) are not available.** If an add-on's Dockerfile uses such an image, remove `armhf` and `i386` from the `arch` list in `config.yaml` and limit its build to the remaining archs. Otherwise buildx fails with `no match for platform in manifest: not found`.

### Upstreams without a version bump per change (open-workspace)

`open-workspace` keeps `version: "0.1.0"` in `deploy/ha-addon/config.yaml` while `main` moves on, so a version comparison never detects updates. It has its own jobs in `sync-addons.yml` (`open-workspace-check`, `-build`, `-publish`):

- **Trigger:** upstream `main` HEAD differs from `open-workspace/.upstream-sha` and the diff touches something that ends up in the image or the manifest (`src/`, `scripts/`, `public/`, `seed/`, `ontology/`, `deploy/ha-addon/`, `Dockerfile`, `package.json`, `bun.lock`, …). Docs-only commits are skipped.
- **Gate:** all check runs of that commit are completed and green; otherwise the next run picks it up.
- **Version:** `{upstream version}.{commit time YYYYMMDDHHMM}`; *Force rebuild* of an unchanged commit uses the current time so HA still offers the update.
- **Build:** natively per arch (`ubuntu-latest`, `ubuntu-24.04-arm`) with the upstream Dockerfile unchanged (no `BUILD_FROM`; it brings `oven/bun` and `node:22-alpine`, hence amd64/aarch64 only). bun under QEMU is unreliable.
- **Publish:** `config.yaml` is committed only after both images are pushed. The upstream `image:` field (`ghcr.io/pajew-ski/open-workspace`, never built) is replaced, not appended.

---

## Home Assistant Repository Requirements (reference)

A valid HA add-on repository must have:

1. **`repository.json`** at the root:
   ```json
   { "name": "…", "url": "https://github.com/…", "maintainer": "…" }
   ```
2. **One directory per add-on** containing at minimum `config.yaml`.
3. Each `config.yaml` must specify `name`, `version`, `slug`, `arch`,
   `startup`, and `boot`.
4. If the add-on uses pre-built images (preferred for meta-repos), the
   `image` field must use the `{arch}` placeholder:
   ```yaml
   image: "ghcr.io/<owner>/<repo>/{arch}-<slug>"
   ```

---

## Exocortex — Custom Add-on

Exocortex is the flagship add-on in this collection. Unlike the mirrored add-ons
it lives entirely in this repo under `exocortex/` and ships its own Dockerfile.

**What it is:** A Knowledge Operating System for Home Assistant — a single
Docker container (s6-overlay v3) running six services:

| Service | Port | Purpose |
|---------|------|---------|
| FastAPI | 8000 | Main API + HA ingress |
| MeiliSearch | 7700 | Full-text search |
| Qdrant | 6333 | Semantic vector search |
| Oxigraph | 7878 | RDF/SPARQL graph store |
| Redis | 6379 | Cache, agent memory, pub/sub |
| Git sync daemon | — | Bidirectional vault sync |

**Key features:**
- Hybrid search (fulltext + semantic + graph)
- Git-backed Markdown vault (Obsidian-compatible)
- MCP server for AI agent integration
- Multi-agent orchestration layer connected to the HA Event Bus
- AI agent memory (facts, conversations, working memory)

**Multi-agent orchestration** (`exocortex/exocortex/agents/`):
- `ha_websocket.py` — persistent WS client to HA Event Bus with exponential backoff
- `event_filter.py` — domain filter, debounce, vectorisation router
- `orchestrator.py` — GoT Dispatcher with RAG context (Redis + Qdrant + SPARQL)
- `domain_agents.py` — Climate, Security, Lighting, Communication agents
- `llm_client.py` — async Ollama client
- `ha_mcp_client.py` — HA Supervisor REST API client
- `knoten_k.py` — decision audit agent (RDF + Redis)

**Versioning scheme:** `{semver}.{packaging_patch}`, e.g. `1.0.0.1`.
- Code changes → bump the `{semver}` part in `exocortex/config.yaml` (e.g. to `1.1.0.0`). The push to `main` under `exocortex/` starts the workflow, which builds every version whose images are not in the registry yet. Until then Home Assistant already sees the new version, so the build starts on the push, not on the next schedule.
- Force rebuild without code changes → the workflow increments the packaging suffix

**To trigger a rebuild:**
Actions → Sync Add-ons → Run workflow → slug: `exocortex`, Force rebuild: ✓

**Architecture support:** `amd64`, `aarch64` only (Ubuntu base image required for
the bundled Oxigraph binary; Alpine is not used).

---

## Do Not

- **Do not** copy full application source code into this repository.
- **Do not** modify `repository.json` `url` or `maintainer` unless the GitHub
  organisation changes.
- **Do not** remove the `image:` field from any `config.yaml` – without it HA
  would try to build from source and fail (no Dockerfile present).
- **Do not** hardcode the `GITHUB_TOKEN` or any other secrets.
- **Do not** modify the exocortex add-on's internal Oxigraph service configuration
  — it is not the same as the former standalone Oxigraph add-on.
