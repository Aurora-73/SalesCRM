"""Fix broken links and URL encoding issues in OKF wiki.

Fixes:
1. URL-encoded characters in filenames (e.g. %25 -> %)
2. Wrong filenames (e.g. 框架（Frame）.md -> 框架.md)
3. Convert all internal links to bundle-relative absolute paths (/entities/xxx.md)
"""
import os
import re
import sys
from urllib.parse import unquote

BUNDLE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs", "sales", "wiki"))

LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def get_all_files():
    """Get all .md files in bundle. Returns {bundle_relative_path: absolute_path}."""
    files = {}
    for dirpath, dirs, filenames in os.walk(BUNDLE_ROOT):
        for f in filenames:
            if not f.endswith(".md"):
                continue
            filepath = os.path.join(dirpath, f)
            rel = os.path.relpath(filepath, BUNDLE_ROOT).replace(os.sep, "/")
            files[rel] = filepath
    return files


def find_matching_file(bundle_rel, all_files):
    """Try to find a matching file, handling common mismatches."""
    # Direct match
    if bundle_rel in all_files:
        return bundle_rel

    # Try without （Frame）suffix
    base = os.path.basename(bundle_rel)
    dirname = os.path.dirname(bundle_rel)
    if "（Frame）" in base:
        new_base = base.replace("（Frame）", "")
        candidate = os.path.join(dirname, new_base).replace(os.sep, "/")
        if candidate in all_files:
            return candidate

    # Try unquoted version
    unquoted = unquote(bundle_rel)
    if unquoted != bundle_rel and unquoted in all_files:
        return unquoted

    return None


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    all_files = get_all_files()
    print(f"Total files: {len(all_files)}")

    fixed_files = 0
    fixed_links = 0
    broken_links = []

    for rel_path, filepath in sorted(all_files.items()):
        # Skip non-concept files (index.md is ok, it has links too)
        if rel_path.startswith("_") or rel_path.startswith("."):
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        count = [0]

        def replacer(m, _rp=rel_path, _fp=filepath, _c=count):
            display = m.group(1)
            target = m.group(2)

            # Skip external and anchor links
            if target.startswith("http") or target.startswith("mailto:") or target.startswith("#"):
                return m.group(0)

            # Only process .md links
            if not target.endswith(".md"):
                return m.group(0)

            # Unquote URL-encoded characters
            target_unquoted = unquote(target)

            # Compute current file's directory (bundle-relative)
            current_dir = os.path.dirname(_rp).replace(os.sep, "/")
            if current_dir == ".":
                current_dir = ""

            # Resolve target to bundle-relative path
            if target_unquoted.startswith("/"):
                # Already bundle-relative
                bundle_rel = target_unquoted.lstrip("/")
            else:
                # Relative path - resolve against current directory
                if current_dir:
                    combined = current_dir + "/" + target_unquoted
                else:
                    combined = target_unquoted
                # Normalize (handle .. and .)
                parts = []
                for part in combined.split("/"):
                    if part == "..":
                        if parts:
                            parts.pop()
                    elif part == ".":
                        pass
                    else:
                        parts.append(part)
                bundle_rel = "/".join(parts)

            # Find matching file
            match = find_matching_file(bundle_rel, all_files)
            if match is None:
                broken_links.append((_rp, target, bundle_rel))
                return m.group(0)

            new_target = "/" + match
            if new_target != target:
                _c[0] += 1
                return f"[{display}]({new_target})"

            return m.group(0)

        new_content = LINK_RE.sub(replacer, content)

        if count[0] > 0:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_content)
            fixed_files += 1
            fixed_links += count[0]
            print(f"  [FIX] {rel_path}: {count[0]} links")

    print(f"\nFixed files: {fixed_files}")
    print(f"Fixed links: {fixed_links}")

    if broken_links:
        print(f"\nRemaining broken links: {len(broken_links)}")
        for src, tgt, resolved in broken_links[:30]:
            print(f"  {src} -> {tgt} (resolved: {resolved})")


if __name__ == "__main__":
    main()
