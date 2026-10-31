"""Shared project facts for query selection, copy, and promotion drafts."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PROJECT_TYPES = ("auto", "cli", "library", "ui", "dataset", "list", "skill", "docs")
TEXT_FIELDS = ("summary", "audience", "problem", "differentiator", "goal")


def load_context(path: str) -> dict:
    """Read an explicitly supplied context JSON; its claims remain user-provided."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Context must be a JSON object.")
    for key in TEXT_FIELDS:
        if key in data and not isinstance(data[key], str):
            raise ValueError(f"Context {key} must be a string.")
    for key in ("queries", "channels"):
        if key in data and (not isinstance(data[key], list) or any(not isinstance(v, str) for v in data[key])):
            raise ValueError(f"Context {key} must be a list of strings.")
    if data.get("project_type", "auto") not in PROJECT_TYPES:
        raise ValueError("Unsupported context project_type.")
    return data


def readme_summary(markdown: str) -> str:
    """Use the first real introduction paragraph, without inventing capabilities."""
    lines = []
    in_fence = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if stripped.startswith("##") and lines:
            break
        if not stripped:
            if lines:
                break
            continue
        if stripped.startswith(("#", "![", "[![", "<", "|", "<!--")):
            continue
        if re.match(r"^\[[^\]]+\]:", stripped):
            continue
        lines.append(stripped.lstrip("> "))
        if len(lines) == 4:
            break
    return " ".join(lines)[:500]


def local_facts(path: str | None) -> list[dict]:
    """Read known manifests only; report documented commands without running them."""
    if not path or not Path(path).is_dir():
        return []
    root = Path(path).resolve()
    facts = []
    package = root / "package.json"
    if package.is_file() and not package.resolve().is_relative_to(root):
        facts.append({"kind": "unavailable", "text": "Manifest symlink points outside the local repository", "source": "package.json"})
    elif package.is_file():
        try:
            data = json.loads(package.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for name, command in (data.get("scripts") or {}).items():
                    if isinstance(command, str):
                        facts.append({"kind": "command", "text": f"npm run {name}", "definition": command,
                                      "source": package.relative_to(root).as_posix(), "confidence": "Confirmed", "executed": False})
                if data.get("engines"):
                    facts.append({"kind": "runtime", "text": json.dumps(data["engines"], ensure_ascii=False),
                                  "source": package.relative_to(root).as_posix(), "confidence": "Confirmed"})
        except (OSError, ValueError, AttributeError):
            facts.append({"kind": "unavailable", "text": "package.json could not be parsed", "source": package.relative_to(root).as_posix()})
    for filename in ("pyproject.toml", "Cargo.toml", "go.mod"):
        manifest = root / filename
        if not manifest.is_file():
            continue
        if not manifest.resolve().is_relative_to(root):
            facts.append({"kind": "unavailable", "text": "Manifest symlink points outside the local repository", "source": filename})
            continue
        try:
            text = manifest.read_text(encoding="utf-8")
        except OSError:
            facts.append({"kind": "unavailable", "text": "Manifest could not be read", "source": manifest.relative_to(root).as_posix()})
            continue
        for line in text.splitlines():
            if re.match(r"\s*(requires-python\s*=|rust-version\s*=|go\s+\d)", line):
                facts.append({"kind": "runtime", "text": line.strip(), "source": manifest.relative_to(root).as_posix(), "confidence": "Confirmed"})
    return facts


def collect_context(meta: dict, markdown: str, supplied: dict | None = None,
                    local_path: str | None = None, project_type: str = "auto") -> dict:
    supplied = supplied or {}
    summary = supplied.get("summary") or meta.get("description") or readme_summary(markdown)
    kind = project_type if project_type != "auto" else supplied.get("project_type", "auto")
    if kind == "auto":
        text = (str(meta.get("name", "")) + " " + summary + " " + markdown[:4000]).lower()
        kind = ("skill" if "skill.md" in text else "list" if "awesome-" in text or "curated list" in text
                else "dataset" if "dataset" in text or "数据集" in text else "library" if "sdk" in text or "library" in text
                else "ui" if any(term in text for term in ("web ui", "web wizard", "dashboard", "界面", "向导")) else "cli")
    facts = local_facts(local_path)
    source = "user-context" if supplied.get("summary") else "metadata.description" if meta.get("description") else "README introduction"
    context = {key: supplied.get(key, "") for key in TEXT_FIELDS}
    context.update({"summary": summary, "summary_source": source, "project_type": kind,
                    "project_type_source": "explicit" if project_type != "auto" or supplied.get("project_type") else "heuristic",
                    "queries": list(dict.fromkeys(q.strip() for q in supplied.get("queries", []) if q.strip()))[:8],
                    "channels": supplied.get("channels", [])[:2], "facts": facts,
                    "evidence": [{"source": source, "text": summary}] if summary else [],
                    "limitations": ["Project type is a selectable heuristic; user context is not independently verified."]})
    code_blocks = re.findall(r"(?ms)^```([^\n]*)\n(.*?)^```\s*$", markdown)
    context["documented_examples"] = [{"language": lang.strip(), "content": body.strip()[:1500],
                                       "source": "README", "executed": False} for lang, body in code_blocks[:3]]
    return context


def promotion_plan(meta: dict, context: dict) -> dict:
    """Return reviewable drafts based on observed copy, never publish them."""
    summary = context.get("summary", "")
    url = f"https://github.com/{meta['full_name']}" if meta.get("full_name") else ""
    audience = context.get("audience") or "需要项目所述功能的开发者"
    goal = context.get("goal") or "阅读快速开始并试用；记录上手反馈"
    channels = context.get("channels") or ["相关技术社区", "项目发布记录与教程"]
    drafts = []
    if summary and url:
        for index, channel in enumerate(channels):
            lead = f"{meta.get('name', meta['full_name'])}：{summary}" if index == 0 else f"项目介绍：{summary}"
            drafts.append({"channel": channel, "audience": audience, "status": "draft",
                           "text": f"{lead}\n\n{url}", "cta": goal,
                           "evidence": context.get("evidence", []), "rationale": "按受众与真实用例选择；发布前核查渠道规则。"})
    return {"goal": goal, "drafts": drafts,
            "materials": ["核对项目简介与实际能力", "准备一个真实输入与预期输出", "确认快速开始可用"],
            "review": [{"day": 0, "action": "记录基线、修复资料并准备素材"},
                       {"day": 7, "action": "复查访问、clone、有效反馈及已提交清单状态"},
                       {"day": 14, "action": "对比同口径搜索样本与流量；记录变化，避免自动归因"}],
            "limitations": ["These are drafts and a review plan; nothing has been published or scheduled."]}


def main():
    parser = argparse.ArgumentParser(description="Inspect local project context without executing code.")
    parser.add_argument("readme")
    parser.add_argument("--context")
    parser.add_argument("--local-path")
    parser.add_argument("--project-type", choices=PROJECT_TYPES, default="auto")
    args = parser.parse_args()
    supplied = load_context(args.context) if args.context else {}
    markdown = Path(args.readme).read_text(encoding="utf-8")
    print(json.dumps(collect_context({}, markdown, supplied, args.local_path, args.project_type), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
