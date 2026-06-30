"""Wiki 索引加载器。

读取 search-index.json，维护内存索引。
支持 Markdown fallback 扫描和别名词表加载。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from engine.config import ROOT_DIR, WIKI_DIR

# 内容目录类型映射
_TYPE_MAP = {
    "entities": "entity",
    "topics": "topic",
    "synthesis": "synthesis",
    "scenarios": "scenario",
    "sources": "source",
    "comparisons": "comparison",
}


@dataclass
class WikiPage:
    """单个 Wiki 页面的元数据。"""
    id: str
    title: str
    path: str           # 相对 Wiki 根目录
    page_type: str      # entity / topic / synthesis
    summary: str
    tags: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    search_terms: list[str] = field(default_factory=list)
    scenarios: list[str] = field(default_factory=list)
    stages: list[str] = field(default_factory=list)
    related_skills: list[str] = field(default_factory=list)
    source_tier: list[str] = field(default_factory=list)
    confidence: str = ""
    updated_at: str = ""


class WikiIndex:
    """Wiki 索引管理器。"""

    def __init__(self, wiki_root: str | Path | None = None):
        self._wiki_root: Path = self._resolve_wiki_root(wiki_root)
        self._content_dir: Path | None = None
        self._pages: list[WikiPage] = []
        self._aliases: dict[str, list[str]] = {}  # keyword -> [aliases]
        self._loaded = False

    @property
    def wiki_root(self) -> Path:
        return self._wiki_root

    @property
    def content_dir(self) -> Path | None:
        return self._content_dir

    @property
    def pages(self) -> list[WikiPage]:
        if not self._loaded:
            self.load()
        return self._pages

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def is_empty(self) -> bool:
        return len(self.pages) == 0

    @property
    def aliases(self) -> dict[str, list[str]]:
        if not self._loaded:
            self.load()
        return self._aliases

    def expand_query(self, text: str) -> str:
        """用别名词表双向展开查询文本。

        - 如果查询包含某个别名，追加 canonical
        - 如果查询包含 canonical，追加所有别名
        """
        expanded_parts: list[str] = []
        text_lower = text.lower()

        for canonical, alias_list in self._aliases.items():
            canon_lower = canonical.lower()
            all_forms = [canonical] + alias_list

            # 检查是否命中任意形式
            matched = False
            for form in all_forms:
                if form.lower() in text_lower:
                    matched = True
                    break

            if matched:
                # 追加所有未出现的形式
                for form in all_forms:
                    if form.lower() not in text_lower and form not in expanded_parts:
                        expanded_parts.append(form)

        if expanded_parts:
            return text + " " + " ".join(expanded_parts)
        return text

    def load(self) -> bool:
        """加载索引。优先读 search-index.json，fallback 扫描 Markdown。"""
        self._loaded = True
        self._content_dir = self._detect_content_dir()
        self._aliases = self._load_aliases()

        # 优先读 search-index.json
        index_path = self._wiki_root / "search-index.json"
        if index_path.is_file():
            try:
                with open(index_path, encoding="utf-8") as f:
                    data = json.load(f)
                self._pages = self._parse_index(data)
                if self._pages:
                    return True
            except (json.JSONDecodeError, KeyError):
                pass

        # fallback: 扫描 Markdown
        if self._content_dir:
            self._pages = self._scan_markdown()
            return len(self._pages) > 0

        return False

    def get_page_content(self, page: WikiPage) -> str | None:
        """读取页面正文。"""
        if not self._content_dir:
            return None
        full_path = self._content_dir.parent / page.path
        if not full_path.is_file():
            # 也尝试直接在 content_dir 下
            full_path = self._wiki_root / page.path
        if not full_path.is_file():
            return None
        try:
            return full_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def _resolve_wiki_root(self, wiki_root: str | Path | None) -> Path:
        if wiki_root:
            return Path(wiki_root).resolve()
        return WIKI_DIR

    def _detect_content_dir(self) -> Path | None:
        """自动探测内容目录：docs/wiki/wiki/ 或 docs/wiki/。"""
        # 优先检查双层 wiki/
        double = self._wiki_root / "wiki" / "entities"
        if double.is_dir():
            return self._wiki_root / "wiki"

        # 单层
        single = self._wiki_root / "entities"
        if single.is_dir():
            return self._wiki_root

        return None

    def _load_aliases(self) -> dict[str, list[str]]:
        """从 .wiki-schema.md 加载别名词表。

        返回 {canonical: [alias1, alias2, ...]} 映射。
        每组同义词中第一个词为 canonical。
        """
        schema_path = self._wiki_root / ".wiki-schema.md"
        if not schema_path.is_file():
            return {}

        aliases: dict[str, list[str]] = {}
        try:
            text = schema_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return {}

        # 找到 Alias Table 区域
        in_alias_section = False
        for line in text.splitlines():
            if "Alias Table" in line or "别名词表" in line:
                in_alias_section = True
                continue
            if in_alias_section:
                # 遇到新的 ## 区域结束
                if line.startswith("## ") and ("别名" not in line and "Alias" not in line):
                    break
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("```") or line.startswith("格式") or line.startswith("维护"):
                    continue
                # 解析: canonical = alias1 = alias2
                if "=" in line:
                    parts = [p.strip() for p in line.split("=") if p.strip()]
                    if len(parts) >= 2:
                        canonical = parts[0]
                        aliases[canonical] = parts[1:]
        return aliases

    def _parse_index(self, data: dict) -> list[WikiPage]:
        pages = []
        for p in data.get("pages", []):
            pages.append(WikiPage(
                id=p.get("id", ""),
                title=p.get("title", ""),
                path=p.get("path", ""),
                page_type=p.get("type", ""),
                summary=p.get("summary", ""),
                tags=p.get("tags", []),
                keywords=p.get("keywords", []),
                search_terms=p.get("search_terms", []),
                scenarios=p.get("scenarios", []),
                stages=p.get("stages", []),
                related_skills=p.get("related_skills", []),
                source_tier=p.get("source_tier", []),
                confidence=p.get("confidence", ""),
                updated_at=p.get("updated_at", ""),
            ))
        return pages

    def _scan_markdown(self) -> list[WikiPage]:
        """fallback：扫描 Markdown 文件提取元数据。"""
        pages = []
        if not self._content_dir:
            return pages

        scan_dirs = ["entities", "topics", "synthesis", "scenarios"]
        for subdir in scan_dirs:
            dir_path = self._content_dir / subdir
            if not dir_path.is_dir():
                continue
            for md_file in sorted(dir_path.glob("*.md")):
                page = self._parse_markdown_file(md_file, subdir)
                if page:
                    pages.append(page)
        return pages

    def _parse_markdown_file(self, path: Path, subdir: str) -> WikiPage | None:
        """从 Markdown 文件提取元数据。"""
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

        # 提取 frontmatter
        fm = {}
        if text.startswith("---"):
            m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
            if m:
                try:
                    import yaml
                    fm = yaml.safe_load(m.group(1)) or {}
                except Exception:
                    pass

        # 提取标题
        title = fm.get("title", "")
        if not title:
            m = re.search(r"^#\s+(.+)", text, re.MULTILINE)
            if m:
                title = m.group(1).strip()
        if not title:
            title = path.stem

        # 提取摘要：frontmatter summary > 标题下引用块 > 首段
        summary = fm.get("summary", "")
        if not summary:
            # 标题下引用块
            m = re.search(r"^#\s+.+\n+>\s*(.+)", text, re.MULTILINE)
            if m:
                summary = m.group(1).strip()
        if not summary:
            # 首段（跳过 frontmatter 和标题）
            body = re.sub(r"^---.*?---\s*", "", text, flags=re.DOTALL)
            body = re.sub(r"^#\s+.+\n*", "", body, count=1).strip()
            for line in body.split("\n"):
                line = line.strip()
                if line and not line.startswith(">"):
                    summary = line[:120]
                    break

        # 相对 wiki root 的路径
        rel_path = path.relative_to(self._wiki_root).as_posix()

        return WikiPage(
            id=f"{subdir}-{path.stem}",
            title=title,
            path=rel_path,
            page_type=_TYPE_MAP.get(subdir, subdir),
            summary=summary,
            tags=fm.get("tags", []),
            keywords=fm.get("keywords", []),
            search_terms=fm.get("search_terms", []),
            scenarios=fm.get("scenarios", []),
            stages=fm.get("stages", []),
            related_skills=fm.get("related_skills", []),
            source_tier=fm.get("source_tier", []),
            confidence=fm.get("confidence", "EXTRACTED"),
            updated_at=fm.get("updated_at", ""),
        )
