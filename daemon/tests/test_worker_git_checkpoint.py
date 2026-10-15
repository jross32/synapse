import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from synapse_daemon.worker_git_checkpoint import checkpoint_after_verified_run

class WorkerCheckpointTests(unittest.TestCase):
    def test_disabled(self):
        self.assertEqual(checkpoint_after_verified_run(Path("."), completed=True, environ={})["skipped"], "not enabled")
    def test_failed_worker(self):
        self.assertEqual(checkpoint_after_verified_run(Path("."), completed=False, environ={"SYNAPSE_GIT_CHECKPOINT":"1"})["skipped"], "worker incomplete")
    def test_tests_required(self):
        self.assertIn("A real test command", checkpoint_after_verified_run(Path("."), completed=True, environ={"SYNAPSE_GIT_CHECKPOINT":"1"})["error"])
    def test_owned_paths_required(self):
        env={"SYNAPSE_GIT_CHECKPOINT":"1","SYNAPSE_GIT_TEST_COMMAND":"python -c pass"}
        self.assertIn("Owned paths",checkpoint_after_verified_run(Path("."),completed=True,environ=env)["error"])
    def test_invokes_verified_checkpoint(self):
        env={"SYNAPSE_GIT_CHECKPOINT":"1","SYNAPSE_GIT_TEST_COMMAND":"python -c pass","SYNAPSE_GIT_OWNED_PATHS":"src/a.py","SYNAPSE_GIT_CHECKPOINT_MESSAGE":"Test"}
        with patch("synapse_daemon.worker_git_checkpoint.subprocess.run") as run:
            from unittest.mock import Mock
            run.side_effect=[Mock(returncode=0,stdout=''),Mock(returncode=0,stdout='{"committed":true}')]
            self.assertTrue(checkpoint_after_verified_run(Path("."),completed=True,environ=env)["committed"])
            self.assertIn("--commit",run.call_args.args[0])

    def test_real_git_checkpoint_and_failed_verification(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            def run(*args):
                return subprocess.run(["git", *args], cwd=repo, capture_output=True,
                                      text=True, check=True).stdout.strip()
            run("init", "-q")
            run("config", "user.name", "Synapse Test")
            run("config", "user.email", "synapse-test@example.invalid")
            target = repo / "module.py"
            target.write_text("print('before')\\n")
            run("add", "module.py")
            run("commit", "-qm", "Initial")
            target.write_text("print('after')\\n")
            env = {"SYNAPSE_GIT_CHECKPOINT": "1",
                   "SYNAPSE_GIT_TEST_COMMAND": f"{sys.executable} -c pass",
                   "SYNAPSE_GIT_OWNED_PATHS": "module.py",
                   "SYNAPSE_GIT_CHECKPOINT_MESSAGE": "Verified worker milestone"}
            result = checkpoint_after_verified_run(repo, completed=True, environ=env)
            self.assertTrue(result, result)
            self.assertTrue(result.get("committed"), result)
            self.assertEqual(run("log", "-1", "--format=%s"), "Verified worker milestone")
            target.write_text("print('unverified')\\n")
            env["SYNAPSE_GIT_TEST_COMMAND"] = f"{sys.executable} -c exit(1)"
            failed = checkpoint_after_verified_run(repo, completed=True, environ=env)
            self.assertIn("failed", failed["error"])
            self.assertEqual(run("log", "-1", "--format=%s"), "Verified worker milestone")

if __name__ == "__main__":
    unittest.main()
