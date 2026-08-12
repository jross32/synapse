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


async def test_a_repair_is_never_discarded_untested(tmp_path, monkeypatch):
    """Detecting a repeated error must not throw away the fix just written for it.

    From a real build: `passwords` shipped without `import hmac`, so `verify_password`
    raised `NameError` on every call. The loop saw the same fingerprint twice, wrote a
    repair that added the import - the correct fix - and then escalated without running it.
    The saving early-escalation exists for is the generation step, which by then has already
    been spent; one more test run is the difference between a pass and a false escalation.
    """
    IMPL_FIXED = "import hmac\n" + IMPL_RIGHT
    answers = iter([IMPL_WRONG, TEST_CODE, IMPL_RIGHT, IMPL_FIXED])
    monkeypatch.setattr(local_pipeline, "generate_code", lambda *a, **k: next(answers))

    same = "NameError: name 'hmac' is not defined"
    result = await local_pipeline.run_pipeline(
        "Write add(a, b) returning the sum.", workspace=tmp_path, max_repairs=5,
        # Same fingerprint twice -> the loop notices it is circling. The third run is the
        # repair it wrote in response, and that one passes.
        runner=_fake_runner([(False, same), (False, same), (True, "")]))

    assert result.passed, (
        f"the loop escalated while holding a repair that passes: {result.stop_reason}")
    assert "import hmac" in result.code
    assert not result.needs_escalation


async def test_still_escalates_when_the_extra_attempt_also_fails(tmp_path, monkeypatch):
    """The economy of giving up early has to survive the fix above."""
    answers = iter([IMPL_WRONG, TEST_CODE, IMPL_RIGHT, "def add(a, b):\n    return a * b\n"])
    monkeypatch.setattr(local_pipeline, "generate_code", lambda *a, **k: next(answers))

    same = "TypeError: unsupported operand"
    result = await local_pipeline.run_pipeline(
        "Write add(a, b) returning the sum.", workspace=tmp_path, max_repairs=9,
        runner=_fake_runner([(False, same), (False, same), (False, same)]))

    assert not result.passed
    assert "circling" in result.stop_reason, result.stop_reason
    assert len(result.attempts) == 2, (
        f"gave up early should still mean early: {len(result.attempts)} attempts")


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
    """An identical answer at every temperature means more attempts cannot help.

    "Identical" only counts once the sampler has been given a chance: at temperature 0 a
    repeated answer is what greedy decoding does, not a model out of ideas, so the loop
    resamples before concluding anything.
    """
    temperatures: list[float] = []

    def stub(spec, *a, **k):
        # Match the pipeline's actual marker, not the bare word "test": the *repair* prompt
        # says "Running the tests produced", so a substring check on "test" routes every
        # repair into the test-writing branch and the repair path is never exercised.
        if "Write a test for that code" in spec:
            return TEST_CODE
        temperatures.append(k.get("temperature", a[3] if len(a) > 3 else 0.0))
        return IMPL_WRONG

    monkeypatch.setattr(local_pipeline, "generate_code", stub)

    result = await local_pipeline.run_pipeline(
        "Write add(a, b).", workspace=tmp_path, max_repairs=10,
        runner=_fake_runner([(False, "AssertionError")] * 11))

    assert "identical code across 4 samples" in result.stop_reason
    # [initial draft, first repair, one call per resample, then the start-over rewrite] -
    # temperature 0 for the first two, which is the model's best guess, raised thereafter.
    assert temperatures[:2] == [0.0, 0.0], (
        f"the draft and the first repair should be the model's best guess: {temperatures}")
    assert temperatures[2:] == [*local_pipeline.RESAMPLE_TEMPERATURES,
                                local_pipeline.RESAMPLE_TEMPERATURES[-1]], (
        f"the sampler was never turned up before giving up: {temperatures}")
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
