"""指标报告 — agent_metrics, agent_status, agent_rank, agent_weekly, agent_compare_analysis。"""
from __future__ import annotations

from pathlib import Path

import yaml

from engine.agent.core import _get_conn, _resolve_person
from engine.config import OUTPUTS_REPORTS_DIR, OUTPUTS_RANKINGS_DIR, OUTPUTS_ANALYSIS_DIR, slug_display_name


def agent_metrics(name: str) -> dict | str:
    from engine.analyzers.metrics import compute_metrics_for_contact
    conn, config = _get_conn()
    try:
        person = _resolve_person(conn, name)
        if not person:
            return f"未找到联系人: {name}"
        if not person.accounts:
            return f"未找到联系人: {name}"
        result = {"person_id": person.id, "display_name": person.display_name, "accounts": []}
        for account in person.accounts:
            wxid = account.conversation_id or account.wxid
            if not wxid:
                continue
            metrics = compute_metrics_for_contact(conn, config, wxid, account.display_name or person.display_name)
            result["accounts"].append({
                "wxid": wxid, "display_name": account.display_name,
                "composite": metrics.composite, "base_score": metrics.base_score,
                "signal_level": metrics.signal_level, "neediness_penalty": metrics.neediness_penalty,
                "interaction_pattern": metrics.interaction_pattern,
                "metrics": {k: v.to_dict() for k, v in metrics.all_metrics().items()},
                "session_recency": metrics.session_recency, "momentum": metrics.momentum,
                "initiation_source": metrics.initiation_source, "media_engagement": metrics.media_engagement,
            })
        return result
    finally:
        conn.close()


def agent_status(name: str) -> str:
    from engine.analyzers.metrics import compute_metrics_for_contact
    conn, config = _get_conn()
    try:
        person = _resolve_person(conn, name)
        if not person:
            return f"未找到联系人: {name}"
        if not person.accounts:
            return f"未找到联系人: {name}"
        parts = [f"# 状态: {person.display_name}\n"]
        parts.append(f"- person_id: {person.id}")
        parts.append(f"- 账号数: {len(person.accounts)}\n")
        for idx, account in enumerate(person.accounts, 1):
            wxid = account.conversation_id or account.wxid
            if not wxid:
                continue
            msg_row = conn.execute("SELECT COUNT(*) AS cnt FROM messages WHERE conversation_id = ?", (wxid,)).fetchone()
            message_count = msg_row["cnt"] if msg_row else 0
            metrics = compute_metrics_for_contact(conn, config, wxid, account.display_name or person.display_name)
            label = account.remark or account.nickname or account.display_name or account.wxid
            parts.append(f"## 账号 {idx}: {label} ({wxid[:25]})\n")
            parts.append(f"- 消息数: {message_count}")
            parts.append(f"- base_score: {metrics.base_score:.4f}")
            parts.append(f"- composite: {metrics.composite:.4f}")
            parts.append(f"- 信号等级: {metrics.signal_level}")
            parts.append("\n### 指标详情\n")
            parts.append("| 指标 | normalized | confidence | sample_size |")
            parts.append("|------|-----------|------------|-------------|")
            for name_k, mv in metrics.all_metrics().items():
                parts.append(f"| {name_k} | {mv.normalized:.4f} | {mv.confidence:.2f} | {mv.sample_size} |")
            if metrics.neediness_penalty < 1.0:
                parts.append(f"\n- 跟进投入惩罚: {metrics.neediness_penalty:.2f}")
            if metrics.interaction_pattern:
                parts.append(f"- 互动模式: {metrics.interaction_pattern}")
            sr = metrics.session_recency
            mom = metrics.momentum
            init_m = metrics.initiation_source
            if sr or mom or init_m:
                parts.append("\n### 动态信号\n")
                if sr:
                    parts.append(f"- 最近活跃: {sr.get('label', '未知')}")
                if mom:
                    parts.append(f"- 动量: {mom.get('direction', '未知')} ({mom.get('momentum', 1.0):.1f}x)")
                if init_m:
                    parts.append(f"- 发起方: {init_m.get('signal', '未知')}")
            media = metrics.media_engagement
            if media:
                sc = media.get("sticker_count", 0)
                ic = media.get("image_count", 0)
                if sc > 0 or ic > 0:
                    parts.append("\n### 媒体参与度\n")
                    parts.append(f"- 贴纸: {sc} 条 ({media.get('sticker_ratio', 0):.0%})")
                    parts.append(f"- 图片: {ic} 条 ({media.get('image_ratio', 0):.0%})")
                    ds = media.get("distinct_stickers", 0)
                    if ds > 0:
                        parts.append(f"- 贴纸词典: {ds} 种")
                mimicry = media.get("mimicry_signal", "")
                if mimicry:
                    parts.append(f"- 镜像信号: {mimicry}")
            parts.append("")
        return "\n".join(parts)
    finally:
        conn.close()


def agent_rank() -> str:
    from engine.analyzers.ranker import compute_rankings, format_ranking_table
    conn, config = _get_conn()
    try:
        ranking = compute_rankings(conn, config)
        return format_ranking_table(ranking, conn=conn)
    finally:
        conn.close()


def agent_weekly(deep: bool = False) -> str:
    from engine.analyzers.weekly_report import generate_weekly_report, format_weekly_summary
    conn, config = _get_conn()
    try:
        ranking, md = generate_weekly_report(conn, config, deep=deep)
        summary = format_weekly_summary(ranking, conn=conn)
        report_path = OUTPUTS_REPORTS_DIR / f"{ranking.week}_report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(md)
        return f"{summary}\n\n---\n周报已保存: {report_path}\n排名快照: {OUTPUTS_RANKINGS_DIR / f'{ranking.week}.yaml'}"
    finally:
        conn.close()


def agent_compare_analysis(name: str) -> str:
    """对比 latest.yaml 和 previous.yaml 的变化。"""
    conn, config = _get_conn()
    try:
        person = _resolve_person(conn, name)
        if not person:
            return f"未找到联系人: {name}"
        slug = slug_display_name(person.display_name)
        person_dir = OUTPUTS_ANALYSIS_DIR / f"{slug}__{person.id}"
        latest_path = person_dir / "latest.yaml"
        previous_path = person_dir / "previous.yaml"

        if not latest_path.exists():
            return f"没有找到 {person.display_name} 的分析结论"

        with open(latest_path, encoding="utf-8") as f:
            latest = yaml.safe_load(f)

        if not previous_path.exists():
            lines = [f"# {person.display_name} — 分析结论（首次）\n"]
            stage = latest.get("stage", {})
            lines.append(f"**阶段**: {stage.get('stage', '未知')}（置信度 {stage.get('confidence', 0):.0%}）")
            if latest.get("diagnosis"):
                lines.append(f"**诊断**: {latest['diagnosis']}")
            if latest.get("strategy"):
                lines.append(f"**策略**: {latest['strategy']}")
            lines.append(f"\n生成时间: {latest.get('generated_at', '未知')}")
            lines.append("（无历史版本可对比）")
            return "\n".join(lines)

        with open(previous_path, encoding="utf-8") as f:
            prev = yaml.safe_load(f)

        lines = [f"# {person.display_name} — 分析对比\n"]

        # 阶段变化
        cur_stage = latest.get("stage", {})
        prev_stage = prev.get("stage", {})
        cur_s = cur_stage.get("stage", "")
        prev_s = prev_stage.get("stage", "")
        if cur_s != prev_s:
            lines.append(f"**阶段变化**: {prev_s} → {cur_s}")
        else:
            lines.append(f"**阶段**: {cur_s}（未变化）")

        cur_conf = cur_stage.get("confidence", 0)
        prev_conf = prev_stage.get("confidence", 0)
        conf_diff = cur_conf - prev_conf
        if abs(conf_diff) > 0.01:
            direction = "↑" if conf_diff > 0 else "↓"
            lines.append(f"**置信度**: {prev_conf:.0%} → {cur_conf:.0%} ({direction}{abs(conf_diff):.0%})")

        # 诊断变化
        cur_diag = latest.get("diagnosis", "")
        prev_diag = prev.get("diagnosis", "")
        if cur_diag != prev_diag:
            lines.append(f"\n**诊断变化**:")
            lines.append(f"- 旧: {prev_diag or '（无）'}")
            lines.append(f"- 新: {cur_diag or '（无）'}")

        # 策略变化
        cur_strat = latest.get("strategy", "")
        prev_strat = prev.get("strategy", "")
        if cur_strat != prev_strat:
            lines.append(f"\n**策略变化**:")
            lines.append(f"- 旧: {prev_strat or '（无）'}")
            lines.append(f"- 新: {cur_strat or '（无）'}")

        # 时间
        lines.append(f"\n**上次分析**: {prev.get('generated_at', '未知')}")
        lines.append(f"**本次分析**: {latest.get('generated_at', '未知')}")

        return "\n".join(lines)
    finally:
        conn.close()
