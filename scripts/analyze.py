#!/usr/bin/env python3
"""
github-repo-seo — full discoverability report for a GitHub repository.

Orchestrates: metadata audit, README lint, in-site search position check,
topic-page competition analysis, and awesome-list matching. Emits a markdown
report (stdout) with scores, findings, and copy-pasteable fix suggestions.

Standalone usage:
  python analyze.py owner/repo
  python analyze.py https://github.com/owner/repo --save report.md
  python analyze.py /path/to/local/clone --json

Auth: GH_TOKEN env > GITHUB_TOKEN env > `gh auth token`. No hardcoded tokens.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone

from github_api import (
    GitHubAPIError,
    auth_context,
    fetch_json,
    get_token,
    resolve_repo,
    token_setup_hint,
)
from repo_audit import LANGUAGE_TOPICS, build_audit, tokenize
from readme_lint import fetch_readme_from_repo, score_report
from topic_competition import SEARCH_PAUSE, analyze_topics
from awesome_match import find_awesome_lists

# metadata 25 / readme 30 / topic_quality 20 / topic_ranking 5 / ecosystem 20 = 100
# topic_ranking is a star-driven, approximate long-term signal — kept at a
# minimal weight on purpose (see render_markdown note).
WEIGHTS = {"metadata": 0.25, "readme": 0.30, "topic_quality": 0.20,
           "topic_ranking": 0.05, "ecosystem": 0.20}


def overall_rating(score: float) -> str:
    """Map 0-100 to a rating label."""
    return ("Excellent" if score >= 90 else "Good" if score >= 70 else
            "Needs Improvement" if score >= 50 else "Poor" if score >= 30 else "Critical")


def search_position(repo: str, queries: list[str], token: str, provider: str) -> list[dict]:
    """Find the repo's rank in GitHub in-site search for a few key queries."""
    results = []
    for query in queries[:3]:
        time.sleep(SEARCH_PAUSE)
        try:
            data = fetch_json("/search/repositories", token=token,
                              params={"q": query, "per_page": 100}, provider=provider, timeout=35)
            rank = next((i for i, item in enumerate(data.get("items") or [], 1)
                         if (item.get("full_name") or "").lower() == repo.lower()), None)
            results.append({"query": query, "total": data.get("total_count", 0),
                            "rank_in_top100": rank})
        except GitHubAPIError as exc:
            results.append({"query": query, "total": None, "rank_in_top100": None, "error": str(exc)})
    return results


def suggest_description(meta: dict, keywords: list[str]) -> str:
    """Draft a keyword-rich About description (template; polish before use)."""
    current = (meta.get("description") or "").strip()
    lang = meta.get("language") or ""
    functional = [k for k in keywords if k not in LANGUAGE_TOPICS][:4]
    kw_phrase = " / ".join(functional) if functional else "[core-capability]"
    if len(current) >= 60:
        return current  # already decent; don't rewrite for the sake of it
    parts = []
    parts.append(f"[What it does: one verb phrase using {kw_phrase}].")
    if lang:
        parts.append(f"Built with {lang}.")
    parts.append("[Who it is for + the problem it solves — the words a user would search for.]")
    return " ".join(parts)


def suggest_topics(current: list[str], topic_report: dict) -> tuple[list[str], list[str]]:
    """Return (recommended topic list ≤15, notes) from verdicts + candidates."""
    notes = []
    keep, drop = [], []
    for entry in topic_report.get("per_topic", []):
        if entry["verdict"] in ("crowded-swap",):
            drop.append(entry["topic"])
        else:
            keep.append(entry["topic"])
    if drop:
        notes.append(f"Dropped as too crowded: {', '.join(drop)}")
    candidates = [c["topic"] for c in topic_report.get("candidate_topics", {}).get("candidates", [])]
    recommended = []
    for t in keep + candidates:
        if t.lower() not in [r.lower() for r in recommended]:
            recommended.append(t)
        if len(recommended) >= 15:
            break
    if candidates:
        notes.append(f"Added from comparable-repo co-occurrence: {', '.join(candidates[:6])}")
    return recommended, notes


def readme_opening_draft(meta: dict, keywords: list[str]) -> str:
    """Scaffold for a discoverability-friendly README opening."""
    name = meta.get("name") or "project"
    functional = [k for k in keywords if k not in LANGUAGE_TOPICS][:3]
    kw = ", ".join(functional) or "[core keywords]"
    return (
        f"# {name}\n\n"
        f"> One sentence: what it is + the problem it solves (include: {kw}).\n\n"
        "[badge row: build status | license | stars]\n\n"
        "![demo](./docs/demo.gif)  <!-- a 10-20s GIF beats three paragraphs -->\n\n"
        "## Why\n"
        "[2-3 bullets: the pain point, how this solves it, what's different]\n\n"
        "## Quickstart\n"
        "```bash\n"
        "# one copy-pasteable command that gets to a working result\n"
        "```\n"
    )


def build_report(repo: str, token: str, provider: str, max_topics: int, top_n: int) -> dict:
    """Run every module and assemble the aggregate report dict."""
    limitations = []
    ctx = auth_context(token=token)

    # 1. metadata audit
    audit = build_audit(repo, token=token, provider=provider)
    meta = audit["metadata"]
    limitations += audit.get("limitations", [])

    # 2. README lint (remote README; intents = repo's functional keywords)
    keywords = sorted(set(audit.get("name_tokens", [])) | set(audit.get("description_tokens", []))
                      | {t.lower() for t in (meta.get("topics") or []) if t.lower() not in LANGUAGE_TOPICS})
    readme_report = {"summary": {"score": 0, "rating": "Unknown"}, "findings": [], "limitations": []}
    try:
        markdown = fetch_readme_from_repo(repo, token=token, provider=provider)
        if markdown.strip():
            readme_report = score_report(markdown, intents=keywords[:10])
        else:
            readme_report["limitations"].append("README is empty on the default branch.")
    except GitHubAPIError as exc:
        readme_report["limitations"].append(f"README fetch failed: {exc}")
    limitations += readme_report.get("limitations", [])

    # 3. topic competition
    topic_report = analyze_topics(
        repo=repo, current_topics=meta.get("topics") or [],
        our_stars=int(meta.get("stargazers_count", 0)),
        keywords=[k for k in keywords if k not in LANGUAGE_TOPICS][:4],
        token=token, provider=provider, max_topics=max_topics, top_n=top_n,
    )
    limitations += topic_report.get("limitations", [])

    # 4. in-site search position for a couple of key queries
    name_phrase = (meta.get("name") or "").replace("-", " ").replace("_", " ")
    queries = [q for q in [name_phrase, " ".join(keywords[:2])] if q.strip()][:2]
    bench = search_position(repo, queries, token, provider) if queries else []

    # 5. awesome-list matching
    awesome_report = find_awesome_lists(
        repo=repo, topics=meta.get("topics") or [], language=meta.get("language") or "",
        name=meta.get("name") or "", description=meta.get("description") or "",
        token=token, provider=provider,
    )

    # aggregate score
    eco = min(100, awesome_report["score"] + (10 if meta.get("homepage") else 0))
    scores = {
        "metadata": audit["summary"]["score"],
        "readme": readme_report["summary"]["score"],
        "topic_quality": topic_report.get("quality_score", 0),
        "topic_ranking": topic_report.get("ranking_score", 0),
        "ecosystem": eco,
    }
    overall = round(sum(scores[k] * WEIGHTS[k] for k in WEIGHTS))

    # copy-paste suggestions
    rec_topics, topic_notes = suggest_topics(meta, topic_report)
    suggestions = {
        "description": suggest_description(meta, keywords),
        "topics": rec_topics,
        "topic_notes": topic_notes,
        "readme_opening": readme_opening_draft(meta, keywords),
    }

    return {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "repo": repo,
        "auth_context": ctx,
        "overall": {"score": overall, "rating": overall_rating(overall), "weights": WEIGHTS},
        "module_scores": scores,
        "metadata": meta,
        "audit": audit,
        "readme": readme_report,
        "topics": topic_report,
        "search_benchmark": bench,
        "awesome": awesome_report,
        "suggestions": suggestions,
        "limitations": limitations,
    }


def priority_actions(r: dict) -> list[dict]:
    """Derive ≤3 actions sorted by impact-per-minute (gain in overall points / effort)."""
    actions = []
    ms = r["module_scores"]

    # 1. Topics: biggest controllable lever when quality is low
    tq = ms["topic_quality"]
    if tq < 80:
        gain = round((85 - tq) * WEIGHTS["topic_quality"])
        actions.append({
            "text": "补齐/调整 Topics 为 5-15 个精准功能词(直接把第六节推荐列表粘贴到 About → Topics)",
            "gain": gain, "minutes": 5,
        })

    # 2. Trust files: each Warning costs the metadata score 8 points
    trust = [f for f in r["audit"].get("findings", [])
             if f.get("area") == "Trust" and f.get("severity") in ("Critical", "Warning")]
    if trust:
        recoverable = min(len(trust) * 8, max(0, 100 - ms["metadata"]))
        gain = round(recoverable * WEIGHTS["metadata"])
        names = sorted({
            f["finding"].split(":")[-1].strip(" .")
            for f in trust if f["finding"].startswith("Missing community file")
        })
        label = ", ".join(names) if names else "社区治理文件"
        actions.append({
            "text": f"补齐信任文件({label})— 可用 GitHub 社区模板在网页端一键生成",
            "gain": gain, "minutes": 10 * len(trust),
        })

    # 3. README category fixes → readme score points × readme weight
    readme_fixes = {
        "Opening Clarity": ("按第六节示例改写 README 首段", 10, 15),
        "Install + Quickstart": ("README 增加 Quickstart 安装命令区", 12, 15),
        "Proof & Visuals": ("README 增加截图或演示 GIF", 9, 30),
        "Badges": ("README 顶部增加 badges(CI/license/stars,shields.io)", 6, 10),
        "CTA + Community": ("README 增加 Contributing / issue 反馈入口", 6, 10),
    }
    seen = set()
    for f in r["readme"].get("findings", []):
        cat = f.get("category")
        if cat in readme_fixes and cat not in seen and f.get("severity") in ("Critical", "Warning"):
            label, pts, mins = readme_fixes[cat]
            actions.append({"text": label, "gain": round(pts * WEIGHTS["readme"], 1), "minutes": mins})
            seen.add(cat)

    actions.sort(key=lambda a: a["gain"] / a["minutes"], reverse=True)
    return actions[:3]


def render_markdown(r: dict) -> str:
    """Render the aggregate report as markdown."""
    md = r["metadata"]
    o = r["overall"]
    out = []
    out.append(f"# GitHub 可发现性分析报告 — {r['repo']}\n")
    out.append(f"> 生成时间: {r['generated_at_utc']} | 认证方式: {r['auth_context']['mode']} | "
               f"分析脚本: github-repo-seo skill\n")

    ms = r["module_scores"]
    acts = priority_actions(r)
    if acts:
        out.append("## 零、优先行动清单(按性价比排序:预计提分 ÷ 耗时)\n")
        for i, a in enumerate(acts, 1):
            out.append(f"{i}. **{a['text']}** — 预计总分 **+{a['gain']} 分**,约 {a['minutes']} 分钟")
        out.append("")

    out.append("## 一、总体评分\n")
    out.append(f"**{o['score']}/100 — {o['rating']}**\n")
    out.append("| 模块 | 得分 | 权重 | 说明 |")
    out.append("|---|---|---|---|")
    out.append(f"| 元数据(名称/About/Topics) | {ms['metadata']} | 25% | 仓库 About 区与标签质量 |")
    out.append(f"| README 结构 | {ms['readme']} | 30% | 首屏清晰度/安装/截图/badges |")
    out.append(f"| Topic 质量(覆盖度/精准度) | {ms['topic_quality']} | 20% | 完全可控:有无 topics、数量、功能词 |")
    out.append(f"| Topic 预估排名 | {ms['topic_ranking']} | 5% | 半可控 + API 近似值,仅作参考 |")
    out.append(f"| 生态收录机会 | {ms['ecosystem']} | 20% | awesome-list 候选 + homepage |")
    out.append("")

    if md:
        license_label = md.get("license") or "—"
        if license_label == "NOASSERTION":
            license_label = "NOASSERTION(有 LICENSE 文件但非标准 SPDX,建议换用常见许可证)"
        out.append("## 二、现状速览\n")
        out.append(f"- ⭐ {md.get('stargazers_count')} stars / 🍴 {md.get('forks_count')} forks / "
                   f"👀 {md.get('watchers_count')} watchers")
        out.append(f"- 语言: {md.get('language') or '—'} | 许可: {license_label} | "
                   f"默认分支: `{md.get('default_branch')}`")
        out.append(f"- 最近推送: {md.get('pushed_at')} | Homepage: {md.get('homepage') or '—'}")
        out.append(f"- 当前描述: {md.get('description') or '(空)'}")
        out.append(f"- 当前 Topics({len(md.get('topics') or [])}): {', '.join(md.get('topics') or []) or '(空)'}")
        bench = r["search_benchmark"]
        if bench:
            out.append("- GitHub 站内搜索位置:")
            for b in bench:
                rank = b.get("rank_in_top100")
                rank_txt = f"第 {rank} 名" if rank else "前 100 名外"
                err = f"(出错: {b['error']})" if b.get("error") else ""
                out.append(f"  - 关键词 `{b['query']}`: {rank_txt} / 共 {b.get('total')} 个结果 {err}")
        out.append("")

    out.append("## 三、问题清单(按严重度)\n")
    all_findings = []
    all_findings += [dict(f, module="元数据") for f in r["audit"].get("findings", [])]
    all_findings += [dict(f, module="README", area=f.get("category", "")) for f in r["readme"].get("findings", [])]
    order = {"Critical": 0, "Warning": 1, "Info": 2, "Pass": 3}
    all_findings = [f for f in all_findings if f.get("severity") in ("Critical", "Warning", "Info")]
    all_findings.sort(key=lambda f: order.get(f["severity"], 9))
    if not all_findings:
        out.append("✅ 未发现明显问题。\n")
    for f in all_findings:
        out.append(f"- **[{f['severity']}]** ({f['module']}/{f.get('area','')}) {f['finding']}")
        out.append(f"  - 依据: {f.get('evidence','')}")
        out.append(f"  - 修复: {f.get('fix','')}")
    out.append("")

    out.append("## 四、Topic 竞争度分析\n")
    out.append(f"**Topic 质量分: {ms['topic_quality']}/100**(计入总分,权重 20%)")
    for note in r["topics"].get("quality_notes", []):
        out.append(f"- {note}")
    out.append("")
    out.append(f"**Topic 预估排名分: {ms['topic_ranking']}/100**(计入总分,权重仅 5%)\n")
    out.append("> ⚠️ 预估排名是**长期指标**:与 star 数、活跃度强相关,且排名本身是 GitHub Search API"
               "(`topic:<name>` 默认 best-match 排序)对 topics 页面排序的近似。"
               "**不建议作为短期行动依据** — 短期提分请看「零、优先行动清单」和 Topic 质量分;"
               "排名会随 stars 增长自然改善。⭐对比取自 star 排序前 20 名的中位数。\n")
    per = r["topics"].get("per_topic", [])
    if per:
        out.append("| Topic | 页面内排名 | 收录仓库总数 | Top20 中位⭐ | 你的⭐ | 判定 | 建议 |")
        out.append("|---|---|---|---|---|---|---|")
        verdict_cn = {"keep-strong": "🟢 强势守住", "keep": "🟢 可见", "niche-opportunity": "🔵 冷门蓝海",
                      "crowded-swap": "🔴 过卷建议换", "off-page": "🟠 页面外", "error": "⚠️ 查询失败",
                      "unknown": "—"}
        for e in per:
            rank = f"≈#{e['best_match_rank']}" if e["best_match_rank"] else "前{}外".format("N")
            out.append(f"| `{e['topic']}` | {rank} | {e['pool_total']} | "
                       f"{e['median_stars_top20'] if e['median_stars_top20'] is not None else '—'} | "
                       f"{r['topics']['our_stars']} | {verdict_cn.get(e['verdict'], e['verdict'])} | {e['advice'] or e['error']} |")
        out.append("")
        leaders = per[0].get("top_repos", [])[:5] if per else []
        if leaders:
            out.append(f"`{per[0]['topic']}` best-match 前 5 名示例:")
            for row in leaders:
                out.append(f"  - {row['full_name']} ({row['stars']}⭐)")
            out.append("")
    cands = r["topics"].get("candidate_topics", {}).get("candidates", [])
    if cands:
        out.append("**值得新增的候选 topic**(来自可比仓库的共现统计):")
        for c in cands[:8]:
            out.append(f"  - `{c['topic']}` — 被 {c['comparable_count']} 个可比仓库使用,如 {', '.join(c['examples'][:2])}")
        out.append("")

    out.append("## 五、Awesome-list 收录机会\n")
    awesome = r["awesome"]
    out.append(f"检索词: {', '.join(awesome.get('terms_used', []))} | 命中 {awesome.get('total_matches', 0)} 个(展示前 5)\n")
    if not awesome.get("lists"):
        out.append("未找到仍在维护且规模达标的 awesome-list。可尝试更换检索词,或考虑领域内非 awesome 命名的清单。\n")
    for entry in awesome.get("lists", []):
        out.append(f"- **[{entry['full_name']}]({entry['url']})** — {entry['stars']}⭐,"
                   f"最近推送 {entry['days_since_push']} 天前,匹配词: {', '.join(entry['matched_terms'])}")
        if entry.get("contributing_url"):
            out.append(f"  - 📖 贡献指南: {entry['contributing_url']}")
        elif entry.get("note"):
            out.append(f"  - ℹ️ {entry['note']}")
        if entry.get("description"):
            out.append(f"  - {entry['description']}")
    out.append("")

    s = r["suggestions"]
    out.append("## 六、可直接复制的修改文案\n")
    out.append("### 1) About 描述(GitHub 仓库页 → About → 编辑)\n")
    out.append("```")
    out.append(s["description"])
    out.append("```\n")
    out.append("### 2) Topics 建议列表(逗号分隔,直接粘贴)\n")
    out.append("```")
    out.append(", ".join(s["topics"]) if s["topics"] else "(暂无可推荐)")
    out.append("```")
    for note in s["topic_notes"]:
        out.append(f"- {note}")
    out.append("")
    out.append("### 3) README 首屏改写示例\n")
    out.append("```markdown")
    out.append(s["readme_opening"].rstrip())
    out.append("```\n")

    if r["limitations"]:
        out.append("## 限制与说明\n")
        for lim in r["limitations"][:12]:
            out.append(f"- {lim}")
        out.append("")
    out.append("---")
    out.append("*评分为方向性启发式,非 GitHub 官方排名权重。方法论与部分检查项改编自 "
               "[Bhanunamikaze/Agentic-SEO-Skill](https://github.com/Bhanunamikaze/Agentic-SEO-Skill)(MIT),"
               "topic 共现方法参考 [agentic-devrel/github-topic-recommender](https://github.com/agentic-devrel/github-topic-recommender)。*")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(
        description="Full GitHub repo discoverability (SEO) report.",
        epilog="Example: python analyze.py Royo-Qiao/Cloudflare-Edgetunnel --save report.md",
    )
    parser.add_argument("repo", help="owner/repo, GitHub URL, or local clone path")
    parser.add_argument("--token", help="GitHub token override (prefer GH_TOKEN env)")
    parser.add_argument("--provider", choices=["auto", "api", "gh"], default="auto")
    parser.add_argument("--max-topics", type=int, default=8, help="topics to analyze (default 8)")
    parser.add_argument("--top-n", type=int, default=15, help="topic-page window (default 15)")
    parser.add_argument("--json", action="store_true", help="emit raw JSON instead of markdown")
    parser.add_argument("--save", metavar="PATH", help="also write the report to a file")
    args = parser.parse_args()

    token = get_token(args.token)
    if not token:
        print(token_setup_hint(), file=sys.stderr)
        sys.exit(2)

    try:
        repo = resolve_repo(args.repo)
        print(f"[1/5] metadata audit … ({repo})", file=sys.stderr)
        report = build_report(repo, token=token, provider=args.provider,
                              max_topics=args.max_topics, top_n=args.top_n)
    except GitHubAPIError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        sys.exit(130)

    if args.json:
        text = json.dumps(report, indent=2, ensure_ascii=False)
    else:
        text = render_markdown(report)
    print(text)
    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"\n[saved] {args.save}", file=sys.stderr)


if __name__ == "__main__":
    main()
