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
- `addons-registry.json` – machine-readable registry of all mirrored add-ons
- One subdirectory per add-on with `config.yaml` (+ `build.yaml`, optional assets)
- `.github/workflows/sync-addons.yml` – automation that keeps everything in sync

Pre-built Docker images live in
`ghcr.io/pajew-ski/home-assistant-apps-collection/` and are referenced via the
`image` field in each add-on's `config.yaml`.

---

## Repository Structure

```
home-assistant-apps-collection/
├── repository.json            # HA repository descriptor
├── addons-registry.json       # Registry of mirrored add-ons
├── README.md
├── CLAUDE.md                  # This file
├── .github/
│   └── workflows/
│       └── sync-addons.yml    # Daily sync + Docker build workflow
└── <slug>/                    # One directory per add-on
    ├── config.yaml            # Mirrored + image field injected
    ├── build.yaml             # Mirrored
    ├── icon.png               # Optional – mirrored if present upstream
    └── logo.png               # Optional – mirrored if present upstream
```

### Key files explained

| File | Purpose |
|------|---------|
| `repository.json` | Identifies the repo to Home Assistant (name, url, maintainer) |
| `addons-registry.json` | Source of truth for which add-ons are mirrored and from where |
| `<slug>/config.yaml` | HA add-on manifest; must include `image:` pointing to ghcr.io |
| `<slug>/build.yaml` | Maps architectures to base images; used by the Docker build step |
| `.github/workflows/sync-addons.yml` | Checks upstream versions, builds images, commits updates |

---

## Adding a New Add-on

Follow these steps exactly. Do **not** copy full source code into this repo.

### 1. Verify the upstream repository

The upstream must be a valid Home Assistant add-on, meaning it has:
- A `config.yaml` (or `config.json`) with at minimum `name`, `version`, `slug`,
  `arch`, `startup`, and `boot` fields.
- A `Dockerfile` that accepts `ARG BUILD_FROM` (HA build convention).

### 2. Register in `addons-registry.json`

Add an entry to the `addons` array:

```json
{
  "slug": "<slug>",
  "name": "<Human-readable name>",
  "source": "https://github.com/<owner>/<repo>",
  "branch": "main",
  "sync_files": ["config.yaml", "build.yaml", "icon.png", "logo.png"],
  "image_prefix": "ghcr.io/pajew-ski/home-assistant-apps-collection/{arch}-<slug>"
}
```

### 3. Create the add-on directory

```
mkdir <slug>/
```

Download `config.yaml` and `build.yaml` from the upstream repo:

```bash
curl -sf https://raw.githubusercontent.com/<owner>/<repo>/main/config.yaml \
  -o <slug>/config.yaml
curl -sf https://raw.githubusercontent.com/<owner>/<repo>/main/build.yaml \
  -o <slug>/build.yaml
```

Then append the `image` field to `config.yaml` if it is not already present:

```yaml
image: "ghcr.io/pajew-ski/home-assistant-apps-collection/{arch}-<slug>"
```

Download optional display assets:

```bash
curl -sf https://raw.githubusercontent.com/<owner>/<repo>/main/icon.png \
  -o <slug>/icon.png 2>/dev/null || true
curl -sf https://raw.githubusercontent.com/<owner>/<repo>/main/logo.png \
  -o <slug>/logo.png 2>/dev/null || true
```

### 4. Add a sync step to the workflow

Open `.github/workflows/sync-addons.yml` and duplicate the block for `prompts`
(the section between the two `# ---` dividers), replacing every occurrence of
`prompts` with the new `<slug>` and updating the upstream GitHub URL.

The pattern is:
1. A step named `Check <slug> for updates` that fetches the upstream version and
   compares it to the local one, outputting `needs_update`, `upstream`, and
   `current`.
2. A step named `Sync <slug> config files` that downloads the sync files and
   injects the `image` field.
3. A step named `Build and push <slug> Docker images` that clones the upstream
   repo, iterates over all architectures, runs `docker buildx build --push`.
4. A step named `Commit and push changes` that commits and pushes any file
   changes.

### 5. Update README.md

Add a row to the **Included Add-ons** table:

```markdown
| [Name](./<slug>/) | x.y.z | Short description | [owner/repo](https://github.com/owner/repo) |
```

### 6. Commit

```
git add .
git commit -m "feat(<slug>): add <Name> add-on"
git push
```

---

## Updating an Existing Add-on Manually

If you need to force-update an add-on without waiting for the daily schedule:

1. Open **Actions** → **Sync Add-ons** → **Run workflow**
2. Enter the `slug` in the *Add-on slug to sync* field (e.g. `prompts`).
3. Check *Force rebuild* if you want to rebuild even though the version number
   has not changed.

Or locally:

```bash
# Update config.yaml from upstream, re-inject image field
curl -sf https://raw.githubusercontent.com/pajew-ski/prompts/main/config.yaml \
  -o prompts/config.yaml
echo 'image: "ghcr.io/pajew-ski/home-assistant-apps-collection/{arch}-prompts"' \
  >> prompts/config.yaml

git add prompts/
git commit -m "chore(prompts): manual sync"
git push
```

---

## Workflow Permissions

The `sync-addons.yml` workflow requires:

| Permission | Reason |
|------------|--------|
| `contents: write` | Commit updated config files |
| `packages: write` | Push images to ghcr.io |

No additional secrets are needed beyond the automatic `GITHUB_TOKEN`.

---

## Known Issues & Lessons Learned

### ghcr.io packages are private by default

Newly pushed images land as **private** packages on ghcr.io. Home Assistant
cannot pull private images (403/401). The workflow therefore calls the GitHub
API after every build to set each package to public:

```bash
gh api --method PATCH \
  -H "Accept: application/vnd.github+json" \
  "/user/packages/container/home-assistant-apps-collection%2F${ARCH}-<slug>" \
  -f visibility=public
```

This step must run **unconditionally** (not gated on `needs_update`), otherwise
packages that were pushed in a previous run and are already at the correct
version will stay private.

### node:22-alpine does not support all HA architectures

`node:22-alpine` (and Node.js 22 in general) only publishes images for:

| Docker platform | HA arch |
|-----------------|---------|
| `linux/amd64`   | `amd64` |
| `linux/arm64`   | `aarch64` |
| `linux/arm/v7`  | `armv7` |

**`armhf` (`linux/arm/v6`) and `i386` (`linux/386`) are not available.**

If an add-on's Dockerfile uses `node:22-alpine` (or any other image that lacks
`linux/arm/v6` / `linux/386`), you must:
1. Remove `armhf` and `i386` from the `arch` list in `config.yaml`.
2. Limit the build loop in the workflow to `amd64 aarch64 armv7`.

Failing to do so causes the Docker buildx step to error with:
> `no match for platform in manifest: not found`

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

## Do Not

- **Do not** copy full application source code into this repository.
- **Do not** modify `repository.json` `url` or `maintainer` unless the GitHub
  organisation changes.
- **Do not** remove the `image:` field from any `config.yaml` – without it HA
  would try to build from source and fail (no Dockerfile present).
- **Do not** hardcode the `GITHUB_TOKEN` or any other secrets.
