"""Offline checks for bounded search observations and non-additive traffic history."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from github_api import GitHubAPIError
from search_benchmark import SEARCH_PAUSE, benchmark_queries, compare_benchmarks
from traffic_snapshot import collect_traffic


def search_payload(names=("other/lib", "owner/project"), incomplete=False, total=None):
    return {"total_count": len(names) if total is None else total,
            "incomplete_results": incomplete,
            "items": [{"full_name": name, "stargazers_count": 12,
                       "description": "An observed description", "html_url": f"https://github.com/{name}"}
                      for name in names]}


def observation(query="cli tool", rank=2, **overrides):
    return {"query": query, "sort": "best-match", "sample_limit": 100,
            "sampled_count": 2, "total": 2, "incomplete_results": False,
            "status": "ok", "rank_in_sample": rank, **overrides}


def traffic_series(kind, days, uniques=4):
    return {"count": sum(count for _, count in days), "uniques": uniques,
            kind: [{"timestamp": f"{date}T00:00:00Z", "count": count, "uniques": min(count, 2)}
                   for date, count in days]}


def traffic_response(days=None):
    days = days or [("2026-09-29", 3), ("2026-09-30", 4)]
    return [traffic_series("views", days), traffic_series("clones", days),
            [{"referrer": "example.com", "count": 5, "uniques": 3}],
            [{"path": "/owner/project", "title": "project", "count": 8, "uniques": 4}]]


class SearchBenchmarkTests(unittest.TestCase):
    def setUp(self):
        pause = patch("search_benchmark.time.sleep")
        self.sleep = pause.start()
        self.addCleanup(pause.stop)

    @patch("search_benchmark.fetch_json")
    def test_deduplicates_queries_and_only_reports_requested_competitors(self, fetch):
        fetch.return_value = search_payload()
        rows = benchmark_queries("Owner/Project", [" cli tool ", "cli tool", "", "other"],
                                 competitors=["OTHER/lib", "unobserved/repo"])
        self.assertEqual(fetch.call_count, 2)
        self.sleep.assert_called_once_with(SEARCH_PAUSE)
        self.assertEqual([row["query"] for row in rows], ["cli tool", "other"])
        self.assertEqual(rows[0]["rank_in_sample"], 2)
        self.assertEqual(rows[0]["status"], "ok")
        self.assertEqual([row["full_name"] for row in rows[0]["competitors"]], ["other/lib"])
        self.assertEqual(rows[0]["competitors"][0]["rank_in_sample"], 1)
        self.assertNotIn("sort", fetch.call_args.kwargs["params"])
        self.assertTrue(rows[0]["observed_at_utc"].endswith("+00:00"))

    @patch("search_benchmark.fetch_json")
    def test_limits_apply_after_deduplication(self, fetch):
        fetch.return_value = search_payload()
        self.assertEqual(len(benchmark_queries("owner/project", ["same"] * 12)), 1)
        for limit in (0, 101, True):
            with self.assertRaises(ValueError):
                benchmark_queries("owner/project", ["query"], top_n=limit)
        with self.assertRaises(ValueError):
            benchmark_queries("owner/project", [str(n) for n in range(9)])

    @patch("search_benchmark.fetch_json")
    def test_api_failures_are_independent_and_unknown(self, fetch):
        fetch.side_effect = [GitHubAPIError("Bad credentials", status=401),
                             GitHubAPIError("Forbidden", status=403), search_payload()]
        rows = benchmark_queries("owner/project", ["one", "two", "three"])
        for row, status in zip(rows[:2], (401, 403)):
            self.assertEqual(row["status"], "unavailable")
            self.assertEqual(row["error"]["status"], status)
            self.assertIsNone(row["total"])
            self.assertIsNone(row["sampled_count"])
            self.assertIsNone(row["rank_in_sample"])
            self.assertIsNone(row["incomplete_results"])
        self.assertEqual(rows[2]["status"], "ok")
        self.assertEqual(self.sleep.call_count, 2)
        self.assertTrue(all(call.args == (SEARCH_PAUSE,) for call in self.sleep.call_args_list))

    @patch("search_benchmark.fetch_json")
    def test_queries_are_sequential_with_pauses_between_calls(self, fetch):
        actions = []
        self.sleep.side_effect = lambda seconds: actions.append(("pause", seconds))
        fetch.side_effect = lambda *args, **kwargs: actions.append(("query", kwargs["params"]["q"])) or search_payload()
        benchmark_queries("owner/project", ["one", "one", "two", "three"])
        self.assertEqual(actions, [("query", "one"), ("pause", SEARCH_PAUSE),
                                   ("query", "two"), ("pause", SEARCH_PAUSE), ("query", "three")])

    @patch("search_benchmark.fetch_json")
    def test_partial_or_missing_data_is_not_complete(self, fetch):
        missing_flag = search_payload()
        missing_flag.pop("incomplete_results")
        fetch.side_effect = [search_payload(incomplete=True), missing_flag,
                             search_payload(total=100), {}, search_payload(names=())]
        rows = benchmark_queries("owner/project", ["one", "two", "three", "four", "five"])
        self.assertEqual([row["status"] for row in rows], ["partial", "partial", "partial", "unavailable", "ok"])
        self.assertIsNone(rows[1]["incomplete_results"])
        self.assertIsNone(rows[3]["sampled_count"])
        self.assertEqual(rows[4]["total"], 0)
        self.assertIsNone(rows[4]["rank_in_sample"])

    def test_comparison_never_invents_a_rank_for_absence(self):
        result = compare_benchmarks([observation(rank=None)], [observation(rank=2)])
        row = result["comparisons"][0]
        self.assertEqual(row["status"], "comparable")
        self.assertEqual(row["change"], "left_sample")
        self.assertIsNone(row["rank_delta"])
        self.assertIsNone(row["current_rank"])
        row = compare_benchmarks([observation(rank=1)], [observation(rank=2)])["comparisons"][0]
        self.assertEqual(row["change"], "improved")
        self.assertEqual(row["rank_delta"], 1)
        row = compare_benchmarks([observation(rank=None)], [observation(rank=None)])["comparisons"][0]
        self.assertEqual(row["change"], "not_observed")
        self.assertIsNone(row["rank_delta"])

    def test_missing_and_incomparable_baselines(self):
        current = observation()
        cases = [observation(sort="stars"), observation(sample_limit=20),
                 observation(sort=None),
                 observation(incomplete_results=True, status="partial"),
                 observation(status="unavailable", sampled_count=None),
                 observation(sampled_count=None), observation(rank=0), observation(rank=3),
                 observation(rank=True), observation(rank=1.0)]
        for baseline in cases:
            with self.subTest(baseline=baseline):
                row = compare_benchmarks([current], [baseline])["comparisons"][0]
                self.assertEqual(row["status"], "incomparable")
                self.assertEqual(row["change"], "unknown")
                self.assertIsNone(row["rank_delta"])
        row = compare_benchmarks([current], [observation(query="different")])["comparisons"][0]
        self.assertEqual(row["status"], "missing_baseline")
        row = compare_benchmarks([observation(status="partial", incomplete_results=True)],
                                 [observation(status="partial", incomplete_results=True)])["comparisons"][0]
        self.assertEqual(row["status"], "incomparable")
        row = compare_benchmarks([current], [current, copy.deepcopy(current)])["comparisons"][0]
        self.assertEqual(row["status"], "incomparable")
        row = compare_benchmarks([observation(sort=None)], [observation(sort=None)])["comparisons"][0]
        self.assertEqual(row["status"], "incomparable")

    def test_malformed_baseline_is_a_readable_validation_error(self):
        for invalid in (None, {}, "text", [None], ["row"]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                compare_benchmarks([observation()], invalid)
        with self.assertRaises(ValueError):
            compare_benchmarks(None, [observation()])

    def test_missing_rank_field_is_not_a_negative_observation(self):
        missing_rank = observation()
        missing_rank.pop("rank_in_sample")
        for current, baseline in ((missing_rank, observation()), (observation(), missing_rank)):
            with self.subTest(current=current, baseline=baseline):
                row = compare_benchmarks([current], [baseline])["comparisons"][0]
                self.assertEqual(row["status"], "incomparable")
                self.assertEqual(row["change"], "unknown")
                self.assertIsNone(row["rank_delta"])


class TrafficSnapshotTests(unittest.TestCase):
    @patch("traffic_snapshot.fetch_json")
    def test_valid_special_names_use_shared_normalization(self, fetch):
        with tempfile.TemporaryDirectory() as directory:
            for source in ("owner/.github", "https://github.com/OWNER/_repo.git", "git@github.com:owner/-repo.git"):
                with self.subTest(source=source):
                    fetch.side_effect = traffic_response()
                    result = collect_traffic(source, archive_dir=directory)
                    self.assertEqual(result["status"], "ok")
                    expected = {"owner/.github", "owner/_repo", "owner/-repo"}
                    self.assertIn(result["repo"], expected)
                    self.assertEqual(Path(result["archived_path"]).parent,
                                     Path(directory).resolve().joinpath(*result["repo"].split("/")))

    @patch("traffic_snapshot.fetch_json")
    def test_invalid_repositories_never_fetch_or_create_archives(self, fetch):
        with tempfile.TemporaryDirectory() as directory:
            for source in ("owner/..", "../project", "owner/project/../../escape",
                           "owner/project/extra", "https://example.com/owner/project",
                           "https://github.com/owner/%2e%2e", "file:///owner/project", "owner/project?secret=x"):
                with self.subTest(source=source), self.assertRaises(ValueError):
                    collect_traffic(source, archive_dir=directory)
            fetch.assert_not_called()
            self.assertEqual(list(Path(directory).rglob("*")), [])

    @patch("traffic_snapshot.fetch_json")
    def test_default_collection_writes_no_archive(self, fetch):
        fetch.side_effect = traffic_response()
        with patch("traffic_snapshot._archive") as archive:
            result = collect_traffic("owner/project", token="do_not_save", provider="api")
        archive.assert_not_called()
        self.assertEqual(fetch.call_count, 4)
        self.assertEqual(result["status"], "ok")
        self.assertIsNone(result["archived_path"])
        self.assertNotIn("do_not_save", json.dumps(result))
        self.assertTrue(all(item["status"] == "ok" for item in result["coverage"].values()))
        self.assertIn("14 days", " ".join(result["limitations"]))
        self.assertIn("top 10", " ".join(result["limitations"]))

    @patch("traffic_snapshot.fetch_json")
    def test_401_and_403_never_become_zero_traffic(self, fetch):
        for code in (401, 403):
            with self.subTest(code=code):
                fetch.side_effect = [GitHubAPIError("Unavailable", status=code)] * 4
                result = collect_traffic("owner/project")
                self.assertEqual(result["status"], "unavailable")
                for kind in ("views", "clones", "referrers", "paths"):
                    self.assertIsNone(result[kind])
                    self.assertEqual(result["coverage"][kind]["error"]["status"], code)

    @patch("traffic_snapshot.fetch_json")
    def test_partial_response_preserves_observed_endpoints(self, fetch):
        responses = traffic_response()
        responses[1] = GitHubAPIError("Forbidden", status=403)
        fetch.side_effect = responses
        result = collect_traffic("owner/project")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["views"]["count"], 7)
        self.assertIsNone(result["clones"])
        self.assertEqual(result["referrers"][0]["referrer"], "example.com")

    @patch("traffic_snapshot.fetch_json")
    def test_overlap_upserts_days_and_keeps_windows_separate(self, fetch):
        with tempfile.TemporaryDirectory() as directory:
            fetch.side_effect = traffic_response()
            first = collect_traffic("owner/project", token="do_not_save", archive_dir=directory)
            fetch.side_effect = traffic_response([("2026-09-30", 9), ("2026-10-01", 2)])
            second = collect_traffic("OWNER/PROJECT", archive_dir=directory)
            data = json.loads(Path(second["archived_path"]).read_text())
            self.assertEqual(first["archived_path"], second["archived_path"])
            self.assertEqual(len(data["daily"]["views"]), 3)
            self.assertEqual(data["daily"]["views"]["2026-09-30"]["count"], 9)
            self.assertEqual([row["count"] for row in second["history"]["views"]], [3, 9, 2])
            self.assertEqual(len(data["windows"]["referrers"]), 2)
            self.assertEqual(len(data["windows"]["paths"]), 2)
            self.assertEqual(len(data["windows"]["views"]), 2)
            self.assertEqual(second["views"]["uniques"], 4)
            self.assertNotIn("total_uniques", second["history"])
            self.assertNotIn("do_not_save", json.dumps(data))
            self.assertFalse(list(Path(directory).rglob("*.tmp")))

    @patch("traffic_snapshot.fetch_json")
    def test_archives_are_isolated_by_repository(self, fetch):
        with tempfile.TemporaryDirectory() as directory:
            fetch.side_effect = traffic_response()
            first = collect_traffic("owner/project", archive_dir=directory)
            fetch.side_effect = traffic_response([("2026-10-01", 1)])
            other = collect_traffic("other/project", archive_dir=directory)
            self.assertNotEqual(first["archived_path"], other["archived_path"])
            self.assertEqual(len(other["history"]["views"]), 1)
            self.assertEqual(json.loads(Path(first["archived_path"]).read_text())["repo"], "owner/project")

    @patch("traffic_snapshot.fetch_json")
    def test_invalid_existing_archives_are_not_overwritten(self, fetch):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "owner" / "project" / "traffic.json"
            destination.parent.mkdir(parents=True)
            for invalid in ({"schema_version": 1, "repo": "someone/else"},
                            {"schema_version": 2, "repo": "owner/project"},
                            {"schema_version": 1, "repo": "owner/project", "daily": None},
                            {"schema_version": 1, "repo": "owner/project", "daily": {}, "windows": {}},
                            "invalid json"):
                with self.subTest(invalid=invalid):
                    original = json.dumps(invalid) if isinstance(invalid, dict) else invalid
                    destination.write_text(original)
                    fetch.side_effect = traffic_response()
                    result = collect_traffic("owner/project", archive_dir=directory)
                    self.assertIsNone(result["archived_path"])
                    self.assertIsNotNone(result["archive_error"])
                    self.assertEqual(destination.read_text(), original)

    @patch("traffic_snapshot.fetch_json")
    def test_failed_atomic_replace_preserves_existing_archive(self, fetch):
        with tempfile.TemporaryDirectory() as directory:
            fetch.side_effect = traffic_response()
            first = collect_traffic("owner/project", archive_dir=directory)
            destination = Path(first["archived_path"])
            original = destination.read_text()
            fetch.side_effect = traffic_response([("2026-10-01", 1)])
            with patch("traffic_snapshot.os.replace", side_effect=OSError("disk unavailable")):
                result = collect_traffic("owner/project", archive_dir=directory)
            self.assertIsNotNone(result["archive_error"])
            self.assertEqual(destination.read_text(), original)
            self.assertFalse(list(Path(directory).rglob("*.tmp")))

    @patch("traffic_snapshot.fetch_json")
    def test_symlink_alias_cannot_mix_repository_archives(self, fetch):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "other" / "project"
            target.mkdir(parents=True)
            alias = root / "owner" / "project"
            alias.parent.mkdir()
            try:
                alias.symlink_to(target, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"Symlinks unavailable: {exc}")
            fetch.side_effect = traffic_response()
            result = collect_traffic("owner/project", archive_dir=directory)
            self.assertIsNone(result["archived_path"])
            self.assertIn("symlink", result["archive_error"])
            self.assertFalse((target / "traffic.json").exists())

    @patch("traffic_snapshot.fetch_json")
    def test_invalid_payloads_remain_unknown(self, fetch):
        invalid_day = traffic_series("views", [("2026-10-01", 3)])
        invalid_day["views"][0]["timestamp"] = "not-a-date"
        fetch.side_effect = [invalid_day, {"count": None}, None, []]
        result = collect_traffic("owner/project")
        self.assertIsNone(result["views"])
        self.assertIsNone(result["clones"])
        self.assertIsNone(result["referrers"])
        self.assertEqual(result["paths"], [])
        self.assertEqual(result["status"], "partial")


if __name__ == "__main__":
    unittest.main()
