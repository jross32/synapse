import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
