"""扫描 docs/ 下所有 .txt/.md 文件，非 UTF-8 的转为 UTF-8。"""

import glob
import os
import sys
import chardet

TARGET = os.path.join(os.path.dirname(__file__), "..", "docs")


def detect_encoding(path: str) -> str:
    """读取文件原始字节，用 chardet 检测编码。"""
    with open(path, "rb") as f:
        raw = f.read()
    result = chardet.detect(raw)
    return result.get("encoding") or "unknown", raw


def is_valid_utf8(raw: bytes) -> bool:
    """尝试用 UTF-8 解码，能完整解码说明就是 UTF-8。"""
    try:
        raw.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def convert_to_utf8(path: str, raw: bytes, original_encoding: str) -> bool:
    """将文件内容从 original_encoding 转为 UTF-8 并覆盖写回。"""
    try:
        text = raw.decode(original_encoding, errors="replace")
    except (UnicodeDecodeError, LookupError):
        text = raw.decode("utf-8", errors="replace")

    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return True


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    patterns = [
        os.path.join(TARGET, "**", "*.txt"),
        os.path.join(TARGET, "**", "*.md"),
    ]

    files = []
    for pat in patterns:
        files.extend(glob.glob(pat, recursive=True))
    files = sorted(set(files))

    print(f"扫描 {len(files)} 个文件\n")

    utf8_ok, converted, failed = 0, 0, 0

    for i, path in enumerate(files, 1):
        name = os.path.relpath(path, TARGET)

        try:
            with open(path, "rb") as f:
                raw = f.read()
        except (FileNotFoundError, OSError):
            failed += 1
            continue

        if is_valid_utf8(raw):
            utf8_ok += 1
            continue

        # 不是 UTF-8，检测实际编码
        encoding, _ = detect_encoding(path)
        print(f"[{i}] {name}  {encoding} -> UTF-8 ... ", end="", flush=True)

        try:
            convert_to_utf8(path, raw, encoding)
            print("OK")
            converted += 1
        except Exception as e:
            print(f"FAIL: {e}")
            failed += 1

    print(f"\n结果: {utf8_ok} 已是UTF-8, {converted} 已转换, {failed} 失败")


if __name__ == "__main__":
    main()
