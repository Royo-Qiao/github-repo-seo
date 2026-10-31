import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from content_plan import build_content_plan, render_markdown


class ContentPlanTests(unittest.TestCase):
    def test_maps_real_document_evidence_and_marks_unknown_performance(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "README.md").write_text("# Electron export verification\n\nDecode the exported video completely.\n")
            report = build_content_plan(root, ["Electron export verification", "cloud login"])
            self.assertEqual(report["queries"][0]["evidence"][0]["path"], "README.md")
            self.assertEqual(report["queries"][1]["status"], "no-lexical-evidence")
            self.assertNotIn(folder, json.dumps(report))
            self.assertFalse(report["network_used"])
            self.assertEqual(report["surfaces"][1]["status"], "unobserved")

    def test_code_is_not_prose_and_symlinks_do_not_leak(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as secret:
            root = Path(folder)
            (root / "README.md").write_text("# Project\n```sh\nrecord screen studio\n```\n")
            (Path(secret) / "private-customer-merger.md").write_text("record screen studio")
            (root / "docs").symlink_to(secret)
            report = build_content_plan(root, ["record screen studio"])
            self.assertEqual(report["queries"][0]["status"], "no-lexical-evidence")
            self.assertNotIn(secret, json.dumps(report))
            self.assertNotIn("private-customer-merger", json.dumps(report))

    def test_query_validation_and_deduplication(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for values in (None, "export", [], [" "], [str(i) for i in range(9)], ["a" * 301], [1]):
                with self.assertRaises(ValueError):
                    build_content_plan(root, values)
            self.assertEqual(len(build_content_plan(root, ["export", " export "])["queries"]), 1)

    def test_long_fence_and_indented_code_are_not_answers(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "README.md").write_text("# Project\n````markdown\n```\nexport verification\n```\n````\n\n    export verification\n\texport verification\n")
            report = build_content_plan(root, ["export verification"])
            self.assertEqual(report["queries"][0]["status"], "no-lexical-evidence")

    def test_cjk_query_and_markdown_keep_evidence_relative(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "README.md").write_text("# 原生录制验证\n\n完整解码视频。", encoding="utf-8")
            report = build_content_plan(root, ["原生录制"])
            self.assertEqual(report["queries"][0]["evidence"][0]["line"], 1)
            self.assertIn("README.md:1", render_markdown(report))


if __name__ == "__main__":
    unittest.main()
