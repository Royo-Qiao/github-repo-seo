<!-- Adapted from Bhanunamikaze/Agentic-SEO-Skill (MIT License)
     https://github.com/Bhanunamikaze/Agentic-SEO-Skill/blob/main/resources/references/github-ranking-factors.md
     Trimmed to factors this skill actually measures. -->
# GitHub Repository Discoverability Factors (Practical Reference)

GitHub does not publish a full ranking formula. These are empirically useful,
directional factors — not ranking weights.

## High-Signal Metadata

- Repository name clarity and intent match (hyphen-separated tokens).
- Description specificity and keyword fit (what-it-does words, not just a brand).
- Topics relevance and completeness: mix broad categories + long-tail functional
  tags; ≤20 total; don't stop at language tags.
- Homepage URL quality (docs/demo site in the About card).
- Social preview image for share CTR.

## README Signals

- Strong opening summary in the first 3-5 lines (what / for whom / why).
- Query-aligned language for target use cases.
- Copy-pasteable install + quickstart commands.
- Proof of utility: screenshots, demo GIF, sample output.
- Badge row (CI, license, stars) as an at-a-glance maintenance signal.
- Clean heading hierarchy (single H1, no level skips) — used by search engines
  to build structured outlines.

## Trust and Maintenance Signals

- Community profile completion (LICENSE, CONTRIBUTING, code of conduct,
  security policy, issue templates).
- Release cadence and push recency (freshness as a trust proxy).
- Stars/forks as adoption proxies.

## Topic-Page Position (this skill's Module A)

- A topic page orders repos by best match; being inside the visible first page
  (≈top 15-20) is where the discovery traffic is.
- Competition read: pool size (repos tagged with the topic) vs. top-20 median
  stars vs. your stars. Crowded + off-page → swap to long-tail; small pool +
  near the page → own the niche.
- Comparable-repo topic co-occurrence surfaces candidate tags you're missing.

## Anti-Hallucination Rules

- Never claim definitive ranking weights.
- Distinguish observed evidence from inferred hypothesis.
- Mark API-limited sections as unknown, not failed.
