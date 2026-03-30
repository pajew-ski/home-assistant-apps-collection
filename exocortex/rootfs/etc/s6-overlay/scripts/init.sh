#!/command/with-contenv bash
# shellcheck shell=bash
set -euo pipefail

CONFIG_PATH="/data/options.json"

echo "[init] Exocortex initialization starting..."

# ── Load config from HA Add-on Options ──────────────────────────────
GITHUB_REPO=$(jq -r '.github_repo // ""' "$CONFIG_PATH")
GITHUB_TOKEN=$(jq -r '.github_token // ""' "$CONFIG_PATH")
GITHUB_BRANCH=$(jq -r '.github_branch // "main"' "$CONFIG_PATH")
MEILI_KEY=$(jq -r '.meilisearch_master_key // ""' "$CONFIG_PATH")
REDIS_PASSWORD=$(jq -r '.redis_password // ""' "$CONFIG_PATH")
LOG_LEVEL=$(jq -r '.log_level // "info"' "$CONFIG_PATH")
SYNC_INTERVAL=$(jq -r '.sync_interval_minutes // 5' "$CONFIG_PATH")
WEBHOOK_SECRET=$(jq -r '.webhook_secret // ""' "$CONFIG_PATH")
AUTO_PUSH=$(jq -r '.auto_push // true' "$CONFIG_PATH")
ENABLE_SEMANTIC=$(jq -r '.enable_semantic_search // true' "$CONFIG_PATH")
EMBEDDING_MODEL=$(jq -r '.embedding_model // "all-MiniLM-L6-v2"' "$CONFIG_PATH")

# ── Set environment variables for s6 services ────────────────────────
S6_ENV="/var/run/s6/container_environment"
mkdir -p "$S6_ENV"

printf "%s" "$MEILI_KEY"        > "${S6_ENV}/MEILI_MASTER_KEY"
printf "%s" "$REDIS_PASSWORD"   > "${S6_ENV}/REDIS_PASSWORD"
printf "%s" "$LOG_LEVEL"        > "${S6_ENV}/LOG_LEVEL"
printf "%s" "$GITHUB_REPO"      > "${S6_ENV}/GITHUB_REPO"
printf "%s" "$GITHUB_TOKEN"     > "${S6_ENV}/GITHUB_TOKEN"
printf "%s" "$GITHUB_BRANCH"    > "${S6_ENV}/GITHUB_BRANCH"
printf "%s" "$SYNC_INTERVAL"    > "${S6_ENV}/SYNC_INTERVAL_MINUTES"
printf "%s" "$WEBHOOK_SECRET"   > "${S6_ENV}/WEBHOOK_SECRET"
printf "%s" "$AUTO_PUSH"        > "${S6_ENV}/AUTO_PUSH"
printf "%s" "$ENABLE_SEMANTIC"  > "${S6_ENV}/ENABLE_SEMANTIC_SEARCH"
printf "%s" "$EMBEDDING_MODEL"  > "${S6_ENV}/EMBEDDING_MODEL"

# ── Configure Git ────────────────────────────────────────────────────
git config --global user.email "exocortex@homeassistant.local"
git config --global user.name "Exocortex"
git config --global credential.helper store
git config --global init.defaultBranch main

# Store Git credentials for push
if [ -n "$GITHUB_TOKEN" ] && [ -n "$GITHUB_REPO" ]; then
    REPO_HOST=$(echo "$GITHUB_REPO" | sed 's|https://||' | cut -d'/' -f1)
    echo "https://exocortex:${GITHUB_TOKEN}@${REPO_HOST}" > ~/.git-credentials
    echo "[init] Git credentials configured for ${REPO_HOST}"
fi

# ── Clone repo if not present ────────────────────────────────────────
if [ -n "$GITHUB_REPO" ]; then
    if [ ! -d "/data/repo/.git" ]; then
        echo "[init] Cloning repository: ${GITHUB_REPO}"
        git clone --branch "$GITHUB_BRANCH" "$GITHUB_REPO" /data/repo
        echo "[init] Clone complete. Will trigger full reindex."
        touch /data/.needs_full_reindex
    else
        echo "[init] Repository exists. Pulling latest changes..."
        cd /data/repo
        git fetch origin 2>/dev/null || echo "[init] Warning: fetch failed (offline?)"
        git merge --ff-only "origin/${GITHUB_BRANCH}" 2>/dev/null || \
            echo "[init] Warning: fast-forward merge not possible, will sync later"
    fi
else
    echo "[init] No GitHub repo configured. Creating empty repo."
    if [ ! -d "/data/repo/.git" ]; then
        mkdir -p /data/repo
        cd /data/repo
        git init
        git checkout -b main
    fi
fi

# ── Generate Redis config ────────────────────────────────────────────
cat > /etc/redis/exocortex.conf <<EOF
bind 127.0.0.1
port 6379
dir /data/redis
save 900 1
save 300 10
save 60 10000
appendonly yes
appendfsync everysec
maxmemory 100mb
maxmemory-policy allkeys-lru
protected-mode yes
loglevel notice
logfile ""
EOF

if [ -n "$REDIS_PASSWORD" ]; then
    echo "requirepass $REDIS_PASSWORD" >> /etc/redis/exocortex.conf
fi

# ── Generate nginx config ────────────────────────────────────────────
cat > /etc/nginx/http.d/exocortex.conf <<'EOF'
server {
    listen 8080 default_server;

    client_max_body_size 50m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Ingress-Path $http_x_ingress_path;
        proxy_http_version 1.1;

        # WebSocket support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # SSE support
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400;
    }

    # SPARQL endpoint (direct access for debug)
    location /sparql {
        proxy_pass http://127.0.0.1:7878/;
        proxy_set_header Host $host;
    }
}
EOF

echo "[init] Initialization complete."
