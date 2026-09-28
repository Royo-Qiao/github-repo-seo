# Contributing to github-repo-seo

Thanks for taking the time to contribute! :sparkles:

## Development Setup

Requirements: Python 3.10+ (stdlib only — no virtualenv needed) and a GitHub
token (`export GH_TOKEN=<pat>` or `gh auth login`).

```bash
git clone https://github.com/Royo-Qiao/github-repo-seo.git
cd github-repo-seo
python3 scripts/repo_audit.py octocat/Hello-World   # smoke test, ~2 API calls
```

## Pull Requests

1. Create your branch from `main`.
2. Keep changes focused — one concern per PR.
3. Each script under `scripts/` must stay independently runnable and
   stdlib-only (no third-party imports).
4. Verify the module you touched still runs cleanly against a public repo
   (e.g. `octocat/Hello-World`).
5. By participating, you agree to the [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Reporting Issues

Please include:

- the command you ran and the repo (or README) it failed on
- expected vs. actual output
- Python version and OS

False-positive lint findings are bugs too — please open an issue with the
README excerpt that triggered them.
