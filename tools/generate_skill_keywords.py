#!/usr/bin/env python3
"""从 SKILL.md 文件中提取 Wiki 概念关键词，生成 skill-keywords.json。

用法:
    python tools/generate_skill_keywords.py              # 输出到 skills/skill-keywords.json
    python tools/generate_skill_keywords.py --dry-run    # 预览，不写文件

逻辑:
    1. 扫描 docs/wiki/wiki/ 下所有实体/主题/场景/综合分析页标题
    2. 扫描 skills/*/SKILL.md 和 skills/*/skill/references/*.md
    3. 匹配标题在 Skill 文本中出现的概念
    4. 生成 skill-keywords.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WIKI_ENTITIES = PROJECT_ROOT / "docs" / "wiki" / "wiki" / "entities"
WIKI_TOPICS = PROJECT_ROOT / "docs" / "wiki" / "wiki" / "topics"
WIKI_SCENARIOS = PROJECT_ROOT / "docs" / "wiki" / "wiki" / "scenarios"
WIKI_SYNTHESIS = PROJECT_ROOT / "docs" / "wiki" / "wiki" / "synthesis"
SKILLS_DIR = PROJECT_ROOT / "skills"
OUTPUT = PROJECT_ROOT / "skills" / "skill-keywords.json"

# 不参与匹配的过短/过泛标题
SKIP_TITLES = {
}


def collect_wiki_titles() -> dict[str, list[str]]:
    """收集所有 Wiki 页面标题，按类型分组。"""
    result: dict[str, list[str]] = {
        "entities": [],
        "topics": [],
        "scenarios": [],
        "synthesis": [],
    }
    for dir_path, key in [
        (WIKI_ENTITIES, "entities"),
        (WIKI_TOPICS, "topics"),
        (WIKI_SCENARIOS, "scenarios"),
        (WIKI_SYNTHESIS, "synthesis"),
    ]:
        if not dir_path.exists():
            continue
        for f in sorted(dir_path.glob("*.md")):
            title = f.stem
            result[key].append(title)
    return result


def scan_skill_text(skill_dir: Path) -> str:
    """读取 SKILL.md 和 references/ 下所有 md 文件，拼接为纯文本。"""
    parts: list[str] = []

    # SKILL.md
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        parts.append(skill_md.read_text(encoding="utf-8", errors="replace"))

    # 也检查 skill/ 子目录（qingsheng-skill 的结构）
    alt_skill_md = skill_dir / "skill" / "SKILL.md"
    if alt_skill_md.exists() and alt_skill_md != skill_md:
        parts.append(alt_skill_md.read_text(encoding="utf-8", errors="replace"))

    # references/
    for ref_dir in [
        skill_dir / "references",
        skill_dir / "skill" / "references",
    ]:
        if ref_dir.exists():
            for ref_file in sorted(ref_dir.glob("*.md")):
                try:
                    parts.append(ref_file.read_text(encoding="utf-8", errors="replace"))
                except Exception:
                    pass

    return "\n".join(parts)


def find_matching_titles(text: str, titles: list[str], min_length: int = 2) -> list[str]:
    """在文本中查找出现的 Wiki 标题。"""
    matches: list[str] = []
    text_lower = text.lower()
    for title in titles:
        if len(title) < min_length:
            continue
        if title in SKIP_TITLES:
            continue
        if title.lower() in text_lower:
            matches.append(title)
    return sorted(set(matches))


def extract_skill_name(skill_dir: Path) -> str:
    """从 SKILL.md frontmatter 提取 name，否则用目录名。"""
    skill_md = skill_dir / "SKILL.md"
    alt_md = skill_dir / "skill" / "SKILL.md"
    for md in [skill_md, alt_md]:
        if md.exists():
            try:
                content = md.read_text(encoding="utf-8", errors="replace")
                if content.startswith("---"):
                    end = content.find("---", 3)
                    if end != -1:
                        fm = content[3:end]
                        m = re.search(r"name:\s*(.+)", fm)
                        if m:
                            return m.group(1).strip().strip("\"'")
            except Exception:
                pass
    return skill_dir.name


def classify_skill_type(skill_dir: Path) -> str:
    """分类 Skill 类型：self-contained / reference-routed / framework。"""
    has_references = any([
        (skill_dir / "references").is_dir(),
        (skill_dir / "skill" / "references").is_dir(),
    ])
    if has_references:
        return "reference-routed"

    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        try:
            content = skill_md.read_text(encoding="utf-8", errors="replace")
            # 检查是否是框架型（定义分析层，不含具体技术）
            framework_indicators = ["分析框架", "四层", "阶段", "路线图", "framework"]
            if any(ind in content.lower() or ind in content for ind in framework_indicators):
                # 进一步检查：如果内容很长（>5000字），可能是自包含型
                if len(content) > 5000:
                    return "self-contained"
                return "framework"
        except Exception:
            pass
    return "self-contained"


def main():
    parser = argparse.ArgumentParser(description="生成 skill-keywords.json")
    parser.add_argument("--dry-run", action="store_true", help="预览，不写文件")
    args = parser.parse_args()

    # 1. 收集 Wiki 标题
    wiki_titles = collect_wiki_titles()
    all_titles = (
        wiki_titles["entities"]
        + wiki_titles["topics"]
        + wiki_titles["scenarios"]
        + wiki_titles["synthesis"]
    )
    print(f"Wiki 页面标题：{len(all_titles)} 个", file=sys.stderr)

    # 2. 扫描每个 Skill
    result: dict[str, dict] = {}
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        if skill_dir.name.startswith("_") or skill_dir.name.startswith("."):
            continue

        skill_name = extract_skill_name(skill_dir)
        skill_type = classify_skill_type(skill_dir)
        text = scan_skill_text(skill_dir)

        if not text.strip():
            continue

        # 匹配 Wiki 标题
        matched_entities = find_matching_titles(text, wiki_titles["entities"])
        matched_topics = find_matching_titles(text, wiki_titles["topics"])
        matched_scenarios = find_matching_titles(text, wiki_titles["scenarios"])
        matched_synthesis = find_matching_titles(text, wiki_titles["synthesis"])

        total = len(matched_entities) + len(matched_topics) + len(matched_scenarios)
        if total == 0:
            continue

        entry: dict = {
            "skill_type": skill_type,
            "wiki_concepts": matched_entities,
            "wiki_topics": matched_topics,
            "wiki_scenarios": matched_scenarios,
        }
        if matched_synthesis:
            entry["wiki_synthesis"] = matched_synthesis

        result[skill_name] = entry
        print(
            f"  {skill_name:<30s} [{skill_type:<20s}] "
            f"concepts={len(matched_entities):2d}  topics={len(matched_topics)}  "
            f"scenarios={len(matched_scenarios)}  synthesis={len(matched_synthesis)}",
            file=sys.stderr,
        )

    print(f"\n共匹配 {len(result)} 个 Skill", file=sys.stderr)

    output_json = json.dumps(result, ensure_ascii=False, indent=2)

    if args.dry_run:
        print(output_json)
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(output_json, encoding="utf-8")
        print(f"已写入: {OUTPUT}", file=sys.stderr)
        print(f"文件大小: {len(output_json.encode('utf-8'))} bytes", file=sys.stderr)


if __name__ == "__main__":
    main()
