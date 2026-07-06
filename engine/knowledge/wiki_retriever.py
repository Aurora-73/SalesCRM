"""Wiki 检索器。

根据查询文本、任务类型、阶段等结构化输入检索 Wiki 页面。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.knowledge.wiki_index import WikiIndex, WikiPage


@dataclass
class WikiSnippet:
    """检索结果片段。"""
    title: str
    path: str
    page_type: str
    summary: str
    content: str
    tags: list[str] = field(default_factory=list)
    source_tier: list[str] = field(default_factory=list)
    confidence: str = ""
    score: float = 0.0


# 任务类型 → 允许的页面类型
_TASK_TYPE_FILTER: dict[str, set[str]] = {
    "reply":   {"entity", "topic", "scenario"},
    "meet":    {"entity", "topic", "scenario"},
    "ask":     {"entity", "topic", "synthesis", "scenario"},
    "analyze": {"entity", "topic", "synthesis", "scenario"},
}

# 任务类型 → 字符预算
_TASK_TYPE_BUDGET: dict[str, tuple[int, int]] = {
    "reply":   (3, 2500),
    "meet":    (4, 4000),
    "ask":     (6, 6000),
    "analyze": (8, 8000),
}


class WikiRetriever:
    """Wiki 检索器。"""

    def __init__(self, index: WikiIndex):
        self._index = index

    def retrieve(
        self,
        query_text: str,
        task_type: str = "analyze",
        stage: str = "",
        focus: str = "",
        max_chars: int | None = None,
        max_pages: int | None = None,
    ) -> list[WikiSnippet]:
        """检索 Wiki 页面。

        Args:
            query_text: 查询文本（用户输入、最近聊天、人物档案摘要等拼接）
            task_type: 任务类型（reply/meet/ask/analyze）
            stage: 当前销售阶段
            focus: 分析聚焦点
            max_chars: 最大字符数（默认按 task_type）
            max_pages: 最大页面数（默认按 task_type）
        """
        pages = self._index.pages
        if not pages:
            return []

        # 别名展开
        expanded_query = self._index.expand_query(query_text)

        # 预算
        default_pages, default_chars = _TASK_TYPE_BUDGET.get(task_type, (4, 4000))
        max_pages = max_pages or default_pages
        max_chars = max_chars or default_chars

        # focus 加权关键词
        focus_keywords = self._extract_focus_keywords(focus)

        # 允许的页面类型
        allowed_types = _TASK_TYPE_FILTER.get(task_type, {"entity", "topic", "synthesis"})

        # 打分
        scored: list[tuple[float, WikiPage]] = []
        for page in pages:
            if page.page_type not in allowed_types:
                continue
            score = self._score_page(page, expanded_query, task_type, stage, focus_keywords)
            if score > 0:
                scored.append((score, page))

        # 排序
        scored.sort(key=lambda x: x[0], reverse=True)
        top_pages = scored[:max_pages]

        # 读取内容并裁剪
        snippets: list[WikiSnippet] = []
        total_chars = 0
        for score, page in top_pages:
            content = self._index.get_page_content(page) or ""
            snippet_text = self._trim_content(content, page, max_chars - total_chars)
            if not snippet_text:
                continue
            snippet = WikiSnippet(
                title=page.title,
                path=page.path,
                page_type=page.page_type,
                summary=page.summary,
                content=snippet_text,
                tags=page.tags,
                source_tier=page.source_tier,
                confidence=page.confidence,
                score=score,
            )
            snippets.append(snippet)
            total_chars += len(snippet_text)
            if total_chars >= max_chars:
                break

        return snippets

    def _score_page(
        self,
        page: WikiPage,
        query_text: str,
        task_type: str,
        stage: str,
        focus_keywords: list[str],
    ) -> float:
        score = 0.0
        query_lower = query_text.lower()
        title_lower = page.title.lower()

        # 标题完全命中
        if title_lower in query_lower or query_lower in title_lower:
            score += 10
        else:
            # 标题子串命中（3字以上才加分，避免短子串误匹配）
            for char_seq in self._split_chinese(page.title):
                if len(char_seq) >= 3 and char_seq in query_lower:
                    score += 4
                    break

        # keyword 命中（所有匹配，不只第一个）
        kw_hits = sum(1 for kw in page.keywords if kw.lower() in query_lower)
        score += min(kw_hits, 3) * 5  # 最多 +15

        # 全查询命中加成：查询文本的大部分出现在 keywords 中
        query_words = [w for w in query_text.split() if len(w) >= 2]
        if query_words:
            kw_text = " ".join(page.keywords).lower()
            matched_words = sum(1 for w in query_words if w.lower() in kw_text)
            if matched_words >= len(query_words) * 0.6 and matched_words >= 2:
                score += 4  # 大部分查询词都命中了

        # tag 命中
        tag_hits = sum(1 for tag in page.tags if tag.lower() in query_lower)
        score += min(tag_hits, 2) * 4  # 最多 +8

        # search_terms 命中（口语化查询词，权重低于 keywords）
        if page.search_terms:
            st_hits = sum(1 for st in page.search_terms if st.lower() in query_lower)
            if st_hits > 0:
                score += min(st_hits, 3) * 3  # 最多 +9
                score += 2  # search_terms 命中即相关，降低噪声分干扰

        # summary 命中
        if page.summary and any(w in page.summary for w in query_text.split() if len(w) >= 2):
            score += 2

        # scenario 匹配 task_type
        if task_type in page.scenarios:
            score += 3

        # stage 匹配（强权重——阶段是核心过滤条件）
        if stage and stage in page.stages:
            score += 5

        # confidence 为 EXTRACTED
        if page.confidence == "EXTRACTED":
            score += 1

        # source_tier 包含 tier0/tier1
        if any(t in ("tier0", "tier1") for t in page.source_tier):
            score += 1

        # focus 关键词加权
        if focus_keywords:
            focus_text = (page.title + " " + " ".join(page.tags) + " " + page.summary + " " + " ".join(page.search_terms)).lower()
            focus_hits = sum(1 for fk in focus_keywords if fk in focus_text)
            score += focus_hits * 3

        return score

    @staticmethod
    def _extract_focus_keywords(focus: str) -> list[str]:
        """从 focus 参数提取关键词。"""
        if not focus:
            return []
        focus_map = {
            "signals": ["信号", "意向指标", "意向", "回应"],
            "strategy": ["策略", "方法", "技巧", "操作"],
            "risk": ["风险", "暂停", "冷淡", "挽回"],
            "date": ["会面", "见面", "线下", "转场"],
            "chat": ["沟通", "回复", "话题"],
        }
        return focus_map.get(focus, [focus])

    def _split_chinese(self, text: str) -> list[str]:
        """将中文标题拆分为可匹配的子串（2-4 字）。"""
        segments = []
        for length in (4, 3, 2):
            for i in range(len(text) - length + 1):
                seg = text[i:i + length]
                if any("一" <= c <= "鿿" for c in seg):
                    segments.append(seg)
        return segments

    def _trim_content(self, content: str, page: WikiPage, budget: int) -> str:
        """裁剪内容到预算内。优先保留标题、摘要、来源、核心段落。"""
        if budget <= 0:
            return ""

        # 跳过 frontmatter
        body = content
        if body.startswith("---"):
            end = body.find("---", 3)
            if end != -1:
                body = body[end + 3:].strip()

        # 如果内容在预算内，直接返回
        if len(body) <= budget:
            return body

        # 否则裁剪：保留标题 + 摘要 + 前 N 段
        lines = body.split("\n")
        result_lines: list[str] = []
        total = 0

        for line in lines:
            if total + len(line) + 1 > budget:
                break
            result_lines.append(line)
            total += len(line) + 1

        return "\n".join(result_lines) + "\n\n...(内容截断)"
