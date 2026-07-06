"""事实追溯视图 — agent_evidence。"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime

import yaml

from engine.config import Config, ROOT_DIR
from engine.identity import IdentityPerson
from engine.facts.people_archive import get_person_archive_path
from engine.agent.core import _build_cross_refs

_SECTION_MAP = {
    "timeline": "关系时间线",
    "evaluations": "当前状态",
    "notes": "Notes",
    "dates": "Dates",
}


def _dedup_timeline(content: str) -> str:
    """去重时间线中的事件条目（- [date] type: detail 格式），保留首次出现。"""
    seen: set[str] = set()
    result: list[str] = []
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("- [") and "] " in stripped:
            if stripped in seen:
                continue
            seen.add(stripped)
        result.append(line)
    return "\n".join(result)


def agent_evidence(
    conn: sqlite3.Connection, config: Config, person: IdentityPerson, *,
    section: str = "all", since_date: str | None = None,
) -> str:
    archive_path = get_person_archive_path(person, my_wxid=config.my_wxid)
    if not archive_path or not archive_path.is_file():
        return f"# Evidence: {person.display_name}\n\n未找到事实档案。"
    raw = archive_path.read_text(encoding="utf-8")
    rel_path = archive_path.relative_to(ROOT_DIR)
    frontmatter = {}
    body = raw
    if raw.startswith("---"):
        end = raw.find("---", 3)
        if end > 0:
            try:
                frontmatter = yaml.safe_load(raw[3:end]) or {}
            except Exception:
                pass
            body = raw[end + 3:].strip()
    sections: dict[str, str] = {}
    current_name = "_header"
    current_lines: list[str] = []
    for line in body.split("\n"):
        if line.startswith("## "):
            sections[current_name] = "\n".join(current_lines).strip()
            current_name = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    sections[current_name] = "\n".join(current_lines).strip()
    parts = [f"# Evidence: {person.display_name}\n"]
    parts.append(f"- 来源: `{rel_path}`")
    parts.append(f"- 更新时间: {frontmatter.get('updated_at', 'N/A')}")
    parts.append(f"- section 过滤: {section}")
    if since_date:
        parts.append(f"- since: {since_date}")
    parts.append("")
    if section == "all":
        target_sections = sections
    else:
        cn_name = _SECTION_MAP.get(section, section)
        target_sections = {}
        for k, v in sections.items():
            if k == "_header" or k == cn_name:
                target_sections[k] = v
    since_ts = None
    if since_date:
        try:
            since_ts = int(datetime.strptime(since_date, "%Y-%m-%d").timestamp())
        except ValueError:
            pass
    for name, content in target_sections.items():
        if name == "_header":
            continue
        if not content:
            continue
        if name == "关系时间线":
            content = _dedup_timeline(content)
        parts.append(f"## {name}\n")
        if name == "关系时间线" and since_ts:
            entries = re.split(r"(?=^### )", content, flags=re.MULTILINE)
            for entry in entries:
                if not entry.strip():
                    continue
                date_match = re.match(r"### (\d{4}-\d{2}-\d{2})", entry)
                if date_match:
                    try:
                        entry_ts = int(datetime.strptime(date_match.group(1), "%Y-%m-%d").timestamp())
                        if entry_ts < since_ts:
                            continue
                    except ValueError:
                        pass
                parts.append(f"- Source: fact_archive (`{rel_path}`)")
                parts.append(entry.rstrip())
                parts.append("")
        else:
            parts.append(content)
            parts.append("")
    parts.append(_build_cross_refs(person, has_chat=True, has_event=True))
    return "\n".join(parts)
