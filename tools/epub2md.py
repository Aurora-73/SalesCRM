"""批量将 epub 转为 Markdown，转换后删除源文件。

epub 解压后取 OEBPS/Text/*.html 按顺序拼接，提取正文转为 md。
仅依赖标准库，无需额外安装。

用法:
    python epub2md.py <目录>        # 递归扫描并转换
    python epub2md.py <单文件.epub> # 转换单个文件
"""

import glob
import os
import re
import sys
import zipfile
from html.parser import HTMLParser


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

    def handle_data(self, data):
        if not self._skip:
            self.lines.append(data)

    def get_markdown(self) -> str:
        text = "".join(self.lines)
        # 合并多余空行（保留最多一个空行）
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip() + "\n"


def extract_html_from_epub(epub_path: str) -> str | None:
    """从 epub 中提取 OEBPS/Text/*.html 并转为 Markdown。"""
    try:
        with zipfile.ZipFile(epub_path) as z:
            # 找到所有 OEBPS/Text/ 下的 html 文件，按文件名排序
            html_files = sorted(
                [n for n in z.namelist()
                 if n.startswith("OEBPS/Text/") and n.endswith(".html")],
                key=lambda x: x
            )
            if not html_files:
                # 有些 epub 结构不同，尝试其他路径
                html_files = sorted(
                    [n for n in z.namelist()
                     if n.endswith(".html") and "Text" in n],
                    key=lambda x: x
                )
            if not html_files:
                return None

            parts: list[str] = []
            for html_file in html_files:
                with z.open(html_file) as f:
                    raw = f.read()
                    # 尝试 utf-8，失败则 gb18030
                    try:
                        html_content = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        html_content = raw.decode("gb18030", errors="replace")

                    parser = HTMLToMarkdown()
                    parser.feed(html_content)
                    md = parser.get_markdown()
                    if md.strip():
                        parts.append(md)

            return "\n\n---\n\n".join(parts)

    except zipfile.BadZipFile:
        return None


def convert_epub(epub_path: str) -> bool:
    """转换单个 epub 文件，成功返回 True。"""
    md_content = extract_html_from_epub(epub_path)
    if not md_content or len(md_content) < 50:
        return False

    md_path = os.path.splitext(epub_path)[0] + ".md"

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # 验证写入成功后删除 epub
    if os.path.getsize(md_path) > 0:
        os.remove(epub_path)
        return True
    else:
        os.remove(md_path)
        return False


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) < 2:
        print("用法: python epub2md.py <目录或epub文件>")
        sys.exit(1)

    target = sys.argv[1]

    if os.path.isfile(target) and target.endswith(".epub"):
        files = [target]
    elif os.path.isdir(target):
        files = sorted(glob.glob(os.path.join(target, "**", "*.epub"), recursive=True))
    else:
        print(f"路径不存在: {target}")
        sys.exit(1)

    if not files:
        print("没有找到 epub 文件")
        sys.exit(0)

    print(f"找到 {len(files)} 个 epub 文件\n")

    ok, fail = 0, 0
    for epub in files:
        rel = os.path.relpath(epub, target if os.path.isdir(target) else os.path.dirname(epub))
        print(f"[{'OK':>4}] {rel} ... ", end="", flush=True)
        try:
            if convert_epub(epub):
                md_path = os.path.splitext(epub)[0] + ".md"
                size_kb = os.path.getsize(md_path) // 1024
                print(f"OK ({size_kb} KB)")
                ok += 1
            else:
                print("FAIL (内容不足)")
                fail += 1
        except Exception as e:
            print(f"ERROR: {e}")
            fail += 1

    print(f"\n完成: {ok} 成功, {fail} 失败")


if __name__ == "__main__":
    main()
