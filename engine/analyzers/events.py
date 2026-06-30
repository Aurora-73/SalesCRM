"""事件流检测器。

从聊天记录中自动提取关键关系事件，无需 LLM。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from engine.identity import IdentityPerson


class EventType(Enum):
    FIRST_CHAT = "首次聊天"
    FREQUENCY_UP = "聊天频率上升"
    FREQUENCY_DOWN = "聊天频率下降"
    DISCONNECT = "断联"
    RECONNECT = "恢复联系"
    FIRST_DATE = "首次约见"

    # 销售特有事件
    REQUIREMENT_CONFIRM = "需求确认"
    DECISION_MAKER_APPEAR = "决策人出现"
    PROPOSAL_SENT = "报价发送"


@dataclass
class Event:
    event_type: EventType
    date: str              # YYYY-MM-DD
    detail: str
    confidence: float      # 0-1


def detect_events(
    conn: sqlite3.Connection,
    person: IdentityPerson,
    disconnect_days: int = 7,
) -> list[Event]:
    """检测某人的关系事件。返回按时间排序的事件列表。"""
    wxids = [a.wxid for a in person.accounts]
    if not wxids:
        return []

    events: list[Event] = []

    # 获取所有消息（按时间排序）
    placeholders = ",".join("?" for _ in wxids)
    rows = conn.execute(
        f"""
        SELECT timestamp, sender_id, content
        FROM messages
        WHERE conversation_id IN ({placeholders})
          AND type = 1
        ORDER BY timestamp ASC
        """,
        tuple(wxids),
    ).fetchall()

    if not rows:
        return []

    # 1. 首次聊天
    first_ts = rows[0]["timestamp"]
    first_date = datetime.fromtimestamp(first_ts)
    events.append(Event(
        event_type=EventType.FIRST_CHAT,
        date=first_date.strftime("%Y-%m-%d"),
        detail=f"首条消息时间",
        confidence=1.0,
    ))

    # 2. 按日聚合消息量
    daily_counts: dict[str, int] = {}
    for row in rows:
        dt = datetime.fromtimestamp(row["timestamp"])
        day_str = dt.strftime("%Y-%m-%d")
        daily_counts[day_str] = daily_counts.get(day_str, 0) + 1

    sorted_days = sorted(daily_counts.keys())
    if len(sorted_days) < 2:
        return events

    # 3. 断联与恢复联系检测
    prev_date = datetime.strptime(sorted_days[0], "%Y-%m-%d")
    in_disconnect = False
    disconnect_start = None

    for day_str in sorted_days[1:]:
        curr_date = datetime.strptime(day_str, "%Y-%m-%d")
        gap = (curr_date - prev_date).days

        if gap >= disconnect_days:
            # 断联事件
            events.append(Event(
                event_type=EventType.DISCONNECT,
                date=prev_date.strftime("%Y-%m-%d"),
                detail=f"断联 {gap} 天（{prev_date.strftime('%m-%d')} 至 {curr_date.strftime('%m-%d')}）",
                confidence=1.0,
            ))
            in_disconnect = True
            disconnect_start = prev_date
        elif in_disconnect:
            # 恢复联系
            events.append(Event(
                event_type=EventType.RECONNECT,
                date=day_str,
                detail=f"断联 {(curr_date - disconnect_start).days} 天后恢复联系",
                confidence=1.0,
            ))
            in_disconnect = False
            disconnect_start = None

        prev_date = curr_date

    # 4. 聊天频率变化检测（7 天意向滑动对比，只报告状态转变）
    if len(sorted_days) >= 14:
        window = 7
        last_freq_state = "normal"  # normal / up / down
        for i in range(window, len(sorted_days)):
            recent_start = datetime.strptime(sorted_days[i], "%Y-%m-%d")

            prev_count = sum(
                daily_counts.get((recent_start - timedelta(days=window + d)).strftime("%Y-%m-%d"), 0)
                for d in range(window)
            )
            recent_count = sum(
                daily_counts.get((recent_start - timedelta(days=d)).strftime("%Y-%m-%d"), 0)
                for d in range(window)
            )

            if prev_count > 0 and recent_count > prev_count * 2 and recent_count >= 10:
                state = "up"
            elif prev_count >= 10 and recent_count < prev_count * 0.5:
                state = "down"
            else:
                state = "normal"

            if state != last_freq_state and state != "normal":
                if state == "up":
                    events.append(Event(
                        event_type=EventType.FREQUENCY_UP,
                        date=sorted_days[i],
                        detail=f"近 7 天消息量 {recent_count} 条，前 7 天 {prev_count} 条（{recent_count/prev_count:.1f}x）",
                        confidence=0.7,
                    ))
                elif state == "down":
                    events.append(Event(
                        event_type=EventType.FREQUENCY_DOWN,
                        date=sorted_days[i],
                        detail=f"近 7 天消息量 {recent_count} 条，前 7 天 {prev_count} 条（降至 {recent_count/prev_count:.0%}）",
                        confidence=0.7,
                    ))
            last_freq_state = state

    # 5. 首次约见（从 Dates section 检测）
    # 这个通过 facts/people_archive.py 的 Dates 数据获取，此处跳过
    # （CLI 的 events scan 命令会在外层处理）

    # 6. 销售特有事件检测
    # 需求确认关键词
    requirement_keywords = ["需求", "痛点", "问题", "困难", "需要", "想要", "希望", "目标"]
    # 决策人关键词
    decision_keywords = ["老板", "领导", "负责人", "老板说", "领导说", "总监", "经理"]
    # 报价关键词
    proposal_keywords = ["报价", "价格", "费用", "预算", "方案", "合同", "付款"]

    requirement_found = False
    decision_found = False
    proposal_found = False
    requirement_date = None
    decision_date = None
    proposal_date = None

    for row in rows:
        content = row["content"] or ""
        dt = datetime.fromtimestamp(row["timestamp"])
        day_str = dt.strftime("%Y-%m-%d")

        if not requirement_found and any(kw in content for kw in requirement_keywords):
            requirement_found = True
            requirement_date = day_str

        if not decision_found and any(kw in content for kw in decision_keywords):
            decision_found = True
            decision_date = day_str

        if not proposal_found and any(kw in content for kw in proposal_keywords):
            proposal_found = True
            proposal_date = day_str

    if requirement_found and requirement_date:
        events.append(Event(
            event_type=EventType.REQUIREMENT_CONFIRM,
            date=requirement_date,
            detail="客户首次明确描述需求或痛点",
            confidence=0.7,
        ))

    if decision_found and decision_date:
        events.append(Event(
            event_type=EventType.DECISION_MAKER_APPEAR,
            date=decision_date,
            detail="沟通中出现更高层级联系人或决策人",
            confidence=0.7,
        ))

    if proposal_found and proposal_date:
        events.append(Event(
            event_type=EventType.PROPOSAL_SENT,
            date=proposal_date,
            detail="发送报价/方案/合同相关内容",
            confidence=0.8,
        ))

    # 按日期排序
    events.sort(key=lambda e: e.date)
    return events


def format_events(events: list[Event]) -> str:
    """格式化事件列表为文本。"""
    if not events:
        return "(未检测到事件)"

    lines = []
    for e in events:
        conf = f" ({e.confidence:.0%})" if e.confidence < 1.0 else ""
        lines.append(f"- [{e.date}] {e.event_type.value}{conf}: {e.detail}")
    return "\n".join(lines)
