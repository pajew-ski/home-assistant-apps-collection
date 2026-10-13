#!/bin/bash
# Copies the model from /config/architektur into the add-on's own data
# directory, so Structurizr never writes into the git checkout of /config,
# then runs Structurizr local (read-only) behind nginx on the ingress port.
set -euo pipefail

QUELLE=/homeassistant/architektur
ZIEL=/data/workspace
mkdir -p "$ZIEL"

kopieren() {
    [ -f "$QUELLE/workspace.dsl" ] || { echo "Kein Modell unter $QUELLE/workspace.dsl"; return; }
    # shortcut: deleted source files stay in $ZIEL until restart; fine while the model only grows.
    if ! diff -rq --exclude=.structurizr --exclude=workspace.json "$QUELLE" "$ZIEL" >/dev/null 2>&1; then
        cp -a "$QUELLE/." "$ZIEL/"
        echo "Modell übernommen: $(date -u +%FT%TZ)"
    fi
}

# Structurizr parses again only when a file in $ZIEL changes, and live.groovy
# reads the states only while parsing. So: when a watched state changes,
# touch live.groovy; the parse runs, and open pages reload by themselves.
# Which states count is decided in live.groovy alone; here only "changed or not".
fingerabdruck() {
    local ids
    ids=$(grep -ohE '"ha\.entity" *"[^"]+"' "$ZIEL"/*.dsl 2>/dev/null \
        | sed -E 's/.*"ha\.entity" *"([^"]+)"/\1/' | tr ',' '\n' | tr -d ' ' | sort -u | jq -R . | jq -sc .)
    {
        curl -sf -m 8 -H "Authorization: Bearer ${SUPERVISOR_TOKEN:-}" http://supervisor/core/api/states \
            | jq -c --argjson ids "$ids" '[.[] | select(.entity_id as $e | $ids | index($e)) | [.entity_id, .state]] | sort'
        curl -sf -m 8 -H "Authorization: Bearer ${SUPERVISOR_TOKEN:-}" http://supervisor/addons \
            | jq -c '[.data.addons[] | [.slug, .state, .version]] | sort'
    } | sha1sum
}

kopieren
if [ ! -f "$ZIEL/workspace.dsl" ]; then
    cp /etc/architektur/leer.dsl "$ZIEL/workspace.dsl"
fi
(
    stand=""
    while true; do
        sleep 30
        kopieren || true
        neu=$(fingerabdruck || true)
        if [ -n "$stand" ] && [ "$neu" != "$stand" ] && [ -f "$ZIEL/live.groovy" ]; then
            touch "$ZIEL/live.groovy"
        fi
        stand=$neu
    done
) &

nginx -c /etc/architektur/nginx.conf

cd "$ZIEL"
export STRUCTURIZR_EDITABLE=false
export STRUCTURIZR_AUTOREFRESHINTERVAL=5000
export STRUCTURIZR_THEMES=/usr/local/structurizr-themes
exec java -Xmx256m -XX:+UseSerialGC -Dserver.port=8080 -Dserver.address=127.0.0.1 -Dio.netty.noUnsafe=true \
    --enable-native-access=ALL-UNNAMED -jar /usr/local/structurizr.war local "$ZIEL"
