<!-- Metadata/README guidance originated from Bhanunamikaze/Agentic-SEO-Skill (MIT).
     This reference documents the current skill's measurement and interpretation limits. -->
# GitHub Discoverability: Evidence and Measurement

GitHub does not publish a complete repository ranking formula. Separate what was
observed from why an improvement might help, and from whether it caused growth.

For search-intent planning and the distinction between GitHub search, Google,
owned sites and X/Search Console platform properties, read
[the content workflow](../docs/search-intent-workflow.md). Content evidence and
Search Console availability do not contribute to the readiness score.

## Evidence contract

Each important finding should identify its source, observation, impact hypothesis,
and suggested fix. `Confirmed` means the condition was directly observed;
`Likely` or `Hypothesis` means further verification is needed. API errors, missing
permissions, unsupported file encodings, and incomplete samples are unknown data,
not confirmed missing files, poor ranking, or zero traffic.

Keep two questions distinct:

| Question | Appropriate evidence |
|---|---|
| Is this README/topic/metadata condition present? | Actual file text, API field, line number, or complete response |
| Will changing it increase exposure/adoption? | An explicit hypothesis followed by comparable observations; no guarantee |

User context supplies positioning intent. It does not independently prove a feature,
performance claim, target audience's behavior, or a competitor comparison. Script
output also needs semantic review: headings, keywords, and a score alone cannot
establish that a README explains the project well.

## Repository presentation

Useful checks include a clear purpose/audience, accurate About description,
relevant topics, documentation/demo links, a usable getting-started path, and trust
or maintenance information. Their weight in readiness is a local product decision,
not a claim about search weights.

Adapt the README to the project: CLI invocation, library examples/API, real UI
screenshots, dataset access/schema, list navigation, skill installation/invocation,
or documentation entry points. Images and badges are optional. Recommend only
commands grounded in the README, manifest, or examples; say whether they were run.

Topics should accurately categorize the project. Use broad category, niche,
capability, ecosystem, and distribution type when supported. Retain current topics
until there is evidence for a specific change; compare aliases and redundancy rather
than swapping a relevant topic merely because it is crowded. GitHub caps repository
topics at 20. See [GitHub's topic documentation](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics).

## Readiness rubric

Current weights are metadata **35%**, README **40%**, and topic structure **25%**.
Readiness summarizes controllable presentation checks; it is not an exposure or
adoption score. Required unavailable evidence means no total score. Search position,
topic competition, awesome-list opportunities, and traffic do not contribute.
The historical 61/82/93 case used a different rubric and cannot be compared directly.

## Search and topic competition

GitHub repository search supports explicit scope and classification qualifiers;
the default search does not search all README content. Choose queries from the
audience's problem and the repository's actual terminology, then record the exact
query, sort, UTC time, sample limit/count, and completeness. See
[GitHub's repository-search documentation](https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories).

Search API best-match positions are observed within a returned sample. They are
not verified topic-page positions, exposure counts, or proof of ranking factors.
“Not observed in the first N results” does not mean rank N+1. Partial/failed samples
cannot establish nonappearance. Compare only complete observations for the same
repo and identical query/sort/sample/completeness settings.

Competition statistics and co-occurring topics help investigate an ecosystem.
Their samples may favor popular repositories; stars are not audience demand or
semantic relevance. A candidate topic must still fit actual project capabilities.
Small pools are not evidence of high-value traffic, and crowded pools are not a
reason to remove a relevant topic.

## Awesome-list opportunities

Candidate discovery is a search/filter heuristic, not a health score. Inspect real
README and admission/format rules before recommending a submission. Report the
exact repository URL if already included, and the actual heading/line when suggesting
a section. A similar list name is insufficient section evidence. Unreadable README
content means listing status unknown; unreadable rules mean eligibility unknown.
`candidate` still needs review against the quoted rules. Drafting an entry or PR body
does not mean a PR was sent or the list accepted the project.

## Traffic and effect measurement

[GitHub traffic endpoints](https://docs.github.com/en/rest/metrics/traffic) require
repository write access; fine-grained tokens need Administration (read). They supply
views/clones and the top referral sources/popular paths for rolling 14-day windows,
with UTC day boundaries. Collect/archive only when requested; unavailable values
remain unknown.

Upsert daily views/clones by UTC date as later snapshots revise the same days.
Do not sum daily uniques into longer-period unique visitors/cloners or sum
overlapping rolling windows. Referral/path windows are snapshots, not independent
period totals. A Google referrer records a source label; it does not identify a
search query or prove an edit caused the visit. Changes alone cannot establish
Google, GitHub-search, or campaign attribution.

Compare consistent baselines and record publication/edit dates separately. Track
useful outcomes such as documented onboarding feedback as well as views/clones.
Promotion schedules in a report are suggestions; they do not create reminders.
External website SEO and AI citation/indexing verification require separate evidence
and scope, not an inference from a GitHub readiness score.
