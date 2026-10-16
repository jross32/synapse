import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from creative_tool_registry import inventory, REGISTRY

class CreativeRegistryTests(unittest.TestCase):
    def test_catalog_and_safe_detection(self):
        result = inventory(REGISTRY, resolver=lambda c: "/fake/" + c if c == "blender" else None)
        self.assertGreaterEqual(len(result["tools"]), 20)
        ids = {x["id"]: x for x in result["tools"]}
        self.assertTrue(ids["blender"]["detected_on_path"])
        self.assertFalse(ids["blender"]["usable"])
        self.assertFalse(ids["godot"]["detected_on_path"])
        self.assertIn("fmod-studio", ids)
        self.assertIn("ldtk", ids)

    def test_duplicate_ids_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "registry.json"
            file.write_text(json.dumps({"schema_version": 1, "tools": [
                {"id": "x", "category":"engine", "domains":[], "commands":[]},
                {"id": "x", "category":"audio", "domains":[], "commands":[]}
            ]}))
            with self.assertRaisesRegex(ValueError, "duplicate"):
                inventory(file)

if __name__ == "__main__":
    unittest.main()
