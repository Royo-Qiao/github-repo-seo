# GitHub Repo SEO — a Claude Code skill

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](SKILL.md)
[![Zero dependencies](https://img.shields.io/badge/dependencies-0-brightgreen.svg)](scripts/github_api.py)

An agent skill for auditing how clearly a GitHub repository presents itself:
metadata, README structure, topic/search samples and awesome-list candidates.
It produces a Markdown report with a heuristic score, prioritized fixes and
editable drafts. Python 3.10+; standard library only.

Use it when an open-source project needs a clearer quickstart, accurate Topics
or a better description of who it helps. The collector reads repository evidence;
it does not verify Google/ChatGPT indexing or guarantee rankings, traffic or stars.

Read the [sample report](docs/sample-report.md) and
[historical case study](docs/case-study.md). Its 61 → 82 values are the tool's
own rubric scores, not measured growth. The case study's submission status is a
historical note, not a current acceptance claim.

> 中文说明见下方 [中文简介](#中文简介)。

## What the published v1 checks

| Module | Weight | Controllability |
|---|---|---|
| Metadata audit (name / About description / topics / trust files) | 25% | fully controllable |
| README structure lint (7 categories, 0–100) | 30% | fully controllable |
| Topic quality (coverage, precision, generic-word blacklist) | 20% | fully controllable |
| Topic Search API sample observations | 5% | semi-controllable, approximate |
| Ecosystem: awesome-list matching + homepage | 20% | partially controllable |

Highlights:

- **Topic search samples** — observes Search API best-match results and mines
  comparable-repository topics. These samples are not verified topic-page ranks.
  The v1 collector's `crowded-swap` verdict is a review hint: keep a relevant
  existing topic when crowding is the only reason offered for removing it.
- **Awesome-list matching** — finds maintained `awesome-*` lists that fit your
  repo, with each list's contribution-guide URL for manual PR submission.
- **Honest heuristics** — GitHub's ranking formula is a black box; every score
  is labeled directional, never presented as official weights.

## Quickstart

Requires: Python 3.10+ and a GitHub token (fine-grained PAT with no scopes
works for public repos).

```bash
git clone https://github.com/Royo-Qiao/github-repo-seo.git
cd github-repo-seo
export GH_TOKEN=<your_pat>          # or: gh auth login

# full report (~35 API calls, 60–120 s)
python3 scripts/analyze.py owner/repo

# per-module
python3 scripts/repo_audit.py owner/repo          # metadata + trust files
python3 scripts/readme_lint.py --repo owner/repo  # README structure
python3 scripts/topic_competition.py owner/repo   # topic Search API samples
python3 scripts/awesome_match.py owner/repo       # awesome-list candidates
```

Every module runs standalone with `--json` output, so you can use them
outside Claude Code in scripts and CI.

### Example report

The [historical sample](docs/sample-report.md) includes a module breakdown,
findings with evidence and suggested copy. Its 2026-09-28 score can be represented
by these excerpted JSON fields:

```json
{
  "repo": "Royo-Qiao/Cloudflare-Edgetunnel",
  "overall": {"score": 93, "rating": "Excellent"}
}
```

This is an excerpt from that old example, not a new measurement or an expected
score for your repository. The analyzer also returns `module_scores`, `audit`,
`readme`, `topics`, `search_benchmark`, `awesome`, `suggestions` and `limitations`.

### Install as a Claude Code skill

Copy (or symlink) this folder into your skills directory:

```bash
git clone https://github.com/Royo-Qiao/github-repo-seo.git \
  ~/.claude/skills/github-repo-seo
```

Then ask Claude: *"检查仓库 SEO"* / *"analyze my repo's discoverability"* /
*"why does my repo get no stars from search"* — the skill auto-triggers on
those phrases (see [SKILL.md](SKILL.md) for the full trigger list).

## 中文简介

这是一个可供 Agent 使用的 GitHub 仓库可发现性审查 Skill：读取真实的
元数据、README 和 Topics，观察有限的搜索样本，输出启发式评分、优先修改项
和文案草稿。它不验证 Google/ChatGPT 收录，也不保证排名或流量增长。

- 五大模块：元数据审计 / README 结构 lint / Topic 质量 / Topic 搜索样本
  （含可比仓库共现挖掘）/ awesome-list 收录机会
- 纯标准库实现，零第三方依赖；每个模块可独立 CLI 运行并支持 `--json`
- 评分是方向性启发式，明确区分官方文档与社区经验，不冒充官方排名权重

```bash
export GH_TOKEN=<你的PAT>   # 细粒度 PAT、公共仓库无需任何 scope
python3 scripts/analyze.py owner/repo
```

## Interpreting an audit

- Read findings against the actual README and source. A heading/keyword check
  alone cannot validate a capability or command; example commands are not executed.
- Preserve accurate topics; co-occurrence and a crowded search sample are not
  evidence that a topic is unsuitable. Review suggested additions against the code.
- Use `in:readme` for GitHub repository queries intended to include README text.
  GitHub's default repository search covers name, description and topics.
- Treat failed API checks as unknown. The published v1 rubric mixes presentation
  and ecosystem observations, so its score is not comparable to newer local
  readiness rubrics and does not measure growth.
- Useful long-tail docs answer real audience questions with original steps,
  evidence and limits. Publishing a repository does not prove Google indexing.

This page describes the code currently published in this repository. Local-only
collector experiments and uncommitted changes are not advertised as shipped flags.

## Contributing

Issues and PRs are welcome — especially a lint finding on your own README
that turned out to be a false positive. See
[CONTRIBUTING.md](CONTRIBUTING.md); by participating you agree to the
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Design notes

- **Read-only by design** — the skill never pushes changes to your repo; all
  suggestions are drafts you apply yourself.
- **Rate-limit friendly** — polite pauses between Search API calls, exponential
  backoff with jitter-free retries, and a `gh` CLI fallback when no token env
  var is set.
- **Progressive disclosure** — [SKILL.md](SKILL.md) stays small; the ranking
  factors reference and per-module scripts load only when needed.

## Credits

- Metadata/README checks and the scoring rubric are adapted from
  [Bhanunamikaze/Agentic-SEO-Skill](https://github.com/Bhanunamikaze/Agentic-SEO-Skill)
  (MIT).
- Topic co-occurrence methodology after
  [agentic-devrel/github-topic-recommender](https://github.com/agentic-devrel/github-topic-recommender)
  (methodological reference).
- Search sampling and awesome-list matching were added in this skill.

## License

[MIT](LICENSE). GitHub's search ranking is not publicly documented; scores
here are directional heuristics, not official weights.
