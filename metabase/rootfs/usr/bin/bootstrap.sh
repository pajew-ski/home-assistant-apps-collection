#!/usr/bin/with-contenv bashio
# Idempotent first-run setup for Metabase:
#   1. Create admin user (first run only)
#   2. Connect HA Recorder database (if configured)
set -e

MB_URL="http://127.0.0.1:3000"
ADMIN_FILE="/data/admin.json"

# ── 1. Admin user setup ─────────────────────────────────────────────────────
if [ ! -f "$ADMIN_FILE" ]; then
    bashio::log.info "First run detected – running Metabase setup..."

    # Check if the setup endpoint is available
    SETUP_TOKEN=$(curl -sf "${MB_URL}/api/session/properties" \
        | jq -r '."setup-token" // empty')

    if [ -z "$SETUP_TOKEN" ]; then
        bashio::log.fatal "Metabase setup token not available. Is Metabase already configured?"
        bashio::log.fatal "If so, delete /data/metabase.db* and restart to reset."
        exit 1
    fi

    # Generate admin credentials
    ADMIN_EMAIL="admin@homeassistant.local"
    ADMIN_PASS=$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24)

    # Run the setup API
    SETUP_RESP=$(curl -sf -X POST "${MB_URL}/api/setup" \
        -H "Content-Type: application/json" \
        -d "{
            \"token\": \"${SETUP_TOKEN}\",
            \"user\": {
                \"email\": \"${ADMIN_EMAIL}\",
                \"password\": \"${ADMIN_PASS}\",
                \"first_name\": \"Home\",
                \"last_name\": \"Assistant\",
                \"site_name\": \"Home Assistant Analytics\"
            },
            \"prefs\": {
                \"site_name\": \"Home Assistant Analytics\",
                \"allow_tracking\": false
            }
        }")

    if echo "$SETUP_RESP" | jq -e .id >/dev/null 2>&1; then
        # Save credentials for session management
        jq -n --arg e "$ADMIN_EMAIL" --arg p "$ADMIN_PASS" \
            '{"email":$e,"password":$p}' > "$ADMIN_FILE"
        chmod 600 "$ADMIN_FILE"
        bashio::log.info "Metabase admin user created (${ADMIN_EMAIL})."
    else
        bashio::log.fatal "Metabase setup failed: ${SETUP_RESP}"
        exit 1
    fi
else
    bashio::log.info "Metabase already configured (admin.json exists)."
fi

# ── 2. Connect Recorder database ────────────────────────────────────────────
RECORDER_URL=$(bashio::config 'recorder_db_url')

# Auto-detect from HA configuration if not set
if [ -z "$RECORDER_URL" ] && [ -f /config/configuration.yaml ]; then
    RECORDER_URL=$(grep -A5 'recorder:' /config/configuration.yaml 2>/dev/null \
        | grep 'db_url:' \
        | sed 's/.*db_url:\s*//' \
        | sed 's/^["'"'"']//' | sed 's/["'"'"']$//' \
        | head -1) || true
fi

if [ -z "$RECORDER_URL" ]; then
    # Default: auto-connect the HA SQLite database
    HA_SQLITE="/config/home-assistant_v2.db"
    if [ -f "$HA_SQLITE" ]; then
        bashio::log.info "No recorder DB URL configured – auto-connecting default SQLite DB."
        RECORDER_URL="sqlite:///${HA_SQLITE}"
    else
        bashio::log.info "No recorder DB URL configured and no SQLite DB found at ${HA_SQLITE}."
        bashio::log.info "Configure 'recorder_db_url' or add the database manually in Metabase."
        exit 0
    fi
fi

# Get session for API calls
ADMIN_EMAIL=$(jq -r .email "$ADMIN_FILE")
ADMIN_PASS=$(jq -r .password "$ADMIN_FILE")
SESSION=$(curl -sf -X POST "${MB_URL}/api/session" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASS}\"}" \
    | jq -r .id)

if [ -z "$SESSION" ] || [ "$SESSION" = "null" ]; then
    bashio::log.warning "Could not obtain session for DB setup. Skipping."
    exit 0
fi

# Check if HA database already exists in Metabase
EXISTING=$(curl -sf "${MB_URL}/api/database" \
    -H "X-Metabase-Session: ${SESSION}" \
    | jq '[.data[] | select(.name == "Home Assistant")] | length')

if [ "$EXISTING" -gt 0 ]; then
    bashio::log.info "Home Assistant database already connected in Metabase."
    exit 0
fi

# Determine engine and connection details
if echo "$RECORDER_URL" | grep -qi '^postgresql://\|^postgres://'; then
    # PostgreSQL: postgresql://user:pass@host:port/dbname
    ENGINE="postgres"
    DB_HOST=$(echo "$RECORDER_URL" | sed 's|.*://[^@]*@||' | sed 's|/.*||' | sed 's|:.*||')
    DB_PORT=$(echo "$RECORDER_URL" | sed 's|.*://[^@]*@||' | sed 's|/.*||' | grep -o ':[0-9]*' | tr -d ':')
    DB_PORT=${DB_PORT:-5432}
    DB_NAME=$(echo "$RECORDER_URL" | sed 's|.*://[^@]*@[^/]*/||' | sed 's|?.*||')
    DB_USER=$(echo "$RECORDER_URL" | sed 's|.*://||' | sed 's|:.*||')
    DB_PASS=$(echo "$RECORDER_URL" | sed 's|.*://[^:]*:||' | sed 's|@.*||')

    curl -sf -X POST "${MB_URL}/api/database" \
        -H "Content-Type: application/json" \
        -H "X-Metabase-Session: ${SESSION}" \
        -d "{
            \"engine\": \"${ENGINE}\",
            \"name\": \"Home Assistant\",
            \"details\": {
                \"host\": \"${DB_HOST}\",
                \"port\": ${DB_PORT},
                \"dbname\": \"${DB_NAME}\",
                \"user\": \"${DB_USER}\",
                \"password\": \"${DB_PASS}\"
            }
        }" >/dev/null

    bashio::log.info "PostgreSQL database connected: ${DB_HOST}:${DB_PORT}/${DB_NAME}"

elif echo "$RECORDER_URL" | grep -qi '^mysql://\|^mysql+pymysql://'; then
    ENGINE="mysql"
    CLEAN_URL=$(echo "$RECORDER_URL" | sed 's|mysql+pymysql://|mysql://|')
    DB_HOST=$(echo "$CLEAN_URL" | sed 's|.*://[^@]*@||' | sed 's|/.*||' | sed 's|:.*||')
    DB_PORT=$(echo "$CLEAN_URL" | sed 's|.*://[^@]*@||' | sed 's|/.*||' | grep -o ':[0-9]*' | tr -d ':')
    DB_PORT=${DB_PORT:-3306}
    DB_NAME=$(echo "$CLEAN_URL" | sed 's|.*://[^@]*@[^/]*/||' | sed 's|?.*||')
    DB_USER=$(echo "$CLEAN_URL" | sed 's|.*://||' | sed 's|:.*||')
    DB_PASS=$(echo "$CLEAN_URL" | sed 's|.*://[^:]*:||' | sed 's|@.*||')

    curl -sf -X POST "${MB_URL}/api/database" \
        -H "Content-Type: application/json" \
        -H "X-Metabase-Session: ${SESSION}" \
        -d "{
            \"engine\": \"${ENGINE}\",
            \"name\": \"Home Assistant\",
            \"details\": {
                \"host\": \"${DB_HOST}\",
                \"port\": ${DB_PORT},
                \"dbname\": \"${DB_NAME}\",
                \"user\": \"${DB_USER}\",
                \"password\": \"${DB_PASS}\"
            }
        }" >/dev/null

    bashio::log.info "MySQL database connected: ${DB_HOST}:${DB_PORT}/${DB_NAME}"

elif echo "$RECORDER_URL" | grep -qi '^sqlite:///'; then
    ENGINE="sqlite"
    SRC_PATH=$(echo "$RECORDER_URL" | sed 's|^sqlite:///||')
    DB_COPY="/data/ha_recorder.db"

    # Create a consistent snapshot using SQLite's VACUUM INTO, which
    # only needs read access to the source and writes a brand-new,
    # self-contained DB file. No lock files (-wal/-shm) are created on
    # the read-only /config mount.
    bashio::log.info "Creating consistent snapshot: ${SRC_PATH} → ${DB_COPY} ..."
    rm -f "$DB_COPY"
    sqlite3 "file:${SRC_PATH}?mode=ro&immutable=1" "VACUUM INTO '${DB_COPY}';"

    # Pass the plain file path to Metabase. The SQLite driver's
    # confirm_file_is_sqlite check opens the value as a regular file,
    # so URI query parameters (e.g. ?mode=ro) cause a
    # FileNotFoundException.
    curl -sf -X POST "${MB_URL}/api/database" \
        -H "Content-Type: application/json" \
        -H "X-Metabase-Session: ${SESSION}" \
        -d "{
            \"engine\": \"${ENGINE}\",
            \"name\": \"Home Assistant\",
            \"details\": {
                \"db\": \"${DB_COPY}\"
            }
        }" >/dev/null

    bashio::log.info "SQLite database connected (copy): ${DB_COPY}"

else
    bashio::log.warning "Unsupported recorder DB URL scheme: ${RECORDER_URL}"
    bashio::log.warning "Supported: postgresql://, mysql://, mysql+pymysql://, sqlite:///"
    bashio::log.warning "Add the database manually through the Metabase UI."
fi
