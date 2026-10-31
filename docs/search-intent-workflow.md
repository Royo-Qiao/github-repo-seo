# From long-tail search questions to useful repository documentation

Reviewed 2026-10-29. The motivating [AI_Jasonyu post](https://x.com/AI_Jasonyu/status/2115631160189669566)
describes the author's experience of Google traffic to X articles and suggests
covering relevant search terms and checking Search Console. The X page returned
403 during review; public FxTwitter and VxTwitter JSON agreed on its text. It is
an anecdote about X, not evidence of GitHub's ranking formula or a growth guarantee.

## Choose the appropriate surface

| Surface | What to improve | What can be observed |
|---|---|---|
| GitHub repository | Accurate name, About, topics, useful README and linked docs | Bounded Search API samples and repository traffic |
| Google search | Original answers, descriptive titles, readable links and actual evidence | Real search appearance; GSC only for a supported property the user can verify |
| Owned Pages site/domain | Useful published documentation and ordinary website metadata | Verified website property performance when access is available |
| X article | A complete experience-based article that links to the repository | Eligible X platform property data in GSC, separately from X's own impressions |

[GitHub's repository search documentation](https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories)
states that default repository search covers names, descriptions and topics.
`in:readme` includes README text. A claim about the README's search visibility
therefore needs an appropriately scoped query.

Google's [helpful-content guidance](https://developers.google.com/search/docs/fundamentals/creating-helpful-content)
supports original experience and descriptive, accurate headings. Its
[SEO starter guide](https://developers.google.com/search/docs/fundamentals/seo-starter-guide)
does not support keyword stuffing, a required article length, or meta-keyword tricks.

Google currently documents [platform properties](https://support.google.com/webmasters/answer/17148418)
for Instagram, TikTok, X and YouTube, with gradual availability. These show
Google-side search performance; they are not X's internal reach or a full index
coverage report. GitHub is not on that list. Do not promise GSC verification for
`github.com/owner/repo`. For an owned website, follow the actual
[website verification process](https://support.google.com/webmasters/answer/9008080).

## Practical workflow

1. Write down the audience's actual question and the project's supported answer.
2. Run `scripts/content_plan.py LOCAL_PATH --query "question" --json`. The collector
   reads only root Markdown and `docs/**/*.md`, with bounded file sizes/counts.
3. Review cited passages and commands. Literal matching is not semantic validation;
   a heading alone cannot prove the documented procedure works.
4. Improve an existing page when it can answer the question. Include prerequisites,
   real steps, observable results, failure cases and uncertainty. Link from README.
5. Apply accurate About/topics and use a query with `in:readme` for README sampling.
6. Draft an X article only if useful. Treat posting and GSC access as separate actions.
7. Record an initial observation and compare compatible future samples. Do not claim
   publication, readiness scores, or one search observation proves growth or causality.

For a reverse-engineering case, useful questions include how an Electron resource
is loaded, why executable modes matter, and how to verify that an export actually
exists and decodes. A page should answer those questions from evidence rather
than advertise unverified compatibility, activation, or completeness.

## Local publication review

An unpublished checkout must be reviewed from its current local files, not from
an older remote README. The offline audit identifies its local provenance and
leaves remote metadata, topics, search and traffic unknown. A later online audit
is a distinct observation; never blend the two into a fabricated before/after rank.
