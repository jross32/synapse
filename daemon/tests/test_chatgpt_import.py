"""Unit tests for the ChatGPT export parser (ADR-0003 Phase E · v0.1.33).

These don't hit any network or filesystem -- everything runs against
synthesized JSON / zip bytes so the parser logic stays the focus.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from synapse_daemon.chatgpt_import import (
    ChatgptImportError,
    parse_export,
    render_markdown,
    filename_for,
)


def _make_message(node_id: str, role: str, text: str, parent: str | None, child_ids: list[str], create_time: float = 1700_000_000):
    return {
        "id": node_id,
        "message": {
            "id": node_id,
            "author": {"role": role},
            "create_time": create_time,
            "content": {"content_type": "text", "parts": [text]},
        },
        "parent": parent,
        "children": child_ids,
    }


def _make_export(conversations: list[dict]) -> bytes:
    """Pack a synthetic conversations.json into a zip the parser will accept."""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("conversations.json", json.dumps(conversations))
    return buf.getvalue()


def _basic_conversation(title: str = "Hello chat") -> dict:
    return {
        "title": title,
        "conversation_id": "conv-abc",
        "create_time": 1700_000_000.0,
        "current_node": "m3",
        "mapping": {
            "m1": _make_message("m1", "user", "Hi there", parent=None, child_ids=["m2"]),
            "m2": _make_message("m2", "assistant", "Hello! How can I help?", parent="m1", child_ids=["m3"]),
            "m3": _make_message("m3", "user", "Tell me a joke", parent="m2", child_ids=[]),
        },
    }


# ── parser ───────────────────────────────────────────────────────────────


def test_parse_basic_conversation_walks_current_node_path() -> None:
    payload = _make_export([_basic_conversation()])
    parsed = parse_export(payload)
    assert len(parsed) == 1
    convo = parsed[0]
    assert convo.title == "Hello chat"
    assert convo.id == "conv-abc"
    assert [m.role for m in convo.messages] == ["user", "assistant", "user"]
    assert convo.messages[1].text == "Hello! How can I help?"


def test_parse_export_skips_messages_with_unknown_roles() -> None:
    convo = _basic_conversation()
    convo["mapping"]["m2"]["message"]["author"]["role"] = "unrecognised-role"
    parsed = parse_export(_make_export([convo]))[0]
    assert [m.role for m in parsed.messages] == ["user", "user"]


def test_parse_export_handles_missing_current_node_by_walking_first_child() -> None:
    convo = _basic_conversation()
    convo.pop("current_node")
    parsed = parse_export(_make_export([convo]))[0]
    assert [m.role for m in parsed.messages] == ["user", "assistant", "user"]


def test_parse_export_picks_chosen_branch_on_a_fork() -> None:
    """Retries fork the mapping: the parser must follow the path that ends
    at ``current_node``."""

    convo = {
        "title": "Fork test",
        "conversation_id": "conv-fork",
        "current_node": "m3b",
        "mapping": {
            "m1": _make_message("m1", "user", "ask", None, ["m2a", "m2b"]),
            "m2a": _make_message("m2a", "assistant", "first try (skipped)", "m1", ["m3a"]),
            "m2b": _make_message("m2b", "assistant", "retry answer", "m1", ["m3b"]),
            "m3a": _make_message("m3a", "user", "wrong followup", "m2a", []),
            "m3b": _make_message("m3b", "user", "correct followup", "m2b", []),
        },
    }
    parsed = parse_export(_make_export([convo]))[0]
    texts = [m.text for m in parsed.messages]
    assert "first try (skipped)" not in texts
    assert "retry answer" in texts
    assert "correct followup" in texts


def test_parse_export_drops_empty_text_parts() -> None:
    convo = _basic_conversation()
    convo["mapping"]["m1"]["message"]["content"]["parts"] = [""]
    parsed = parse_export(_make_export([convo]))[0]
    # m1 was empty, so we should skip it and pick up at m2 onward.
    assert [m.role for m in parsed.messages] == ["assistant", "user"]


def test_parse_export_default_title_for_missing_title() -> None:
    convo = _basic_conversation()
    del convo["title"]
    parsed = parse_export(_make_export([convo]))[0]
    assert parsed.title == "Untitled chat"


def test_parse_export_rejects_non_zip() -> None:
    with pytest.raises(ChatgptImportError, match="Not a valid zip"):
        parse_export(b"not a zip at all")


def test_parse_export_rejects_zip_without_conversations_json() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "no conversations here")
    with pytest.raises(ChatgptImportError, match="conversations.json"):
        parse_export(buf.getvalue())


def test_parse_export_rejects_non_list_root() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("conversations.json", json.dumps({"oops": "object not list"}))
    with pytest.raises(ChatgptImportError, match="not a list"):
        parse_export(buf.getvalue())


def test_parse_export_finds_conversations_json_in_subfolder() -> None:
    """Some exports nest everything under a top-level folder; we should
    locate ``conversations.json`` no matter the depth."""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "export-2025-11-12/conversations.json",
            json.dumps([_basic_conversation()]),
        )
    parsed = parse_export(buf.getvalue())
    assert len(parsed) == 1


# ── markdown rendering ───────────────────────────────────────────────────


def test_render_markdown_includes_title_and_messages() -> None:
    parsed = parse_export(_make_export([_basic_conversation()]))[0]
    md = render_markdown(parsed)
    assert "# Hello chat" in md
    assert "## You" in md
    assert "## ChatGPT" in md
    assert "Tell me a joke" in md
    # Stable trailing newline so the file behaves nicely with tools.
    assert md.endswith("\n")


def test_render_markdown_is_deterministic_for_dedup() -> None:
    """Same input -> same bytes is the property the dedup rule relies on."""

    parsed_a = parse_export(_make_export([_basic_conversation()]))[0]
    parsed_b = parse_export(_make_export([_basic_conversation()]))[0]
    assert render_markdown(parsed_a) == render_markdown(parsed_b)


def test_render_markdown_for_conversation_with_no_messages() -> None:
    """Empty mapping -> still renders the header so the user gets a sense
    of what was empty."""

    parsed = parse_export(_make_export([{"title": "Blank", "mapping": {}}]))[0]
    md = render_markdown(parsed)
    assert "# Blank" in md
    # No message headings.
    assert "## You" not in md
    assert "## ChatGPT" not in md


def test_filename_for_uses_date_prefix_when_available() -> None:
    parsed = parse_export(_make_export([_basic_conversation()]))[0]
    name = filename_for(parsed, 0)
    assert name.endswith("_hello-chat.md")
    assert name[:10].count("-") == 2  # YYYY-MM-DD prefix


def test_filename_for_falls_back_to_index_without_a_date() -> None:
    convo = _basic_conversation()
    del convo["create_time"]
    parsed = parse_export(_make_export([convo]))[0]
    name = filename_for(parsed, 7)
    assert name.startswith("0007_")
