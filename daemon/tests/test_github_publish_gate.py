from pathlib import Path
from unittest.mock import patch

from synapse_daemon.github_publish_gate import check_github_publish

SHA = "a" * 40
BRANCH = "fix/example"


def fake_git(_repo, *args):
    if args[:3] == ("remote", "get-url", "origin"):
        return "https://github.com/jross32/synapse.git"
    if args[0] == "symbolic-ref":
        return BRANCH
    if args[0] == "rev-parse":
        return SHA
    if args[0] == "ls-remote":
        return f"{SHA}\trefs/heads/{BRANCH}"
    raise AssertionError(args)


def test_verified_remote_commit():
    with patch("synapse_daemon.github_publish_gate._git", side_effect=fake_git):
        assert check_github_publish(Path("."), expected_sha=SHA).ready


def test_changed_head_is_not_verified():
    with patch("synapse_daemon.github_publish_gate._git", side_effect=fake_git):
        assert check_github_publish(Path("."), expected_sha="b" * 40).reason == "head_changed"


def test_unpushed_commit_is_not_verified():
    def remote_behind(repo, *args):
        result = fake_git(repo, *args)
        return f"{'b' * 40}\trefs/heads/{BRANCH}" if args[0] == "ls-remote" else result
    with patch("synapse_daemon.github_publish_gate._git", side_effect=remote_behind):
        assert check_github_publish(Path(".")).reason == "not_pushed"


def test_unapproved_remote_fails_closed():
    def bad_remote(repo, *args):
        return "https://github.com/other/repo.git" if args[0] == "remote" else fake_git(repo, *args)
    with patch("synapse_daemon.github_publish_gate._git", side_effect=bad_remote):
        assert check_github_publish(Path(".")).reason == "unexpected_remote"


def test_code_work_requires_remote_evidence():
    from synapse_daemon.github_publish_gate import assess_code_work_completion
    assert assess_code_work_completion(Path("."), code_changed=True, tests_passed=True).status == "verified_not_published"
    assert assess_code_work_completion(Path("."), code_changed=True, tests_passed=False).status == "verification_failed"
    assert assess_code_work_completion(Path("."), code_changed=False, tests_passed=True).status == "complete"
    with patch("synapse_daemon.github_publish_gate._git", side_effect=fake_git):
        assert assess_code_work_completion(Path("."), code_changed=True, tests_passed=True, expected_sha=SHA).status == "complete"
