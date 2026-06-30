"""失败案例档案读写。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml

from engine.config import FACTS_DIR
from engine.models.failure import FailureCase


FAILURES_DIR = FACTS_DIR / "failures"


def _ensure_dir() -> None:
    FAILURES_DIR.mkdir(parents=True, exist_ok=True)


def save_failure(case: FailureCase) -> Path:
    """保存失败案例到 YAML 文件。返回文件路径。"""
    _ensure_dir()
    # 文件名：{date}_{person_slug}.yaml
    slug = case.person.replace("/", "_").replace("\\", "_")[:20] or "unknown"
    date_str = case.date or datetime.now().strftime("%Y-%m-%d")
    filename = f"{date_str}_{slug}.yaml"
    path = FAILURES_DIR / filename
    # 如果已存在，加序号
    if path.exists():
        i = 2
        while True:
            candidate = FAILURES_DIR / f"{date_str}_{slug}_{i}.yaml"
            if not candidate.exists():
                path = candidate
                break
            i += 1
    data = case.to_yaml()
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return path


def load_all_failures() -> list[FailureCase]:
    """读取所有失败案例。"""
    _ensure_dir()
    cases: list[FailureCase] = []
    for f in sorted(FAILURES_DIR.glob("*.yaml")):
        try:
            with open(f, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if data:
                cases.append(FailureCase.from_yaml(data))
        except Exception:
            continue
    return cases


def find_similar_failures(
    current_stage: str,
    current_signals: list[str] = None,
) -> list[FailureCase]:
    """查找与当前阶段/信号相似的失败案例。"""
    all_cases = load_all_failures()
    similar: list[FailureCase] = []
    current_signals = current_signals or []

    for case in all_cases:
        # 阶段匹配
        if current_stage and case.stage:
            if current_stage in case.stage or case.stage in current_stage:
                similar.append(case)
                continue
        # 信号匹配
        if current_signals and case.signals:
            overlap = set(current_signals) & set(case.signals)
            if overlap:
                similar.append(case)
    return similar


def format_failures(cases: list[FailureCase]) -> str:
    """格式化失败案例列表。"""
    if not cases:
        return "(无失败案例)"

    lines = []
    for i, c in enumerate(cases, 1):
        name = c.person or "未知"
        stage = c.stage or c.stage_reached or "未知阶段"
        lines.append(f"### 案例 {i}: {name}（{stage}）")
        if c.cause:
            lines.append(f"原因: {c.cause}")
        if c.lesson:
            lines.append(f"教训: {c.lesson}")
        if c.signals:
            lines.append(f"信号: {', '.join(c.signals)}")
        if c.outcome:
            lines.append(f"结果: {c.outcome}")
        lines.append("")
    return "\n".join(lines)
