import subprocess

import pytest

from synapse_daemon.ai_worktree_merge import (
    MergeNeedsReview, create_agent_worktree, merge_agent_worktree,
)


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def repo(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Synapse Test")
    (root / "file.txt").write_text("initial\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "initial")
    return root


def test_isolated_agent_merge_does_not_change_main(tmp_path):
    root = repo(tmp_path)
    main_head = git(root, "rev-parse", "HEAD")
    agent = create_agent_worktree(root, tmp_path / "agent", "synapse-agent/test1")
    (agent.path / "file.txt").write_text("agent change\n", encoding="utf-8")
    git(agent.path, "add", ".")
    git(agent.path, "commit", "-m", "agent update")
    merged = merge_agent_worktree(root, agent, validation_commands=[["git", "status", "--porcelain"]])
    assert merged != main_head
    assert git(root, "rev-parse", "HEAD") == main_head
    assert (root / "file.txt").read_text(encoding="utf-8") == "initial\n"


def test_dirty_main_prevents_merge(tmp_path):
    root = repo(tmp_path)
    agent = create_agent_worktree(root, tmp_path / "agent", "synapse-agent/test2")
    (root / "file.txt").write_text("human edits\n", encoding="utf-8")
    with pytest.raises(MergeNeedsReview):
        merge_agent_worktree(root, agent, validation_commands=[])


def test_uncommitted_agent_work_rejected(tmp_path):
    root = repo(tmp_path)
    agent = create_agent_worktree(root, tmp_path / "agent", "synapse-agent/test3")
    (agent.path / "file.txt").write_text("unsaved agent\n", encoding="utf-8")
    with pytest.raises(MergeNeedsReview):
        merge_agent_worktree(root, agent, validation_commands=[])
