"""Note templates for common note types."""

from __future__ import annotations

from datetime import datetime, timezone

TEMPLATES: dict[str, dict] = {
    "default": {
        "description": "Basic note with title and tags",
        "frontmatter_defaults": {
            "confidence": 1,
            "status": "draft",
            "type": "note",
        },
        "body": "# {title}\n\n",
    },
    "project": {
        "description": "Project tracking note",
        "frontmatter_defaults": {
            "confidence": 2,
            "status": "active",
            "type": "project",
        },
        "body": (
            "# {title}\n\n"
            "## Goals\n\n"
            "## Tasks\n\n"
            "- [ ] \n\n"
            "## Notes\n\n"
            "## Links\n\n"
        ),
    },
    "person": {
        "description": "Person/contact note",
        "frontmatter_defaults": {
            "confidence": 3,
            "status": "active",
            "type": "person",
        },
        "body": (
            "# {title}\n\n"
            "## Contact\n\n"
            "## Notes\n\n"
            "## Interactions\n\n"
        ),
    },
    "log": {
        "description": "Daily log entry",
        "frontmatter_defaults": {
            "confidence": 2,
            "status": "active",
            "type": "log",
        },
        "body": "# {title}\n\n## Events\n\n## Thoughts\n\n",
    },
    "review": {
        "description": "Weekly/monthly review",
        "frontmatter_defaults": {
            "confidence": 1,
            "status": "draft",
            "type": "review",
        },
        "body": (
            "# {title}\n\n"
            "## Highlights\n\n"
            "## Learnings\n\n"
            "## Next Steps\n\n"
        ),
    },
}


def render_template(
    template_name: str,
    title: str,
    tags: list[str] | None = None,
    confidence: int | None = None,
    extra_frontmatter: dict | None = None,
) -> str:
    """Render a note template with frontmatter."""
    tmpl = TEMPLATES.get(template_name, TEMPLATES["default"])
    defaults = dict(tmpl["frontmatter_defaults"])

    if confidence is not None:
        defaults["confidence"] = confidence
    if tags:
        defaults["tags"] = tags
    if extra_frontmatter:
        defaults.update(extra_frontmatter)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    defaults["created"] = now
    defaults["modified"] = now

    # Build YAML frontmatter
    lines = ["---"]
    lines.append(f"title: {title}")
    for key, val in defaults.items():
        if isinstance(val, list):
            lines.append(f"{key}: [{', '.join(val)}]")
        else:
            lines.append(f"{key}: {val}")
    lines.append("---")
    lines.append("")

    body = tmpl["body"].format(title=title)
    return "\n".join(lines) + body
