#!/usr/bin/env python3
"""
Module B: Awesome-list matching.

Derives search terms from the repo's topics/language/name, queries the GitHub
Search API for awesome-xxx lists, filters for relevance + maintenance, and
resolves each list's contribution guide URL for manual PR submission.

Standalone usage:
  python awesome_match.py owner/repo [--json]
  python awesome_match.py owner/repo --terms "workers,proxy"
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from github_api import GitHubAPIError, fetch_json, get_token, resolve_repo
from repo_audit import LANGUAGE_TOPICS, tokenize

MAX_LISTS = 5
MIN_STARS = 300            # quality floor for a list worth submitting to
NICHE_MIN_STARS = 30       # lower floor when the list name contains our keyword
STALE_DAYS = 548           # ~18 months: "still maintained" threshold

# Terms too generic to drive relevant matches (language names are also excluded).
GENERIC_TERMS = {
    "pages", "page", "app", "apps", "web", "site", "sites", "tool", "tools",
    "project", "projects", "code", "github", "api", "apis", "cli", "ui",
    "demo", "free", "best", "top", "list", "guide", "guides", "tutorial",
    "tutorials", "examples", "template", "templates", "awesome", "deploy",
    "deployment", "server", "servers", "self", "hosted", "hosting",
}


def derive_terms(topics: list[str], language: str, name: str, description: str) -> list[str]:
    """Build search terms: functional topics first, then name/description tokens.

    Excludes language names and generic words to avoid irrelevant matches.
    """
    skip = LANGUAGE_TOPICS | GENERIC_TERMS
    terms = [t.lower() for t in topics if t.lower() not in skip and len(t) >= 3]
    # language alone is too broad as a search term; only keep distinctive ones
    if language and language.lower() not in terms and language.lower() not in skip:
        terms.append(language.lower())
    for token in tokenize(name.replace("-", " ").replace("_", " ")):
        if len(token) >= 3 and token not in terms and token not in skip:
            terms.append(token)
    for token in tokenize(description):
        if len(token) >= 3 and token not in terms and token not in skip:
            terms.append(token)
    return terms[:6]


def _days_since(value: str | None) -> int | None:
    """Days between an ISO8601 timestamp and now (UTC)."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - dt).days


def search_awesome_lists(terms: list[str], token: str, provider: str) -> dict:
    """Search + dedupe + filter awesome lists for the given terms."""
    import re
    import time
    seen: dict[str, dict] = {}
    errors = []

    for term in terms[:4]:  # cap queries to stay within search rate limits
        for query in (f"awesome-{term} in:name", f"awesome {term} in:name,description"):
            try:
                time.sleep(1.2)
                data = fetch_json(
                    "/search/repositories",
                    token=token,
                    params={"q": query, "sort": "stars", "order": "desc", "per_page": 10},
                    provider=provider, timeout=35,
                )
            except GitHubAPIError as exc:
                errors.append(f"{query}: {exc}")
                continue
            for item in data.get("items") or []:
                full_name = item.get("full_name") or ""
                name = (item.get("name") or "").lower()
                description_lc = (item.get("description") or "").lower()
                if not re.match(r"^awesome[-_]", name):
                    continue
                # relevance gate: the search term must actually describe this list
                if term not in name and term not in description_lc:
                    continue
                stars = item.get("stargazers_count", 0)
                stale = _days_since(item.get("pushed_at"))
                floor = NICHE_MIN_STARS if term in name else MIN_STARS
                if stars < floor or (stale is not None and stale > STALE_DAYS):
                    continue
                if full_name in seen:
                    seen[full_name]["matched_terms"].add(term)
                    continue
                seen[full_name] = {
                    "full_name": full_name,
                    "url": item.get("html_url"),
                    "description": (item.get("description") or "")[:140],
                    "stars": stars,
                    "last_push": item.get("pushed_at"),
                    "days_since_push": stale,
                    "matched_terms": {term},
                    "contributing_url": None,
                    "open_issues": int(item.get("open_issues_count", 0)),
                }

    return {"lists": list(seen.values()), "errors": errors}


def resolve_contributing_guide(lists: list[dict], token: str, provider: str, cap: int = MAX_LISTS) -> None:
    """Fill contributing_url via each list's community profile (mutates in place)."""
    for entry in lists[:cap]:
        try:
            profile = fetch_json(f"/repos/{entry['full_name']}/community/profile",
                                 token=token, provider=provider)
            files = profile.get("files") or {}
            contributing = (files.get("contributing") or {})
            entry["contributing_url"] = contributing.get("html_url")
            if not entry["contributing_url"]:
                readme = files.get("readme") or {}
                entry["contributing_url"] = None
                entry["note"] = ("No CONTRIBUTING file — check the README's 'Contributing' section: "
                                 + (readme.get("html_url") or entry["url"]))
        except GitHubAPIError as exc:
            entry["note"] = f"contributing guide lookup failed: {exc}"


def find_awesome_lists(repo: str, topics: list[str], language: str, name: str,
                       description: str, terms: list[str] | None = None,
                       token: str = "", provider: str = "auto") -> dict:
    """Full awesome-list matching report for a repo."""
    terms = terms or derive_terms(topics, language, name, description)
    result = search_awesome_lists(terms, token, provider)
    lists = sorted(result["lists"], key=lambda x: (-len(x["matched_terms"]), -x["stars"]))
    for entry in lists:
        entry["matched_terms"] = sorted(entry["matched_terms"])
    resolve_contributing_guide(lists, token, provider)

    # module score: opportunities exist and are actionable
    if not lists:
        score = 20  # no obvious list — not necessarily bad, just no quick win
    elif any(l.get("contributing_url") for l in lists[:MAX_LISTS]):
        score = 90
    else:
        score = 65
    return {
        "repo": repo,
        "terms_used": terms,
        "lists": lists[:MAX_LISTS],
        "total_matches": len(lists),
        "errors": result["errors"],
        "score": score,
    }


def print_text(report: dict):
    """Human-readable summary for standalone CLI use."""
    print(f"\nAwesome-list Matching: {report['repo']}  score={report['score']}")
    print("=" * 60)
    print(f"Terms: {', '.join(report['terms_used'])}")
    if not report["lists"]:
        print("No maintained awesome-lists matched these terms.")
    for entry in report["lists"]:
        print(f"\n- {entry['full_name']} ({entry['stars']}⭐, last push {entry['days_since_push']}d ago)")
        print(f"  {entry['url']}")
        print(f"  match: {', '.join(entry['matched_terms'])}")
        if entry.get("contributing_url"):
            print(f"  contributing guide: {entry['contributing_url']}")
        elif entry.get("note"):
            print(f"  {entry['note']}")
    for err in report["errors"]:
        print(f"Error: {err}")


def main():
    parser = argparse.ArgumentParser(description="Find awesome-lists to submit a GitHub repo to.")
    parser.add_argument("repo", help="owner/repo, GitHub URL, or local clone path")
    parser.add_argument("--token", help="GitHub token override (prefer GH_TOKEN env)")
    parser.add_argument("--provider", choices=["auto", "api", "gh"], default="auto")
    parser.add_argument("--terms", default="", help="comma-separated search terms (default: derived from repo)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        repo = resolve_repo(args.repo)
        token = get_token(args.token)
        meta = fetch_json(f"/repos/{repo}", token=token, provider=args.provider)
    except GitHubAPIError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    terms = [t.strip() for t in args.terms.split(",") if t.strip()] or None
    report = find_awesome_lists(
        repo=repo,
        topics=meta.get("topics") or [],
        language=meta.get("language") or "",
        name=meta.get("name") or "",
        description=meta.get("description") or "",
        terms=terms, token=token, provider=args.provider,
    )
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_text(report)


if __name__ == "__main__":
    main()
