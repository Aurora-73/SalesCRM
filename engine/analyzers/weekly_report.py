"""周报生成器。

生成 Markdown 周报并保存到 data/outputs/rankings/。
"""

import sqlite3
from datetime import datetime
from pathlib import Path

import yaml

from engine.config import Config, OUTPUTS_RANKINGS_DIR
from engine.models.ranking import Ranking
from engine.analyzers.ranker import compute_rankings, format_ranking_table, get_coverage_info


def generate_weekly_report(conn: sqlite3.Connection, config: Config,
                           deep: bool = False) -> tuple[Ranking, str]:
    """生成周报，返回 (ranking, markdown_report)。"""
    ranking = compute_rankings(conn, config)

    # 保存排名快照
    rankings_dir = OUTPUTS_RANKINGS_DIR
    rankings_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = rankings_dir / f"{ranking.week}.yaml"

    with open(snapshot_path, "w", encoding="utf-8") as f:
        yaml.dump(ranking.to_yaml(), f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # 深度分析
    deep_results: list[dict] = []
    if deep and ranking.rankings:
        deep_results = _run_deep_analysis(ranking, conn, config)

    # 生成 Markdown 周报
    md = _format_markdown(ranking, config, conn=conn, deep_results=deep_results)

    return ranking, md


def _run_deep_analysis(
    ranking: Ranking,
    conn: sqlite3.Connection,
    config: Config,
) -> list[dict]:
    """深度分析已由 Agent 自行完成，此函数保留为占位。

    原实现依赖已删除的 pipeline_analyze。Agent 驱动架构下，
    分析由 Claude Code 直接完成，不通过代码调 LLM API。
    """
    results = []
    for rp in ranking.rankings[:5]:
        results.append({
            "name": rp.name,
            "rank": rp.rank,
            "analysis": None,
            "error": "Agent-driven: 深度分析由 Agent 直接完成，不通过 pipeline",
        })
    return results


def _format_markdown(ranking: Ranking, config: Config,
                     conn: sqlite3.Connection | None = None,
                     deep_results: list[dict] | None = None) -> str:
    """格式化周报为 Markdown。"""
    lines = [
        f"# 销售周报 — {ranking.week}",
        "",
        f"> 生成时间: {ranking.generated_at}",
        f"> 候选人总数: {ranking.total_candidates}",
        f"> 有效排名: {len(ranking.rankings)}",
        f"> 数据不足: {len(ranking.insufficient_data)}",
    ]

    # 数据可信度
    if conn:
        coverage = get_coverage_info(conn)
        if coverage:
            lines.append(f"> {coverage}")

    lines.append("")
    lines.append("## 排名")
    lines.append("")

    if ranking.rankings:
        lines.append("| 排名 | 姓名 | base | composite | 信号 | 趋势 |")
        lines.append("|------|------|------|-----------|------|------|")
        for r in ranking.rankings:
            trend = f"+{r.delta_composite:.3f}" if r.delta_composite >= 0 else f"{r.delta_composite:.3f}"
            rank_change = ""
            if r.delta_rank > 0:
                rank_change = f"↑{r.delta_rank}"
            elif r.delta_rank < 0:
                rank_change = f"↓{abs(r.delta_rank)}"
            else:
                rank_change = "→"
            lines.append(
                f"| {r.rank} | {r.name} | {r.base_score:.4f} | {r.composite:.4f} | "
                f"{r.signal_level} | {trend} {rank_change} |"
            )
    else:
        lines.append("暂无排名数据")

    lines.append("")

    # 变动
    if ranking.risers or ranking.fallers:
        lines.append("## 变动")
        lines.append("")
        if ranking.risers:
            lines.append("**上升:**")
            for r in ranking.risers:
                lines.append(f"- {r.name}: {r.reason}")
            lines.append("")
        if ranking.fallers:
            lines.append("**下降:**")
            for f in ranking.fallers:
                lines.append(f"- {f.name}: {f.reason}")
            lines.append("")

    # 数据不足
    if ranking.insufficient_data:
        lines.append("## 数据不足")
        lines.append("")
        for ins in ranking.insufficient_data:
            lines.append(f"- {ins.name}: {ins.message_count} 条消息（需要 {config.metrics.min_messages} 条）")
        lines.append("")

    # 深度分析
    if deep_results:
        lines.append("## 深度分析（Top 5）")
        lines.append("")
        for dr in deep_results:
            name = dr["name"]
            rank = dr["rank"]
            analysis = dr.get("analysis")
            error = dr.get("error")

            lines.append(f"### #{rank} {name}")
            lines.append("")

            if error:
                lines.append(f"> 分析失败: {error}")
            elif analysis:
                s = analysis.stage
                lines.append(f"**阶段:** {s.stage}（置信度 {s.confidence:.0%}）")
                if s.reasoning:
                    lines.append(f"**依据:** {s.reasoning}")
                if s.signals:
                    lines.append(f"**信号:** {', '.join(s.signals)}")
                if analysis.diagnosis:
                    lines.append(f"**诊断:** {analysis.diagnosis}")
                if analysis.strategy:
                    lines.append(f"**策略:** {analysis.strategy}")
                if analysis.risks:
                    lines.append(f"**风险:** {', '.join(analysis.risks)}")
                if s.next_step:
                    lines.append(f"**下一步:** {s.next_step}")
            lines.append("")

    return "\n".join(lines)


def format_weekly_summary(ranking: Ranking, conn: sqlite3.Connection | None = None) -> str:
    """终端友好的周报摘要。"""
    table = format_ranking_table(ranking, conn=conn)
    lines = [table]

    if ranking.risers:
        lines.append("\n上升:")
        for r in ranking.risers:
            lines.append(f"  {r.name}: {r.reason}")

    if ranking.fallers:
        lines.append("\n下降:")
        for f in ranking.fallers:
            lines.append(f"  {f.name}: {f.reason}")

    return "\n".join(lines)
