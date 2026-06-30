"""Convert /wiki/ absolute links to relative paths for OKF conformance."""
import re
import os

WIKI_PAGES = os.path.join(os.path.dirname(__file__), "..", "docs", "wiki", "wiki")
LINK_RE = re.compile(r"\[([^\]]+)\]\((/wiki/[^)]+)\)")


def abs_to_rel(file_path, target):
    if not target.startswith("/wiki/"):
        return target
    bundle_rel = target[6:]  # strip /wiki/
    file_dir = os.path.dirname(file_path)
    target_abs = os.path.join(WIKI_PAGES, bundle_rel)
    return os.path.relpath(target_abs, file_dir).replace(os.sep, "/")


def main():
    fixed_files = 0
    fixed_links = 0

    for dirpath, dirs, files in os.walk(WIKI_PAGES):
        for f in files:
            if not f.endswith(".md"):
                continue
            filepath = os.path.join(dirpath, f)
            with open(filepath, "r", encoding="utf-8") as fh:
                content = fh.read()

            count = [0]

            def replacer(m, _fp=filepath, _c=count):
                display = m.group(1)
                old_target = m.group(2)
                new_target = abs_to_rel(_fp, old_target)
                if new_target != old_target:
                    _c[0] += 1
                    return f"[{display}]({new_target})"
                return m.group(0)

            new_content = LINK_RE.sub(replacer, content)

            if count[0] > 0:
                with open(filepath, "w", encoding="utf-8") as fh:
                    fh.write(new_content)
                fixed_files += 1
                fixed_links += count[0]

    print(f"修复文件: {fixed_files}")
    print(f"修复链接: {fixed_links}")


if __name__ == "__main__":
    main()
