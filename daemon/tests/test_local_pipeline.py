"""Tests for the code-orchestrated local codegen pipeline.

Both the model and the test-runner are stubbed. What is under test is the orchestration --
generate, test, repair, escalate -- not Ollama and not ``subprocess``. Spawning real
processes here also made the suite hostage to this machine's real-time AV, which the shared
conftest already works around for file scanning. The pipeline is exercised end to end for
real by ``benchmarks/local-models/squad_bench.py``, which scores it at 100%.
"""

from __future__ import annotations

from synapse_daemon import local_pipeline

IMPL_WRONG = "def add(a, b):\n    return a - b\n"
IMPL_RIGHT = "def add(a, b):\n    return a + b\n"
TEST_CODE = "from solution import add\nassert add(2, 2) == 4\nprint('OK')\n"


def _fake_runner(results):
    """A runner that yields the given (ok, error) pairs in order."""
    it = iter(results)

    def run(_test_file, _cwd):
        return next(it)

    return run


async def test_repairs_from_a_real_error(tmp_path, monkeypatch):
    """A failing test must trigger re-generation, not a declared success."""
    answers = iter([IMPL_WRONG, TEST_CODE, IMPL_RIGHT])
    monkeypatch.setattr(local_pipeline, "generate_code", lambda *a, **k: next(answers))

    result = await local_pipeline.run_pipeline(
        "Write add(a, b) returning the sum.", workspace=tmp_path, max_repairs=2,
        runner=_fake_runner([(False, "AssertionError: add(2, 2) == 0"), (True, "")]))

    assert result.passed, result.stop_reason
    assert len(result.attempts) == 1, "should have needed exactly one repair"
    assert "a + b" in result.code
    assert result.attempts[0].changed
    assert not result.needs_escalation


async def test_escalates_with_a_self_contained_packet(tmp_path, monkeypatch):
    """Escalation only saves money if a stronger model can act on the packet alone."""
    codes = iter([IMPL_WRONG, TEST_CODE,
                  "def add(a, b):\n    return a * b\n",
                  "def add(a, b):\n    return a / b\n"])
    monkeypatch.setattr(local_pipeline, "generate_code", lambda *a, **k: next(codes))

    result = await local_pipeline.run_pipeline(
        "Write add(a, b) returning the sum.", workspace=tmp_path, max_repairs=2,
        runner=_fake_runner([(False, "AssertionError: got 0"),
                             (False, "AssertionError: got 4"),
                             (False, "AssertionError: got 1.0")]))

    assert not result.passed
    assert result.needs_escalation
    packet = result.escalation_packet
    assert "REQUIREMENT:" in packet
    assert "CURRENT CODE" in packet
    assert "LAST ERROR:" in packet, "a packet without the error cannot be acted on"
    assert "Write add(a, b)" in packet


async def test_gives_up_when_the_model_stops_changing_anything(tmp_path, monkeypatch):
    """An identical answer twice means more attempts cannot help, so stop early."""
    monkeypatch.setattr(
        local_pipeline, "generate_code",
        lambda spec, *a, **k: TEST_CODE if "test" in spec.lower() else IMPL_WRONG)

    result = await local_pipeline.run_pipeline(
        "Write add(a, b).", workspace=tmp_path, max_repairs=10,
        runner=_fake_runner([(False, "AssertionError")] * 11))

    assert "stopped changing" in result.stop_reason
    assert len(result.attempts) < 10, "should give up early, not burn every attempt"
    assert result.needs_escalation


async def test_skipping_verification_is_reported_honestly(tmp_path, monkeypatch):
    """write_test=False returns unverified code and must not imply it was tested."""
    monkeypatch.setattr(local_pipeline, "generate_code", lambda *a, **k: "x = 1\n")

    result = await local_pipeline.run_pipeline(
        "anything", workspace=tmp_path, write_test=False)

    assert result.passed
    assert "without verification" in result.stop_reason
    assert not result.needs_escalation
