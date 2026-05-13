"""Contract #18 — restart policy."""

from __future__ import annotations

from synapse_daemon.restart_policy import RestartPolicy, next_backoff_seconds, should_restart


def test_default_is_never() -> None:
    p = RestartPolicy()
    assert p.mode == "never"
    assert p.max_retries == 3


def test_should_restart_never() -> None:
    p = RestartPolicy(mode="never")
    assert not should_restart(p, exit_code=1, attempts_so_far=0)


def test_should_restart_always_until_max_retries() -> None:
    p = RestartPolicy(mode="always", max_retries=3)
    assert should_restart(p, 0, 0)
    assert should_restart(p, 0, 2)
    assert not should_restart(p, 0, 3)


def test_should_restart_on_failure_only_on_nonzero_exit() -> None:
    p = RestartPolicy(mode="on-failure", max_retries=5)
    assert should_restart(p, 1, 0)
    assert not should_restart(p, 0, 0)


def test_backoff_grows_exponentially() -> None:
    p = RestartPolicy(initial_backoff_seconds=2, max_backoff_seconds=60)
    assert next_backoff_seconds(p, 0) == 2
    assert next_backoff_seconds(p, 1) == 2
    assert next_backoff_seconds(p, 2) == 4
    assert next_backoff_seconds(p, 3) == 8
    assert next_backoff_seconds(p, 4) == 16
    assert next_backoff_seconds(p, 5) == 32


def test_backoff_capped() -> None:
    p = RestartPolicy(initial_backoff_seconds=2, max_backoff_seconds=10)
    # Would be 32 unbounded; capped at 10.
    assert next_backoff_seconds(p, 5) == 10
    assert next_backoff_seconds(p, 99) == 10
