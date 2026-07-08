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
        parts = [f"# {person.display_name} 的客户事件 ({len(events)} 条)\n"]
        parts.append(format_events(events))
        if scan and events:
            from engine.facts.people_archive import append_event
            written = 0
            skipped = 0
            for e in events:
                _, is_new = append_event(person, e.date, e.event_type.value, e.detail, my_wxid=config.my_wxid)
                if is_new:
                    written += 1
                else:
                    skipped += 1
            parts.append(f"\n已写入 {written} 条新事件到事实档案")
            if skipped:
                parts.append(f"跳过 {skipped} 条重复事件")
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
) -> dict:
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
        "evidence_refs": evidence_refs or [],
        "metric_snapshot": metric_snapshot or {},
        "data_window": data_window or {},
        "changed_from_previous": changed_from_previous or "",
    }
    latest_path = person_dir / "latest.yaml"
    previous_path = person_dir / "previous.yaml"
    # 读取旧版本信息用于覆盖告知
    previous_info: dict | None = None
    changed_fields: list[str] = []
    if latest_path.exists():
        try:
            old_stat = latest_path.stat()
            with open(latest_path, encoding="utf-8") as f:
                old_data = yaml.safe_load(f) or {}
            previous_info = {
                "path": str(latest_path),
                "size": old_stat.st_size,
                "generated_at": old_data.get("generated_at", ""),
            }
            old_stage = old_data.get("stage", {}) or {}
            if (old_stage.get("stage") or "") != stage:
                changed_fields.append("stage")
            if old_stage.get("confidence", 0.0) != confidence:
                changed_fields.append("confidence")
            if (old_stage.get("reasoning") or "") != reasoning:
                changed_fields.append("reasoning")
            if (old_data.get("diagnosis") or "") != diagnosis:
                changed_fields.append("diagnosis")
            if (old_data.get("strategy") or "") != strategy:
                changed_fields.append("strategy")
        except Exception:
            previous_info = {"path": str(latest_path), "size": 0, "generated_at": ""}
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
    return {
        "path": latest_path,
        "previous_info": previous_info,
        "changed_fields": changed_fields,
        "history_path": history_path,
    }

# ---------------------------------------------------------------------------
# agent_save_from_markdown — Markdown 保存分析
# ---------------------------------------------------------------------------

_SECTION_KEYWORDS: dict[str, list[str]] = {
    "stage": ["场景理解", "阶段", "当前阶段", "销售阶段", "客户阶段", "关系阶段", "场景"],
    "signals": ["关键信号分析", "关键信号", "信号", "意向信号", "意向指标", "购买信号"],
    "diagnosis": ["Wiki 框架诊断", "诊断", "wiki", "框架"],
    "strategy": ["具体操作", "策略", "操作", "行动方案", "方案"],
    "risks": ["核心风险", "风险", "禁忌", "注意事项"],
    "reasoning": ["底层判断", "依据", "底层", "本质", "核心逻辑", "判断"],
    "next_step": ["下一步", "行动", "建议行动", "操作建议", "后续行动", "计划"],
}


def _find_section(sections: dict[str, str], keywords: list[str]) -> str:
    """按关键词匹配段名，优先精确匹配，回退到子串匹配。"""
    for key, content in sections.items():
        if key == "_header":
            continue
        for kw in keywords:
            if key.lower() == kw.lower():
                return content
    for key, content in sections.items():
        if key == "_header":
            continue
        key_lower = key.lower()
        for kw in keywords:
            if kw.lower() in key_lower:
                return content
    return ""


def _parse_list(text: str) -> list[str]:
    """从文本解析列表项，兼容 '- '、'* ' 前缀和 Markdown 表格。"""
    items: list[str] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("- ") or stripped.startswith("* "):
            items.append(stripped[2:].strip())
            i += 1
            continue
        if stripped.startswith("|"):
            table_rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = lines[i].strip()
                cells = [c.strip() for c in row.strip("|").split("|")]
                table_rows.append(cells)
                i += 1
            for j, cells in enumerate(table_rows):
                if j < 2:
                    continue
                non_empty = [c for c in cells if c]
                if non_empty:
                    items.append(" - ".join(non_empty))
            continue
        i += 1
    return items


def agent_save_from_markdown(person: IdentityPerson, markdown_text: str) -> Path:
    sections = _extract_sections(markdown_text)

    stage_text = _find_section(sections, _SECTION_KEYWORDS["stage"]).strip()
    stage_name = stage_text
    conf = 0.0
    conf_match = re.search(r"置信度[\s:：]*(\d+(?:\.\d+)?)\s*%?", stage_text)
    if conf_match:
        raw = float(conf_match.group(1))
        conf = raw / 100 if raw > 1 else raw
        stage_name = stage_text[: conf_match.start()].strip().rstrip("（(").strip()

    signals_raw = _find_section(sections, _SECTION_KEYWORDS["signals"])
    signals = _parse_list(signals_raw)

    next_step = _find_section(sections, _SECTION_KEYWORDS["next_step"]).strip()
    risks_raw = _find_section(sections, _SECTION_KEYWORDS["risks"])
    risks = _parse_list(risks_raw)

    diagnosis = _find_section(sections, _SECTION_KEYWORDS["diagnosis"]).strip()
    strategy = _find_section(sections, _SECTION_KEYWORDS["strategy"]).strip()
    reasoning = _find_section(sections, _SECTION_KEYWORDS["reasoning"]).strip()

    if not stage_name:
        print(f"[save_from_markdown] warning: stage 为空，已解析段名: {list(k for k in sections if k != '_header')}")
    if conf == 0.0 and "置信度" not in markdown_text:
        print(f"[save_from_markdown] warning: confidence 为 0，报告中未找到 '置信度' 字样")

    save_result = agent_save_analysis(
        person, stage=stage_name, confidence=conf,
        reasoning=reasoning, signals=signals,
        next_step=next_step, diagnosis=diagnosis,
        strategy=strategy, risks=risks,
    )
    yaml_path = save_result["path"]
    # 同时保存原始 Markdown 报告到 latest.md
    md_path = yaml_path.parent / "latest.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown_text)
    # 归档历史 MD
    from datetime import datetime as dt
    history_dir = yaml_path.parent / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    ts = dt.now().strftime("%Y-%m-%dT%H%M%S")
    history_md_path = history_dir / f"{ts}.md"
    with open(history_md_path, "w", encoding="utf-8") as f:
        f.write(markdown_text)
    return md_path
