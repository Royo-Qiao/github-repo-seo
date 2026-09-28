#!/usr/bin/env python3
"""
Shared GitHub API helpers for github-repo-seo skill.

Self-contained, stdlib-only (urllib + optional `gh` CLI fallback) — no
third-party dependencies.
Token resolution order: --token arg > GH_TOKEN env > GITHUB_TOKEN env > `gh auth token`.

Authored for github-repo-seo; auth/provider logic adapted from
Bhanunamikaze/Agentic-SEO-Skill (MIT License)
https://github.com/Bhanunamikaze/Agentic-SEO-Skill
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://api.github.com"
USER_AGENT = "github-repo-seo-skill (+https://github.com/Royo-Qiao/github-repo-seo)"

_TOKEN_CACHE: str | None = None
_GH_AUTH_CACHE: dict | None = None


class GitHubAPIError(RuntimeError):
    """Raised when GitHub API requests fail terminally."""

    def __init__(self, message: str, status: int | None = None, details: dict | None = None):
        super().__init__(message)
        self.status = status
        self.details = details or {}


# ---------------------------------------------------------------------------
# Token / auth resolution
# ---------------------------------------------------------------------------

def get_token(cli_token: str = "") -> str:
    """Resolve a GitHub token from CLI arg, env vars, or `gh auth token`.

    Returns "" when nothing is available; callers decide how to degrade.
    """
    global _TOKEN_CACHE
    if cli_token:
        return cli_token.strip()
    if _TOKEN_CACHE is not None:
        return _TOKEN_CACHE

    for env_key in ("GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(env_key, "").strip()
        if value:
            _TOKEN_CACHE = value
            return value

    if gh_authenticated():
        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True, text=True, check=False, timeout=15,
            )
            token = (result.stdout or "").strip()
            if result.returncode == 0 and token:
                _TOKEN_CACHE = token
                return token
        except Exception:
            pass

    _TOKEN_CACHE = ""
    return ""


def gh_available() -> bool:
    """Return True when the GitHub CLI is on PATH."""
    try:
        result = subprocess.run(
            ["gh", "--version"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False, text=True,
        )
        return result.returncode == 0
    except Exception:
        return False


def gh_authenticated() -> bool:
    """Return True when `gh` is logged into github.com."""
    global _GH_AUTH_CACHE
    if _GH_AUTH_CACHE is not None:
        return _GH_AUTH_CACHE["authenticated"]
    details = {"available": gh_available(), "authenticated": False}
    if details["available"]:
        try:
            result = subprocess.run(
                ["gh", "auth", "status", "-h", "github.com"],
                capture_output=True, text=True, check=False, timeout=15,
            )
            text = ((result.stdout or "") + "\n" + (result.stderr or "")).lower()
            details["authenticated"] = (
                "logged in to github.com" in text
                and "failed to log in" not in text
                and "not logged into" not in text
            )
        except Exception:
            pass
    _GH_AUTH_CACHE = details
    return details["authenticated"]


def auth_context(token: str = "") -> dict:
    """Describe the effective auth mode for reports."""
    if token:
        mode = "token"
    elif gh_authenticated():
        mode = "gh-cli"
    else:
        mode = "unauthenticated"
    return {
        "token_present": bool(token),
        "gh_available": gh_available(),
        "gh_authenticated": gh_authenticated(),
        "mode": mode,
    }


def token_setup_hint() -> str:
    """Human-readable instructions for configuring API auth."""
    return (
        "No GitHub token found. Configure one of:\n"
        "  1) export GH_TOKEN=<your_pat>      # fine-grained PAT, no scopes needed for public repos\n"
        "  2) export GITHUB_TOKEN=<your_pat>\n"
        "  3) gh auth login                    # the skill falls back to `gh auth token`\n"
        "Without auth, the GitHub Search API is limited to ~10 requests/minute and\n"
        "the topic-competition module will likely fail. Create a token at:\n"
        "  https://github.com/settings/tokens"
    )


# ---------------------------------------------------------------------------
# Repo slug helpers
# ---------------------------------------------------------------------------

def normalize_repo_slug(value: str) -> str:
    """Normalize a repo identifier (URL, ssh, owner/repo) to owner/repo."""
    if not value:
        return ""
    text = value.strip()
    text = re.sub(r"\.git$", "", text)
    if text.startswith("git@github.com:"):
        text = text.split(":", 1)[1]
    elif text.startswith(("https://github.com/", "http://github.com/", "www.github.com/")):
        text = urllib.parse.urlparse(text).path.strip("/")
    parts = [p for p in text.split("/") if p]
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return ""


def infer_repo_from_git(cwd: str = ".") -> str:
    """Infer owner/repo from the local git origin remote."""
    try:
        output = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=cwd, stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except Exception:
        return ""
    return normalize_repo_slug(output)


def resolve_repo(repo: str | None = None, cwd: str = ".") -> str:
    """Resolve slug from explicit value, or from git origin when given a local path."""
    slug = normalize_repo_slug(repo or "")
    if slug:
        return slug
    if repo and os.path.isdir(repo):
        inferred = infer_repo_from_git(cwd=repo)
        if inferred:
            return inferred
    inferred = infer_repo_from_git(cwd=cwd)
    if inferred:
        return inferred
    raise GitHubAPIError(
        "Could not resolve repository. Pass owner/repo, a GitHub URL, "
        "or run inside a git repo with an origin remote."
    )


def parse_repo_slug(repo: str) -> tuple[str, str]:
    """Return (owner, name) for a slug."""
    slug = normalize_repo_slug(repo)
    parts = slug.split("/")
    if len(parts) != 2:
        raise GitHubAPIError(f"Invalid repository slug: {repo}")
    return parts[0], parts[1]


# ---------------------------------------------------------------------------
# HTTP access
# ---------------------------------------------------------------------------

def _headers(token: str = "") -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": USER_AGENT,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _http(method: str, url: str, params: dict | None, body: dict | None,
          headers: dict, timeout: int) -> tuple[int, object, str]:
    """One stdlib HTTP call. Returns (status, headers, text); never raises on
    HTTP error statuses — the caller decides retry/raise policy."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers = {**headers, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.headers, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:  # error statuses still carry headers/body
        return exc.code, exc.headers, (exc.read() or b"").decode("utf-8", errors="replace")


def _gh_api_json(path: str, params: dict | None = None, timeout: int = 30,
                 method: str = "GET", body: dict | None = None) -> dict:
    """Call the API via `gh api` (uses the CLI's own auth)."""
    if not gh_available():
        raise GitHubAPIError("GitHub CLI (`gh`) is not available.")
    endpoint = path.replace(API_BASE, "", 1).lstrip("/")
    cmd = ["gh", "api", endpoint, "--method", method.upper()]
    input_data = None
    if body is not None:
        cmd += ["--input", "-"]
        input_data = json.dumps(body)
    else:
        for key, value in (params or {}).items():
            cmd += ["-f", f"{key}={value}"]
    try:
        result = subprocess.run(cmd, input=input_data, capture_output=True, text=True,
                                timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise GitHubAPIError(f"gh api timed out after {timeout}s") from exc
    if result.returncode != 0:
        raise GitHubAPIError(f"gh api error: {(result.stderr or '').strip() or 'unknown'}")
    payload = (result.stdout or "").strip()
    return json.loads(payload) if payload else {}


def fetch_json(
    path: str,
    token: str = "",
    params: dict | None = None,
    provider: str = "auto",
    timeout: int = 25,
    retries: int = 2,
    method: str = "GET",
    body: dict | None = None,
) -> dict:
    """Fetch a GitHub API endpoint and return the parsed payload.

    provider:
      auto  - REST with token when present, else `gh api` when authenticated,
              else unauthenticated REST (subject to 60 req/h limit).
      api   - REST only.
      gh    - `gh api` only.

    method/body: defaults to GET; pass method="PATCH" with body for updates
    (e.g. repo description). Mutating calls require token or gh auth.
    Gotcha: PATCH /repos silently ignores the `topics` field — use the
    dedicated PUT /repos/{owner}/{repo}/topics with body {"names": [...]}.

    Raises GitHubAPIError on terminal failure.
    """
    mode = (provider or "auto").lower()
    if mode == "gh":
        return _gh_api_json(path, params=params, timeout=timeout, method=method, body=body)

    url = path if path.startswith("http") else f"{API_BASE}{path}"
    use_token = token
    if mode == "auto" and not token and gh_authenticated():
        try:
            return _gh_api_json(path, params=params, timeout=timeout, method=method, body=body)
        except GitHubAPIError:
            pass  # fall through to unauthenticated REST

    attempt = 0
    while True:
        try:
            status, resp_headers, text = _http(method.upper(), url, params, body,
                                               _headers(use_token), timeout)
        except (urllib.error.URLError, OSError) as exc:  # DNS / refused / timed out
            if attempt < retries:
                time.sleep(2 ** attempt)
                attempt += 1
                continue
            raise GitHubAPIError(f"Network error calling GitHub API: {exc}") from exc

        if status < 400:
            return json.loads(text) if text.strip() else {}

        remaining = resp_headers.get("X-RateLimit-Remaining")
        reset = resp_headers.get("X-RateLimit-Reset")
        if attempt < retries and status in (429, 500, 502, 503, 504):
            time.sleep(min(30, 2 ** attempt + 1))
            attempt += 1
            continue
        if attempt < retries and status == 403 and remaining == "0" and reset:
            try:
                wait = max(1, min(30, int(reset) - int(time.time()) + 1))
            except ValueError:
                wait = 5
            time.sleep(wait)
            attempt += 1
            continue

        try:
            detail = json.loads(text)
        except ValueError:
            detail = {"raw": text[:500]}
        message = detail.get("message", f"GitHub API error: HTTP {status}")
        raise GitHubAPIError(message, status=status, details=detail)
