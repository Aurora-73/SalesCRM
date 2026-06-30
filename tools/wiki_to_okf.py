"""Convert wiki/ to OKF format.

Changes:
1. Frontmatter: type→English, date→timestamp, add description
2. [[wikilinks]] → standard markdown links
3. Rewrite root index.md in OKF format
4. Generate subdirectory index.md files
"""
import os
import re
import sys
from collections import defaultdict

WIKI_ROOT = os.path.join(os.path.dirname(__file__), "..", "docs", "wiki")
WIKI_PAGES = os.path.join(WIKI_ROOT, "wiki")

TYPE_MAP = {
    "entity": "Concept",
    "topic": "Topic",
    "scenario": "Scenario",
    "source": "Source",
    "synthesis": "Synthesis",
}

# Directory name for each type
TYPE_DIR = {
    "Concept": "entities",
    "Topic": "topics",
    "Scenario": "scenarios",
    "Source": "sources",
    "Synthesis": "synthesis",
}


def build_name_map():
    """Build {page_name: relative_path} for all wiki pages."""
    name_map = {}
    for dirpath, dirs, files in os.walk(WIKI_PAGES):
        for f in files:
            if not f.endswith(".md"):
                continue
            name = f[:-3]
            rel = os.path.relpath(os.path.join(dirpath, f), WIKI_ROOT)
            name_map[name] = rel.replace(os.sep, "/")
    return name_map


def parse_frontmatter(content):
    """Parse YAML frontmatter, return (fm_dict, body, raw_fm_string)."""
    m = re.match(r"^(---\s*\n)(.*?\n)(---\s*\n)", content, re.DOTALL)
    if not m:
        return None, content, ""
    raw_fm = m.group(2)
    body = content[m.end():]
    fm = {}
    for line in raw_fm.strip().split("\n"):
        km = re.match(r"^(\w[\w_]*):\s*(.*)", line)
        if km:
            fm[km.group(1)] = km.group(2).strip()
    return fm, body, raw_fm


def build_frontmatter(fm, body, name):
    """Build new frontmatter string."""
    lines = ["---"]

    # type (required, map to English)
    old_type = fm.get("type", "entity")
    new_type = TYPE_MAP.get(old_type, old_type)
    lines.append(f"type: {new_type}")

    # title
    if "title" in fm:
        lines.append(f"title: {fm['title']}")

    # description (extract from first blockquote in body)
    desc_match = re.search(r"^>\s*(.+)", body, re.MULTILINE)
    if desc_match:
        desc = desc_match.group(1).strip()
        # Truncate if too long
        if len(desc) > 200:
            desc = desc[:197] + "..."
        lines.append(f"description: {desc}")

    # resource (optional)
    if "resource" in fm:
        lines.append(f"resource: {fm['resource']}")

    # tags
    if "tags" in fm:
        lines.append(f"tags: {fm['tags']}")

    # timestamp (convert from date)
    date = fm.get("date", "")
    if date:
        lines.append(f"timestamp: {date}T00:00:00Z")
    elif "timestamp" in fm:
        lines.append(f"timestamp: {fm['timestamp']}")

    # Preserve all extension fields
    skip_keys = {"type", "title", "tags", "date", "timestamp", "resource"}
    for k, v in fm.items():
        if k not in skip_keys:
            lines.append(f"{k}: {v}")

    lines.append("---")
    return "\n".join(lines) + "\n"


def replace_wikilinks(content, name_map):
    """Replace [[name]] and [[name|alias]] with standard markdown links."""
    def replacer(m):
        target = m.group(1)
        alias = m.group(2)
        if target in name_map:
            path = "/" + name_map[target]
            display = alias if alias else target
            return f"[{display}]({path})"
        # Keep original if target not found
        if alias:
            return f"[[{target}|{alias}]]"
        return f"[[{target}]]"

    # Match [[name|alias]] first, then [[name]]
    return re.sub(r"\[\[([^\]|]+?)(?:\|([^\]]+))?\]\]", replacer, content)


def convert_file(filepath, name_map, dry_run=False):
    """Convert a single wiki page to OKF. Returns (changed, details)."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    fm, body, raw_fm = parse_frontmatter(content)
    if fm is None:
        # No frontmatter — still replace wikilinks
        new_content = replace_wikilinks(content, name_map)
        if new_content != content:
            if not dry_run:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(new_content)
            return True, "links-only"
        return False, "no frontmatter"

    name = os.path.splitext(os.path.basename(filepath))[0]

    # 1. Build new frontmatter
    new_fm = build_frontmatter(fm, body, name)

    # 2. Replace wikilinks in body
    new_body = replace_wikilinks(body, name_map)

    # 3. Also replace wikilinks in frontmatter (sources field may have them)
    new_fm = replace_wikilinks(new_fm, name_map)

    new_content = new_fm + new_body

    if new_content == content:
        return False, "no changes"

    if not dry_run:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

    return True, "converted"


def generate_subdir_index(subdir, name_map):
    """Generate index.md for a subdirectory."""
    entries = []
    for f in sorted(os.listdir(subdir)):
        if not f.endswith(".md") or f == "index.md":
            continue
        filepath = os.path.join(subdir, f)
        with open(filepath, "r", encoding="utf-8") as fh:
            content = fh.read()
        fm, body, _ = parse_frontmatter(content)
        if fm is None:
            continue
        name = f[:-3]
        title = fm.get("title", name)
        desc_match = re.search(r"^>\s*(.+)", body, re.MULTILINE)
        desc = desc_match.group(1).strip() if desc_match else ""
        if len(desc) > 80:
            desc = desc[:77] + "..."
        entries.append((name, title, desc))

    if not entries:
        return None

    dir_name = os.path.basename(subdir)
    lines = [f"# {dir_name}\n"]
    for name, title, desc in entries:
        if desc:
            lines.append(f"* [{title}]({name}.md) - {desc}")
        else:
            lines.append(f"* [{title}]({name}.md)")

    return "\n".join(lines) + "\n"


def generate_root_index(name_map):
    """Generate root index.md in OKF format."""
    categories = defaultdict(list)

    for dirpath, dirs, files in os.walk(WIKI_PAGES):
        for f in files:
            if not f.endswith(".md") or f == "index.md":
                continue
            filepath = os.path.join(dirpath, f)
            with open(filepath, "r", encoding="utf-8") as fh:
                content = fh.read()
            fm, body, _ = parse_frontmatter(content)
            if fm is None:
                continue

            name = f[:-3]
            title = fm.get("title", name)
            old_type = fm.get("type", "entity")
            new_type = TYPE_MAP.get(old_type, old_type)
            rel = os.path.relpath(filepath, WIKI_ROOT).replace(os.sep, "/")

            desc_match = re.search(r"^>\s*(.+)", body, re.MULTILINE)
            desc = desc_match.group(1).strip() if desc_match else ""
            if len(desc) > 100:
                desc = desc[:97] + "..."

            categories[new_type].append((rel, title, desc))

    # Section headers
    section_names = {
        "Concept": "实体页（Concepts）",
        "Topic": "主题页（Topics）",
        "Scenario": "场景决策（Scenarios）",
        "Source": "素材摘要（Sources）",
        "Synthesis": "综合分析（Synthesis）",
    }

    lines = [
        "# Wiki 知识库索引\n",
        "> 销售知识库 | OKF v0.1\n",
    ]

    for type_key in ["Concept", "Topic", "Scenario", "Source", "Synthesis"]:
        items = categories.get(type_key, [])
        if not items:
            continue
        lines.append(f"# {section_names.get(type_key, type_key)}\n")
        for rel, title, desc in sorted(items, key=lambda x: x[1]):
            if desc:
                lines.append(f"* [{title}]({rel}) - {desc}")
            else:
                lines.append(f"* [{title}]({rel})")
        lines.append("")

    return "\n".join(lines) + "\n"


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    dry_run = "--dry-run" in sys.argv

    # Build name map
    name_map = build_name_map()
    print(f"Wiki 页面总数: {len(name_map)}")

    # Convert all wiki pages
    converted = 0
    skipped = 0
    errors = []

    for dirpath, dirs, files in os.walk(WIKI_PAGES):
        for f in files:
            if not f.endswith(".md"):
                continue
            filepath = os.path.join(dirpath, f)
            try:
                changed, detail = convert_file(filepath, name_map, dry_run)
                if changed:
                    converted += 1
                    print(f"  [转换] {os.path.relpath(filepath, WIKI_ROOT)}")
                else:
                    skipped += 1
            except Exception as e:
                errors.append((f, str(e)))
                print(f"  [错误] {f}: {e}")

    print(f"\n{'[DRY RUN] ' if dry_run else ''}页面转换: {converted} 改动, {skipped} 跳过, {len(errors)} 错误")

    # Generate subdirectory index.md files
    if not dry_run:
        subdirs_generated = 0
        for d in os.listdir(WIKI_PAGES):
            subdir = os.path.join(WIKI_PAGES, d)
            if not os.path.isdir(subdir):
                continue
            index_content = generate_subdir_index(subdir, name_map)
            if index_content:
                index_path = os.path.join(subdir, "index.md")
                with open(index_path, "w", encoding="utf-8") as f:
                    f.write(index_content)
                subdirs_generated += 1
                print(f"  [索引] wiki/{d}/index.md")

        # Generate root index.md
        root_index = generate_root_index(name_map)
        root_index_path = os.path.join(WIKI_ROOT, "index.md")
        with open(root_index_path, "w", encoding="utf-8") as f:
            f.write(root_index)
        print(f"  [索引] wiki/index.md")
        print(f"\n生成子目录索引: {subdirs_generated} 个")
    else:
        print("\n[DRY RUN] 跳过索引生成")

    if errors:
        print("\n错误列表:")
        for f, e in errors:
            print(f"  {f}: {e}")


if __name__ == "__main__":
    main()
