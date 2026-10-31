# Offline collector regressions

`evals.json` defines three targeted cases: topic preservation, unavailable API
evidence, and a Chinese CLI README. `run_offline.py` runs the selected skill's
actual report pipeline against deterministic API fixtures, blocking real network
access and subprocesses. It does not run a model or test skill triggering, final
LLM rewriting, search exposure, or marketing outcomes.

From the repository root:

```bash
python3 evals/run_offline.py --skill-root . --scenario 1 --output-dir /tmp/github-repo-seo-eval-1
python3 evals/run_offline.py --skill-root . --scenario 2 --output-dir /tmp/github-repo-seo-eval-2
python3 evals/run_offline.py --skill-root . --scenario 3 --output-dir /tmp/github-repo-seo-eval-3
```

Each explicit output directory contains `outputs/report.md`,
`outputs/report.json`, `grading.json`, and `timing.json`. Use a separate output
directory and `--skill-root /path/to/previous-copy` to compare an older version.
The pass rates describe only these targeted script assertions. In particular,
the old skill already instructed the model to polish drafts; a placeholder in an
old raw CLI report does not establish failure of the final model-written copy.

The independent unit suite remains the main check:

```bash
python3 -m unittest discover -s tests -v
```
