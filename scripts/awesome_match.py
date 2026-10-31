#!/usr/bin/env python3
"""
Module B: Awesome-list matching.

Derives search terms from the repo's topics/language/name, queries the GitHub
Search API for awesome-xxx lists, filters for relevance + maintenance, reads
README/contribution evidence, and drafts entries for manual review.

Standalone usage:
  python awesome_match.py owner/repo [--json]
  python awesome_match.py owner/repo --terms "workers,proxy"
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import re
import sys
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

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
    import time
    seen: dict[str, dict] = {}
    errors = []
    attempted = succeeded = 0

    for term in terms[:4]:  # cap queries to stay within search rate limits
        for query in (f"awesome-{term} in:name", f"awesome {term} in:name,description"):
            attempted += 1
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
            succeeded += 1
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
                    "default_branch": item.get("default_branch") or "main",
                }

    return {"lists": list(seen.values()), "errors": errors,
            "queries_attempted": attempted, "queries_succeeded": succeeded}


def _content_text(data: dict) -> str:
    """Decode a complete contents/readme API response; failures stay unknown."""
    if data.get("encoding") != "base64" or not isinstance(data.get("content"), str):
        raise ValueError("GitHub did not return complete base64 file content")
    if data.get("truncated"):
        raise ValueError("GitHub returned truncated file content")
    try:
        return base64.b64decode("".join(data["content"].split()), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError(f"File content could not be decoded: {exc}") from exc


def _file_path(file: dict, entry: dict) -> str | None:
    if file.get("path"):
        return file["path"]
    # Community profiles sometimes omit path but provide a blob URL.
    url = urlsplit(file.get("html_url") or "")
    prefix = f"/{entry['full_name']}/blob/{entry['default_branch']}/"
    if url.hostname == "github.com" and url.path.startswith(prefix):
        return url.path[len(prefix):]
    return None


def _headings(markdown: str) -> list[dict]:
    """Preserve heading text and source line numbers, ignoring fenced examples."""
    headings = []
    fence = None
    lines = markdown.splitlines()
    for i, line in enumerate(lines):
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            char = marker.group(1)[0]
            if fence is None:
                fence = char
            elif fence == char:
                fence = None
            continue
        if fence:
            continue
        atx = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if atx:
            headings.append({"heading": atx.group(2), "level": len(atx.group(1)), "line": i + 1})
        elif i and re.match(r"^\s{0,3}(={3,}|-{3,})\s*$", line) and lines[i - 1].strip():
            headings.append({"heading": lines[i - 1].strip(), "level": 1 if "=" in line else 2,
                             "line": i})
    return headings


_CONTRIBUTION = re.compile(r"contribut|submission|adding|准入|收录|贡献|提交", re.I)
_RULE = re.compile(r"\b(must|should|please|require\w*|only|format|alphabet\w*|criteria|"
                   r"qualif\w*|add|entry|entries|pull request|description)\b|"
                   r"提交|收录|格式|要求|必须|应当|请|排序|条目|链接", re.I)


def _section_for(markdown: str, terms: list[str], url: str) -> dict | None:
    candidates = []
    for heading in _headings(markdown):
        if heading["level"] < 2 or _CONTRIBUTION.search(heading["heading"]):
            continue
        matched = []
        for term in terms:
            words = re.split(r"[-_\s]+", term)
            if words and all(re.search(r"(?<![A-Za-z0-9])" + re.escape(word) +
                                      r"(?![A-Za-z0-9])", heading["heading"], re.I)
                             for word in words if word):
                matched.append(term)
        if matched:
            candidates.append({**heading, "matched_terms": matched,
                               "url": f"{url}#L{heading['line']}"})
    return max(candidates, key=lambda h: len(h["matched_terms"])) if candidates else None


def _rule_evidence(markdown: str, url: str, readme: bool = False) -> list[dict]:
    lines = markdown.splitlines()
    allowed = set(range(len(lines)))
    if readme:
        allowed = set()
        headings = _headings(markdown)
        for index, heading in enumerate(headings):
            if not _CONTRIBUTION.search(heading["heading"]):
                continue
            end = next((h["line"] - 1 for h in headings[index + 1:]
                        if h["level"] <= heading["level"]), len(lines))
            allowed.update(range(heading["line"], end))
    evidence = []
    for i, line in enumerate(lines):
        text = line.strip()
        if i in allowed and text and not text.startswith(("#", "```", "~~~")) and _RULE.search(text):
            evidence.append({"text": text[:500], "line": i + 1, "url": f"{url}#L{i + 1}"})
    return evidence[:12]


def _listed_evidence(markdown: str, repo: str, url: str) -> dict | None:
    for i, line in enumerate(markdown.splitlines(), 1):
        for match in re.finditer(r"https?://(?:www\.)?github\.com/[^\s<>\"'`\[\]()]+", line, re.I):
            candidate = urlsplit(match.group(0).rstrip(".,;"))
            path = candidate.path.rstrip("/")
            if path.lower().endswith(".git"):
                path = path[:-4]
            if path.lower() == "/" + repo.lower():
                return {"text": line.strip()[:500], "line": i, "url": f"{url}#L{i}"}
    return None


def resolve_contributing_guide(lists: list[dict], token: str, provider: str, cap: int = MAX_LISTS,
                              repo: str = "", description: str = "") -> None:
    """Read candidate README/rules and draft a submission without taking action."""
    for entry in lists[:cap]:
        entry.update({"readme_url": None, "rules_url": None, "already_listed": None,
                      "status": "review-required", "limitations": [],
                      "eligibility": {"status": "unknown", "evidence": [], "section": None},
                      "coverage": {"readme": False, "rules": False}})
        files = {}
        try:
            profile = fetch_json(f"/repos/{entry['full_name']}/community/profile",
                                 token=token, provider=provider)
            files = profile.get("files") or {}
        except GitHubAPIError as exc:
            entry["limitations"].append(f"Contribution profile unavailable: {exc}")
        readme = files.get("readme") or {}
        path = _file_path(readme, entry)
        readme_text = None
        try:
            endpoint = f"/repos/{entry['full_name']}/contents/{quote(path, safe='/')}" if path else f"/repos/{entry['full_name']}/readme"
            data = fetch_json(endpoint, token=token, provider=provider)
            readme_text = _content_text(data)
            entry["readme_url"] = data.get("html_url") or readme.get("html_url") or entry["url"]
            entry["coverage"]["readme"] = True
            listed = _listed_evidence(readme_text, repo, entry["readme_url"])
            entry["already_listed"] = bool(listed)
            entry["listing_evidence"] = listed
            entry["eligibility"]["section"] = _section_for(readme_text, entry["matched_terms"], entry["readme_url"])
        except (GitHubAPIError, ValueError) as exc:
            entry["limitations"].append(f"README unreadable; listing status unknown: {exc}")

        contributing = files.get("contributing") or {}
        entry["contributing_url"] = contributing.get("html_url")
        entry["rules_url"] = contributing.get("html_url") or entry["readme_url"]
        rules_path = _file_path(contributing, entry)
        evidence = []
        if contributing:
            if not rules_path:
                entry["limitations"].append("Contribution file path unknown; rules could not be read.")
            else:
                try:
                    data = fetch_json(f"/repos/{entry['full_name']}/contents/{quote(rules_path, safe='/')}", token=token, provider=provider)
                    text = _content_text(data)
                    entry["rules_url"] = data.get("html_url") or entry["rules_url"]
                    entry["coverage"]["rules"] = True
                    evidence = _rule_evidence(text, entry["rules_url"] or entry["url"])
                except (GitHubAPIError, ValueError) as exc:
                    entry["limitations"].append(f"Contribution rules unreadable: {exc}")
        elif readme_text is not None:
            evidence = _rule_evidence(readme_text, entry["readme_url"], readme=True)
            entry["coverage"]["rules"] = bool(evidence)
        entry["eligibility"]["evidence"] = evidence
        if evidence:
            entry["eligibility"]["status"] = "review-required"
        else:
            entry["limitations"].append("Admission/format rules unknown; verify with the list maintainer.")
        section = entry["eligibility"]["section"]
        if entry["already_listed"] is True:
            entry["status"] = "already-listed"
        elif entry["already_listed"] is False and section and evidence and not entry["limitations"]:
            entry["status"] = "candidate"
        if section is None and entry["already_listed"] is not True:
            entry["limitations"].append("Matching list section unknown; list-title similarity is not section evidence.")
        project_name = repo.split("/")[-1]
        pitch = " ".join(description.split())
        submission_entry = f"- [{project_name}](https://github.com/{repo})" + (f" — {pitch}" if pitch else "")
        body = f"Proposed entry:\n\n{submission_entry}"
        if section:
            body += f"\n\nSuggested section: {section['heading']} ({section['url']})."
        body += "\n\nPlease review eligibility and entry format against the contribution rules."
        entry["submission"] = {"title": f"Add {project_name}", "entry": submission_entry, "body": body}
        if not pitch:
            entry["limitations"].append("Target repository description is empty; draft includes only its name and URL.")


def find_awesome_lists(repo: str, topics: list[str], language: str, name: str,
                       description: str, terms: list[str] | None = None,
                       token: str = "", provider: str = "auto", homepage: str = "") -> dict:
    """Full awesome-list matching report for a repo."""
    terms = terms or derive_terms(topics, language, name, description)
    result = search_awesome_lists(terms, token, provider)
    lists = sorted(result["lists"], key=lambda x: (-len(x["matched_terms"]), -x["stars"]))
    for entry in lists:
        entry["matched_terms"] = sorted(entry["matched_terms"])
    resolve_contributing_guide(lists, token, provider, repo=repo, description=description)
    shown = lists[:MAX_LISTS]
    limitations = list(result["errors"])
    limitations.extend(f"{entry['full_name']}: {item}" for entry in shown for item in entry["limitations"])
    if not terms:
        limitations.append("No specific search terms could be derived; discovery was not attempted.")
    succeeded = result["queries_succeeded"]
    status = "unavailable" if not succeeded else ("partial" if limitations else "ok")
    return {
        "repo": repo,
        "terms_used": terms,
        "lists": shown,
        "total_matches": len(lists),
        "errors": result["errors"],
        "score": None,
        "status": status,
        "coverage": {"queries_attempted": result["queries_attempted"], "queries_succeeded": succeeded,
                     "lists_inspected": len(shown), "readmes_read": sum(e["coverage"]["readme"] for e in shown),
                     "rules_read": sum(e["coverage"]["rules"] for e in shown)},
        "limitations": limitations,
    }


def print_text(report: dict):
    """Human-readable summary for standalone CLI use."""
    print(f"\nAwesome-list Matching: {report['repo']}  status={report['status']}")
    print("=" * 60)
    print(f"Terms: {', '.join(report['terms_used'])}")
    if not report["lists"]:
        print("No maintained awesome-lists matched these terms.")
    for entry in report["lists"]:
        print(f"\n- {entry['full_name']} ({entry['stars']}⭐, last push {entry['days_since_push']}d ago)")
        print(f"  {entry['url']}")
        print(f"  match: {', '.join(entry['matched_terms'])}")
        print(f"  status: {entry['status']}; already listed: {entry['already_listed']}")
        section = entry["eligibility"]["section"]
        if section:
            print(f"  suggested section: {section['heading']} ({section['url']})")
        if entry.get("contributing_url"):
            print(f"  contributing guide: {entry['contributing_url']}")
        elif entry.get("note"):
            print(f"  {entry['note']}")
        print(f"  draft entry: {entry['submission']['entry']}")
    for limitation in report["limitations"]:
        print(f"Limitation: {limitation}")


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
