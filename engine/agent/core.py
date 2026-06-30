"""共享基础设施 — _get_conn, _resolve_person, _validate_path, _build_cross_refs, _find_fact_archive, _extract_sections, Session。"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from engine.config import (
    Config, ROOT_DIR, OUTPUTS_ANALYSIS_DIR,
    FACTS_PEOPLE_DIR, FACTS_SELF_DIR,
    slug_display_name, load_config,
)
from engine.identity import IdentityPerson

# ---------------------------------------------------------------------------
# 安全路径校验
# ---------------------------------------------------------------------------

_ALLOWED_PREFIXES = (
    "skills/",
    "docs/wiki/",
    "docs/kb/",
    "data/outputs/analysis/",
    "data/outputs/reports/",
    "data/outputs/evaluations/",
    "plan/",
)


def _validate_path(path: str) -> Path:
    p = Path(path)
    resolved = (ROOT_DIR / p).resolve()
    if not str(resolved).startswith(str(ROOT_DIR.resolve())):
        raise ValueError(f"路径越界: {path}")
    rel = str(p).replace("\\", "/")
    if not any(rel.startswith(prefix) for prefix in _ALLOWED_PREFIXES):
        raise ValueError(f"不允许读取该目录: {path}")
    if not resolved.is_file():
        raise ValueError(f"文件不存在: {path}")
    return resolved


# ---------------------------------------------------------------------------
# 交叉引用
# ---------------------------------------------------------------------------

def _build_cross_refs(
    person: IdentityPerson | None = None,
    *,
    has_chat: bool = False,
    has_fact: bool = False,
    has_event: bool = False,
    has_analysis: bool = False,
    skill_hits: list[str] | None = None,
    wiki_hits: list[str] | None = None,
) -> str:
    lines = ["---", "**Cross-references:**"]
    if person:
        name = person.display_name
        pid = person.id
        slug = slug_display_name(name)
        if has_chat:
            lines.append(f"- chat: `{name}` → `agent chat \"{name}\" --recent 200`")
        if has_fact:
            lines.append(f"- fact: `data/customers/{slug}__{pid}.md` → `agent evidence \"{name}\"`")
        if has_event:
            lines.append(f"- event: `{pid}` → `agent evidence \"{name}\" --section timeline`")
        if has_analysis:
            lines.append(f"- analysis: `data/outputs/analysis/{slug}__{pid}/latest.yaml`")
    for s in (skill_hits or []):
        lines.append(f"- skill: `{s}` → `agent material show \"{s}\"`")
    for w in (wiki_hits or []):
        lines.append(f"- wiki: `{w}`")
    return "\n".join(lines)


def _find_fact_archive(person: IdentityPerson) -> Path | None:
    pid = person.id
    for d in (FACTS_PEOPLE_DIR, FACTS_SELF_DIR):
        if d.is_dir():
            for f in d.iterdir():
                if f.is_file() and f.suffix == ".md" and pid in f.stem:
                    return f
    return None


def _extract_sections(text: str) -> dict[str, str]:
    """按 ## 标题分割 Markdown 为 {section_name: content}。"""
    sections: dict[str, str] = {}
    current_name = "_header"
    current_lines: list[str] = []
    for line in text.split("\n"):
        if line.startswith("## "):
            sections[current_name] = "\n".join(current_lines).strip()
            current_name = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    sections[current_name] = "\n".join(current_lines).strip()
    return sections


# ---------------------------------------------------------------------------
# 连接管理
# ---------------------------------------------------------------------------

_local = threading.local()


def _get_conn():
    """获取连接。如果当前有 Session 连接，复用它；否则新建。"""
    if hasattr(_local, "session_conn") and _local.session_conn is not None:
        return _local.session_conn, _local.session_config
    from engine.importers.db_init import get_db
    config = load_config()
    conn = get_db(config.db_path)
    return conn, config


class Session:
    """上下文管理器，session 内复用同一个 DB 连接。

    用法：
        with Session() as (conn, config):
            # 连续调用多个工具时共享同一个连接
            from engine.tools import metrics, status
    """

    def __enter__(self):
        from engine.importers.db_init import get_db
        config = load_config()
        conn = get_db(config.db_path)
        _local.session_conn = conn
        _local.session_config = config
        return conn, config

    def __exit__(self, *args):
        if hasattr(_local, "session_conn") and _local.session_conn:
            _local.session_conn.close()
            _local.session_conn = None
            _local.session_config = None


def _resolve_person(conn, name: str) -> IdentityPerson | None:
    from engine.identity import resolve_contact
    from engine.facts import ensure_people_archives_migrated
    config = load_config()
    ensure_people_archives_migrated(conn, config.my_wxid)
    result = resolve_contact(conn, name)
    return result.person
