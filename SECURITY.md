# Security Policy

## Reporting a Vulnerability

Please **do not** open a public issue for security vulnerabilities.

Report privately via GitHub's
[private vulnerability reporting](https://github.com/Royo-Qiao/github-repo-seo/security/advisories/new)
on this repository.

## Scope

This skill is read-only against the GitHub API and handles tokens
(`GH_TOKEN` / `GITHUB_TOKEN` / `gh auth token`). Of particular interest:
any path where a token could be logged, echoed, or sent to a host other
than `api.github.com`.

Issues in the upstream projects credited in the README should be reported
upstream.
