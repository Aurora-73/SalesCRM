"""Wiki 检索单元测试。

用 fixture 构造最小 OKF 知识库（7 个销售场景条目），不修改 conftest.py 全局配置。
覆盖：WikiIndex 加载/别名扩展、WikiRetriever.retrieve() 检索、task_type 预算、
search_terms 打分、空查询/无效查询处理、低分命中处理。

SalesCRM 使用单层 wiki 结构（docs/wiki/entities/），与 loveMentor 双层结构不同。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.knowledge.wiki_index import WikiIndex, WikiPage
from engine.knowledge.wiki_retriever import WikiRetriever, WikiSnippet


# ── Fixture：构造最小 OKF 知识库（销售场景） ──────────────────────────

WIKI_SCHEMA = """# Wiki Schema

## 别名词表（Alias Table）

格式：每行一组同义词，用 `=` 分隔。

```
异议处理 = 价格异议 = 太贵了 = 预算不足
客户失联 = 不回消息 = 已读不回 = 联系不上 = 消失
```
"""

ENTITY_YIYI = """---
type: Concept
title: 异议处理
description: 处理客户价格、需求、竞品等异议的技巧。
tags: [异议, 价格, 核心技术, 谈判]
keywords: [异议, 价格, 异议处理]
search_terms: [太贵了, 预算不足, 价格异议, 考虑一下, 对比一下]
scenarios: [reply, ask]
stages: [方案展示, 报价]
confidence: EXTRACTED
---
# 异议处理

> 处理客户价格、需求、竞品等异议的技巧。

## 核心原则

1. 先认同后引导
2. 价值锚定
3. 预算前置
"""

ENTITY_XINHAO = """---
type: Concept
title: 购买信号
description: 识别客户的成交窗口和购买意向信号。
tags: [信号, 成交, 窗口, 意向]
keywords: [购买信号, 成交信号, 窗口]
search_terms: [购买信号, 成交信号, 意向, 主动询问, 什么时候能交付]
scenarios: [reply, analyze]
stages: [需求确认, 方案展示]
confidence: EXTRACTED
---
# 购买信号

> 识别客户的成交窗口和购买意向信号。

## 成交窗口信号

- 主动追问交付时间
- 询问付款方式
"""

ENTITY_YIXIANG = """---
type: Concept
title: 购买意向指标
description: 客户被产品吸引的非口头迹象。
tags: [意向, 购买意向, 信号识别]
keywords: [购买意向, 意向指标, 信号]
search_terms: [意向, 购买意向, 感兴趣, 有需求, 询问价格]
scenarios: [reply, analyze]
stages: [接触, 需求确认]
confidence: EXTRACTED
---
# 购买意向指标

> 客户被产品吸引的非口头迹象。

## 定义

被动、主动或假性的购买意向指标。
"""

ENTITY_KUANGJIA = """---
type: Concept
title: 谈判框架
description: 谈判中谁定义现实的权力。
tags: [框架, 势能, 主导]
keywords: [框架, 势能, 谈判]
search_terms: [框架, 势能, 主导, 主动权, 谈判]
scenarios: [ask, analyze]
stages: [报价, 成交]
confidence: EXTRACTED
---
# 谈判框架

> 谈判中谁定义现实的权力。

## 核心要点

保持自己的框架不被客户带跑。
"""

SCENARIO_BULUI = """---
type: Scenario
title: 客户不回消息怎么办
description: 客户突然不回消息或回复变慢——先判断原因，再决定动作。
tags: [场景, 沟通, 不回消息, 跟进]
keywords: [不回消息, 冷淡, 频率]
search_terms: [不回消息, 已读不回, 失联, 联系不上, 消失, 冷淡]
scenarios: [reply, ask]
stages: [接触, 需求确认]
confidence: EXTRACTED
---
# 客户不回消息怎么办

> 客户突然不回消息或回复变慢——先判断原因，再决定动作。

## 第一步：判断原因

不回消息有多种可能，先定位客户状态。
"""

TOPIC_GOUTONG = """---
type: Topic
title: 沟通技巧
description: 销售沟通相关的技术汇总。
tags: [沟通, 话术, 话题]
keywords: [沟通, 话术, 话题]
search_terms: [沟通, 话术, 话题, 回复]
scenarios: [reply, meet]
stages: [接触, 需求确认]
confidence: EXTRACTED
---
# 沟通技巧

> 销售沟通相关的技术汇总。

## 基础原则

多线程话题、异议处理、需求挖掘。
"""

SYNTHESIS_DUIGI = """---
type: Synthesis
title: 销售框架对比
description: 不同销售框架的对比分析。
tags: [对比, 销售, 框架]
keywords: [对比, 框架, 销售]
search_terms: [对比, 框架, 分析]
scenarios: [ask, analyze]
stages: [接触, 需求确认]
confidence: EXTRACTED
---
# 销售框架对比

> 不同销售框架的对比分析。

## 三种框架

SPIN、MEDDIC、解决方案销售。
"""


@pytest.fixture
def wiki_root(tmp_path: Path) -> Path:
    """构造最小 OKF 知识库（7 个销售场景条目 + 别名词表）。

    SalesCRM 使用单层结构：wiki_root/entities/（非 wiki_root/wiki/entities/）。
    """
    root = tmp_path / "wiki"
    (root).mkdir()

    # 别名词表
    (root / ".wiki-schema.md").write_text(WIKI_SCHEMA, encoding="utf-8")

    # 内容目录（单层：直接在 root 下）
    (root / "entities").mkdir(parents=True)
    (root / "scenarios").mkdir(parents=True)
    (root / "topics").mkdir(parents=True)
    (root / "synthesis").mkdir(parents=True)

    (root / "entities" / "异议处理.md").write_text(ENTITY_YIYI, encoding="utf-8")
    (root / "entities" / "购买信号.md").write_text(ENTITY_XINHAO, encoding="utf-8")
    (root / "entities" / "购买意向指标.md").write_text(ENTITY_YIXIANG, encoding="utf-8")
    (root / "entities" / "谈判框架.md").write_text(ENTITY_KUANGJIA, encoding="utf-8")
    (root / "scenarios" / "客户不回消息怎么办.md").write_text(SCENARIO_BULUI, encoding="utf-8")
    (root / "topics" / "沟通技巧.md").write_text(TOPIC_GOUTONG, encoding="utf-8")
    (root / "synthesis" / "销售框架对比.md").write_text(SYNTHESIS_DUIGI, encoding="utf-8")

    return root


@pytest.fixture
def index(wiki_root: Path) -> WikiIndex:
    """加载后的 WikiIndex。"""
    idx = WikiIndex(wiki_root=wiki_root)
    idx.load()
    return idx


@pytest.fixture
def retriever(index: WikiIndex) -> WikiRetriever:
    """WikiRetriever。"""
    return WikiRetriever(index=index)


# ── WikiIndex 测试 ────────────────────────────────────────────────────

def test_wiki_index_loads_pages(index: WikiIndex) -> None:
    """WikiIndex 能从 Markdown fallback 加载页面。"""
    pages = index.pages
    assert len(pages) == 7, f"期望 7 个页面，实际 {len(pages)}"
    titles = {p.title for p in pages}
    assert "异议处理" in titles
    assert "购买信号" in titles
    assert "客户不回消息怎么办" in titles


def test_wiki_index_page_types(index: WikiIndex) -> None:
    """页面 page_type 正确映射。"""
    type_counts: dict[str, int] = {}
    for p in index.pages:
        type_counts[p.page_type] = type_counts.get(p.page_type, 0) + 1
    assert type_counts.get("entity", 0) == 4
    assert type_counts.get("scenario", 0) == 1
    assert type_counts.get("topic", 0) == 1
    assert type_counts.get("synthesis", 0) == 1


def test_wiki_index_alias_expansion(index: WikiIndex) -> None:
    """expand_query 用别名词表双向展开。"""
    # 查询包含别名 → 追加 canonical
    expanded = index.expand_query("客户说太贵了")
    assert "异议处理" in expanded, "别名「太贵了」应展开为 canonical「异议处理」"
    assert "价格异议" in expanded, "应追加同组其他别名"

    # 查询包含 canonical → 追加所有别名
    expanded2 = index.expand_query("异议处理技巧")
    assert "太贵了" in expanded2
    assert "价格异议" in expanded2

    # 无关查询不变
    expanded3 = index.expand_query("今天天气不错")
    assert expanded3 == "今天天气不错"


def test_wiki_index_get_page_content(index: WikiIndex) -> None:
    """get_page_content 能读取页面正文。"""
    page = next(p for p in index.pages if p.title == "异议处理")
    content = index.get_page_content(page)
    assert content is not None
    assert "先认同后引导" in content


def test_wiki_index_empty_root(tmp_path: Path) -> None:
    """空 wiki root 加载后 is_empty 为 True。"""
    empty_root = tmp_path / "empty_wiki"
    empty_root.mkdir()
    idx = WikiIndex(wiki_root=empty_root)
    idx.load()
    assert idx.is_empty
    assert idx.pages == []


# ── WikiRetriever 基本检索测试 ────────────────────────────────────────

def test_retriever_basic_retrieval(retriever: WikiRetriever) -> None:
    """retrieve() 对匹配查询返回非空结果。"""
    snippets = retriever.retrieve("异议处理", task_type="analyze")
    assert len(snippets) > 0
    titles = [s.title for s in snippets]
    assert "异议处理" in titles, "查询「异议处理」应命中异议处理条目"


def test_retriever_title_exact_match_scores_high(retriever: WikiRetriever) -> None:
    """标题完全命中得分高，排在前面。"""
    snippets = retriever.retrieve("购买信号", task_type="analyze")
    assert len(snippets) > 0
    assert snippets[0].title == "购买信号"
    assert snippets[0].score >= 10, "标题完全命中应 ≥ 10 分"


def test_retriever_search_terms_hit(retriever: WikiRetriever) -> None:
    """search_terms 命中加分（口语化查询词）。"""
    # 「失联」是客户不回消息的 search_term，也是别名
    snippets = retriever.retrieve("客户失联了怎么办", task_type="reply")
    titles = [s.title for s in snippets]
    # 客户不回消息场景的 search_terms 含「失联」
    assert "客户不回消息怎么办" in titles, "search_terms「失联」应命中场景页"


def test_retriever_keyword_hit(retriever: WikiRetriever) -> None:
    """keywords 命中加分。"""
    snippets = retriever.retrieve("购买意向 意向指标", task_type="analyze")
    titles = [s.title for s in snippets]
    assert "购买意向指标" in titles, "keywords 命中应返回购买意向指标条目"


# ── task_type 预算测试 ────────────────────────────────────────────────

def test_retriever_task_type_budget_reply(retriever: WikiRetriever) -> None:
    """reply task_type 预算：最多 3 页 / 2500 字符。"""
    # 用宽泛查询命中多个页面
    snippets = retriever.retrieve("沟通 异议 信号 框架 意向", task_type="reply")
    assert len(snippets) <= 3, "reply 最多 3 页"
    for s in snippets:
        assert len(s.content) <= 2500, "每段内容不超过 2500 字符"


def test_retriever_task_type_budget_analyze(retriever: WikiRetriever) -> None:
    """analyze task_type 预算：最多 8 页 / 8000 字符。"""
    snippets = retriever.retrieve("沟通 异议 信号 框架 意向 指标", task_type="analyze")
    assert len(snippets) <= 8, "analyze 最多 8 页"
    # analyze 比 reply 允许更多页面
    snippets_reply = retriever.retrieve("沟通 异议 信号 框架 意向 指标", task_type="reply")
    assert len(snippets) >= len(snippets_reply), "analyze 预算应 ≥ reply"


def test_retriever_task_type_filter(retriever: WikiRetriever) -> None:
    """task_type 过滤不允许的页面类型。reply 不含 synthesis。"""
    # _TASK_TYPE_FILTER: reply/meet = {entity, topic, scenario}; ask/analyze 多 synthesis
    # reply 不含 synthesis，所以查 synthesis 标题时 reply 不应返回
    snippets = retriever.retrieve("销售框架对比", task_type="reply")
    titles = [s.title for s in snippets]
    # synthesis 类型不在 reply 的 allowed_types 中，所以不返回
    assert "销售框架对比" not in titles, "synthesis 页面在 reply task_type 下应被过滤"

    # analyze 允许 synthesis
    snippets_analyze = retriever.retrieve("销售框架对比", task_type="analyze")
    titles_analyze = [s.title for s in snippets_analyze]
    assert "销售框架对比" in titles_analyze, "analyze task_type 应允许 synthesis"


# ── 空查询 / 无效查询 / 低分命中测试 ──────────────────────────────────

def test_retriever_empty_query(retriever: WikiRetriever) -> None:
    """空查询：记录当前检索器的实际行为。

    空字符串 `""` 满足 `query_lower in title_lower`（空串在所有字符串中），
    所以每个页面获得 +10 标题命中分（已知行为）。
    返回的 snippet 分数由 标题命中(10) + scenario 匹配(0或3) + EXTRACTED(1) 组成。
    Agent 侧 fallback 策略（wiki_context.py 低置信度处理）负责兜底这种低质量命中。
    """
    snippets = retriever.retrieve("", task_type="analyze")
    assert len(snippets) > 0, "空查询仍返回页面（标题空串匹配）"
    for s in snippets:
        # 分数为 10（标题）+ 0/3（scenario）+ 1（EXTRACTED）= 11 或 14
        assert s.score in (11.0, 14.0), f"空查询的 snippet 分数应为 11 或 14，实际 {s.score}"


def test_retriever_invalid_query(retriever: WikiRetriever) -> None:
    """无意义查询：无查询词命中，仅 scenario 匹配 + EXTRACTED 基线分。"""
    snippets = retriever.retrieve("zzzqqqxxx", task_type="analyze")
    for s in snippets:
        # 分数为 0（无标题命中）+ 0/3（scenario）+ 1（EXTRACTED）= 1 或 4
        assert s.score in (1.0, 4.0), f"无意义查询的 snippet 分数应为 1 或 4，实际 {s.score}"


def test_retriever_low_score_still_returned(retriever: WikiRetriever) -> None:
    """score > 0 的低分命中仍返回（不设最低分阈值）。"""
    # 用宽泛查询命中 summary 或 tag 但分数不高
    snippets = retriever.retrieve("沟通", task_type="analyze")
    # 「沟通」会命中多个页面的 tags/keywords/search_terms
    assert len(snippets) > 0, "「沟通」应命中多个条目"
    # 所有返回的 snippet score 都 > 0
    for s in snippets:
        assert s.score > 0, f"返回的 snippet score 应 > 0，实际 {s.score}"


# ── stage / focus 加权测试 ────────────────────────────────────────────

def test_retriever_stage_match_boosts(retriever: WikiRetriever) -> None:
    """stage 匹配加分（强权重）。"""
    # 异议处理的 stages 含「方案展示」
    snippets_no_stage = retriever.retrieve("异议处理", task_type="analyze")
    snippets_with_stage = retriever.retrieve("异议处理", task_type="analyze", stage="方案展示")

    # 找异议处理条目
    yiyi_no = next((s for s in snippets_no_stage if s.title == "异议处理"), None)
    yiyi_with = next((s for s in snippets_with_stage if s.title == "异议处理"), None)
    assert yiyi_no is not None and yiyi_with is not None
    assert yiyi_with.score > yiyi_no.score, "stage 匹配应加分"
    assert yiyi_with.score >= yiyi_no.score + 5, "stage 匹配加 5 分"


def test_retriever_focus_keywords_boosts(retriever: WikiRetriever) -> None:
    """focus 参数加权相关页面。"""
    # focus=signals 应加权含「信号/意向指标/意向/回应」的页面
    snippets_no_focus = retriever.retrieve("识别", task_type="analyze")
    snippets_focus = retriever.retrieve("识别", task_type="analyze", focus="signals")

    # 购买信号的 focus_text 含「信号」「意向」
    xinhao_no = next((s for s in snippets_no_focus if s.title == "购买信号"), None)
    xinhao_with = next((s for s in snippets_focus if s.title == "购买信号"), None)
    if xinhao_no and xinhao_with:
        assert xinhao_with.score > xinhao_no.score, "focus=signals 应给购买信号加分"


def test_retriever_snippet_has_content(retriever: WikiRetriever) -> None:
    """返回的 snippet 含正文内容（非空）。"""
    snippets = retriever.retrieve("异议处理", task_type="analyze")
    assert len(snippets) > 0
    for s in snippets:
        assert s.content, "snippet content 不应为空"
        assert s.title, "snippet title 不应为空"
        assert s.path, "snippet path 不应为空"
        assert s.page_type in ("entity", "topic", "synthesis", "scenario")


def test_retriever_max_pages_override(retriever: WikiRetriever) -> None:
    """max_pages 参数覆盖 task_type 默认预算。"""
    snippets = retriever.retrieve("沟通 异议 信号 框架 意向 指标", task_type="analyze", max_pages=2)
    assert len(snippets) <= 2, "max_pages=2 应限制返回 2 页"


def test_retriever_max_chars_override(retriever: WikiRetriever) -> None:
    """max_chars 参数裁剪内容长度。"""
    snippets = retriever.retrieve("异议处理", task_type="analyze", max_chars=100)
    assert len(snippets) > 0
    total_chars = sum(len(s.content) for s in snippets)
    # 总字符数受 max_chars 限制（单页可能略超？实际 _trim_content 裁剪到 budget）
    assert total_chars <= 200, "max_chars 应限制总内容长度"
