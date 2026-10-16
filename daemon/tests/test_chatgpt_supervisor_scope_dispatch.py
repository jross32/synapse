import pytest
from synapse_daemon.durable_scope_leases import DurableScopeLeases
from synapse_daemon.worker_scope_coordination import ScopeConflict
from synapse_daemon.agent_squads import AgentWorkItemLaunchRequest

def test_distinct_scopes_parallel_and_wildcard_exclusive(tmp_path):
    leases = DurableScopeLeases(tmp_path / "scope.sqlite")
    a = leases.acquire("repo", "a", ["daemon/a.py"])
    b = leases.acquire("repo", "b", ["daemon/b.py"])
    with pytest.raises(ScopeConflict):
        leases.acquire("repo", "c", ["daemon/a.py"])
    with pytest.raises(ScopeConflict):
        leases.acquire("repo", "global", ["*"])
    assert leases.release(a, "a")
    assert leases.release(b, "b")
    root = leases.acquire("repo", "global", ["*"])
    with pytest.raises(ScopeConflict):
        leases.acquire("repo", "other", ["daemon/new.py"])
    assert leases.release(root, "global")

def test_launch_explicit_edit_scopes_validate():
    launch = AgentWorkItemLaunchRequest(
        preferred_runtime="chatgpt_web",
        edit_scopes=["daemon/a.py", "daemon/b.py"],
        fresh_chat=True,
    )
    assert launch.edit_scopes == ["daemon/a.py", "daemon/b.py"]
