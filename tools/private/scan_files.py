"""扫描项目文件排查隐私泄露。

读取 data/private/dictionary.yaml，遍历项目文件（排除 .git/data/ 等），
逐行检查是否包含字典中的隐私内容，输出到 data/private/scan_report.csv。

用法（从项目根目录）：
    python -X utf8 tools/private/scan_files.py
    python -X utf8 tools/private/scan_files.py --all          # 扫描所有文件（含未跟踪）
    python -X utf8 tools/private/scan_files.py --min-len 3    # 只查长度≥3的条目
"""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
PRIVATE_DIR = DATA_DIR / "private"
DICT_PATH = PRIVATE_DIR / "dictionary.yaml"
REPORT_PATH = PRIVATE_DIR / "scan_report.csv"

# 扫描时排除的目录
EXCLUDE_DIRS = {".git", "data", "__pycache__", "node_modules", ".pytest_cache",
                ".trae", ".codex", ".agents", ".claude", ".history", ".vscode",
                ".idea", "ml/models", "_reference", "backup", "plan", "docs"}

# 扫描时排除的文件扩展名（二进制/大文件）
EXCLUDE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
                ".mp4", ".mp3", ".wav", ".avi", ".mov", ".flv",
                ".zip", ".gz", ".tar", ".7z", ".rar",
                ".onnx", ".pt", ".pth", ".bin", ".pkl", ".npy",
                ".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite3",
                ".exe", ".dll", ".so", ".dylib", ".pyc", ".pyo",
                ".pdf", ".docx", ".xlsx", ".pptx",
                ".bundle"}

# 尝试读取文件的编码列表
ENCODINGS = ["utf-8", "gbk", "latin-1"]


def load_search_terms(dict_path: Path, min_len: int = 1) -> list[tuple[str, str]]:
    """从字典库加载搜索词条目。

    Returns:
        [(value, source), ...]  source 标注来源（my_identity/contacts/custom）
    """
    if not dict_path.exists():
        print(f"[错误] 字典库不存在: {dict_path}", file=sys.stderr)
        print(f"       请先运行: python -X utf8 tools/private/build_dictionary.py", file=sys.stderr)
        sys.exit(1)

    with open(dict_path, "r", encoding="utf-8") as f:
        d = yaml.safe_load(f) or {}

    terms: list[tuple[str, str]] = []

    # my_identity
    my = d.get("my_identity", {})
    if isinstance(my, dict):
        for field in ("nickname", "wxid", "remark"):
            v = str(my.get(field, "") or "").strip()
            if len(v) >= min_len:
                terms.append((v, f"my_identity.{field}"))

    # contacts
    contacts = d.get("contacts", [])
    if isinstance(contacts, list):
        for c in contacts:
            if not isinstance(c, dict):
                continue
            for field in ("nickname", "remark", "alias", "wxid"):
                v = str(c.get(field, "") or "").strip()
                if len(v) >= min_len:
                    terms.append((v, f"contacts.{field}"))

    # custom（用户自定义，可能是字符串或 {value: ...} 字典）
    custom = d.get("custom", [])
    if isinstance(custom, list):
        for item in custom:
            if isinstance(item, str):
                v = item.strip()
                if len(v) >= min_len:
                    terms.append((v, "custom"))
            elif isinstance(item, dict):
                v = str(item.get("value", "") or "").strip()
                if len(v) >= min_len:
                    terms.append((v, "custom"))

    # 去重（保留首次出现的来源标注）
    seen = {}
    for v, src in terms:
        if v not in seen:
            seen[v] = src
    return [(v, s) for v, s in seen.items()]


def build_regex(terms: list[tuple[str, str]]) -> re.Pattern:
    """构建合并正则表达式（用 alternation 一次匹配所有词条）。"""
    escaped = [re.escape(v) for v, _ in terms]
    # 按长度降序排列，优先匹配更长的（避免短词部分匹配长词）
    escaped.sort(key=len, reverse=True)
    pattern = "|".join(escaped)
    return re.compile(pattern)


def get_tracked_files() -> list[Path]:
    """获取 git 跟踪的文件列表。"""
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=str(ROOT_DIR),
            capture_output=True, text=True, encoding="utf-8",
        )
        if result.returncode == 0:
            files = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    p = ROOT_DIR / line
                    if p.is_file():
                        files.append(p)
            return files
    except Exception:
        pass
    return []


def get_all_files() -> list[Path]:
    """获取所有文件（排除敏感目录和二进制扩展名）。"""
    files = []
    for p in ROOT_DIR.rglob("*"):
        if not p.is_file():
            continue
        # 检查是否在排除目录中
        rel = p.relative_to(ROOT_DIR)
        parts = rel.parts
        if any(part in EXCLUDE_DIRS or str(Path(*parts[:i+1])) in EXCLUDE_DIRS
               for i, part in enumerate(parts)):
            continue
        # 检查扩展名
        if p.suffix.lower() in EXCLUDE_EXTS:
            continue
        files.append(p)
    return files


def read_file_lines(path: Path) -> list[str] | None:
    """尝试用多种编码读取文件，返回行列表。失败返回 None。"""
    for enc in ENCODINGS:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.readlines()
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception:
            return None
    return None


def scan_file(path: Path, regex: re.Pattern, terms_map: dict[str, str]) -> list[dict]:
    """扫描单个文件，返回匹配记录列表。"""
    lines = read_file_lines(path)
    if lines is None:
        return []

    results = []
    rel_path = path.relative_to(ROOT_DIR)
    for line_no, line in enumerate(lines, 1):
        matches = regex.findall(line)
        if not matches:
            continue
        for match in matches:
            match_str = match if isinstance(match, str) else str(match)
            source = terms_map.get(match_str, "unknown")
            results.append({
                "file": str(rel_path),
                "line": line_no,
                "match": match_str,
                "source": source,
                "context": line.rstrip()[:200],  # 截断长行
            })
    return results


def main():
    parser = argparse.ArgumentParser(description="扫描项目文件排查隐私泄露")
    parser.add_argument("--dict", type=Path, default=DICT_PATH,
                        help=f"字典库路径（默认: {DICT_PATH}）")
    parser.add_argument("--output", type=Path, default=REPORT_PATH,
                        help=f"输出报告路径（默认: {REPORT_PATH}）")
    parser.add_argument("--all", action="store_true",
                        help="扫描所有文件（含未跟踪），默认只扫描 git 跟踪文件")
    parser.add_argument("--min-len", type=int, default=2,
                        help="最小匹配长度（默认2，避免单字符误报）")
    args = parser.parse_args()

    # 加载搜索词
    terms = load_search_terms(args.dict, min_len=args.min_len)
    if not terms:
        print("字典库为空，无可搜索条目。请先运行 build_dictionary.py 并确认 custom 区。")
        return

    terms_map = {v: s for v, s in terms}
    regex = build_regex(terms)
    print(f"已加载 {len(terms)} 个搜索词条目")

    # 获取文件列表
    if args.all:
        files = get_all_files()
        print(f"扫描所有文件（含未跟踪）: {len(files)} 个")
    else:
        files = get_tracked_files()
        print(f"扫描 git 跟踪文件: {len(files)} 个")

    # 扫描
    all_results = []
    for i, path in enumerate(files, 1):
        if i % 50 == 0:
            print(f"  进度: {i}/{len(files)}", file=sys.stderr)
        results = scan_file(path, regex, terms_map)
        all_results.extend(results)

    # 输出 CSV
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "line", "match", "source", "context"])
        writer.writeheader()
        writer.writerows(all_results)

    # 统计
    print(f"\n扫描完成: {args.output}")
    print(f"  扫描文件: {len(files)}")
    print(f"  匹配记录: {len(all_results)}")
    if all_results:
        # 按文件汇总
        file_counts = {}
        for r in all_results:
            file_counts[r["file"]] = file_counts.get(r["file"], 0) + 1
        print(f"  涉及文件: {len(file_counts)}")
        print(f"\n  匹配最多的文件:")
        for path, count in sorted(file_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"    {count:4d}  {path}")


if __name__ == "__main__":
    main()
