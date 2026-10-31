#!/usr/bin/env python3
"""Run real report code against offline fixtures in a fresh Python process.

Each invocation imports only the selected skill root. This measures script
regressions, not agent quality, live GitHub ranking, traffic, or SEO outcomes.
Reports live in output-dir/outputs; grading and timing live in output-dir.
"""

from __future__ import annotations

import argparse
import base64
from contextlib import ExitStack
import copy
import importlib
import inspect
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

REPO = "example/csv-json"
SUMMARY = "将 CSV 文件转换为 JSON 的 Python 命令行工具。"
TOPICS = ["csv", "json", "csv-parser", "csv-to-json", "data-conversion", "command-line",
          "data-processing", "etl", "text-processing", "developer-tools", "file-converter", "offline-tool"]
README = """# CSV JSON

将 CSV 文件转换为 JSON 的 Python 命令行工具。

## 快速开始

```bash
python3 convert.py examples/input.csv
```

## 示例输入

```csv
name,age
Ada,37
```

## 预期输出

```json
[{"name": "Ada", "age": "37"}]
```

## 反馈与贡献

通过 Issues 报告问题，欢迎贡献 Pull Request。
"""
ASSERTIONS = {
    1: ["保留全部 12 个已有有效 topics，不因采样范围或拥挤而删除。",
        "未采样的后 4 个 topics 仍保留在建议列表中。",
        "ai 候选标记为待审核，且未自动加入建议 topics。",
        "ai 共现支持计为 2 个独立仓库，而非重复关键词命中次数。"],
    2: ["README 403 显示为 unavailable，得分为 null，不能记作 0 分。",
        "README 数据缺失时总体资料分为 null。",
        "Awesome 搜索 403 显示为 unavailable，机会得分未知。",
        "Markdown 报告中同时展示 README 和 Awesome 搜索的 403 错误证据。"],
    3: ["中文 CLI 不因缺少图片或 badges 收到 Critical/Warning 视觉要求。",
        "中文快速开始和示例输出被识别，安装与证明类别未因此扣分。",
        "宣传简介和 README 开场使用实际项目简介，没有占位符或假造 demo 资源。",
        "报告明确文档中的命令未执行，未声称已验证运行成功。"],
}
MARKER = ("Collector/script 离线回归对照：未访问真实 GitHub，example/csv-json 不是实际仓库观测；"
          "未运行模型，未测 skill 触发或最终 LLM 改写，未证明曝光变化。"
          "旧 SKILL.md 已要求 LLM 清理占位符；旧 CLI 的原始草稿问题不能说明旧 skill 的最终 LLM 输出必然失败。")


def content(text: str, repo: str = REPO, path: str = "README.md") -> dict:
    return {"encoding": "base64", "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
            "html_url": f"https://github.com/{repo}/blob/main/{path}", "path": path, "truncated": False}


def metadata(scenario: int) -> dict:
    return {"name": "csv-json", "full_name": REPO, "description": SUMMARY,
            "topics": TOPICS if scenario == 1 else ["csv", "json"], "language": "Python",
            "default_branch": "main", "license": {"spdx_id": "MIT"}, "stargazers_count": 10,
            "forks_count": 2, "subscribers_count": 1, "open_issues_count": 0,
            "pushed_at": "2026-09-30T00:00:00Z", "created_at": "2026-09-01T00:00:00Z",
            "html_url": f"https://github.com/{REPO}", "homepage": "", "archived": False,
            "fork": False, "has_pages": False}


def profile(repo: str) -> dict:
    files = {name: {"path": path, "html_url": f"https://github.com/{repo}/blob/main/{path}"}
             for name, path in (("readme", "README.md"), ("contributing", "CONTRIBUTING.md"),
                                ("code_of_conduct", "CODE_OF_CONDUCT.md"),
                                ("issue_template", ".github/ISSUE_TEMPLATE/bug.md"),
                                ("security_policy", "SECURITY.md"), ("license", "LICENSE"))}
    return {"health_percentage": 100, "files": files}


def make_fixture(scenario: int, api_error):
    """Return a fixture API: unknown endpoints fail instead of reaching the network."""
    calls, unrecognized = [], []
    listing_repo = "maintainer/awesome-csv"
    listing = {"name": "awesome-csv", "full_name": listing_repo,
               "description": "CSV JSON conversion command-line data-processing tools",
               "topics": ["csv", "json"], "stargazers_count": 800,
               "pushed_at": "2026-09-30T00:00:00Z", "default_branch": "main",
               "open_issues_count": 1, "html_url": f"https://github.com/{listing_repo}"}
    peers = [{"name": name.split("/")[1], "full_name": name, "topics": ["csv", "json", "ai"],
              "stargazers_count": stars, "description": "CSV and JSON converters",
              "fork": False, "archived": False, "pushed_at": "2026-09-30T00:00:00Z",
              "html_url": f"https://github.com/{name}"}
             for name, stars in (("peer/one", 100), ("peer/two", 200))]
    def fake(path: str, **kwargs):
        params = kwargs.get("params") or {}
        calls.append({"path": path, "params": copy.deepcopy(params)})
        if kwargs.get("method", "GET").upper() != "GET":
            unrecognized.append({"path": path, "method": kwargs["method"]})
            raise AssertionError("Offline regression fixtures only support read-only GET requests")
        if path == f"/repos/{REPO}":
            return copy.deepcopy(metadata(scenario))
        if path == f"/repos/{REPO}/community/profile":
            return profile(REPO)
        if path == f"/repos/{REPO}/readme":
            if scenario == 2:
                raise api_error("README 403: offline fixture permission denied", status=403)
            return content(README)
        if path == "/search/repositories":
            query = params.get("q")
            if not isinstance(query, str):
                unrecognized.append({"path": path, "params": params})
                raise AssertionError("Offline search requires a query string")
            if query.startswith("awesome"):
                if scenario == 2:
                    raise api_error("Awesome search 403: offline fixture permission denied", status=403)
                items = [listing]
            elif query.startswith("topic:"):
                items = [peers[0], metadata(scenario), peers[1]]
            elif params.get("sort") == "stars":
                # All keyword searches return the same two independent peers.
                items = peers
            else:
                items = [peers[0], metadata(scenario), peers[1]]
            return {"total_count": len(items), "incomplete_results": False,
                    "items": copy.deepcopy(items[:params.get("per_page", 100)])}
        if path == f"/repos/{listing_repo}/community/profile":
            return profile(listing_repo)
        if path in (f"/repos/{listing_repo}/readme", f"/repos/{listing_repo}/contents/README.md"):
            return content("# Awesome CSV\n\n## CSV and JSON conversion\n\n- [Existing tool](https://github.com/peer/existing) — Converts CSV.\n", listing_repo)
        if path == f"/repos/{listing_repo}/contents/CONTRIBUTING.md":
            return content("# Contributing\n\nAdd a useful CSV conversion tool with a short description.\nUse one Markdown entry and place it in the CSV and JSON conversion section.\n", listing_repo, "CONTRIBUTING.md")
        unrecognized.append({"path": path, "params": params})
        raise AssertionError(f"Unrecognized offline endpoint: {path}")
    return fake, calls, unrecognized


def grade(scenario: int, report: dict, rendered: str) -> dict:
    expectations = []
    def record(index, passed, evidence):
        expectations.append({"text": ASSERTIONS[scenario][index], "passed": bool(passed), "evidence": evidence})
    suggestions = report.get("suggestions", {})
    if scenario == 1:
        recommended = suggestions.get("topics", [])
        candidates = report.get("topics", {}).get("candidate_topics", {}).get("candidates", [])
        candidate = next((row for row in candidates if row.get("topic") == "ai"), {})
        record(0, recommended == TOPICS, "suggestions.topics=" + json.dumps(recommended, ensure_ascii=False))
        record(1, all(topic in recommended for topic in TOPICS[8:]), "Unsampled topics=" + json.dumps(TOPICS[8:]) + "; recommended=" + json.dumps(recommended))
        record(2, candidate.get("requires_review") is True and "ai" not in recommended,
               "ai candidate=" + json.dumps(candidate, ensure_ascii=False) + "; auto-added=" + str("ai" in recommended))
        record(3, candidate.get("comparable_count") == 2, "ai comparable_count=" + str(candidate.get("comparable_count")))
    elif scenario == 2:
        readme = report.get("readme", {})
        readme_score = readme.get("summary", {}).get("score")
        awesome = report.get("awesome", {})
        record(0, readme.get("status") == "unavailable" and readme_score is None,
               f"readme.status={readme.get('status')}; readme.score={readme_score}")
        record(1, report.get("overall", {}).get("score") is None,
               "overall.score=" + str(report.get("overall", {}).get("score")))
        record(2, awesome.get("status") == "unavailable" and awesome.get("score") is None,
               f"awesome.status={awesome.get('status')}; awesome.score={awesome.get('score')}")
        errors = ["README 403: offline fixture permission denied", "Awesome search 403: offline fixture permission denied"]
        record(3, all(error in rendered for error in errors),
               "; ".join(error + " visible=" + str(error in rendered) for error in errors))
    else:
        readme = report.get("readme", {})
        visual_issues = [row for row in readme.get("findings", [])
                         if row.get("category") in ("Proof & Visuals", "Badges") and row.get("severity") in ("Critical", "Warning")]
        scores = readme.get("category_scores", {})
        record(0, not visual_issues, "Critical/Warning visual findings=" + json.dumps(visual_issues, ensure_ascii=False))
        record(1, scores.get("install_quickstart") == 20 and scores.get("proof_visuals") == 15,
               "category_scores=" + json.dumps(scores, ensure_ascii=False))
        drafts = suggestions.get("description", "") + "\n" + suggestions.get("readme_opening", "")
        record(2, SUMMARY in suggestions.get("description", "") and SUMMARY in suggestions.get("readme_opening", "")
               and "[" not in drafts and "demo.gif" not in drafts,
               "Raw collector description and README opening (no model polishing was run; the original SKILL.md already requests that later step)=" + drafts)
        metric = readme.get("metrics", {}).get("commands_executed")
        limitation = " ".join(readme.get("limitations", []))
        record(3, metric is False and "commands were not executed" in limitation,
               f"commands_executed={metric}; limitations={limitation}")
    passed = sum(row["passed"] for row in expectations)
    return {"evaluation_mode": "offline-fixture-regression", "model_run": False,
            "scope_notice": MARKER,
            "expectations": expectations,
            "summary": {"passed": passed, "failed": len(expectations) - passed,
                        "total": len(expectations), "pass_rate": passed / len(expectations)}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", required=True, type=Path)
    parser.add_argument("--scenario", required=True, type=int, choices=(1, 2, 3))
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    scripts = (args.skill_root / "scripts").resolve()
    if not (scripts / "analyze.py").is_file():
        parser.error("--skill-root must contain scripts/analyze.py")
    sys.path.insert(0, str(scripts))
    modules = [importlib.import_module(name) for name in ("analyze", "repo_audit", "readme_lint", "topic_competition", "awesome_match", "github_api")]
    for name in ("search_benchmark", "traffic_snapshot", "project_context"):
        if (scripts / f"{name}.py").is_file():
            modules.append(importlib.import_module(name))
    if any(Path(module.__file__).resolve().parent != scripts for module in modules):
        raise AssertionError("A module was loaded from outside the selected skill root")
    analyze, *_, github_api = modules[:6]
    fake, calls, unrecognized = make_fixture(args.scenario, github_api.GitHubAPIError)
    with ExitStack() as stack:
        for target in ("socket.create_connection", "socket.socket.connect", "urllib.request.urlopen", "subprocess.Popen"):
            stack.enter_context(patch(target, side_effect=AssertionError("Offline fixtures forbid real I/O: " + target)))
        stack.enter_context(patch("time.sleep"))
        for module in modules:
            if hasattr(module, "fetch_json"):
                stack.enter_context(patch.object(module, "fetch_json", side_effect=fake))
            if hasattr(module, "auth_context"):
                stack.enter_context(patch.object(module, "auth_context", return_value={"mode": "offline-simulated", "token_present": False, "gh_available": False, "gh_authenticated": False}))
        extra = {"project_type": "cli"} if "project_type" in inspect.signature(analyze.build_report).parameters else {}
        report = analyze.build_report(REPO, "offline-fixture-placeholder", "api", 8, 15, **extra)
        rendered = analyze.render_markdown(report)
    if unrecognized:
        raise AssertionError("Unknown endpoints were swallowed by report code: " + json.dumps(unrecognized))
    rendered = "> **" + MARKER + "**\n\n" + rendered
    report["_evaluation"] = {"simulated": True, "model_run": False, "scenario": args.scenario,
                             "fixture_repo": REPO, "skill_root": str(args.skill_root.resolve()),
                             "notice": MARKER, "api_calls": calls}
    grading = grade(args.scenario, report, rendered)
    elapsed = time.perf_counter() - started
    timing = {"total_tokens": 0, "duration_ms": round(elapsed * 1000, 3),
              "total_duration_seconds": elapsed, "model_run": False,
              "evaluation_mode": "offline-fixture-regression",
              "note": "Actual Python pipeline duration; no model was run, so token usage is zero. Not agent-performance timing."}
    destination = args.output_dir.resolve()
    outputs = destination / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / "report.md").write_text(rendered + "\n", encoding="utf-8")
    (outputs / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (destination / "grading.json").write_text(json.dumps(grading, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (destination / "timing.json").write_text(json.dumps(timing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"scenario": args.scenario, "skill_root": str(args.skill_root.resolve()),
                      "output_dir": str(destination), "grading": grading["summary"], "duration_ms": timing["duration_ms"],
                      "notice": MARKER}, ensure_ascii=False))


if __name__ == "__main__":
    main()
