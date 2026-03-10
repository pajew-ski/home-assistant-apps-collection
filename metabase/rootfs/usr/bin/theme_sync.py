#!/usr/bin/env python3
"""
Fetch the active Home Assistant theme colours via the WebSocket API
and generate a Metabase CSS override file.

Runs as a one-shot on startup and then watches for theme changes
via subscribe_events (frontend_updated).
"""

import json
import os
import signal
import socket
import subprocess
import sys
import time

SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
WS_URL_HOST = "supervisor"
WS_URL_PORT = 80
WS_PATH = "/core/websocket"
CSS_PATH = "/data/ha-theme.css"

# HA default colours (fallback when no theme is set)
DEFAULTS = {
    "primary-color": "#03a9f4",
    "accent-color": "#ff9800",
    "primary-background-color": "#fafafa",
    "card-background-color": "#ffffff",
    "primary-text-color": "#212121",
}

# ── Minimal WebSocket client (no external deps) ─────────────────────────────
# We only need text frames; no masking required from server→client direction
# but we DO need to mask client→server frames per RFC 6455.

import hashlib
import base64
import struct
import random


def _ws_connect():
    """Open a raw WebSocket connection to the HA supervisor."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(30)
    sock.connect((WS_URL_HOST, WS_URL_PORT))

    # WebSocket handshake
    key = base64.b64encode(random.randbytes(16)).decode()
    handshake = (
        f"GET {WS_PATH} HTTP/1.1\r\n"
        f"Host: {WS_URL_HOST}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n"
        f"\r\n"
    )
    sock.sendall(handshake.encode())

    # Read HTTP response headers
    resp = b""
    while b"\r\n\r\n" not in resp:
        resp += sock.recv(4096)
    if b"101" not in resp.split(b"\r\n")[0]:
        raise ConnectionError(f"WebSocket handshake failed: {resp[:200]}")

    return sock


def _ws_recv(sock):
    """Read one WebSocket text frame and return decoded string."""
    header = sock.recv(2)
    if len(header) < 2:
        raise ConnectionError("Connection closed")
    payload_len = header[1] & 0x7F
    if payload_len == 126:
        payload_len = struct.unpack(">H", sock.recv(2))[0]
    elif payload_len == 127:
        payload_len = struct.unpack(">Q", sock.recv(8))[0]

    data = b""
    while len(data) < payload_len:
        chunk = sock.recv(payload_len - len(data))
        if not chunk:
            raise ConnectionError("Connection closed during read")
        data += chunk

    return data.decode("utf-8")


def _ws_send(sock, text):
    """Send a masked WebSocket text frame."""
    payload = text.encode("utf-8")
    frame = bytearray()
    frame.append(0x81)  # FIN + text opcode

    length = len(payload)
    if length < 126:
        frame.append(0x80 | length)  # MASK bit set
    elif length < 65536:
        frame.append(0x80 | 126)
        frame.extend(struct.pack(">H", length))
    else:
        frame.append(0x80 | 127)
        frame.extend(struct.pack(">Q", length))

    mask = random.randbytes(4)
    frame.extend(mask)
    frame.extend(bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
    sock.sendall(frame)


# ── Theme logic ──────────────────────────────────────────────────────────────

def fetch_themes(sock, msg_id):
    """Send frontend/get_themes and return (themes_dict, default_theme_name)."""
    _ws_send(sock, json.dumps({"id": msg_id, "type": "frontend/get_themes"}))

    while True:
        raw = _ws_recv(sock)
        msg = json.loads(raw)
        if msg.get("id") == msg_id:
            themes = msg.get("result", {}).get("themes", {})
            default_theme = msg.get("result", {}).get("default_theme", "")
            return themes, default_theme


def resolve_colours(themes, default_theme):
    """Extract colour values from the active theme, with fallback to defaults."""
    colours = dict(DEFAULTS)

    if default_theme and default_theme in themes:
        theme = themes[default_theme]
        for key in DEFAULTS:
            if key in theme:
                colours[key] = theme[key]

    return colours


def lighten_hex(hex_colour, factor=0.85):
    """Lighten a hex colour toward white by the given factor (0=unchanged, 1=white)."""
    hex_colour = hex_colour.lstrip("#")
    if len(hex_colour) == 3:
        hex_colour = "".join(c * 2 for c in hex_colour)
    r, g, b = int(hex_colour[0:2], 16), int(hex_colour[2:4], 16), int(hex_colour[4:6], 16)
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


def generate_css(colours):
    """Generate Metabase CSS override from HA theme colours."""
    primary = colours["primary-color"]
    primary_light = lighten_hex(primary, 0.85)
    bg = colours["primary-background-color"]
    card_bg = colours["card-background-color"]
    text = colours["primary-text-color"]
    accent = colours["accent-color"]

    return f"""\
/* Auto-generated from Home Assistant theme – do not edit */
:root {{
    --mb-color-brand: {primary};
    --mb-color-brand-light: {primary_light};
    --mb-color-focus: {primary};
    --mb-color-bg-white: {card_bg};
    --mb-color-bg-light: {bg};
    --mb-color-text-dark: {text};
    --mb-color-text-medium: {text}cc;
    --mb-color-saturated-primary: {primary};
    --mb-color-accent1: {accent};
}}
.Nav {{
    background-color: {primary} !important;
}}
"""


def write_css(css_text):
    """Write CSS to disk and reload nginx if content changed."""
    old = ""
    if os.path.exists(CSS_PATH):
        with open(CSS_PATH) as f:
            old = f.read()

    if css_text != old:
        with open(CSS_PATH, "w") as f:
            f.write(css_text)
        # Reload nginx so sub_filter picks up any structural changes
        subprocess.run(["nginx", "-s", "reload"], capture_output=True)
        return True
    return False


# ── Main loop ────────────────────────────────────────────────────────────────

def main():
    if not SUPERVISOR_TOKEN:
        print("[theme_sync] No SUPERVISOR_TOKEN – writing default CSS.", flush=True)
        write_css(generate_css(DEFAULTS))
        return

    msg_id = 1

    while True:
        try:
            sock = _ws_connect()

            # Step 1: receive auth_required
            _ws_recv(sock)

            # Step 2: authenticate
            _ws_send(sock, json.dumps({
                "type": "auth",
                "access_token": SUPERVISOR_TOKEN,
            }))
            auth_resp = json.loads(_ws_recv(sock))
            if auth_resp.get("type") != "auth_ok":
                print(f"[theme_sync] Auth failed: {auth_resp}", flush=True)
                time.sleep(30)
                continue

            # Step 3: fetch current themes
            msg_id += 1
            themes, default_theme = fetch_themes(sock, msg_id)
            colours = resolve_colours(themes, default_theme)
            css = generate_css(colours)
            changed = write_css(css)
            if changed:
                print("[theme_sync] CSS updated from HA theme.", flush=True)
            else:
                print("[theme_sync] CSS unchanged.", flush=True)

            # Step 4: subscribe to theme change events
            msg_id += 1
            _ws_send(sock, json.dumps({
                "id": msg_id,
                "type": "subscribe_events",
                "event_type": "themes_updated",
            }))

            # Step 5: wait for theme change events
            while True:
                raw = _ws_recv(sock)
                msg = json.loads(raw)

                if msg.get("type") == "event" and \
                   msg.get("event", {}).get("event_type") == "themes_updated":
                    print("[theme_sync] Theme change detected, refreshing...", flush=True)
                    msg_id += 1
                    themes, default_theme = fetch_themes(sock, msg_id)
                    colours = resolve_colours(themes, default_theme)
                    css = generate_css(colours)
                    if write_css(css):
                        print("[theme_sync] CSS updated.", flush=True)

        except Exception as e:
            print(f"[theme_sync] Error: {e} – reconnecting in 30s", flush=True)
            time.sleep(30)


if __name__ == "__main__":
    main()
