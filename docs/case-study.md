# Case study: Cloudflare-Edgetunnel, 61 → 82 → 93

This is the skill's first real-world run, applied to its own author's repo
[Royo-Qiao/Cloudflare-Edgetunnel](https://github.com/Royo-Qiao/Cloudflare-Edgetunnel)
(a local web wizard that deploys VLESS+WS+TLS nodes to Cloudflare Pages).

All scores below come from `scripts/analyze.py`; they are directional
heuristics, not official GitHub weights.

## Timeline

| Date | Score | What changed |
|---|---|---|
| 2026-08-08 | **61** | Initial audit: thin README structure, incomplete community profile, unpolished topic set |
| 2026-08-08 | **82** | First fix round driven by the report (PR [#1](https://github.com/Royo-Qiao/Cloudflare-Edgetunnel/pull/1)): badge row with alt text, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, LICENSE cleanup, contribution/acknowledgment/license sections in the README — merged as `f01ce0a` |
| 2026-08-08 | — | Submitted to [zhuima/awesome-cloudflare](https://github.com/zhuima/awesome-cloudflare/pull/200) using the skill's awesome-list matching module |
| 2026-09-28 | **93** | Second fix round after a `/code-review` pass: `SECURITY.md`, `NOTICE.md` with upstream attribution, corrected CoC version attribution — completing the community-profile trust signals |

## What the score components looked like (2026-09-28)

- Metadata / trust files: community profile complete → the biggest single
  recoverable block in the first audit
- Topic quality: **100/100** — functional long-tail topics instead of
  language-only tags
- Topic ranking: deliberately ignored as a short-term lever (star-driven,
  long-term signal — the report says so itself)
- The report's "priority actions" section correctly identified trust files as
  the highest gain-per-minute fix in both rounds

## Takeaways

1. **Community/trust files were the cheapest points** — GitHub's community
   health checklist (LICENSE, CONTRIBUTING, CoC, SECURITY) is fully
   controllable and worth a large chunk of the metadata weight.
2. **The report's fix drafts are meant to be edited, not pasted** — the
   README rewrites are keyword scaffolds; the natural-sounding copy around
   them still needs a human (or Claude) pass.
3. **Read-only reporting worked** — every fix was reviewed before being
   committed, which caught real problems (e.g. a license claim that conflicted
   with GPL-derived vendored code) that a blind auto-apply would have cemented.
