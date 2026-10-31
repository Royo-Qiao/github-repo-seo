#!/usr/bin/env python3
"""Repeatable, bounded observations of GitHub repository search results.

Best-match API results are observations, not GitHub topic-page rankings or
evidence of a particular ranking factor. No files are written by this module.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import time

from github_api import GitHubAPIError, fetch_json, get_token, normalize_repo_slug, resolve_repo

SEARCH_PAUSE = 1.2


def benchmark_queries(repo: str, queries: list[str], token: str = "",
                      provider: str = "auto", top_n: int = 100,
                      competitors: list[str] | None = None) -> list[dict]:
    """Observe up to eight distinct queries without assigning ranks to missing data."""
    if isinstance(top_n, bool) or not isinstance(top_n, int) or not 1 <= top_n <= 100:
        raise ValueError("top_n must be an integer from 1 to 100")
    if not isinstance(queries, list) or any(not isinstance(q, str) for q in queries):
        raise ValueError("queries must be a list of strings")
    unique_queries = list(dict.fromkeys(q.strip() for q in queries if q.strip()))
    if len(unique_queries) > 8:
        raise ValueError("At most eight distinct queries can be benchmarked")
    target = normalize_repo_slug(repo).lower()
    if not target:
        raise ValueError("A repository identifier is required")
    requested = {
        normalize_repo_slug(name).lower()
        for name in (competitors or []) if normalize_repo_slug(name)
    }
    results = []
    for index, query in enumerate(unique_queries):
        if index:
            time.sleep(SEARCH_PAUSE)
        row = {
            "query": query, "sort": "best-match",
            "observed_at_utc": datetime.now(timezone.utc).isoformat(),
            "sample_limit": top_n, "sampled_count": None,
            "incomplete_results": None, "status": "unavailable",
            "total": None, "rank_in_sample": None,
            "competitors": [], "error": None,
        }
        try:
            # Omit sort: the Search API defaults to best-match.
            payload = fetch_json("/search/repositories", token=token,
                                 params={"q": query, "per_page": top_n, "page": 1},
                                 provider=provider, timeout=35)
            if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                raise GitHubAPIError("Search response does not contain a result sample")
            items = payload["items"][:top_n]
            total = payload.get("total_count")
            complete_flag = payload.get("incomplete_results")
            row["sampled_count"] = len(items)
            row["total"] = total if isinstance(total, int) and not isinstance(total, bool) and total >= 0 else None
            row["incomplete_results"] = complete_flag if isinstance(complete_flag, bool) else None
            problems = []
            if row["total"] is None:
                problems.append("Search response has no valid total_count")
            if row["incomplete_results"] is None:
                problems.append("Search response has no completeness flag")
            elif row["incomplete_results"]:
                problems.append("GitHub marked these search results incomplete")
            if row["total"] is not None and len(items) != min(top_n, row["total"]):
                problems.append("Returned sample is shorter than the requested result window")
            for position, item in enumerate(items, 1):
                if not isinstance(item, dict) or not isinstance(item.get("full_name"), str):
                    problems.append("Search sample contains an invalid repository entry")
                    continue
                name = item["full_name"].lower()
                if name == target:
                    row["rank_in_sample"] = position
                if name in requested:
                    row["competitors"].append({
                        "full_name": item["full_name"], "rank_in_sample": position,
                        "stars": item.get("stargazers_count"),
                        "description": item.get("description"), "url": item.get("html_url"),
                    })
            row["status"] = "partial" if problems else "ok"
            if problems:
                row["error"] = {"message": "; ".join(dict.fromkeys(problems)), "status": None}
        except GitHubAPIError as exc:
            row["error"] = {"message": str(exc), "status": exc.status}
        results.append(row)
    return results


def _complete_observation(row: dict) -> bool:
    total, limit, count = row.get("total"), row.get("sample_limit"), row.get("sampled_count")
    return (isinstance(row.get("query"), str) and bool(row["query"].strip())
            and row.get("sort") == "best-match"
            and row.get("status") == "ok" and row.get("incomplete_results") is False
            and "rank_in_sample" in row
            and isinstance(total, int) and not isinstance(total, bool) and total >= 0
            and isinstance(limit, int) and not isinstance(limit, bool) and 1 <= limit <= 100
            and isinstance(count, int) and not isinstance(count, bool)
            and count == min(total, limit))


def compare_benchmarks(current: list[dict], baseline: list[dict]) -> dict:
    """Compare only complete observations with identical query, sort and sample limit.

    The caller must ensure both collections concern the same repository.
    Positive rank_delta means an improvement. An unobserved rank stays null.
    """
    if any(not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows)
           for rows in (current, baseline)):
        raise ValueError("Benchmark collections must be lists of observation objects")
    comparisons = []
    for row in current:
        entry = {"query": row.get("query"), "status": "incomparable", "reason": None,
                 "baseline_rank": None, "current_rank": row.get("rank_in_sample"),
                 "rank_delta": None, "change": "unknown"}
        candidates = [b for b in baseline if b.get("query") == row.get("query")]
        matching = [b for b in candidates
                    if b.get("sort") == row.get("sort")
                    and b.get("sample_limit") == row.get("sample_limit")
                    and b.get("incomplete_results") == row.get("incomplete_results")]
        if not candidates:
            entry.update(status="missing_baseline", reason="No baseline for this query")
        elif not matching:
            entry["reason"] = "Sort, sample limit or completeness differs from the baseline"
        elif len(matching) != 1:
            entry["reason"] = "Baseline contains multiple observations for this query"
        else:
            previous = matching[0]
            entry["baseline_rank"] = previous.get("rank_in_sample")
            if not (_complete_observation(row) and _complete_observation(previous)):
                entry["reason"] = "A search observation is unavailable, partial or missing data"
            else:
                old, new = entry["baseline_rank"], entry["current_rank"]
                valid_rank = lambda value, sample: value is None or (
                    isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= sample)
                if not (valid_rank(old, previous["sampled_count"])
                        and valid_rank(new, row["sampled_count"])):
                    entry["reason"] = "An observed rank is outside its returned sample"
                else:
                    entry.update(status="comparable", reason=None)
                    if old is not None and new is not None:
                        entry["rank_delta"] = old - new
                        entry["change"] = "improved" if new < old else "declined" if new > old else "unchanged"
                    elif old is None and new is None:
                        entry["change"] = "not_observed"
                    else:
                        entry["change"] = "entered_sample" if old is None else "left_sample"
        comparisons.append(entry)
    return {
        "comparisons": comparisons,
        "limitations": [
            "The caller must verify that current and baseline observations refer to the same repository.",
            "Comparisons describe Search API samples; they do not establish topic-page rank or SEO causality.",
            "Missing ranks are not zero or an exact rank beyond the sampled window.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Observe explicit GitHub search queries (JSON output).")
    parser.add_argument("repo", help="owner/repo, GitHub URL, or local clone")
    parser.add_argument("queries", nargs="+", help="quoted search queries; at most eight distinct queries")
    parser.add_argument("--top-n", type=int, default=100)
    parser.add_argument("--competitor", action="append", default=[], help="explicit competitor owner/repo")
    parser.add_argument("--token", default="", help="prefer GH_TOKEN environment variable")
    parser.add_argument("--provider", choices=["auto", "api", "gh"], default="auto")
    args = parser.parse_args()
    try:
        repo = resolve_repo(args.repo)
        results = benchmark_queries(repo, args.queries, get_token(args.token),
                                    args.provider, args.top_n, args.competitor)
    except (GitHubAPIError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({"repo": repo, "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
