"""Offline regression tests for repository identifiers and topic evidence."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import github_api
import topic_competition as topics


class RepositoryIdentifierTests(unittest.TestCase):
    def test_local_directory_uses_origin_before_slug_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(github_api, "infer_repo_from_git", return_value="owner/repo") as origin:
                self.assertEqual(github_api.resolve_repo(directory), "owner/repo")
                origin.assert_called_once_with(cwd=directory)

    def test_accepts_repository_identifiers(self):
        for value in ("owner/repo", "https://github.com/owner/repo/",
                      "https://github.com/owner/repo.git", "git@github.com:owner/repo.git",
                      "ssh://git@github.com/owner/repo.git"):
            with self.subTest(value=value):
                self.assertEqual(github_api.normalize_repo_slug(value), "owner/repo")

    def test_rejects_other_hosts_and_extra_paths(self):
        for value in ("https://example.com/owner/repo", "https://github.com.evil.test/owner/repo",
                      "https://github.com/owner/repo/tree/main", "owner/repo/extra",
                      "/nonexistent/github-repo-seo-fixture", "git@gitlab.com:owner/repo.git"):
            with self.subTest(value=value):
                self.assertEqual(github_api.normalize_repo_slug(value), "")
                with patch.object(github_api, "infer_repo_from_git", return_value="other/repo"):
                    with self.assertRaises(github_api.GitHubAPIError):
                        github_api.resolve_repo(value)


class ApiRetryTests(unittest.TestCase):
    def setUp(self):
        github_api._COOLDOWNS.clear()
        github_api._LAST_SEARCH = None

    def test_status_code_alias_preserves_status(self):
        error = github_api.GitHubAPIError("not found", status=404)
        self.assertEqual(error.status_code, 404)
        self.assertEqual(error.status, 404)

    def test_secondary_limit_obeys_retry_after(self):
        failure = (403, {"Retry-After": "7", "X-RateLimit-Remaining": "4980"},
                   json.dumps({"message": "You have exceeded a secondary rate limit."}))
        with patch.object(github_api, "_http", side_effect=[failure, (200, {}, "{}")]) as http:
            with patch.object(github_api.time, "sleep") as sleep:
                self.assertEqual(github_api.fetch_json("/test", provider="api"), {})
                sleep.assert_called_once_with(7)
                self.assertEqual(http.call_count, 2)

    def test_retry_is_bounded(self):
        failure = (429, {"Retry-After": "1"}, '{"message":"rate limited"}')
        with patch.object(github_api, "_http", return_value=failure) as http:
            with patch.object(github_api.time, "sleep"):
                with self.assertRaises(github_api.GitHubAPIError) as raised:
                    github_api.fetch_json("/test", provider="api", retries=2)
                self.assertEqual(http.call_count, 3)
                self.assertEqual(raised.exception.status_code, 429)

    def test_long_retry_after_fails_without_retrying_early(self):
        failure = (429, {"Retry-After": "120"}, '{"message":"rate limited"}')
        with patch.object(github_api, "_http", return_value=failure) as http:
            with patch.object(github_api.time, "sleep") as sleep:
                with self.assertRaises(github_api.GitHubAPIError):
                    github_api.fetch_json("/test", provider="api")
                sleep.assert_not_called()
                self.assertEqual(http.call_count, 1)


class TopicStructureTests(unittest.TestCase):
    def test_invalid_topic_syntax_is_explained(self):
        for invalid in ("Uppercase", "with space", "underscore_tag", "x" * 51, ""):
            with self.subTest(topic=invalid):
                score, notes = topics.quality_score(["proxy", "vless", "cloudflare", "tunnel", invalid])
                self.assertLess(score, 100)
                self.assertTrue(any("syntax" in note.lower() for note in notes))

    def test_topic_cap_is_checked(self):
        score, notes = topics.quality_score([f"tag-{i}" for i in range(21)])
        self.assertLess(score, 100)
        self.assertTrue(any("20" in note for note in notes))

    def test_structure_does_not_claim_semantic_precision(self):
        score, notes = topics.quality_score(["banana-storage", "moon-output", "paper-metric",
                                            "cat-server", "chair-network"])
        self.assertEqual(score, 100)
        self.assertTrue(any("semantic" in note.lower() for note in notes))


class TopicEvidenceTests(unittest.TestCase):
    def test_search_sample_is_not_a_topic_page_claim(self):
        best = {"total_count": 1, "incomplete_results": False,
                "items": [{"full_name": "other/repo", "stargazers_count": 10}]}
        starred = {"items": [{"full_name": "other/one", "stargazers_count": 20},
                             {"full_name": "other/two", "stargazers_count": 10}],
                   "total_count": 2, "incomplete_results": False}
        with patch.object(topics, "_search_repos", side_effect=[best, starred]):
            result = topics.analyze_single_topic("proxy", "owner/repo", 2, "", "api", 15)
        self.assertEqual(result["query"], "topic:proxy")
        self.assertEqual(result["sort"], "best-match")
        self.assertEqual(result["sample_limit"], 15)
        self.assertEqual(result["sampled_count"], 1)
        self.assertTrue(result["observed_at"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["star_sampled_count"], 2)
        self.assertEqual(result["median_stars_sample"], 15)
        self.assertIsNone(result["best_match_rank"])
        self.assertNotIn("just outside", result["advice"])
        self.assertNotIn("traffic source", result["advice"])

    def test_crowded_sample_does_not_recommend_removal(self):
        items = [{"full_name": f"other/repo-{i}", "stargazers_count": 1000} for i in range(15)]
        best = {"total_count": 2000, "items": items, "incomplete_results": False}
        starred = best
        with patch.object(topics, "_search_repos", side_effect=[best, starred]):
            result = topics.analyze_single_topic("proxy", "owner/repo", 1, "", "api", 15)
        self.assertNotEqual(result["verdict"], "crowded-swap")
        self.assertEqual(result["verdict"], "crowded-unobserved")
        self.assertNotIn("replace", result["advice"])
        self.assertNotIn("swapping", result["advice"])

    def test_incomplete_results_are_partial(self):
        result_data = {"total_count": 20, "items": [], "incomplete_results": True}
        with patch.object(topics, "_search_repos", return_value=result_data):
            result = topics.analyze_single_topic("proxy", "owner/repo", 1, "", "api", 15)
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["incomplete_results"])
        self.assertEqual(result["verdict"], "unknown")
        self.assertIsNone(topics.ranking_score([result]))

    def test_missing_or_invalid_samples_remain_unknown(self):
        for payload in ({}, {"items": None}, {"items": "not a list"}):
            with self.subTest(payload=payload), patch.object(topics, "_search_repos", return_value=payload):
                result = topics.analyze_single_topic("proxy", "owner/repo", 1, "", "api", 15)
            self.assertEqual(result["status"], "unavailable")
            self.assertIsNone(result["pool_total"])
            self.assertIsNone(result["sampled_count"])
            self.assertIsNone(result["star_sampled_count"])
            self.assertIsNone(result["incomplete_results"])

    def test_missing_completeness_and_invalid_totals_are_partial(self):
        for total in (None, True, -1, "10"):
            payload = {"items": [], "total_count": total}
            with self.subTest(total=total), patch.object(topics, "_search_repos", return_value=payload):
                result = topics.analyze_single_topic("proxy", "owner/repo", 1, "", "api", 15)
            self.assertEqual(result["status"], "partial")
            self.assertIsNone(result["pool_total"])
            self.assertIsNone(result["incomplete_results"])
            self.assertEqual(result["sampled_count"], 0)
            self.assertEqual(result["verdict"], "unknown")
            self.assertIsNone(topics.ranking_score([result]))

    def test_known_empty_sample_is_observed_zero(self):
        payload = {"items": [], "total_count": 0, "incomplete_results": False}
        with patch.object(topics, "_search_repos", return_value=payload):
            result = topics.analyze_single_topic("proxy", "owner/repo", 1, "", "api", 15)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["pool_total"], 0)
        self.assertEqual(result["sampled_count"], 0)

    def test_failed_star_query_has_unknown_star_count(self):
        best = {"items": [], "total_count": 0, "incomplete_results": False}
        with patch.object(topics, "_search_repos", side_effect=[best, github_api.GitHubAPIError("403", status=403)]):
            result = topics.analyze_single_topic("proxy", "owner/repo", 1, "", "api", 15)
        self.assertEqual(result["status"], "partial")
        self.assertIsNone(result["star_sampled_count"])
        self.assertIsNone(result["median_stars_sample"])
        self.assertEqual(result["verdict"], "unknown")

    def test_missing_ranking_returns_none(self):
        self.assertIsNone(topics.ranking_score([]))
        self.assertIsNone(topics.ranking_score([{"verdict": "error", "status": "unavailable"}]))

    def test_candidate_support_uses_unique_repositories_and_eligibility(self):
        payload = {"total_count": 5, "incomplete_results": False, "items": [
            {"full_name": "one/repo", "topics": ["useful", "unsupported"]},
            {"full_name": "two/repo", "topics": ["useful"]},
            {"full_name": "owner/repo", "topics": ["self-tag"]},
            {"full_name": "fork/repo", "fork": True, "topics": ["fork-tag"]},
            {"full_name": "old/repo", "archived": True, "topics": ["archived-tag"]},
        ]}
        with patch.object(topics, "_search_repos", return_value=payload):
            result = topics.discover_candidate_topics(["proxy", "vless"], set(), "", "api",
                                                     repo="owner/repo", evidence_text="Supports useful workflows.")
        self.assertEqual(len(result["comparables_sampled"]), 2)
        candidate, = result["candidates"]
        self.assertEqual(candidate["topic"], "useful")
        self.assertEqual(candidate["support_count"], 2)
        self.assertEqual(candidate["comparable_count"], 2)
        self.assertEqual(candidate["sample_denominator"], 2)
        self.assertEqual(candidate["examples"], ["one/repo", "two/repo"])
        self.assertTrue(candidate["requires_review"])
        self.assertTrue(candidate["lexical_support"])
        self.assertIn("useful", candidate["evidence_snippet"])

    def test_duplicate_single_repository_cannot_satisfy_support_threshold(self):
        payload = {"total_count": 1, "incomplete_results": False,
                   "items": [{"full_name": "one/repo", "topics": ["false-candidate"]}]}
        with patch.object(topics, "_search_repos", return_value=payload):
            result = topics.discover_candidate_topics(["proxy", "vless"], set(), "", "api")
        self.assertEqual(result["candidates"], [])

    def test_candidate_search_missing_payload_has_unknown_counts(self):
        with patch.object(topics, "_search_repos", return_value={}):
            result = topics.discover_candidate_topics(["proxy"], set(), "", "api")
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["observations"][0]["sampled_count"])
        self.assertIsNone(result["sample_denominator"])
        self.assertTrue(result["errors"])

    def test_all_topic_failures_are_unavailable_and_listed(self):
        failure = {"topic": "proxy", "status": "unavailable", "verdict": "error", "error": "HTTP 403"}
        with patch.object(topics, "analyze_single_topic", return_value=failure):
            with patch.object(topics, "discover_candidate_topics", return_value={"candidates": [], "errors": ["candidate HTTP 429"], "status": "unavailable"}):
                report = topics.analyze_topics("owner/repo", ["proxy"], 1, ["proxy"])
        self.assertEqual(report["status"], "unavailable")
        self.assertIsNone(report["ranking_score"])
        self.assertEqual(report["coverage"]["topics_succeeded"], 0)
        self.assertTrue(any("403" in item for item in report["limitations"]))
        self.assertTrue(any("429" in item for item in report["limitations"]))

    def test_skipped_candidate_queries_do_not_mask_topic_failure(self):
        failure = {"topic": "proxy", "status": "unavailable", "verdict": "error", "error": "HTTP 403"}
        with patch.object(topics, "analyze_single_topic", return_value=failure):
            report = topics.analyze_topics("owner/repo", ["proxy"], 1, [])
        self.assertEqual(report["status"], "unavailable")

    def test_empty_configuration_can_be_scored_without_remote_observations(self):
        report = topics.analyze_topics("owner/repo", [], 1, [])
        self.assertEqual(report["status"], "ok")
        self.assertIsNone(report["ranking_score"])
        self.assertEqual(report["coverage"]["topics_total"], 0)

    def test_unanalysed_topics_make_coverage_partial(self):
        success = {"topic": "proxy", "status": "ok", "verdict": "off-sample", "error": ""}
        with patch.object(topics, "analyze_single_topic", return_value=success):
            with patch.object(topics, "discover_candidate_topics", return_value={"candidates": [], "errors": [], "status": "ok"}):
                report = topics.analyze_topics("owner/repo", ["proxy", "tunnel"], 1, ["proxy"], max_topics=1)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["coverage"]["topics_total"], 2)
        self.assertEqual(report["coverage"]["topics_analyzed"], 1)


if __name__ == "__main__":
    unittest.main()
