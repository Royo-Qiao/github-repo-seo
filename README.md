# GitHub Repo SEO — a Claude Code skill

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](SKILL.md)
[![Zero dependencies](https://img.shields.io/badge/dependencies-0-brightgreen.svg)](scripts/github_api.py)

A [Claude Code](https://claude.com/claude-code) skill that audits a GitHub
repository's **discoverability** — in-site search ranking and external
search (Google / ChatGPT) indexing — and produces a markdown report:
**score → prioritized fix list → copy-pasteable drafts**.

Read the [sample report](docs/sample-report.md) or the
[case study](docs/case-study.md): the author used this skill to take
[Cloudflare-Edgetunnel](https://github.com/Royo-Qiao/Cloudflare-Edgetunnel)
from **61 → 82/100** and land it in an awesome-list (PR pending).

> 中文说明见下方 [中文简介](#中文简介)。

## What it checks

| Module | Weight | Controllability |
|---|---|---|
| Metadata audit (name / About description / topics / trust files) | 25% | fully controllable |
| README structure lint (7 categories, 0–100) | 30% | fully controllable |
| Topic quality (coverage, precision, generic-word blacklist) | 20% | fully controllable |
| Topic-page competition estimate (per-topic rank on `github.com/topics/<t>`) | 5% | semi-controllable, approximate |
| Ecosystem: awesome-list matching + homepage | 20% | partially controllable |

Highlights:

- **Topic-page competition** — estimates your position on each topic page via
  the Search API's best-match ordering, classifies every topic as
  keep / crowded-swap / niche-opportunity, and mines comparable repos for
  candidate tags (co-occurrence).
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
python3 scripts/topic_competition.py owner/repo   # topic-page competition
python3 scripts/awesome_match.py owner/repo       # awesome-list candidates
```

Every module runs standalone with `--json` output, so you can use them
outside Claude Code in scripts and CI.

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

这是一个 Claude Code skill，分析任意 GitHub 仓库的**可发现性**：站内搜索
排名 + 外部搜索（Google/ChatGPT）收录，输出「现状评分 → 按性价比排序的
修复清单 → 可直接复制的修改文案」。

- 五大模块：元数据审计 / README 结构 lint / Topic 质量 / Topic 页竞争度
  （含可比仓库共现挖掘）/ awesome-list 收录机会
- 纯标准库实现，零第三方依赖；每个模块可独立 CLI 运行并支持 `--json`
- 评分是方向性启发式，明确区分官方文档与社区经验，不冒充官方排名权重

```bash
export GH_TOKEN=<你的PAT>   # 细粒度 PAT、公共仓库无需任何 scope
python3 scripts/analyze.py owner/repo
```

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
  (MIT).
- Topic-page competition and awesome-list matching are original to this skill.

## License

[MIT](LICENSE). GitHub's search ranking is not publicly documented; scores
here are directional heuristics, not official weights.
