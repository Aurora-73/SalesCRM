"""身份管理 — agent_contact, agent_exclude, agent_failure, agent_sticker。"""
from __future__ import annotations

from datetime import datetime

from engine.identity import IdentityPerson
from engine.agent.core import _get_conn, _resolve_person
from engine.config import slug_display_name


def _format_person_md(person: IdentityPerson) -> str:
    lines = [f"# {person.display_name}\n", f"- person_id: {person.id}"]
    if person.real_name:
        lines.append(f"- 真实姓名: {person.real_name}")
    if person.note:
        lines.append(f"- 备注: {person.note}")
    lines.append("\n## 账号")
    for a in person.accounts:
        parts = [a.wxid or a.id]
        if a.remark:
            parts.append(f"备注={a.remark}")
        if a.nickname:
            parts.append(f"昵称={a.nickname}")
        lines.append(f"- {' | '.join(parts)}")
    lines.append("\n## 别名")
    for alias in person.aliases:
        lines.append(f"- {alias['type']}: {alias['value']}")
    return "\n".join(lines)


def agent_contact(query: str, action: str = "search", **kwargs) -> str:
    from engine.identity import (
        resolve_contact, add_alias, remove_alias, set_display_name,
        link_account, merge_people, audit_identity, bootstrap_identity,
    )
    from engine.facts import ensure_people_archives_migrated, rename_person_archive

    conn, config = _get_conn()
    try:
        ensure_people_archives_migrated(conn, config.my_wxid)
        if action == "init":
            stats = bootstrap_identity(conn)
            ensure_people_archives_migrated(conn, config.my_wxid)
            return (f"身份目录初始化完成: "
                    f"新增 {stats['people']} 人 / {stats['accounts']} 账号 / "
                    f"{stats['aliases']} 别名 / 合并 {stats['merges']} 组")
        if action == "search":
            result = resolve_contact(conn, query)
            if result.person:
                return _format_person_md(result.person)
            return f"未找到联系人: {query}"
        if action == "show":
            result = resolve_contact(conn, query)
            if not result.person:
                return f"未找到联系人: {query}"
            if kwargs.get("set_name"):
                old_person = result.person
                set_display_name(conn, result.person.id, kwargs["set_name"])
                rename_person_archive(old_person, kwargs["set_name"], my_wxid=config.my_wxid)
                result = resolve_contact(conn, result.person.id)
            return _format_person_md(result.person)
        if action == "alias":
            result = resolve_contact(conn, query)
            if not result.person:
                return f"未找到联系人: {query}"
            ok = add_alias(conn, result.person.id, kwargs.get("type", ""), kwargs.get("value", ""),
                           sensitivity=kwargs.get("sensitivity", "normal"))
            return "已添加别名" if ok else "别名已存在或添加失败"
        if action == "remove_alias":
            result = resolve_contact(conn, query)
            if not result.person:
                return f"未找到联系人: {query}"
            deleted = remove_alias(
                conn, result.person.id,
                kwargs.get("type", ""),
                value=kwargs.get("value"),
            )
            if deleted:
                scope = f"type={kwargs.get('type', '')}, value={kwargs.get('value', '(全部)')}"
                return f"已删除 {deleted} 条别名（{scope}）"
            return f"未找到匹配的别名（type={kwargs.get('type', '')}, value={kwargs.get('value', '(全部)')}）"
        if action == "link":
            result = resolve_contact(conn, query)
            if not result.person:
                return f"未找到联系人: {query}"
            ok = link_account(conn, result.person.id, kwargs.get("wxid", ""))
            return "已绑定账号" if ok else "绑定失败"
        if action == "merge":
            r1 = resolve_contact(conn, query)
            r2 = resolve_contact(conn, kwargs.get("merged", ""))
            if not r1.person:
                return f"未找到: {query}"
            if not r2.person:
                return f"未找到: {kwargs.get('merged', '')}"
            ok = merge_people(conn, r1.person.id, r2.person.id)
            return f"已合并: {r2.person.display_name} -> {r1.person.display_name}" if ok else "合并失败"
        if action == "audit":
            audit = audit_identity(conn)
            parts = ["# 身份审计\n"]
            parts.append("## 多账号联系人")
            for item in audit.get("multi_account", []):
                parts.append(f"- {item['display_name']} ({item['person_id']}): {item['accounts']} 个账号")
            parts.append("\n## 疑似重复")
            for item in audit.get("duplicate_aliases", []):
                people = ", ".join(item["people"])
                parts.append(f"- {item['value']} -> {people}")
            return "\n".join(parts)
        return f"未知的 contact action: {action}"
    finally:
        conn.close()


def agent_sticker(action: str = "list", **kwargs) -> str:
    from engine.stickers import (
        scan_stickers, list_stickers, label_sticker, format_sticker_list, get_sticker,
    )
    conn, config = _get_conn()
    try:
        if action == "scan":
            private_only = kwargs.get("private_only", True)
            result = scan_stickers(conn, private_only=private_only)
            scope = "私聊" if private_only else "全部"
            return f"扫描完成 ({scope}): {result['total']} 种贴纸 (新增 {result['new']}, 更新 {result['updated']})\n总贴纸消息: {result['total_messages']} 条"
        if action == "list":
            limit = kwargs.get("limit", 30)
            unlabeled = kwargs.get("unlabeled", False)
            min_freq = kwargs.get("min_freq", 1)
            stickers = list_stickers(conn, limit=limit, unlabeled_only=unlabeled, min_frequency=min_freq)
            if not stickers:
                return "无贴纸数据。先运行 sticker scan"
            title = "未标注贴纸" if unlabeled else "贴纸词典"
            return f"{title} (Top {limit}):\n{format_sticker_list(stickers)}"
        if action == "label":
            md5 = kwargs.get("md5", "")
            sticker = get_sticker(conn, md5)
            if not sticker:
                all_stickers = list_stickers(conn, limit=9999)
                matches = [s for s in all_stickers if s.md5.startswith(md5)]
                if len(matches) == 1:
                    sticker = matches[0]
                elif len(matches) > 1:
                    return f"匹配到 {len(matches)} 个贴纸，请输入更多字符"
                else:
                    return f"未找到 md5 以 {md5} 开头的贴纸"
            ok = label_sticker(conn, sticker.md5, label=kwargs.get("label", ""),
                               emotion=kwargs.get("emotion", ""), content_type=kwargs.get("content_type", ""))
            return f"已标注: {sticker.md5[:12]}..." if ok else "标注失败"
        return f"未知的 sticker action: {action}"
    finally:
        conn.close()


def agent_exclude(action: str = "list", **kwargs) -> str:
    from engine.analyzers.exclude import (
        filter_contacts, add_manual_exclude, remove_manual_exclude,
        get_manual_excludes,
    )
    from engine.analyzers.metrics import get_all_contacts_with_messages

    conn, config = _get_conn()
    try:
        if action == "list":
            manual = get_manual_excludes(conn)
            all_contacts = get_all_contacts_with_messages(conn, min_messages=0)
            _, auto_excluded = filter_contacts(all_contacts, conn, my_wxid=config.my_wxid,
                                               name_keywords=config.ranking.exclude.name_keywords)
            label_excluded = [e for e in auto_excluded if e.reason.startswith("标签:")]
            hard_excluded = [e for e in auto_excluded if not e.reason.startswith("标签:")]
            parts = ["# 排除列表\n"]
            parts.append("## 硬排除")
            for e in hard_excluded:
                if e.wxid not in manual:
                    parts.append(f"- {e.display_name} ({e.wxid[:25]}) — {e.reason}")
            parts.append(f"\n## 标签排除 ({len(label_excluded)})")
            for e in label_excluded:
                if e.wxid not in manual:
                    parts.append(f"- {e.display_name} ({e.wxid[:25]}) — {e.reason}")
            parts.append(f"\n## 手动排除 ({len(manual)})")
            for wxid, reason in manual.items():
                parts.append(f"- {wxid[:25]} — {reason}")
            included, _ = filter_contacts(all_contacts, conn, my_wxid=config.my_wxid,
                                          name_keywords=config.ranking.exclude.name_keywords)
            parts.append(f"\n参与排名: {len(included)} / {len(all_contacts)}")
            return "\n".join(parts)
        if action == "add":
            name = kwargs.get("name", "")
            reason = kwargs.get("reason", "手动排除")
            from engine.identity import resolve_contact
            result = resolve_contact(conn, name)
            if not result.person:
                return f"未找到: {name}"
            if not result.person.accounts:
                return f"{result.person.display_name} 无关联账号"
            for account in result.person.accounts:
                add_manual_exclude(conn, account.wxid, reason)
            return f"已排除: {result.person.display_name} (原因: {reason})"
        if action == "remove":
            name = kwargs.get("name", "")
            from engine.identity import resolve_contact
            result = resolve_contact(conn, name)
            if not result.person:
                return f"未找到: {name}"
            removed = 0
            for account in result.person.accounts:
                if remove_manual_exclude(conn, account.wxid):
                    removed += 1
            return f"已取消排除: {result.person.display_name} ({removed} 个账号)" if removed else f"{result.person.display_name} 不在排除列表中"
        return f"未知的 exclude action: {action}"
    finally:
        conn.close()


def agent_failure(action: str = "list", **kwargs) -> str:
    from engine.facts.failure_archive import save_failure, load_all_failures, format_failures
    from engine.models.failure import FailureCase

    if action == "add":
        case = FailureCase(
            person=kwargs.get("person", ""), stage=kwargs.get("stage", ""),
            cause=kwargs.get("cause", ""), lesson=kwargs.get("lesson", ""),
            signals=[s.strip() for s in kwargs.get("signals", "").split(",") if s.strip()] if kwargs.get("signals") else [],
            outcome=kwargs.get("outcome", ""), created_at=datetime.now().strftime("%Y-%m-%d"),
        )
        path = save_failure(case)
        return f"已保存失败案例: {path}"
    if action == "list":
        cases = load_all_failures()
        return format_failures(cases)
    return f"未知的 failure action: {action}"
