import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from synapse_daemon.worker_git_workspace import prepare_worker_worktree


class WorktreeTests(unittest.TestCase):
    def test_isolated_worktree_and_duplicate_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            repo.mkdir()
            def git(*args):
                return subprocess.run(["git", *args], cwd=repo, check=True,
                                      capture_output=True, text=True).stdout.strip()
            git("init", "-q")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.invalid")
            (repo / "a.py").write_text("original")
            git("add", "a.py")
            git("commit", "-qm", "initial")
            worker = root / "worker"
            receipt = prepare_worker_worktree(repo, worker, "feature/isolated-test")
            self.assertTrue(receipt["isolated"])
            (worker / "a.py").write_text("worker edit")
            self.assertEqual((repo / "a.py").read_text(), "original")
            with self.assertRaises(ValueError):
                prepare_worker_worktree(repo, root / "other", "feature/isolated-test")

    def test_rejects_nested_and_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            with self.assertRaises(ValueError):
                prepare_worker_worktree(repo, repo / "nested", "feature/test")
            with self.assertRaises(ValueError):
                prepare_worker_worktree(repo, repo.parent / "other", "main")
            with self.assertRaises(ValueError):
                prepare_worker_worktree(repo, repo.parent / "other", "feature/../main")


if __name__ == "__main__":
    unittest.main()
