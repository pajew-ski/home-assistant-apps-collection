#!/bin/bash
# Copies the model from /config/<folder> into the add-on's own data directory,
# so Structurizr never writes into the git checkout of /config, then runs
# Structurizr local (read-only) behind nginx on the ingress port.
set -euo pipefail

FOLDER=$(jq -r '.folder // "architecture"' /data/options.json 2>/dev/null || echo architecture)
# Admin input, but it becomes a path: one or more plain segments below /config.
if ! [[ "$FOLDER" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]*(/[A-Za-z0-9_][A-Za-z0-9_.-]*)*$ ]]; then
    echo "Invalid folder '$FOLDER', using 'architecture'"
    FOLDER=architecture
fi
SOURCE=/homeassistant/$FOLDER
TARGET=/data/workspace
mkdir -p "$TARGET"

copy_model() {
    [ -f "$SOURCE/workspace.dsl" ] || { echo "No model at $SOURCE/workspace.dsl"; return; }
    # shortcut: deleted source files stay in $TARGET until restart; fine while the model only grows.
    if ! diff -rq --exclude=.structurizr --exclude=workspace.json "$SOURCE" "$TARGET" >/dev/null 2>&1; then
        cp -a "$SOURCE/." "$TARGET/"
        echo "Model copied: $(date -u +%FT%TZ)"
    fi
}

# Structurizr parses again only when a file in $TARGET changes, and live.groovy
# reads the states only while parsing. So: when a watched state changes,
# touch live.groovy; the parse runs, and open pages reload by themselves.
# Which states count is decided in live.groovy alone; here only "changed or not".
fingerprint() {
    local ids
    ids=$(grep -ohE '"ha\.entity" *"[^"]+"' "$TARGET"/*.dsl 2>/dev/null \
        | sed -E 's/.*"ha\.entity" *"([^"]+)"/\1/' | tr ',' '\n' | tr -d ' ' | sort -u | jq -R . | jq -sc .)
    {
        curl -sf -m 8 -H "Authorization: Bearer ${SUPERVISOR_TOKEN:-}" http://supervisor/core/api/states \
            | jq -c --argjson ids "$ids" '[.[] | select(.entity_id as $e | $ids | index($e)) | [.entity_id, .state]] | sort'
        curl -sf -m 8 -H "Authorization: Bearer ${SUPERVISOR_TOKEN:-}" http://supervisor/addons \
            | jq -c '[.data.addons[] | [.slug, .state, .version]] | sort'
    } | sha1sum
}

copy_model
if [ ! -f "$TARGET/workspace.dsl" ]; then
    cp /etc/architecture/empty.dsl "$TARGET/workspace.dsl"
fi
(
    last=""
    while true; do
        sleep 30
        copy_model || true
        now=$(fingerprint || true)
        if [ -n "$last" ] && [ "$now" != "$last" ] && [ -f "$TARGET/live.groovy" ]; then
            touch "$TARGET/live.groovy"
        fi
        last=$now
    done
) &

nginx -c /etc/architecture/nginx.conf

cd "$TARGET"
export STRUCTURIZR_EDITABLE=false
export STRUCTURIZR_AUTOREFRESHINTERVAL=5000
export STRUCTURIZR_THEMES=/usr/local/structurizr-themes
exec java -Xmx256m -XX:+UseSerialGC -Dserver.port=8080 -Dserver.address=127.0.0.1 -Dio.netty.noUnsafe=true \
    --enable-native-access=ALL-UNNAMED -jar /usr/local/structurizr.war local "$TARGET"
