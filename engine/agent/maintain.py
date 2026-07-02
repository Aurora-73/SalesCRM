"""维持关系候选人筛选。"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from engine.agent.core import _get_conn
from engine.analyzers.metrics import compute_metrics_for_contact, get_all_contacts_with_messages, SIGNAL_ORDER
from engine.analyzers.exclude import filter_contacts
from engine.analyzers.ranker import _resolve_person_name
from engine.identity.directory import get_person_by_wxid, _person_id_for_wxid


@dataclass
class Candidate:
    name: str
    person_id: str
    wxid: str
    rank: int
    composite: float
    signal_level: str
    recent_days: float
    trend: float
    neediness_penalty: float
    interaction_pattern: str
    last_msg_summary: str
    reason: str


def maintain_candidates(max_people: int = 10) -> list[Candidate] | str:
    """筛选需要维持关系的候选人。

    逻辑：
    1. 从未排除的联系人中，按 composite 排序
    2. 过滤 recent_days > 1（超过 1 天没联系）
    3. 过滤 signal_level 不是"无信号"
    4. 按优先级排序：
       - 热度下降（recent > 3 且 trend < 0）最优先
       - 有意向但未推进（signal_level ≥ 弱意向 且 recent > 1）次之
       - 高潜力未投入（neediness_penalty > 0.9 且 recent > 2）再次
    5. 返回 top N

    返回 list[Candidate] 或错误字符串。
    """
    conn, config = _get_conn()
    try:
        all_contacts = get_all_contacts_with_messages(conn, min_messages=20)
        included, _ = filter_contacts(
            all_contacts, conn,
            my_wxid=config.my_wxid,
            name_keywords=config.ranking.exclude.name_keywords,
        )

        # 按 person_id 聚合（多微信号合并）
        person_groups: dict[str, list[dict]] = {}
        for c in included:
            pid = _person_id_for_wxid(c["wxid"])
            person_groups.setdefault(pid, []).append(c)

        candidates: list[Candidate] = []
        now_ts = datetime.now().timestamp()

        for pid, group in person_groups.items():
            group.sort(key=lambda x: x["message_count"], reverse=True)
            primary = group[0]
            wxid = primary["wxid"]
            name = _resolve_person_name(conn, wxid) or primary["display_name"]

            metrics = compute_metrics_for_contact(conn, config, wxid, name)

            # 过滤条件
            recent_days = metrics.recent.raw  # 最后消息距今天数
            signal_level = metrics.signal_level
            trend = metrics.trend.normalized - 0.5  # 转为变化值

            # 必须超过 1 天没联系
            if recent_days <= 1:
                continue
            # 必须有信号（不是完全无信号）
            if signal_level == "无信号":
                continue
            # 跳过自己
            if wxid == config.my_wxid:
                continue

            # 判断优先级和原因
            reason = _classify_reason(recent_days, signal_level, trend, metrics.neediness_penalty)

            # 获取最后一条消息摘要
            last_msg = _get_last_message_summary(conn, wxid, config.my_wxid)

            candidates.append(Candidate(
                name=name,
                person_id=pid,
                wxid=wxid,
                rank=0,  # 后面排序后赋值
                composite=metrics.composite,
                signal_level=signal_level,
                recent_days=round(recent_days, 1),
                trend=round(trend, 4),
                neediness_penalty=metrics.neediness_penalty,
                interaction_pattern=metrics.interaction_pattern,
                last_msg_summary=last_msg,
                reason=reason,
            ))

        # 排序：兴趣下降 > 意向未推进 > 高潜力
        priority_order = {"兴趣下降": 0, "意向未推进": 1, "高潜力未投入": 2, "需关注": 3}
        candidates.sort(key=lambda c: (
            priority_order.get(c.reason, 9),
            -c.composite,
        ))

        # 赋排名
        for i, c in enumerate(candidates):
            c.rank = i + 1

        return candidates[:max_people]

    finally:
        conn.close()


def _classify_reason(
    recent_days: float,
    signal_level: str,
    trend: float,
    neediness_penalty: float,
) -> str:
    """分类候选人原因。"""
    signal_strength = SIGNAL_ORDER.get(signal_level, 0)

    # 兴趣下降：超过 3 天没联系，且趋势下降
    if recent_days > 3 and trend < -0.005:
        return "兴趣下降"

    # 有意向但未推进：信号 ≥ 弱意向，1-3 天没联系
    if signal_strength >= 2 and 1 < recent_days <= 3:
        return "意向未推进"

    # 高潜力未投入：neediness 正常，超过 2 天没联系
    if neediness_penalty > 0.9 and recent_days > 2:
        return "高潜力未投入"

    return "需关注"


def _get_last_message_summary(conn: sqlite3.Connection, wxid: str, my_wxid: str) -> str:
    """获取最后一条消息的简短摘要。"""
    row = conn.execute(
        "SELECT sender_id, content, timestamp FROM messages "
        "WHERE conversation_id = ? AND type = 1 AND content NOT LIKE '<?xml%' "
        "ORDER BY timestamp DESC LIMIT 1",
        (wxid,),
    ).fetchone()

    if not row:
        return ""

    sender = "我" if (row[0] or "") == my_wxid else "客户"
    content = (row[1] or "")[:50]
    ts = row[2]
    if ts:
        day_str = datetime.fromtimestamp(ts).strftime("%m-%d")
        return f"[{day_str}] {sender}: {content}"
    return f"{sender}: {content}"


def format_candidates(candidates: list[Candidate]) -> str:
    """格式化候选人为 Markdown。"""
    if not candidates:
        return "当前无需维持关系的联系人。"

    lines = [f"## 维持关系提醒\n"]
    lines.append(f"共 {len(candidates)} 人需要关注：\n")

    for c in candidates:
        lines.append(f"### {c.rank}. {c.name}")
        lines.append(f"- 原因: {c.reason}")
        lines.append(f"- 信号: {c.signal_level} | composite: {c.composite:.3f} | 模式: {c.interaction_pattern}")
        lines.append(f"- 最后联系: {c.recent_days} 天前")
        lines.append(f"- 趋势: {c.trend:+.3f}")
        if c.last_msg_summary:
            lines.append(f"- 上次消息: {c.last_msg_summary}")
        lines.append("")

    lines.append("---")
    lines.append("每人建议给出 3 条可发送的消息选项，要求：")
    lines.append("1. 基于实际聊天内容，不编造叙事")
    lines.append("2. 有具体 hook（问句/分享/价值点）")
    lines.append("3. 不超过 2 句话，低压力")
    lines.append("4. 每人 3 条风格不同（轻松/分享/推进）")

    return "\n".join(lines)
