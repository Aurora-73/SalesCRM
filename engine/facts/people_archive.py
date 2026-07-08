"""人物事实档案的路径、迁移和写入。"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from engine.config import CUSTOMERS_DIR, FACTS_PEOPLE_DIR, FACTS_SELF_DIR, LEGACY_WIKI_PEOPLE_DIR, slug_display_name
from engine.identity import IdentityPerson


def ensure_people_archives_migrated(conn, my_wxid: str) -> None:
    """将旧的 wiki/people 档案迁移到 data/facts。"""
    from engine.identity import resolve_contact

    FACTS_PEOPLE_DIR.mkdir(parents=True, exist_ok=True)
    FACTS_SELF_DIR.mkdir(parents=True, exist_ok=True)
    if not LEGACY_WIKI_PEOPLE_DIR.exists():
        return

    for path in LEGACY_WIKI_PEOPLE_DIR.glob("*.md"):
        if path.name == "_TEMPLATE.md":
            target = FACTS_PEOPLE_DIR / "_TEMPLATE.md"
            if not target.exists():
                shutil.move(str(path), str(target))
            continue

        result = resolve_contact(conn, path.stem)
        if result.person is None:
            continue
        person = result.person
        target = get_person_archive_path(person, my_wxid=my_wxid)
        if target.exists():
            try:
                path.unlink()
            except OSError:
                pass
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        content = path.read_text(encoding="utf-8")
        target.write_text(_ensure_frontmatter(content, person), encoding="utf-8")
        path.unlink()

    try:
        LEGACY_WIKI_PEOPLE_DIR.rmdir()
        LEGACY_WIKI_PEOPLE_DIR.parent.rmdir()
    except OSError:
        pass


def get_person_archive_path(person: IdentityPerson, *, my_wxid: str = "") -> Path:
    slug = slug_display_name(person.display_name)
    filename = f"{slug}__{person.id}.md"
    if _is_self_person(person, my_wxid):
        return FACTS_SELF_DIR / filename
    return FACTS_PEOPLE_DIR / filename


def append_note(person: IdentityPerson, text: str, *, my_wxid: str = "") -> Path:
    path = get_person_archive_path(person, my_wxid=my_wxid)
    content = _load_or_init_archive(path, person)
    section = "## Notes"
    content = _ensure_section(content, section)
    entry = f"- {datetime.now():%Y-%m-%d %H:%M} {text.strip()}"
    content = _append_to_section(content, section, entry)
    content = _update_timestamp(content)
    path.write_text(content, encoding="utf-8")
    return path


def append_event(
    person: IdentityPerson,
    event_date: str,
    event_type: str,
    detail: str,
    *,
    my_wxid: str = "",
) -> tuple[Path, bool]:
    """将事件写入事实档案的客户时间线。返回 (path, is_new)：is_new=False 表示重复跳过。"""
    path = get_person_archive_path(person, my_wxid=my_wxid)
    content = _load_or_init_archive(path, person)
    section = "## 客户时间线"
    content = _ensure_section(content, section)
    entry = f"- [{event_date}] {event_type}: {detail}"
    if _event_entry_exists(content, section, entry):
        return path, False
    content = _append_to_section(content, section, entry)
    content = _update_timestamp(content)
    path.write_text(content, encoding="utf-8")
    return path, True


def _event_entry_exists(content: str, section: str, entry: str) -> bool:
    """检查事件条目是否已存在于该 section 中（基于文本精确匹配）。"""
    lines = content.splitlines()
    in_section = False
    entry_norm = entry.strip()
    for line in lines:
        if line.strip() == section:
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section and line.strip() == entry_norm:
            return True
    return False


def append_date_entry(
    person: IdentityPerson,
    *,
    date_text: str | None,
    location: str | None,
    rating: int | None,
    my_wxid: str = "",
) -> Path:
    path = get_person_archive_path(person, my_wxid=my_wxid)
    content = _load_or_init_archive(path, person)
    section = "## Dates"
    content = _ensure_section(content, section)

    title = date_text or datetime.now().strftime("%Y-%m-%d")
    parts = []
    if location:
        parts.append(f"地点：{location}")
    if rating is not None:
        parts.append(f"评分：{rating}/5")
    detail = "；".join(parts) if parts else "待补充"
    entry = f"### {title}\n- {detail}"
    content = _append_to_section(content, section, entry)
    content = _update_timestamp(content)
    path.write_text(content, encoding="utf-8")
    return path


def rename_person_archive(person: IdentityPerson, new_display_name: str, *, my_wxid: str = "") -> Path | None:
    old_path = get_person_archive_path(person, my_wxid=my_wxid)
    updated_person = IdentityPerson(
        id=person.id,
        display_name=new_display_name,
        real_name=person.real_name,
        note=person.note,
        accounts=person.accounts,
        aliases=person.aliases,
    )
    new_path = get_person_archive_path(updated_person, my_wxid=my_wxid)
    if old_path == new_path:
        return new_path
    if not old_path.exists():
        return new_path
    new_path.parent.mkdir(parents=True, exist_ok=True)
    if new_path.exists():
        return new_path
    old_path.rename(new_path)
    return new_path


def _load_or_init_archive(path: Path, person: IdentityPerson) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return _ensure_frontmatter(path.read_text(encoding="utf-8"), person)
    return _initial_archive(person)


def _initial_archive(person: IdentityPerson) -> str:
    now = datetime.now().strftime("%Y-%m-%d")
    wxids = " / ".join(a.wxid for a in person.accounts if a.wxid) or "N/A"
    nickname = next((a.nickname for a in person.accounts if a.nickname), "")
    return (
        f"---\n"
        f"person_id: {person.id}\n"
        f"display_name: {person.display_name}\n"
        f"updated_at: {datetime.now().isoformat(timespec='seconds')}\n"
        f"---\n\n"
        f"# {person.display_name}\n\n"
        f"> 创建日期：{now}\n"
        f"> 最后更新：{now}\n"
        f"> person_id：{person.id}\n"
        f"> wxid：{wxids}\n"
        f"> 微信昵称：{nickname}\n\n"
        f"## 基本信息\n\n"
        f"## 数据概览\n\n"
        f"## 客户时间线\n\n"
        f"## 当前状态\n\n"
        f"## 关键信息\n\n"
        f"## Dates\n\n"
        f"## Notes\n"
    )


def _ensure_frontmatter(content: str, person: IdentityPerson) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    if content.startswith("---\n"):
        if "person_id:" not in content.split("---", 2)[1]:
            content = re.sub(r"^---\n", f"---\nperson_id: {person.id}\ndisplay_name: {person.display_name}\nupdated_at: {now}\n", content, count=1)
        return content
    return (
        f"---\n"
        f"person_id: {person.id}\n"
        f"display_name: {person.display_name}\n"
        f"updated_at: {now}\n"
        f"---\n\n{content}"
    )


def _update_timestamp(content: str) -> str:
    """刷新 frontmatter 的 updated_at 和 body 的'最后更新'行。"""
    now_iso = datetime.now().isoformat(timespec="seconds")
    now_date = datetime.now().strftime("%Y-%m-%d")
    content = re.sub(r"(updated_at:\s*).+", rf"\g<1>{now_iso}", content)
    content = re.sub(r"(>\s*最后更新[：:]\s*).+", rf"\g<1>{now_date}", content)
    return content


def _ensure_section(content: str, section: str) -> str:
    if section in content:
        return content
    suffix = "" if content.endswith("\n") else "\n"
    return f"{content}{suffix}\n{section}\n"


def _append_to_section(content: str, section: str, entry: str) -> str:
    lines = content.splitlines()
    header_index = None
    for i, line in enumerate(lines):
        if line.strip() == section:
            header_index = i
            break
    if header_index is None:
        return f"{content.rstrip()}\n\n{section}\n{entry}\n"

    insert_at = len(lines)
    for i in range(header_index + 1, len(lines)):
        if lines[i].startswith("## "):
            insert_at = i
            break

    entry_lines = entry.splitlines()
    if insert_at > 0 and lines[insert_at - 1].strip():
        entry_lines = [""] + entry_lines
    lines[insert_at:insert_at] = entry_lines
    return "\n".join(lines).rstrip() + "\n"


def _is_self_person(person: IdentityPerson, my_wxid: str) -> bool:
    if not my_wxid:
        return False
    return any(account.wxid == my_wxid for account in person.accounts)
