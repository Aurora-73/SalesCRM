"""Wiki/框架推荐 — 根据信号和数据推荐相关 Wiki 页面。"""
from __future__ import annotations

import sqlite3
from engine.config import Config
from engine.identity import IdentityPerson

# 分析框架 Wiki 页面
_FRAMEWORK_WIKI: dict[str, list[tuple[str, str]]] = {
    "always": [
        ("wiki/entities/意向指标.md", "判断客户对产品有没有兴趣的核心框架"),
        ("wiki/entities/销售三要素.md", "需求匹配+价值认可+决策链完整——三者缺一不可"),
        ("wiki/entities/投入控制.md", "跟进投入比失衡时的止损框架"),
    ],
    "rejection": [
        ("wiki/scenarios/客户说预算不够.md", "客户拒绝后的行动方案和策略调整"),
        ("wiki/entities/客户分类.md", "客户把你归类为'备选'还是'首选'的判断框架"),
        ("wiki/scenarios/什么时候该止损.md", "五维度止损判断框架"),
    ],
    "confession": [
        ("wiki/scenarios/客户主动咨询怎么办.md", "客户主动时如何回应——积极但不急于成交"),
        ("wiki/entities/推进节奏.md", "商务推进的时机和方法"),
    ],
    "invitation": [
        ("wiki/scenarios/从线上沟通到首次会面.md", "线上到线下的关键一步"),
        ("wiki/scenarios/首次演示怎么安排.md", "演示设计和推进节奏"),
    ],
    "cold": [
        ("wiki/scenarios/客户一直聊但不成交.md", "聊了很久但不推进的判断和应对"),
        ("wiki/scenarios/什么时候该止损.md", "五维度止损判断框架"),
        ("wiki/entities/频率控制法则.md", "频率控制的核心法则"),
    ],
    "moments_strong_signal": [
        ("wiki/entities/意向指标.md", "朋友圈评论是明确的意向信号——客户主动找话题互动"),
        ("wiki/entities/意向识别.md", "朋友圈互动 vs 聊天态度矛盾时如何判断成交意向"),
    ],
    "moments_weak_signal": [
        ("wiki/entities/意向指标.md", "点赞是弱意向信号——有关注但不强烈"),
    ],
}


def _build_framework_recommendations(signals: dict[str, list[str]], has_archive: bool) -> list[tuple[str, str]]:
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for path, desc in _FRAMEWORK_WIKI["always"]:
        if path not in seen:
            result.append((path, desc))
            seen.add(path)
    for signal_type in ("rejection", "confession", "invitation", "moments_strong_signal", "moments_weak_signal"):
        if signal_type in signals:
            for path, desc in _FRAMEWORK_WIKI.get(signal_type, []):
                if path not in seen:
                    result.append((path, desc))
                    seen.add(path)
    if "rejection" not in signals and "confession" not in signals and "moments_strong_signal" not in signals:
        for path, desc in _FRAMEWORK_WIKI.get("cold", []):
            if path not in seen:
                result.append((path, desc))
                seen.add(path)
    return result


def _recommend_wiki(conn: sqlite3.Connection, config: Config, person: IdentityPerson,
                    ctx, events: list, max_pages: int = 5) -> list[dict]:
    from engine.knowledge.wiki_index import WikiIndex
    from engine.knowledge.wiki_retriever import WikiRetriever
    query_parts = []
    if ctx.recent_messages:
        recent_msgs = ctx.recent_messages[-15:]
        recent_text = " ".join(m.get("content", "")[:80] for m in recent_msgs)
        query_parts.append(recent_text)
    if ctx.fact_archive:
        archive = ctx.fact_archive
        for section_name in ["关键信息", "当前状态", "关系时间线"]:
            idx = archive.find(f"## {section_name}")
            if idx != -1:
                end = archive.find("\n## ", idx + 3)
                section = archive[idx:end] if end != -1 else archive[idx:]
                query_parts.append(section[:300])
    if events:
        event_text = " ".join(e.event_type.value for e in events[:2])
        query_parts.append(event_text)
    query_text = " ".join(query_parts).strip()
    if not query_text:
        return []
    stage = ""
    if ctx.historical_analysis:
        stage = ctx.historical_analysis.get("stage", {}).get("stage", "")
    index = WikiIndex()
    if not index.load() or index.is_empty:
        return []
    retriever = WikiRetriever(index)
    snippets = retriever.retrieve(
        query_text=query_text, task_type="analyze", selected_skills=None,
        stage=stage, max_chars=5000, max_pages=max_pages,
    )
    return [
        {"type": "wiki", "title": s.title, "path": s.path, "page_type": s.page_type,
         "summary": s.summary, "score": s.score}
        for s in snippets
    ]
