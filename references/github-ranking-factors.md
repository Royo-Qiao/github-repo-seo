# Evidence and limits for GitHub repository discoverability

GitHub does not publish a complete repository-ranking formula. This project's
published v1 score combines presentation and ecosystem heuristics; its weights
are local product choices, not search-engine factors or a growth forecast.

## Read evidence before interpreting a score

Use actual repository metadata, README text, manifests and examples to check each
finding. Structure and keyword overlap cannot prove that a capability works, a
command is correct or a user will adopt the project. Mark unavailable API evidence
unknown rather than concluding that a file is absent or a rank is poor.

The [historical case study](../docs/case-study.md) documents older rubric scores.
Those numbers are not measured traffic, causality or a comparison with newer
readiness rubrics. Do not update dates just to imply freshness.

## GitHub search and topics

[GitHub repository search](https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories)
searches name, description and topics by default. Use `in:readme` to include
README content. Search API best-match positions are bounded observations and are
not verified ordering on `github.com/topics/...`. An unobserved repository has
an unknown position beyond the sample, not an exact rank of N+1.

[Topics](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics)
should describe actual capabilities, ecosystem and distribution type. Preserve
relevant existing topics; the v1 collector's `crowded-swap` label does not establish
irrelevance. Co-occurrence candidates require semantic review. GitHub allows at
most 20 topics, using lowercase letters, numbers and hyphens.

## Useful long-tail documentation

Answer questions the intended audience actually has: prerequisites, a minimal
working path, observed output and known limits. Prefer original experience and
clear headings over repeated keywords or speculative compatibility promises.
[Google's helpful-content guidance](https://developers.google.com/search/docs/fundamentals/creating-helpful-content)
is about serving readers; it does not turn a README score into proof of indexing.

Google Search Console website or platform-property access is a separate check.
[Current platform-property documentation](https://support.google.com/webmasters/answer/17148418)
lists gradually available X, Instagram, TikTok and YouTube properties. GitHub repo
URLs are not in that list. A user's controlled Pages site/domain can have its own
website verification. Do not configure properties or publish X drafts without an
explicit request.

## Awesome-list candidates and promotion

A list-name match alone cannot establish an eligible section or accepted entry.
Read the list and contribution rules, check the exact repository URL for existing
inclusion, and keep submissions as drafts. No score guarantees acceptance or stars.
Only send submissions when the user authorizes that action.

## What was not measured

The collector does not verify Google/ChatGPT indexing, Google ranking, X impressions
or optimization-driven adoption. Repository traffic and compatible future search
samples need real observations; publishing a repository or improving documentation
is not proof that traffic increased. Do not combine overlapping traffic windows or
claim that a referrer identifies a search query or proves causality.
