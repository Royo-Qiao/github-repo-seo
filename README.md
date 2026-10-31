# GitHub Repo SEO — discoverability and promotion drafts

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](SKILL.md)
[![Zero dependencies](https://img.shields.io/badge/dependencies-0-brightgreen.svg)](scripts/github_api.py)

An agent skill for checking how clearly a GitHub repository presents itself,
observing bounded search results, and preparing README, metadata, and promotion
drafts backed by project facts. It reports evidence and unknowns, with concrete
next steps. It does not promise search rankings, Google/ChatGPT indexing, or stars.

See the [sample report](docs/sample-report.md) and
[historical case study](docs/case-study.md). The case's 61 → 82 → 93 scores used
an earlier rubric; they are not measured growth or comparable to today's readiness.

## What it does

| Area | Result |
|---|---|
| Repository readiness | Metadata, project-type-aware README checks, and topic structure |
| Search observations | Explicit query samples, named competitors, and compatible baseline comparisons |
| Topic candidates | Comparable-repo evidence for human/agent review; relevant existing topics stay |
| Awesome lists | Real README/section/rule evidence, existing-listing checks, and submission drafts |
| Promotion package | Factual project copy, channel drafts, and a suggested follow-up plan |
| Optional traffic | Views/clones/referrers/paths and repository-isolated local history |

Readiness uses custom weights: **metadata 35% / README 40% / topic structure 25%**.
It summarizes presentation checks; it is not GitHub's ranking formula. Incomplete
required evidence means no total score. Search rank, awesome-list availability,
stars, and traffic do not enter readiness.

## Quickstart

Python 3.10+; standard library only. An existing `gh` login or `GH_TOKEN` /
`GITHUB_TOKEN` enables search. Without authentication, the analyzer still collects
available basic metadata/README evidence and marks skipped search checks unknown.

```bash
git clone https://github.com/Royo-Qiao/github-repo-seo.git
cd github-repo-seo
python3 scripts/analyze.py owner/repo

# Explicit search intent and project type; repeat --query / --competitor as needed
python3 scripts/analyze.py owner/repo --project-type cli \
  --query "GitHub repository audit" --query "README discoverability" \
  --competitor other/repo --json

# Review current local files before publication; no origin, Git, credentials or network
python3 scripts/analyze.py /path/to/repository --offline --project-type docs --json
```

Offline mode uses current local README/license/community files and relative-path
evidence. Remote About, topics, search and traffic stay unknown; there is no total
readiness score. `--local-path PATH --offline` is an equivalent explicit input.
Run an online audit after publishing to verify actual repository settings separately.

The default report goes to stdout; nothing is posted or submitted. Use
`--save report.md` only when a saved report is wanted. To keep a JSON baseline,
explicitly save stdout and later provide that file:

```bash
python3 scripts/analyze.py owner/repo --query "GitHub repository audit" --json > baseline.json
python3 scripts/analyze.py owner/repo --query "GitHub repository audit" --baseline baseline.json
```

Other options: `--query-file PATH` (JSON string list or one query per line),
`--context PATH`, `--provider auto|api|gh`, `--token`, `--max-topics N`, and
`--top-n N`. `--project-type` accepts `auto/cli/library/ui/dataset/list/skill/docs`.
Queries are capped at eight distinct phrases; search samples are bounded. A baseline
must be a v2 JSON report for the same repository with compatible query/sort/sample/
completeness. Generate a new baseline instead of importing old-rubric reports.

An optional context file makes the intended audience and goal explicit:

```json
{
  "summary": "Audit GitHub repository presentation and prepare promotion drafts.",
  "audience": "Open-source maintainers",
  "problem": "A useful project is hard to understand or discover.",
  "differentiator": "Deterministic checks with source-backed draft suggestions.",
  "goal": "Help suitable users reach the quickstart and give feedback.",
  "project_type": "skill",
  "queries": ["GitHub repository audit", "README discoverability"],
  "channels": ["Relevant developer community", "Project release notes"]
}
```

Run `python3 scripts/analyze.py owner/repo --context context.json`. Context values
remain user-provided claims until checked against the project. The agent completes
the semantic review and natural copy using the actual README, manifests, and examples;
the scripts do not execute the target project's program.

### Plan content around real search questions

Before publication, map audience questions to the actual local documentation:

```bash
python3 scripts/content_plan.py /path/to/repository \
  --query "How to verify a native video export" \
  --query "Electron ASAR executable permissions" --json
```

This reads root Markdown and `docs/**/*.md`, returning relative file/line evidence
and editorial gaps. It skips symlinks and code blocks. Literal overlap needs a
human or agent review; it is not semantic coverage or keyword-volume research.
Write a useful answer with working steps, original observations, and limitations,
then use the reader's wording naturally. There is no keyword-density target.

GitHub search, Google search, and X promotion are separate surfaces. GitHub's
default repository search covers name/description/topics; add `in:readme` to search
README text. A public repository is not proof of Google indexing. Search Console
now documents gradually available **X platform properties**, but not GitHub repo
properties; actual eligibility and Google-side impressions/clicks require a live
check. An owned Pages site or domain has its own website-verification workflow.
See the [source review and practical workflow](docs/search-intent-workflow.md).

### Optional traffic history

```bash
python3 scripts/analyze.py owner/repo --traffic-dir ./traffic-history
```

This explicitly requests collection and local archival. GitHub traffic requires
repository write access; fine-grained tokens need **Administration (read)**. Lack
of access is unknown, not zero. GitHub supplies rolling 14-day windows; daily data
is upserted by UTC date. Do not add uniques across days or add overlapping referral
windows. Referrers alone cannot attribute growth to Google, GitHub search, or a
particular edit. See [GitHub's traffic documentation](https://docs.github.com/en/rest/metrics/traffic).

### Standalone modules

```bash
python3 scripts/repo_audit.py owner/repo --json
python3 scripts/readme_lint.py --repo owner/repo --json
python3 scripts/topic_competition.py owner/repo --json
python3 scripts/awesome_match.py owner/repo --json
python3 scripts/search_benchmark.py owner/repo "README discoverability"
python3 scripts/traffic_snapshot.py owner/repo
```

Search observations are positions within Search API samples, not verified topic-page
rankings. Awesome-list matching inspects at most five candidates and distinguishes
`candidate`, `review-required`, and `already-listed`. Commands and submission text
are drafts based on source evidence; they do not publish changes.

## Install as an agent skill

Install the **whole repository**, so `SKILL.md`, scripts and references stay
together. Requires Git and Python 3.10+; there are no Python dependencies to install.
For Claude Code:

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/Royo-Qiao/github-repo-seo.git \
  ~/.claude/skills/github-repo-seo
```

For another agent, clone into that agent's documented skills directory, or ask it
to read the cloned `SKILL.md` by its absolute path. Copying only `SKILL.md` is not
enough: it invokes sibling scripts and references.

For an existing clean installation, update without rewriting local changes:

```bash
git -C ~/.claude/skills/github-repo-seo pull --ff-only
```

If Git reports local edits or divergent history, preserve them and resolve the
conflict before updating; do not reset the installation blindly. To verify an
installation without GitHub credentials or network requests:

```bash
python3 ~/.claude/skills/github-repo-seo/scripts/analyze.py \
  ~/.claude/skills/github-repo-seo --offline --project-type skill --json
```

For online search, use an existing `gh auth login` session or `GH_TOKEN` /
`GITHUB_TOKEN` in the environment. Never include a token in an installation prompt.

Then ask “检查仓库 SEO”, “GitHub宣传”, “开源推广”, “仓库曝光”, “README转化”,
or “analyze my repo's discoverability”. [SKILL.md](SKILL.md) explains how the agent
collects JSON, checks the underlying facts, and delivers reviewed copy.

## 中文简介

这是一个用于 **GitHub 可发现性和推广准备** 的 agent skill：先检查仓库资料、
README 和 Topics，再观察搜索样本、匹配清单机会，生成有事实依据的修改文案与推广草稿。
默认在会话交付；不自动发帖、提交 PR、改仓库或设置日程。

- 资料准备度只评估可控的呈现质量；缺少必要证据时不提供总分。
- Topics 候选需要核对真实能力，不因竞争拥挤自动删掉现有相关词。
- 无 token 可完成基础检查；API 失败与未知项不会当成项目缺陷。
- 可选保存同口径搜索基线与 14 天流量快照，变化不能直接证明推广效果。

## Contributing and credits

See [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md),
and the [evidence reference](references/github-ranking-factors.md).

Metadata/README checks originated from
[Bhanunamikaze/Agentic-SEO-Skill](https://github.com/Bhanunamikaze/Agentic-SEO-Skill)
(MIT). Topic co-occurrence was inspired by
[agentic-devrel/github-topic-recommender](https://github.com/agentic-devrel/github-topic-recommender),
a CLI whose current main branch has no license file; this is a method reference,
not a claim of MIT-licensed code reuse. The current readiness rubric and evidence/
promotion orchestration are maintained here.

## License

[MIT](LICENSE). Scores are custom heuristics, not official ranking weights.
