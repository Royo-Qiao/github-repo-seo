"""Offline integration checks for truthful reports and project-aware lint."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze
import repo_audit
from github_api import GitHubAPIError
from readme_lint import score_report, fetch_readme_from_repo, extract_images, extract_headings, strip_code_fences
from project_context import collect_context, load_context, readme_summary
import tempfile
import json

README = """# Sample

为开发者将 CSV 文件转换为 JSON，支持本地使用。

## 快速开始
```bash
python convert.py data.csv
```

## 示例输出
```json
{"name": "sample"}
```

## 反馈与贡献
通过 Issues 提交反馈，欢迎贡献。
"""


class RecommendationTests(unittest.TestCase):
    def test_profile_null_does_not_prove_directory_issue_templates_are_missing(self):
        meta = {"name": "repo", "description": "Read-only native recording validation for developers.",
                "topics": ["macos"], "license": {"spdx_id": "MIT"}}
        community = {"files": {"code_of_conduct": {}, "contributing": {}, "issue_template": None}}
        with patch.object(repo_audit, "fetch_json", side_effect=[meta, community]):
            report = repo_audit.build_audit("owner/repo", token="fixture")
        self.assertFalse(any(f["finding"] == "Missing community file: issue_template." for f in report["findings"]))
        self.assertTrue(any("directory-based" in text for text in report["limitations"]))

    def test_unobserved_and_crowded_topics_are_preserved(self):
        topics = ["cloudflare", "cloudflare-pages"] + [f"capability-{n}" for n in range(10)]
        report = {"per_topic": [{"topic": "cloudflare", "verdict": "crowded-swap"}],
                  "candidate_topics": {"candidates": [{"topic": "ai", "comparable_count": 3}]}}
        recommended, notes = analyze.suggest_topics(topics, report)
        self.assertEqual(recommended, topics)
        self.assertNotIn("ai", recommended)
        self.assertTrue(notes)

    def test_drafts_have_actual_content_without_invented_commands(self):
        meta = {"name": "Sample", "full_name": "owner/sample", "description": "Convert CSV files to JSON."}
        description = analyze.suggest_description(meta, ["csv", "json"])
        opening = analyze.readme_opening_draft(meta, ["csv", "json"])
        self.assertIn("Convert CSV", description)
        self.assertIn("Convert CSV", opening)
        self.assertNotIn("[", description)
        self.assertNotIn("demo.gif", opening)
        self.assertNotIn("pip install", opening)


class ReadmeTests(unittest.TestCase):
    def test_labeled_expected_output_does_not_require_a_dedicated_heading(self):
        text = "# Tool\n\nChecks a local video.\n\n## Quickstart\n```sh\npython verify.py demo.mp4\n```\n\nExample fields from an export result:\n\n```json\n{\"ok\": true}\n```\n"
        report = score_report(text, project_type="cli")
        self.assertEqual(report["category_scores"]["proof_visuals"], 15)
        self.assertFalse(any(f["severity"] == "Warning" and f["category"] == "Proof & Visuals"
                             for f in report["findings"]))

    def test_ui_images_do_not_imply_missing_animation(self):
        for extension in ("webp", "png"):
            markdown = f"# Wizard\n\nA local web interface.\n\n## Demo\n![Demo](https://example.com/demo.{extension})\n\n## Quickstart\n```bash\nnpm start\n```\n"
            with self.subTest(extension=extension):
                report = score_report(markdown, project_type="ui")
                self.assertEqual(report["category_scores"]["proof_visuals"], 15)
                self.assertFalse(any("Static screenshots" in row["finding"] or "no demo GIF" in row["finding"] for row in report["findings"]))

    def test_indented_comments_are_not_headings_and_lines_are_preserved(self):
        text = "# Title\n\n    # shell comment\n\n```bash\n# another comment\n```\n\n### Jump\n"
        headings = extract_headings(strip_code_fences(text))
        self.assertEqual([(h["text"], h["line"]) for h in headings], [("Title", 1), ("Jump", 9)])

    def test_incomplete_readme_payload_is_unknown(self):
        for payload in ({}, {"encoding": "none", "content": ""},
                        {"encoding": "base64", "truncated": True, "content": ""},
                        {"encoding": "base64", "content": "!not-base64!"}):
            with self.subTest(payload=payload), patch("readme_lint.fetch_json", return_value=payload):
                with self.assertRaises(GitHubAPIError):
                    fetch_readme_from_repo("owner/repo")

    def test_valid_empty_content_is_observed_empty(self):
        with patch("readme_lint.fetch_json", return_value={"encoding": "base64", "content": ""}):
            self.assertEqual(fetch_readme_from_repo("owner/repo"), "")

    def test_reference_and_html_images(self):
        images = extract_images("![Demo][shot]\n\n[shot]: docs/screen.png\n<img src='other.png' alt='Result'>")
        self.assertEqual({image["url"] for image in images}, {"docs/screen.png", "other.png"})

    def test_example_elsewhere_does_not_satisfy_quickstart(self):
        report = score_report("# Sample\n\nConverts files.\n\n## Quickstart\nComing soon.\n\n## Output\n```json\n{}\n```\n", project_type="cli")
        self.assertTrue(any("getting-started" in finding["finding"] for finding in report["findings"]))

    def test_cli_can_prove_utility_without_images_or_badges(self):
        report = score_report(README, project_type="cli")
        findings = report["findings"]
        self.assertFalse(any(f["category"] in ("Badges", "Proof & Visuals") and f["severity"] != "Info"
                             for f in findings))
        self.assertFalse(any("sparse" in f["finding"].lower() for f in findings))

    def test_list_does_not_require_installation(self):
        report = score_report("# Curated tools\n\nA curated collection.\n\n## Tools\n- [Tool](https://example.com)\n",
                              project_type="list")
        self.assertFalse(any(f["category"] == "Install + Quickstart" for f in report["findings"]))

    def test_heading_only_is_not_an_executable_quickstart(self):
        report = score_report("# Sample\n\nConverts files.\n\n## Quickstart\nComing soon.\n", project_type="cli")
        self.assertTrue(any(f["category"] == "Install + Quickstart" for f in report["findings"]))
        self.assertFalse(report["metrics"]["commands_executed"])


class MetadataTests(unittest.TestCase):
    def test_concise_functional_descriptions_are_not_penalized_by_length(self):
        for description in ("将 CSV 文件转换为 JSON 的 Python 命令行工具。", "Convert CSV files to JSON."):
            data = {"name": "csv-json", "description": description,
                    "topics": ["csv", "json", "csv-parser", "file-conversion", "command-line"],
                    "license": {"spdx_id": "MIT"}}
            community = {"files": {key: {"path": key} for key in ("code_of_conduct", "contributing", "issue_template")}}
            with self.subTest(description=description), patch.object(repo_audit, "fetch_json", side_effect=[data, community]):
                result = repo_audit.build_audit("owner/csv-json", token="offline-test")
            self.assertEqual(result["summary"]["score"], 100)
            self.assertFalse(any("search indexing" in row["finding"] for row in result["findings"]))

    def test_empty_metadata_payload_is_unknown(self):
        with patch.object(repo_audit, "fetch_json", return_value={}):
            result = repo_audit.build_audit("owner/repo", token="offline-test")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["findings"], [])
        self.assertIsNone(result["summary"]["score"])

    def test_missing_topics_field_does_not_confirm_no_topics(self):
        data = {"name": "repo", "description": "Real description", "license": {"spdx_id": "MIT"}}
        with patch.object(repo_audit, "fetch_json", side_effect=[data, {"files": {}}]):
            result = repo_audit.build_audit("owner/repo", token="offline-test")
        self.assertEqual(result["coverage"]["topics"], "unavailable")
        self.assertIsNone(result["summary"]["score"])
        self.assertFalse(any("No topics" in finding["finding"] for finding in result["findings"]))

    def test_fetch_failure_is_not_a_repo_defect(self):
        with patch.object(repo_audit, "fetch_json", side_effect=GitHubAPIError("Unauthorized", status=401)):
            result = repo_audit.build_audit("owner/repo", token="offline-test")
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["summary"]["score"])
        self.assertEqual(result["findings"], [])

    def test_community_failure_keeps_metadata_without_false_missing_files(self):
        data = {"name": "repo", "description": "Convert CSV files into JSON documents for developers.",
                "topics": ["csv", "json"], "license": {"spdx_id": "MIT"}}
        with patch.object(repo_audit, "fetch_json", side_effect=[data, GitHubAPIError("Forbidden", status=403)]):
            result = repo_audit.build_audit("owner/repo", token="offline-test")
        self.assertEqual(result["status"], "partial")
        self.assertIsNone(result["summary"]["score"])
        self.assertFalse(any("Missing community" in f["finding"] for f in result["findings"]))
        self.assertFalse(any("social preview" in f["finding"].lower() for f in result["findings"]))


class ReportTests(unittest.TestCase):
    def test_no_token_keeps_basic_audit_and_skips_search(self):
        with patch.object(analyze, "build_audit", return_value=self._audit()), \
             patch.object(analyze, "fetch_readme_from_repo", return_value=README), \
             patch.object(analyze, "analyze_topics") as topics, \
             patch.object(analyze, "find_awesome_lists") as awesome, \
             patch.object(analyze, "benchmark_queries") as benchmark:
            result = analyze.build_report("owner/sample", "", "api", 8, 15)
        topics.assert_not_called()
        awesome.assert_not_called()
        benchmark.assert_not_called()
        self.assertIsNotNone(result["overall"]["score"])
        self.assertEqual(result["suggestions"]["topics"], ["csv", "json"])
        self.assertEqual(result["topics"]["status"], "unavailable")
        self.assertIsNone(result["traffic"])

    def test_invalid_inputs_are_rejected_before_network(self):
        with patch.object(analyze, "build_audit") as api:
            for options in ({"queries": [str(i) for i in range(9)]},
                            {"baseline": {"schema_version": 2, "repo": "other/repo"}},
                            {"baseline": {"schema_version": 2, "repo": "owner/repo", "search_benchmark": None}}):
                with self.assertRaises(ValueError):
                    analyze.build_report("owner/repo", "offline-test", "auto", 8, 15, **options)
            api.assert_not_called()

    def _audit(self):
        return {"status": "ok", "coverage": {"metadata": "ok", "community": "ok"},
                "summary": {"score": 80}, "findings": [], "limitations": [],
                "metadata": {"name": "Sample", "full_name": "owner/sample", "description": "Convert CSV files to JSON.",
                             "topics": ["csv", "json"], "stargazers_count": 0, "default_branch": "main"},
                "name_tokens": ["sample"], "description_tokens": ["convert", "csv", "json"]}

    def _topics(self):
        return {"status": "ok", "structure_score": 75, "structure_notes": [], "quality_score": 75,
                "ranking_score": 20, "per_topic": [], "candidate_topics": {"candidates": []},
                "limitations": [], "our_stars": 0}

    def test_readme_failure_has_no_numeric_readiness(self):
        with patch.object(analyze, "build_audit", return_value=self._audit()), \
             patch.object(analyze, "fetch_readme_from_repo", side_effect=GitHubAPIError("Forbidden", status=403)), \
             patch.object(analyze, "analyze_topics", return_value=self._topics()), \
             patch.object(analyze, "benchmark_queries", return_value=[]), \
             patch.object(analyze, "find_awesome_lists", return_value={"status": "unavailable", "lists": [],
                                                                         "limitations": ["Search unavailable"]}):
            result = analyze.build_report("owner/sample", "offline-test", "auto", 8, 15)
        self.assertIsNone(result["overall"]["score"])
        self.assertIsNone(result["module_scores"]["readme"])
        self.assertIn("Search unavailable", result["limitations"])
        self.assertIn("未完整评估", analyze.render_markdown(result))

    def test_opportunities_and_rankings_do_not_change_readiness(self):
        with patch.object(analyze, "build_audit", return_value=self._audit()), \
             patch.object(analyze, "fetch_readme_from_repo", return_value=README), \
             patch.object(analyze, "analyze_topics", return_value=self._topics()), \
             patch.object(analyze, "benchmark_queries", return_value=[]), \
             patch.object(analyze, "find_awesome_lists", return_value={"status": "ok", "lists": [], "score": 90}):
            first = analyze.build_report("owner/sample", "offline-test", "auto", 8, 15)
        topics = self._topics()
        topics["ranking_score"] = 100
        with patch.object(analyze, "build_audit", return_value=self._audit()), \
             patch.object(analyze, "fetch_readme_from_repo", return_value=README), \
             patch.object(analyze, "analyze_topics", return_value=topics), \
             patch.object(analyze, "benchmark_queries", return_value=[]), \
             patch.object(analyze, "find_awesome_lists", return_value={"status": "ok", "lists": [], "score": 20}):
            second = analyze.build_report("owner/sample", "offline-test", "auto", 8, 15)
        self.assertEqual(first["overall"]["score"], second["overall"]["score"])
        text = analyze.render_markdown(first)
        self.assertNotIn("预估排名分", text)
        self.assertNotIn("预计总分", text)


class ContextTests(unittest.TestCase):
    def test_reference_badge_definitions_are_not_the_summary(self):
        text = "# Project\n\n[![build][ci]][job]\n[ci]: https://example.com/badge.svg\n[job]: https://example.com\n\nConverts CSV to JSON.\n"
        self.assertEqual(readme_summary(text), "Converts CSV to JSON.")

    def test_user_context_is_labelled_and_local_commands_are_not_run(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "package.json"
            package.write_text(json.dumps({"scripts": {"start": "node app.js"}, "engines": {"node": ">=20"}}))
            result = collect_context({"description": "Observed summary"}, README,
                                     {"summary": "User summary", "audience": "Developers"}, directory)
        self.assertEqual(result["summary_source"], "user-context")
        self.assertEqual(result["facts"][0]["text"], "npm run start")
        self.assertFalse(result["facts"][0]["executed"])

    def test_context_rejects_wrong_field_types(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.json"
            path.write_text('{"queries": "not a list"}')
            with self.assertRaises(ValueError):
                load_context(str(path))


if __name__ == "__main__":
    unittest.main()
