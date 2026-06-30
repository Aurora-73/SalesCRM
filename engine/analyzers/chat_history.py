"""聊天记录查询与格式化。

面向 CLI 和后续 LLM 上下文组装，封装“联系人 + 时间段”的 SQLite 查询。
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, time
from html import unescape
from pathlib import Path
from typing import Iterable

from engine.analyzers.exclude import search_contacts


@dataclass(frozen=True)
class ChatTarget:
    wxid: str
    display_name: str
    remark: str = ""
    nickname: str = ""


@dataclass(frozen=True)
class ChatMessage:
    id: str
    conversation_id: str
    sender_id: str
    sender_name: str
    timestamp: int
    type: int
    content: str
    raw_content: str

    @property
    def local_time(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp)


def parse_date_bound(value: str | None, *, is_end: bool = False) -> int | None:
    """解析 CLI 日期参数为本地时区 Unix timestamp。

    支持 `YYYY-MM-DD`、`YYYY-MM-DD HH:MM`、`YYYY-MM-DDTHH:MM:SS`。
    结束日期如果只给到天，则包含当天 23:59:59。
    """
    if not value:
        return None

    raw = value.strip()
    try:
        if len(raw) == 10:
            day = datetime.strptime(raw, "%Y-%m-%d").date()
            dt = datetime.combine(day, time.max if is_end else time.min)
        else:
            dt = datetime.fromisoformat(raw.replace(" ", "T"))
    except ValueError as exc:
        raise ValueError(
            f"无法解析日期: {value}，请使用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM"
        ) from exc

    return int(dt.timestamp())


def resolve_chat_target(conn: sqlite3.Connection, keyword: str) -> tuple[ChatTarget | None, list[ChatTarget]]:
    """按 wxid 或名称定位私聊会话。

    返回 `(target, candidates)`。当存在多个模糊候选且没有精确匹配时，`target`
    为 None，调用方应展示 candidates 让用户缩小关键词。
    """
    row = conn.execute(
        """
        SELECT c.id AS wxid,
               COALESCE(c.display_name, c.id) AS display_name,
               co.remark,
               co.nickname
        FROM conversations c
        LEFT JOIN contacts co ON co.id = c.id
        WHERE c.type = 'private' AND c.id = ?
        """,
        (keyword,),
    ).fetchone()
    if row:
        return _target_from_row(row), []

    results = search_contacts(conn, keyword)
    candidates = [
        ChatTarget(
            wxid=r["wxid"],
            display_name=r["display_name"],
            remark=r.get("remark", ""),
            nickname=r.get("nickname", ""),
        )
        for r in results
    ]
    if not candidates:
        return None, []

    exact = [
        c for c in candidates
        if keyword in {c.display_name, c.remark, c.nickname}
    ]
    if len(exact) == 1:
        return exact[0], candidates
    if len(candidates) == 1:
        return candidates[0], candidates

    return None, candidates


def query_chat_messages(
    conn: sqlite3.Connection,
    conversation_id: str,
    *,
    start_ts: int | None = None,
    end_ts: int | None = None,
    limit: int | None = 200,
    text_only: bool = True,
    include_system: bool = False,
    reverse: bool = False,
) -> list[ChatMessage]:
    """查询指定会话的消息。

    无时间边界时默认取最近 `limit` 条，再按时间正序返回；带时间边界时从
    时间段开头开始取。`limit=None` 表示不限制条数。
    """
    where = ["conversation_id = ?"]
    params: list[object] = [conversation_id]

    if start_ts is not None:
        where.append("timestamp >= ?")
        params.append(start_ts)
    if end_ts is not None:
        where.append("timestamp <= ?")
        params.append(end_ts)
    if text_only and not include_system:
        where.append("type = 1")
    elif text_only and include_system:
        where.append("(type = 1 OR type = 10000)")
    if not include_system:
        where.append("type != 10000")

    where_sql = " AND ".join(where)
    limit_sql = ""
    if limit is not None and limit > 0:
        limit_sql = " LIMIT ?"

    # 未指定时间段时，“最近 N 条”通常比“最早 N 条”更符合分析入口。
    if start_ts is None and end_ts is None and limit_sql:
        params_with_limit = params + [limit]
        outer_order = "DESC" if reverse else "ASC"
        rows = conn.execute(
            f"""
            SELECT * FROM (
                SELECT id, conversation_id, sender_id, sender_name, timestamp,
                       type, content, raw_content
                FROM messages
                WHERE {where_sql}
                ORDER BY timestamp DESC
                {limit_sql}
            )
            ORDER BY timestamp {outer_order}, id {outer_order}
            """,
            params_with_limit,
        ).fetchall()
    else:
        order = "DESC" if reverse else "ASC"
        if limit_sql:
            params = params + [limit]
        rows = conn.execute(
            f"""
            SELECT id, conversation_id, sender_id, sender_name, timestamp,
                   type, content, raw_content
            FROM messages
            WHERE {where_sql}
            ORDER BY timestamp {order}, id {order}
            {limit_sql}
            """,
            params,
        ).fetchall()

    return [_message_from_row(row) for row in rows]


def format_chat_messages(
    target: ChatTarget,
    messages: Iterable[ChatMessage],
    *,
    my_wxid: str,
    fmt: str = "text",
    reverse: bool = False,
) -> str:
    """格式化聊天记录为 text / markdown / json。"""
    msg_list = list(messages)
    summary = _summarize_messages(msg_list, target, my_wxid)
    if fmt == "json":
        return json.dumps(
            {
                "target": {
                    "wxid": target.wxid,
                    "display_name": target.display_name,
                },
                "summary": summary,
                "messages": [
                    {
                        "id": m.id,
                        "time": m.local_time.isoformat(timespec="seconds"),
                        "sender": _speaker(m, target, my_wxid),
                        "sender_id": m.sender_id,
                        "type": m.type,
                        "content": _display_content(m),
                        "raw_content": "" if _is_xml_message(m.content) else m.raw_content,
                    }
                    for m in msg_list
                ],
            },
            ensure_ascii=False,
            indent=2,
        )

    if fmt == "md":
        lines = _format_summary_md(summary)
        for day, day_messages in _group_by_day(msg_list, reverse=reverse):
            lines.append("")
            lines.append(f"## {day} ({len(day_messages)}条)")
            lines.append("")
            for m in day_messages:
                content = _display_content(m)
                lines.append(
                    f"- **{m.local_time:%H:%M}** "
                    f"{_speaker(m, target, my_wxid)}: {content}"
                )
        return "\n".join(lines)

    if fmt != "text":
        raise ValueError(f"不支持的格式: {fmt}")

    lines = _format_summary_text(summary)
    for day, day_messages in _group_by_day(msg_list, reverse=reverse):
        lines.append("")
        lines.append(f"=== {day} ({len(day_messages)}条) ===")
        for m in day_messages:
            content = _display_content(m).replace("\n", " / ")
            lines.append(
                f"[{m.local_time:%H:%M}] "
                f"{_speaker(m, target, my_wxid)}: {content}"
            )
    return "\n".join(lines)


def write_chat_output(path: str | Path, content: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content, encoding="utf-8")


def _target_from_row(row: sqlite3.Row) -> ChatTarget:
    return ChatTarget(
        wxid=row["wxid"],
        display_name=row["display_name"],
        remark=row["remark"] or "",
        nickname=row["nickname"] or "",
    )


def _message_from_row(row: sqlite3.Row) -> ChatMessage:
    return ChatMessage(
        id=row["id"],
        conversation_id=row["conversation_id"],
        sender_id=row["sender_id"],
        sender_name=row["sender_name"] or "",
        timestamp=int(row["timestamp"]),
        type=int(row["type"]),
        content=row["content"] or "",
        raw_content=row["raw_content"] or "",
    )


def _speaker(message: ChatMessage, target: ChatTarget, my_wxid: str) -> str:
    if not message.sender_id:
        return "系统"
    if message.type == 10000:
        return "系统"
    if message.sender_id == my_wxid:
        return "我"
    return message.sender_name or target.display_name or message.sender_id


def _normalize_content(content: str) -> str:
    return content.replace("\r\n", "\n").replace("\r", "\n").strip()


def _display_content(message: ChatMessage) -> str:
    content = _normalize_content(message.content)
    if not content:
        return _fallback_content(message)
    if _is_xml_message(content):
        return _fold_xml_message(content)
    return content


def _fallback_content(message: ChatMessage) -> str:
    if message.type == 10000:
        return "[系统消息]"
    if message.type == 3:
        return f"[图片:{message.id}]"
    if message.type == 34:
        return f"[语音:{message.id}]"
    if message.type == 43:
        return f"[视频:{message.id}]"
    return f"[非文本消息:{message.type}:{message.id}]"


def _is_xml_message(content: str) -> bool:
    stripped = content.lstrip()
    return stripped.startswith("<?xml") or stripped.startswith("<msg") or stripped.startswith("<appmsg")


def _fold_xml_message(content: str) -> str:
    title_match = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>", content, re.S)
    title = ""
    if title_match:
        title = title_match.group(1) or title_match.group(2) or ""
        title = unescape(_strip_cdata(title).strip())

    app_match = re.search(r"<appname><!\[CDATA\[(.*?)\]\]></appname>|<appname>(.*?)</appname>", content, re.S)
    app_name = ""
    if app_match:
        app_name = app_match.group(1) or app_match.group(2) or ""
        app_name = unescape(_strip_cdata(app_name).strip())

    if title and app_name:
        return f"[小程序: {app_name} - {title}]"
    if title:
        return f"[小程序: {title}]"
    if app_name:
        return f"[小程序: {app_name}]"
    return "[XML消息]"


def _strip_cdata(value: str) -> str:
    return value.replace("<![CDATA[", "").replace("]]>", "")


def _summarize_messages(
    messages: list[ChatMessage],
    target: ChatTarget,
    my_wxid: str,
) -> dict:
    my_count = 0
    target_count = 0
    system_count = 0
    for message in messages:
        speaker = _speaker(message, target, my_wxid)
        if speaker == "我":
            my_count += 1
        elif speaker == "系统":
            system_count += 1
        else:
            target_count += 1

    first_time = datetime.fromtimestamp(min(m.timestamp for m in messages)) if messages else None
    last_time = datetime.fromtimestamp(max(m.timestamp for m in messages)) if messages else None
    return {
        "display_name": target.display_name,
        "wxid": target.wxid,
        "count": len(messages),
        "target_count": target_count,
        "my_count": my_count,
        "system_count": system_count,
        "first_time": first_time.isoformat(timespec="seconds") if first_time else "",
        "last_time": last_time.isoformat(timespec="seconds") if last_time else "",
        "date_range": (
            f"{first_time:%Y-%m-%d} ~ {last_time:%Y-%m-%d}"
            if first_time and last_time else "N/A"
        ),
    }


def _format_summary_text(summary: dict) -> list[str]:
    count_line = f"=== 消息数: {summary['count']} (对方 {summary['target_count']} / 我 {summary['my_count']}"
    if summary["system_count"]:
        count_line += f" / 系统 {summary['system_count']}"
    count_line += ") ==="
    return [
        f"=== 联系人: {summary['display_name']} ===",
        f"=== wxid: {summary['wxid']} ===",
        count_line,
        f"=== 时间范围: {summary['date_range']} ===",
    ]


def _format_summary_md(summary: dict) -> list[str]:
    count_line = f"- 消息数: {summary['count']} (对方 {summary['target_count']} / 我 {summary['my_count']}"
    if summary["system_count"]:
        count_line += f" / 系统 {summary['system_count']}"
    count_line += ")"
    return [
        f"# {summary['display_name']} 聊天记录",
        "",
        f"- wxid: `{summary['wxid']}`",
        count_line,
        f"- 时间范围: {summary['date_range']}",
    ]


def _group_by_day(messages: list[ChatMessage], *, reverse: bool) -> list[tuple[str, list[ChatMessage]]]:
    groups: dict[str, list[ChatMessage]] = {}
    for message in messages:
        day = f"{message.local_time:%Y-%m-%d}"
        groups.setdefault(day, []).append(message)
    return sorted(groups.items(), reverse=reverse)
