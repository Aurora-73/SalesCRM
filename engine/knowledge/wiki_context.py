"""Wiki prompt 格式化。

将 WikiSnippet 列表格式化为 prompt 独立段落。
"""

from __future__ import annotations

import re

from engine.knowledge.wiki_retriever import WikiSnippet


def _strip_frontmatter(content: str) -> str:
    """移除 YAML frontmatter，只保留正文。"""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            return content[end + 3:].strip()
    return content


def _extract_key_steps(body: str, max_chars: int = 1500) -> str:
    """从场景决策页中提取关键判断步骤和行动表。

    优先保留：表格、有序列表、"判断"/"止损"/"信号"相关段落。
    """
    lines = body.split("\n")
    priority_lines: list[str] = []
    other_lines: list[str] = []
    in_priority_section = False

    for line in lines:
        lower = line.lower()
        # 优先保留包含判断/行动关键词的段落
        if any(kw in lower for kw in ["判断", "止损", "信号", "什么时候", "怎么做", "不要做", "常见错误", "行动"]):
            in_priority_section = True
        elif line.startswith("## ") or line.startswith("# "):
            in_priority_section = False

        # 表格行始终保留
        if line.strip().startswith("|"):
            priority_lines.append(line)
        elif in_priority_section:
            priority_lines.append(line)
        else:
            other_lines.append(line)

    # 先放优先内容，再补充其他内容到 max_chars
    result = "\n".join(priority_lines).strip()
    if len(result) < max_chars:
        remaining = max_chars - len(result)
        extra = "\n".join(other_lines).strip()[:remaining]
        if extra:
            result = result + "\n\n" + extra

    return result[:max_chars]


def _format_snippets(snippets: list[WikiSnippet]) -> str:
    """将 snippet 列表格式化为正文内容（不含 header）。"""
    parts: list[str] = []
    for snippet in snippets:
        body = _strip_frontmatter(snippet.content)

        # 场景决策页：提取关键步骤
        if snippet.page_type == "scenario":
            parts.append(f"### 场景: {snippet.title}")
            parts.append(f"来源: {snippet.path}")
            if snippet.summary:
                parts.append(f"> {snippet.summary}")
            parts.append("")
            key_content = _extract_key_steps(body, max_chars=1500)
            parts.append(key_content)
            parts.append("")
        else:
            # 实体/主题/综合页：保留全文
            parts.append(f"### {snippet.title}")
            parts.append(f"来源: {snippet.path}")
            if snippet.confidence:
                parts.append(f"置信度: {snippet.confidence}")
            parts.append("")
            parts.append(body)
            parts.append("")
    return "\n".join(parts)


def format_wiki_for_prompt(snippets: list[WikiSnippet]) -> str:
    """将检索结果格式化为 prompt section。

    场景决策页提取关键步骤，实体页保留全文。
    空结果或低分命中时返回 fallback 指引。
    """
    if not snippets:
        return (
            "## 本地知识库参考（无匹配结果）\n"
            "未找到相关 Wiki 条目。请凭通用销售经验判断，并标记知识缺口告知用户"
            "（如「Wiki 缺少关于 XX 的条目」），以便后续补充知识库。\n"
        )

    # 低分命中检测：最高分 < 5 表示匹配较弱
    max_score = max(s.score for s in snippets)
    if max_score < 5:
        return (
            "## 本地知识库参考（低置信度匹配）\n"
            f"找到 {len(snippets)} 条相关条目，但匹配度较低（最高分 {max_score:.1f}）。"
            "以下内容仅供参考，请结合事实档案和实时数据独立判断。"
            "如确信存在相关知识但未命中，可能是关键词不匹配——"
            "尝试用同义词或相关概念重新搜索（如「逼单」vs「成交推进」vs「报价时机」）。\n\n"
            + _format_snippets(snippets)
        )

    parts = [
        "## 本地知识库参考（推理主轴）\n",
        "Wiki 是 Agent 推理的方法论主轴。当与实时数据冲突时，以实时数据为准；"
        "但 Wiki 框架始终是分析的出发点，不要机械套用条目内容。\n",
    ]
    parts.append(_format_snippets(snippets))
    return "\n".join(parts)
