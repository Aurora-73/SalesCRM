#!/usr/bin/env python3
"""从 wiki Markdown 页面生成 search-index.json。

用法:
    python tools/generate_wiki_index.py                # 输出到 docs/wiki/search-index.json
    python tools/generate_wiki_index.py --dry-run       # 预览，不写文件
    python tools/generate_wiki_index.py --include-sources  # 也索引 sources/ 页面

契约: docs/plan/knowledge-wiki/INTEGRATION_PLAN.md §4
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# ── 常量 ────────────────────────────────────────────────

WIKI_ROOT = Path(__file__).resolve().parent.parent / "docs" / "wiki"

INDEXABLE_DIRS = ["entities", "topics", "synthesis", "scenarios"]
OPTIONAL_DIR = "sources"


def detect_content_dir(wiki_root: Path) -> Path:
    """自动探测内容目录：优先双层 wiki/wiki/，否则单层 wiki/。"""
    double = wiki_root / "wiki"
    if (double / "entities").is_dir():
        return double
    if (wiki_root / "entities").is_dir():
        return wiki_root
    raise FileNotFoundError(
        f"找不到 entities/ 目录。已尝试: {double / 'entities'} 和 {wiki_root / 'entities'}"
    )


CONTENT_DIR = detect_content_dir(WIKI_ROOT)

# ── 规则映射 ────────────────────────────────────────────

# 关键词 -> scenarios
SCENARIO_RULES: list[tuple[list[str], list[str]]] = [
    # reply: 沟通/回复相关
    (["沟通", "回复", "开场白", "话题", "深入话题", "不回消息", "冷淡",
      "已读不回", "不理我", "微笑", "敷衍", "怎么回", "说什么", "接话"],
     ["reply"]),
    # meet: 会面/线下相关
    (["会面", "会议", "演示", "拜访", "面谈", "冷场", "尴尬", "收场",
      "见面", "约出来", "累了", "想回去", "没话说"],
     ["meet"]),
    # ask: 概念/理论/咨询
    (["概念", "理论", "框架", "频率", "金字塔", "心态", "焦虑",
      "怎么判断", "怎么回事", "是什么", "为什么", "有没有兴趣", "怎么看"],
     ["ask"]),
    # analyze: 分析/诊断/工具
    (["分析", "诊断", "评估", "分类", "信号", "趋势", "正常吗", "什么信号"],
     ["analyze"]),
]

# 关键词 -> stages
STAGE_RULES: list[tuple[list[str], list[str]]] = [
    (["线索", "获客", "名片", "首次", "初次", "认识"], ["线索"]),
    (["需求", "痛点", "价值", "方案", "产品", "优势"], ["需求"]),
    (["沟通", "跟进", "信任", "建立", "关系", "深入"], ["跟进"]),
    (["会面", "会议", "演示", "拜访", "面谈", "交流"], ["会面"]),
    (["报价", "合同", "谈判", "成交", "签约", "订单"], ["成交"]),
]

# tags -> related_skills
SKILL_MAP: dict[str, list[str]] = {
    "客户": ["customer-analysis"],
    "销售": ["sales-strategy"],
    "沟通": ["communication-skill"],
    "谈判": ["negotiation-skill"],
    "需求": ["requirement-analysis"],
    "跟进": ["follow-up-skill"],
    "会面": ["meeting-prep"],
}

# ── 工具函数 ────────────────────────────────────────────


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """解析 YAML frontmatter 和正文。返回 (meta, body)。"""
    if not text.startswith("---"):
        return {}, text
    end = text.find("---", 3)
    if end == -1:
        return {}, text
    fm_text = text[3:end].strip()
    body = text[end + 3:].strip()

    # 简单 YAML 解析（不依赖 PyYAML，避免引入额外依赖）
    meta: dict = {}
    current_key = None
    for line in fm_text.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        # key: value
        m = re.match(r"^(\w[\w_]*)\s*:\s*(.*)", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if val.startswith("[") and val.endswith("]"):
                # 解析列表 [a, b, c]
                val = [v.strip().strip("\"'") for v in val[1:-1].split(",") if v.strip()]
            elif val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            elif val.startswith("'") and val.endswith("'"):
                val = val[1:-1]
            meta[key] = val
            current_key = key
        elif line.startswith("  - ") and current_key and isinstance(meta.get(current_key), list):
            item = line[4:].strip().strip("\"'")
            meta[current_key].append(item)

    return meta, body


def extract_summary(body: str) -> str:
    """从正文中提取摘要：优先 blockquote，其次第一段。"""
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("> ") and len(line) > 4:
            return line[2:].strip()
        # 跳过空行和标题
        if line and not line.startswith("#") and not line.startswith(">"):
            return line[:120]
    return ""


def infer_page_type(path: Path) -> str:
    """从路径推断页面类型。"""
    parts = path.parts
    type_map = {
        "entities": "entity",
        "topics": "topic",
        "synthesis": "synthesis",
        "scenarios": "scenario",
        "sources": "source",
        "comparisons": "comparison",
    }
    for dirname, page_type in type_map.items():
        if dirname in parts:
            return page_type
    return "unknown"


def map_scenarios(tags: list[str], body: str) -> list[str]:
    """根据标签和正文推断适用场景。"""
    combined = " ".join(tags) + " " + body[:500]
    scenarios: list[str] = []
    for keywords, sc in SCENARIO_RULES:
        if any(kw in combined for kw in keywords):
            scenarios.extend(sc)
    return sorted(set(scenarios)) if scenarios else ["ask"]


def map_stages(tags: list[str], body: str) -> list[str]:
    """根据标签和正文推断适用阶段。"""
    combined = " ".join(tags) + " " + body[:500]
    stages: list[str] = []
    for keywords, st in STAGE_RULES:
        if any(kw in combined for kw in keywords):
            stages.extend(st)
    return sorted(set(stages)) if stages else []


def map_related_skills(tags: list[str], body: str) -> list[str]:
    """根据标签和正文推断关联 Skill。"""
    combined = " ".join(tags) + " " + body[:500]
    skills: list[str] = []
    for keyword, sk_list in SKILL_MAP.items():
        if keyword in combined:
            skills.extend(sk_list)
    return sorted(set(skills))


def map_source_tier(meta: dict, rel_path: str, body: str) -> list[str]:
    """从 sources 字段、正文内容或路径推断来源层级。"""
    tiers: list[str] = []
    sources = meta.get("sources", [])
    if isinstance(sources, str):
        sources = [sources]
    for s in sources:
        if not isinstance(s, str):
            continue
        s_lower = s.lower()
        if "tier0" in s_lower or "classic" in s_lower:
            tiers.append("tier0")
        if "tier1" in s_lower:
            tiers.append("tier1")
        if "tier2" in s_lower:
            tiers.append("tier2")

    # 从正文内容推断
    body_head = body[:1000]
    if not tiers:
        if any(kw in body_head for kw in ["SPIN", "MEDDIC", "Challenger",
                                           "sales", "销售", "客户", "商机"]):
            tiers.append("tier0")

    # 兜底
    if not tiers:
        tiers = ["tier0", "tier1"]

    return sorted(set(tiers))


def map_confidence(meta: dict, body: str) -> str:
    """推断置信度。"""
    if "confidence" in meta:
        return meta["confidence"]
    # 包含"综合""对比""分析"的页面可能是推断
    combined = body[:300]
    if any(kw in combined for kw in ["综合分析", "跨素材", "对比"]):
        return "INFERRED"
    return "EXTRACTED"


def make_page_id(rel_path: str) -> str:
    """生成稳定的页面 ID。"""
    p = Path(rel_path)
    type_map = {
        "entities": "entity",
        "topics": "topic",
        "synthesis": "synthesis",
        "scenarios": "scenario",
        "sources": "source",
        "comparisons": "comparison",
    }
    page_type = "unknown"
    for dirname, pt in type_map.items():
        if dirname in p.parts:
            page_type = pt
            break
    name = p.stem
    slug = re.sub(r"[^\w一-鿿]", "-", name).strip("-")
    return f"{page_type}-{slug}"


def extract_keywords(title: str, tags: list[str], body: str) -> list[str]:
    """提取搜索关键词。"""
    keywords: list[str] = []
    # 标题本身就是关键词
    keywords.append(title)
    # tags
    keywords.extend(tags)
    # 从 [[wikilinks]] 提取
    for m in re.findall(r"\[\[([^\]]+)\]\]", body[:2000]):
        keywords.append(m)
    # 去重
    return sorted(set(kw for kw in keywords if kw))


# ── 主流程 ──────────────────────────────────────────────


def scan_pages(include_sources: bool = False) -> list[dict]:
    """扫描所有 wiki 页面，生成索引条目列表。"""
    dirs_to_scan = list(INDEXABLE_DIRS)
    if include_sources:
        dirs_to_scan.append(OPTIONAL_DIR)

    pages: list[dict] = []
    now = datetime.now().strftime("%Y-%m-%d")

    for subdir in dirs_to_scan:
        dir_path = CONTENT_DIR / subdir
        if not dir_path.exists():
            continue
        for md_file in sorted(dir_path.glob("*.md")):
            # 相对路径基于 WIKI_ROOT，兼容双层和单层结构
            rel_path = str(md_file.relative_to(WIKI_ROOT)).replace("\\", "/")
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception as e:
                print(f"  [WARN] 读取失败: {rel_path} - {e}", file=sys.stderr)
                continue

            meta, body = parse_frontmatter(text)
            title = meta.get("title", md_file.stem)
            tags = meta.get("tags", [])
            if isinstance(tags, str):
                tags = [tags]

            summary = extract_summary(body)
            scenarios = meta.get("scenarios") or map_scenarios(tags, body)
            if isinstance(scenarios, str):
                scenarios = [scenarios]
            stages = meta.get("stages") or map_stages(tags, body)
            if isinstance(stages, str):
                stages = [stages]
            related_skills = map_related_skills(tags, body)
            source_tier = map_source_tier(meta, rel_path, body)
            confidence = map_confidence(meta, body)
            keywords = extract_keywords(title, tags, body)
            search_terms = meta.get("search_terms", [])
            if isinstance(search_terms, str):
                search_terms = [search_terms]
            page_type = infer_page_type(md_file)

            updated_at = meta.get("updated", meta.get("date", now))
            if isinstance(updated_at, list):
                updated_at = str(updated_at[0]) if updated_at else now

            page = {
                "id": make_page_id(rel_path),
                "title": title,
                "path": rel_path,
                "type": page_type,
                "summary": summary,
                "tags": tags,
                "keywords": keywords,
                "search_terms": search_terms,
                "scenarios": scenarios,
                "stages": stages,
                "related_skills": related_skills,
                "source_tier": source_tier,
                "confidence": confidence,
                "updated_at": str(updated_at),
            }
            pages.append(page)

    return pages


def generate_index(include_sources: bool = False) -> dict:
    """生成完整的 search-index.json 结构。"""
    pages = scan_pages(include_sources)
    return {
        "version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "root": "docs/wiki",
        "page_count": len(pages),
        "include_sources": include_sources,
        "pages": pages,
    }


def main():
    parser = argparse.ArgumentParser(description="从 wiki Markdown 页面生成 search-index.json")
    parser.add_argument("--dry-run", action="store_true", help="预览输出，不写文件")
    parser.add_argument("--include-sources", action="store_true", help="也索引 sources/ 页面")
    parser.add_argument("--output", type=str, default=str(WIKI_ROOT / "search-index.json"),
                        help="输出路径 (默认: docs/wiki/search-index.json)")
    args = parser.parse_args()

    print(f"扫描 Wiki 目录: {CONTENT_DIR}")
    index = generate_index(include_sources=args.include_sources)
    print(f"共索引 {index['page_count']} 个页面")

    # 统计
    type_counts: dict[str, int] = {}
    for p in index["pages"]:
        t = p["type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    for t, c in sorted(type_counts.items()):
        print(f"  {t}: {c}")

    output_json = json.dumps(index, ensure_ascii=False, indent=2)

    if args.dry_run:
        print("\n--- dry-run 输出预览 (前 2000 字符) ---")
        print(output_json[:2000])
        if len(output_json) > 2000:
            print(f"... (共 {len(output_json)} 字符)")
    else:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_json, encoding="utf-8")
        print(f"\n已写入: {output_path}")
        print(f"文件大小: {len(output_json.encode('utf-8'))} bytes")


if __name__ == "__main__":
    main()
