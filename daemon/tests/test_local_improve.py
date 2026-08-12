"""Tests for the improver's safety gates.

These matter more than its ability to find a win. An improver that promotes a lucky run, or
one that trades tool-calling for coding, makes the system worse while reporting progress -
which is harder to notice than an improver that simply never helps.
"""

from __future__ import annotations

import pytest

from synapse_daemon import local_improve as LI
from synapse_daemon.local_improve import Config, Measurement


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Never touch the real improver state from a test."""
    monkeypatch.setattr(LI, "state_dir", lambda: tmp_path)


def _fake_measure(scores_by_config):
    """Return canned scores keyed by a config attribute, so gates can be tested exactly."""
    def measure(config, skills, only_ids=None, repeats=1):
        per_skill = scores_by_config(config, only_ids)
        mean = sum(per_skill.values()) / len(per_skill) if per_skill else 0.0
        return Measurement(config=config, per_skill=per_skill, mean=round(mean, 4))
    return measure


def test_a_gain_inside_the_noise_floor_is_rejected(monkeypatch):
    """Promoting luck is how a search convinces itself it is working."""
    monkeypatch.setattr(LI, "noise_floor", lambda *a, **k: 0.10)
    monkeypatch.setattr(LI, "measure", _fake_measure(
        lambda cfg, ids: {"coding": 0.80 if cfg.num_ctx == 4096 else 0.85}))

    d = LI.evaluate_candidate("num_ctx", 8192, ["coding"], Config(num_ctx=4096))
    assert d.verdict == "rejected"
    assert "noise floor" in d.reason


def test_a_win_that_regresses_another_skill_is_rejected(monkeypatch):
    """The exact mistake of reading one number as a fact about the whole system."""
    monkeypatch.setattr(LI, "noise_floor", lambda *a, **k: 0.01)
    monkeypatch.setattr(LI, "measure", _fake_measure(
        lambda cfg, ids: ({"coding": 0.60, "tool_calling": 0.90} if cfg.num_ctx == 4096
                          else {"coding": 0.95, "tool_calling": 0.50})))

    d = LI.evaluate_candidate("num_ctx", 8192, ["coding", "tool_calling"], Config(num_ctx=4096))
    assert d.verdict == "rejected"
    assert "tool_calling" in str(d.regressions)


def test_a_tuning_set_win_that_fails_held_out_is_rejected_as_overfitting(monkeypatch):
    """The whole reason a slice of checks is never tuned against."""
    monkeypatch.setattr(LI, "noise_floor", lambda *a, **k: 0.01)

    def measure(config, skills, only_ids=None, repeats=1):
        tuning = only_ids is not None and any(
            len(v) > 3 for v in (only_ids or {}).values())
        better = config.num_ctx == 8192
        score = (0.95 if better else 0.60) if tuning else (0.40 if better else 0.80)
        return Measurement(config=config, per_skill={"coding": score}, mean=score)

    monkeypatch.setattr(LI, "measure", measure)
    monkeypatch.setattr(LI, "split_tasks", lambda skills: ({"coding": ["a", "b", "c", "d"]},
                                                           {"coding": ["e", "f"]}))

    d = LI.evaluate_candidate("num_ctx", 8192, ["coding"], Config(num_ctx=4096))
    assert d.verdict == "rejected"
    assert "overfitting" in d.reason


def test_a_genuine_win_is_accepted(monkeypatch):
    monkeypatch.setattr(LI, "noise_floor", lambda *a, **k: 0.01)
    monkeypatch.setattr(LI, "measure", _fake_measure(
        lambda cfg, ids: {"coding": 0.95 if cfg.num_ctx == 8192 else 0.60,
                          "tool_calling": 0.80}))

    d = LI.evaluate_candidate("num_ctx", 8192, ["coding", "tool_calling"], Config(num_ctx=4096))
    assert d.verdict == "accepted"
    assert d.held_out_confirmed


def test_shadow_mode_changes_nothing(monkeypatch):
    """Autonomy is earned. Until then it may observe and record only."""
    monkeypatch.setattr(LI, "noise_floor", lambda *a, **k: 0.01)
    monkeypatch.setattr(LI, "measure", _fake_measure(
        lambda cfg, ids: {"coding": 0.95 if cfg.temperature == 0.2 else 0.60}))

    before = LI.active_config().model_dump()
    decisions = LI.run_experiment(skills=["coding"], variables=["temperature"], repeats=1)

    assert any(d.verdict == "accepted" for d in decisions), "should find the win"
    assert not any(d.promoted for d in decisions), "shadow mode must not promote"
    assert LI.active_config().model_dump() == before, "config must be untouched"


def test_promotion_unlocks_only_after_repeated_calibration():
    for i in range(LI.CALIBRATION_THRESHOLD - 1):
        state = LI._record_calibration(True)
        assert state["mode"] == LI.Autonomy.SHADOW.value, f"unlocked too early at {i+1}"
    state = LI._record_calibration(True)
    assert state["mode"] == LI.Autonomy.PROMOTE.value


def test_a_wrong_prediction_resets_the_streak():
    LI._record_calibration(True)
    LI._record_calibration(True)
    state = LI._record_calibration(False)
    assert state["calibrated_streak"] == 0
    assert state["mode"] == LI.Autonomy.SHADOW.value


def test_rollback_restores_the_previous_config():
    """One call, because a bad promotion has to be cheap to undo."""
    LI.set_active_config(Config(num_ctx=4096), "first")
    LI.set_active_config(Config(num_ctx=8192), "second")
    assert LI.active_config().num_ctx == 8192

    restored = LI.rollback()
    assert restored is not None and restored.num_ctx == 4096
    assert LI.active_config().num_ctx == 4096


def test_the_search_space_cannot_reach_source_code():
    """The improver tunes configuration, never code. Guard the boundary explicitly."""
    for variable in LI.SEARCH_SPACE:
        assert variable in Config.model_fields, (
            f"{variable} is not a Config field, so it is not a bounded option")
    for values in LI.SEARCH_SPACE.values():
        for value in values:
            assert isinstance(value, (str, int, float, bool)), (
                "search values must be plain data - anything executable would make this an "
                "agent editing the system rather than a bounded search")
