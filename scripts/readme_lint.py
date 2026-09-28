#!/usr/bin/env python3
"""
Module 2: README structure lint for discoverability.

Standalone usage:
  python readme_lint.py path/to/README.md --json
  python readme_lint.py --repo owner/repo            # fetch README via API

Scoring framework adapted from github_readme_lint.py in
Bhanunamikaze/Agentic-SEO-Skill (MIT License)
https://github.com/Bhanunamikaze/Agentic-SEO-Skill
— added explicit badge and screenshot/GIF checks; default intents are derived
per-repo instead of hardcoded SEO vocabulary.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys

from github_api import GitHubAPIError, fetch_json, get_token, resolve_repo

BADGE_HOSTS = ("shields.io", "badgen.net", "badge.fury.io", "img.shields.io",
               "badge.svg", "badges.gitter.im", "codecov.io", "coveralls.io",
               "codeclimate.com", "goreportcard.com", "deepsource.io", "snyk.io")


def fetch_readme_from_repo(repo: str, token: str = "", provider: str = "auto") -> str:
    """Fetch README content for a repo via the contents API (base64-decoded)."""
    payload = fetch_json(f"/repos/{repo}/readme", token=token, provider=provider, timeout=30)
    content = (payload or {}).get("content") or ""
    if not content:
        return ""
    return base64.b64decode(content.encode("utf-8"), validate=False).decode("utf-8", errors="replace")


def strip_code_fences(text: str) -> str:
    """Remove fenced code blocks so their contents don't pollute text scans."""
    text = re.sub(r"(?ms)^```[\s\S]*?^```[ \t]*$", "", text)
    return re.sub(r"(?ms)^~~~[\s\S]*?^~~~[ \t]*$", "", text)


def extract_headings(markdown: str) -> list[dict]:
    """Return ATX + setext headings with line/level/text."""
    headings = []
    lines = markdown.splitlines()
    for i, line in enumerate(lines, start=1):
        m = re.match(r"^(#{1,6})\s+(.+?)\s*$", line.strip())
        if m:
            headings.append({"line": i, "level": len(m.group(1)), "text": m.group(2).strip()})
            continue
        if i < len(lines):
            nxt = lines[i].strip()
            if line.strip() and re.match(r"^(=+|-+)\s*$", nxt):
                headings.append({"line": i, "level": 1 if nxt.startswith("=") else 2, "text": line.strip()})
    return headings


def count_code_blocks(markdown: str) -> int:
    """Count fenced + indented code blocks."""
    fenced = len(re.findall(r"(?ms)^```[\s\S]*?^```[ \t]*$", markdown))
    fenced += len(re.findall(r"(?ms)^~~~[\s\S]*?^~~~[ \t]*$", markdown))
    indented, run = 0, 0
    for line in markdown.splitlines():
        if re.match(r"^(    |\t)\S", line):
            run += 1
        else:
            if run >= 2:
                indented += 1
            run = 0
    if run >= 2:
        indented += 1
    return fenced + indented


def extract_images(markdown: str) -> list[dict]:
    """Markdown + HTML img references. An <img> without alt counts as empty-alt."""
    images = [{"alt": (m.group(1) or "").strip(), "url": (m.group(2) or "").strip()}
              for m in re.finditer(r"!\[(.*?)\]\((.*?)\)", markdown)]
    seen = {img["url"] for img in images}
    for m in re.finditer(r"<img\b[^>]*>", markdown):
        tag = m.group(0)
        src = re.search(r'\bsrc="([^"]*)"', tag)
        if not src:
            continue
        url = src.group(1).strip()
        if url in seen:
            continue
        alt = re.search(r'\balt="([^"]*)"', tag)
        images.append({"alt": (alt.group(1) if alt else "").strip(), "url": url})
        seen.add(url)
    return images


def is_badge_url(url: str) -> bool:
    """True when an image URL is a status badge rather than real content."""
    low = url.lower()
    return any(host in low for host in BADGE_HOSTS) or low.endswith(".svg") and "badge" in low


def plain_word_count(markdown: str) -> int:
    """Word count excluding code fences, images, and markdown punctuation."""
    text = strip_code_fences(markdown)
    text = re.sub(r"!\[.*?\]\(.*?\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[#>*`_~\-]", " ", text)
    return len(re.findall(r"\b[\w']+\b", text.lower()))


def detect_heading_jumps(headings: list[dict]) -> list[dict]:
    """Heading level skips (e.g. H1 -> H3) that hurt structured extraction."""
    jumps, prev = [], None
    for h in headings:
        if prev is not None and h["level"] > prev + 1:
            jumps.append({"line": h["line"], "from": prev, "to": h["level"], "text": h["text"]})
        prev = h["level"]
    return jumps


def add_finding(findings: list, category: str, severity: str, finding: str, evidence: str, fix: str):
    """Append one lint finding."""
    findings.append({"category": category, "severity": severity,
                     "finding": finding, "evidence": evidence, "fix": fix})


def score_report(markdown: str, intents: list[str] | None = None) -> dict:
    """Score README across 7 categories, total 100. Returns summary + findings."""
    intents = [t.lower() for t in (intents or [])]
    # extract headings from fence-stripped text so bash/python comments like
    # `# full report` inside code blocks don't count as H1s
    headings = extract_headings(strip_code_fences(markdown))
    heading_text = [h["text"].strip().lower() for h in headings]
    images = extract_images(markdown)
    badges = [img for img in images if is_badge_url(img["url"])]
    content_images = [img for img in images if not is_badge_url(img["url"])]
    gifs = [img for img in content_images if img["url"].lower().split("?")[0].endswith(".gif")]
    words = plain_word_count(markdown)
    findings = []

    # Opening clarity (20): what-is-it in the first lines + intent terms
    opening_score = 20
    opening_lines = [ln for ln in strip_code_fences(markdown).strip().splitlines()[:12] if ln.strip()]
    opening_text = " ".join(opening_lines).lower()
    if intents:
        matched = [t for t in intents if t in opening_text]
        if not matched:
            opening_score -= 10
            add_finding(findings, "Opening Clarity", "Warning",
                        "Opening lines contain none of the repo's functional keywords.",
                        f"Checked terms: {', '.join(intents[:8])}",
                        "State what the project IS and what problem it solves in the first 3-5 lines, using the words users search for.")
    if len(opening_lines) < 2 or words < 200:
        opening_score -= 5
        add_finding(findings, "Opening Clarity", "Info",
                    "README opening is sparse.",
                    f"Word count: {words}.",
                    "Add a concise value-proposition paragraph under the title.")
    opening_score = max(0, opening_score)

    # Information architecture (15): single H1, no level jumps
    ia_score = 15
    h1_count = sum(1 for h in headings if h["level"] == 1)
    jumps = detect_heading_jumps(headings)
    if h1_count == 0:
        ia_score -= 10
        add_finding(findings, "Information Architecture", "Warning",
                    "No H1 heading found.",
                    "Google/GitHub extract the H1 as the page title.",
                    "Start the README with a single `# Title`.")
    elif h1_count > 1:
        ia_score -= 8
        add_finding(findings, "Information Architecture", "Warning",
                    f"{h1_count} H1 headings detected — should be exactly one.",
                    "Multiple H1s dilute the page title signal.",
                    "Demote extra H1s to H2.")
    if jumps:
        ia_score -= 5
        add_finding(findings, "Information Architecture", "Warning",
                    "Heading hierarchy skips levels.",
                    f"{len(jumps)} jump(s), e.g. line {jumps[0]['line']}: H{jumps[0]['from']}→H{jumps[0]['to']}.",
                    "Use contiguous H1→H2→H3 nesting; search engines use it to build structured outlines.")
    ia_score = max(0, ia_score)

    # Install + quickstart (20)
    install_score = 20
    install_markers = ("install", "quick start", "quickstart", "getting started",
                       "setup", "usage", "快速开始", "安装", "使用")
    has_install = any(any(m in t for m in install_markers) for t in heading_text)
    code_blocks = count_code_blocks(markdown)
    if not has_install:
        install_score -= 12
        add_finding(findings, "Install + Quickstart", "Critical",
                    "No installation/quickstart section heading.",
                    f"Headings: {', '.join(h['text'] for h in headings[:12]) or '(none)'}",
                    "Add `## Quickstart` (or 安装/快速开始) with copy-pasteable commands.")
    if code_blocks == 0:
        install_score -= 8
        add_finding(findings, "Install + Quickstart", "Warning",
                    "No code blocks detected.",
                    "Zero fenced/indented code blocks.",
                    "Include runnable install + minimal usage commands in fenced blocks.")
    install_score = max(0, install_score)

    # Proof & visuals (15): screenshots / demo GIF
    proof_score = 15
    if not content_images:
        proof_score -= 9
        add_finding(findings, "Proof & Visuals", "Warning",
                    "No screenshots or demo images.",
                    "README has no content images (badges don't count).",
                    "Add at least one screenshot or demo GIF showing the product in action — this strongly lifts conversion and rich-result eligibility.")
    elif not gifs:
        proof_score -= 4
        add_finding(findings, "Proof & Visuals", "Info",
                    "Static screenshots present but no demo GIF/video.",
                    f"{len(content_images)} content image(s), 0 GIFs.",
                    "A short demo GIF (or asciinema/YouTube embed) communicates value faster than text.")
    proof_markers = ("example", "screenshot", "demo", "output", "preview", "示例", "演示", "截图")
    if not any(any(m in t for m in proof_markers) for t in heading_text) and content_images:
        proof_score -= 2
        add_finding(findings, "Proof & Visuals", "Info",
                    "Demo images exist but sit under no demo/screenshot section.",
                    "No demo-like heading found.",
                    "Group visuals under `## Demo` / `## Screenshots` for scannability.")
    proof_score = max(0, proof_score)

    # Badges (10): stars / CI / license coverage
    badge_score = 10
    if not badges:
        badge_score -= 6
        add_finding(findings, "Badges", "Warning",
                    "No status badges found.",
                    "No shields.io/badgen/workflow-badge images detected.",
                    "Add build-status + license badges at the top; they signal maintenance at a glance.")
    else:
        badge_blob = " ".join(b["url"].lower() for b in badges)
        has_ci = any(k in badge_blob for k in ("workflow", "actions", "ci", "build", "test"))
        has_license = "license" in badge_blob
        if not has_ci:
            badge_score -= 2
            add_finding(findings, "Badges", "Info",
                        "No CI/build badge.",
                        f"Badge URLs: {', '.join(b['url'][:60] for b in badges[:5])}",
                        "Add a GitHub Actions workflow badge to show the build is green.")
        if not has_license:
            badge_score -= 2
            add_finding(findings, "Badges", "Info",
                        "No license badge.",
                        "License is not surfaced in the badge row.",
                        "Add a license badge (shields.io) next to the CI badge.")
    badge_score = max(0, badge_score)

    # CTA + community (10)
    cta_score = 10
    cta_markers = ("contribut", "issue", "pull request", "support", "discussion",
                   "feedback", "roadmap", "贡献", "反馈")
    hits = sum(1 for m in cta_markers if m in markdown.lower())
    if hits < 2:
        cta_score -= 6
        add_finding(findings, "CTA + Community", "Warning",
                    "Weak contribution/support CTAs.",
                    f"{hits} CTA marker(s) found.",
                    "Add a `## Contributing` section and invite issues/discussions.")
    cta_score = max(0, cta_score)

    # Readability & accessibility (10)
    read_score = 10
    missing_alt = [img for img in content_images if not img["alt"]]
    if missing_alt:
        read_score -= 5
        add_finding(findings, "Readability", "Warning",
                    "Images missing alt text.",
                    f"{len(missing_alt)} content image(s) with empty alt.",
                    "Describe each screenshot in its alt text — it's indexed by image search.")
    if len(headings) < 4:
        read_score -= 3
        add_finding(findings, "Readability", "Info",
                    "Shallow sectioning.",
                    f"Only {len(headings)} heading(s).",
                    "Break content into descriptive H2/H3 sections.")
    read_score = max(0, read_score)

    category_scores = {
        "opening_clarity": opening_score,
        "information_architecture": ia_score,
        "install_quickstart": install_score,
        "proof_visuals": proof_score,
        "badges": badge_score,
        "cta_community": cta_score,
        "readability": read_score,
    }
    total = sum(category_scores.values())
    rating = ("Excellent" if total >= 90 else "Good" if total >= 70 else
              "Needs Improvement" if total >= 50 else "Poor" if total >= 30 else "Critical")

    return {
        "summary": {"score": total, "rating": rating},
        "category_scores": category_scores,
        "metrics": {
            "word_count": words,
            "heading_count": len(headings),
            "h1_count": h1_count,
            "code_block_count": code_blocks,
            "content_image_count": len(content_images),
            "gif_count": len(gifs),
            "badge_count": len(badges),
            "images_missing_alt": len(missing_alt),
            "first_heading_outline": [f"H{h['level']}: {h['text']}" for h in headings[:15]],
        },
        "findings": findings,
    }


def print_text(report: dict):
    """Human-readable summary for standalone CLI use."""
    summary = report.get("summary", {})
    print(f"\nREADME Lint: {report.get('source', '')}")
    print("=" * 60)
    print(f"Score: {summary.get('score', 'NA')}/100 ({summary.get('rating', 'Unknown')})")
    for cat, val in report.get("category_scores", {}).items():
        print(f"  {cat}: {val}")
    print("\nFindings:")
    for f in report.get("findings", []):
        print(f"- [{f['severity']}] ({f['category']}) {f['finding']}")


def main():
    parser = argparse.ArgumentParser(description="README structure lint for GitHub discoverability.")
    parser.add_argument("readme", nargs="?", default="", help="Path to README file (optional if --repo given)")
    parser.add_argument("--repo", help="owner/repo for remote README fetch")
    parser.add_argument("--token", help="GitHub token override (prefer GH_TOKEN env)")
    parser.add_argument("--provider", choices=["auto", "api", "gh"], default="auto")
    parser.add_argument("--intent", action="append", default=[], help="Intent term (repeatable)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    markdown, source = "", args.readme or args.repo or "(none)"
    if args.readme:
        try:
            with open(args.readme, encoding="utf-8") as f:
                markdown = f.read()
        except OSError as exc:
            print(f"Error reading {args.readme}: {exc}", file=sys.stderr)
            sys.exit(2)
    if not markdown.strip() and args.repo:
        try:
            token = get_token(args.token)
            markdown = fetch_readme_from_repo(resolve_repo(args.repo), token=token, provider=args.provider)
            source = f"github:{resolve_repo(args.repo)}"
        except GitHubAPIError as exc:
            print(f"Error fetching remote README: {exc}", file=sys.stderr)
            sys.exit(2)
    if not markdown.strip():
        print("Error: no README content (pass a file path or --repo).", file=sys.stderr)
        sys.exit(2)

    report = {"source": source, "intents": args.intent, **score_report(markdown, args.intent)}
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_text(report)


if __name__ == "__main__":
    main()
