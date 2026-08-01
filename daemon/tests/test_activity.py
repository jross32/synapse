"""AI-activity notifications: projector + CRUD + routes (ADR-0028, PLAN 5 Phase 2)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon import activity
from synapse_daemon import agent_squads as squads
from synapse_daemon import coordination as coord
from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create as create_project
from synapse_daemon.proposals import ProposalCreate, create_proposal
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _storage(tmp_path: Path) -> Storage:
    s = Storage(tmp_path / "data")
    s.open()
    s.migrate()
    return s


# -- projector ----------------------------------------------------------------


def test_projector_session_connected(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    with s.transaction() as conn:
        n = activity.project_event(
            conn,
            "v1.coordination.session_registered",
            {
                "session_id": "abc",
                "seq": 7,
                "runtime_id": "claude",
                "agent_label": "Claude",
                "task": "build the backend",
                "connection_level": "yellow",
                "connection_code": "degraded.no_project",
            },
        )
    assert n is not None
    assert n.kind == "session.connected"
    assert n.title.startswith("Session #007")
    assert n.level == "yellow"
    assert "degraded.no_project" in n.body_md
    assert "build the backend" in n.body_md
    assert n.seq == 7 and n.session_id == "abc"


def test_projector_squad_created_quotes_goal(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    with s.transaction() as conn:
        n = activity.project_event(
            conn,
            "v1.agent_squad.created",
            {"squad": {"id": "sq1", "name": "Hardening", "goal_md": "Ship it safely", "project_id": "p1"}},
        )
    assert n is not None
    assert n.title == "New squad: Hardening"
    assert "Ship it safely" in n.body_md
    # The jump-to link targets the Squads section (a NavigationIntent the renderer feeds navigate()).
    assert n.links and n.links[0].intent == {"page": "ai-coding", "section": "squads"}


def test_projector_proposal_filed_reads_real_title(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    with s.transaction() as conn:
        p = create_proposal(conn, ProposalCreate(title="Cache the roster", rationale_md="It is refetched"))
        n = activity.project_event(conn, "v1.review.proposal_filed", {"id": p.id})
    assert n is not None
    assert "Cache the roster" in n.title
    assert n.links and n.links[0].intent == {"page": "ai-coding", "section": "review"}


def test_projector_project_errored_is_red(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    with s.transaction() as conn:
        n = activity.project_event(conn, "v1.project.errored", {"id": "my-app"})
    assert n is not None
    assert n.level == "red"
    assert "my-app" in n.title


def test_projector_ignores_non_milestones(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    with s.transaction() as conn:
        assert activity.project_event(conn, "v1.process.heartbeat", {}) is None
        assert activity.project_event(conn, "v1.activity.notification", {}) is None


def test_projector_records_mcp_attachment_as_structured_journal(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    with s.transaction() as conn:
        events = activity.project_journal_events(
            conn,
            "v1.agent_mcp.attached",
            {
                "squad_id": "sq1",
                "work_item_id": "wi1",
                "runtime": "codex",
                "mcp_server_ids": ["reflex", "web-scraper"],
            },
        )
    assert len(events) == 1
    event = events[0]
    assert event.category == activity.ActivityJournalCategory.MCP
    assert event.status == activity.ActivityJournalStatus.SUCCESS
    assert event.squad_id == "sq1"
    assert "reflex" in event.summary_md
    assert event.source == "synapse"


# -- CRUD ---------------------------------------------------------------------


def test_unread_lifecycle(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    with s.transaction() as conn:
        a = activity.create_notification(conn, kind="x", title="A")
        activity.create_notification(conn, kind="x", title="B")
    assert activity.unread_count(s.conn) == 2
    with s.transaction() as conn:
        read = activity.mark_read(conn, a.id)
    assert read.read_at is not None
    assert activity.unread_count(s.conn) == 1
    assert [n.title for n in activity.list_notifications(s.conn, unread_only=True)] == ["B"]
    with s.transaction() as conn:
        assert activity.mark_all_read(conn) == 1
    assert activity.unread_count(s.conn) == 0


# -- routes + live end-to-end -------------------------------------------------


def _client(tmp_path: Path) -> TestClient:
    s = _storage(tmp_path)
    app = build_app(s, EventBus())
    return TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})


def test_register_session_produces_a_notification_end_to_end(tmp_path: Path) -> None:
    # The real chain: POST /coordination/sessions -> bus event -> projector -> feed.
    with _client(tmp_path) as c:
        r = c.post(
            "/api/v1/coordination/sessions",
            json={"runtime_id": "claude", "agent_label": "Claude", "task": "dogfood"},
        )
        assert r.status_code == 200, r.text
        feed = c.get("/api/v1/activity/notifications").json()
        assert feed["unread_count"] >= 1
        titles = [n["title"] for n in feed["notifications"]]
        assert any(t.startswith("Session #001") for t in titles), titles
        connected = next(n for n in feed["notifications"] if n["kind"] == "session.connected")
        # No project bound -> the yellow grade flows through to the notification.
        assert connected["level"] == "yellow"

        # Mark it read via the route.
        rid = connected["id"]
        assert c.post(f"/api/v1/activity/notifications/{rid}/read").status_code == 200
        assert c.get("/api/v1/activity/notifications?unread=true").json()["unread_count"] == 0


def test_sessions_history_and_detail_routes(tmp_path: Path) -> None:
    with _client(tmp_path) as c:
        c.post("/api/v1/coordination/sessions", json={"runtime_id": "claude"})
        c.post("/api/v1/coordination/sessions", json={"runtime_id": "codex"})
        listing = c.get("/api/v1/activity/sessions").json()["sessions"]
        assert [s["seq"] for s in listing] == [2, 1]  # newest first
        detail = c.get(f"/api/v1/activity/sessions/{listing[0]['id']}").json()
        assert detail["session"]["seq"] == 2
        assert detail["session"]["connection_help"]["title"] == "Connected — no project"
        assert detail["squads"] == []  # no project bound
        assert any(n["kind"] == "session.connected" for n in detail["notifications"])
        assert detail["journal"] == []


def test_session_can_report_deep_view_receipts_and_heartbeat_focus(tmp_path: Path) -> None:
    with _client(tmp_path) as c:
        registered = c.post(
            "/api/v1/coordination/sessions",
            json={"runtime_id": "codex", "agent_label": "Codex"},
        ).json()
        session_id = registered["id"]
        reported = c.post(
            f"/api/v1/activity/sessions/{session_id}/events",
            json={
                "category": "reasoning",
                "status": "active",
                "title": "Compared two safe attachment designs",
                "summary_md": "Per-worker stdio isolation avoids stale shared ownership while preserving automatic availability.",
                "mcp_server_id": None,
                "authority": "observe",
            },
        )
        assert reported.status_code == 201, reported.text
        assert reported.json()["category"] == "reasoning"

        heartbeat = c.post(
            f"/api/v1/coordination/sessions/{session_id}/heartbeat",
            json={"status": "active", "last_intent": "Verifying Reflex attachment"},
        )
        assert heartbeat.status_code == 200, heartbeat.text
        assert heartbeat.json()["last_intent"] == "Verifying Reflex attachment"

        detail = c.get(f"/api/v1/activity/sessions/{session_id}").json()
        titles = [entry["title"] for entry in detail["journal"]]
        assert "Compared two safe attachment designs" in titles
        assert "Current focus updated" in titles
        focus = next(entry for entry in detail["journal"] if entry["title"] == "Current focus updated")
        assert focus["summary_md"] == "Verifying Reflex attachment"


def test_session_event_rejects_unknown_mcp_server(tmp_path: Path) -> None:
    with _client(tmp_path) as c:
        session_id = c.post(
            "/api/v1/coordination/sessions", json={"runtime_id": "codex"}
        ).json()["id"]
        response = c.post(
            f"/api/v1/activity/sessions/{session_id}/events",
            json={
                "category": "mcp",
                "status": "active",
                "title": "Using an unknown MCP",
                "mcp_server_id": "does-not-exist",
                "authority": "control",
            },
        )
        assert response.status_code == 404


def test_ai_session_header_creates_safe_synapse_api_receipt(tmp_path: Path) -> None:
    with _client(tmp_path) as c:
        session_id = c.post(
            "/api/v1/coordination/sessions", json={"runtime_id": "codex"}
        ).json()["id"]
        response = c.get(
            "/api/v1/projects",
            headers={"X-Synapse-Session": session_id},
        )
        assert response.status_code == 200
        detail = c.get(f"/api/v1/activity/sessions/{session_id}").json()
        receipt = next(event for event in detail["journal"] if event["title"] == "Synapse · projects")
        assert receipt["category"] == "tool"
        assert receipt["status"] == "success"
        assert receipt["authority"] == "observe"
        assert receipt["tool_name"] == "Synapse · projects"
        assert "GET /projects" in receipt["summary_md"]
        assert "bodies were not copied" in receipt["summary_md"]


def test_squad_created_with_session_header_stays_with_that_session(tmp_path: Path) -> None:
    with _client(tmp_path) as c:
        project = c.post(
            "/api/v1/projects",
            json={
                "id": "live-demo",
                "name": "Live Demo",
                "path": str(tmp_path),
                "kind": "other",
                "launch_cmd": "echo ready",
            },
        )
        assert project.status_code == 201, project.text
        first = c.post(
            "/api/v1/coordination/sessions",
            json={"runtime_id": "codex", "project_id": "live-demo"},
        ).json()
        second = c.post(
            "/api/v1/coordination/sessions",
            json={"runtime_id": "claude", "project_id": "live-demo"},
        ).json()

        created = c.post(
            "/api/v1/agent-squads",
            headers={"X-Synapse-Session": first["id"]},
            json={"project_id": "live-demo", "name": "Codex squad"},
        )
        assert created.status_code == 201, created.text

        first_detail = c.get(f"/api/v1/activity/sessions/{first['id']}").json()
        second_detail = c.get(f"/api/v1/activity/sessions/{second['id']}").json()
        assert [view["squad"]["name"] for view in first_detail["squads"]] == ["Codex squad"]
        assert second_detail["squads"] == []
        projected = next(
            event for event in first_detail["journal"] if event["title"] == "Squad created: Codex squad"
        )
        assert projected["session_id"] == first["id"]
