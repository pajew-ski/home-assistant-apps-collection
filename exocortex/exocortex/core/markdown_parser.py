"""Markdown parsing: frontmatter extraction, wikilink detection, text stripping."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import frontmatter


# Regex patterns
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
STRIP_MD_RE = re.compile(
    r"(?:"
    r"!\[[^\]]*\]\([^)]*\)"  # images
    r"|```[\s\S]*?```"  # code blocks
    r"|`[^`]+`"  # inline code
    r"|\*\*([^*]+)\*\*"  # bold
    r"|\*([^*]+)\*"  # italic
    r"|__([^_]+)__"  # bold alt
    r"|_([^_]+)_"  # italic alt
    r"|~~([^~]+)~~"  # strikethrough
    r"|#{1,6}\s+"  # headings
    r"|\[([^\]]+)\]\([^)]+\)"  # links (keep text)
    r"|\[\[([^\]|]+)(?:\|([^\]]+))?\]\]"  # wikilinks (keep display text)
    r"|^>\s+"  # blockquotes
    r"|^[-*+]\s+"  # list markers
    r"|^\d+\.\s+"  # ordered list
    r"|^---+$"  # hr
    r"|\|"  # table pipes
    r")"
)


@dataclass
class ParsedNote:
    title: str = ""
    body: str = ""
    plain_text: str = ""
    frontmatter: dict[str, Any] = field(default_factory=dict)
    wikilinks: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    confidence: int = 0
    status: str = ""
    note_type: str = "note"
    created: str | None = None
    modified: str | None = None
    location: tuple[float, float] | None = None
    word_count: int = 0
    snippet: str = ""


def extract_wikilinks(text: str) -> list[str]:
    """Extract all [[wikilink]] targets from markdown text."""
    return list(dict.fromkeys(WIKILINK_RE.findall(text)))


def extract_h1(text: str) -> str | None:
    """Extract the first H1 heading from markdown."""
    match = H1_RE.search(text)
    return match.group(1).strip() if match else None


def strip_markdown(text: str) -> str:
    """Strip markdown formatting, returning plain text."""

    def replacer(m: re.Match) -> str:
        # Return captured group content for formatting (bold, italic, etc.)
        for g in m.groups():
            if g is not None:
                return g
        return ""

    result = STRIP_MD_RE.sub(replacer, text)
    # Collapse whitespace
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def parse_note(raw: str, path: str | Path = "") -> ParsedNote:
    """Parse a markdown file with YAML frontmatter into structured data."""
    post = frontmatter.loads(raw)
    meta = dict(post.metadata)
    body = post.content

    # Title: frontmatter > H1 > filename
    title = meta.get("title", "") or extract_h1(body) or ""
    if not title and path:
        title = Path(path).stem.replace("-", " ").replace("_", " ").title()

    # Wikilinks from body
    wikilinks = extract_wikilinks(body)

    # Also add explicit links from frontmatter
    explicit_links = meta.get("links", [])
    if isinstance(explicit_links, list):
        for link in explicit_links:
            if link not in wikilinks:
                wikilinks.append(link)

    # Tags
    tags = meta.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]

    # Aliases
    aliases = meta.get("aliases", [])
    if isinstance(aliases, str):
        aliases = [a.strip() for a in aliases.split(",")]

    # Location
    location = None
    loc = meta.get("location")
    if isinstance(loc, (list, tuple)) and len(loc) == 2:
        try:
            location = (float(loc[0]), float(loc[1]))
        except (TypeError, ValueError):
            pass

    # Plain text
    plain_text = strip_markdown(body)

    # Snippet
    snippet = plain_text[:300]

    # Word count
    word_count = len(plain_text.split())

    return ParsedNote(
        title=title,
        body=body,
        plain_text=plain_text,
        frontmatter=meta,
        wikilinks=wikilinks,
        tags=tags,
        aliases=aliases,
        confidence=int(meta.get("confidence", 0)),
        status=meta.get("status", ""),
        note_type=meta.get("type", "note"),
        created=meta.get("created"),
        modified=meta.get("modified"),
        location=location,
        word_count=word_count,
        snippet=snippet,
    )
