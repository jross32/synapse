"""End-to-end tests for the ChatGPT importer route (ADR-0003 Phase E · v0.1.33).

We pack a synthetic export.zip in memory (so no real ChatGPT data is
needed and the test stays deterministic) and POST it to the daemon. We
then verify that:

  * the route creates the ``imported-chatgpt`` project on first call,
  * each conversation lands as a Markdown file under that project,
  * a re-upload of the same zip is recognised as a duplicate,
  * malformed or empty payloads are rejected with the standard envelope.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon import projects as projects_module
from synapse_daemon.app import build_app
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _make_export(conversations: list[dict]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("conversations.json", json.dumps(conversations))
    return buf.getvalue()


def _message(node_id: str, role: str, text: str, parent: str | None, child_ids: list[str]):
    return {
        "id": node_id,
        "message": {
            "id": node_id,
            "author": {"role": role},
            "create_time": 1700_000_000.0,
            "content": {"content_type": "text", "parts": [text]},
        },
        "parent": parent,
        "children": child_ids,
    }


def _convo(title: str, suffix: str = "") -> dict:
    return {
        "title": title,
        "conversation_id": f"conv-{title.lower().replace(' ', '-')}{suffix}",
        "create_time": 1700_000_000.0,
        "current_node": "b",
        "mapping": {
            "a": _message("a", "user", f"Hi from {title}", parent=None, child_ids=["b"]),
            "b": _message("b", "assistant", f"Hello, this is {title}!{suffix}", parent="a", child_ids=[]),
        },
    }


def _harness(tmp_path: Path):
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    app = build_app(storage, EventBus())
    client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
    return client, storage


def test_chatgpt_import_creates_project_and_lands_files(tmp_path: Path) -> None:
    client, storage = _harness(tmp_path)
    payload = _make_export([_convo("Alpha"), _convo("Beta")])
    with client as c:
        res = c.post(
            "/api/v1/imports/chatgpt",
            files={"file": ("export.zip", io.BytesIO(payload), "application/zip")},
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["imported"] == 2
    assert body["duplicates"] == 0
    assert body["skipped_empty"] == 0
    assert body["project_id"] == "imported-chatgpt"
    titles = [entry["title"] for entry in body["files"]]
    assert "Alpha" in titles and "Beta" in titles

    # Project row was lazy-created.
    proj = projects_module.get_or_none(storage.conn, "imported-chatgpt")
    assert proj is not None
    assert proj.name == "ChatGPT imports"

    # Files are listable on the per-project files endpoint.
    listed = client.get("/api/v1/projects/imported-chatgpt/files")
    assert listed.status_code == 200
    rows = listed.json()["files"]
    assert len(rows) == 2
    for row in rows:
        assert row["mime"] == "text/markdown"
        assert row["source"] == "chatgpt-import"
        assert row["duplicate_of"] is None


def test_chatgpt_import_dedups_identical_re_upload(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    payload = _make_export([_convo("Repeat")])
    with client as c:
        first = c.post(
            "/api/v1/imports/chatgpt",
            files={"file": ("export.zip", io.BytesIO(payload), "application/zip")},
        ).json()
        second = c.post(
            "/api/v1/imports/chatgpt",
            files={"file": ("export.zip", io.BytesIO(payload), "application/zip")},
        ).json()

    assert first["imported"] == 1 and first["duplicates"] == 0
    assert second["imported"] == 1
    assert second["duplicates"] == 1
    assert second["duplicate_names"]
    # Both rows live on disk -- the second's duplicate_of points at the first.
    canonical = first["files"][0]["id"]
    assert second["files"][0]["duplicate_of"] == canonical


def test_chatgpt_import_rejects_non_zip(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    with client as c:
        res = c.post(
            "/api/v1/imports/chatgpt",
            files={"file": ("not.zip", io.BytesIO(b"plain text"), "application/zip")},
        )
    assert res.status_code == 422
    body = res.json()
    assert body["code"].startswith("imports.invalid")


def test_chatgpt_import_rejects_zip_without_conversations_json(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "no conversations here")
    with client as c:
        res = c.post(
            "/api/v1/imports/chatgpt",
            files={"file": ("export.zip", io.BytesIO(buf.getvalue()), "application/zip")},
        )
    assert res.status_code == 422
    assert "conversations.json" in res.json()["message"]


def test_chatgpt_import_skips_empty_conversations(tmp_path: Path) -> None:
    """A conversation whose mapping has zero renderable messages should be
    counted under ``skipped_empty`` rather than silently dropped."""

    client, _ = _harness(tmp_path)
    empty_convo = {"title": "Blank", "conversation_id": "conv-blank", "mapping": {}}
    payload = _make_export([_convo("Good"), empty_convo])
    with client as c:
        res = c.post(
            "/api/v1/imports/chatgpt",
            files={"file": ("export.zip", io.BytesIO(payload), "application/zip")},
        ).json()
    assert res["imported"] == 1
    assert res["skipped_empty"] == 1
    assert "Blank" in res["skipped_titles"]


def test_chatgpt_import_empty_file_rejected(tmp_path: Path) -> None:
    client, _ = _harness(tmp_path)
    with client as c:
        res = c.post(
            "/api/v1/imports/chatgpt",
            files={"file": ("export.zip", io.BytesIO(b""), "application/zip")},
        )
    assert res.status_code == 422
    assert "empty" in res.json()["message"].lower()
