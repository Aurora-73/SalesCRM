"""Final OKF fixes:
1. Convert all bundle-relative absolute links (/entities/xxx.md) to relative paths
2. Add frontmatter to subdirectory index.md files
"""
import os
import re
import sys

BUNDLE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs", "sales", "wiki"))

LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def abs_to_rel(current_file, target):
    """Convert bundle-relative absolute path to relative path."""
    if not target.startswith("/"):
        return target

    # Strip leading /
    target_bundle_rel = target.lstrip("/")

    current_dir = os.path.dirname(current_file)
    target_abs = os.path.normpath(os.path.join(BUNDLE_ROOT, target_bundle_rel))
    return os.path.relpath(target_abs, current_dir).replace(os.sep, "/")


def process_file(filepath):
    """Process a single file."""
    rel_path = os.path.relpath(filepath, BUNDLE_ROOT).replace(os.sep, "/")

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    count = [0]

    def replacer(m):
        display = m.group(1)
        target = m.group(2)

        if target.startswith("http") or target.startswith("mailto:") or target.startswith("#"):
            return m.group(0)

        if not target.endswith(".md"):
            return m.group(0)

        new_target = abs_to_rel(rel_path, target)
        if new_target != target:
            count[0] += 1
            return f"[{display}]({new_target})"

        return m.group(0)

    new_content = LINK_RE.sub(replacer, content)

    if count[0] > 0:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)
        return count[0]

    return 0


def add_index_frontmatter():
    """Add frontmatter to subdirectory index.md files."""
    subdirs = {
        "entities": {
            "title": "Entities",
            "description": "Sales concepts, techniques, and models.",
            "type": "Section",
            "tags": ["entities", "concepts"],
        },
        "scenarios": {
            "title": "Scenarios",
            "description": "Solutions for common sales situations and problems.",
            "type": "Section",
            "tags": ["scenarios", "playbooks"],
        },
    }

    for subdir, meta in subdirs.items():
        index_path = os.path.join(BUNDLE_ROOT, subdir, "index.md")
        if not os.path.exists(index_path):
            continue

        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check if already has frontmatter
        if content.startswith("---"):
            continue

        fm = [
            "---",
            f"type: {meta['type']}",
            f"title: {meta['title']}",
            f"description: {meta['description']}",
            f"tags: [{', '.join(meta['tags'])}]",
            "timestamp: 2026-07-01T00:00:00Z",
            "---",
            "",
        ]

        new_content = "\n".join(fm) + content

        with open(index_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        print(f"  [FM] {subdir}/index.md")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    # Step 1: Convert links to relative paths
    fixed_files = 0
    fixed_links = 0

    for dirpath, dirs, files in os.walk(BUNDLE_ROOT):
        for f in files:
            if not f.endswith(".md"):
                continue
            if f.startswith("_") or f.startswith("."):
                continue
            filepath = os.path.join(dirpath, f)
            rel = os.path.relpath(filepath, BUNDLE_ROOT).replace(os.sep, "/")

            count = process_file(filepath)
            if count > 0:
                fixed_files += 1
                fixed_links += count
                print(f"  [LINK] {rel}: {count} links")

    print(f"\nFixed files: {fixed_files}")
    print(f"Fixed links: {fixed_links}")

    # Step 2: Add frontmatter to subdirectory index files
    print("\nAdding frontmatter to subdirectory index files:")
    add_index_frontmatter()

    print("\nDone!")


if __name__ == "__main__":
    main()
