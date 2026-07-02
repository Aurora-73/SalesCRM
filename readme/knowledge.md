# 销售知识库

## 概述

`engine/knowledge/` 提供销售知识库的检索能力。知识库内容存储在 `docs/wiki/` 目录下（OKF 格式），本模块负责索引、搜索、格式化输出。

## 核心文件

| 文件 | 行数 | 功能 |
|------|------|------|
| `wiki_index.py` | 311 | Wiki 索引（加载 search-index.json 或扫描 frontmatter） |
| `wiki_retriever.py` | 291 | 检索器（关键词匹配 + 评分 + 预算裁剪） |
| `wiki_context.py` | ~80 | 格式化输出（提取关键步骤，适配 prompt 注入） |

## 知识库内容结构

```
docs/wiki/                   # OKF 格式知识库
├── index.md                 # Knowledge Bundle 根索引
├── entities/                # 概念/框架
│   ├── index.md
│   ├── SPIN.md
│   ├── MEDDIC.md
│   └── ChallengerSale.md
├── scenarios/               # 场景决策页
│   ├── index.md
│   ├── 客户说太贵了怎么回.md
│   ├── 客户不回复了怎么办.md
│   └── 如何识别决策人.md
├── sources/                 # 参考资料
├── topics/                  # 主题索引
├── synthesis/               # 综合分析
└── okf-report.json          # OKF 验证报告
```

**当前状态**：`docs/wiki/` 已有 95 个条目（78 实体 + 14 场景 + 索引），OKF 格式已验证通过。

每个 Markdown 文件有 YAML frontmatter：

```yaml
---
title: SPIN 销售法
type: entity
tags: [SPIN, 销售方法, 需求挖掘]
keywords: [SPIN, situation, problem, implication, need-payoff]
stages: [需求确认, 方案演示, 报价谈判]
skills: [需求挖掘, 提问技巧]
---
```

## WikiIndex（索引）

```python
class WikiIndex:
    def __init__(self, wiki_root: Path):
        """加载索引。优先从 search-index.json 加载，不存在则扫描 frontmatter。"""

    def search(self, query: str) -> list[WikiPage]:
        """按关键词搜索。"""
```

### WikiPage

```python
@dataclass
class WikiPage:
    title: str           # "SPIN 销售法"
    path: str            # "docs/wiki/entities/SPIN.md"
    page_type: str       # "entity" / "scenario" / "comparison" / "query"
    tags: list[str]
    keywords: list[str]
    stages: list[str]
    skills: list[str]
    description: str
```

### 别名扩展

`expand_query()` 使用 `.wiki-schema.md` 中的别名表扩展搜索词。例如搜"价格太贵"会自动扩展为"预算有限""性价比""竞品价格"。

## WikiRetriever（检索器）

```python
class WikiRetriever:
    def __init__(self, index: WikiIndex):
        """初始化检索器。"""

    def retrieve(self, query: str, task_type: str = "default",
                 max_pages: int = 5, max_chars: int = 5000) -> list[WikiSnippet]:
        """搜索 + 评分 + 裁剪。"""
```

### 评分逻辑

每个 WikiPage 的得分基于多维度匹配：

| 维度 | 权重 | 说明 |
|------|------|------|
| title 精确匹配 | 高 | 标题包含搜索词 |
| keyword 匹配 | 中 | frontmatter keywords 匹配 |
| tag 匹配 | 中 | frontmatter tags 匹配 |
| search_term 匹配 | 低 | 全文搜索 |
| stage 匹配 | 中 | 与当前销售阶段匹配 |
| skill 匹配 | 低 | 与推荐 skill 匹配 |

### task_type 预算

不同场景有不同的页面数和字数预算：

| task_type | max_pages | max_chars | 典型场景 |
|-----------|-----------|-----------|---------|
| `default` | 5 | 5000 | 一般分析 |
| `reply` | 3 | 2500 | 紧急回复（要快） |
| `deep` | 8 | 10000 | 深度分析 |
| `search` | 10 | 8000 | 用户主动搜索 |

### WikiSnippet

```python
@dataclass
class WikiSnippet:
    title: str
    path: str
    content: str       # 裁剪后的内容
    score: float       # 匹配分数
    page_type: str
```

## 格式化输出（wiki_context.py）

```python
def format_wiki_for_prompt(snippets: list[WikiSnippet]) -> str:
    """将 WikiSnippet 列表格式化为可注入 prompt 的 Markdown。"""
```

输出格式：

```markdown
## Wiki: SPIN 销售法
> 来源: docs/wiki/entities/SPIN.md | 类型: entity

（关键步骤提取后的内容）

## Wiki: 价格异议应对
> 来源: docs/wiki/scenarios/价格异议应对.md | 类型: scenario

（关键步骤提取后的内容）
```

`_extract_key_steps()` 从长文档中提取关键步骤（限制 1500 字），避免注入过长内容。

## 数据流

```
tools.py: wiki_search('SPIN 需求挖掘')
    ↓
material.py: WikiIndex → WikiRetriever.retrieve('SPIN 需求挖掘')
    ↓
1. expand_query('SPIN 需求挖掘') → ['SPIN', '需求挖掘', 'situation problem implication']
2. search() → 匹配 WikiPage 列表
3. 评分排序
4. 裁剪到预算内
    ↓
返回 Markdown（标题 + 路径 + 摘要）

tools.py: wiki_show('docs/wiki/entities/SPIN.md')
    ↓
直接读取文件内容，返回 str
```

## 注意事项

1. **search-index.json 是预构建的**：新增 Wiki 页面后需要运行 `tools/generate_wiki_index.py` 更新索引。如果索引不存在，会回退到扫描 frontmatter（较慢）。
2. **别名表在 `.wiki-schema.md`**：同义词扩展依赖这个文件。如果搜索结果不理想，检查别名表是否覆盖了相关词。
3. **wiki_show 只读文件**：不做任何评分或裁剪，直接返回文件全部内容（受 max_chars 限制）。
4. **wiki_search 不需要 person**：只需要 conn 和 config（用于定位 wiki 根目录），不涉及具体联系人。
5. **内容不进 git**：`docs/` 目录有独立的二级 git 仓库，不推远程。
6. **知识库扩展**：`docs/wiki/` 为销售场景知识库（OKF 格式，持续扩充中）。