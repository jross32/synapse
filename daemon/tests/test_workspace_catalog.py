from pathlib import Path
import pytest
from synapse_daemon.workspace_catalog import WorkspaceCatalog


def test_account_scoped_locations(tmp_path: Path):
    store = WorkspaceCatalog(tmp_path / 'workspace.db')
    store.register('alice', 'rewardz', 'laptop', 'C:/rewardz', 'a1')
    store.register('alice', 'rewardz', 'desktop', 'D:/rewardz', 'b2')
    assert len(store.locations('alice', 'rewardz')) == 2
    assert store.locations('bob', 'rewardz') == []
    store.register('alice', 'rewardz', 'laptop', 'C:/new', 'a2')
    assert len(store.locations('alice', 'rewardz')) == 2


def test_note_version_and_conflicts(tmp_path: Path):
    store = WorkspaceCatalog(tmp_path / 'workspace.db')
    assert store.set_note('alice', 'rewardz', 'plan', 'one', 0) == 1
    assert store.set_note('alice', 'rewardz', 'plan', 'two', 1) == 2
    assert store.get_note('alice', 'rewardz', 'plan')['content'] == 'two'
    with pytest.raises(ValueError, match='conflict'):
        store.set_note('alice', 'rewardz', 'plan', 'overwritten', 1)
    assert store.get_note('alice', 'rewardz', 'plan')['content'] == 'two'
    assert store.get_note('bob', 'rewardz', 'plan') is None
