from __future__ import annotations

import subprocess
from pathlib import Path

from synapse_daemon.repair_arena_candidates import (
    evaluate_staged_candidate,
    inspect_candidate_worktree,
    prepare_candidate_worktrees,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "target"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True, text=True)
    _git(repo, "config", "user.email", "repair-arena@example.invalid")
    _git(repo, "config", "user.name", "Repair Arena Test")
    (repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "baseline")
    return repo


def test_prepare_candidate_worktrees_preserves_primary_tree_and_starts_clean(tmp_path: Path):
    repo = _repo(tmp_path)
    (repo / "local-note.txt").write_text("unrelated local work\n", encoding="utf-8")
    status_before = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")

    result = prepare_candidate_worktrees(
        str(repo),
        project_id="target-project",
        project_name="Target Project",
        tournament_id="tour-123",
        candidates=[
            {"rank": 1, "agent_id": "builder", "name": "Builder", "score": 91.2, "plan": "Add the regression test first."},
            {"rank": 2, "agent_id": "critic", "name": "Critic", "score": 88.4, "plan": "Verify the reported defect before changing code."},
        ],
        baseline={"score": 72, "grade": "C"},
        findings=[{"id": "bug-1", "severity": "high", "title": "Bug"}],
        candidate_count=2,
        workspace_root=tmp_path / "arena-workspaces",
    )

    assert result["prepared"] is True
    assert result["candidate_count"] == 2
    assert result["primary_working_tree_preserved"] is True
    assert result["repository_metadata_modified"] is True
    assert Path(result["staging_receipt_path"]).is_file()
    assert _git(repo, "status", "--porcelain=v1", "--untracked-files=all") == status_before

    for candidate in result["candidates"]:
        worktree = Path(candidate["worktree_path"])
        brief = Path(candidate["brief_path"])
        assert worktree.is_dir()
        assert brief.is_file()
        assert candidate["worktree_clean_at_stage"] is True
        assert _git(worktree, "status", "--porcelain=v1", "--untracked-files=all") == ""
        assert brief.parent == worktree.parent
        assert brief.parent != worktree


def test_inspect_candidate_worktree_reports_changes_without_running_code(tmp_path: Path):
    repo = _repo(tmp_path)
    staged = prepare_candidate_worktrees(
        str(repo),
        project_id="target-project",
        project_name="Target Project",
        tournament_id="tour-456",
        candidates=[{"rank": 1, "agent_id": "builder", "plan": "Change app.py safely."}],
        candidate_count=1,
        workspace_root=tmp_path / "arena-workspaces",
    )
    candidate = staged["candidates"][0]
    worktree = Path(candidate["worktree_path"])
    (worktree / "app.py").write_text("VALUE = 2\n", encoding="utf-8")

    receipt = inspect_candidate_worktree(str(worktree), base_commit=staged["base_commit"])

    assert receipt["dirty"] is True
    assert receipt["changed_files"] == ["app.py"]
    assert receipt["tests_executed"] is False
    assert receipt["project_code_executed"] is False
    assert receipt["eligible_for_promotion"] is False


def test_evaluate_staged_candidate_compares_static_findings_without_running_project(tmp_path: Path):
    repo = _repo(tmp_path)
    app_doctor = tmp_path / "AppDoctor"
    app_doctor.mkdir()
    (app_doctor / "doctor_engine.py").write_text(
        """
def scan_project(path):
    from pathlib import Path
    text = (Path(path) / 'app.py').read_text(encoding='utf-8')
    if 'VALUE = 1' in text:
        findings = [{'id': 'bug-1', 'severity': 'high', 'title': 'Old value'}]
        score = 70
    else:
        findings = []
        score = 95
    return {'project': {'name': 'Target', 'path': path, 'stack': ['Python']},
            'score': score, 'grade': 'A' if score >= 90 else 'C', 'metrics': {}, 'findings': findings}
""",
        encoding="utf-8",
    )
    staged = prepare_candidate_worktrees(
        str(repo),
        project_id="target-project",
        project_name="Target Project",
        tournament_id="tour-eval",
        candidates=[{"rank": 1, "agent_id": "builder", "plan": "Change the old value."}],
        baseline={"score": 70, "grade": "C"},
        findings=[{"id": "bug-1", "severity": "high", "title": "Old value"}],
        candidate_count=1,
        workspace_root=tmp_path / "arena-workspaces",
    )
    worktree = Path(staged["candidates"][0]["worktree_path"])
    (worktree / "app.py").write_text("VALUE = 2\n", encoding="utf-8")

    result = evaluate_staged_candidate(
        "target-project",
        "tour-eval",
        candidate="builder",
        workspace_root=tmp_path / "arena-workspaces",
        app_doctor_root=app_doctor,
    )

    assert result["provisional_outcome"] == "static_improvement_detected"
    assert result["app_doctor"]["fixed_finding_ids"] == ["bug-1"]
    assert result["app_doctor"]["score_delta"] == 25.0
    assert result["verification"]["tests_executed"] is False
    assert result["verification"]["project_code_executed"] is False
    assert result["promotion_gate"]["eligible_now"] is False
