from dataclasses import replace

from synapse_daemon.ai_edit_policy import EditAction, EditObservation, decide_edit


BASE = EditObservation(
    same_file=True,
    other_agent_active=False,
    other_agent_heartbeat_fresh=False,
    same_base_revision=True,
    local_dirty=False,
    remote_dirty=False,
    remote_available=True,
    compatible_schema=True,
)


def test_two_active_agents_use_isolated_worktrees():
    assert decide_edit(replace(BASE, other_agent_active=True, other_agent_heartbeat_fresh=True)).action == EditAction.ISOLATE


def test_stale_agent_does_not_implicitly_release_file():
    assert decide_edit(replace(BASE, other_agent_active=True)).action == EditAction.WAIT


def test_two_devices_dirty_requires_merge():
    assert decide_edit(replace(BASE, local_dirty=True, remote_dirty=True)).action == EditAction.MERGE


def test_divergent_base_requires_merge():
    assert decide_edit(replace(BASE, same_base_revision=False)).action == EditAction.MERGE


def test_offline_remote_changes_wait():
    assert decide_edit(replace(BASE, remote_available=False, remote_dirty=True)).action == EditAction.WAIT


def test_unknown_schema_is_rejected():
    assert decide_edit(replace(BASE, compatible_schema=False)).action == EditAction.REJECT


def test_unrelated_files_can_proceed():
    assert decide_edit(replace(BASE, same_file=False)).action == EditAction.PROCEED
