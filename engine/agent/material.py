"""材料搜索与阅读 — agent_material_search, agent_material_show。"""
from __future__ import annotations

import json
import sqlite3
import yaml

from engine.config import Config, ROOT_DIR, OUTPUTS_ANALYSIS_DIR
from engine.agent.core import _build_cross_refs, _validate_path


def _search_skills(query_terms: list[str], results: list[dict]) -> None:
    from engine.agent.registry import SkillRegistry
    registry = SkillRegistry(ROOT_DIR / "skills")
    registry.scan()
    query_text = " ".join(query_terms)
    matches = registry.search_by_triggers(query_text)
    for name, score in matches[:10]:
        meta = registry.get(name)
        if meta:
            results.append({
                "type": "skill", "title": meta.display_name or name,
                "path": str(meta.path.relative_to(ROOT_DIR)).replace("\\", "/"),
                "reason": f"trigger match (score={score:.1f})",
                "keywords": ", ".join(query_terms), "score": score, "priority": 1,
            })


def _search_wiki(query_terms: list[str], results: list[dict]) -> None:
    from engine.knowledge.wiki_index import WikiIndex
    from engine.knowledge.wiki_retriever import WikiRetriever
    index = WikiIndex()
    if not index.load() or index.is_empty:
        return
    retriever = WikiRetriever(index)
    query_text = " ".join(query_terms)
    snippets = retriever.retrieve(
        query_text=query_text, task_type="ask", selected_skills=None, max_chars=5000, max_pages=10,
    )
    for s in snippets:
        raw_path = s.path
        path = f"docs/wiki/{raw_path}" if not raw_path.startswith("docs/") else raw_path
        results.append({
            "type": "wiki", "title": s.title, "path": path, "page_type": s.page_type,
            "reason": f"{s.page_type} match (score={s.score:.1f})",
            "keywords": ", ".join(s.tags[:5]), "score": s.score, "priority": 2, "summary": s.summary,
        })


def _search_analysis(query_terms: list[str], results: list[dict]) -> None:
    if not OUTPUTS_ANALYSIS_DIR.is_dir():
        return
    for d in OUTPUTS_ANALYSIS_DIR.iterdir():
        if not d.is_dir():
            continue
        yaml_path = d / "latest.yaml"
        if not yaml_path.is_file():
            continue
        try:
            with open(yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        searchable = json.dumps(data, ensure_ascii=False).lower()
        score = sum(1 for t in query_terms if t in searchable)
        if score > 0:
            stage = data.get("stage", {})
            results.append({
                "type": "analysis", "title": f"{d.name} ({stage.get('stage', '?')})",
                "path": str(yaml_path.relative_to(ROOT_DIR)).replace("\\", "/"),
                "reason": f"content match ({score} terms)",
                "keywords": stage.get("stage", ""), "score": score, "priority": 3,
            })


def _search_kb(query_terms: list[str], results: list[dict]) -> None:
    kb_dir = ROOT_DIR / "docs" / "kb"
    if not kb_dir.is_dir():
        return
    count = 0
    for f in kb_dir.rglob("*.md"):
        if count >= 200:
            break
        count += 1
        rel = str(f.relative_to(ROOT_DIR)).replace("\\", "/").lower()
        stem = f.stem.lower()
        if any(t in rel or t in stem for t in query_terms):
            results.append({
                "type": "kb", "title": f.stem,
                "path": str(f.relative_to(ROOT_DIR)).replace("\\", "/"),
                "reason": "filename/path match", "keywords": "", "score": 1, "priority": 4,
            })


def agent_material_search(conn: sqlite3.Connection, config: Config, query: str) -> str:
    results: list[dict] = []
    query_terms = query.lower().split()
    _search_skills(query_terms, results)
    _search_wiki(query_terms, results)
    _search_analysis(query_terms, results)
    _search_kb(query_terms, results)
    results.sort(key=lambda r: (r.get("priority", 99), -r.get("score", 0)))
    parts = [f'# Material Search: "{query}"\n']
    parts.append(f"## 结果 ({len(results)} 条)\n")
    for i, r in enumerate(results[:20], 1):
        parts.append(f"### {i}. [{r['type']}] {r['title']}")
        parts.append(f"- Path: `{r['path']}`")
        parts.append(f"- Reason: {r['reason']}")
        if r.get("keywords"):
            parts.append(f"- Keywords: {r['keywords']}")
        parts.append(f"- Show: `wiki_show(\"{r['path']}\")`")
        parts.append("")
    skill_hits = [r["path"] for r in results if r["type"] == "skill"][:5]
    wiki_hits = [r["path"] for r in results if r["type"] == "wiki"][:5]
    parts.append(_build_cross_refs(skill_hits=skill_hits, wiki_hits=wiki_hits))
    return "\n".join(parts)


def agent_material_show(path: str, *, max_chars: int = 50000) -> str:
    resolved = _validate_path(path)
    content = resolved.read_text(encoding="utf-8")
    total = len(content)
    parts = [f"# Material: {path}\n"]
    parts.append(f"- Size: {total} chars")
    if total > max_chars:
        content = content[:max_chars]
        parts.append(f"- Showing: first {max_chars} chars (truncated)")
    else:
        parts.append(f"- Showing: all {total} chars")
    parts.append("")
    parts.append("---\n")
    parts.append(content)
    if total > max_chars:
        remaining = total - max_chars
        parts.append(f"\n---\n(truncated at {max_chars} chars, {remaining} chars remaining)")
    return "\n".join(parts)
