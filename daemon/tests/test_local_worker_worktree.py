import asyncio
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from synapse_daemon import local_worker


class LocalWorkerWorktreeTests(unittest.TestCase):
    def test_worker_uses_isolated_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            repo.mkdir()
            def git(*args):
                subprocess.run(["git", *args], cwd=repo, check=True,
                               capture_output=True, text=True)
            git("init", "-q")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.invalid")
            (repo / "file.py").write_text("original")
            git("add", "file.py")
            git("commit", "-qm", "base")
            prompt = root / "prompt.txt"
            prompt.write_text("test")
            worker_dir = root / "worker"
            async def fake_agent(**kwargs):
                self.assertEqual(kwargs["workspace"], worker_dir)
                return SimpleNamespace(completed=True, answer="done",
                                       stop_reason="", steps=[])
            env = {"SYNAPSE_GIT_CHECKPOINT": "1",
                   "SYNAPSE_GIT_WORKTREE_PATH": str(worker_dir),
                   "SYNAPSE_GIT_PUSH_BRANCH": "feature/local-worker"}
            with patch.dict(os.environ, env), patch.object(sys, "argv",
                ["local_worker", "--prompt-file", str(prompt), "--workspace", str(repo)]), \
                patch.object(local_worker, "run_agent", side_effect=fake_agent), \
                patch.object(local_worker, "checkpoint_after_verified_run",
                             return_value={"committed": True}), \
                patch.object(local_worker, "handoff") as handoff:
                self.assertEqual(local_worker.main(), 0)
                self.assertEqual(handoff.call_args.args[0]["status"], "handoff")
            self.assertEqual((repo / "file.py").read_text(), "original")
            self.assertTrue((worker_dir / ".git").exists())


if __name__ == "__main__":
    unittest.main()
