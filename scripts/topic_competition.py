#!/usr/bin/env python3
"""
Module A: Topic-page competition analysis.

For each of the repo's topics, estimate its position on github.com/topics/<topic>
via the GitHub Search API (q=topic:<t>, default best-match ordering — the same
index that renders the topic page; the page itself is client-rendered React and
no longer exposes ranks/stars in server HTML). Then classify topics as
keep / crowded-swap / niche-opportunity, and mine comparable repos' topics for
add/replace candidates (co-occurrence methodology after
agentic-devrel/github-topic-recommender, MIT).

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

from github_api import GitHubAPIError, fetch_json, get_token, resolve_repo
from repo_audit import LANGUAGE_TOPICS, tokenize

SEARCH_PAUSE = 1.2  # be polite to the search API secondary rate limit

# Topics that add no search value — too vague to match any real query intent.
TOPIC_GENERIC_WORDS = {
    "tool", "tools", "app", "apps", "application", "applications", "project",
    "projects", "code", "coding", "awesome", "demo", "demos", "sample",
    "samples", "example", "examples", "test", "tests", "testing", "misc",
    "other", "new", "best", "free", "cool", "fun", "practice", "learning",
    "tutorial", "tutorials", "program", "programming", "software",
}


def quality_score(topics: list[str]) -> tuple[int, list[str]]:
    """Score fully-controllable topic quality (0-100) + human-readable notes.

    Factors: presence, count in the 5-15 sweet spot, share of precise
    functional tags, and generic-blacklist hits.
    """
    if not topics:
        return 10, ["No topics configured — the biggest controllable gap."]
    lowered = [t.lower() for t in topics]
    functional = [t for t in lowered if t not in LANGUAGE_TOPICS and t not in TOPIC_GENERIC_WORDS]
    generics = [t for t in lowered if t in TOPIC_GENERIC_WORDS]
    notes = []
    score = 100

    n = len(topics)
    if n < 3:
        score -= 25
        notes.append(f"Topic count too low ({n}) — aim for 5-15.")
    elif n < 5:
        score -= 10
        notes.append(f"Topic count on the thin side ({n}) — aim for 5-15.")
    elif n > 15:
        score -= 5
        notes.append(f"Topic count on the high side ({n}) — trim toward ≤15 focused tags.")

    if not functional:
        score -= 30
        notes.append("No precise functional tags (all topics are language names or generic words).")
    elif len(functional) < 3:
        score -= 12
        notes.append(f"Only {len(functional)} precise functional tag(s) — aim for ≥3.")

    if generics:
        score -= 8 * len(generics)
        notes.append(f"Generic blacklist hit(s): {', '.join(generics)} (−8 each).")

    return max(0, min(100, score)), notes


def ranking_score(per_topic: list[dict]) -> int:
    """Score estimated topic-page visibility (0-100). Semi-controllable, approximate."""
    verdict_points = {"keep-strong": 100, "keep": 85, "niche-opportunity": 90,
                      "off-page": 55, "crowded-swap": 30, "unknown": 50}
    scored = [verdict_points.get(e["verdict"], 50) for e in per_topic if e["verdict"] != "error"]
    if not scored:
        return 0
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


def analyze_single_topic(topic: str, repo: str, our_stars: int,
                         token: str, provider: str, top_n: int) -> dict:
    """Rank + leaders + verdict for one topic."""
    entry = {
        "topic": topic,
        "pool_total": None,
        "best_match_rank": None,
        "in_top_n": False,
        "top_repos": [],
        "median_stars_top20": None,
        "top1_stars": None,
        "verdict": "unknown",
        "advice": "",
        "error": "",
    }
    try:
        best = _search_repos(f"topic:{topic}", token, provider, per_page=top_n)
    except GitHubAPIError as exc:
        entry["error"] = str(exc)
        entry["verdict"] = "error"
        return entry

    entry["pool_total"] = best.get("total_count", 0)
    items = best.get("items") or []
    for idx, item in enumerate(items, start=1):
        entry["top_repos"].append({
            "full_name": item.get("full_name"),
            "stars": item.get("stargazers_count", 0),
            "description": (item.get("description") or "")[:110],
        })
        if (item.get("full_name") or "").lower() == repo.lower():
            entry["best_match_rank"] = idx

    stars_list = [r["stars"] for r in entry["top_repos"]]
    if stars_list:
        entry["top1_stars"] = stars_list[0]
    try:
        starred = _search_repos(f"topic:{topic}", token, provider, per_page=top_n, sort="stars")
        star_items = starred.get("items") or []
        star_vals = [i.get("stargazers_count", 0) for i in star_items]
        if star_vals:
            entry["median_stars_top20"] = int(statistics.median(star_vals))
            entry["top1_stars"] = star_vals[0]
    except GitHubAPIError as exc:
        entry["error"] = f"star-sorted query failed: {exc}"

    # ---- verdict ----
    rank = entry["best_match_rank"]
    pool = entry["pool_total"] or 0
    median = entry["median_stars_top20"]
    entry["in_top_n"] = rank is not None

    if rank is not None and rank <= 10:
        entry["verdict"] = "keep-strong"
        entry["advice"] = f"Hold position: ranks ~#{rank} on the topic page — a real traffic source."
    elif rank is not None and rank <= top_n:
        entry["verdict"] = "keep"
        entry["advice"] = f"Visible (rank ~#{rank}/{top_n}); stars/README improvements can push it into the top 10."
    elif rank is None and pool and pool < 120:
        entry["verdict"] = "niche-opportunity"
        entry["advice"] = (f"Small topic (only ~{pool} repos) and you're just outside the visible page — "
                           "a few stars/README pushes can own this long-tail term.")
    elif pool and pool >= 500 and (median is None or our_stars < max(10, (median or 0) * 0.25)):
        entry["verdict"] = "crowded-swap"
        entry["advice"] = (f"Crowded topic (~{pool} repos, top-20 median ≈{median}⭐ vs your {our_stars}⭐) "
                           "and the repo is off the visible page — consider swapping for a narrower long-tail topic.")
    elif rank is None:
        entry["verdict"] = "off-page"
        entry["advice"] = f"Not in the topic page top {top_n}; improve stars/README or replace with a less contested topic."
    return entry


def discover_candidate_topics(keywords: list[str], exclude: set[str], token: str,
                              provider: str, max_keywords: int = 3,
                              comparable_per_kw: int = 8) -> dict:
    """Mine topics used by comparable repos (co-occurrence) as add/replace candidates."""
    from collections import Counter
    cooccurrence = Counter()
    evidence: dict[str, list[str]] = {}
    comparables: list[dict] = []
    errors = []

    for kw in keywords[:max_keywords]:
        if len(kw) < 3:
            continue
        try:
            data = _search_repos(kw, token, provider, per_page=comparable_per_kw, sort="stars")
        except GitHubAPIError as exc:
            errors.append(f"{kw}: {exc}")
            continue
        for item in data.get("items") or []:
            name = item.get("full_name") or ""
            topics = item.get("topics") or []
            comparables.append({"full_name": name, "stars": item.get("stargazers_count", 0),
                                "topics": topics[:12]})
            for t in topics:
                if t.lower() in exclude:
                    continue
                cooccurrence[t] += 1
                evidence.setdefault(t, []).append(name)

    candidates = [
        {"topic": t, "comparable_count": n, "examples": sorted(set(evidence[t]))[:4]}
        for t, n in cooccurrence.most_common(12)
        if n >= 2
    ]
    return {"candidates": candidates, "comparables_sampled": comparables, "errors": errors}


def analyze_topics(repo: str, current_topics: list[str], our_stars: int,
                   keywords: list[str], token: str = "", provider: str = "auto",
                   max_topics: int = 8, top_n: int = 15) -> dict:
    """Full topic-competition report for a repo."""
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
    if len(current_topics) > max_topics:
        report["limitations"].append(
            f"Analyzed first {max_topics} of {len(current_topics)} topics (raise with --max-topics)."
        )

    exclude = {t.lower() for t in current_topics} | LANGUAGE_TOPICS
    try:
        report["candidate_topics"] = discover_candidate_topics(keywords, exclude, token, provider)
    except Exception as exc:  # noqa: BLE001 — candidate mining must never kill the report
        report["limitations"].append(f"Candidate topic mining failed: {exc}")

    # split scores: quality (fully controllable) vs ranking (approximate, semi-controllable)
    q_score, q_notes = quality_score(current_topics)
    report["quality_score"] = q_score
    report["quality_notes"] = q_notes
    report["ranking_score"] = ranking_score(report["per_topic"])
    return report


def print_text(report: dict):
    """Human-readable summary for standalone CLI use."""
    print(f"\nTopic Competition: {report['repo']} ({report['our_stars']}⭐)  "
          f"quality={report.get('quality_score')} ranking={report.get('ranking_score')}")
    print("=" * 60)
    for note in report.get("quality_notes", []):
        print(f"  quality: {note}")
    for e in report["per_topic"]:
        rank = e["best_match_rank"] or "off-page"
        print(f"- {e['topic']}: rank≈{rank}, pool≈{e['pool_total']}, "
              f"top20-median={e['median_stars_top20']}⭐  → {e['verdict']}")
        print(f"    {e['advice'] or e['error']}")
    cands = report.get("candidate_topics", {}).get("candidates", [])
    if cands:
        print("\nCandidate topics (from comparable repos):")
        for c in cands[:8]:
            print(f"- {c['topic']} (used by {c['comparable_count']} comparables, e.g. {', '.join(c['examples'][:2])})")
    for lim in report["limitations"]:
        print(f"Limitation: {lim}")


def main():
    parser = argparse.ArgumentParser(description="GitHub topic-page competition analysis.")
    parser.add_argument("repo", help="owner/repo, GitHub URL, or local clone path")
    parser.add_argument("--token", help="GitHub token override (prefer GH_TOKEN env)")
    parser.add_argument("--provider", choices=["auto", "api", "gh"], default="auto")
    parser.add_argument("--max-topics", type=int, default=8)
    parser.add_argument("--top-n", type=int, default=15, help="page window size (default 15)")
    parser.add_argument("--keywords", default="", help="comma-separated keywords for candidate mining "
                                                       "(default: derived from repo name)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

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
