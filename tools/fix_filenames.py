"""Fix filenames that exceed Windows 260-char limit or have no extension.

Uses \\?\ prefix for long paths on Windows.
"""
import os
import sys

DOCS_ROOT = os.path.join(os.path.dirname(__file__), "..", "docs")


def long_path(p):
    """Convert to Windows long path prefix if needed."""
    if sys.platform == "win32" and not p.startswith("\\\\?\\"):
        return "\\\\?\\" + os.path.abspath(p)
    return p


def fix_anomalous_filenames():
    """Fix files with no extension or truncated suffixes by adding .md."""
    fixed = 0
    skipped = 0

    root = long_path(DOCS_ROOT)

    for dirpath, dirs, files in os.walk(root):
        for name in files:
            _, ext = os.path.splitext(name)
            ext_lower = ext.lower()

            # Skip known extensions
            if ext_lower in (".md", ".gitkeep", ".gitignore", ".py", ".css",
                             ".log", ".png", ".jpg", ".jpeg", ".pdf", ".doc",
                             ".docx", ".txt", ".html", ".htm", ".pptx", ".ppt",
                             ".xlsx", ".chm", ".db", ".m"):
                continue

            # Skip .下载 files (incomplete downloads, not content)
            if ext == ".下载":
                continue

            new_name = None

            # Files with truncated note suffixes as "extension"
            if ext_lower in ("_note", "_not", "_no", "_n", "_"):
                new_name = name + ".md"

            # Files with no extension at all (no dot in filename)
            elif "." not in name:
                new_name = name + ".md"

            if new_name:
                src = os.path.join(dirpath, name)
                dst = os.path.join(dirpath, new_name)
                try:
                    if not os.path.exists(dst):
                        os.rename(src, dst)
                        print(f"  OK: ...{name[-80:]}.md")
                        fixed += 1
                    else:
                        skipped += 1
                except OSError as e:
                    print(f"  FAIL: ...{name[-60:]}: {e}")
                    skipped += 1

    print(f"\nFixed: {fixed}, Skipped/Failed: {skipped}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    fix_anomalous_filenames()
