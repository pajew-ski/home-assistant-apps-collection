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

| Add-on | Version | Description | Source |
|--------|---------|-------------|--------|
| [Prompts](./prompts/) | 1.0.3 | 100+ KI-Prompting-Strategien – durchsuchbar, filterbar, sofort kopierbar. | [pajew-ski/prompts](https://github.com/pajew-ski/prompts) |
| [Open Entrainer](./open-entrainer/) | 2026.3.6 | Binaural beats generator for brainwave entrainment – Delta, Theta, Alpha, Beta, Gamma. | [pajew-ski/open-entrainer](https://github.com/pajew-ski/open-entrainer) |
| [Open Desensitizer](./open-desensitizer/) | 2026.3.6 | Bilateral stimulation tool for stress reduction and relaxation via guided eye movement. | [pajew-ski/open-desensitizer](https://github.com/pajew-ski/open-desensitizer) |

## How It Works

Each add-on in this collection is mirrored from its upstream source repository.
The `config.yaml` and `build.yaml` files are synced automatically. Pre-built
Docker images are published to the GitHub Container Registry (ghcr.io) and
referenced from each add-on's `config.yaml` via the `image` field.

The [sync workflow](./.github/workflows/sync-addons.yml) runs daily and:
- Detects version bumps in upstream repositories
- Rebuilds multi-arch Docker images (amd64, aarch64, armv7, armhf, i386)
- Pushes images to `ghcr.io/pajew-ski/home-assistant-apps-collection/`
- Updates the mirrored `config.yaml` and commits the change

## Adding a New Add-on

See [CLAUDE.md](./CLAUDE.md) for the step-by-step instructions used when
extending this collection programmatically.

## License

Each add-on retains the license of its upstream source repository.
