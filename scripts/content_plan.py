#!/usr/bin/env python3
"""Map audience queries to local documentation; no network, publishing, or ranking claims."""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from readme_lint import strip_code_fences

STOP = set("a an the how to for of in on with and or is does can my your using".split())
MAX_FILES = 100
MAX_BYTES = 256_000
SOURCES = {
    "github_search": "https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories",
    "helpful_content": "https://developers.google.com/search/docs/fundamentals/creating-helpful-content",
    "platform_properties": "https://support.google.com/webmasters/answer/17148418",
}


def query_terms(query: str) -> list[str]:
    # CJK spans stay literal. Matching is deliberately lexical, not semantic proof.
    return list(dict.fromkeys(w for w in re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", query.lower())
                             if w not in STOP))


def read_documents(root: Path) -> tuple[list[dict], list[str]]:
    if not root.is_dir():
        raise ValueError("Local repository must be a directory.")
    root = root.resolve()
    documents, limitations = [], []
    candidates = list(root.glob("*.md"))
    docs = root / "docs"
    if docs.is_symlink():
        limitations.append("Skipped symlink directory: docs")
    elif docs.is_dir():
        for folder, directories, files in os.walk(docs, followlinks=False):
            directories[:] = [name for name in directories if not (Path(folder) / name).is_symlink()]
            candidates.extend(Path(folder) / name for name in files if name.endswith(".md"))
    candidates = sorted(set(candidates))
    for path in candidates:
        if len(documents) >= MAX_FILES:
            limitations.append(f"Documentation sample capped at {MAX_FILES} files.")
            break
        # Never traverse a docs symlink into another private directory.
        relative = path.relative_to(root)
        if any((root / Path(*relative.parts[:i])).is_symlink() for i in range(1, len(relative.parts) + 1)):
            limitations.append(f"Skipped symlink: {relative.as_posix()}")
            continue
        try:
            if path.stat().st_size > MAX_BYTES:
                limitations.append(f"Skipped oversized document: {relative.as_posix()}")
                continue
            markdown = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            limitations.append(f"Unreadable document: {relative.as_posix()}")
            continue
        # Ignore code blocks: a command containing a query is not an explanation.
        lines = []
        for number, line in enumerate(strip_code_fences(markdown).splitlines(), 1):
            if line.strip() and not line.startswith(("    ", "\t")):
                lines.append((number, line.strip()))
        documents.append({"path": relative.as_posix(), "lines": lines})
    return documents, limitations


def build_content_plan(root: Path, queries: list[str]) -> dict:
    if not isinstance(queries, list) or any(not isinstance(q, str) for q in queries):
        raise ValueError("Queries must be strings.")
    queries = list(dict.fromkeys(q.strip() for q in queries if q.strip()))
    if not queries or len(queries) > 8 or any(len(q) > 300 for q in queries):
        raise ValueError("Provide one to eight queries, each at most 300 characters.")
    documents, limitations = read_documents(root)
    rows = []
    for query in queries:
        terms = query_terms(query)
        matches = []
        for document in documents:
            for line, text in document["lines"]:
                matched = [term for term in terms if term in query_terms(text) or
                           (re.search(r"[\u3400-\u9fff]", term) and term in text.lower())]
                if matched:
                    matches.append({"path": document["path"], "line": line,
                                    "matched_terms": matched, "term_coverage": len(matched) / len(terms)})
        matches.sort(key=lambda item: (-item["term_coverage"], item["path"], item["line"]))
        evidence = matches[:3]
        rows.append({"query": query, "status": "lexical-evidence" if evidence else "no-lexical-evidence",
                     "evidence": evidence,
                     "editorial_action": ("Read the cited passages and check whether they answer this question; add missing steps and limits."
                                          if evidence else "Check whether this question is within the project's scope before writing an answer."),
                     "github_readme_query": query + " in:readme"})
    return {
        "schema_version": 1, "mode": "local-content-plan", "network_used": False,
        "documents_sampled": len(documents), "queries": rows,
        "surfaces": [
            {"surface": "github", "status": "draft", "action": "Use accurate name, description and topics; README searches require in:readme."},
            {"surface": "google", "status": "unobserved", "action": "Write original answers with real evidence. A public repository does not prove indexing or ranking."},
            {"surface": "owned-site", "status": "unobserved", "action": "If the user controls a Pages site or domain, separately verify a Search Console website property."},
            {"surface": "x", "status": "draft-only", "action": "Draft an experience-based article linking to the repository. X platform properties are rolling out; eligibility and Google-side data must be checked in Search Console."},
        ],
        "sources": SOURCES,
        "limitations": limitations + [
            "Literal term overlap is an editorial aid, not semantic coverage, search volume, ranking, or validation of a capability.",
            "Continuous Chinese text uses literal spans; split long questions into useful phrases for editorial matching.",
            "Only root Markdown and docs/**/*.md were sampled; no target program was run.",
            "GitHub is not listed among the currently documented Search Console platform properties; no property was verified.",
            "Nothing was published or scheduled; there is no keyword-density or word-count target.",
        ],
    }


def render_markdown(report: dict) -> str:
    lines = ["# Search intent and content plan", "", "Local editorial evidence; no search performance was measured.", ""]
    for row in report["queries"]:
        lines.extend([f"## {row['query']}", "", row["editorial_action"], ""])
        for entry in row["evidence"]:
            lines.append(f"- `{entry['path']}:{entry['line']}` — literal terms: {', '.join(entry['matched_terms'])}")
        lines.extend(["", f"GitHub README query: `{row['github_readme_query']}`", ""])
    for surface in report["surfaces"]:
        lines.append(f"- **{surface['surface']} ({surface['status']})**: {surface['action']}")
    lines.extend(["", "## Limits", ""] + [f"- {item}" for item in report["limitations"]])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="local repository; no Git remote required")
    parser.add_argument("--query", action="append", required=True, help="audience question; repeat up to eight times")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        report = build_content_plan(args.path, args.query)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render_markdown(report), end="\n")


if __name__ == "__main__":
    main()
