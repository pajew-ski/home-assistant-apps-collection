#!/usr/bin/env python3
"""Wikipedia Pulse: the edit stream of all Wikimedia wikis, counted live.

Reads the public EventStream mediawiki.recentchange (Server-Sent Events, no key)
in one long-lived connection and serves what it counted as one JSON object on
http://<host>:8104/. Home Assistant polls that with a rest sensor; nothing is
pushed, so a stopped add-on shows up as unavailable, not as a frozen value.

What it counts:
  per_minute  edits per minute over the last five minutes: all wikis, humans,
              bots, new pages, and the largest wikis by name
  hot         articles (namespace 0) on the wikis in HOT_WIKIS with the most
              distinct human editors in the last hour; many people editing one
              article at once is how breaking news shows up in Wikipedia

The stream closes connections from time to time; the reader reconnects with
Last-Event-ID, so no event is lost within the stream's retention. If nothing
arrives for STALL seconds the connection is treated as dead.

Standard library only. Self-test without network: python3 pulse.py --test
"""
import json
import sys
import threading
import time
import urllib.request
from collections import Counter, deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STREAM = "https://stream.wikimedia.org/v2/stream/recentchange"
# Wikimedia's User-Agent policy asks for a contact; this is the add-on's home.
UA = "wikipedia-pulse/1 (https://github.com/pajew-ski/home-assistant-apps-collection; Home Assistant add-on)"
PORT = 8104
RATE_WINDOW = 300
HOT_WINDOW = 3600
HOT_WIKIS = ("dewiki", "enwiki")
NAMED_WIKIS = ("dewiki", "enwiki", "wikidatawiki", "commonswiki")
HOT_MIN_EDITORS = 2
HOT_TOP = 10
STALL = 60


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds") if t else None


class Pulse:
    def __init__(self, now=time.time):
        self.now = now
        self.lock = threading.Lock()
        self.started = now()
        self.events = deque()  # (t, wiki, bot, new)
        self.hot = {w: deque() for w in HOT_WIKIS}  # (t, title, user)
        self.last_event = None
        self.connected = False
        self.reconnects = 0

    def add(self, e):
        """One recentchange event. Only edits and page creations count; log entries and
        categorisation are bookkeeping, not writing."""
        if e.get("type") not in ("edit", "new"):
            return
        t = self.now()
        wiki, bot, new = e.get("wiki"), bool(e.get("bot")), e.get("type") == "new"
        with self.lock:
            self.last_event = t
            self.events.append((t, wiki, bot, new))
            if wiki in self.hot and not bot and e.get("namespace") == 0 and e.get("title"):
                self.hot[wiki].append((t, e["title"], e.get("user")))

    def _prune(self, t):
        while self.events and self.events[0][0] < t - RATE_WINDOW:
            self.events.popleft()
        for q in self.hot.values():
            while q and q[0][0] < t - HOT_WINDOW:
                q.popleft()

    def snapshot(self):
        t = self.now()
        with self.lock:
            self._prune(t)
            window = min(RATE_WINDOW, max(60.0, t - self.started))
            per = 60.0 / window
            counts = Counter()
            for _, wiki, bot, new in self.events:
                counts["all"] += 1
                counts["bots" if bot else "humans"] += 1
                counts["new"] += new
                if wiki in NAMED_WIKIS:
                    counts[wiki] += 1
            hot = {}
            for wiki, q in self.hot.items():
                edits, editors = Counter(), {}
                for _, title, user in q:
                    edits[title] += 1
                    editors.setdefault(title, set()).add(user)
                ranked = sorted((t_ for t_ in edits if len(editors[t_]) >= HOT_MIN_EDITORS),
                                key=lambda t_: (len(editors[t_]), edits[t_]), reverse=True)[:HOT_TOP]
                hot[wiki] = [{"title": t_, "edits": edits[t_], "editors": len(editors[t_])} for t_ in ranked]
            return {
                "updated": iso(t), "since": iso(self.started), "connected": self.connected,
                "last_event": iso(self.last_event), "reconnects": self.reconnects,
                "window_s": round(window), "warm": t - self.started >= RATE_WINDOW,
                "per_minute": {k: round(counts[k] * per, 1)
                               for k in ("all", "humans", "bots", "new") + NAMED_WIKIS},
                "hot": hot,
            }


def sse(lines):
    """(id, data) per event from an iterable of decoded lines."""
    data, ident = [], None
    for line in lines:
        line = line.rstrip("\r\n")
        if not line:
            if data:
                yield ident, "\n".join(data)
            data = []
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if field == "data":
            data.append(value)
        elif field == "id":
            ident = value


def read_forever(pulse):
    last_id, delay = None, 1
    while True:
        headers = {"User-Agent": UA, "Accept": "text/event-stream"}
        if last_id:
            headers["Last-Event-ID"] = last_id
        try:
            with urllib.request.urlopen(urllib.request.Request(STREAM, headers=headers), timeout=STALL) as r:
                pulse.connected, delay = True, 1
                for ident, data in sse(line.decode("utf-8", "replace") for line in r):
                    last_id = ident or last_id
                    try:
                        pulse.add(json.loads(data))
                    except ValueError:
                        continue
        except Exception as e:  # noqa: BLE001 - every failure means: reconnect
            print(f"stream: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        pulse.connected = False
        pulse.reconnects += 1
        time.sleep(delay)
        delay = min(delay * 2, 60)


def serve(pulse):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server API
            body = json.dumps(pulse.snapshot(), ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # one poll a minute is not worth a log line
            pass

    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


def test():
    clock = [1000.0]
    p = Pulse(now=lambda: clock[0])
    raw = [":ok", "", "event: message", 'id: [{"o":1}]',
           'data: {"type":"edit","wiki":"dewiki","namespace":0,"title":"A","user":"u1","bot":false}', "",
           'data: {"type":"log","wiki":"dewiki"}', ""]
    events = list(sse(raw))
    assert events[0][0] == '[{"o":1}]' and len(events) == 2, events
    for _, d in events:
        p.add(json.loads(d))
    for user in ("u2", "u2", "u3"):
        p.add({"type": "edit", "wiki": "dewiki", "namespace": 0, "title": "A", "user": user})
    p.add({"type": "edit", "wiki": "dewiki", "namespace": 0, "title": "B", "user": "u9"})  # one editor: not hot
    p.add({"type": "edit", "wiki": "dewiki", "namespace": 2, "title": "User:X", "user": "u4"})  # not an article
    p.add({"type": "edit", "wiki": "enwiki", "namespace": 0, "title": "C", "user": "bot", "bot": True})
    p.add({"type": "new", "wiki": "wikidatawiki", "namespace": 0, "title": "Q1", "user": "u5"})
    s = p.snapshot()
    assert s["per_minute"]["all"] == 8 and s["window_s"] == 60, s  # first minute: divide by one minute
    assert s["per_minute"]["bots"] == 1 and s["per_minute"]["new"] == 1 and s["per_minute"]["dewiki"] == 6, s
    assert s["hot"]["dewiki"] == [{"title": "A", "edits": 4, "editors": 3}] and s["hot"]["enwiki"] == [], s
    assert not s["warm"]
    clock[0] += 600  # rate window passed, hot window not
    s = p.snapshot()
    assert s["per_minute"]["all"] == 0 and s["warm"] and s["hot"]["dewiki"][0]["title"] == "A", s
    clock[0] += 3600
    assert p.snapshot()["hot"]["dewiki"] == []
    print("ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--test"]:
        test()
    else:
        pulse = Pulse()
        threading.Thread(target=read_forever, args=(pulse,), daemon=True).start()
        serve(pulse)
