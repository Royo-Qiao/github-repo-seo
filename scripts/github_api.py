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
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

API_BASE = "https://api.github.com"
USER_AGENT = "github-repo-seo-skill (+https://github.com/Royo-Qiao/github-repo-seo)"
MAX_RETRY_WAIT = 60  # stop rather than retrying before a longer server-requested wait

_TOKEN_CACHE: str | None = None
_GH_AUTH_CACHE: dict | None = None


class GitHubAPIError(RuntimeError):
    """Raised when GitHub API requests fail terminally."""

    def __init__(self, message: str, status: int | None = None, details: dict | None = None):
        super().__init__(message)
        self.status = status
        self.status_code = status
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
    """Accept only owner/repo or a GitHub repository URL/SSH remote."""
    if not value:
        return ""
    text = value.strip()
    if text.startswith("git@github.com:"):
        text = text.split(":", 1)[1]
    elif "://" in text or text.startswith("www.github.com/"):
        url = urllib.parse.urlparse(text if "://" in text else "https://" + text)
        if url.scheme not in ("http", "https", "ssh") or url.hostname not in ("github.com", "www.github.com"):
            return ""
        if url.scheme == "ssh" and url.username not in (None, "git"):
            return ""
        text = url.path.removeprefix("/").removesuffix("/")
    text = re.sub(r"\.git$", "", text)
    match = re.fullmatch(r"([A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)/([A-Za-z0-9_.-]+)", text)
    if not match or match.group(2) in (".", ".."):
        return ""
    return f"{match.group(1)}/{match.group(2)}"


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
    if repo and os.path.isdir(repo):
        inferred = infer_repo_from_git(cwd=repo)
        if inferred:
            return inferred
    elif repo:
        slug = normalize_repo_slug(repo)
        if slug:
            return slug
    else:
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


# State is shared by all collectors in this process, never persisted with credentials.
_COOLDOWNS: dict[str, float] = {}
_LAST_SEARCH: float | None = None


def _wait(seconds: float, reason: str) -> None:
    if seconds > 0:
        print(f"[github-api] {reason}; waiting {seconds:.1f}s", file=sys.stderr, flush=True)
        time.sleep(seconds)


def _before_request(bucket: str, authenticated: bool) -> None:
    global _LAST_SEARCH
    for key in ("all", bucket):
        remaining = _COOLDOWNS.get(key, 0) - time.time()
        if remaining > MAX_RETRY_WAIT:
            raise GitHubAPIError("GitHub rate-limit cooldown active; request skipped.", status=429,
                                 details={"retry_after_seconds": round(remaining, 1), "resource": key})
        if remaining > 0:
            _wait(remaining, f"{key} cooldown")
            _COOLDOWNS.pop(key, None)
    if bucket == "search":
        interval = 3.1 if authenticated else 6.1
        if _LAST_SEARCH is not None:
            _wait(max(0, interval - (time.monotonic() - _LAST_SEARCH)), "shared search pacing")
        _LAST_SEARCH = time.monotonic()


def _gh_http(path: str, params: dict | None, timeout: int,
             method: str, body: dict | None) -> tuple[int, dict, str]:
    """Keep status/headers on both successful and failed gh requests."""
    if not gh_available():
        raise GitHubAPIError("GitHub CLI (`gh`) is not available.")
    endpoint = path.replace(API_BASE, "", 1).lstrip("/")
    cmd = ["gh", "api", endpoint, "--include", "--method", method.upper()]
    data = None
    if body is not None:
        cmd += ["--input", "-"]
        data = json.dumps(body)
    else:
        for key, value in (params or {}).items():
            cmd += ["-f", f"{key}={value}"]
    try:
        result = subprocess.run(cmd, input=data, capture_output=True, text=True,
                                timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise GitHubAPIError(f"gh api timed out after {timeout}s") from exc
    output = (result.stdout or "").replace("\r\n", "\n")
    # Redirects can produce multiple HTTP header blocks. Decode the final one.
    status, headers = None, {}
    while output.startswith("HTTP/"):
        head, separator, rest = output.partition("\n\n")
        match = re.match(r"HTTP/\S+ (\d{3})", head)
        if not match or not separator:
            break
        status = int(match.group(1))
        headers = dict(line.split(":", 1) for line in head.splitlines()[1:] if ":" in line)
        headers = {key.strip().lower(): value.strip() for key, value in headers.items()}
        output = rest
    if status is None or (result.returncode and status < 400):
        raise GitHubAPIError("gh api failed without an HTTP error response.")
    return status, headers, output


def _gh_api_json(path: str, params: dict | None = None, timeout: int = 30,
                 method: str = "GET", body: dict | None = None) -> dict:
    return fetch_json(path, params=params, timeout=timeout, method=method, body=body, provider="gh")


def fetch_json(path: str, token: str = "", params: dict | None = None,
               provider: str = "auto", timeout: int = 25, retries: int = 2,
               method: str = "GET", body: dict | None = None) -> dict:
    """Shared pacing/retries for REST and gh. No provider switching on throttling.

    A single wait is bounded by MAX_RETRY_WAIT. Longer delays are retained as
    process-local cooldowns so later collectors fail explicitly without HTTP.
    Independent processes/accounts are not coordinated by this helper.
    """
    mode = (provider or "auto").lower()
    use_gh = mode == "gh" or (mode == "auto" and not token and gh_authenticated())
    url = path if path.startswith("http") else f"{API_BASE}{path}"
    bucket = "search" if urllib.parse.urlparse(url).path.startswith("/search/") else "core"
    for attempt in range(retries + 1):
        _before_request(bucket, bool(token) or use_gh)
        try:
            if use_gh:
                status, response_headers, text = _gh_http(path, params, timeout, method, body)
            else:
                status, response_headers, text = _http(method.upper(), url, params, body, _headers(token), timeout)
        except (urllib.error.URLError, OSError) as exc:
            if attempt < retries and method.upper() in ("GET", "HEAD"):
                _wait(2 ** attempt, "network retry")
                continue
            raise GitHubAPIError("Network error calling GitHub API") from exc
        headers = {key.lower(): value for key, value in response_headers.items()}
        remaining = headers.get("x-ratelimit-remaining")
        reset = headers.get("x-ratelimit-reset")
        retry_after = headers.get("retry-after")
        try:
            detail = json.loads(text) if text.strip() else {}
        except ValueError:
            raise GitHubAPIError("GitHub returned non-JSON response", status=status)
        if status < 400:
            if remaining == "0":
                try:
                    _COOLDOWNS[bucket] = max(time.time(), float(reset)) + 1
                except (ValueError, TypeError):
                    _COOLDOWNS[bucket] = time.time() + 60
            return detail
        message = detail.get("message", f"GitHub API error: HTTP {status}") if isinstance(detail, dict) else f"HTTP {status}"
        limited = status == 429 or (status == 403 and (remaining == "0" or retry_after is not None or "rate limit" in message.lower()))
        if limited:
            wait = 60 * (2 ** attempt)
            key = "all" if status == 429 or retry_after is not None or "secondary" in message.lower() else bucket
            if retry_after is not None:
                try:
                    wait = max(0, float(retry_after))
                except ValueError:
                    try:
                        wait = max(0, (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds())
                    except (ValueError, TypeError, OverflowError):
                        pass
            elif remaining == "0" and reset:
                try:
                    wait = max(1, float(reset) - time.time() + 1)
                except ValueError:
                    pass
            _COOLDOWNS[key] = time.time() + wait
            if attempt < retries and wait <= MAX_RETRY_WAIT and method.upper() in ("GET", "HEAD"):
                _wait(wait, f"HTTP {status} rate limit")
                _COOLDOWNS.pop(key, None)
                continue
            raise GitHubAPIError(message, status=status, details={"retry_after_seconds": wait, "resource": key})
        if status in (500, 502, 503, 504) and attempt < retries and method.upper() in ("GET", "HEAD"):
            _wait(2 ** attempt + 1, "server retry")
            continue
        raise GitHubAPIError(message, status=status, details=detail if isinstance(detail, dict) else {})
