from pathlib import Path
import subprocess
from synapse_daemon.git_publish_guard import publication_readiness


def git(path, *args):
    subprocess.run(["git", "-C", str(path), *args], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def test_non_repo_fails_closed(tmp_path):
    result = publication_readiness(tmp_path, "jross32")
    assert not result["ready"]


def test_uncommitted_changes_block(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    (repo / "x.txt").write_text("first")
    git(repo, "add", "x.txt")
    git(repo, "commit", "-m", "initial")
    git(repo, "remote", "add", "origin", "https://github.com/jross32/verified.git")
    git(repo, "branch", "--set-upstream-to", "main") if False else None
    (repo / "x.txt").write_text("dirty")
    result = publication_readiness(repo, "jross32")
    assert not result["ready"]
    assert "Working tree has uncommitted changes" in result["blockers"]


def test_unrecognized_owner_blocks(tmp_path):
    assert not publication_readiness(tmp_path, "../someone")["ready"]
from pathlib import Path
from unittest.mock import patch
from synapse_daemon.git_publish_guard import publication_readiness


def _fake_git(root, *args):
    commands = {
        ('rev-parse', '--show-toplevel'): str(root),
        ('status', '--porcelain'): '',
        ('branch', '--show-current'): 'main',
        ('remote', 'get-url', 'origin'): 'git@github.com:jross32/sample.git',
        ('rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}'): 'origin/main',
        ('rev-list', '--left-right', '--count', 'HEAD...origin/main'): '2 1',
    }
    return commands[args]


def test_diverged_remote_and_unverified_quality_fail_closed(tmp_path):
    with patch('synapse_daemon.git_publish_guard._git', side_effect=_fake_git):
        result = publication_readiness(tmp_path, 'jross32')
    assert not result['ready']
    assert result['facts']['behind'] == 1
    assert 'Upstream has commits not present locally' in result['blockers']


def test_clean_git_still_requires_real_authorization_and_quality(tmp_path):
    def clean(root, *args):
        result = _fake_git(root, *args)
        return '1 0' if args[0] == 'rev-list' else result
    with patch('synapse_daemon.git_publish_guard._git', side_effect=clean):
        result = publication_readiness(tmp_path, 'jross32')
    assert not result['ready']
    assert any('authorization' in item.lower() for item in result['blockers'])


def test_wrong_github_owner_fails(tmp_path):
    def other(root, *args):
        return 'git@github.com:someone-else/sample.git' if args[0] == 'remote' else _fake_git(root, *args)
    with patch('synapse_daemon.git_publish_guard._git', side_effect=other):
        result = publication_readiness(tmp_path, 'jross32')
    assert not result['ready']
    assert any('expected GitHub account' in item for item in result['blockers'])
