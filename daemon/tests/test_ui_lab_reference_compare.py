"""Offline synthetic checks for the reference screenshot comparison gate."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from PIL import Image

SOURCE = Path(__file__).resolve().parents[2] / "tools" / "ui_lab_reference_compare.py"
SPEC = importlib.util.spec_from_file_location("ui_lab_reference_compare", SOURCE)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class ReferenceComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reference = self.root / "reference.png"
        self.actual = self.root / "actual.png"
        self.output = self.root / "proof"
        Image.new("RGB", (32, 32), "#202020").save(self.reference)

    def test_identical_screens_pass_and_write_evidence(self):
        Image.new("RGB", (32, 32), "#202020").save(self.actual)
        result = module.compare(self.reference, self.actual, self.output)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["bad_fraction"], 0)
        self.assertTrue((self.output / "difference.png").is_file())
        self.assertTrue((self.output / "report.json").is_file())

    def test_total_difference_fails(self):
        Image.new("RGB", (32, 32), "#ffffff").save(self.actual)
        result = module.compare(self.reference, self.actual, self.output)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["bad_fraction"], 1)
        self.assertGreater(result["mean_absolute_rgb_error"], 15)

    def test_mismatched_viewport_blocks(self):
        Image.new("RGB", (31, 32), "#202020").save(self.actual)
        result = module.compare(self.reference, self.actual, self.output)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse((self.output / "overlay.png").exists())

    def test_mask_ignores_dynamic_region(self):
        Image.new("RGB", (32, 32), "#ffffff").save(self.actual)
        mask = self.root / "mask.png"
        Image.new("L", (32, 32), 255).save(mask)
        with Image.open(mask) as mask_src:
            out = mask_src.copy()
        for x in range(4):
            for y in range(4):
                out.putpixel((x, y), 0)
        out.save(mask)
        with Image.open(self.actual) as src:
            actual = src.copy()
        for x in range(4):
            for y in range(4):
                actual.putpixel((x, y), (32, 32, 32))
        actual.save(self.actual)
        result = module.compare(self.reference, self.actual, self.output, ignore_mask=mask)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["compared_pixels"], 16)

    def test_total_mask_blocks(self):
        Image.new("RGB", (32, 32), "#ffffff").save(self.actual)
        mask = self.root / "mask.png"
        Image.new("L", (32, 32), 255).save(mask)
        result = module.compare(self.reference, self.actual, self.output, ignore_mask=mask)
        self.assertEqual(result["status"], "BLOCKED")

    def test_validation_rejects_bad_threshold(self):
        Image.new("RGB", (32, 32), "#202020").save(self.actual)
        with self.assertRaises(ValueError):
            module.compare(self.reference, self.actual, self.output, max_bad_fraction=1.1)


if __name__ == "__main__":
    unittest.main()
