"""Read local publication materials without Git, credentials, or network I/O."""
from __future__ import annotations

import hashlib
from pathlib import Path


def _find(root: Path, directories: tuple[str, ...], names: tuple[str, ...]) -> Path | None:
    for directory in directories:
        folder = root / directory
        if not folder.is_dir() or not folder.resolve().is_relative_to(root):
            continue
        entries = {entry.name.lower(): entry for entry in folder.iterdir()}
        for name in names:
            candidate = entries.get(name.lower())
            if candidate is not None:
                return candidate
    return None


def _observe(root: Path, path: Path | None, *, read_text: bool = False) -> dict:
    if path is None:
        return {"status": "missing", "path": None}
    relative = path.relative_to(root).as_posix()
    if not path.resolve().is_relative_to(root):
        return {"status": "unavailable", "path": relative,
                "reason": "Symlink points outside the selected local repository."}
    try:
        if not path.is_file():
            return {"status": "unavailable", "path": relative, "reason": "Not a regular file."}
        data = path.read_bytes()
        result = {"status": "present", "path": relative, "sha256": hashlib.sha256(data).hexdigest()}
        if read_text:
            result["markdown"] = data.decode("utf-8")
        return result
    except (OSError, UnicodeError) as exc:
        return {"status": "unavailable", "path": relative,
                "reason": f"Local file could not be read ({type(exc).__name__})."}


def collect_local_evidence(path: str, label: str | None = None) -> dict:
    """Observed files use relative paths; GitHub-only fields stay unknown.

    A supplied owner/repo label is identification input, not proof that a remote
    exists or has matching settings. No origin lookup or subprocess is needed.
    """
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("--local-path must select an existing local directory.")
    specs = {
        "readme": ((".github", "", "docs"), ("README.md", "README.markdown", "README", "README.txt")),
        "license": (("",), ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "COPYING.md")),
        "contributing": ((".github", "", "docs"), ("CONTRIBUTING.md", "CONTRIBUTING")),
        "code_of_conduct": ((".github", "", "docs"), ("CODE_OF_CONDUCT.md", "CODE_OF_CONDUCT")),
        "security_policy": ((".github", "", "docs"), ("SECURITY.md", "SECURITY")),
    }
    files = {key: _observe(root, _find(root, directories, names), read_text=key == "readme")
             for key, (directories, names) in specs.items()}
    issue_folder = root / ".github" / "ISSUE_TEMPLATE"
    if issue_folder.is_dir() and issue_folder.resolve().is_relative_to(root):
        templates = sorted(p for p in issue_folder.iterdir() if p.suffix.lower() in (".md", ".yml", ".yaml")
                           and p.name.lower() not in ("config.yml", "config.yaml"))
        issue = _observe(root, templates[0] if templates else None)
    else:
        issue = _observe(root, _find(root, (".github", "", "docs"), ("ISSUE_TEMPLATE.md",)))
    files["issue_template"] = issue
    readme = files["readme"]
    markdown = readme.pop("markdown", None)
    findings = []
    for key, observation in files.items():
        if observation["status"] != "missing":
            continue
        findings.append({"area": f"Local {key}", "severity": "Warning" if key in ("readme", "license") else "Info",
                         "finding": f"No local {key} file found in the checked locations.",
                         "evidence": "Explicit local file inventory; remote/community defaults were not inspected.",
                         "fix": f"Review whether this project needs a {key} file before publishing.",
                         "confidence": "Confirmed", "evidence_tier": "local-file-observation"})
    limitations = ["Offline local snapshot only; no GitHub settings, topics, search, traffic, or remote defaults were observed.",
                   "Local file presence is not verification of legal terms, community policy quality, or runnable commands."]
    for key, observation in files.items():
        if observation["status"] == "unavailable":
            limitations.append(f"Local {key}: {observation['reason']}")
    return {"repo": label or f"local:{root.name}", "name": root.name,
            "markdown": markdown, "files": files,
            "audit": {"status": "partial", "coverage": {"metadata": "unavailable", "topics": "unavailable", "community": "local-only"},
                      "metadata": {"name": root.name}, "community_profile": {}, "findings": findings,
                      "summary": {"score": None, "rating": "Unknown", "critical": 0, "warning": len([f for f in findings if f['severity'] == 'Warning'])},
                      "limitations": limitations}}
