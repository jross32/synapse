from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from synapse_daemon import ai_executions, coder_runtimes, review_engine
from synapse_daemon.projects import Project, ProjectKind


@pytest.fixture(autouse=True)
def _pretend_default_runtimes_are_installed(monkeypatch) -> None:
    # Pure planner tests do not have the daemon's SQLite capacity ledger.
    monkeypatch.setattr(coder_runtimes, "available", lambda runtime: True)


def _project(tmp_path, *, project_id: str = "demo", kind: ProjectKind = ProjectKind.APP) -> Project:
    return Project(
        id=project_id,
        name="Demo",
        path=str(tmp_path),
        launch_cmd="python -m demo",
        kind=kind,
    )


def test_small_source_change_uses_one_economy_review_and_independent_runtime(tmp_path) -> None:
    project = _project(tmp_path)
    plan = review_engine.plan_project_review(
        project,
        review_engine.ReviewEngineRequest(
            changed_files=["src/demo.py"],
            diff_text="+def answer():\n+    return 42\n",
            primary_runtime="codex",
        ),
    )

    assert plan.risk == review_engine.ReviewRisk.LOW
    assert plan.mode == review_engine.ReviewMode.ECONOMY
    assert plan.ai_review_required is True
    assert len(plan.review_passes) == 1
    assert plan.review_passes[0].review_kind == "qa"
    assert plan.review_passes[0].requested_runtime_id == "claude"
    assert any(item.id == "source-without-tests" for item in plan.deterministic_findings)
    assert plan.policy.token_budget == 8_000


def test_high_risk_auth_change_escalates_but_caps_pass_count(tmp_path) -> None:
    project = _project(tmp_path)
    plan = review_engine.plan_project_review(
        project,
        review_engine.ReviewEngineRequest(
            changed_files=["daemon/auth/session.py", "daemon/tests/test_auth.py"],
            diff_text="+def authorize(token):\n+    return token is not None\n",
            primary_runtime="claude",
        ),
    )

    assert plan.risk == review_engine.ReviewRisk.HIGH
    assert plan.mode == review_engine.ReviewMode.THOROUGH
    assert plan.policy.max_ai_passes == 3
    assert len(plan.review_passes) == 3
    assert {item.review_kind for item in plan.review_passes} == {"qa", "security", "judge"}
    assert all(item.requested_runtime_id != "claude" for item in plan.review_passes[:2])


def test_docs_only_change_skips_ai_by_default(tmp_path) -> None:
    project = _project(tmp_path)
    plan = review_engine.plan_project_review(
        project,
        review_engine.ReviewEngineRequest(
            changed_files=["docs/guide.md", "README.md"],
            diff_text="+Clarify the setup instructions.\n",
        ),
    )

    assert plan.change.docs_only is True
    assert plan.ai_review_required is False
    assert plan.review_passes == []
    assert "Docs-only" in plan.reason


def test_force_ai_can_review_docs_only_change(tmp_path) -> None:
    project = _project(tmp_path)
    plan = review_engine.plan_project_review(
        project,
        review_engine.ReviewEngineRequest(
            changed_files=["docs/guide.md"],
            diff_text="+New public contract wording.\n",
            force_ai=True,
        ),
    )

    assert plan.ai_review_required is True
    assert len(plan.review_passes) == 1


def test_release_mode_warns_when_release_docs_are_untouched(tmp_path) -> None:
    project = _project(tmp_path)
    plan = review_engine.plan_project_review(
        project,
        review_engine.ReviewEngineRequest(
            mode=review_engine.ReviewMode.RELEASE,
            changed_files=["src/package.py"],
            diff_text='+__version__ = "2.0.0"\n',
        ),
    )

    assert plan.mode == review_engine.ReviewMode.RELEASE
    finding = next(item for item in plan.deterministic_findings if item.id == "release-metadata-not-touched")
    assert finding.severity == "warning"
    assert "changelog.md" in finding.detail
    assert "readme.md" in finding.detail
    assert len(plan.review_passes) <= 4


def test_secret_file_blocks_ai_and_withholds_diff(tmp_path) -> None:
    project = _project(tmp_path)
    plan = review_engine.plan_project_review(
        project,
        review_engine.ReviewEngineRequest(
            changed_files=[".env", "src/app.py"],
            diff_text="+API_KEY=super-secret-value\n",
            force_ai=True,
        ),
    )

    assert plan.ai_review_required is False
    assert any(item.id == "secret-file-changed" for item in plan.deterministic_findings)
    assert "withheld" in review_engine.bounded_diff_for_prompt(plan)
    assert "super-secret-value" not in review_engine.bounded_diff_for_prompt(plan)


def test_repo_local_policy_customizes_budget_and_focus_without_code_change(tmp_path) -> None:
    policy_dir = tmp_path / ".synapse"
    policy_dir.mkdir()
    (policy_dir / "review-policy.json").write_text(
        json.dumps(
            {
                "mode": "standard",
                "token_budget": 12_000,
                "max_ai_passes": 2,
                "max_diff_chars": 10_000,
                "focus_points": [
                    "Never imply a confidence score is a guaranteed return.",
                    "Require point-in-time evidence semantics.",
                ],
            }
        ),
        encoding="utf-8",
    )
    project = _project(tmp_path, project_id="specialized-app")

    plan = review_engine.plan_project_review(
        project,
        review_engine.ReviewEngineRequest(
            changed_files=["src/ranking.py", "tests/test_ranking.py"],
            diff_text="+score = evidence_score()\n",
        ),
    )

    assert plan.policy.source == ".synapse/review-policy.json"
    assert plan.mode == review_engine.ReviewMode.STANDARD
    assert plan.policy.token_budget == 12_000
    assert len(plan.review_passes) == 1  # one candidate is enough for this low-risk diff
    assert "Require point-in-time evidence semantics." in plan.review_passes[0].focus_points


def test_diff_context_is_truncated_to_policy_cap(tmp_path) -> None:
    policy_dir = tmp_path / ".synapse"
    policy_dir.mkdir()
    (policy_dir / "review-policy.json").write_text(
        json.dumps({"max_diff_chars": 4_000}), encoding="utf-8"
    )
    project = _project(tmp_path)
    diff = "+x = 1\n" * 2_000
    plan = review_engine.plan_project_review(
        project,
        review_engine.ReviewEngineRequest(
            changed_files=["src/app.py", "tests/test_app.py"],
            diff_text=diff,
        ),
    )

    bounded = review_engine.bounded_diff_for_prompt(plan)
    assert len(bounded) < len(diff)
    assert "truncated by Synapse review budget" in bounded
    assert plan.estimated_context_tokens <= plan.policy.token_budget



def test_release_title_triggers_release_mode_without_release_files(tmp_path) -> None:
    project = _project(tmp_path)
    plan = review_engine.plan_project_review(
        project,
        review_engine.ReviewEngineRequest(
            change_title="v1.61: make timeline semantics explicit",
            changed_files=["src/feature.py", "tests/test_feature.py"],
            diff_text="+TIMELINE_SEMANTICS = 're-evaluation'\n",
        ),
    )
    assert plan.mode == review_engine.ReviewMode.RELEASE
    assert any(item.review_kind == "release" for item in plan.review_passes)


def test_changed_file_without_diff_stays_in_free_evidence_lane(tmp_path) -> None:
    project = _project(tmp_path)
    plan = review_engine.plan_project_review(
        project,
        review_engine.ReviewEngineRequest(changed_files=["src/new_file.py"]),
    )
    assert plan.change.diff_complete is False
    assert plan.ai_review_required is False
    assert any(item.id == "diff-evidence-incomplete" for item in plan.deterministic_findings)


def test_secret_like_assignment_blocks_ai_even_in_normal_source_file(tmp_path) -> None:
    project = _project(tmp_path)
    plan = review_engine.plan_project_review(
        project,
        review_engine.ReviewEngineRequest(
            changed_files=["src/config.py"],
            diff_text="+API_KEY=sk_live_1234567890abcdef\n",
            force_ai=True,
        ),
    )
    assert plan.ai_review_required is False
    assert any(item.id == "secret-like-value-in-diff" for item in plan.deterministic_findings)
    assert "sk_live_1234567890abcdef" not in review_engine.bounded_diff_for_prompt(plan)


def test_aggregate_budget_counts_repeated_context_across_passes(tmp_path) -> None:
    project = _project(tmp_path)
    diff = "+x = 1\n" * 18_000
    plan = review_engine.plan_project_review(
        project,
        review_engine.ReviewEngineRequest(
            mode=review_engine.ReviewMode.RELEASE,
            changed_files=["src/app.py", "tests/test_app.py"],
            diff_text=diff,
            change_title="release v9.9.9",
        ),
    )
    assert plan.review_passes
    assert plan.estimated_aggregate_tokens == sum(
        item.estimated_total_tokens for item in plan.review_passes
    )
    assert plan.estimated_context_tokens == sum(
        item.estimated_input_tokens for item in plan.review_passes
    )
    assert plan.estimated_aggregate_tokens <= plan.policy.token_budget
    assert plan.budget_remaining_after_plan == plan.policy.token_budget - plan.estimated_aggregate_tokens


def test_runtime_capacity_skips_unavailable_or_primary_reviewers(tmp_path) -> None:
    now = datetime.now(UTC)
    capacity = [
        ai_executions.RuntimeCapacity(
            runtime_id="codex", state=ai_executions.RuntimeCapacityState.AVAILABLE,
            usable_now=True, eligible_for_attempt=True, updated_at=now,
        ),
        ai_executions.RuntimeCapacity(
            runtime_id="claude", state=ai_executions.RuntimeCapacityState.QUOTA_EXHAUSTED,
            usable_now=False, eligible_for_attempt=False, updated_at=now,
        ),
        ai_executions.RuntimeCapacity(
            runtime_id="copilot", state=ai_executions.RuntimeCapacityState.AVAILABLE,
            usable_now=True, eligible_for_attempt=True, updated_at=now,
        ),
    ]
    plan = review_engine.plan_project_review(
        _project(tmp_path),
        review_engine.ReviewEngineRequest(
            changed_files=["src/app.py", "tests/test_app.py"],
            diff_text="+x = 1\n",
            primary_runtime="codex",
        ),
        runtime_capacity=capacity,
    )
    assert plan.ai_review_required is True
    assert {item.requested_runtime_id for item in plan.review_passes} == {"copilot"}


def test_no_independent_runtime_means_no_doomed_review_pass(tmp_path) -> None:
    now = datetime.now(UTC)
    capacity = [
        ai_executions.RuntimeCapacity(
            runtime_id="codex", state=ai_executions.RuntimeCapacityState.AVAILABLE,
            usable_now=True, eligible_for_attempt=True, updated_at=now,
        ),
        ai_executions.RuntimeCapacity(
            runtime_id="claude", state=ai_executions.RuntimeCapacityState.NOT_INSTALLED,
            usable_now=False, eligible_for_attempt=False, updated_at=now,
        ),
    ]
    plan = review_engine.plan_project_review(
        _project(tmp_path),
        review_engine.ReviewEngineRequest(
            changed_files=["src/app.py"], diff_text="+x = 1\n", primary_runtime="codex"
        ),
        runtime_capacity=capacity,
    )
    assert plan.ai_review_required is False
    assert plan.review_passes == []
    assert "No independent reviewer runtime" in plan.reason


def test_common_secret_file_patterns_block_ai_context(tmp_path) -> None:
    for secret_path in (".env.development", ".npmrc", "certs/private.pem", "config/credentials.yaml"):
        plan = review_engine.plan_project_review(
            _project(tmp_path),
            review_engine.ReviewEngineRequest(
                changed_files=[secret_path],
                diff_text="+SAFE_EXAMPLE=placeholder-value\n",
                force_ai=True,
            ),
        )
        assert plan.ai_review_required is False
        assert any(item.id == "secret-file-changed" for item in plan.deterministic_findings)
        assert "withheld" in review_engine.bounded_diff_for_prompt(plan)
