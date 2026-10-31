#!/usr/bin/env python3
"""Collect GitHub's 14-day traffic windows; archive only when requested.

Daily totals are upserted by UTC date. Unique visitors/cloners and referral
windows cannot be summed into a longer-period unique count.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from github_api import GitHubAPIError, fetch_json, get_token, normalize_repo_slug, resolve_repo

SCHEMA_VERSION = 1
ENDPOINTS = {"views": "views", "clones": "clones",
             "referrers": "popular/referrers", "paths": "popular/paths"}
LIMITATIONS = [
    "Views, full clones, referrers and popular paths cover only the past 14 days, using UTC day boundaries.",
    "Referrers and popular paths contain only the top 10 entries per 14-day observation window.",
    "Traffic requires repository write access; fine-grained tokens need Administration (read). Unavailable data is unknown, not zero.",
    "Unique visitors/cloners can repeat across dates; daily or rolling-window uniques must not be summed into longer-period uniques.",
    "Overlapping referral/path windows must not be summed. Traffic changes alone do not establish SEO attribution.",
]


def _nonnegative(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _utc_date(timestamp: str) -> str:
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("Traffic timestamps must use UTC")
    return parsed.date().isoformat()


def _validated_payload(name: str, payload: object) -> object:
    """Retain only expected data fields; malformed data is not archived as zero."""
    if name in ("views", "clones"):
        if not isinstance(payload, dict) or not all(_nonnegative(payload.get(k)) for k in ("count", "uniques")):
            raise ValueError(f"Invalid {name} totals")
        days = payload.get(name)
        if not isinstance(days, list):
            raise ValueError(f"Invalid {name} daily sample")
        cleaned = []
        seen_dates = set()
        for item in days:
            if not isinstance(item, dict) or not isinstance(item.get("timestamp"), str):
                raise ValueError(f"Invalid {name} daily entry")
            date = _utc_date(item["timestamp"])
            if date in seen_dates or not all(_nonnegative(item.get(k)) for k in ("count", "uniques")):
                raise ValueError(f"Invalid or repeated {name} date")
            seen_dates.add(date)
            cleaned.append({"timestamp": item["timestamp"], "count": item["count"], "uniques": item["uniques"]})
        return {"count": payload["count"], "uniques": payload["uniques"], name: cleaned}
    if not isinstance(payload, list):
        raise ValueError(f"Invalid {name} sample")
    required = "referrer" if name == "referrers" else "path"
    cleaned = []
    for item in payload[:10]:
        if not isinstance(item, dict) or not isinstance(item.get(required), str) or not all(
                _nonnegative(item.get(k)) for k in ("count", "uniques")):
            raise ValueError(f"Invalid {name} entry")
        row = {required: item[required], "count": item["count"], "uniques": item["uniques"]}
        if name == "paths":
            row["title"] = item.get("title")
        cleaned.append(row)
    return cleaned


def _load_archive(path: Path, repo: str) -> dict:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "repo": repo,
                "daily": {"views": {}, "clones": {}},
                "windows": {name: {} for name in ENDPOINTS}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or type(data.get("schema_version")) is not int
            or data["schema_version"] != SCHEMA_VERSION or data.get("repo") != repo
            or set(data) != {"schema_version", "repo", "daily", "windows"}):
        raise ValueError("Existing traffic archive has a different repository or unsupported schema")
    if not isinstance(data.get("daily"), dict) or not isinstance(data.get("windows"), dict):
        raise ValueError("Existing traffic archive is missing daily or window data")
    if set(data["daily"]) != {"views", "clones"} or set(data["windows"]) != set(ENDPOINTS):
        raise ValueError("Existing traffic archive has unexpected data fields")
    for name in ("views", "clones"):
        days = data["daily"].get(name)
        if not isinstance(days, dict):
            raise ValueError("Existing traffic archive has invalid daily data")
        for date, item in days.items():
            if (not isinstance(item, dict) or set(item) != {"timestamp", "count", "uniques"}
                    or not isinstance(item.get("timestamp"), str) or _utc_date(item["timestamp"]) != date):
                raise ValueError("Existing traffic archive has invalid date keys")
            if not all(_nonnegative(item.get(k)) for k in ("count", "uniques")):
                raise ValueError("Existing traffic archive has invalid daily counts")
    for name in ENDPOINTS:
        windows = data["windows"].get(name)
        if not isinstance(windows, dict):
            raise ValueError("Existing traffic archive has invalid window data")
        for timestamp, payload in windows.items():
            _utc_date(timestamp)
            if _validated_payload(name, payload) != payload:
                raise ValueError("Existing traffic archive has unexpected window fields")
    return data


def _archive(result: dict, archive_dir: str) -> None:
    owner, name = result["repo"].split("/")
    path = Path(archive_dir).expanduser().resolve() / owner / name / "traffic.json"
    if path.is_symlink() or path.parent.resolve() != path.parent:
        raise ValueError("Archive repository paths must not use symlink aliases")
    data = _load_archive(path, result["repo"])
    for kind in ENDPOINTS:
        if result[kind] is None:
            continue
        data["windows"][kind][result["observed_at_utc"]] = result[kind]
        if kind in ("views", "clones"):
            for item in result[kind][kind]:
                date = _utc_date(item["timestamp"])
                data["daily"][kind][date] = item
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=".traffic-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    result["archived_path"] = str(path)
    result["history"] = {kind: [dict(date=date, **item) for date, item in sorted(data["daily"][kind].items())]
                         for kind in ("views", "clones")}


def collect_traffic(repo: str, token: str = "", provider: str = "auto",
                    archive_dir: str | None = None) -> dict:
    """Read four endpoints independently; optional archives are isolated by repository."""
    slug = normalize_repo_slug(repo).lower()
    # Shared normalization validates both components, rejects traversal and
    # foreign URLs, and permits valid repository names such as .github.
    if not slug:
        raise ValueError("A valid owner/repo identifier is required")
    result = {"repo": slug, "status": "unavailable", "coverage": {},
              "limitations": list(LIMITATIONS),
              "observed_at_utc": datetime.now(timezone.utc).isoformat(),
              "archived_path": None, "archive_error": None,
              "history": {"views": [], "clones": []},
              **{name: None for name in ENDPOINTS}}
    for name, endpoint in ENDPOINTS.items():
        try:
            payload = fetch_json(f"/repos/{slug}/traffic/{endpoint}", token=token,
                                 provider=provider, params={"per": "day"} if name in ("views", "clones") else None)
            result[name] = _validated_payload(name, payload)
            result["coverage"][name] = {"status": "ok", "error": None}
        except (GitHubAPIError, ValueError, TypeError) as exc:
            result["coverage"][name] = {"status": "unavailable",
                                       "error": {"message": str(exc), "status": getattr(exc, "status", None)}}
            result["limitations"].append(f"{name} unavailable: {exc}")
    successful = sum(result[name] is not None for name in ENDPOINTS)
    result["status"] = "ok" if successful == 4 else "partial" if successful else "unavailable"
    if archive_dir is not None:
        try:
            _archive(result, archive_dir)
        except (OSError, ValueError, TypeError) as exc:
            result["archive_error"] = str(exc)
            result["limitations"].append(f"Archive was not updated: {exc}")
            if result["status"] == "ok":
                result["status"] = "partial"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Read GitHub 14-day traffic windows (JSON output).")
    parser.add_argument("repo", help="owner/repo, GitHub URL, or local clone")
    parser.add_argument("--archive-dir", help="explicitly save repository-isolated traffic history here")
    parser.add_argument("--token", default="", help="prefer GH_TOKEN environment variable")
    parser.add_argument("--provider", choices=["auto", "api", "gh"], default="auto")
    args = parser.parse_args()
    try:
        result = collect_traffic(resolve_repo(args.repo), get_token(args.token), args.provider, args.archive_dir)
    except (GitHubAPIError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
