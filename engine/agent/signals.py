"""信号检测 — 关键词扫描、情感操控检测、朋友圈-聊天联动分析。"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from engine.config import load_config

# 信号关键词
_REJECTION_KEYWORDS = (
    "不喜欢", "做朋友", "删好友", "没感觉", "不想谈", "不合适", "别追了", "没可能",
    "冒昧", "不太合适", "不是我的类型", "做朋友吧", "只把你当", "当朋友",
    "不是那种", "没有那种感觉", "对我没感觉", "你很好但是", "我们不合适",
)
_CONFESSION_KEYWORDS = ("签约", "合作吧", "签合同", "同意合作", "确认合作", "达成协议")
_INVITATION_KEYWORDS = ("出来", "见面", "约", "一起", "去哪", "周末", "下午")
_MONEY_KEYWORDS = ("红包", "转账", "买", "借", "充值", "打赏", "付款", "支付宝", "微信支付", "发个")
_MANIPULATION_SWEET_KEYWORDS = ("全世界最好", "最专业", "最靠谱", "不可或缺")
_MANIPULATION_VICTIM_KEYWORDS = ("我好害怕", "我好难过", "我好孤独", "没有人对我好", "他们都欺负我", "我只有你", "你别不理我", "别离开我")
_ESCALATION_AMOUNT_KEYWORDS = ("999", "666", "888", "一万", "两万", "三万", "手机", "电脑", "设备")

# 暴露给 _select_important_messages 使用
SIGNAL_KEYWORDS = _REJECTION_KEYWORDS + _CONFESSION_KEYWORDS + ("签约", "合作", "合同", "报价")


def _detect_signals(messages: list[dict]) -> dict[str, list[str]]:
    signals: dict[str, list[str]] = {}
    for msg in messages:
        content = msg.get("content", "")
        sender = msg.get("sender", "")
        ts = msg.get("timestamp", 0)
        ts_str = datetime.fromtimestamp(ts).strftime("%m-%d %H:%M") if ts else ""
        for kw in _REJECTION_KEYWORDS:
            if kw in content:
                signals.setdefault("rejection", []).append(f"[{ts_str}] {sender}: {content[:60]}")
                break
        for kw in _CONFESSION_KEYWORDS:
            if kw in content:
                signals.setdefault("confession", []).append(f"[{ts_str}] {sender}: {content[:60]}")
                break
        for kw in _INVITATION_KEYWORDS:
            if kw in content and sender != "我":
                signals.setdefault("invitation", []).append(f"[{ts_str}] {sender}: {content[:60]}")
                break
    return signals


def detect_manipulation_signals(messages: list[dict], my_wxid: str) -> dict[str, list[str]]:
    signals: dict[str, list[str]] = {}
    customer_msgs = [m for m in messages if m.get("sender_id") != my_wxid]
    for msg in customer_msgs:
        content = msg.get("content", "")
        ts = msg.get("timestamp", 0)
        ts_str = datetime.fromtimestamp(ts).strftime("%m-%d %H:%M") if ts else ""
        for kw in _MONEY_KEYWORDS:
            if kw in content:
                signals.setdefault("money_requests", []).append(f"[{ts_str}] {content[:60]}")
                break
        for kw in _MANIPULATION_SWEET_KEYWORDS:
            if kw in content:
                signals.setdefault("sweet_escalation", []).append(f"[{ts_str}] {content[:60]}")
                break
        for kw in _MANIPULATION_VICTIM_KEYWORDS:
            if kw in content:
                signals.setdefault("victim_play", []).append(f"[{ts_str}] {content[:60]}")
                break
        for kw in _ESCALATION_AMOUNT_KEYWORDS:
            if kw in content:
                signals.setdefault("amount_escalation", []).append(f"[{ts_str}] {content[:60]}")
                break
    return signals


def _detect_moments_chat_signals(
    conn: sqlite3.Connection, wxid: str, my_wxid: str, display_name: str = "",
) -> dict[str, list[str]]:
    from datetime import datetime as dt, timedelta
    signals: dict[str, list[str]] = {}
    # 1. 聊天时间线
    chat_days_raw = conn.execute("""
        SELECT DISTINCT strftime('%Y-%m-%d', timestamp, 'unixepoch', 'localtime') as day
        FROM messages
        WHERE conversation_id = ? AND type = 1 AND content NOT LIKE '<?xml%'
        ORDER BY day
    """, (wxid,)).fetchall()
    chat_days = {r[0] for r in chat_days_raw}
    if not chat_days:
        return signals
    # 2. 客户在我朋友圈的互动
    customer_interactions = conn.execute("""
        SELECT mi.type, mi.content, mi.timestamp, m.content, m.timestamp as post_ts
        FROM moment_interactions mi
        JOIN moments m ON mi.moment_id = m.id
        WHERE m.author_id = ? AND mi.user_name = ?
        ORDER BY mi.timestamp
    """, (my_wxid, display_name)).fetchall()
    # 3. 我在客户朋友圈的互动
    my_name = ""
    row = conn.execute("SELECT display_name FROM contacts WHERE id = ?", (my_wxid,)).fetchone()
    if row:
        my_name = row[0] or ""
    if my_name:
        my_interactions = conn.execute("""
            SELECT mi.type, mi.content, mi.timestamp, m.content
            FROM moment_interactions mi
            JOIN moments m ON mi.moment_id = m.id
            WHERE m.author_id = ? AND mi.user_name = ?
            ORDER BY mi.timestamp
        """, (wxid, my_name)).fetchall()
    else:
        my_interactions = []
    # 4. 检测断联期
    sorted_days = sorted(chat_days)
    silence_periods: list[tuple[str, str]] = []
    for i in range(len(sorted_days) - 1):
        d1 = dt.strptime(sorted_days[i], "%Y-%m-%d")
        d2 = dt.strptime(sorted_days[i + 1], "%Y-%m-%d")
        gap = (d2 - d1).days
        if gap >= 3:
            silence_periods.append((
                (d1 + timedelta(days=1)).strftime("%Y-%m-%d"),
                (d2 - timedelta(days=1)).strftime("%Y-%m-%d"),
            ))
    # 5. 客户在我朋友圈的互动
    for interaction in customer_interactions:
        itype = interaction[0]
        icontent = interaction[1] or ""
        its = interaction[2]
        ipost = interaction[3] or ""
        iday = dt.fromtimestamp(its).strftime("%Y-%m-%d")
        its_str = dt.fromtimestamp(its).strftime("%m-%d %H:%M")
        in_silence = any(start <= iday <= end for start, end in silence_periods)
        if itype == "comment":
            if in_silence:
                signals.setdefault("moments_strong_signal", []).append(
                    f"[{its_str}] 关注期客户评论你的朋友圈: \"{icontent[:40]}\" (原文: {ipost[:30]})"
                )
            else:
                signals.setdefault("moments_comment", []).append(
                    f"[{its_str}] 客户评论你的朋友圈: \"{icontent[:40]}\""
                )
        elif itype == "like":
            if in_silence:
                signals.setdefault("moments_weak_signal", []).append(
                    f"[{its_str}] 关注期客户点赞你的朋友圈 (原文: {ipost[:30]})"
                )
    total_client_interactions = len(customer_interactions)
    total_my_interactions = len(my_interactions)
    if total_client_interactions == 0 and total_my_interactions > 0:
        signals.setdefault("moments_one_sided", []).append(
            f"你有 {total_my_interactions} 次朋友圈互动，客户 0 次——单向投入"
        )
    comments = [r for r in customer_interactions if r[0] == "comment"]
    for i in range(len(comments) - 1):
        c1_ts = comments[i][2]
        c2_ts = comments[i + 1][2]
        if (c2_ts - c1_ts) < 3600 * 24:
            signals.setdefault("moments_conversation", []).append(
                f"[{dt.fromtimestamp(c1_ts).strftime('%m-%d')}] 客户连续评论你的朋友圈"
            )
            break
    return signals


def _query_signal_messages(
    conn: sqlite3.Connection, wxids: list[str], my_wxid: str, months: int = 3,
) -> list[dict]:
    if not wxids:
        return []
    placeholders = ",".join("?" for _ in wxids)
    sql = f"""
        SELECT sender_id, content, timestamp
        FROM messages
        WHERE conversation_id IN ({placeholders})
          AND type = 1 AND content NOT LIKE '<?xml%'
          AND timestamp >= strftime('%s', 'now', '-{months} months', 'localtime')
        ORDER BY timestamp ASC
    """
    rows = conn.execute(sql, wxids).fetchall()
    return [
        {"sender": "我" if (r[0] or "") == my_wxid else "客户", "content": r[1] or "", "timestamp": r[2]}
        for r in rows
    ]
