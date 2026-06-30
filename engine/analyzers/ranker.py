"""排名引擎。

从 SQLite 计算所有联系人的指标，按 person_id 聚合，生成排名。
"""

import sqlite3
from datetime import datetime
from pathlib import Path

import yaml

from engine.config import Config, OUTPUTS_RANKINGS_DIR
from engine.models.ranking import (
    Ranking, RankedPerson, RankingChange, InsufficientData,
)
from engine.analyzers.metrics import (
    compute_metrics_for_contact,
    get_all_contacts_with_messages,
)
from engine.analyzers.exclude import filter_contacts
from engine.identity.directory import (
    get_person_by_wxid,
    _person_id_for_wxid,
)


def _load_prev_ranking() -> dict[str, dict]:
    """加载上周排名快照（如果存在），返回 {person_id: {base_score, composite, rank}}。"""
    rankings_dir = OUTPUTS_RANKINGS_DIR
    if not rankings_dir.exists():
        return {}

    files = sorted(rankings_dir.glob("*.yaml"), reverse=True)
    if not files:
        return {}

    with open(files[0], "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        return {}

    result = {}
    for i, entry in enumerate(data.get("rankings", [])):
        # 优先用 person_id，兼容旧格式的 _id
        pid = entry.get("person_id", "") or entry.get("_id", "")
        if pid:
            result[pid] = {
                "base_score": entry.get("base_score", 0.0),
                "composite": entry.get("composite", 0.0),
                "rank": i + 1,
            }
    return result


def _resolve_person_id(conn: sqlite3.Connection, wxid: str) -> str:
    """解析 wxid 对应的 person_id。优先用 identity 系统，fallback 到确定性哈希。"""
    person = get_person_by_wxid(conn, wxid)
    if person:
        return person.id
    return _person_id_for_wxid(wxid)


def _resolve_person_name(conn: sqlite3.Connection, wxid: str) -> str | None:
    """解析 wxid 对应的 person 显示名。"""
    person = get_person_by_wxid(conn, wxid)
    return person.display_name if person else None


def compute_rankings(conn: sqlite3.Connection, config: Config) -> Ranking:
    """计算当前排名。按 person_id 聚合多账号。"""
    min_msgs = config.metrics.min_messages
    all_contacts = get_all_contacts_with_messages(conn, min_messages=0)

    if not all_contacts:
        return Ranking(
            week=_current_week(),
            generated_at=datetime.now().isoformat(timespec="seconds"),
            total_candidates=0,
        )

    # 排除过滤
    contacts, excluded = filter_contacts(
        all_contacts,
        conn,
        my_wxid=config.my_wxid,
        name_keywords=config.ranking.exclude.name_keywords,
    )

    # 按 person_id 分组
    person_groups: dict[str, list[dict]] = {}
    for c in contacts:
        pid = _resolve_person_id(conn, c["wxid"])
        person_groups.setdefault(pid, []).append(c)

    # 加载上周排名用于 delta 计算
    prev_rankings = _load_prev_ranking()

    ranked = []
    insufficient = []

    for pid, group in person_groups.items():
        # 按消息数降序，取消息最多的作为主账号
        group.sort(key=lambda x: x["message_count"], reverse=True)
        primary = group[0]
        total_msg = sum(c["message_count"] for c in group)

        # 显示名称：优先用 identity 系统的名称
        person_name = _resolve_person_name(conn, primary["wxid"])
        name = person_name or primary["display_name"]

        if total_msg < min_msgs:
            insufficient.append(InsufficientData(
                name=name,
                message_count=total_msg,
            ))
            continue

        prev = prev_rankings.get(pid)
        prev_base = prev["base_score"] if prev else None

        metrics = compute_metrics_for_contact(
            conn, config, primary["wxid"], name, prev_base_score=prev_base,
        )

        # 多账号时覆盖消息数为合并总数
        if len(group) > 1:
            metrics.msg_count.raw = total_msg
            from engine.analyzers.metrics import _clamp, _confidence
            cap = config.metrics.msg_count_cap
            import math
            metrics.msg_count.normalized = round(_clamp(math.log(1 + total_msg) / math.log(1 + cap)), 4)
            metrics.msg_count.sample_size = total_msg
            metrics.msg_count.confidence = round(_confidence(total_msg), 2)

        delta_composite = 0.0
        if prev:
            delta_composite = metrics.composite - prev["composite"]

        tags = []
        if len(group) > 1:
            tags.append(f"多账号({len(group)})")
        if primary.get("top_target"):
            tags.append("置顶")

        ranked.append(RankedPerson(
            name=name,
            _id=pid,
            person_id=pid,
            base_score=metrics.base_score,
            composite=metrics.composite,
            signal_level=metrics.signal_level,
            delta_composite=round(delta_composite, 4),
            delta_rank=0,
            tags=tags,
            interaction_pattern=metrics.interaction_pattern,
            urgency=metrics.urgency,
            recent_raw=int(metrics.recent.raw),
        ))

    # 按 composite 降序，同分按 base_score 降序
    ranked.sort(key=lambda r: (r.composite, r.base_score), reverse=True)

    # 设置排名和 delta_rank
    prev_rank_map = {k: v.get("rank", 0) for k, v in prev_rankings.items()}
    for i, r in enumerate(ranked):
        r.rank = i + 1
        prev_rank = prev_rank_map.get(r.person_id, 0)
        if prev_rank > 0:
            r.delta_rank = prev_rank - r.rank

    # 检测 risers 和 fallers
    risers = []
    fallers = []
    for r in ranked:
        if r.delta_rank >= 3:
            risers.append(RankingChange(name=r.name, reason="排名上升"))
        elif r.delta_rank <= -3:
            fallers.append(RankingChange(name=r.name, reason="排名下降"))
        elif r.delta_composite >= 0.05:
            risers.append(RankingChange(name=r.name, reason="得分上升"))
        elif r.delta_composite <= -0.05:
            fallers.append(RankingChange(name=r.name, reason="得分下降"))

    # 客户排名视图
    hot_customers = [r for r in ranked if r.composite >= 0.5]
    silent_customers = [r for r in ranked if r.recent_raw > 7]
    urgent_customers = [r for r in ranked if r.urgency >= 0.3]

    return Ranking(
        week=_current_week(),
        generated_at=datetime.now().isoformat(timespec="seconds"),
        total_candidates=len(ranked) + len(insufficient),
        rankings=ranked,
        risers=risers,
        fallers=fallers,
        insufficient_data=insufficient,
        hot_customers=hot_customers,
        silent_customers=silent_customers,
        urgent_customers=urgent_customers,
    )


def _current_week() -> str:
    now = datetime.now()
    return f"{now.year}-W{now.isocalendar()[1]:02d}"


def get_coverage_info(conn: sqlite3.Connection) -> str | None:
    """获取数据覆盖率摘要，用于排名和周报的可信度提示。"""
    from datetime import datetime

    try:
        total_conv = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        if total_conv == 0:
            return None

        ok_count = conn.execute(
            "SELECT COUNT(*) FROM sync_state WHERE last_error IS NULL"
        ).fetchone()[0]

        last_sync = conn.execute(
            "SELECT MAX(last_sync_at) FROM sync_state"
        ).fetchone()[0]
        last_sync_str = (
            datetime.fromtimestamp(last_sync).strftime("%m-%d %H:%M")
            if last_sync else "未知"
        )

        msg_range = conn.execute(
            "SELECT MIN(timestamp), MAX(timestamp) FROM messages"
        ).fetchone()
        range_str = ""
        if msg_range[0]:
            first = datetime.fromtimestamp(msg_range[0]).strftime("%Y-%m")
            last = datetime.fromtimestamp(msg_range[1]).strftime("%Y-%m")
            range_str = f"  消息范围: {first} ~ {last}"

        pct = ok_count / total_conv * 100
        return f"数据可信度: 会话覆盖率 {ok_count}/{total_conv} ({pct:.0f}%)  最后同步: {last_sync_str}{range_str}"
    except Exception:
        return None


def format_ranking_table(ranking: Ranking, conn: sqlite3.Connection | None = None) -> str:
    """格式化排名为终端表格。"""
    if not ranking.rankings:
        return "暂无排名数据（需要至少 20 条消息的联系人）"

    lines = [
        f"排名 ({ranking.week})",
        f"{'─' * 70}",
        f"{'排名':<4} {'姓名':<12} {'base':<8} {'composite':<10} {'信号':<8} {'趋势':<8} {'标签'}",
        f"{'─' * 70}",
    ]

    for r in ranking.rankings:
        trend = f"+{r.delta_composite:.3f}" if r.delta_composite >= 0 else f"{r.delta_composite:.3f}"
        rank_change = f"↑{r.delta_rank}" if r.delta_rank > 0 else (f"↓{abs(r.delta_rank)}" if r.delta_rank < 0 else "→")
        tags_str = ", ".join(r.tags) if r.tags else ""
        lines.append(
            f"{r.rank:<4} {r.name:<12} {r.base_score:<8.4f} {r.composite:<10.4f} "
            f"{r.signal_level:<8} {trend} {rank_change:<4} {tags_str}"
        )

    if ranking.insufficient_data:
        lines.append(f"\n{'─' * 70}")
        lines.append("数据不足（< 20 条消息）:")
        for ins in ranking.insufficient_data:
            lines.append(f"  {ins.name} — {ins.message_count} 条消息")

    if ranking.hot_customers:
        lines.append(f"\n{'─' * 70}")
        lines.append("热客榜（composite ≥ 0.5）:")
        for r in ranking.hot_customers[:10]:
            lines.append(f"  {r.name} — composite: {r.composite:.4f}")

    if ranking.silent_customers:
        lines.append(f"\n{'─' * 70}")
        lines.append(f"沉默榜（{len(ranking.silent_customers)} 人，最近 > 7 天无消息）:")
        for r in ranking.silent_customers[:10]:
            lines.append(f"  {r.name} — 沉默 {r.recent_raw} 天")

    if ranking.urgent_customers:
        lines.append(f"\n{'─' * 70}")
        lines.append(f"紧急榜（{len(ranking.urgent_customers)} 人，urgency ≥ 0.3）:")
        for r in ranking.urgent_customers[:10]:
            lines.append(f"  {r.name} — urgency: {r.urgency:.4f}")

    if conn:
        coverage = get_coverage_info(conn)
        if coverage:
            lines.append(f"\n{'─' * 70}")
            lines.append(coverage)

    return "\n".join(lines)
