#!/usr/bin/env python3
"""Read-only repository readiness, search observations, and promotion drafts."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from github_api import GitHubAPIError, auth_context, get_token, resolve_repo
from repo_audit import LANGUAGE_TOPICS, build_audit, tokenize
from readme_lint import fetch_readme_from_repo, score_report
from topic_competition import analyze_topics, structure_score
from awesome_match import find_awesome_lists
from search_benchmark import benchmark_queries, compare_benchmarks
from traffic_snapshot import collect_traffic
from project_context import PROJECT_TYPES, collect_context, load_context, promotion_plan
from local_audit import collect_local_evidence

# Readiness rubric v2. Rankings, opportunities, and traffic are observations.
WEIGHTS = {"metadata": 0.35, "readme": 0.40, "topic_structure": 0.25}


def overall_rating(score: float) -> str:
    return ("Excellent" if score >= 90 else "Good" if score >= 70 else
            "Needs Improvement" if score >= 50 else "Poor" if score >= 30 else "Critical")


def search_position(repo: str, queries: list[str], token: str, provider: str) -> list[dict]:
    """Compatibility wrapper; positions are API samples, not page rankings."""
    return benchmark_queries(repo, queries, token, provider)


def suggest_description(meta: dict, keywords: list[str], context: dict | None = None) -> str:
    """Copy observed summary text; leave unsupported claims out."""
    return ((context or {}).get("summary") or meta.get("description") or "").strip()


def suggest_topics(current: list[str], topic_report: dict) -> tuple[list[str], list[str]]:
    """Preserve original valid topics; mined candidates require semantic review."""
    kept, invalid = [], []
    for topic in current:
        if not isinstance(topic, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,49}", topic):
            invalid.append(str(topic))
            continue
        if topic not in kept:
            kept.append(topic)
    notes = ["保留原有有效标签；拥挤、未分析或查询失败均不构成删除理由。"]
    if invalid:
        notes.append("语法不合规的标签待修正: " + ", ".join(invalid))
    if len(kept) > 20:
        notes.append("超过 GitHub 20 个标签上限；请按项目事实审核裁减。")
    candidates = topic_report.get("candidate_topics", {}).get("candidates", [])
    if candidates:
        notes.append("共现候选待核实项目能力；未自动加入推荐列表。")
    return kept[:20], notes


def readme_opening_draft(meta: dict, keywords: list[str], context: dict | None = None) -> str:
    name = meta.get("name") or "project"
    summary = suggest_description(meta, keywords, context)
    return f"# {name}\n" + (f"\n{summary}\n" if summary else "")


def derive_queries(meta: dict, context: dict) -> list[str]:
    """Evidence-derived starting points, explicitly adjustable by the user."""
    words = tokenize(context.get("summary", ""))
    queries = [" ".join(words[:3])] if words else []
    queries += [f"topic:{t}" for t in meta.get("topics", []) if t not in LANGUAGE_TOPICS][:2]
    name = meta.get("name", "").replace("-", " ").replace("_", " ")
    if name:
        queries.append(name)
    return list(dict.fromkeys(q for q in queries if q.strip()))[:4]


def skipped(reason: str, **fields) -> dict:
    return {"status": "unavailable", "coverage": {}, "limitations": [reason], **fields}


def build_report(repo: str, token: str, provider: str, max_topics: int, top_n: int,
                 *, queries: list[str] | None = None, competitors: list[str] | None = None,
                 context: dict | None = None, project_type: str = "auto",
                 baseline: dict | None = None, traffic_dir: str | None = None,
                 local_path: str | None = None, offline: bool = False) -> dict:
    if offline and not local_path:
        raise ValueError("Offline audit requires a local directory.")
    if offline and (traffic_dir or baseline):
        raise ValueError("Offline audits cannot collect traffic or compare remote search baselines.")
    explicit_queries = queries or (context or {}).get("queries", [])
    if not isinstance(explicit_queries, list) or any(not isinstance(q, str) for q in explicit_queries):
        raise ValueError("Queries must be a list of strings.")
    if len(set(q.strip() for q in explicit_queries if q.strip())) > 8:
        raise ValueError("Use at most eight distinct benchmark queries.")
    if baseline is not None:
        if not isinstance(baseline, dict) or str(baseline.get("repo", "")).lower() != repo.lower():
            raise ValueError("Baseline must be a JSON report for the same repository.")
        if baseline.get("schema_version") != 2:
            raise ValueError("Baseline uses a different report schema; generate a v2 JSON baseline first.")
        rows = baseline.get("search_benchmark", [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("Baseline search_benchmark must be a list of observations.")
    limitations = []
    local = collect_local_evidence(local_path, repo) if offline else None
    audit = local["audit"] if local else build_audit(repo, token=token, provider=provider)
    meta = audit.get("metadata", {})
    metadata_observed = bool(meta) and not offline
    markdown = ""
    readme_report = skipped("README unavailable because repository metadata could not be fetched.",
                            summary={"score": None, "rating": "Unknown"}, findings=[])
    if local:
        observation = local["files"]["readme"]
        if observation["status"] != "unavailable":
            markdown = local["markdown"] or ""
            readme_report = score_report(markdown, project_type=project_type)
            if not markdown.strip():
                readme_report["summary"] = {"score": 0, "rating": "Critical"}
                readme_report["limitations"].append("Local README was observed missing or empty.")
        else:
            readme_report = skipped("Local README could not be read: " + observation["reason"],
                                    summary={"score": None, "rating": "Unknown"}, findings=[])
    elif metadata_observed:
        try:
            markdown = fetch_readme_from_repo(repo, token=token, provider=provider)
            # A successful empty response confirms empty content. HTTP errors do not.
            readme_report = score_report(markdown, project_type=project_type)
            if not markdown.strip():
                readme_report["summary"] = {"score": 0, "rating": "Critical"}
                readme_report["limitations"].append("README content was observed to be empty.")
        except GitHubAPIError as exc:
            readme_report = skipped(f"README fetch failed: {exc}", summary={"score": None, "rating": "Unknown"}, findings=[])
    draft_meta = dict(meta, full_name="" if offline else repo, name=meta.get("name") or repo.split("/")[-1])
    project = collect_context(draft_meta, markdown, context, local_path, project_type)
    keywords = list(dict.fromkeys(tokenize(project["summary"]) +
                                  [t for t in meta.get("topics", []) if t not in LANGUAGE_TOPICS]))
    if readme_report.get("status") == "ok" and markdown.strip():
        readme_report = score_report(markdown, intents=keywords[:10], project_type=project["project_type"])
    if local:
        readme_report["source"] = {"kind": "local-file", "path": local["files"]["readme"]["path"]}
    topics_observed = metadata_observed and audit.get("coverage", {}).get("topics", "ok") == "ok"
    q_score, q_notes = structure_score(meta.get("topics", [])) if topics_observed else (None, [])
    reason = ("Offline audit: GitHub metadata, topics, search, and list checks were not requested." if offline else
              "Repository metadata unavailable; search modules were not run." if not metadata_observed else
              "No token: basic metadata/README checks only; authenticate to enable Search API modules.")
    if metadata_observed and token:
        topics = analyze_topics(repo, meta.get("topics", []), int(meta.get("stargazers_count", 0)),
                                keywords[:4], token=token, provider=provider, max_topics=max_topics,
                                top_n=top_n, evidence_text=markdown + "\n" + project["summary"])
        awesome = find_awesome_lists(repo=repo, topics=meta.get("topics", []), language=meta.get("language", ""),
                                     name=meta.get("name", ""), description=meta.get("description", ""), token=token, provider=provider)
    else:
        topics = skipped(reason, per_topic=[], candidate_topics={"candidates": []}, ranking_score=None,
                         structure_score=q_score, structure_notes=q_notes, our_stars=meta.get("stargazers_count"))
        awesome = skipped(reason, lists=[], terms_used=[], total_matches=None, score=None)
    selected_queries = list(dict.fromkeys(q.strip() for q in (queries or project["queries"] or derive_queries(meta, project)) if q.strip()))
    if len(selected_queries) > 8:
        raise ValueError("Use at most eight distinct benchmark queries.")
    bench = benchmark_queries(repo, selected_queries, token, provider, competitors=competitors) if metadata_observed and token else []
    for row in bench:
        if row.get("error"):
            limitations.append(f"Search query {row['query']}: {row['error']}")
    comparison = None
    if baseline is not None:
        if not isinstance(baseline, dict) or str(baseline.get("repo", "")).lower() != repo.lower():
            raise ValueError("Baseline must be a JSON report for the same repository.")
        if baseline.get("schema_version") != 2:
            raise ValueError("Baseline uses a different report schema; generate a v2 JSON baseline first.")
        comparison = compare_benchmarks(bench, baseline.get("search_benchmark", []))
        limitations.extend(comparison["limitations"])
    traffic = collect_traffic(repo, token, provider, archive_dir=traffic_dir) if traffic_dir else None
    scores = {"metadata": audit.get("summary", {}).get("score"),
              "readme": readme_report.get("summary", {}).get("score"), "topic_structure": q_score}
    evaluated_weight = sum(WEIGHTS[k] for k, score in scores.items() if score is not None)
    total = round(sum(scores[k] * WEIGHTS[k] for k in WEIGHTS)) if all(v is not None for v in scores.values()) else None
    recommended, notes = suggest_topics(meta.get("topics", []), topics)
    for module in (audit, readme_report, topics, awesome, traffic or {}):
        limitations.extend(module.get("limitations", []))
    limitations.extend(project["limitations"])
    return {"schema_version": 2, "rubric_version": "readiness-v2", "repo": repo,
            "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "input_source": "local-offline" if offline else "github-api",
            "local_evidence": {"files": local["files"]} if local else None,
            "auth_context": {"mode": "offline", "token_present": False, "gh_available": None, "gh_authenticated": None} if offline else auth_context(token=token), "overall": {"score": total,
                "rating": overall_rating(total) if total is not None else "Unknown", "weights": WEIGHTS,
                "evaluated_weight": round(evaluated_weight, 3), "status": "ok" if total is not None else "partial"},
            "module_scores": scores, "metadata": meta, "audit": audit, "readme": readme_report,
            "project_context": project, "topics": topics, "search_benchmark": bench,
            "benchmark_queries": selected_queries, "query_source": "provided" if queries or project["queries"] else "heuristic",
            "comparison": comparison, "awesome": awesome, "traffic": traffic,
            "suggestions": {"description": suggest_description(draft_meta, keywords, project), "topics": recommended,
                            "topic_notes": notes, "readme_opening": readme_opening_draft(draft_meta, keywords, project)},
            "promotion": promotion_plan(draft_meta, project), "limitations": list(dict.fromkeys(limitations))}


def priority_actions(report: dict) -> list[dict]:
    """Prioritize observed gaps; do not predict score or traffic increases."""
    actions, seen = [], set()
    for module in (report["readme"], report["audit"]):
        if module.get("status") == "unavailable":
            continue
        for finding in module.get("findings", []):
            if finding.get("severity") not in ("Critical", "Warning"):
                continue
            category = finding.get("category") or finding.get("area")
            if category in seen:
                continue
            seen.add(category)
            actions.append({"text": finding["fix"], "evidence": finding["evidence"],
                            "severity": finding["severity"], "confidence": finding.get("confidence", "Confirmed")})
    return sorted(actions, key=lambda a: 0 if a["severity"] == "Critical" else 1)[:5]


def cell(value) -> str:
    return "未知" if value is None else str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict) -> str:
    overall = report["overall"]
    out = [f"# GitHub 可发现性与推广报告 — {report['repo']}", "",
           f"> 生成时间: {report['generated_at_utc']} | 评分口径: readiness-v2", "",
           "## 资料完整度", ""]
    if report.get("input_source") == "local-offline":
        out += ["本报告只检查本地文件；未联网、未读取凭据，GitHub About、Topics、搜索与流量均未知。", "",
                "| 本地材料 | 状态 | 相对路径 |", "|---|---|---|"]
        for key, observation in report["local_evidence"]["files"].items():
            out.append(f"| {key} | {observation['status']} | {cell(observation['path'])} |")
        out.append("")
    if overall["score"] is None:
        out.append(f"**未完整评估**；已评估权重 {overall['evaluated_weight']:.0%}，未知项未计为零分。")
    else:
        out.append(f"**{overall['score']}/100 — {overall['rating']}**（自定义结构与资料启发式，不是排名或增长指标）")
    out += ["", "| 模块 | 得分 | 权重 |", "|---|---|---|"]
    names = {"metadata": "元数据与社区资料", "readme": "README 结构", "topic_structure": "Topics 语法与结构覆盖"}
    for key, weight in WEIGHTS.items():
        out.append(f"| {names[key]} | {cell(report['module_scores'][key])} | {weight:.0%} |")
    out += ["", "搜索样本、投稿机会、流量均单独展示；与旧版总分不可直接比较。", "", "## 优先行动", ""]
    actions = priority_actions(report)
    for index, action in enumerate(actions, 1):
        out += [f"{index}. {action['text']}", f"   依据: {action['evidence']}；事实置信度: {action['confidence']}。"]
    if not actions:
        out.append("现有可获取数据未产生优先修复项；请同时查看数据限制。")
    context = report["project_context"]
    out += ["", "## 项目定位与文案", "", f"- 类型: {context['project_type']}（{context['project_type_source']}）",
            f"- 简介来源: {context['summary_source']}"]
    for key in ("audience", "problem", "differentiator", "goal"):
        if context.get(key):
            out.append(f"- {key}: {context[key]}（用户提供）")
    for fact in context.get("facts", []):
        out.append(f"- 仓库依据: {fact['text']} — `{fact['source']}`；命令未执行。")
    out += ["", "### About 草稿", "", "````text", report["suggestions"]["description"] or "暂无足够事实生成简介。", "````",
            "", "### README 首屏草稿", "", "````markdown", report["suggestions"]["readme_opening"].rstrip(), "````",
            "", "## 观察到的问题", ""]
    findings = report["audit"].get("findings", []) + report["readme"].get("findings", [])
    for finding in findings:
        out += [f"- **{finding['severity']}** {finding['finding']}", f"  - 依据: {finding['evidence']}",
                f"  - 建议: {finding['fix']}",
                f"  - 事实: {finding.get('confidence', 'Confirmed')}；效果证据: {finding.get('evidence_tier', 'heuristic')}。"]
    if not findings:
        out.append("没有已确认的问题；不可获取的模块见限制。")
    out += ["", "## Topics 保留与候选审核", "", ", ".join(report["suggestions"]["topics"]) or "未观察到原有标签。"]
    out += [f"- {note}" for note in report["suggestions"]["topic_notes"]]
    for note in report["topics"].get("structure_notes", []):
        out.append(f"- 结构检查: {note}")
    candidates = report["topics"].get("candidate_topics", {}).get("candidates", [])
    for candidate in candidates:
        out.append(f"- 待审核 `{candidate['topic']}`: {candidate.get('support_count', candidate.get('comparable_count'))}/"
                   f"{candidate.get('sample_denominator', '未知')} 个独立样本；字面线索: {candidate.get('evidence_snippet') or '未观察到'}；"
                   f"来源: {', '.join(candidate.get('examples', []))}。")
    per_topic = report["topics"].get("per_topic", [])
    if per_topic:
        out += ["", "| Topic | API 样本位置 | 样本数/上限 | Stars 样本中位数 | Stars 样本数 | 状态 |",
                "|---|---|---|---|---|---|"]
        for row in per_topic:
            rank = row.get("best_match_rank")
            position = f"#{rank}" if rank is not None else "未知" if row.get("status") == "unavailable" else "未进入样本"
            out.append(f"| {cell(row['topic'])} | {position} | {cell(row.get('sampled_count'))}/{cell(row.get('sample_limit'))} | "
                       f"{cell(row.get('median_stars_sample'))} | {cell(row.get('star_sampled_count'))} | {row.get('status')} |")
        out.append("\n这些是 Search API best-match 查询观察，与 Topics 页面实际排序分开；不据此预测流量。")
    out += ["", "## 目标查询基准", "", f"查询来源: {report['query_source']}；可用 --query 明确目标词。",
            "", "| 查询 | 样本位置 | 返回数/上限 | 完整性 | 时间 UTC |", "|---|---|---|---|---|"]
    for row in report["search_benchmark"]:
        rank = row.get("rank_in_sample")
        position = f"#{rank}" if rank is not None else "未知" if row["status"] == "unavailable" else "未进入样本"
        out.append(f"| {cell(row['query'])} | {position} | {cell(row.get('sampled_count'))}/{row['sample_limit']} | "
                   f"{row['status']} | {row['observed_at_utc']} |")
        for competitor in row.get("competitors", []):
            out.append(f"\n明确指定的竞品: {competitor['full_name']}，同查询样本 #{competitor['rank_in_sample']}。")
    if not report["search_benchmark"]:
        out.append("\n查询数据未采集。")
    if report.get("comparison"):
        out += ["", "### 与基线比较", ""]
        for comparison in report["comparison"]["comparisons"]:
            out.append(f"- {comparison['query']}: {comparison['change']}；位置变化 {cell(comparison['rank_delta'])}；"
                       f"{comparison.get('reason') or '同口径观察；变化不证明优化因果'}。")
    out += ["", "## Awesome-list 投稿机会", "", f"采集状态: {report['awesome'].get('status')}；机会不计入资料分。"]
    for entry in report["awesome"].get("lists", []):
        out += ["", f"### [{entry['full_name']}]({entry['url']})", "", f"状态: {entry['status']}；已收录: {cell(entry['already_listed'])}。"]
        eligibility = entry.get("eligibility", {})
        section = eligibility.get("section")
        if section:
            out.append(f"建议章节: [{section['heading']}]({section['url']})（行 {section['line']}）。")
        for evidence in eligibility.get("evidence", [])[:3]:
            out.append(f"- 准入依据: {evidence['text']} — {evidence['url']}，行 {evidence['line']}。")
        if entry.get("rules_url"):
            out.append(f"贡献规则: {entry['rules_url']}")
        submission = entry.get("submission", {})
        if submission and entry.get("already_listed") is not True:
            out += ["", f"PR 标题草稿: {submission.get('title', '')}", "", "````markdown", submission.get("entry", ""), "````",
                    "", submission.get("body", "")]
    out += ["", "## 宣传草稿与复查计划", ""]
    for draft in report["promotion"]["drafts"]:
        out += [f"### {draft['channel']}", "", f"受众: {draft['audience']}；目标: {draft['cta']}",
                "", "````text", draft["text"], "````", ""]
    for review in report["promotion"]["review"]:
        out.append(f"- 第 {review['day']} 天: {review['action']}。")
    out.append("\n草稿未发布，复查计划未创建定时任务。")
    traffic = report.get("traffic")
    if traffic:
        out += ["", "## 流量快照", "", f"状态: {traffic['status']}；最近 14 天，UTC 口径。"]
        for key in ("views", "clones"):
            data = traffic.get(key)
            out.append(f"- {key}: 总计 {cell(data.get('count') if data else None)}；窗口 unique {cell(data.get('uniques') if data else None)}。")
        if traffic.get("archived_path"):
            out.append(f"- 归档: `{traffic['archived_path']}`（按日期更新，不累加重叠窗口）。")
        out.append("- 各日 unique 不可相加；来源榜不代表 Google/GitHub 搜索归因，流量变化不证明因果。")
    out += ["", "## 限制与证据", ""] + [f"- {limitation}" for limitation in report["limitations"]]
    out += ["", "*数据采集与事实观察分开；结构分、共现和渠道建议均不保证排名或曝光增长。*"]
    return "\n".join(out)


def read_queries(path: str) -> list[str]:
    text = Path(path).read_text(encoding="utf-8")
    if text.lstrip().startswith("["):
        values = json.loads(text)
        if not isinstance(values, list) or any(not isinstance(q, str) for q in values):
            raise ValueError("Query JSON must be a list of strings.")
        return values
    return [line.strip() for line in text.splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser(description="GitHub readiness, search evidence, and promotion drafts.")
    parser.add_argument("repo", nargs="?", help="owner/repo, GitHub URL, or local directory (offline mode needs no origin)")
    parser.add_argument("--offline", action="store_true", help="read only local materials; no network, Git, or credential access")
    parser.add_argument("--local-path", help="local directory, required for --offline unless given as the positional input")
    parser.add_argument("--token", help="token override; prefer GH_TOKEN or gh auth")
    parser.add_argument("--provider", choices=["auto", "api", "gh"], default="auto")
    parser.add_argument("--max-topics", type=int, default=8)
    parser.add_argument("--top-n", type=int, default=15, help="topic Search API sample limit, 1-100")
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--query-file")
    parser.add_argument("--competitor", action="append", default=[])
    parser.add_argument("--context", help="project context JSON")
    parser.add_argument("--project-type", choices=PROJECT_TYPES, default="auto")
    parser.add_argument("--baseline", help="previous v2 JSON report for the same repo")
    parser.add_argument("--traffic-dir", help="explicitly collect and archive traffic under this directory")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--save", metavar="PATH")
    args = parser.parse_args()
    if args.max_topics < 0 or not 1 <= args.top_n <= 100:
        parser.error("--max-topics must be >= 0; --top-n must be between 1 and 100")
    try:
        if args.local_path and not args.offline:
            raise ValueError("--local-path requires --offline; online local-clone input remains positional.")
        local_path = args.local_path or (args.repo if args.repo and Path(args.repo).is_dir() else None)
        if args.offline:
            if not local_path:
                raise ValueError("--offline requires --local-path PATH or a local directory as positional input.")
            # A remote-looking input is a label only; never resolve Git origin offline.
            repo = args.repo if args.repo and not Path(args.repo).is_dir() else f"local:{Path(local_path).resolve().name}"
        else:
            repo = resolve_repo(args.repo)
        context = load_context(args.context) if args.context else None
        queries = args.query + (read_queries(args.query_file) if args.query_file else [])
        if args.offline and args.competitor:
            raise ValueError("Offline audits cannot observe competitors.")
        competitors = [resolve_repo(value) for value in args.competitor]
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8")) if args.baseline else None
        token = "" if args.offline else get_token(args.token)
        if not token and not args.offline:
            print("No token: running basic metadata/README checks; Search API modules are skipped.", file=sys.stderr)
        report = build_report(repo, token, args.provider, args.max_topics, args.top_n,
                              queries=queries, competitors=competitors, context=context, project_type=args.project_type,
                              baseline=baseline, traffic_dir=args.traffic_dir,
                              local_path=local_path, offline=args.offline)
        output = json.dumps(report, ensure_ascii=False, indent=2) if args.json else render_markdown(report)
        if args.save:
            Path(args.save).write_text(output + "\n", encoding="utf-8")
        print(output)
    except (GitHubAPIError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
