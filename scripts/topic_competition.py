#!/usr/bin/env python3
"""
Module A: Topic structure checks and GitHub Search API samples.

For each topic, observe the first N Search API results for q=topic:<t>.
This is not an observation of the Topics page or a prediction of traffic.
Co-occurring tags are candidates requiring project-specific review, not
automatic replacements (co-occurrence methodology after
agentic-devrel/github-topic-recommender; methodological reference, license unverified).

Standalone usage:
  python topic_competition.py owner/repo [--json]
  python topic_competition.py owner/repo --max-topics 5 --top-n 10
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from datetime import datetime, timezone

from github_api import GitHubAPIError, fetch_json, get_token, resolve_repo
from repo_audit import LANGUAGE_TOPICS, tokenize

SEARCH_PAUSE = 1.2  # be polite to the search API secondary rate limit

# Generic label patterns; this list cannot establish semantic relevance.
TOPIC_GENERIC_WORDS = {
    "tool", "tools", "app", "apps", "application", "applications", "project",
    "projects", "code", "coding", "awesome", "demo", "demos", "sample",
    "samples", "example", "examples", "test", "tests", "testing", "misc",
    "other", "new", "best", "free", "cool", "fun", "practice", "learning",
    "tutorial", "tutorials", "program", "programming", "software",
}


def structure_score(topics: list[str]) -> tuple[int, list[str]]:
    """Score topic syntax and label coverage, never semantic relevance."""
    notes = ["Structure/syntax coverage only; semantic relevance requires project-specific review."]
    if not topics:
        return 10, notes + ["No topics configured."]
    lowered = [t.lower() for t in topics]
    functional = [t for t in lowered if t not in LANGUAGE_TOPICS and t not in TOPIC_GENERIC_WORDS]
    generics = [t for t in lowered if t in TOPIC_GENERIC_WORDS]
    score = 100

    invalid = [t for t in topics if not re.fullmatch(r"[a-z0-9-]{1,50}", t)]
    if invalid:
        score -= 20 * len(invalid)
        notes.append(f"Invalid topic syntax: {', '.join(repr(t) for t in invalid)}; use 1-50 lowercase letters, digits or hyphens.")
    if len(lowered) != len(set(lowered)):
        score -= 10
        notes.append("Duplicate topics detected.")

    n = len(topics)
    if n < 3:
        score -= 25
        notes.append(f"Topic count too low ({n}) — aim for 5-15.")
    elif n < 5:
        score -= 10
        notes.append(f"Topic count on the thin side ({n}) — aim for 5-15.")
    elif n > 20:
        score -= 20
        notes.append(f"Topic count exceeds GitHub's 20-topic limit ({n}).")
    elif n > 15:
        score -= 5
        notes.append(f"Topic count on the high side ({n}) — trim toward ≤15 focused tags.")

    if not functional:
        score -= 30
        notes.append("All labels match the language/framework or generic-word lists; review coverage of use-case labels.")
    elif len(functional) < 3:
        score -= 12
        notes.append(f"Only {len(functional)} label(s) outside the language/framework and generic-word lists; review use-case coverage.")

    if generics:
        score -= 8 * len(generics)
        notes.append(f"Generic blacklist hit(s): {', '.join(generics)} (−8 each).")

    return max(0, min(100, score)), notes


def quality_score(topics: list[str]) -> tuple[int, list[str]]:
    """Compatibility alias for the structure/syntax rubric."""
    return structure_score(topics)


def ranking_score(per_topic: list[dict]) -> int | None:
    """Descriptive Search API sample score; unavailable observations have no score."""
    verdict_points = {"observed-top10": 100, "observed-in-sample": 85,
                      "small-pool-unobserved": 55, "off-sample": 55, "crowded-unobserved": 30}
    scored = [verdict_points[e["verdict"]] for e in per_topic
              if e.get("status") == "ok" and e.get("verdict") in verdict_points]
    if not scored:
        return None
    return round(statistics.mean(scored))


def _search_repos(query: str, token: str, provider: str,
                  per_page: int = 20, sort: str | None = None) -> dict:
    """One /search/repositories call; returns raw payload ({total_count, items})."""
    params = {"q": query, "per_page": per_page}
    if sort:
        params["sort"] = sort
        params["order"] = "desc"
    time.sleep(SEARCH_PAUSE)
    return fetch_json("/search/repositories", token=token, params=params, provider=provider, timeout=35)


def _sample_data(payload: dict, limit: int) -> tuple[list, int | None, bool | None, list[str]]:
    """Keep observed items separate from missing totals/completeness metadata."""
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise GitHubAPIError("Search response does not contain a result sample.")
    items = payload["items"][:limit]
    raw_total = payload.get("total_count")
    total = raw_total if isinstance(raw_total, int) and not isinstance(raw_total, bool) and raw_total >= 0 else None
    raw_flag = payload.get("incomplete_results")
    flag = raw_flag if isinstance(raw_flag, bool) else None
    problems = []
    if total is None:
        problems.append("Search response has no valid total_count")
    if flag is None:
        problems.append("Search response has no completeness flag")
    elif flag:
        problems.append("GitHub marked these search results incomplete")
    if total is not None and len(items) != min(total, limit):
        problems.append("Returned sample is shorter than the requested result window")
    if any(not isinstance(item, dict) or not isinstance(item.get("full_name"), str)
           or not item["full_name"] for item in items):
        problems.append("Search sample contains an invalid repository entry")
    return items, total, flag, problems


def analyze_single_topic(topic: str, repo: str, our_stars: int,
                         token: str, provider: str, top_n: int) -> dict:
    """Observe one Search API sample and a separately star-sorted sample."""
    entry = {
        "topic": topic,
        "query": f"topic:{topic}",
        "sort": "best-match",
        "observed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "sample_limit": top_n,
        "sampled_count": None,
        "incomplete_results": None,
        "status": "unavailable",
        "pool_total": None,
        "best_match_rank": None,
        "in_top_n": False,
        "top_repos": [],
        "star_query": f"topic:{topic}",
        "star_sort": "stars",
        "star_observed_at": None,
        "star_sample_limit": top_n,
        "star_sampled_count": None,
        "star_incomplete_results": None,
        "median_stars_sample": None,
        "top1_stars": None,
        "verdict": "unknown",
        "advice": "",
        "error": "",
    }
    try:
        best = _search_repos(f"topic:{topic}", token, provider, per_page=top_n)
        items, total, complete_flag, problems = _sample_data(best, top_n)
    except GitHubAPIError as exc:
        entry["error"] = str(exc)
        entry["verdict"] = "error"
        return entry

    entry["pool_total"] = total
    entry["sampled_count"] = len(items)
    entry["incomplete_results"] = complete_flag
    entry["status"] = "partial" if problems else "ok"
    if problems:
        entry["error"] = "best-match sample: " + "; ".join(problems)
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict) or not isinstance(item.get("full_name"), str):
            continue
        entry["top_repos"].append({
            "full_name": item.get("full_name"),
            "stars": item.get("stargazers_count"),
            "description": (item.get("description") or "")[:110],
        })
        if (item.get("full_name") or "").lower() == repo.lower():
            entry["best_match_rank"] = idx

    try:
        entry["star_observed_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        starred = _search_repos(f"topic:{topic}", token, provider, per_page=top_n, sort="stars")
        star_items, _, star_flag, star_problems = _sample_data(starred, top_n)
        entry["star_sampled_count"] = len(star_items)
        entry["star_incomplete_results"] = star_flag
        star_vals = [item.get("stargazers_count") for item in star_items if isinstance(item, dict)]
        valid_stars = len(star_vals) == len(star_items) and all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in star_vals)
        if not valid_stars:
            star_problems.append("Star sample contains missing or invalid star counts")
        if star_problems:
            entry["status"] = "partial"
            entry["error"] = "; ".join(filter(None, [entry["error"], "star sample: " + "; ".join(star_problems)]))
        if star_vals and valid_stars:
            entry["median_stars_sample"] = statistics.median(star_vals)
            entry["top1_stars"] = star_vals[0]
    except GitHubAPIError as exc:
        entry["error"] = "; ".join(filter(None, [entry["error"], f"star-sorted query failed: {exc}"]))
        entry["status"] = "partial"

    # ---- verdict ----
    if entry["status"] != "ok":
        entry["advice"] = "Search observations are partial; no ranking or competition conclusion was drawn."
        return entry
    rank = entry["best_match_rank"]
    pool = entry["pool_total"] or 0
    median = entry["median_stars_sample"]
    entry["in_top_n"] = rank is not None

    if rank is not None and rank <= 10:
        entry["verdict"] = "observed-top10"
        entry["advice"] = f"Observed at #{rank} in this Search API sample; this does not establish Topics-page placement or traffic."
    elif rank is not None and rank <= top_n:
        entry["verdict"] = "observed-in-sample"
        entry["advice"] = f"Observed at #{rank} in the first {top_n} Search API results; keep the tag when it accurately describes the project."
    elif rank is None and pool and pool < 120:
        entry["verdict"] = "small-pool-unobserved"
        entry["advice"] = f"Small reported pool (~{pool} repositories), but the repo was not observed in the first {top_n} results; its position beyond the sample is unknown."
    elif pool and pool >= 500 and (median is None or our_stars < max(10, (median or 0) * 0.25)):
        entry["verdict"] = "crowded-unobserved"
        entry["advice"] = (f"Large reported pool (~{pool} repos); star sample median={median} across {entry['star_sampled_count']} results vs your {our_stars}. "
                           "Not observed in the best-match sample; crowding alone is not a reason to remove a relevant tag.")
    elif rank is None:
        entry["verdict"] = "off-sample"
        entry["advice"] = f"Not observed in the first {top_n} Search API results; no Topics-page placement or growth effect was measured."
    return entry


def discover_candidate_topics(keywords: list[str], exclude: set[str], token: str,
                              provider: str, max_keywords: int = 3,
                              comparable_per_kw: int = 8, repo: str = "",
                              evidence_text: str = "") -> dict:
    """Mine unique non-fork, active repository tags for manual relevance review."""
    from collections import Counter
    cooccurrence = Counter()
    evidence: dict[str, list[str]] = {}
    comparables: dict[str, dict] = {}
    errors = []
    observations = []
    attempted = succeeded = 0
    incomplete = False

    for kw in list(dict.fromkeys(keywords))[:max_keywords]:
        if len(kw) < 3:
            continue
        attempted += 1
        observation = {"query": kw, "sort": "stars", "sample_limit": comparable_per_kw,
                       "observed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                       "sampled_count": None, "incomplete_results": None, "status": "unavailable"}
        observations.append(observation)
        try:
            data = _search_repos(kw, token, provider, per_page=comparable_per_kw, sort="stars")
            items, total, complete_flag, problems = _sample_data(data, comparable_per_kw)
        except GitHubAPIError as exc:
            errors.append(f"{kw}: {exc}")
            continue
        succeeded += 1
        observation["sampled_count"] = len(items)
        observation["pool_total"] = total
        observation["incomplete_results"] = complete_flag
        observation["status"] = "partial" if problems else "ok"
        incomplete |= bool(problems)
        if problems:
            errors.append(f"{kw}: " + "; ".join(problems))
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("full_name"), str):
                continue
            name = item.get("full_name") or ""
            key = name.lower()
            if not name or key == repo.lower() or item.get("fork") or item.get("archived") or key in comparables:
                continue
            topics = list(dict.fromkeys(t.lower() for t in (item.get("topics") or [])
                                        if re.fullmatch(r"[a-z0-9-]{1,50}", t)))
            comparables[key] = {"full_name": name, "stars": item.get("stargazers_count"),
                                "topics": topics}
            for t in topics:
                if t.lower() in exclude:
                    continue
                cooccurrence[t] += 1
                evidence.setdefault(t, []).append(name)

    candidates = []
    for t, n in sorted(cooccurrence.items(), key=lambda item: (-item[1], item[0])):
        if n < 2:
            continue
        match_at = evidence_text.lower().find(t)
        candidates.append({
            "topic": t, "support_count": n, "comparable_count": n,
            "sample_denominator": len(comparables), "examples": sorted(set(evidence[t]))[:4],
            "requires_review": True, "lexical_support": match_at >= 0,
            "evidence_snippet": evidence_text[max(0, match_at - 60):match_at + len(t) + 100] if match_at >= 0 else "",
        })
        if len(candidates) >= 12:
            break
    status = "unavailable" if attempted and not succeeded else "partial" if errors or incomplete else "ok"
    return {"candidates": candidates, "comparables_sampled": list(comparables.values()),
            "sample_denominator": None if attempted and not succeeded else len(comparables),
            "errors": errors, "status": status,
            "coverage": {"queries_attempted": attempted, "queries_succeeded": succeeded},
            "observations": observations,
            "note": "Co-occurrence and literal text matches are clues only; semantic relevance requires review."}


def analyze_topics(repo: str, current_topics: list[str], our_stars: int,
                   keywords: list[str], token: str = "", provider: str = "auto",
                   max_topics: int = 8, top_n: int = 15, evidence_text: str = "") -> dict:
    """Topic structure and bounded Search API observations for a repo."""
    if max_topics < 0 or not 1 <= top_n <= 100:
        raise GitHubAPIError("Use max_topics >= 0 and top_n between 1 and 100.")
    report = {
        "repo": repo,
        "our_stars": our_stars,
        "current_topics": current_topics,
        "per_topic": [],
        "candidate_topics": {},
        "limitations": [],
    }
    if not current_topics:
        report["limitations"].append("Repo has no topics; per-topic analysis skipped — see candidates below.")

    for topic in current_topics[:max_topics]:
        report["per_topic"].append(
            analyze_single_topic(topic, repo, our_stars, token, provider, top_n)
        )
        entry = report["per_topic"][-1]
        if entry.get("error"):
            report["limitations"].append(f"{topic}: {entry['error']}")
        if entry.get("incomplete_results") or entry.get("star_incomplete_results"):
            report["limitations"].append(f"{topic}: GitHub returned incomplete search results.")
    if len(current_topics) > max_topics:
        report["limitations"].append(
            f"Analyzed first {max_topics} of {len(current_topics)} topics (raise with --max-topics)."
        )

    exclude = {t.lower() for t in current_topics} | LANGUAGE_TOPICS
    try:
        report["candidate_topics"] = discover_candidate_topics(keywords, exclude, token, provider,
                                                               repo=repo, evidence_text=evidence_text)
    except Exception as exc:  # noqa: BLE001 — candidate mining must never kill the report
        report["candidate_topics"] = {"candidates": [], "status": "unavailable", "errors": [str(exc)]}
    candidate_report = report["candidate_topics"]
    report["limitations"].extend(f"Candidate topic mining: {error}" for error in candidate_report.get("errors", []))
    if any(observation.get("incomplete_results") for observation in candidate_report.get("observations", [])):
        report["limitations"].append("Candidate topic mining: GitHub returned incomplete search results.")

    q_score, q_notes = structure_score(current_topics)
    report["structure_score"] = report["quality_score"] = q_score  # old keys kept for CLI consumers
    report["structure_notes"] = report["quality_notes"] = q_notes
    report["ranking_score"] = ranking_score(report["per_topic"])
    succeeded = sum(e.get("status") in ("ok", "partial") for e in report["per_topic"])
    report["coverage"] = {"topics_total": len(current_topics), "topics_analyzed": len(report["per_topic"]),
                          "topics_succeeded": succeeded,
                          "candidate_queries": candidate_report.get("coverage", {})}
    statuses = [e.get("status", "unavailable") for e in report["per_topic"]]
    if candidate_report.get("coverage", {}).get("queries_attempted") != 0:
        statuses.append(candidate_report.get("status", "unavailable"))
    if statuses and all(status == "unavailable" for status in statuses):
        report["status"] = "unavailable"
    elif all(status == "ok" for status in statuses) and len(report["per_topic"]) == len(current_topics):
        report["status"] = "ok"
    else:
        report["status"] = "partial"
    return report


def print_text(report: dict):
    """Human-readable summary for standalone CLI use."""
    print(f"\nTopic Structure / Search API Samples: {report['repo']} ({report['our_stars']}⭐)  "
          f"structure={report.get('structure_score')} sample_score={report.get('ranking_score')} status={report['status']}")
    print("=" * 60)
    for note in report.get("structure_notes", []):
        print(f"  structure: {note}")
    for e in report["per_topic"]:
        rank = e["best_match_rank"] or "not observed"
        print(f"- {e['topic']}: rank≈{rank}, pool≈{e['pool_total']}, "
              f"star-sample-median={e['median_stars_sample']}⭐ (n={e['star_sampled_count']}) → {e['verdict']}")
        print(f"    {e['advice'] or e['error']}")
    cands = report.get("candidate_topics", {}).get("candidates", [])
    if cands:
        print("\nCandidate topics (requires relevance review):")
        for c in cands[:8]:
            print(f"- {c['topic']} (used by {c['support_count']}/{c['sample_denominator']} unique sampled repos, e.g. {', '.join(c['examples'][:2])})")
    for lim in report["limitations"]:
        print(f"Limitation: {lim}")


def main():
    parser = argparse.ArgumentParser(description="Topic structure and GitHub Search API samples.")
    parser.add_argument("repo", help="owner/repo, GitHub URL, or local clone path")
    parser.add_argument("--token", help="GitHub token override (prefer GH_TOKEN env)")
    parser.add_argument("--provider", choices=["auto", "api", "gh"], default="auto")
    parser.add_argument("--max-topics", type=int, default=8)
    parser.add_argument("--top-n", type=int, default=15, help="Search API sample limit (1-100, default 15)")
    parser.add_argument("--keywords", default="", help="comma-separated keywords for candidate mining "
                                                       "(default: derived from repo name)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.max_topics < 0 or not 1 <= args.top_n <= 100:
        parser.error("--max-topics must be >= 0; --top-n must be between 1 and 100")

    try:
        repo = resolve_repo(args.repo)
        token = get_token(args.token)
        meta = fetch_json(f"/repos/{repo}", token=token, provider=args.provider)
    except GitHubAPIError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    keywords = ([k.strip() for k in args.keywords.split(",") if k.strip()]
                or tokenize((meta.get("name") or "").replace("-", " ").replace("_", " ")))
    report = analyze_topics(
        repo=repo,
        current_topics=meta.get("topics") or [],
        our_stars=int(meta.get("stargazers_count", 0)),
        keywords=keywords,
        token=token, provider=args.provider,
        max_topics=args.max_topics, top_n=args.top_n,
    )
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_text(report)


if __name__ == "__main__":
    main()
