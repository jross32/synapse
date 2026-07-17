"""Bug-hunt scoring helper (Plan 3 Phase 2) -- in-daemon twin of bug-hunt-fixture/grade.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.benchmarks import BugHuntScore, load_fixture_answer_key, score_bug_hunt
from synapse_daemon.errors import SynapseError
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus

_INLINE_KEY = {
    "bugs": [
        {"id": "X1", "surface": "form", "match": ["empty submit", "no validation"]},
        {"id": "X2", "surface": "nav", "match": ["nav overlap", "unclickable"]},
    ]
}


def test_scores_true_and_false_positives() -> None:
    findings = [
        {"surface": "form", "text": "Empty submit still succeeds -- no validation"},
        {"surface": "footer", "text": "the year looks old"},
    ]
    score = score_bug_hunt(_INLINE_KEY, findings, total_tokens=10_000)
    assert isinstance(score, BugHuntScore)
    assert score.true_positives == 1
    assert score.false_positives == 1
    assert score.missed == ["X2"]
    assert score.recall == 0.5
    assert score.false_positive_rate == 0.5
    assert score.bugs_per_1k_tokens == 0.1  # 1 / (10000/1000)


def test_duplicate_finding_not_double_counted() -> None:
    findings = [
        {"text": "empty submit, no validation at all"},
        {"text": "again: empty submit with no validation"},
    ]
    score = score_bug_hunt(_INLINE_KEY, findings, total_tokens=5_000)
    assert score.true_positives == 1
    assert score.duplicates == 1
    assert score.false_positives == 0


def test_finding_naming_two_bugs_credits_the_still_open_one() -> None:
    # A single finding blob contains phrases for two distinct bugs. The first (A) is already
    # claimed by an earlier finding; the second (B) is still open. The finding must get credit
    # for B rather than being dropped as a duplicate of A -- otherwise true_positives (and the
    # headline bugs_per_1k_tokens the topology benchmark ranks on) are deflated.
    key = {
        "bugs": [
            {"id": "A", "match": ["slow load"]},
            {"id": "B", "match": ["broken link"]},
        ]
    }
    findings = [
        {"text": "the homepage has a slow load"},  # claims A
        {"text": "still a slow load, and also a broken link in the footer"},  # matches A (claimed) + B (open)
    ]
    score = score_bug_hunt(key, findings, total_tokens=10_000)
    assert score.true_positives == 2  # A and B, not 1 + a dropped duplicate
    assert score.duplicates == 0
    assert score.missed == []


def test_true_duplicate_still_counts_when_no_other_bug_matches() -> None:
    # Guard the fix's boundary: a finding matching ONLY an already-claimed bug is still a duplicate.
    findings = [
        {"text": "empty submit, no validation"},
        {"text": "yet another empty submit, no validation"},  # only ever matches X1 (claimed)
    ]
    score = score_bug_hunt(_INLINE_KEY, findings, total_tokens=5_000)
    assert score.true_positives == 1
    assert score.duplicates == 1
    assert score.false_positives == 0


def test_zero_tokens_gives_none_efficiency() -> None:
    score = score_bug_hunt(_INLINE_KEY, [{"text": "nav overlap, unclickable"}], total_tokens=0)
    assert score.true_positives == 1
    assert score.bugs_per_1k_tokens is None


def test_empty_findings() -> None:
    score = score_bug_hunt(_INLINE_KEY, [], total_tokens=1_000)
    assert score.true_positives == 0
    assert score.false_positives == 0
    assert score.missed == ["X1", "X2"]
    assert score.recall == 0.0


def test_matches_shipped_fixture_answer_key() -> None:
    key_path = Path(__file__).resolve().parents[2] / "benchmarks" / "bug-hunt-fixture" / "answer-key.json"
    key = json.loads(key_path.read_text(encoding="utf-8"))
    findings = [
        {"surface": "contact form", "text": "Empty submit still shows success -- no validation"},
        {"surface": "header", "text": "Mobile nav overlaps the logo and links are unclickable"},
        {"surface": "contact confirmation", "text": "Name into innerHTML unescaped -> reflected XSS"},
        {"surface": "footer", "text": "copyright year feels old"},
    ]
    score = score_bug_hunt(key, findings, total_tokens=10_000)
    assert score.total_bugs == 12
    assert score.true_positives == 3  # B01, B04, B12
    assert score.false_positives == 1
    assert score.bugs_per_1k_tokens == 0.3
    assert len(score.missed) == 9


def _client(tmp_path: Path) -> TestClient:
    s = Storage(tmp_path / "data")
    s.open()
    s.migrate()
    app = build_app(s, EventBus())
    return TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})


def test_score_bug_hunt_route(tmp_path: Path) -> None:
    with _client(tmp_path) as c:
        r = c.post(
            "/api/v1/benchmarks/score-bug-hunt",
            json={
                "answer_key": _INLINE_KEY,
                "findings": [
                    {"surface": "form", "text": "empty submit, no validation"},
                    {"text": "totally unrelated nitpick"},
                ],
                "total_tokens": 2_000,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["true_positives"] == 1
        assert body["false_positives"] == 1
        assert body["bugs_per_1k_tokens"] == 0.5


def test_load_fixture_answer_key_resolves_shipped_fixture() -> None:
    key = load_fixture_answer_key("bug-hunt-fixture")
    assert key["fixture"] == "buttermore-bakery"
    assert len(key["bugs"]) == 12


def test_load_fixture_answer_key_rejects_path_traversal() -> None:
    for bad in ("../secret", "a/b", "..", ""):
        with pytest.raises(SynapseError):
            load_fixture_answer_key(bad)


def test_load_fixture_answer_key_unknown_fixture() -> None:
    with pytest.raises(SynapseError):
        load_fixture_answer_key("no-such-fixture")


def test_score_route_accepts_fixture_name(tmp_path: Path) -> None:
    with _client(tmp_path) as c:
        r = c.post(
            "/api/v1/benchmarks/score-bug-hunt",
            json={
                "fixture": "bug-hunt-fixture",
                "findings": [
                    {"surface": "contact form", "text": "empty submit shows success, no validation"},
                    {"surface": "header", "text": "mobile nav overlaps logo, unclickable"},
                ],
                "total_tokens": 10_000,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total_bugs"] == 12
        assert body["true_positives"] == 2  # B01, B04
        assert body["bugs_per_1k_tokens"] == 0.2


def test_score_route_requires_key_or_fixture(tmp_path: Path) -> None:
    with _client(tmp_path) as c:
        r = c.post("/api/v1/benchmarks/score-bug-hunt", json={"findings": [], "total_tokens": 100})
        assert r.status_code >= 400


def test_list_bug_hunt_fixtures_includes_shipped() -> None:
    from synapse_daemon.benchmarks import list_bug_hunt_fixtures

    names = {f["name"]: f for f in list_bug_hunt_fixtures()}
    assert "bug-hunt-fixture" in names
    assert names["bug-hunt-fixture"]["total_bugs"] == 12
    assert names["bug-hunt-fixture"]["fixture"] == "buttermore-bakery"


def test_list_bug_hunt_fixtures_route(tmp_path: Path) -> None:
    with _client(tmp_path) as c:
        r = c.get("/api/v1/benchmarks/bug-hunt-fixtures")
        assert r.status_code == 200, r.text
        assert any(f["name"] == "bug-hunt-fixture" for f in r.json()["fixtures"])


def test_score_includes_per_category_breakdown() -> None:
    from synapse_daemon.benchmarks import load_fixture_answer_key

    key = load_fixture_answer_key("bug-hunt-fixture")
    findings = [
        {"surface": "contact form", "text": "empty submit shows success, no validation"},  # B01 functional
        {"surface": "header", "text": "mobile nav overlaps logo, unclickable"},  # B04 ui
        {"surface": "contact confirmation", "text": "name into innerHTML unescaped -> xss"},  # B12 security
    ]
    score = score_bug_hunt(key, findings, total_tokens=10_000)
    bc = score.by_category
    assert bc["functional"] == {"found": 1, "total": 2}
    assert bc["ui"] == {"found": 1, "total": 2}
    assert bc["security"] == {"found": 1, "total": 1}
    assert bc["accessibility"] == {"found": 0, "total": 3}  # found nothing in this class
    assert sum(c["total"] for c in bc.values()) == 12
