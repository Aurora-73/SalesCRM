"""Wiki 知识检索模块。

从 docs/wiki/ 检索知识页面，注入 LLM prompt。
"""

from engine.knowledge.wiki_index import WikiIndex, WikiPage
from engine.knowledge.wiki_retriever import WikiRetriever, WikiSnippet
from engine.knowledge.wiki_context import format_wiki_for_prompt

__all__ = [
    "WikiIndex",
    "WikiPage",
    "WikiRetriever",
    "WikiSnippet",
    "format_wiki_for_prompt",
]
