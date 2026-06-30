"""聊天证据视图 — agent_chat + agent_chat_data。"""
from __future__ import annotations

import sqlite3
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from engine.config import Config
from engine.identity import IdentityPerson
from engine.agent.core import _build_cross_refs
from engine.agent.response import ok, err


def _query_chat_messages(
    conn: sqlite3.Connection, config: Config, person: IdentityPerson, *,
    recent: int = 50, from_date: str | None = None, to_date: str | None = None,
    keyword: str | None = None, context_lines: int = 0,
) -> dict:
    """共享查询层：返回 {messages, total, returned, total_before_filter}。"""
    from engine.analyzers.chat_history import parse_date_bound

    start_ts = parse_date_bound(from_date, is_end=False)
    end_ts = parse_date_bound(to_date, is_end=True)
    messages: list[dict] = []
    for account in person.accounts:
        cid = account.conversation_id or account.wxid
        if not cid:
            continue
        params: list = [cid]
        conditions = ["m.conversation_id = ?", "m.type = 1"]
        if start_ts is not None:
            conditions.append("m.timestamp >= ?")
            params.append(start_ts)
        if end_ts is not None:
            conditions.append("m.timestamp <= ?")
            params.append(end_ts)
        sql = (
            f"SELECT m.id, m.conversation_id, m.sender_id, m.content, "
            f"m.timestamp, m.type, m.platform, m.source "
            f"FROM messages m WHERE {' AND '.join(conditions)} ORDER BY m.timestamp ASC"
        )
        rows = conn.execute(sql, params).fetchall()
        for row in rows:
            sender_id = row["sender_id"] or ""
            messages.append({
                "id": row["id"],
                "conversation_id": row["conversation_id"],
                "sender_id": sender_id,
                "is_mine": sender_id == config.my_wxid,
                "timestamp": row["timestamp"],
                "content": row["content"] or "",
                "type": row["type"],
                "platform": row["platform"] or "wechat",
                "source": row["source"] or "sync",
            })
    messages.sort(key=lambda m: m["timestamp"])

    total_before_filter = len(messages)

    if keyword:
        matched_indices: set[int] = set()
        for i, msg in enumerate(messages):
            if keyword in msg["content"]:
                for j in range(max(0, i - context_lines), min(len(messages), i + context_lines + 1)):
                    matched_indices.add(j)
        messages = [messages[i] for i in sorted(matched_indices)]

    total = len(messages)
    if len(messages) > recent:
        messages = messages[-recent:]

    return {
        "messages": messages,
        "total": total,
        "returned": len(messages),
        "total_before_filter": total_before_filter,
    }


def agent_chat_data(
    conn: sqlite3.Connection, config: Config, person: IdentityPerson, *,
    recent: int = 50, from_date: str | None = None, to_date: str | None = None,
    keyword: str | None = None, context_lines: int = 0,
) -> dict:
    """结构化聊天查询 — 返回 ToolEnvelope dict。"""
    result = _query_chat_messages(
        conn, config, person,
        recent=recent, from_date=from_date, to_date=to_date,
        keyword=keyword, context_lines=context_lines,
    )
    return ok(
        {
            "messages": result["messages"],
            "filter": {
                "keyword": keyword,
                "from_date": from_date,
                "to_date": to_date,
                "context_lines": context_lines,
            },
            "total": result["total"],
            "returned": result["returned"],
        },
        person_id=person.id,
        display_name=person.display_name,
    )


def agent_chat(
    conn: sqlite3.Connection, config: Config, person: IdentityPerson, *,
    recent: int = 50, from_date: str | None = None, to_date: str | None = None,
    keyword: str | None = None, context_lines: int = 0, output_file: str | None = None,
) -> str:
    """聊天记录（按日期分组 Markdown，已标注"我"/对方名字）。"""
    result = _query_chat_messages(
        conn, config, person,
        recent=recent, from_date=from_date, to_date=to_date,
        keyword=keyword, context_lines=context_lines,
    )
    messages = result["messages"]
    total = result["total"]
    total_before_filter = result["total_before_filter"]

    grouped: OrderedDict[str, list] = OrderedDict()
    for msg in messages:
        day = datetime.fromtimestamp(msg["timestamp"]).strftime("%Y-%m-%d")
        grouped.setdefault(day, []).append(msg)

    parts = [f"# Chat Evidence: {person.display_name}\n"]
    first_day = next(iter(grouped)) if grouped else "N/A"
    last_day = next(reversed(grouped)) if grouped else "N/A"
    filter_desc = []
    if keyword:
        filter_desc.append(f'keyword="{keyword}"')
    if from_date:
        filter_desc.append(f"from={from_date}")
    if to_date:
        filter_desc.append(f"to={to_date}")
    parts.append(f"- 时间范围: {first_day} ~ {last_day}")
    parts.append(f"- 显示消息: {len(messages)} / {total_before_filter}")
    if filter_desc:
        parts.append(f"- 过滤: {', '.join(filter_desc)}")
    parts.append("")

    for day, day_msgs in grouped.items():
        parts.append(f"## {day} ({len(day_msgs)} 条)\n")
        for msg in day_msgs:
            ts = datetime.fromtimestamp(msg["timestamp"]).strftime("%H:%M")
            sender_label = "我" if msg.get("is_mine") else person.display_name
            parts.append(f"- **{ts}** {sender_label}: {msg['content']}")
        parts.append("")

    parts.append(_build_cross_refs(person, has_fact=True, has_event=True))
    result_md = "\n".join(parts)
    if output_file:
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        Path(output_file).write_text(result_md, encoding="utf-8")
        return f"已写入: {output_file} ({len(messages)} 条消息)"
    return result_md
