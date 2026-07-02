"""上下文组装器 — 从数据库和文件系统组装人物上下文。

供 agent_brief 等工具函数使用。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

_BEIJING_TZ = timezone(timedelta(hours=8))


def _ts_to_beijing(ts):
    """Unix 秒级时间戳转北京时间字符串（内部存储仍为整数，接口处转为可读格式）。"""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=_BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")

from engine.config import Config, FACTS_PEOPLE_DIR, FACTS_SELF_DIR, OUTPUTS_RANKINGS_DIR
from engine.identity import resolve_contact, IdentityPerson


def query_message_context(
    conn: sqlite3.Connection,
    message_ids: list[str],
    before: int = 20,
    after: int = 20,
    my_wxid: str = "",
) -> dict:
    """根据消息 ID 获取前后上下文消息（不跨会话）。

    Returns:
        {"status": "ok", "data": {"contexts": [{target, before, after}, ...]}}
    """
    contexts: list[dict] = []
    for msg_id in message_ids:
        row = conn.execute(
            "SELECT id, conversation_id, sender_id, content, timestamp, type, platform, source "
            "FROM messages WHERE id = ?",
            (msg_id,),
        ).fetchone()
        if not row:
            continue
        conv_id = row["conversation_id"]
        ts = row["timestamp"]

        before_rows = conn.execute(
            "SELECT id, sender_id, content, timestamp, type, platform, source "
            "FROM messages WHERE conversation_id = ? AND timestamp < ? AND type = 1 "
            "ORDER BY timestamp DESC LIMIT ?",
            (conv_id, ts, before),
        ).fetchall()

        after_rows = conn.execute(
            "SELECT id, sender_id, content, timestamp, type, platform, source "
            "FROM messages WHERE conversation_id = ? AND timestamp > ? AND type = 1 "
            "ORDER BY timestamp ASC LIMIT ?",
            (conv_id, ts, after),
        ).fetchall()

        def _map(r):
            sid = r["sender_id"] or ""
            return {
                "id": r["id"],
                "sender_id": sid,
                "is_mine": sid == my_wxid if my_wxid else False,
                "content": r["content"] or "",
                "timestamp": r["timestamp"],
                "time_str": _ts_to_beijing(r["timestamp"]),
                "type": r["type"],
                "platform": r["platform"] or "wechat",
                "source": r["source"] or "sync",
            }

        target = _map(row)
        target["conversation_id"] = row["conversation_id"]
        contexts.append({
            "target": target,
            "before": [_map(r) for r in reversed(before_rows)],
            "after": [_map(r) for r in after_rows],
        })

    return {"status": "ok", "data": {"contexts": contexts}, "meta": {}}


@dataclass
class PersonContext:
    """组装好的人物上下文。"""
    person: IdentityPerson
    fact_archive: str            # 人物档案全文
    fact_archive_path: Path | None
    recent_messages: list[dict]  # 最近 N 条消息
    message_stats: dict          # 消息统计
    has_archive: bool            # 是否有事实档案
    historical_analysis: dict | None = None  # 上次保存的分析结果
    metrics: dict = field(default_factory=dict)       # 量化指标
    data_confidence: str = "未知"  # 数据可信度：充分/一般/不足
    ranking_trend: dict = field(default_factory=dict)  # 排名趋势
    similar_failures: list = field(default_factory=list)  # 相似失败案例


class ContextBuilder:
    """上下文组装器。"""

    def __init__(self, conn: sqlite3.Connection, config: Config):
        self._conn = conn
        self._config = config

    def build_person_context(
        self,
        person: IdentityPerson,
        recent_count: int = 50,
    ) -> PersonContext:
        """组装人物上下文。"""
        # 1. 读取事实档案
        archive_path = self._find_fact_archive(person)
        archive_text = ""
        if archive_path and archive_path.is_file():
            archive_text = archive_path.read_text(encoding="utf-8")

        # 2. 获取所有 wxid
        wxids = [a.wxid for a in person.accounts]

        # 3. 查询最近消息
        recent = self._query_recent_messages(wxids, recent_count)

        # 4. 查询消息统计
        stats = self._query_message_stats(wxids)

        # 5. 读取历史分析结果
        historical = self._load_historical_analysis(person.display_name, person.id)

        # 6. 计算量化指标（取第一个 wxid 的指标）
        metrics = self._compute_metrics(person, wxids)

        # 7. 计算数据可信度
        total = stats.get("total", 0)
        data_confidence = self._compute_data_confidence(total)

        # 8. 读取排名趋势
        ranking_trend = self._load_ranking_trend(person.id, set(wxids))

        # 9. 查找相似失败案例
        similar_failures = self._find_similar_failures(historical)

        return PersonContext(
            person=person,
            fact_archive=archive_text,
            fact_archive_path=archive_path,
            recent_messages=recent,
            message_stats=stats,
            has_archive=bool(archive_text),
            historical_analysis=historical,
            metrics=metrics,
            data_confidence=data_confidence,
            ranking_trend=ranking_trend,
            similar_failures=similar_failures,
        )

    def _find_fact_archive(self, person: IdentityPerson) -> Path | None:
        """查找人物的事实档案文件。"""
        person_id = person.id
        display_name = person.display_name

        # 先在 people/ 下搜索（格式：名称__person_id.md）
        if FACTS_PEOPLE_DIR.is_dir():
            for f in FACTS_PEOPLE_DIR.iterdir():
                if f.is_file() and f.suffix == ".md":
                    if person_id in f.stem:
                        return f

        # 再在 self/ 下搜索
        if FACTS_SELF_DIR.is_dir():
            for f in FACTS_SELF_DIR.iterdir():
                if f.is_file() and f.suffix == ".md":
                    if person_id in f.stem:
                        return f

        # 尝试模板匹配：显示名__person_id.md
        expected = f"{display_name}__{person_id}.md"
        candidate = FACTS_PEOPLE_DIR / expected
        if candidate.is_file():
            return candidate

        return None

    def _query_recent_messages(
        self,
        wxids: list[str],
        limit: int,
    ) -> list[dict]:
        """从 SQLite 查询最近 N 条消息。"""
        if not wxids:
            return []

        placeholders = ",".join("?" for _ in wxids)
        sql = f"""
            SELECT m.id, m.sender_id, m.type, m.content, m.timestamp
            FROM messages m
            WHERE m.conversation_id IN ({placeholders})
              AND m.type = 1
              AND m.content NOT LIKE '<?xml%'
            ORDER BY m.timestamp DESC
            LIMIT ?
        """
        rows = self._conn.execute(sql, (*wxids, limit)).fetchall()

        messages = []
        for row in reversed(rows):  # 按时间正序
            sender_id = row["sender_id"] or ""
            is_mine = sender_id == self._config.my_wxid
            messages.append({
                "id": row["id"],
                "sender_id": sender_id,
                "sender": "我" if is_mine else "客户",
                "is_mine": is_mine,
                "content": row["content"] or "",
                "timestamp": row["timestamp"],
                "time_str": _ts_to_beijing(row["timestamp"]),
            })
        return messages

    def _query_message_stats(self, wxids: list[str]) -> dict:
        """查询消息统计。"""
        if not wxids:
            return {}

        placeholders = ",".join("?" for _ in wxids)

        # 总数 + 各方计数
        sql = f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN sender_id = ? THEN 1 ELSE 0 END) as my_count,
                SUM(CASE WHEN sender_id != ? AND sender_id IS NOT NULL THEN 1 ELSE 0 END) as customer_count,
                MIN(timestamp) as first_ts,
                MAX(timestamp) as last_ts
            FROM messages
            WHERE conversation_id IN ({placeholders})
              AND type = 1
              AND content NOT LIKE '<?xml%'
        """
        row = self._conn.execute(
            sql, (self._config.my_wxid, self._config.my_wxid, *wxids)
        ).fetchone()

        if not row:
            return {}

        return {
            "total": row["total"] or 0,
            "my_count": row["my_count"] or 0,
            "customer_count": row["customer_count"] or 0,
            "first_ts": row["first_ts"],
            "last_ts": row["last_ts"],
        }

    def _load_historical_analysis(self, display_name: str, person_id: str) -> dict | None:
        """读取上次保存的分析结果。"""
        from engine.config import OUTPUTS_ANALYSIS_DIR, slug_display_name
        dir_name = f"{slug_display_name(display_name)}__{person_id}"
        latest_path = OUTPUTS_ANALYSIS_DIR / dir_name / "latest.yaml"
        if not latest_path.is_file():
            return None
        with open(latest_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _compute_metrics(self, person: IdentityPerson, wxids: list[str]) -> dict:
        """为该联系人计算量化指标。返回精简 dict 供 prompt 使用。"""
        if not wxids:
            return {}
        try:
            from engine.analyzers.metrics import compute_metrics_for_contact
            metrics_obj = compute_metrics_for_contact(
                self._conn, self._config, wxids[0],
                contact_name=person.display_name,
            )
            return {
                "composite": metrics_obj.composite,
                "base_score": metrics_obj.base_score,
                "signal_level": metrics_obj.signal_level,
                "fback": metrics_obj.fback.normalized,
                "rlatency": metrics_obj.rlatency.normalized,
                "qscore": metrics_obj.qscore.normalized,
                "escore": metrics_obj.escore.normalized,
                "msg_count": metrics_obj.msg_count.raw,
                "active_days": metrics_obj.active_days.raw,
                "recent": metrics_obj.recent.normalized,
                "fback_confidence": metrics_obj.fback.confidence,
                "rlatency_confidence": metrics_obj.rlatency.confidence,
                # 新增指标
                "fback_quality": metrics_obj.fback_quality.normalized,
                "escore_volatility": metrics_obj.escore_volatility.normalized,
                "qscore_personal": metrics_obj.qscore_personal.normalized,
                "qscore_functional": metrics_obj.qscore_functional.normalized,
                "rlatency_context": metrics_obj.rlatency_context.normalized,
                "neediness_penalty": metrics_obj.neediness_penalty,
                "interaction_pattern": metrics_obj.interaction_pattern,
                "msg_volume_trend": metrics_obj.msg_volume_trend.raw,
                "latency_trend": metrics_obj.latency_trend.raw,
                # 动态信号
                "session_recency": metrics_obj.session_recency,
                "momentum": metrics_obj.momentum,
                "initiation_source": metrics_obj.initiation_source,
                "media_engagement": metrics_obj.media_engagement,
            }
        except Exception:
            return {}

    @staticmethod
    def _compute_data_confidence(total_messages: int) -> str:
        """根据消息总数判断数据可信度。"""
        if total_messages >= 200:
            return "充分"
        if total_messages >= 50:
            return "一般"
        if total_messages > 0:
            return "不足"
        return "无数据"

    def _load_ranking_trend(self, person_id: str, wxids: set[str] = None) -> dict:
        """读取最新排名快照中该人物的趋势数据。"""
        if not OUTPUTS_RANKINGS_DIR.is_dir():
            return {}
        # 找最新的排名文件
        ranking_files = sorted(OUTPUTS_RANKINGS_DIR.glob("*.yaml"), reverse=True)
        if not ranking_files:
            return {}
        wxids = wxids or set()
        try:
            with open(ranking_files[0], encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not data or "rankings" not in data:
                return {}
            for entry in data["rankings"]:
                pid = entry.get("person_id", entry.get("_id", ""))
                # 匹配 person_id 或 wxid
                if pid == person_id or pid in wxids:
                    return {
                        "rank": entry.get("rank", 0),
                        "composite": entry.get("composite", 0),
                        "signal_level": entry.get("signal_level", ""),
                        "delta_rank": entry.get("delta_rank", 0),
                        "delta_composite": entry.get("delta_composite", 0),
                        "week": data.get("week", ""),
                    }
        except Exception:
            pass
        return {}

    @staticmethod
    def _find_similar_failures(historical: dict | None) -> list:
        """从历史分析中提取阶段，查找相似失败案例。"""
        if not historical:
            return []
        stage = ""
        stage_data = historical.get("stage", {})
        if isinstance(stage_data, dict):
            stage = stage_data.get("stage", "")
        elif isinstance(stage_data, str):
            stage = stage_data
        if not stage:
            return []
        try:
            from engine.facts.failure_archive import find_similar_failures
            cases = find_similar_failures(stage)
            return [c.to_yaml() for c in cases[:3]]
        except Exception:
            return []
