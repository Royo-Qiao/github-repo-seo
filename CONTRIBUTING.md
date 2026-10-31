# Contributing to github-repo-seo

## Development setup

Python 3.10+; runtime and tests use the standard library. No token or network access
is required for the offline test suite:

```bash
git clone https://github.com/Royo-Qiao/github-repo-seo.git
cd github-repo-seo
python3 -m unittest discover -s tests -v
```

For reproducible old/new collector comparisons, see
[the offline regression cases](evals/README.md). These checks exercise scripts;
they do not measure model output quality or publicity growth.

A real API smoke test is optional. It reads GitHub data and may require an existing
`gh` login or `GH_TOKEN` / `GITHUB_TOKEN`; keep credentials out of reports and tests:

```bash
python3 scripts/repo_audit.py octocat/Hello-World --json
```

## Pull requests

1. Branch from `main` and keep each change focused.
2. Keep scripts independently runnable and standard-library-only.
3. Run the offline suite. Add regression cases for behavior changes, especially
   partial API failures, missing permissions, incomplete samples, and unknown data.
4. Preserve the evidence boundaries: a read failure is not absence; readiness is
   not rank/growth; topics and copy must be supported by project facts.
5. Keep documentation and CLI examples aligned. Tests must not publish, submit PRs,
   execute target-project programs, or depend on live search ordering.

By participating, you agree to [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Reporting issues

Include the command, repository or relevant README excerpt, expected/actual result,
Python version, and OS. Share redacted errors and observation metadata where useful;
never include tokens. False-positive findings and ungrounded drafts are bugs too.
