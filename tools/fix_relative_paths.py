"""Fix relative paths - convert bundle-relative absolute links to correct relative paths."""
import os
import re
import sys

BUNDLE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs", "wiki"))

LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def fix_links_in_file(filepath):
    """Fix all links in a file to be correct relative paths."""
    file_dir = os.path.dirname(filepath)

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    count = [0]

    def replacer(m):
        display = m.group(1)
        target = m.group(2)

        # Skip external and anchor links
        if target.startswith("http") or target.startswith("mailto:") or target.startswith("#"):
            return m.group(0)

        if not target.endswith(".md"):
            return m.group(0)

        # Check if it's a bundle-relative absolute path (starts with /)
        if target.startswith("/"):
            target_bundle_rel = target.lstrip("/")
            target_abs = os.path.normpath(os.path.join(BUNDLE_ROOT, target_bundle_rel))
        else:
            # Check if it's already a correct relative path
            # Try resolving it
            resolved = os.path.normpath(os.path.join(file_dir, target))
            if os.path.exists(resolved):
                return m.group(0)  # already correct
            # Otherwise, it might be a wrong relative path like ../docs/wiki/...
            # Try to extract the bundle-relative part
            # Look for entities/ or scenarios/ in the path
            for prefix in ["entities/", "scenarios/"]:
                idx = target.find(prefix)
                if idx >= 0:
                    target_bundle_rel = target[idx:]
                    target_abs = os.path.normpath(os.path.join(BUNDLE_ROOT, target_bundle_rel))
                    break
            else:
                return m.group(0)  # can't fix

        # Compute correct relative path
        new_target = os.path.relpath(target_abs, file_dir).replace(os.sep, "/")

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


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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

            count = fix_links_in_file(filepath)
            if count > 0:
                fixed_files += 1
                fixed_links += count
                print(f"  [FIX] {rel}: {count} links")

    print(f"\nFixed files: {fixed_files}")
    print(f"Fixed links: {fixed_links}")


if __name__ == "__main__":
    main()
