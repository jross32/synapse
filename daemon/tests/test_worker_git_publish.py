import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from synapse_daemon.worker_git_publish import publish_verified_branch


class PublishTests(unittest.TestCase):
    def test_rejects_non_feature_branches(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                publish_verified_branch(Path(d), owner="jross32", branch="main")

    def test_rejects_local_remote(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            def git(*args):
                subprocess.run(["git", *args], cwd=root, check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            git("init", "-q")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.invalid")
            (root / "a.txt").write_text("test")
            git("add", "a.txt")
            git("commit", "-qm", "initial")
            git("checkout", "-qb", "feature/test")
            git("remote", "add", "origin", str(root))
            with self.assertRaisesRegex(ValueError, "Unapproved GitHub"):
                publish_verified_branch(root, owner="jross32", branch="feature/test")

    def test_rejects_dirty_worktree(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            def git(*args):
                subprocess.run(["git", *args], cwd=root, check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            git("init", "-q")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.invalid")
            (root / "a.txt").write_text("test")
            git("add", "a.txt")
            git("commit", "-qm", "initial")
            git("checkout", "-qb", "feature/test")
            (root / "a.txt").write_text("dirty")
            with self.assertRaisesRegex(ValueError, "not clean"):
                publish_verified_branch(root, owner="jross32", branch="feature/test")


    def test_real_push_to_isolated_bare_remote(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo = root / "work"
            bare = root / "remote.git"
            repo.mkdir()
            subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
            def git(*args):
                return subprocess.run(["git", *args], cwd=repo, check=True,
                                      capture_output=True, text=True).stdout.strip()
            git("init", "-q")
            git("config", "user.name", "Synapse Test")
            git("config", "user.email", "synapse-test@example.invalid")
            (repo / "module.py").write_text("print(1)\\n")
            git("add", "module.py")
            git("commit", "-qm", "initial")
            git("checkout", "-qb", "feature/checkpoint")
            git("remote", "add", "origin", "https://github.com/synapse-test-owner/checkpoint-test.git")
            # Git transport redirects only this test's URL to an isolated local bare repository.
            git("config", "url." + bare.as_uri() + ".insteadOf",
                "https://github.com/synapse-test-owner/checkpoint-test.git")
            from synapse_daemon import worker_git_publish as publishing
            original_git = publishing._git
            def isolated_git(root, *args, **kwargs):
                if args == ("remote", "get-url", "origin"):
                    return subprocess.CompletedProcess([], 0, stdout="https://github.com/synapse-test-owner/checkpoint-test.git\\n")
                return original_git(root, *args, **kwargs)
            with patch.object(publishing, "_git", side_effect=isolated_git):
                receipt = publish_verified_branch(repo, owner="synapse-test-owner",
                                                  branch="feature/checkpoint")
            self.assertTrue(receipt["pushed"])
            remote_head = subprocess.run(
                ["git", "--git-dir", str(bare), "rev-parse", "refs/heads/feature/checkpoint"],
                capture_output=True, text=True, check=True).stdout.strip()
            self.assertEqual(remote_head, git("rev-parse", "HEAD"))
            (repo / "module.py").write_text("print(2)\\n")
            git("add", "module.py")
            git("commit", "-qm", "second")
            with patch.object(publishing, "_git", side_effect=isolated_git):
                receipt = publish_verified_branch(repo, owner="synapse-test-owner",
                                                  branch="feature/checkpoint")
            self.assertTrue(receipt["pushed"])

if __name__ == "__main__":
    unittest.main()
