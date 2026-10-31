"""Offline checks for evidence-backed awesome-list submission candidates."""
import base64
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import awesome_match
from github_api import GitHubAPIError


LIST = {
    "full_name": "maintainer/awesome-seo", "name": "awesome-seo",
    "description": "SEO resources", "html_url": "https://github.com/maintainer/awesome-seo",
    "stargazers_count": 700, "pushed_at": datetime.now(timezone.utc).isoformat(),
    "default_branch": "main",
}
README_URL = "https://github.com/maintainer/awesome-seo/blob/main/README.md"
RULES_URL = "https://github.com/maintainer/awesome-seo/blob/main/.github/CONTRIBUTING.md"
README = "# Awesome SEO\n\n## GitHub SEO\n\n- [Another](https://github.com/other/project)\n"
RULES = "# Contributing\n\n- Please add entries in alphabetical order.\n- Each entry must include a short description.\n"
DESCRIPTION = "Audit GitHub repositories using deterministic checks."


def content(text, url):
    return {"encoding": "base64", "content": base64.b64encode(text.encode()).decode(), "html_url": url}


class AwesomeTests(unittest.TestCase):
    def run_report(self, readme=README, rules=RULES, profile=None, items=None, **kwargs):
        profile = profile if profile is not None else {"files": {
            "readme": {"path": "README.md", "html_url": README_URL},
            "contributing": {"path": ".github/CONTRIBUTING.md", "html_url": RULES_URL},
        }}
        calls = []

        def fake_fetch(endpoint, **options):
            calls.append(endpoint)
            if endpoint == "/search/repositories":
                return {"items": items if items is not None else [LIST]}
            if endpoint.endswith("/community/profile"):
                if isinstance(profile, Exception):
                    raise profile
                return profile
            if endpoint.endswith(("/contents/README.md", "/readme")):
                if isinstance(readme, Exception):
                    raise readme
                return content(readme, README_URL)
            if endpoint.endswith("/contents/.github/CONTRIBUTING.md"):
                if isinstance(rules, Exception):
                    raise rules
                return content(rules, RULES_URL)
            raise AssertionError(endpoint)

        with patch.object(awesome_match, "fetch_json", side_effect=fake_fetch), patch("time.sleep"):
            report = awesome_match.find_awesome_lists("owner/project", ["seo"], "Python", "project",
                                                     DESCRIPTION, terms=["seo"], **kwargs)
        return report, calls

    def test_candidate_has_source_section_rules_and_truthful_draft(self):
        report, calls = self.run_report()
        entry = report["lists"][0]
        self.assertEqual(report["status"], "ok")
        self.assertIsNone(report["score"])
        self.assertEqual(entry["status"], "candidate")
        self.assertFalse(entry["already_listed"])
        self.assertEqual(entry["eligibility"]["section"]["heading"], "GitHub SEO")
        self.assertEqual(entry["eligibility"]["section"]["line"], 3)
        self.assertEqual(entry["eligibility"]["section"]["url"], README_URL + "#L3")
        self.assertEqual(entry["eligibility"]["evidence"][0]["text"], RULES.splitlines()[2])
        self.assertEqual(entry["rules_url"], RULES_URL)
        self.assertEqual(entry["submission"]["title"], "Add project")
        self.assertEqual(entry["submission"]["entry"],
                         "- [project](https://github.com/owner/project) — " + DESCRIPTION)
        self.assertNotIn("best", entry["submission"]["body"].lower())
        self.assertEqual(calls.count("/repos/maintainer/awesome-seo/community/profile"), 1)

    def test_existing_entry_matches_exact_url_case_insensitively(self):
        report, _ = self.run_report(readme=README + "- [Project](https://github.com/OWNER/Project.git/)\n")
        entry = report["lists"][0]
        self.assertTrue(entry["already_listed"])
        self.assertEqual(entry["status"], "already-listed")
        self.assertIn("OWNER/Project", entry["listing_evidence"]["text"])

    def test_name_and_url_prefix_do_not_mean_already_listed(self):
        report, _ = self.run_report(readme=README +
                                    "Project is interesting. [Different](https://github.com/owner/project-plus)\n"
                                    "[Different owner](https://github.com/other/project)\n")
        self.assertFalse(report["lists"][0]["already_listed"])

    def test_readme_403_is_unknown_instead_of_missing_or_unlisted(self):
        report, _ = self.run_report(readme=GitHubAPIError("Forbidden", status=403))
        entry = report["lists"][0]
        self.assertEqual(report["status"], "partial")
        self.assertIsNone(entry["already_listed"])
        self.assertEqual(entry["status"], "review-required")
        self.assertEqual(report["coverage"]["readmes_read"], 0)
        self.assertTrue(any("listing status unknown" in text for text in report["limitations"]))

    def test_rules_403_keeps_rules_unknown(self):
        report, _ = self.run_report(rules=GitHubAPIError("Forbidden", status=403))
        entry = report["lists"][0]
        self.assertEqual(entry["eligibility"]["status"], "unknown")
        self.assertEqual(entry["eligibility"]["evidence"], [])
        self.assertEqual(entry["status"], "review-required")
        self.assertFalse(entry["already_listed"])
        self.assertEqual(report["status"], "partial")

    def test_title_match_without_real_matching_section_requires_review(self):
        report, _ = self.run_report(readme="# Awesome SEO\n\n## Miscellaneous\n\nUseful projects.\n")
        entry = report["lists"][0]
        self.assertIsNone(entry["eligibility"]["section"])
        self.assertEqual(entry["status"], "review-required")
        self.assertNotIn("Suggested section", entry["submission"]["body"])

    def test_readme_contributing_section_can_supply_real_rules(self):
        readme = README + "\n## Contributing\n\nPlease add a short description for each entry.\n"
        report, _ = self.run_report(readme=readme, profile={"files": {"readme": {"path": "README.md"}}})
        entry = report["lists"][0]
        self.assertEqual(entry["rules_url"], README_URL)
        self.assertEqual(entry["status"], "candidate")
        self.assertEqual(entry["eligibility"]["evidence"][0]["line"], 9)

    def test_profile_failure_does_not_skip_readme_or_claim_rules_absent(self):
        report, calls = self.run_report(profile=GitHubAPIError("Forbidden", status=403))
        entry = report["lists"][0]
        self.assertIn("/repos/maintainer/awesome-seo/readme", calls)
        self.assertFalse(entry["already_listed"])
        self.assertEqual(entry["eligibility"]["status"], "unknown")
        self.assertEqual(report["status"], "partial")

    def test_non_latin_heading_and_rules_preserve_original_text(self):
        section = awesome_match._section_for("# 清单\n\n## 搜索工具 Search\n", ["搜索"], README_URL)
        self.assertEqual(section["heading"], "搜索工具 Search")
        evidence = awesome_match._rule_evidence("# 贡献\n\n请按字母顺序添加条目。\n", RULES_URL)
        self.assertEqual(evidence[0]["text"], "请按字母顺序添加条目。")

    def test_search_failures_make_module_unavailable(self):
        with patch.object(awesome_match, "fetch_json", side_effect=GitHubAPIError("Forbidden", status=403)), patch("time.sleep"):
            report = awesome_match.find_awesome_lists("owner/project", [], "", "", "", terms=["seo"])
        self.assertEqual(report["status"], "unavailable")
        self.assertEqual(report["coverage"]["queries_succeeded"], 0)
        self.assertEqual(report["lists"], [])
        self.assertIsNone(report["score"])

    def test_reads_are_capped_at_five_deduplicated_candidates(self):
        items = [{**LIST, "full_name": f"maintainer/awesome-seo-{n}", "name": f"awesome-seo-{n}"}
                 for n in range(7)]
        report, calls = self.run_report(items=items)
        self.assertEqual(report["total_matches"], 7)
        self.assertEqual(len(report["lists"]), awesome_match.MAX_LISTS)
        self.assertEqual(sum(path.endswith("/community/profile") for path in calls), 5)
        self.assertEqual(report["coverage"]["readmes_read"], 5)

    def test_invalid_or_truncated_content_is_not_a_negative_observation(self):
        for data in ({"encoding": "base64", "content": "not-base64!"},
                     {"encoding": "none", "content": ""},
                     {"encoding": "base64", "content": "", "truncated": True}):
            with self.assertRaises(ValueError):
                awesome_match._content_text(data)


if __name__ == "__main__":
    unittest.main()
