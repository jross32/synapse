import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from synapse_git_checkpoint import checkpoint

class CheckpointTests(unittest.TestCase):
    def test_requires_explicit_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("synapse_git_checkpoint.git", return_value=tmp):
                with self.assertRaises(ValueError):
                    checkpoint(Path(tmp), [])
    def test_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("synapse_git_checkpoint.git", side_effect=[tmp, "feature"]):
                with self.assertRaises(ValueError):
                    checkpoint(Path(tmp), ["../secret"])
    def test_preview_never_commits(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "file.txt").write_text("test")
            with patch("synapse_git_checkpoint.git", side_effect=[tmp, "feature", "", " M file.txt"]):
                result=checkpoint(Path(tmp), ["file.txt"])
                self.assertTrue(result["changed"])
                self.assertFalse(result["committed"])

if __name__=="__main__":
    unittest.main()
