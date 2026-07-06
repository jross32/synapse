"""Per-work-item token accounting (Plan 3 Phase 2, ADR-0025)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from synapse_daemon import agent_squads as squads
from synapse_daemon import token_ledger
from synapse_daemon.errors import SynapseError
from synapse_daemon.projects import Project, create as create_project
from synapse_daemon.routes_token_ledger import build_token_ledger_router
from synapse_daemon.storage import Storage


def _storage(tmp_path: Path) -> Storage:
    s = Storage(tmp_path / "data")
    s.open()
    s.migrate()
    with s.transaction() as conn:
        squads.seed_default_role_templates(conn)
        create_project(conn, Project(id="p1", name="P1", path=str(tmp_path), launch_cmd="echo"))
    return s


def _squad_with_items(conn, roles: list[str]):
    squad = squads.create_squad(
        conn, squads.AgentSquadCreate(project_id="p1", name="Sq", lead_role_id="planner")
    )
    items = [
        squads.create_work_item(
            conn, squad.id, squads.AgentWorkItemCreate(title=f"work-{r}", assigned_role_id=r)
        )
        for r in roles
    ]
    return squad, items


def test_record_computes_total_and_denormalizes_squad_role(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    with s.transaction() as conn:
        squad, (wi,) = _squad_with_items(conn, ["tester"])
        usage = token_ledger.record_tokens(
            conn, wi.id, token_ledger.WorkItemTokenUsageCreate(input_tokens=100, output_tokens=50)
        )
    assert usage.total_tokens == 150  # computed input + output
    assert usage.squad_id == squad.id
    assert usage.role_id == "tester"
    assert usage.token_provenance == "reported"
    assert usage.token_source == "runtime_self_report"


def test_squad_rollup_sums_across_workers(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    with s.transaction() as conn:
        squad, (wi1, wi2) = _squad_with_items(conn, ["tester", "reviewer"])
        token_ledger.record_tokens(conn, wi1.id, token_ledger.WorkItemTokenUsageCreate(input_tokens=100, output_tokens=50))
        token_ledger.record_tokens(conn, wi2.id, token_ledger.WorkItemTokenUsageCreate(input_tokens=200, total_tokens=200))
    rollup = token_ledger.sum_squad_tokens(s.conn, squad.id)
    assert rollup.entries == 2
    assert rollup.total_tokens == 350
    assert rollup.by_role["tester"] == 150
    assert rollup.by_role["reviewer"] == 200


def test_record_unknown_work_item_raises(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    with s.transaction() as conn:
        with pytest.raises(SynapseError):
            token_ledger.record_tokens(conn, "nope", token_ledger.WorkItemTokenUsageCreate())


def test_router_records_and_rolls_up(tmp_path: Path) -> None:
    s = _storage(tmp_path)
    with s.transaction() as conn:
        squad, (wi,) = _squad_with_items(conn, ["tester"])

    app = FastAPI()

    async def _handler(_req, exc: SynapseError):
        return JSONResponse(status_code=exc.status, content=exc.envelope.model_dump())

    app.add_exception_handler(SynapseError, _handler)
    app.include_router(build_token_ledger_router(s), prefix="/api/v1")
    client = TestClient(app)

    r = client.post(f"/api/v1/agent-work-items/{wi.id}/tokens", json={"input_tokens": 10, "output_tokens": 5})
    assert r.status_code == 200, r.text
    assert r.json()["total_tokens"] == 15

    roll = client.get(f"/api/v1/agent-squads/{squad.id}/token-usage").json()
    assert roll["total_tokens"] == 15
    assert roll["entries"] == 1

    bad = client.post("/api/v1/agent-work-items/nope/tokens", json={"input_tokens": 1})
    assert bad.status_code == 404
