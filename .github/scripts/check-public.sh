#!/usr/bin/env bash
# Usage: check-public.sh <image without registry, e.g. pajew-ski/home-assistant-apps-collection/amd64-prompts>...
#
# Home Assistant pulls add-on images anonymously, so every image must be public.
# GitHub has no API to change a package's visibility, and a package that a
# workflow pushes for the first time starts out private. This script cannot
# fix that; it checks with an anonymous pull token and turns a private image
# into a visible warning with the link to the one setting that fixes it.
set -uo pipefail
for IMAGE in "$@"; do
  TOKEN=$(curl -sf "https://ghcr.io/token?scope=repository:${IMAGE}:pull" | jq -r '.token // empty')
  if [ -n "$TOKEN" ] && curl -sfI -H "Authorization: Bearer $TOKEN" \
      -H "Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json" \
      "https://ghcr.io/v2/${IMAGE}/manifests/latest" >/dev/null; then
    echo "${IMAGE}: public"
  else
    PACKAGE=$(echo "${IMAGE#*/}" | sed 's|/|%2F|g')
    echo "::warning::${IMAGE} is not publicly pullable, so Home Assistant cannot install it. Set it to public once: https://github.com/users/${IMAGE%%/*}/packages/container/${PACKAGE}/settings (Danger Zone, Change visibility)."
  fi
done
# A private image is a warning, not a failed run: the images are pushed and
# the setting is a one-time manual step.
exit 0
