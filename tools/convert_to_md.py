"""统一将 docs/ 下非 MD 文件转为 Markdown (UTF-8)。

用法:
    python convert_to_md.py txt      # 转换所有 .txt → .md
    python convert_to_md.py doc      # 转换所有 .doc → .md
    python convert_to_md.py pdf      # 转换所有 .pdf → .md (小文件优先)
    python convert_to_md.py html     # 转换所有 .html → .md
    python convert_to_md.py clean    # 清理垃圾文件 (Thumbs.db 等)
    python convert_to_md.py filenames # 修复异常文件名
    python convert_to_md.py endings  # 规范化行尾为 LF
"""

import glob
import os
import re
import shutil
import sys
import tempfile
from html.parser import HTMLParser

DOCS_ROOT = os.path.join(os.path.dirname(__file__), "..", "docs")


# ─────────────────────────── HTML → Markdown ───────────────────────────

class HTMLToMarkdown(HTMLParser):
    """简易 HTML → Markdown 转换器。"""

    def __init__(self):
        super().__init__()
        self.lines: list[str] = []
        self._tag_stack: list[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        self._tag_stack.append(tag)
        if tag in ("script", "style"):
            self._skip = True
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            self.lines.append("\n" + "#" * level + " ")
        elif tag == "p":
            self.lines.append("\n")
        elif tag == "br":
            self.lines.append("\n")
        elif tag == "li":
            self.lines.append("\n- ")
        elif tag == "strong" or tag == "b":
            self.lines.append("**")
        elif tag == "em" or tag == "i":
            self.lines.append("*")
        elif tag == "a":
            href = dict(attrs).get("href", "")
            self.lines.append("[")
            self._tag_stack.append(("a", href))

    def handle_endtag(self, tag):
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()
        if tag in ("script", "style"):
            self._skip = False
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.lines.append("\n")
        elif tag == "p":
            self.lines.append("\n")
        elif tag == "li":
            self.lines.append("\n")
        elif tag == "strong" or tag == "b":
            self.lines.append("**")
        elif tag == "em" or tag == "i":
            self.lines.append("*")
        elif tag == "a":
            if self._tag_stack and isinstance(self._tag_stack[-1], tuple):
                _, href = self._tag_stack.pop()
                self.lines.append(f"]({href})")

    def handle_data(self, data):
        if not self._skip:
            self.lines.append(data)

    def get_markdown(self) -> str:
        text = "".join(self.lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip() + "\n"


# ─────────────────────────── TXT → MD ───────────────────────────

def convert_txt(filepath: str) -> bool:
    """读取 .txt 文件，转为 .md。处理编码检测。"""
    md_path = os.path.splitext(filepath)[0] + ".md"
    if os.path.exists(md_path):
        print(f"  SKIP (md already exists): {os.path.basename(md_path)}")
        return False

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            import chardet
            with open(filepath, "rb") as f:
                raw = f.read()
            detected = chardet.detect(raw)
            enc = detected.get("encoding", "utf-8") or "utf-8"
            content = raw.decode(enc, errors="replace")
        except Exception:
            with open(filepath, "rb") as f:
                raw = f.read()
            content = raw.decode("utf-8", errors="replace")

    if not content.strip():
        print(f"  SKIP (empty): {os.path.basename(filepath)}")
        return False

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)

    os.remove(filepath)
    size_kb = os.path.getsize(md_path) // 1024
    print(f"  OK ({size_kb} KB)")
    return True


# ─────────────────────────── DOC → MD ───────────────────────────

def convert_doc(filepath: str) -> bool:
    """用 pywin32 COM + python-docx 将 .doc 转为 .md。"""
    from docx import Document as DocxDocument

    md_path = os.path.splitext(filepath)[0] + ".md"
    if os.path.exists(md_path):
        print(f"  SKIP (md already exists): {os.path.basename(md_path)}")
        return False

    ext = os.path.splitext(filepath)[1].lower()
    tmp_docx = None

    try:
        if ext == ".doc":
            # Use Word COM to convert .doc → temp .docx
            import win32com.client
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            try:
                doc = word.Documents.Open(filepath)
                tmp_docx = os.path.join(
                    tempfile.mkdtemp(prefix="doc2md_"),
                    os.path.splitext(os.path.basename(filepath))[0] + ".docx",
                )
                doc.SaveAs2(tmp_docx, FileFormat=16)
                doc.Close()
            finally:
                word.Quit()
            target = tmp_docx
        else:
            target = filepath

        doc = DocxDocument(target)
        lines: list[str] = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                lines.append("")
                continue
            style_name = (para.style.name or "").lower() if para.style else ""
            if style_name.startswith("heading"):
                try:
                    level = int(style_name.replace("heading", "").strip())
                except ValueError:
                    level = 1
                level = min(max(level, 1), 6)
                lines.append(f"{'#' * level} {text}")
            elif style_name.startswith("list"):
                lines.append(f"- {text}")
            else:
                lines.append(text)

        content = "\n".join(lines).strip() + "\n"
        if not content.strip():
            print(f"  SKIP (empty): {os.path.basename(filepath)}")
            return False

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(content)

        os.remove(filepath)
        size_kb = os.path.getsize(md_path) // 1024
        print(f"  OK ({size_kb} KB)")
        return True

    except Exception as e:
        print(f"  FAIL: {e}")
        return False

    finally:
        if tmp_docx and os.path.exists(tmp_docx):
            os.remove(tmp_docx)
            tmp_dir = os.path.dirname(tmp_docx)
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)


# ─────────────────────────── PDF → MD ───────────────────────────

def convert_pdf(filepath: str) -> bool:
    """用 pymupdf4llm 将 PDF 转为 .md。"""
    import pymupdf4llm

    md_path = os.path.splitext(filepath)[0] + ".md"
    if os.path.exists(md_path):
        print(f"  SKIP (md already exists): {os.path.basename(md_path)}")
        return False

    try:
        md_text = pymupdf4llm.to_markdown(
            filepath, write_images=False, image_path=None, page_chunks=False
        )
        if not md_text or len(md_text.strip()) < 10:
            print(f"  SKIP (empty/too short)")
            return False

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_text)

        size_mb = os.path.getsize(md_path) / (1024 * 1024)
        print(f"  OK ({size_mb:.1f} MB)")
        return True

    except Exception as e:
        print(f"  FAIL: {e}")
        return False


# ─────────────────────────── HTML → MD ───────────────────────────

def convert_html(filepath: str) -> bool:
    """将 .html 文件转为 .md。"""
    md_path = os.path.splitext(filepath)[0] + ".md"
    if os.path.exists(md_path):
        print(f"  SKIP (md already exists): {os.path.basename(md_path)}")
        return False

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            html_content = f.read()
    except UnicodeDecodeError:
        with open(filepath, "rb") as f:
            raw = f.read()
        html_content = raw.decode("utf-8", errors="replace")

    parser = HTMLToMarkdown()
    parser.feed(html_content)
    md_content = parser.get_markdown()

    if not md_content or len(md_content.strip()) < 10:
        print(f"  SKIP (empty/too short)")
        return False

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    os.remove(filepath)
    size_kb = os.path.getsize(md_path) // 1024
    print(f"  OK ({size_kb} KB)")
    return True


# ─────────────────────────── 垃圾清理 ───────────────────────────

def clean_garbage():
    """删除 Thumbs.db 等垃圾文件。"""
    patterns = ["**/Thumbs.db", "**/.DS_Store", "**/desktop.ini"]
    removed = 0
    for pat in patterns:
        for f in glob.glob(os.path.join(DOCS_ROOT, pat), recursive=True):
            try:
                os.remove(f)
                print(f"  Deleted: {os.path.relpath(f, DOCS_ROOT)}")
                removed += 1
            except OSError as e:
                print(f"  FAIL: {f}: {e}")
    print(f"\n共删除 {removed} 个垃圾文件")


# ─────────────────────────── 文件名修复 ───────────────────────────

def fix_filenames():
    """修复异常文件名：无扩展名文件加 .md，截断后缀重命名。"""
    fixed = 0

    # Pattern 1: files ending in _note, _not, _no, _n, _ (note fragments without extension)
    note_suffix_pattern = re.compile(r"(.+)_(note|not|no|n)$")

    for root, dirs, files in os.walk(DOCS_ROOT):
        # Skip .git
        if ".git" in root.split(os.sep):
            continue
        for name in files:
            filepath = os.path.join(root, name)

            # Skip already .md files
            _, ext = os.path.splitext(name)
            if ext.lower() in (".md", ".gitkeep", ".gitignore", ".py", ".css", ".log", ".png", ".jpg", ".jpeg"):
                continue

            new_name = None

            # Files with no extension at all (no dot in filename)
            if "." not in name:
                # Check if it's a note fragment
                m = note_suffix_pattern.match(name)
                if m:
                    new_name = m.group(1) + "_note.md"
                else:
                    new_name = name + ".md"

            # Files with truncated note suffix as extension
            elif ext.lower() in ("_note", "_not", "_no", "_n", "_"):
                base = os.path.splitext(name)[0]
                new_name = base + ext + ".md"

            # Files with "下载" as extension (incomplete downloads)
            elif ext == ".下载":
                base = os.path.splitext(name)[0]
                new_name = base + ".下载"  # keep as-is, these are not content

            # .TXT → .txt (normalize case, will be converted by txt handler)
            # .m files that are actually _note.m fragments
            elif ext.lower() == ".m":
                new_name = name + ".md"  # e.g. "_note.m" → "_note.m.md"
                # Actually, better to just treat them as text
                base = os.path.splitext(name)[0]
                new_name = base + "_note.md"

            if new_name and new_name != name:
                new_path = os.path.join(root, new_name)
                if not os.path.exists(new_path):
                    try:
                        os.rename(filepath, new_path)
                        rel = os.path.relpath(filepath, DOCS_ROOT)
                        print(f"  {rel}  →  {new_name}")
                        fixed += 1
                    except OSError as e:
                        print(f"  FAIL: {filepath}: {e}")

    print(f"\n共修复 {fixed} 个文件名")


# ─────────────────────────── 行尾规范化 ───────────────────────────

def fix_line_endings():
    """将所有 .md/.txt 文件的行尾统一为 LF。"""
    fixed = 0
    for root, dirs, files in os.walk(DOCS_ROOT):
        if ".git" in root.split(os.sep):
            continue
        for name in files:
            if not name.endswith((".md", ".txt", ".TXT")):
                continue
            filepath = os.path.join(root, name)
            try:
                with open(filepath, "rb") as f:
                    raw = f.read()

                # Check if has mixed endings or CRLF
                has_crlf = b"\r\n" in raw
                has_cr = b"\r" in raw.replace(b"\r\n", b"")
                has_bom = raw[:3] == b"\xef\xbb\xbf"

                if not has_crlf and not has_cr and not has_bom:
                    continue

                # Normalize: remove BOM, convert CRLF→LF, remove stray CR
                text = raw
                if has_bom:
                    text = text[3:]
                text = text.replace(b"\r\n", b"\n").replace(b"\r", b"\n")

                with open(filepath, "wb") as f:
                    f.write(text)
                fixed += 1

            except OSError:
                pass

    print(f"规范化 {fixed} 个文件的行尾")


# ─────────────────────────── 主入口 ───────────────────────────

def find_files(extensions: list[str], max_size_mb: float = float("inf")) -> list[str]:
    """在 docs/ 下查找指定扩展名的文件，按大小排序。"""
    files = []
    for root, dirs, names in os.walk(DOCS_ROOT):
        if ".git" in root.split(os.sep):
            continue
        for name in names:
            _, ext = os.path.splitext(name)
            if ext.lower() in extensions:
                filepath = os.path.join(root, name)
                size = os.path.getsize(filepath)
                if size <= max_size_mb * 1024 * 1024:
                    files.append((size, filepath))
    files.sort()
    return [f for _, f in files]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    action = sys.argv[1].lower()

    if action == "clean":
        clean_garbage()

    elif action == "txt":
        files = find_files([".txt", ".TXT"])
        print(f"找到 {len(files)} 个 TXT 文件\n")
        ok = 0
        for f in files:
            rel = os.path.relpath(f, DOCS_ROOT)
            print(f"  [{rel}]")
            if convert_txt(f):
                ok += 1
        print(f"\n完成: {ok}/{len(files)} 成功")

    elif action == "doc":
        files = find_files([".doc"])
        print(f"找到 {len(files)} 个 DOC 文件\n")
        ok = 0
        for f in files:
            rel = os.path.relpath(f, DOCS_ROOT)
            print(f"  [{rel}]")
            if convert_doc(f):
                ok += 1
        print(f"\n完成: {ok}/{len(files)} 成功")

    elif action == "pdf":
        files = find_files([".pdf"])
        print(f"找到 {len(files)} 个 PDF 文件\n")
        ok = 0
        fail = 0
        for f in files:
            rel = os.path.relpath(f, DOCS_ROOT)
            size_mb = os.path.getsize(f) / (1024 * 1024)
            print(f"  [{rel}] ({size_mb:.1f} MB)")
            if convert_pdf(f):
                ok += 1
            else:
                fail += 1
        print(f"\n完成: {ok} 成功, {fail} 失败")

    elif action == "html":
        files = find_files([".html", ".htm"])
        # Skip blueprint reload files (web assets, not content)
        files = [f for f in files if "Blueprint Reloaded" not in f]
        print(f"找到 {len(files)} 个 HTML 文件\n")
        ok = 0
        for f in files:
            rel = os.path.relpath(f, DOCS_ROOT)
            print(f"  [{rel}]")
            if convert_html(f):
                ok += 1
        print(f"\n完成: {ok}/{len(files)} 成功")

    elif action == "filenames":
        fix_filenames()

    elif action == "endings":
        fix_line_endings()

    else:
        print(f"未知操作: {action}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
