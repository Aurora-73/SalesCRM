"""摘要辅助 — 个人模式检测、消息筛选、月度统计。"""
from __future__ import annotations

import sqlite3
from collections import Counter

from engine.config import OUTPUTS_ANALYSIS_DIR


def _detect_personal_patterns() -> list[str]:
    if not OUTPUTS_ANALYSIS_DIR.is_dir():
        return []
    diagnoses: list[str] = []
    stages: list[str] = []
    for d in OUTPUTS_ANALYSIS_DIR.iterdir():
        if not d.is_dir():
            continue
        yaml_path = d / "latest.yaml"
        if not yaml_path.is_file():
            continue
        try:
            import yaml
            with open(yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                continue
            diag = data.get("diagnosis", "")
            stage_info = data.get("stage", {})
            if diag:
                diagnoses.append(diag)
            if stage_info.get("stage"):
                stages.append(stage_info["stage"])
        except Exception:
            continue
    if len(diagnoses) < 2:
        return []
    warnings: list[str] = []
    _PATTERN_KEYWORDS = {
        "价值低估": ("价格敏感", "只问不买"),
        "跟进过度": ("投入过多", "过度付出", "太主动"),
        "停滞不前": ("只聊天", "不推进"),
        "沟通质量低": ("聊天质量", "技术话题", "成就展示", "工作汇报"),
        "会面失败": ("约不出来", "被拒", "没空", "不推进"),
    }
    for pattern_name, keywords in _PATTERN_KEYWORDS.items():
        count = sum(1 for d in diagnoses if any(kw in d for kw in keywords))
        if count >= 2:
            warnings.append(f"你最近 {len(diagnoses)} 个分析中有 {count} 个提到「{pattern_name}」——这可能是你的个人模式，需要注意。")
    stage_counts = Counter(stages)
    for stage, count in stage_counts.items():
        if count >= 3 and stage in ("冷淡/停滞", "退出/失败", "有基本互动"):
            warnings.append(f"你有 {count} 个联系人停留在「{stage}」阶段——可能需要调整整体策略。")
    return warnings


def _select_important_messages(messages: list[dict], max_count: int) -> list[dict]:
    from engine.agent.signals import SIGNAL_KEYWORDS
    if len(messages) <= max_count:
        return messages
    important_indices: set[int] = set()
    for i, msg in enumerate(messages):
        content = msg.get("content", "")
        if any(kw in content for kw in SIGNAL_KEYWORDS):
            for j in range(max(0, i - 2), min(len(messages), i + 3)):
                important_indices.add(j)
    if len(important_indices) >= max_count:
        sorted_indices = sorted(important_indices)
        return [messages[i] for i in sorted_indices[-max_count:]]
    remaining = max_count - len(important_indices)
    recent_indices = [i for i in range(len(messages)) if i not in important_indices]
    fill_indices = recent_indices[-remaining:]
    all_indices = sorted(important_indices | set(fill_indices))
    return [messages[i] for i in all_indices[-max_count:]]


def _generate_monthly_summary(conn: sqlite3.Connection, wxids: list[str], my_wxid: str = "") -> str:
    if not wxids:
        return ""
    placeholders = ",".join("?" for _ in wxids)
    sql = f"""
        SELECT strftime('%Y-%m', timestamp, 'unixepoch', 'localtime') as month,
               COUNT(*) as total,
               SUM(CASE WHEN sender_id = ? THEN 1 ELSE 0 END) as my_count
        FROM messages
        WHERE conversation_id IN ({placeholders}) AND type = 1 AND content NOT LIKE '<?xml%'
        GROUP BY month ORDER BY month
    """
    rows = conn.execute(sql, (my_wxid, *wxids)).fetchall()
    if not rows:
        return ""
    lines = ["| 月份 | 总消息 | 我 | 客户 |", "|------|--------|-----|-----|"]
    for row in rows:
        month, total, my = row[0], row[1], row[2]
        client = total - my
        lines.append(f"| {month} | {total} | {my} | {client} |")
    return "\n".join(lines)
