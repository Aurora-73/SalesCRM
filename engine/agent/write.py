"""数据写入 — agent_note, agent_date, agent_evaluate, agent_events, agent_save_analysis, agent_save_from_markdown。"""
from __future__ import annotations

import re
import shutil
from datetime import datetime

import yaml

from engine.config import OUTPUTS_EVALUATIONS_DIR, slug_display_name
from engine.identity import IdentityPerson
from engine.agent.core import _get_conn, _resolve_person, _extract_sections

# ---------------------------------------------------------------------------
# agent_note — 添加备注
# ---------------------------------------------------------------------------

def agent_note(name: str, text: str) -> str:
    from engine.facts import append_note
    conn, config = _get_conn()
    try:
        person = _resolve_person(conn, name)
        if not person:
            return f"未找到联系人: {name}"
        path = append_note(person, text, my_wxid=config.my_wxid)
        return f"已写入备注: {path}"
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# agent_date — 记录会面
# ---------------------------------------------------------------------------

def agent_date(name: str, date_text: str | None = None, location: str | None = None, rating: int | None = None) -> str:
    from engine.facts import append_date_entry
    conn, config = _get_conn()
    try:
        person = _resolve_person(conn, name)
        if not person:
            return f"未找到联系人: {name}"
        path = append_date_entry(person, date_text=date_text, location=location, rating=rating, my_wxid=config.my_wxid)
        return f"已写入会面记录: {path}"
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# agent_evaluate — 记录评估
# ---------------------------------------------------------------------------

def agent_evaluate(name: str, text: str) -> str:
    conn, config = _get_conn()
    try:
        person = _resolve_person(conn, name)
        if not person:
            return f"未找到联系人: {name}"
        now = datetime.now()
        OUTPUTS_EVALUATIONS_DIR.mkdir(parents=True, exist_ok=True)
        eval_path = OUTPUTS_EVALUATIONS_DIR / f"{slug_display_name(person.display_name)}__{person.id}.yaml"
        entries = []
        if eval_path.is_file():
            try:
                with open(eval_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if isinstance(data, list):
                    entries = data
            except Exception:
                pass
        entries.append({"date": now.strftime("%Y-%m-%d"), "time": now.isoformat(timespec="seconds"), "text": text.strip()})
        with open(eval_path, "w", encoding="utf-8") as f:
            yaml.dump(entries, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        return f"已记录评估: {text.strip()}\n写入: {eval_path}"
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# agent_events — 事件检测
# ---------------------------------------------------------------------------

def agent_events(name: str, scan: bool = False, disconnect_days: int = 7) -> str:
    from engine.analyzers.events import detect_events, format_events
    conn, config = _get_conn()
    try:
        person = _resolve_person(conn, name)
        if not person:
            return f"未找到联系人: {name}"
        events = detect_events(conn, person, disconnect_days=disconnect_days)
        parts = [f"# {person.display_name} 的关系事件 ({len(events)} 条)\n"]
        parts.append(format_events(events))
        if scan and events:
            from engine.facts.people_archive import append_event
            written = 0
            for e in events:
                append_event(person, e.date, e.event_type.value, e.detail, my_wxid=config.my_wxid)
                written += 1
            parts.append(f"\n已写入 {written} 条事件到事实档案")
        return "\n".join(parts)
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# agent_save_analysis — 结构化保存
# ---------------------------------------------------------------------------

def agent_save_analysis(
    person: IdentityPerson, *,
    stage: str = "", confidence: float = 0.0, reasoning: str = "",
    signals: list[str] | None = None, next_step: str = "",
    diagnosis: str = "", strategy: str = "", risks: list[str] | None = None,
    skills_used: list[str] | None = None,
    evidence_refs: list[dict] | None = None,
    metric_snapshot: dict | None = None,
    data_window: dict | None = None,
    changed_from_previous: str | None = None,
) -> Path:
    from datetime import datetime as dt
    from pathlib import Path as P
    from engine.config import OUTPUTS_ANALYSIS_DIR
    slug = slug_display_name(person.display_name)
    person_dir = OUTPUTS_ANALYSIS_DIR / f"{slug}__{person.id}"
    person_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "generated_at": dt.now().isoformat(timespec="seconds"),
        "person_id": person.id, "display_name": person.display_name,
        "stage": {"stage": stage, "confidence": confidence, "reasoning": reasoning,
                   "signals": signals or [], "next_step": next_step},
        "diagnosis": diagnosis, "strategy": strategy, "risks": risks or [],
        "skills_used": skills_used or [],
    }
    if evidence_refs:
        data["evidence_refs"] = evidence_refs
    if metric_snapshot:
        data["metric_snapshot"] = metric_snapshot
    if data_window:
        data["data_window"] = data_window
    if changed_from_previous:
        data["changed_from_previous"] = changed_from_previous
    latest_path = person_dir / "latest.yaml"
    previous_path = person_dir / "previous.yaml"
    if latest_path.exists():
        shutil.copy2(latest_path, previous_path)
    with open(latest_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    history_dir = person_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    ts = dt.now().strftime("%Y-%m-%dT%H%M%S")
    history_path = history_dir / f"{ts}.yaml"
    with open(history_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return latest_path

# ---------------------------------------------------------------------------
# agent_save_from_markdown — Markdown 保存分析
# ---------------------------------------------------------------------------

def agent_save_from_markdown(person: IdentityPerson, markdown_text: str) -> Path:
    sections = _extract_sections(markdown_text)
    stage_text = sections.get("阶段", "").strip()
    stage_name = stage_text
    conf = 0.0
    conf_match = re.search(r"置信度[:\s]*(\d+(?:\.\d+)?)%?", stage_text)
    if conf_match:
        raw = float(conf_match.group(1))
        conf = raw / 100 if raw > 1 else raw
        stage_name = stage_text[: conf_match.start()].strip().rstrip("（(").strip()
    signals_raw = sections.get("信号", "")
    signals = [line.lstrip("- ").strip() for line in signals_raw.split("\n") if line.strip().startswith("- ")]
    next_step = sections.get("下一步", "").strip()
    risks_raw = sections.get("风险", "")
    risks = [line.lstrip("- ").strip() for line in risks_raw.split("\n") if line.strip().startswith("- ")]
    return agent_save_analysis(
        person, stage=stage_name, confidence=conf,
        reasoning=sections.get("依据", "").strip(), signals=signals,
        next_step=next_step, diagnosis=sections.get("诊断", "").strip(),
        strategy=sections.get("策略", "").strip(), risks=risks,
    )
