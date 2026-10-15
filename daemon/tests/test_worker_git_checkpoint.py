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
        self.assertIn("Tests not verified", checkpoint_after_verified_run(Path("."), completed=True, environ={"SYNAPSE_GIT_CHECKPOINT":"1"})["error"])
    def test_owned_paths_required(self):
        env={"SYNAPSE_GIT_CHECKPOINT":"1","SYNAPSE_TESTS_VERIFIED":"1"}
        self.assertIn("Owned paths",checkpoint_after_verified_run(Path("."),completed=True,environ=env)["error"])
    def test_invokes_verified_checkpoint(self):
        env={"SYNAPSE_GIT_CHECKPOINT":"1","SYNAPSE_TESTS_VERIFIED":"1","SYNAPSE_GIT_OWNED_PATHS":"src/a.py","SYNAPSE_GIT_CHECKPOINT_MESSAGE":"Test"}
        with patch("synapse_daemon.worker_git_checkpoint.subprocess.run") as run:
            run.return_value.returncode=0
            run.return_value.stdout='{"committed":true}'
            self.assertTrue(checkpoint_after_verified_run(Path("."),completed=True,environ=env)["committed"])
            self.assertIn("--commit",run.call_args.args[0])

if __name__ == "__main__":
    unittest.main()
