"""Proposal backlog API: decision and implementation lifecycle are intentionally separate."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _client(tmp_path: Path):
    s = Storage(tmp_path / "data")
    s.open()
    s.migrate()
    app = build_app(s, EventBus())
    return TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})


def test_file_proposal_shows_in_inbox_then_accept_decision_clears_review(tmp_path: Path) -> None:
    client = _client(tmp_path)
    with client as c:
        filed = c.post(
            "/api/v1/review/proposals",
            json={
                "title": "Add a dark-mode toggle",
                "rationale_md": "Several users asked for it.",
                "source_runtime": "claude",
                "kind": "ui/ux",
                "est_effort": "S",
                "est_token_cost": 20000,
            },
        )
        assert filed.status_code == 200, filed.text
        body = filed.json()
        pid = body["id"]
        assert body["status"] == "proposed"
        assert body["decision"] == "pending"
        assert body["kind"] == "ui-ux"

        inbox = c.get("/api/v1/review/inbox").json()
        assert any(p["id"] == pid for p in inbox["proposals"])

        accepted = c.post(f"/api/v1/review/proposals/{pid}/approve", json={"note": "yes, do it"})
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["decision"] == "accepted"
        # Accepting the idea must not lie about implementation progress.
        assert accepted.json()["status"] == "proposed"
        assert accepted.json()["resolved_at"] == accepted.json()["decision_at"]

        # Human decision is complete, so it leaves the decision inbox but remains in the backlog.
        inbox2 = c.get("/api/v1/review/inbox").json()
        assert not any(p["id"] == pid for p in inbox2["proposals"])
        assert c.get(f"/api/v1/review/proposals/{pid}").json()["status"] == "proposed"


def test_reject_proposal_sets_decision_without_faking_lifecycle(tmp_path: Path) -> None:
    client = _client(tmp_path)
    with client as c:
        pid = c.post("/api/v1/review/proposals", json={"title": "Rewrite everything in Rust"}).json()["id"]
        rejected = c.post(f"/api/v1/review/proposals/{pid}/reject", json={"note": "not now"})
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["decision"] == "declined"
        assert rejected.json()["status"] == "proposed"


def test_proposal_needs_title(tmp_path: Path) -> None:
    client = _client(tmp_path)
    with client as c:
        assert c.post("/api/v1/review/proposals", json={"title": "   "}).status_code == 422


def test_approve_unknown_proposal_404(tmp_path: Path) -> None:
    client = _client(tmp_path)
    with client as c:
        assert c.post("/api/v1/review/proposals/nope/approve").status_code == 404


def test_list_filters_sorting_and_first_class_kind(tmp_path: Path) -> None:
    client = _client(tmp_path)
    with client as c:
        p_ui = c.post(
            "/api/v1/review/proposals",
            json={"title": "Z UI polish", "kind": "ux"},
        ).json()["id"]
        p_bug = c.post(
            "/api/v1/review/proposals",
            json={"title": "A Crash", "metadata": {"kind": "error"}},
        ).json()["id"]
        c.post(f"/api/v1/review/proposals/{p_bug}/reject", json={"note": "won't fix"})

        assert {p["id"] for p in c.get("/api/v1/review/proposals").json()} == {p_ui, p_bug}
        declined = c.get("/api/v1/review/proposals?decision=declined").json()
        assert [p["id"] for p in declined] == [p_bug]
        ui = c.get("/api/v1/review/proposals?kind=ui-ux").json()
        assert [p["id"] for p in ui] == [p_ui]
        ordered = c.get("/api/v1/review/proposals?sort_by=title&sort_dir=asc").json()
        assert [p["title"] for p in ordered] == ["A Crash", "Z UI polish"]

        one = c.get(f"/api/v1/review/proposals/{p_ui}").json()
        assert one["kind"] == "ui-ux" and one["status"] == "proposed"
        assert c.get("/api/v1/review/proposals/nope").status_code == 404
        assert c.get("/api/v1/review/proposals?status=rejected").status_code == 422


def test_manual_lifecycle_transition_persists_evidence_and_can_reopen(tmp_path: Path) -> None:
    client = _client(tmp_path)
    with client as c:
        pid = c.post("/api/v1/review/proposals", json={"title": "Lifecycle me"}).json()["id"]
        started = c.patch(
            f"/api/v1/review/proposals/{pid}/lifecycle",
            json={"status": "in_progress", "note": "starting now"},
        )
        assert started.status_code == 200, started.text
        assert started.json()["started_at"] is not None
        assert started.json()["lifecycle_source"] == "manual"
        assert started.json()["lifecycle_evidence"][-1]["detail"] == "starting now"

        done = c.patch(
            f"/api/v1/review/proposals/{pid}/lifecycle",
            json={"status": "done", "note": "verified"},
        ).json()
        assert done["done_at"] is not None
        assert done["lifecycle_evidence"][-1]["source"] == "manual"

        reopened = c.patch(
            f"/api/v1/review/proposals/{pid}/lifecycle",
            json={"status": "proposed", "note": "regression reopened"},
        ).json()
        assert reopened["status"] == "proposed"
        assert reopened["done_at"] is None
        assert len(reopened["lifecycle_evidence"]) == 3


def test_promote_project_proposal_accepts_and_marks_in_progress(tmp_path: Path) -> None:
    from synapse_daemon import project_records
    from synapse_daemon.projects import Project, create as create_project

    s = Storage(tmp_path / "data")
    s.open()
    s.migrate()
    with s.transaction() as conn:
        create_project(conn, Project(id="proj1", name="Proj", path="/tmp", launch_cmd="echo hi"))
    app = build_app(s, EventBus())
    with TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token}) as c:
        pid = c.post(
            "/api/v1/review/proposals",
            json={"title": "Add dark mode", "rationale_md": "Users want it", "project_id": "proj1"},
        ).json()["id"]

        promoted = c.post(f"/api/v1/review/proposals/{pid}/promote")
        assert promoted.status_code == 200, promoted.text
        body = promoted.json()
        assert body["proposal"]["decision"] == "accepted"
        assert body["proposal"]["status"] == "in_progress"
        assert body["proposal"]["lifecycle_source"] == "backlog"
        assert body["backlog_item"]["title"] == "Add dark mode"
        assert body["backlog_item"]["project_id"] == "proj1"
        assert pid in body["backlog_item"]["body_md"]
        assert c.post(f"/api/v1/review/proposals/{pid}/promote").status_code >= 400

    items = project_records.list_backlog(s.conn, "proj1")
    assert sum(i.title == "Add dark mode" for i in items) == 1


def test_promote_synapse_wide_proposal_is_rejected(tmp_path: Path) -> None:
    client = _client(tmp_path)
    with client as c:
        pid = c.post("/api/v1/review/proposals", json={"title": "Global idea"}).json()["id"]
        assert c.post(f"/api/v1/review/proposals/{pid}/promote").status_code >= 400


def test_schema_explains_lifecycle_decision_linking_and_kinds(tmp_path: Path) -> None:
    client = _client(tmp_path)
    with client as c:
        schema = c.get("/api/v1/review/proposals/schema")
        assert schema.status_code == 200, schema.text
        body = schema.json()
        assert body["lifecycle"]["normal_flow"] == ["proposed", "in_progress", "done"]
        assert "accepted" in body["decision"]["values"]
        assert "ui-ux" in body["kinds"]
        assert "exact proposal id" in body["linking_convention"]


def test_migration_035_preserves_old_decisions_without_claiming_done(tmp_path: Path) -> None:
    db = sqlite3.connect(tmp_path / "legacy.sqlite")
    db.executescript(
        """
        CREATE TABLE projects (id TEXT PRIMARY KEY);
        INSERT INTO projects(id) VALUES ('p1');
        CREATE TABLE improvement_proposals (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, rationale_md TEXT NOT NULL DEFAULT '',
            project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
            source_runtime TEXT NOT NULL DEFAULT '', est_effort TEXT NOT NULL DEFAULT '',
            est_token_cost INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','approved','rejected')),
            resolution_note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, resolved_at TEXT, metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        INSERT INTO improvement_proposals VALUES
          ('o','Open','','p1','','',0,'open','', '2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00',NULL,'{"kind":"ux"}'),
          ('a','Accepted','','p1','','',0,'approved','yes','2026-01-01T00:00:00+00:00','2026-01-02T00:00:00+00:00','2026-01-02T00:00:00+00:00','{"kind":"bug"}'),
          ('r','Declined','','p1','','',0,'rejected','no','2026-01-01T00:00:00+00:00','2026-01-03T00:00:00+00:00','2026-01-03T00:00:00+00:00','{}');
        """
    )
    migration = Path(__file__).parents[1] / "synapse_daemon" / "migrations" / "035_proposal_lifecycle.sql"
    db.executescript(migration.read_text(encoding="utf-8"))
    db.row_factory = sqlite3.Row
    rows = {row["id"]: row for row in db.execute("SELECT * FROM improvement_proposals")}
    assert rows["o"]["status"] == "proposed" and rows["o"]["decision"] == "pending"
    assert rows["a"]["status"] == "proposed" and rows["a"]["decision"] == "accepted"
    assert rows["a"]["decision_at"] == "2026-01-02T00:00:00+00:00"
    assert rows["r"]["status"] == "proposed" and rows["r"]["decision"] == "declined"
    assert rows["o"]["kind"] == "ui-ux"
    assert rows["a"]["done_at"] is None
