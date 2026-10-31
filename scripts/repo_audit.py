#!/usr/bin/env python3
"""
Module 1: Repository metadata audit (name / About description / topics / trust signals).

Standalone usage:
  python repo_audit.py owner/repo [--json]
  python repo_audit.py https://github.com/owner/repo

Checks adapted from github_repo_audit.py in Bhanunamikaze/Agentic-SEO-Skill
(MIT License) https://github.com/Bhanunamikaze/Agentic-SEO-Skill
— website-SEO-specific title strategy was removed; brand-only description and
language-only topics checks were added for repo discoverability.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone

from github_api import (
    GitHubAPIError,
    auth_context,
    fetch_json,
    get_token,
    resolve_repo,
)

STOP_WORDS = {
    "the", "and", "for", "with", "from", "into", "this", "that", "your",
    "are", "was", "were", "been", "being", "have", "has", "had", "will",
    "would", "could", "should", "about", "over", "under", "between", "while",
    "where", "when", "which", "what", "than", "then", "them", "they",
    "you", "our", "their", "its", "via", "all", "any", "not", "can",
    "app", "tool", "tools", "project", "repo", "github", "open", "source",
    "free", "simple", "easy", "fast", "new", "best", "awesome",
}

# Topics that only name a programming language / framework — not functional tags.
LANGUAGE_TOPICS = {
    "python", "javascript", "typescript", "go", "golang", "rust", "java",
    "c", "cpp", "c-plus-plus", "csharp", "dotnet", "ruby", "php", "swift",
    "kotlin", "dart", "html", "css", "scss", "shell", "bash", "zsh",
    "powershell", "lua", "r", "scala", "perl", "haskell", "elixir", "erlang",
    "clojure", "vue", "react", "angular", "svelte", "nextjs", "nuxt",
    "nodejs", "node", "deno", "bun", "django", "flask", "fastapi", "spring",
    "laravel", "rails", "express", "nestjs",
}


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens, minus stopwords and single chars."""
    words = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", (text or "").lower())
    return [w for w in words if len(w) > 1 and w not in STOP_WORDS]


def days_since(value: str | None) -> int | None:
    """Days between an ISO8601 timestamp and now (UTC)."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - dt).days


def add_finding(findings: list, area: str, severity: str, finding: str, evidence: str, fix: str):
    """Append a structured finding (Critical > Warning > Info > Pass)."""
    findings.append({
        "area": area,
        "severity": severity,
        "finding": finding,
        "evidence": evidence,
        "fix": fix,
        "confidence": "Confirmed",
        "evidence_tier": "heuristic",
    })


def score_findings(findings: list) -> dict:
    """Directional 0-100 score from severity counts."""
    critical = sum(1 for f in findings if f["severity"] == "Critical")
    warning = sum(1 for f in findings if f["severity"] == "Warning")
    score = max(0, 100 - critical * 20 - warning * 8)
    rating = (
        "Excellent" if score >= 90
        else "Good" if score >= 70
        else "Needs Improvement" if score >= 50
        else "Poor" if score >= 30
        else "Critical"
    )
    return {"score": score, "rating": rating, "critical": critical, "warning": warning}


def build_audit(repo: str, token: str = "", provider: str = "auto") -> dict:
    """Audit repository metadata and community profile. Returns the full report dict."""
    report = {
        "repo": repo,
        "auth_context": auth_context(token=token),
        "limitations": [],
        "metadata": {},
        "community_profile": {},
        "findings": [],
        "status": "ok",
        "coverage": {"metadata": "unavailable", "community": "unavailable"},
    }
    findings = report["findings"]
    repo_data = {}

    try:
        repo_data = fetch_json(f"/repos/{repo}", token=token, provider=provider)
        if not isinstance(repo_data, dict) or not isinstance(repo_data.get("name"), str) or not repo_data["name"]:
            raise GitHubAPIError("Repository response has no valid repository identity.")
    except GitHubAPIError as exc:
        report["limitations"].append(f"Repository API unavailable: {exc}")
        report["status"] = "unavailable"
        report["summary"] = {"score": None, "rating": "Unknown", "critical": 0, "warning": 0}
        return report

    report["coverage"]["metadata"] = "ok"
    report["coverage"]["topics"] = "ok" if isinstance(repo_data.get("topics"), list) else "unavailable"
    for key in ("description", "topics"):
        if key not in repo_data or (key == "topics" and not isinstance(repo_data[key], list)):
            report["status"] = "partial"
            report["limitations"].append(f"Repository response did not provide {key}; absence is unknown.")

    community_data = {}
    try:
        community_data = fetch_json(f"/repos/{repo}/community/profile", token=token, provider=provider)
        if not isinstance(community_data, dict) or not isinstance(community_data.get("files"), dict):
            raise GitHubAPIError("Community profile response has no files observation.")
        report["community_profile"] = {
            "health_percentage": community_data.get("health_percentage"),
            "files": community_data.get("files") or {},
        }
        report["coverage"]["community"] = "ok"
    except GitHubAPIError as exc:
        report["limitations"].append(f"Community profile API unavailable: {exc}")
        report["status"] = "partial"

    md = {
        "name": repo_data.get("name") or "",
        "full_name": repo_data.get("full_name") or repo,
        "description": (repo_data.get("description") or "").strip(),
        "homepage": (repo_data.get("homepage") or "").strip(),
        "topics": repo_data["topics"] if isinstance(repo_data.get("topics"), list) else [],
        "language": repo_data.get("language") or "",
        "archived": bool(repo_data.get("archived")),
        "fork": bool(repo_data.get("fork")),
        "stargazers_count": int(repo_data.get("stargazers_count", 0)),
        "forks_count": int(repo_data.get("forks_count", 0)),
        "watchers_count": int(repo_data.get("subscribers_count", 0)),
        "open_issues_count": int(repo_data.get("open_issues_count", 0)),
        "pushed_at": repo_data.get("pushed_at"),
        "created_at": repo_data.get("created_at"),
        "default_branch": repo_data.get("default_branch") or "main",
        "license": (repo_data.get("license") or {}).get("spdx_id"),
        "has_pages": bool(repo_data.get("has_pages")),
        "social_preview_url": repo_data.get("social_preview_url"),
    }
    report["metadata"] = md

    # ---------------- metadata checks ----------------
    description = md["description"]
    topics = md["topics"]
    name_tokens = set(tokenize(md["name"].replace("-", " ").replace("_", " ")))
    desc_tokens = [t for t in tokenize(description)]
    pushed_days = days_since(md["pushed_at"])

    if "description" not in repo_data:
        pass
    elif not description:
        add_finding(findings, "Metadata", "Critical",
                    "About description is missing.",
                    "GitHub metadata `description` is empty.",
                    "Add a one-line description containing what-it-does keywords (see suggested copy in the report).")
    else:
        if len(description) < 40:
            add_finding(findings, "Metadata", "Info",
                        "Description is concise; review whether its meaning is clear.",
                        f"Description is {len(description)} characters.",
                        "Keep it concise; add context only if the function or intended users are unclear. Character count alone does not establish search quality.")
        functional = [t for t in desc_tokens if t not in name_tokens]
        if desc_tokens and not functional:
            add_finding(findings, "Metadata", "Warning",
                        "Description repeats the brand/repo name without functional keywords.",
                        f"Description: “{description}”",
                        "Rewrite so someone searching by *capability* (not brand) can match — include the problem solved and the category.")
        if len(description) > 350:
            add_finding(findings, "Metadata", "Info",
                        "Description is lengthy; review readability in the About card.",
                        f"Description is {len(description)} characters.",
                        "Put the project's function first and check the actual About display.")

    if report["coverage"]["topics"] != "ok":
        pass
    elif not topics:
        add_finding(findings, "Metadata", "Warning",
                    "No topics configured.",
                    "GitHub topics list is empty.",
                    "Add 5-15 relevant topics mixing broad categories and long-tail functional tags (max 20).")
    else:
        if len(topics) > 20:
            add_finding(findings, "Metadata", "Critical",
                        "Topic count exceeds GitHub's 20-topic cap.",
                        f"{len(topics)} topics detected.",
                        "Trim to ≤20 high-signal topics.")
        elif len(topics) < 5:
            add_finding(findings, "Metadata", "Info",
                        "Topic coverage is thin.",
                        f"{len(topics)} topics detected.",
                        "Add functional/intent topics to widen discovery surface.")
        lang_only = set(t.lower() for t in topics) & LANGUAGE_TOPICS
        if lang_only and len(lang_only) == len(set(t.lower() for t in topics)):
            add_finding(findings, "Metadata", "Warning",
                        "Topics only name programming languages — no functional tags.",
                        f"Topics: {', '.join(topics)}",
                        "Keep 1-2 language topics and add what-the-project-*does* topics (domain, use-case, ecosystem).")

    if "_" in md["name"]:
        add_finding(findings, "Metadata", "Info",
                    "Repository name uses underscores.",
                    f"Name: `{md['name']}`",
                    "Hyphen-separated names tokenize more cleanly for search (minor).")

    if not md["homepage"]:
        add_finding(findings, "Metadata", "Info",
                    "Homepage URL not set.",
                    "`homepage` is empty.",
                    "Point homepage at docs/demo site if one exists — it renders in the About card.")

    if "social_preview_url" in repo_data and not md["social_preview_url"]:
        add_finding(findings, "Metadata", "Info",
                    "No custom social preview image.",
                    "`social_preview_url` is empty.",
                    "Upload a social preview (Settings → Social preview) to improve share/link CTR on X/Slack/Google.")

    if md["archived"]:
        add_finding(findings, "Maintenance", "Critical",
                    "Repository is archived.",
                    "`archived=true` in metadata.",
                    "State the maintenance status clearly; unarchive only if active development is resuming.")

    if pushed_days is not None and pushed_days > 365:
        add_finding(findings, "Maintenance", "Warning",
                    "No pushes in more than a year; maintenance status needs review.",
                    f"Last push {pushed_days} days ago.",
                    "Explain whether the project is stable, maintained, or discontinued; update docs if that status is unclear.")
    elif pushed_days is not None and pushed_days > 180:
        add_finding(findings, "Maintenance", "Info",
                    "No pushes in 6+ months.",
                    f"Last push {pushed_days} days ago.",
                    "A maintenance release or docs refresh signals activity.")

    if not md["license"]:
        add_finding(findings, "Trust", "Warning",
                    "No license detected.",
                    "`license` is null; many awesome-lists and adopters require one.",
                    "Document the project's actual license and retain upstream notices.")

    # ---------------- community profile checks ----------------
    if community_data:
        health = community_data.get("health_percentage")
        if isinstance(health, (int, float)) and health < 85:
            add_finding(findings, "Trust", "Warning",
                        "Community profile health is below baseline.",
                        f"GitHub community health: {health}%.",
                        "Complete missing governance files below.")
        files = community_data.get("files") or {}
        for key in ("code_of_conduct", "contributing", "issue_template"):
            if not files.get(key):
                if key == "issue_template":
                    add_finding(findings, "Trust", "Info",
                                "Issue template not identified by community profile.",
                                "community/profile `files.issue_template` is null; directory-based templates were not inspected.",
                                "Check `.github/ISSUE_TEMPLATE/` before treating a template as absent.")
                    report["limitations"].append("Community profile alone does not establish absence of directory-based issue templates.")
                    continue
                sev = "Info" if key in ("issue_template", "security_policy") else "Warning"
                add_finding(findings, "Trust", sev,
                            f"Missing community file: {key}.",
                            f"community/profile `files.{key}` is null.",
                            f"Add the `{key}` file (root or .github/).")

    report["summary"] = score_findings(findings)
    if report["status"] != "ok":
        report["summary"]["score"] = None
        report["summary"]["rating"] = "Unknown"
    report["name_tokens"] = sorted(name_tokens)
    report["description_tokens"] = list(dict.fromkeys(desc_tokens))
    return report


def print_text(report: dict):
    """Human-readable summary for standalone CLI use."""
    summary = report.get("summary", {})
    print(f"\nRepo Metadata Audit: {report.get('repo')}")
    print("=" * 60)
    print(f"Score: {summary.get('score', 'NA')}/100 ({summary.get('rating', 'Unknown')})")
    md = report.get("metadata", {})
    if md:
        print(f"Stars: {md.get('stargazers_count')} | Forks: {md.get('forks_count')} | "
              f"Language: {md.get('language')} | Pushed: {md.get('pushed_at')}")
        print(f"Topics: {', '.join(md.get('topics') or []) or '(none)'}")
    for item in report.get("limitations", []):
        print(f"Limitation: {item}")
    print("\nFindings:")
    for f in report.get("findings", []):
        print(f"- [{f['severity']}] ({f['area']}) {f['finding']}")


def main():
    parser = argparse.ArgumentParser(description="GitHub repo metadata discoverability audit.")
    parser.add_argument("repo", help="owner/repo, GitHub URL, or local clone path")
    parser.add_argument("--token", help="GitHub token override (prefer GH_TOKEN env)")
    parser.add_argument("--provider", choices=["auto", "api", "gh"], default="auto")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    try:
        repo = resolve_repo(args.repo)
        token = get_token(args.token)
        report = build_audit(repo, token=token, provider=args.provider)
    except GitHubAPIError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_text(report)


if __name__ == "__main__":
    main()
