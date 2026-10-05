from __future__ import annotations

from pathlib import Path

import pytest

from synapse_daemon.repair_arena import run_repair_arena


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fake_components(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    app_doctor = tmp_path / "AppDoctor"
    arcade = tmp_path / "AgentArcade"
    target = tmp_path / "TargetProject"
    target.mkdir()

    _write(
        app_doctor / "doctor_engine.py",
        """
def scan_project(path):
    return {
        'project': {'name': 'TargetProject', 'path': path, 'stack': ['Python']},
        'score': 74,
        'grade': 'C',
        'metrics': {'files_scanned': 7, 'test_files': 1},
        'findings': [
            {
                'id': 'missing-proof', 'category': 'reliability', 'severity': 'high',
                'title': 'Missing proof', 'detail': 'A verified proof is missing.',
                'evidence': 'tests/test_target.py', 'recommendation': 'Add bounded proof.',
                'confidence': 0.9, 'priority_rank': 1,
            }
        ],
    }

def format_repair_prompt(report):
    return 'repair prompt for ' + report['project']['name']
""",
    )
    _write(
        app_doctor / "evidence_runner.py",
        """
def discover_test_plans(path):
    return [{'id': 'unit', 'label': 'Unit tests', 'supported': True,
             'requires_project_code': True, 'reason': 'Discovered only.'}]
""",
    )
    _write(
        app_doctor / "repair_arena_bridge.py",
        """
DEFAULT_REPAIR_AGENTS = [
    {'agent_id': 'architect', 'name': 'Architect', 'style': 'architect'},
    {'agent_id': 'builder', 'name': 'Builder', 'style': 'builder'},
]

def build_repair_challenge(report, test_plans, repair_prompt=''):
    return {
        'challenge_id': 'challenge123',
        'project': report['project'],
        'baseline': {'score': report['score'], 'grade': report['grade'], 'metrics': report['metrics']},
        'findings': report['findings'],
        'test_plans': test_plans,
        'repair_prompt': repair_prompt,
        'objective': 'Repair TargetProject with evidence.',
    }
""",
    )
    _write(
        arcade / "arena_engine.py",
        """
def run_tournament(objective, agents, rounds=2, mode='demo'):
    assert objective == 'Repair TargetProject with evidence.'
    assert rounds == 2
    assert mode == 'demo'
    return {
        'mode': mode,
        'champion': {'agent_id': 'builder', 'name': 'Builder', 'average_score': 92.0, 'rank': 1},
        'scoreboard': [
            {'agent_id': 'builder', 'name': 'Builder', 'average_score': 92.0, 'rank': 1},
            {'agent_id': 'architect', 'name': 'Architect', 'average_score': 88.0, 'rank': 2},
        ],
        'rounds': [
            {'round': 1, 'rankings': [
                {'agent_id': 'builder', 'response': 'first plan'},
                {'agent_id': 'architect', 'response': 'boundary plan'},
            ]},
            {'round': 2, 'rankings': [
                {'agent_id': 'builder', 'response': 'winning verified plan'},
                {'agent_id': 'architect', 'response': 'refined boundary plan'},
            ]},
        ],
    }
""",
    )
    _write(
        arcade / "history_store.py",
        """
class TournamentHistoryStore:
    def __init__(self, path):
        self.path = path
    def save(self, result):
        stored = dict(result)
        stored['tournament_id'] = 'tour123'
        stored['created_at'] = '2026-09-07T12:00:00-05:00'
        return stored
""",
    )

    monkeypatch.setenv("SYNAPSE_APP_DOCTOR_ROOT", str(app_doctor))
    monkeypatch.setenv("SYNAPSE_AGENT_ARCADE_ROOT", str(arcade))
    return target, app_doctor, arcade


def test_repair_arena_returns_machine_readable_planning_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    target, _, _ = _fake_components(tmp_path, monkeypatch)
    marker = target / "must-not-change.txt"
    marker.write_text("original", encoding="utf-8")

    result = run_repair_arena(
        str(target), project_id="target-project", project_name="Target Project", rounds=2, mode="demo"
    )

    assert result["contract_version"] == "1.1"
    assert result["project"]["id"] == "target-project"
    assert result["baseline"]["score"] == 74
    assert result["findings"][0]["severity"] == "high"
    assert result["test_plans"][0]["requires_project_code"] is True
    assert result["tournament"]["tournament_id"] == "tour123"
    assert result["tournament"]["champion"]["agent_id"] == "builder"
    assert result["tournament"]["winning_plan"] == "winning verified plan"
    assert result["tournament"]["candidate_plans"][0]["agent_id"] == "builder"
    assert result["tournament"]["candidate_plans"][0]["plan"] == "winning verified plan"
    assert result["candidate_staging"] is None
    assert result["execution_policy"]["planning_only"] is True
    assert result["execution_policy"]["target_repository_modified"] is False
    assert result["execution_policy"]["project_tests_executed"] is False
    assert result["execution_policy"]["auto_merge"] is False
    assert result["promotion_gate"]["eligible_now"] is False
    assert marker.read_text(encoding="utf-8") == "original"


def test_repair_arena_validates_rounds_before_loading_components(tmp_path: Path):
    target = tmp_path / "target"
    target.mkdir()
    with pytest.raises(ValueError, match="rounds"):
        run_repair_arena(str(target), rounds=0)


def test_repair_arena_validates_mode_before_loading_components(tmp_path: Path):
    target = tmp_path / "target"
    target.mkdir()
    with pytest.raises(ValueError, match="mode"):
        run_repair_arena(str(target), mode="unknown")


def test_mcp_repair_arena_exposes_optional_candidate_staging():
    from synapse_daemon.mcp_connector import _tool_specs

    spec = next(item for item in _tool_specs(allow_writes=True) if item["name"] == "synapse_repair_arena")
    props = spec["inputSchema"]["properties"]
    assert props["prepare_candidates"]["type"] == "boolean"
    assert props["candidate_count"]["minimum"] == 1
    assert props["candidate_count"]["maximum"] == 3
    assert spec["annotations"]["destructiveHint"] is False
