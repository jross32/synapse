from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapse_daemon import thread_presence
from synapse_daemon.projects import Project, create as create_project
from synapse_daemon.routes_thread_presence import build_thread_presence_router
from synapse_daemon.storage import Storage
from synapse_daemon.time_utils import to_iso, utc_now
from synapse_daemon.ws import EventBus


def _storage(tmp_path: Path) -> Storage:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        create_project(
            conn,
            Project(
                id="demo",
                name="Demo",
                path=str(tmp_path),
                launch_cmd="echo ready",
            ),
        )
    return storage


def _bootstrap(
    storage: Storage,
    *,
    external_key: str,
    title: str = "Build checkout",
    group_id: str | None = None,
    new_group: str | None = None,
):
    with storage.transaction() as conn:
        return thread_presence.bootstrap_thread(
            conn,
            thread_presence.ThreadBootstrap(
                project_id="demo",
                external_thread_key=external_key,
                runtime_id="chatgpt",
                source=thread_presence.ThreadSource.MANAGED_BROWSER,
                conversation_url=f"https://chatgpt.com/c/{external_key}",
                title=title,
                description="Implement and test the checkout flow",
                current_task="Checkout implementation",
                work_group_id=group_id,
                create_group_name=new_group,
                create_group_description="Checkout release request",
            ),
        )


def test_new_thread_requires_deliberate_group_decision(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    item, candidates, needs_decision = _bootstrap(storage, external_key="one")
    assert item is None
    assert candidates == []
    assert needs_decision is True


def test_turn_duration_rolls_up_once_and_threads_sort_by_work_time(tmp_path: Path) -> None:
    storage = _storage(tmp_path)

    first, _, _ = _bootstrap(storage, external_key="one", new_group="Checkout release")
    assert first is not None
    second, _, _ = _bootstrap(
        storage,
        external_key="two",
        title="Review checkout release",
        group_id=first.work_group_id,
    )
    assert second is not None

    with storage.transaction() as conn:
        turn1 = thread_presence.begin_turn(
            conn,
            first.id,
            thread_presence.ThreadBegin(
                prompt_label="Implement checkout",
                current_task="Implementing checkout",
            ),
        )
        completed1, after1 = thread_presence.finish_turn(
            conn,
            first.id,
            thread_presence.ThreadFinish(
                turn_id=turn1.id,
                duration_seconds=300,
                duration_source=thread_presence.DurationSource.UI_DISPLAY,
                summary_md="Checkout implemented.",
            ),
        )
        assert completed1.duration_seconds == 300
        assert completed1.duration_source == thread_presence.DurationSource.UI_DISPLAY
        assert after1.total_work_seconds == 300
        assert after1.turn_count == 1

        # Retry/finalizer duplication must never double-charge time.
        _, after_repeat = thread_presence.finish_turn(
            conn,
            first.id,
            thread_presence.ThreadFinish(
                turn_id=turn1.id,
                duration_seconds=999,
                duration_source=thread_presence.DurationSource.REPORTED,
            ),
        )
        assert after_repeat.total_work_seconds == 300
        assert after_repeat.turn_count == 1

        turn2 = thread_presence.begin_turn(
            conn,
            second.id,
            thread_presence.ThreadBegin(prompt_label="Review checkout"),
        )
        _, after2 = thread_presence.finish_turn(
            conn,
            second.id,
            thread_presence.ThreadFinish(
                turn_id=turn2.id,
                duration_seconds=900,
                duration_source=thread_presence.DurationSource.WALL_CLOCK,
            ),
        )
        assert after2.total_work_seconds == 900

    threads = thread_presence.list_threads(
        storage.conn, work_group_id=first.work_group_id
    )
    assert [thread.id for thread in threads] == [second.id, first.id]
    group = thread_presence.get_group(storage.conn, first.work_group_id)
    assert group.total_work_seconds == 1200
    assert group.thread_count == 2


def test_stale_is_derived_without_destroying_thread_identity(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    item, _, _ = _bootstrap(storage, external_key="one", new_group="Long task")
    assert item is not None

    with storage.transaction() as conn:
        thread_presence.begin_turn(
            conn, item.id, thread_presence.ThreadBegin(prompt_label="Long turn")
        )
        old = to_iso(
            utc_now() - timedelta(seconds=thread_presence.THREAD_STALE_SECONDS + 30)
        )
        conn.execute(
            "UPDATE ai_threads SET last_seen_at = ? WHERE id = ?",
            (old, item.id),
        )

    stale = thread_presence.get_thread(storage.conn, item.id)
    assert stale.status == thread_presence.ThreadStatus.ACTIVE
    assert stale.display_status == thread_presence.ThreadDisplayStatus.STALE
    assert stale.stale is True


def test_external_thread_key_resumes_same_durable_record(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    first, _, _ = _bootstrap(storage, external_key="same", new_group="Same request")
    assert first is not None

    with storage.transaction() as conn:
        resumed, candidates, needs_decision = thread_presence.bootstrap_thread(
            conn,
            thread_presence.ThreadBootstrap(
                project_id="demo",
                external_thread_key="same",
                runtime_id="chatgpt",
                source=thread_presence.ThreadSource.BROWSER_OBSERVER,
                conversation_url="https://chatgpt.com/c/same",
                title="Updated title",
            ),
        )
    assert resumed is not None
    assert resumed.id == first.id
    assert resumed.source == thread_presence.ThreadSource.BROWSER_OBSERVER
    assert resumed.title == "Updated title"
    assert candidates == []
    assert needs_decision is False


def test_group_candidates_include_names_tasks_and_similarity(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    first, _, _ = _bootstrap(
        storage,
        external_key="one",
        title="RackPilot mobile UX",
        new_group="RackPilot mobile UX",
    )
    assert first is not None

    with storage.transaction() as conn:
        _, candidates, needs_decision = thread_presence.bootstrap_thread(
            conn,
            thread_presence.ThreadBootstrap(
                project_id="demo",
                external_thread_key="two",
                runtime_id="chatgpt",
                title="RackPilot mobile UX verification",
                description="Verify mobile UX and fix navigation",
                current_task="mobile UX verification",
            ),
        )
    assert needs_decision is True
    assert candidates
    assert candidates[0].id == first.work_group_id
    assert candidates[0].score > 0
    assert candidates[0].threads[0]["title"] == "RackPilot mobile UX"


def test_rest_overview_reports_active_idle_and_total_time(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    app = FastAPI()
    app.include_router(
        build_thread_presence_router(storage, EventBus()), prefix="/api/v1"
    )
    client = TestClient(app)

    boot = client.post(
        "/api/v1/thread-presence/bootstrap",
        json={
            "project_id": "demo",
            "external_thread_key": "rest-thread",
            "runtime_id": "chatgpt",
            "source": "browser_observer",
            "title": "REST thread",
            "create_group_name": "REST group",
        },
    )
    assert boot.status_code == 200, boot.text
    thread_id = boot.json()["thread"]["id"]

    begin = client.post(
        f"/api/v1/thread-presence/threads/{thread_id}/begin",
        json={"prompt_label": "Do work"},
    )
    assert begin.status_code == 200, begin.text
    turn_id = begin.json()["id"]

    active = client.get("/api/v1/thread-presence/overview").json()
    assert active["counts"]["in_progress"] == 1
    assert active["counts"]["active"] == 1

    finish = client.post(
        f"/api/v1/thread-presence/threads/{thread_id}/finish",
        json={
            "turn_id": turn_id,
            "duration_seconds": 420,
            "duration_source": "ui_display",
            "summary_md": "Done.",
        },
    )
    assert finish.status_code == 200, finish.text

    overview = client.get("/api/v1/thread-presence/overview").json()
    assert overview["counts"]["in_progress"] == 0
    assert overview["counts"]["idle"] == 1
    assert overview["total_work_seconds"] == 420
    assert overview["groups"][0]["threads"][0]["total_work_seconds"] == 420



def test_unassigned_browser_observation_counts_active_without_project(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with storage.transaction() as conn:
        observation, tracked = thread_presence.observe_browser_thread(
            conn,
            thread_presence.BrowserObservation(
                external_thread_key="browser-only",
                browser_tab_id="77",
                conversation_url="https://chatgpt.com/c/browser-only",
                title="Existing manual ChatGPT thread",
                status=thread_presence.ThreadStatus.ACTIVE,
                generation_started_at=utc_now(),
            ),
        )
    assert tracked is None
    assert observation.status == thread_presence.ThreadDisplayStatus.ACTIVE

    snap = thread_presence.overview(storage.conn)
    assert snap["counts"]["threads"] == 0
    assert snap["counts"]["browser_unassigned"] == 1
    assert snap["counts"]["browser_unassigned_active"] == 1
    assert snap["counts"]["in_progress"] == 1


def test_browser_observer_attaches_to_later_bootstrap_and_auto_times_turn(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    started = utc_now() - timedelta(minutes=4)

    with storage.transaction() as conn:
        thread_presence.observe_browser_thread(
            conn,
            thread_presence.BrowserObservation(
                external_thread_key="observed-first",
                browser_tab_id="88",
                conversation_url="https://chatgpt.com/c/observed-first",
                title="Observed first",
                status=thread_presence.ThreadStatus.ACTIVE,
                current_task="Building checkout",
                generation_started_at=started,
            ),
        )

    tracked, _, _ = _bootstrap(
        storage,
        external_key="observed-first",
        title="Observed first",
        new_group="Observed request",
    )
    assert tracked is not None
    assert tracked.display_status == thread_presence.ThreadDisplayStatus.ACTIVE
    assert tracked.current_turn_started_at is not None

    with storage.transaction() as conn:
        observation, finished = thread_presence.observe_browser_thread(
            conn,
            thread_presence.BrowserObservation(
                external_thread_key="observed-first",
                browser_tab_id="88",
                conversation_url="https://chatgpt.com/c/observed-first",
                title="Observed first",
                status=thread_presence.ThreadStatus.IDLE,
                last_duration_seconds=248,
            ),
        )
    assert observation.tracked_thread_id == tracked.id
    assert finished is not None
    assert finished.display_status == thread_presence.ThreadDisplayStatus.IDLE
    assert finished.total_work_seconds == 248
    assert finished.turn_count == 1
    turns = thread_presence.list_turns(storage.conn, tracked.id)
    assert turns[0].duration_source == thread_presence.DurationSource.UI_DISPLAY
    assert turns[0].duration_seconds == 248
