"""Local publication checks must not depend on a remote or expose root paths."""
from contextlib import ExitStack
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze
from local_audit import collect_local_evidence
from project_context import local_facts


README = """# Local demo

Inspect an Electron application and verify a native video export.

## Quickstart
```bash
python3 inspect.py --help
```

## Example output
```json
{"verified": true}
```

## Contributing and feedback
Submit issues with evidence; contributions are welcome.
"""


class LocalAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="private-local-repo-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "README.md").write_text(README, encoding="utf-8")
        (self.root / "LICENSE").write_text("Local project license text\n", encoding="utf-8")

    def forbid_external_io(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        for target in ("socket.create_connection", "socket.socket.connect", "urllib.request.urlopen", "subprocess.Popen",
                       "analyze.get_token", "analyze.auth_context", "analyze.build_audit"):
            stack.enter_context(patch(target, side_effect=AssertionError("Offline path used external I/O: " + target)))

    def test_unpublished_directory_has_readme_but_unknown_remote_readiness(self):
        self.forbid_external_io()
        report = analyze.build_report("local:demo", "ignored-credential", "auto", 8, 15,
                                      local_path=str(self.root), offline=True)
        self.assertEqual(report["input_source"], "local-offline")
        self.assertEqual(report["readme"]["source"], {"kind": "local-file", "path": "README.md"})
        self.assertIsNotNone(report["module_scores"]["readme"])
        self.assertIsNone(report["module_scores"]["metadata"])
        self.assertIsNone(report["module_scores"]["topic_structure"])
        self.assertIsNone(report["overall"]["score"])
        self.assertEqual(report["overall"]["evaluated_weight"], 0.4)
        self.assertEqual(report["search_benchmark"], [])
        self.assertIsNone(report["traffic"])
        self.assertEqual(report["auth_context"]["mode"], "offline")
        self.assertFalse(report["auth_context"]["token_present"])
        self.assertEqual(report["promotion"]["drafts"], [])
        self.assertIn("未联网", analyze.render_markdown(report))

    def test_existing_origin_is_never_read_and_local_readme_wins(self):
        (self.root / ".git").mkdir()
        (self.root / ".git" / "config").write_text('[remote "origin"]\nurl = https://github.com/example/old.git\n')
        self.forbid_external_io()
        report = analyze.build_report("example/label-only", "", "api", 8, 15,
                                      local_path=str(self.root), offline=True)
        self.assertEqual(report["project_context"]["summary_source"], "README introduction")
        self.assertIn("native video export", report["suggestions"]["description"])
        self.assertNotIn("example/old", json.dumps(report))

    def test_file_inventory_preserves_locations_and_does_not_identify_license(self):
        folder = self.root / ".github"
        (folder / "ISSUE_TEMPLATE").mkdir(parents=True)
        (folder / "CONTRIBUTING.md").write_text("Send evidence with contributions.")
        (folder / "ISSUE_TEMPLATE" / "bug.yml").write_text("name: Bug\n")
        evidence = collect_local_evidence(str(self.root))
        self.assertEqual(evidence["files"]["license"]["status"], "present")
        self.assertEqual(evidence["files"]["contributing"]["path"], ".github/CONTRIBUTING.md")
        self.assertEqual(evidence["files"]["issue_template"]["path"], ".github/ISSUE_TEMPLATE/bug.yml")
        self.assertNotIn("license", evidence["audit"]["metadata"])
        self.assertEqual(evidence["files"]["security_policy"]["status"], "missing")

    def test_missing_readme_is_observed_absence_but_total_remains_unknown(self):
        (self.root / "README.md").unlink()
        report = analyze.build_report("local:demo", "", "auto", 8, 15, local_path=str(self.root), offline=True)
        self.assertEqual(report["readme"]["summary"]["score"], 0)
        self.assertIsNone(report["overall"]["score"])
        self.assertEqual(report["local_evidence"]["files"]["readme"]["status"], "missing")

    def test_external_readme_symlink_is_unknown_not_read(self):
        with tempfile.TemporaryDirectory() as outside:
            secret = Path(outside) / "personal.md"
            secret.write_text("Private text must stay outside the report.")
            (self.root / "README.md").unlink()
            (self.root / "README.md").symlink_to(secret)
            report = analyze.build_report("local:demo", "", "auto", 8, 15, local_path=str(self.root), offline=True)
        self.assertIsNone(report["module_scores"]["readme"])
        self.assertEqual(report["readme"]["status"], "unavailable")
        self.assertNotIn("Private text", json.dumps(report))
        self.assertNotIn(outside, json.dumps(report))

    def test_manifest_sources_and_reports_use_relative_paths(self):
        (self.root / "package.json").write_text(json.dumps({"scripts": {"inspect": "node inspect.mjs"}, "engines": {"node": ">=24"}}))
        (self.root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.10"\n')
        facts = local_facts(str(self.root))
        self.assertEqual({f["source"] for f in facts}, {"package.json", "pyproject.toml"})
        report = analyze.build_report("local:demo", "", "auto", 8, 15, local_path=str(self.root), offline=True)
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn(str(self.root), analyze.render_markdown(report))

    def test_external_manifest_symlinks_are_not_imported_as_project_facts(self):
        with tempfile.TemporaryDirectory() as outside:
            package = Path(outside) / "package.json"
            package.write_text(json.dumps({"scripts": {"private": "secret-personal-command"}}))
            (self.root / "package.json").symlink_to(package)
            facts = local_facts(str(self.root))
        self.assertEqual(facts[0]["kind"], "unavailable")
        self.assertNotIn("secret-personal-command", json.dumps(facts))
        self.assertNotIn(outside, json.dumps(facts))

    def test_cli_accepts_explicit_local_path_without_git_origin(self):
        self.forbid_external_io()
        output = io.StringIO()
        with patch.object(sys, "argv", ["analyze.py", "--offline", "--local-path", str(self.root), "--json"]), \
                patch("sys.stdout", output):
            analyze.main()
        report = json.loads(output.getvalue())
        self.assertEqual(report["repo"], "local:" + self.root.name)
        self.assertEqual(report["input_source"], "local-offline")

    def test_cli_accepts_positional_directory(self):
        self.forbid_external_io()
        output = io.StringIO()
        with patch.object(sys, "argv", ["analyze.py", str(self.root), "--offline", "--json"]), \
                patch("sys.stdout", output):
            analyze.main()
        self.assertEqual(json.loads(output.getvalue())["input_source"], "local-offline")

    def test_remote_only_options_are_rejected_offline_before_io(self):
        self.forbid_external_io()
        for option in ({"traffic_dir": "/unused"}, {"baseline": {"repo": "local:demo"}}):
            with self.subTest(option=option), self.assertRaises(ValueError):
                analyze.build_report("local:demo", "", "auto", 8, 15, local_path=str(self.root), offline=True, **option)


if __name__ == "__main__":
    unittest.main()
