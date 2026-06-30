"""Wiki health check (lint) per .wiki-schema.md rules.

Checks:
1. Isolated pages (no inbound links from other pages)
2. Broken links (target page doesn't exist)
3. Missing cross-references (related pages not mutually linked)
4. Index consistency (index.md entries vs actual files)
5. OKF conformance (frontmatter has required type field)
"""
import os
import re
import sys
from collections import defaultdict

WIKI_ROOT = os.path.join(os.path.dirname(__file__), "..", "docs", "wiki")
WIKI_PAGES = os.path.join(WIKI_ROOT, "wiki")

LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+\.md)\)")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def scan_all():
    """Scan all wiki pages, return structured data."""
    pages = {}  # name -> {path, frontmatter, outbound_links, body}
    for dirpath, dirs, files in os.walk(WIKI_PAGES):
        for f in files:
            if not f.endswith(".md") or f == "index.md":
                continue
            filepath = os.path.join(dirpath, f)
            name = f[:-3]
            with open(filepath, "r", encoding="utf-8") as fh:
                content = fh.read()

            fm = {}
            m = FRONTMATTER_RE.match(content)
            if m:
                for line in m.group(1).split("\n"):
                    km = re.match(r"^(\w[\w_]*):\s*(.*)", line)
                    if km:
                        fm[km.group(1)] = km.group(2).strip()

            body = content[m.end():] if m else content

            # Extract outbound links
            outbound = set()
            for lm in LINK_RE.finditer(body):
                target_path = lm.group(2)
                # Normalize: /wiki/entities/X.md -> X
                target_name = os.path.splitext(os.path.basename(target_path))[0]
                outbound.add(target_name)

            rel = os.path.relpath(filepath, WIKI_ROOT).replace(os.sep, "/")
            pages[name] = {
                "path": rel,
                "fm": fm,
                "outbound": outbound,
                "body": body,
            }

    return pages


def check_okf_conformance(pages):
    """Check every concept page has required frontmatter."""
    issues = []
    for name, data in pages.items():
        fm = data["fm"]
        if "type" not in fm:
            issues.append(f"  {data['path']}: 缺少 type 字段")
        elif not fm["type"]:
            issues.append(f"  {data['path']}: type 字段为空")
    return issues


def check_broken_links(pages):
    """Find links to non-existent pages."""
    issues = []
    all_names = set(pages.keys())
    for name, data in pages.items():
        for target in data["outbound"]:
            if target not in all_names:
                issues.append(f"  {data['path']} -> [[{target}]]: 目标不存在")
    return issues


def check_isolated_pages(pages):
    """Find pages that no other page links to."""
    # Build inbound map
    inbound = defaultdict(set)
    for name, data in pages.items():
        for target in data["outbound"]:
            if target in set(pages.keys()):
                inbound[target].add(name)

    isolated = []
    for name, data in pages.items():
        if name not in inbound or not inbound[name]:
            isolated.append(f"  {data['path']}: 无入站链接")
    return isolated


def check_missing_crossrefs(pages):
    """Check if related pages have mutual links."""
    issues = []
    for name, data in pages.items():
        body = data["body"]
        # Check "相关页面" section
        section_match = re.search(r"## 相关页面\s*\n(.*?)(?=\n## |\Z)", body, re.DOTALL)
        if not section_match:
            continue
        section = section_match.group(1)
        referenced = set()
        for lm in LINK_RE.finditer(section):
            target_name = os.path.splitext(os.path.basename(lm.group(2)))[0]
            referenced.add(target_name)

        # Check if referenced pages link back
        for ref in referenced:
            if ref in pages:
                ref_data = pages[ref]
                # Check if ref_data links back to name
                ref_body = ref_data["body"]
                ref_section_match = re.search(r"## 相关页面\s*\n(.*?)(?=\n## |\Z)", ref_body, re.DOTALL)
                if ref_section_match:
                    ref_links = set()
                    for lm in LINK_RE.finditer(ref_section_match.group(1)):
                        ref_links.add(os.path.splitext(os.path.basename(lm.group(2)))[0])
                    if name not in ref_links:
                        issues.append(f"  {name} -> {ref}，但 {ref} 未回链")
    return issues


def check_index_consistency(pages):
    """Check index.md entries match actual files."""
    issues = []
    index_path = os.path.join(WIKI_ROOT, "index.md")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Extract links from index
        index_links = set()
        for lm in LINK_RE.finditer(content):
            target = lm.group(2)
            name = os.path.splitext(os.path.basename(target))[0]
            index_links.add(name)

        actual = set(pages.keys())
        missing_from_index = actual - index_links
        extra_in_index = index_links - actual

        for m in sorted(missing_from_index):
            issues.append(f"  index.md 缺少: {pages[m]['path']}")
        for e in sorted(extra_in_index):
            issues.append(f"  index.md 多余: {e}（文件不存在）")
    return issues


def check_frontmatter_quality(pages):
    """Check frontmatter quality (description, timestamp)."""
    no_desc = []
    no_ts = []
    for name, data in pages.items():
        fm = data["fm"]
        if "description" not in fm:
            no_desc.append(data["path"])
        if "timestamp" not in fm and "date" not in fm:
            no_ts.append(data["path"])
    return no_desc, no_ts


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    pages = scan_all()
    print(f"扫描完成: {len(pages)} 个页面\n")

    # 1. OKF conformance
    conformance = check_okf_conformance(pages)
    print(f"## OKF 规范检查")
    if conformance:
        print(f"  发现 {len(conformance)} 个问题:")
        for i in conformance:
            print(i)
    else:
        print("  全部通过")
    print()

    # 2. Broken links
    broken = check_broken_links(pages)
    print(f"## 断裂链接")
    if broken:
        print(f"  发现 {len(broken)} 个:")
        for i in broken[:20]:
            print(i)
        if len(broken) > 20:
            print(f"  ... 还有 {len(broken)-20} 个")
    else:
        print("  无断裂链接")
    print()

    # 3. Isolated pages
    isolated = check_isolated_pages(pages)
    print(f"## 孤立页面")
    if isolated:
        print(f"  发现 {len(isolated)} 个:")
        for i in isolated:
            print(i)
    else:
        print("  无孤立页面")
    print()

    # 4. Missing cross-refs
    crossrefs = check_missing_crossrefs(pages)
    print(f"## 缺少交叉引用")
    if crossrefs:
        print(f"  发现 {len(crossrefs)} 个:")
        for i in crossrefs[:20]:
            print(i)
        if len(crossrefs) > 20:
            print(f"  ... 还有 {len(crossrefs)-20} 个")
    else:
        print("  全部互链")
    print()

    # 5. Index consistency
    index_issues = check_index_consistency(pages)
    print(f"## Index 一致性")
    if index_issues:
        print(f"  发现 {len(index_issues)} 个:")
        for i in index_issues[:20]:
            print(i)
        if len(index_issues) > 20:
            print(f"  ... 还有 {len(index_issues)-20} 个")
    else:
        print("  index.md 与文件完全一致")
    print()

    # 6. Frontmatter quality
    no_desc, no_ts = check_frontmatter_quality(pages)
    print(f"## Frontmatter 质量")
    print(f"  缺少 description: {len(no_desc)} 个")
    if no_desc:
        for d in no_desc[:5]:
            print(f"    {d}")
    print(f"  缺少 timestamp/date: {len(no_ts)} 个")
    if no_ts:
        for t in no_ts[:5]:
            print(f"    {t}")
    print()

    # Summary
    total_issues = len(conformance) + len(broken) + len(isolated) + len(index_issues)
    print(f"## 总结")
    print(f"  严重问题（需修复）: {total_issues}")
    print(f"  警告（交叉引用/质量）: {len(crossrefs) + len(no_desc) + len(no_ts)}")


if __name__ == "__main__":
    main()
