"""销售阶段识别器。根据指标、事件和失败档案自动识别客户当前阶段。"""

import sqlite3
from datetime import datetime
from typing import Optional, Tuple, Dict, List

from ..models.stage import STAGES, StageState, Stage, StageOverride, EvidenceEntry
from ..models.metrics import Metrics


def recognize_stage(
    conn: sqlite3.Connection,
    metrics: Metrics,
    contact_wxid: str,
    contact_name: str = "",
    stage_override: Optional[StageOverride] = None,
) -> Stage:
    """根据指标和事件识别当前销售阶段。"""
    if stage_override and stage_override.stage:
        return Stage(stage_state=_default_state(stage_override.stage), stage_override=stage_override)

    current_stage, advancement_signals, blockers = _classify_stage(conn, metrics, contact_wxid)
    
    if current_stage == "未识别":
        return Stage(stage_state=_default_state("未识别"))

    entered_at, days_in_current_stage = _get_stage_dates(conn, contact_wxid, current_stage)
    next_stage = _get_next_stage(current_stage)
    is_stagnant = _check_stagnant(days_in_current_stage, current_stage, metrics)

    stage_state = StageState(
        current_stage=current_stage,
        entered_at=entered_at,
        days_in_current_stage=days_in_current_stage,
        is_stagnant=is_stagnant,
        next_stage=next_stage,
        advancement_signals=advancement_signals,
        blockers=blockers,
    )

    evidence_chain = _build_evidence_chain(conn, contact_wxid, metrics, current_stage)

    return Stage(stage_state=stage_state, evidence_chain=evidence_chain)


def _default_state(stage_name: str) -> StageState:
    return StageState(
        current_stage=stage_name,
        next_stage=_get_next_stage(stage_name),
    )


def _classify_stage(
    conn: sqlite3.Connection,
    metrics: Metrics,
    contact_wxid: str,
) -> Tuple[str, List[str], List[str]]:
    """核心阶段分类逻辑。"""
    advancement_signals: List[str] = []
    blockers: List[str] = []

    if _is_failed(conn, contact_wxid):
        return "退出/失败", [], ["客户已标记为失败"]

    has_meeting = _has_event(conn, contact_wxid, "meeting")
    has_signed = _has_event(conn, contact_wxid, "signed")

    if has_signed:
        advancement_signals.append("已确认签约")
        return "签约确认", advancement_signals, blockers

    if metrics.composite >= 0.75:
        if has_meeting:
            advancement_signals.append("已有会面记录")
            advancement_signals.append("综合评分较高")
            return "方案推进", advancement_signals, blockers
        else:
            return "深入沟通", advancement_signals, blockers

    if metrics.composite >= 0.55:
        if has_meeting:
            advancement_signals.append("已有会面记录")
            return "持续跟进", advancement_signals, blockers
        else:
            return "深入沟通", advancement_signals, blockers

    if metrics.composite >= 0.35:
        return "初步接触", advancement_signals, blockers

    if metrics.recent.raw < 30:
        return "线索", advancement_signals, blockers

    return "未识别", advancement_signals, blockers


def _is_failed(conn: sqlite3.Connection, contact_wxid: str) -> bool:
    """检查是否在失败档案中。"""
    rows = conn.execute(
        "SELECT 1 FROM failure_archives WHERE contact_wxid = ?",
        (contact_wxid,),
    ).fetchone()
    return rows is not None


def _has_event(conn: sqlite3.Connection, contact_wxid: str, event_type: str) -> bool:
    """检查是否有指定类型的事件。"""
    rows = conn.execute(
        "SELECT 1 FROM events WHERE contact_wxid = ? AND event_type = ?",
        (contact_wxid, event_type),
    ).fetchone()
    return rows is not None


def _get_next_stage(current_stage: str) -> str:
    """获取下一阶段名称。"""
    terminal_stages = {"签约确认", "退出/失败"}
    if current_stage in terminal_stages:
        return ""
    try:
        idx = STAGES.index(current_stage)
        if idx < len(STAGES) - 1:
            return STAGES[idx + 1]
    except ValueError:
        pass
    return ""


def _get_stage_dates(
    conn: sqlite3.Connection,
    contact_wxid: str,
    current_stage: str,
) -> Tuple[str, int]:
    """估算阶段进入时间和停留天数。"""
    rows = conn.execute(
        "SELECT MIN(timestamp) AS first_ts, MAX(timestamp) AS last_ts "
        "FROM messages WHERE conversation_id = ?",
        (contact_wxid,),
    ).fetchone()

    if not rows or not rows["first_ts"]:
        return "", 0

    first_date = datetime.fromtimestamp(rows["first_ts"]).strftime("%Y-%m-%d")
    days_in_stage = (datetime.now() - datetime.fromtimestamp(rows["first_ts"])).days

    return first_date, days_in_stage


def _check_stagnant(days_in_stage: int, stage: str, metrics: Metrics) -> bool:
    """检查阶段是否停滞。"""
    terminal_stages = {"签约确认", "退出/失败", "未识别"}
    if stage in terminal_stages:
        return False

    if metrics and metrics.recent.raw > 30:
        return True

    stage_stagnation_days: Dict[str, int] = {
        "线索": 7,
        "初步接触": 14,
        "深入沟通": 21,
        "已会面": 14,
        "持续跟进": 21,
        "方案推进": 28,
    }

    threshold = stage_stagnation_days.get(stage, 14)
    return days_in_stage > threshold


def _build_evidence_chain(
    conn: sqlite3.Connection,
    contact_wxid: str,
    metrics: Metrics,
    current_stage: str,
) -> List[EvidenceEntry]:
    """构建阶段证据链。"""
    evidence: List[EvidenceEntry] = []

    rows = conn.execute(
        "SELECT timestamp, event_type, notes FROM events "
        "WHERE contact_wxid = ? ORDER BY timestamp",
        (contact_wxid,),
    ).fetchall()

    for row in rows:
        date_str = datetime.fromtimestamp(row["timestamp"]).strftime("%Y-%m-%d")
        evidence.append(EvidenceEntry(
            date=date_str,
            event=row["event_type"],
            source="events",
            stage_change="",
        ))

    if evidence:
        evidence[-1].stage_change = current_stage

    return evidence


def get_stage_summary(stage: Stage) -> Dict:
    """获取阶段摘要。"""
    return {
        "current_stage": stage.effective_stage,
        "stage_index": STAGES.index(stage.effective_stage) if stage.effective_stage in STAGES else -1,
        "days_in_current_stage": stage.stage_state.days_in_current_stage,
        "is_stagnant": stage.stage_state.is_stagnant,
        "next_stage": stage.stage_state.next_stage,
        "advancement_signals": stage.stage_state.advancement_signals,
        "blockers": stage.stage_state.blockers,
        "has_override": bool(stage.stage_override),
    }
