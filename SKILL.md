---
name: github-repo-seo
license: MIT
description: >
  Analyze and optimize a GitHub repository's discoverability — GitHub in-site
  search samples and repository presentation. It does not verify Google/ChatGPT
  indexing. Triggers when
  the user mentions "检查仓库 SEO", "GitHub SEO", "优化 GitHub 可发现性",
  "repo discoverability", "README SEO 检查", "topics 优化", "分析仓库排名",
  or asks why a repo gets no traffic/stars from search. Covers metadata audit,
  README structure lint, topic-page competition, awesome-list matching, and
  copy-pasteable fix suggestions.
---

# GitHub Repo SEO / Discoverability

Analyze one GitHub repo (owner/repo, URL, or local clone) and produce a
markdown report: 现状评分 → 问题清单 → 可直接复制的修改文案.

## Auth

Scripts read `GH_TOKEN` (or `GITHUB_TOKEN`), falling back to `gh auth token`.
If none is available, tell the user how to set it — never hardcode a token:

```bash
export GH_TOKEN=<pat>      # fine-grained PAT, no scopes needed for public repos
# or rely on the CLI session:
gh auth login && gh auth status
```

Without auth the Search API allows ~10 req/min and the topic/awesome modules
will fail — do not attempt a full run unauthenticated.

## Workflow

### 1. Run the analyzer

Scripts live next to this SKILL.md. Resolve the skill directory first (the
directory containing this file — Claude Code exposes it as
`${CLAUDE_SKILL_DIR}`; otherwise derive it from the path you loaded the skill
from), then:

```bash
python3 "${CLAUDE_SKILL_DIR:-<skill-dir>}/scripts/analyze.py" <owner/repo>
```

Options: `--save report.md` (write to file; default is stdout only),
`--json` (raw data), `--max-topics N`, `--top-n N`.
A full run makes ~35 API calls with polite pauses; expect 60-120s.

The script covers all five modules itself:

1. **Metadata audit** — name / About description (incl. brand-only detection) /
   topics (count + language-only detection) / staleness / trust files.
2. **README lint** — first-screen clarity, quickstart, screenshots/GIF, badges,
   heading hierarchy, alt text. Scored 0-100 across 7 categories.
3. **Topic search samples (Module A)** — per topic: position within the returned
   Search API `topic:<t>` best-match sample, not verified Topics-page placement,
   pool size, top-20 median stars; verdicts: keep / crowded-swap /
   niche-opportunity; plus candidate topics mined from comparable repos
   (co-occurrence).
4. **Awesome-list matching (Module B)** — maintained awesome-xxx lists with
   contribution-guide URLs for manual PRs.
5. **Report** — weighted score (metadata 25 / README 30 / topics 25 /
   ecosystem 20), findings by severity, copy-paste drafts for description,
   topics list, README opening.

Each module also runs standalone, e.g.
`python3 "$SKILL_DIR/scripts/topic_competition.py" owner/repo`.

### 2. Polish the drafts

The script's description/README rewrites are keyword-scaffold drafts
(`[placeholders]`). Before presenting, rewrite them into natural,
brand-appropriate copy using the repo's actual README content — keep the
keywords, drop the brackets. Never overwrite the user's repo; the skill only
reports, it does not push changes.

### 3. Deliver

Output the report in the conversation (markdown). Only write a file when the
user explicitly asks (`--save` or "落盘").

## Rules

- Never claim definitive GitHub ranking weights — scores are directional heuristics.
- Treat API/token failures as environment limitations, not repo defects.
- Topics stay ≤20; preserve the project's voice in rewrite suggestions.
- Search API samples are not verified Topics-page rankings. Report sample limits
  and unknowns; do not claim exact ranks beyond the returned sample.
- The published v1 `crowded-swap` label does not justify removing a relevant
  existing topic. Keep valid topics and review additions against actual capabilities.
- Read real source and documentation before polishing drafts. Never invent
  commands, first-hand tests, compatibility or growth claims.
- Long-tail content should answer audience questions with original evidence and
  known limits. Google indexing and Search Console setup require separate evidence.

## Credits

- Metadata/README checks and the scoring rubric are adapted from
  [Bhanunamikaze/Agentic-SEO-Skill](https://github.com/Bhanunamikaze/Agentic-SEO-Skill)
  (MIT License) — see `references/github-ranking-factors.md` and file headers.
- Topic co-occurrence methodology after
  [agentic-devrel/github-topic-recommender](https://github.com/agentic-devrel/github-topic-recommender) (methodological reference).
- Modules A (topic-page competition) and B (awesome-list matching) are original
  to this skill.
