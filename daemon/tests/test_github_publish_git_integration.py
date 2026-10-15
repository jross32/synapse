"""Real Git subprocess integration, using an isolated local bare origin."""
import subprocess
from pathlib import Path
from unittest.mock import patch

from synapse_daemon import github_publish_gate as gate


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()


def test_real_git_commit_and_remote_push_gate(tmp_path):
    origin = tmp_path / "origin.git"
    repo = tmp_path / "work"
    origin.mkdir()
    repo.mkdir()
    git(origin, "init", "--bare")
    git(repo, "init")
    git(repo, "config", "user.name", "Synapse Test")
    git(repo, "config", "user.email", "synapse-test@example.invalid")
    git(repo, "checkout", "-b", "feature/verified")
    (repo / "code.py").write_text("print('verified')\n")
    git(repo, "add", "code.py")
    git(repo, "commit", "-m", "verified change")
    git(repo, "remote", "add", "origin", str(origin))
    sha = git(repo, "rev-parse", "HEAD")
    real_git = gate._git

    def approved_origin_only(path, *args):
        if args == ("remote", "get-url", "origin"):
            return "https://github.com/jross32/synapse.git"
        return real_git(path, *args)

    with patch.object(gate, "_git", side_effect=approved_origin_only):
        assert gate.check_github_publish(repo, expected_sha=sha).reason == "remote_branch_missing"
        git(repo, "push", "origin", "HEAD:refs/heads/feature/verified")
        assert gate.check_github_publish(repo, expected_sha=sha).ready
        (repo / "code.py").write_text("print('new')\n")
        git(repo, "add", "code.py")
        git(repo, "commit", "-m", "not published")
        assert gate.check_github_publish(repo).reason == "not_pushed"
