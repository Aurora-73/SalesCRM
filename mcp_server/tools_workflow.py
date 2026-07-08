"""Skill-MCP 融合工具：提供工作流导航和双向索引查询。

核心功能：
1. skill_map() — 查询工具与 Skill 的映射关系
2. workflow_step() — 按步骤执行工作流，返回下一步指引

数据来源：skill/mcp_index.yaml
"""

import os
import yaml

_SKILL_INDEX_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "skill",
    "mcp_index.yaml"
)


def _load_index() -> dict:
    """加载双向索引文件。"""
    with open(_SKILL_INDEX_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def skill_map(tool_name: str = None) -> str:
    """查询工具与 Skill 的映射关系。

    Args:
        tool_name: MCP 工具名（如 "person_brief"）。不填则返回所有工具的映射概览。

    Returns:
        Markdown 格式的映射信息，包含下一步建议和 Skill 引用。
    """
    index = _load_index()

    if tool_name:
        tool_info = index.get("tools", {}).get(tool_name)
        if not tool_info:
            return f"❌ 未找到工具 '{tool_name}' 的映射。可用工具列表：\n" + \
                   "\n".join(f"- {name}" for name in sorted(index.get("tools", {}).keys()))

        lines = [
            f"# {tool_name} — 映射信息",
            "",
            f"**描述**：{tool_info.get('description', '')}",
            "",
        ]

        skill_ref = tool_info.get("skill_ref")
        if skill_ref:
            lines.append(f"**Skill 参考**：`{skill_ref}`")

        workflow_ref = tool_info.get("workflow_ref")
        if workflow_ref:
            lines.append(f"**工作流位置**：`guide('{workflow_ref}')`")

        next_steps = tool_info.get("next_step", [])
        if next_steps:
            lines.append("")
            lines.append("**下一步建议**：")
            for step in next_steps:
                next_info = index.get("tools", {}).get(step, {})
                lines.append(f"- `{step}` — {next_info.get('description', '')}")

        return "\n".join(lines)

    lines = [
        "# Skill-MCP 双向映射概览",
        "",
        "## 使用方式",
        "",
        "```",
        "skill_map('person_brief')  # 查特定工具的映射",
        "skill_map()                # 查看所有工具概览",
        "```",
        "",
        "## 工具映射表",
        "",
        "| 工具 | 下一步建议 | Skill 参考 |",
        "|------|-----------|-----------|",
    ]

    tools = index.get("tools", {})
    for name, info in sorted(tools.items()):
        next_steps = ", ".join(info.get("next_step", []))[:50]
        skill_ref = info.get("skill_ref", "")[:30]
        lines.append(f"| `{name}` | {next_steps or '-'} | {skill_ref or '-'} |")

    lines.append("")
    lines.append("## 工作流列表")
    lines.append("")

    workflows = index.get("workflows", {})
    for name, wf in workflows.items():
        steps = len(wf.get("steps", []))
        lines.append(f"- `{name}` — {wf.get('name', '')}（{steps} 步）")

    return "\n".join(lines)


def workflow_step(workflow: str, step: int = None) -> str:
    """按步骤执行工作流，返回下一步指引。

    Args:
        workflow: 工作流名称（analysis/emergency_reply/weekly/maintain）。
        step: 步骤编号（从0开始）。不填则返回工作流概览。

    Returns:
        Markdown 格式的步骤信息，包含工具调用和下一步指引。
    """
    index = _load_index()
    workflows = index.get("workflows", {})

    if workflow not in workflows:
        return f"❌ 未找到工作流 '{workflow}'。可用工作流：\n" + \
               "\n".join(f"- `{name}` — {wf.get('name', '')}" for name, wf in workflows.items())

    wf = workflows[workflow]

    if step is None:
        lines = [
            f"# {wf.get('name', workflow)}",
            "",
            f"**步骤总数**：{len(wf.get('steps', []))}",
            "",
            "## 步骤列表",
            "",
            "| 步骤 | 名称 | 工具 | 描述 |",
            "|------|------|------|------|",
        ]

        for s in wf.get("steps", []):
            lines.append(f"| {s.get('number')} | {s.get('name')} | `{s.get('tool')}` | {s.get('description', '')[:30]} |")

        lines.append("")
        lines.append("## 使用方式")
        lines.append("")
        lines.append("```")
        lines.append(f"workflow_step('{workflow}')        # 查看工作流概览")
        lines.append(f"workflow_step('{workflow}', 0)    # 获取第0步详情")
        lines.append(f"workflow_step('{workflow}', 1)    # 获取第1步详情")
        lines.append("```")

        return "\n".join(lines)

    steps = wf.get("steps", [])
    if step < 0 or step >= len(steps):
        return f"❌ 步骤 {step} 不存在。此工作流共有 {len(steps)} 步（0-{len(steps)-1}）"

    current = steps[step]
    tool_name = current.get("tool")
    tool_info = index.get("tools", {}).get(tool_name, {})

    lines = [
        f"# {wf.get('name', workflow)} — 第 {step} 步",
        "",
        f"**步骤名称**：{current.get('name')}",
        f"**工具调用**：`{tool_name}`",
        f"**描述**：{current.get('description', '')}",
        "",
    ]

    if step < len(steps) - 1:
        next_step = steps[step + 1]
        lines.append(f"**下一步**（第 {step + 1} 步）：")
        lines.append(f"- 名称：{next_step.get('name')}")
        lines.append(f"- 工具：`{next_step.get('tool')}`")
        lines.append(f"- 描述：{next_step.get('description', '')}")

    if step > 0:
        prev_step = steps[step - 1]
        lines.append("")
        lines.append(f"**上一步**（第 {step - 1} 步）：")
        lines.append(f"- 名称：{prev_step.get('name')}")
        lines.append(f"- 工具：`{prev_step.get('tool')}`")

    skill_ref = tool_info.get("skill_ref")
    if skill_ref:
        lines.append("")
        lines.append(f"**Skill 参考**：`{skill_ref}`")

    lines.append("")
    lines.append("## 执行示例")
    lines.append("")
    lines.append("```")
    lines.append(f"# 当前步骤：{current.get('name')}")
    lines.append(f"{tool_name}(name='XX')")
    lines.append("")
    if step < len(steps) - 1:
        lines.append(f"# 完成后执行下一步：{next_step.get('name')}")
        lines.append(f"{next_step.get('tool')}(name='XX')")
    else:
        lines.append("# ✅ 工作流已完成")
    lines.append("```")

    return "\n".join(lines)