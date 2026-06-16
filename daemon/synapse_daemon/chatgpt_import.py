"""ChatGPT export.zip importer (ADR-0003 Phase E · v0.1.33).

Honest scope (ADR-0003 verbatim): we parse the user-initiated export from
``Settings -> Data Controls -> Export Data``. NO browser scraping, NO
live ChatGPT API. One-shot ingest from a zip the user already downloaded.

The export layout we support
----------------------------
The zip contains (at least) ``conversations.json`` -- a list of
conversation objects. Each one has a ``mapping`` tree of messages:

    {
      "title": "...",
      "create_time": <epoch float>,
      "current_node": "<node_id>",
      "mapping": {
        "<node_id>": {
          "id": "...",
          "message": {
            "author": {"role": "user" | "assistant" | "system" | "tool"},
            "create_time": <epoch float>,
            "content": {"content_type": "text", "parts": ["..."]}
          },
          "parent": "<parent_id>",
          "children": ["..."]
        }
      }
    }

The tree branches on retries; we walk the path from root to
``current_node`` so the rendered markdown matches "what the user saw last".
"""

from __future__ import annotations

import io
import json
import logging
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone

log = logging.getLogger(__name__)


class ChatgptImportError(Exception):
    """Raised when the zip is not a recognisable ChatGPT export."""


@dataclass
class ParsedMessage:
    role: str                         # 'user' | 'assistant' | 'system' | 'tool'
    text: str                         # joined content parts
    created_at: str | None = None     # ISO 8601 UTC if present in the export


@dataclass
class ParsedConversation:
    id: str
    title: str
    created_at: str | None
    messages: list[ParsedMessage]

    @property
    def title_slug(self) -> str:
        return _slugify(self.title)


_DEFAULT_TITLE = "Untitled chat"
_ROLE_HEADINGS = {
    "user": "## You",
    "assistant": "## ChatGPT",
    "system": "## System",
    "tool": "## Tool",
}


def _iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _slugify(text: str) -> str:
    """Filename-safe slug -- ASCII letters/digits/hyphens only, capped."""

    base = re.sub(r"[^A-Za-z0-9]+", "-", text.strip()).strip("-").lower()
    return (base or "chat")[:60]


def _extract_text(message: dict) -> str:
    """A ChatGPT message has ``content.parts: [str]``. Some entries are
    images / metadata -- skip non-strings."""

    content = message.get("content")
    if not isinstance(content, dict):
        return ""
    parts = content.get("parts")
    if not isinstance(parts, list):
        return ""
    return "\n".join(str(p) for p in parts if isinstance(p, str)).strip()


def _walk_to_current(mapping: dict, current_node: str | None) -> list[str]:
    """Path from root to ``current_node``. Falls back to a depth-first walk
    of the first child chain when ``current_node`` is missing."""

    if current_node and current_node in mapping:
        chain = []
        cursor: str | None = current_node
        guard = 0  # bound the walk in case of pathological mapping
        while cursor and guard < 10_000:
            chain.append(cursor)
            entry = mapping.get(cursor)
            if not isinstance(entry, dict):
                break
            cursor = entry.get("parent")
            guard += 1
        chain.reverse()
        return chain
    # Fallback: find a root (no parent) and walk first child until leaf.
    roots = [
        node_id for node_id, entry in mapping.items()
        if isinstance(entry, dict) and not entry.get("parent")
    ]
    if not roots:
        return []
    chain: list[str] = []
    cursor = roots[0]
    guard = 0
    while cursor and guard < 10_000:
        chain.append(cursor)
        entry = mapping.get(cursor)
        if not isinstance(entry, dict):
            break
        children = entry.get("children") or []
        cursor = children[0] if children else None
        guard += 1
    return chain


def _parse_conversation(raw: dict) -> ParsedConversation:
    title = str(raw.get("title") or _DEFAULT_TITLE).strip() or _DEFAULT_TITLE
    convo_id = str(raw.get("conversation_id") or raw.get("id") or "")
    created = _iso(raw.get("create_time"))
    mapping = raw.get("mapping") or {}
    if not isinstance(mapping, dict):
        return ParsedConversation(id=convo_id, title=title, created_at=created, messages=[])

    chain = _walk_to_current(mapping, raw.get("current_node"))
    messages: list[ParsedMessage] = []
    for node_id in chain:
        entry = mapping.get(node_id)
        if not isinstance(entry, dict):
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        author = message.get("author")
        if not isinstance(author, dict):
            continue
        role = str(author.get("role") or "").lower().strip()
        if role not in _ROLE_HEADINGS:
            continue
        text = _extract_text(message)
        if not text:
            continue
        messages.append(
            ParsedMessage(
                role=role,
                text=text,
                created_at=_iso(message.get("create_time")),
            )
        )
    return ParsedConversation(id=convo_id, title=title, created_at=created, messages=messages)


def parse_export(zip_bytes: bytes) -> list[ParsedConversation]:
    """Inspect the zip and return one ParsedConversation per chat."""

    try:
        archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise ChatgptImportError(f"Not a valid zip archive: {exc}")

    name = _find_conversations_member(archive)
    if name is None:
        raise ChatgptImportError(
            "Zip is missing conversations.json -- not a ChatGPT export."
        )

    try:
        raw_text = archive.read(name).decode("utf-8")
    except (KeyError, UnicodeDecodeError) as exc:
        raise ChatgptImportError(f"Could not read {name}: {exc}")
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ChatgptImportError(f"{name} is malformed JSON: {exc}")
    if not isinstance(raw, list):
        raise ChatgptImportError(
            f"{name} is not a list of conversations (got {type(raw).__name__})."
        )

    out: list[ParsedConversation] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            out.append(_parse_conversation(entry))
        except Exception:  # pragma: no cover -- defensive
            log.exception("Skipping malformed conversation entry")
    return out


def _find_conversations_member(archive: zipfile.ZipFile) -> str | None:
    """Locate conversations.json. Some exports nest it under a top folder."""

    for name in archive.namelist():
        # Skip directory entries and macOS metadata.
        if name.endswith("/") or name.startswith("__MACOSX/"):
            continue
        base = name.rsplit("/", 1)[-1].lower()
        if base == "conversations.json":
            return name
    return None


def render_markdown(conversation: ParsedConversation) -> str:
    """Render one parsed conversation into a stable Markdown document.

    Stable means: same input -> same bytes -> same sha256 -> the existing
    dedup rule kicks in if the user imports the same export twice.
    """

    lines: list[str] = [f"# {conversation.title}", ""]
    if conversation.created_at:
        lines.append(f"*Created: {conversation.created_at}*")
    if conversation.id:
        lines.append(f"*Conversation id: `{conversation.id}`*")
    if conversation.created_at or conversation.id:
        lines.append("")
    for msg in conversation.messages:
        lines.append(_ROLE_HEADINGS[msg.role])
        if msg.created_at:
            lines.append(f"<sub>{msg.created_at}</sub>")
            lines.append("")
        lines.append(msg.text)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def filename_for(conversation: ParsedConversation, index: int) -> str:
    """Per-conversation .md filename. Date prefix sorts chronologically."""

    date_prefix = (conversation.created_at or "")[:10]  # YYYY-MM-DD
    slug = conversation.title_slug
    prefix = f"{date_prefix}_" if date_prefix else f"{index:04d}_"
    return f"{prefix}{slug}.md"
