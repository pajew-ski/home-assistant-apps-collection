#!/usr/bin/env python3
"""Static apps: one index.html upstream, served by nginx in this collection.

Two commands, both run from the root of the collection:

  check    Decide which static apps need a new image. For each app in
           addons-registry.json with "static_app": true, the newest commit on
           the upstream branch that touched index.html is compared with
           <slug>/.upstream-sha. Writes the build matrix to $GITHUB_OUTPUT.
  publish  Apply what the build jobs pushed: version into <slug>/config.yaml,
           commit into <slug>/.upstream-sha. Reads built/<slug>.json files.

Every merge that changes index.html gets its own version: the commit time as
YYYY.M.D.HHMM (UTC), always higher than the version before. Standard library
only; the runner needs nothing installed.
"""

import datetime
import json
import os
import pathlib
import re
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]


def api(path):
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GH_TOKEN']}"
    req = urllib.request.Request(f"https://api.github.com/{path}", headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def calver(moment):
    return f"{moment.year}.{moment.month}.{moment.day}.{int(moment.strftime('%H%M'))}"


def as_tuple(version):
    return tuple(int(p) if p.isdigit() else 0 for p in re.split(r"[.\-]", version))


def config_value(text, key):
    m = re.search(rf'^{key}:\s*"?([^"\n]*)"?\s*$', text, re.M)
    return m.group(1).strip() if m else ""


def config_archs(text):
    m = re.search(r"^arch:\s*\n((?:\s+-\s*\S+\s*\n)+)", text, re.M)
    return re.findall(r"-\s*(\S+)", m.group(1)) if m else []


def output(**values):
    with open(os.environ.get("GITHUB_OUTPUT", "/dev/stdout"), "a") as f:
        for k, v in values.items():
            f.write(f"{k}={v}\n")


def check():
    wanted = os.environ.get("ADDON", "").strip()
    force = os.environ.get("FORCE", "").strip().lower() == "true"
    registry = json.loads((ROOT / "addons-registry.json").read_text())
    include = []
    for app in registry["addons"]:
        if not app.get("static_app") or (wanted and app["slug"] != wanted):
            continue
        slug = app["slug"]
        repo = app["source"].removeprefix("https://github.com/")
        branch = app.get("branch", "main")
        commits = api(f"repos/{repo}/commits?path=index.html&sha={branch}&per_page=1")
        if not commits:
            print(f"::warning::{slug}: no commit touches index.html on {repo}@{branch}")
            continue
        sha = commits[0]["sha"]
        committed = datetime.datetime.fromisoformat(commits[0]["commit"]["committer"]["date"].replace("Z", "+00:00"))
        sha_file = ROOT / slug / ".upstream-sha"
        last = sha_file.read_text().strip() if sha_file.exists() else ""
        config = (ROOT / slug / "config.yaml").read_text()
        current = config_value(config, "version")
        if sha == last and not force:
            print(f"{slug}: up to date at {current} ({sha[:7]})")
            continue
        version = calver(committed)
        # A forced rebuild of the same commit, or a commit older than the
        # version already published, still has to move the version up, or
        # Home Assistant offers no update.
        if sha == last or as_tuple(version) <= as_tuple(current):
            version = calver(datetime.datetime.now(datetime.timezone.utc))
        print(f"{slug}: {current} -> {version} ({last[:7] or 'none'} -> {sha[:7]})")
        include.append({
            "slug": slug,
            "repo": repo,
            "sha": sha,
            "version": version,
            "port": config_value(config, "ingress_port"),
            "archs": " ".join(config_archs(config)),
        })
    output(matrix=json.dumps({"include": include}), any="true" if include else "false")


def publish():
    built = sorted((ROOT / "built").glob("*.json")) if (ROOT / "built").exists() else []
    done = []
    for path in built:
        result = json.loads(path.read_text())
        slug, version, sha = result["slug"], result["version"], result["sha"]
        config_path = ROOT / slug / "config.yaml"
        config = config_path.read_text()
        config, n = re.subn(r"^version:.*$", f'version: "{version}"', config, count=1, flags=re.M)
        if n != 1:
            sys.exit(f"{slug}/config.yaml has no version line")
        config_path.write_text(config)
        (ROOT / slug / ".upstream-sha").write_text(sha + "\n")
        done.append(f"{slug} {version}")
        print(f"{slug}: published {version} ({sha[:7]})")
    output(summary=", ".join(done))


if __name__ == "__main__":
    {"check": check, "publish": publish}[sys.argv[1]]()
