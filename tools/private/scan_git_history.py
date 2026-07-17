"""扫描 git 历史提交排查隐私泄露。

读取 data/private/dictionary.yaml，遍历所有 git 提交的差异内容，
检查每行新增内容是否包含隐私，输出到 data/private/git_scan_report.csv。
按 (file, match) 去重，只记录首次引入隐私的提交。

用法（从项目根目录）：
    python -X utf8 tools/private/scan_git_history.py
    python -X utf8 tools/private/scan_git_history.py --max-commits 100
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
REPORT_PATH = PRIVATE_DIR / "git_scan_report.csv"


def load_search_terms(dict_path: Path, min_len: int = 2) -> list[tuple[str, str]]:
    """从字典库加载搜索词条目（与 scan_files.py 相同逻辑）。"""
    if not dict_path.exists():
        print(f"[错误] 字典库不存在: {dict_path}", file=sys.stderr)
        print(f"       请先运行: python -X utf8 tools/private/build_dictionary.py", file=sys.stderr)
        sys.exit(1)

    with open(dict_path, "r", encoding="utf-8") as f:
        d = yaml.safe_load(f) or {}

    terms: list[tuple[str, str]] = []

    my = d.get("my_identity", {})
    if isinstance(my, dict):
        for field in ("nickname", "wxid", "remark"):
            v = str(my.get(field, "") or "").strip()
            if len(v) >= min_len:
                terms.append((v, f"my_identity.{field}"))

    contacts = d.get("contacts", [])
    if isinstance(contacts, list):
        for c in contacts:
            if not isinstance(c, dict):
                continue
            for field in ("nickname", "remark", "alias", "wxid"):
                v = str(c.get(field, "") or "").strip()
                if len(v) >= min_len:
                    terms.append((v, f"contacts.{field}"))

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

    seen = {}
    for v, src in terms:
        if v not in seen:
            seen[v] = src
    return [(v, s) for v, s in seen.items()]


def build_regex(terms: list[tuple[str, str]]) -> re.Pattern:
    """构建合并正则表达式。"""
    escaped = sorted([re.escape(v) for v, _ in terms], key=len, reverse=True)
    return re.compile("|".join(escaped))


def parse_diff_filename(line: str) -> str:
    """从 '+++ b/path' 或 'diff --git a/path b/path' 提取文件路径。"""
    if line.startswith("diff --git "):
        # diff --git a/path b/path
        parts = line.split(" b/", 1)
        if len(parts) == 2:
            return parts[1].strip()
        # 回退：取最后一个 token
        return line.split()[-1].strip()
    if line.startswith("+++ "):
        # +++ b/path  或  +++ /dev/null
        path = line[4:].strip()
        if path == "/dev/null":
            return ""
        if path.startswith("b/"):
            path = path[2:]
        return path
    return ""


def parse_hunk_line_num(line: str) -> int:
    """从 '@@ -old,count +new,count @@' 提取新文件的起始行号。"""
    # @@ -1,3 +5,4 @@ context
    m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
    if m:
        return int(m.group(1))
    return 1


def scan_git_history(regex: re.Pattern, terms_map: dict[str, str],
                     max_commits: int = 0) -> list[dict]:
    """流式扫描 git log -p 输出。

    Returns:
        匹配记录列表，按 (file, match) 去重，只保留首次出现的提交。
    """
    cmd = ["git", "log", "--all", "-p", "--format=COMMIT:%H"]
    if max_commits > 0:
        cmd.insert(2, f"-{max_commits}")

    proc = subprocess.Popen(
        cmd, cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )

    results = []
    seen_keys = set()  # (file, match) 去重

    current_commit = ""
    current_file = ""
    new_line_num = 0
    commits_scanned = 0

    assert proc.stdout is not None
    for raw_line in proc.stdout:
        try:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
        except Exception:
            continue

        # 检测新提交
        if line.startswith("COMMIT:"):
            current_commit = line[7:]
            commits_scanned += 1
            if commits_scanned % 100 == 0:
                print(f"  扫描提交: {commits_scanned}", file=sys.stderr)
            continue

        # 检测文件变更
        if line.startswith("diff --git "):
            current_file = parse_diff_filename(line)
            continue
        if line.startswith("+++ "):
            fname = parse_diff_filename(line)
            if fname:
                current_file = fname
            continue

        # 检测 hunk 头
        if line.startswith("@@ "):
            new_line_num = parse_hunk_line_num(line)
            continue

        # 跳过 diff 头部和删除行
        if line.startswith("---") or line.startswith("index ") or line.startswith("Author:") \
                or line.startswith("Date:") or line.startswith("    "):
            continue

        # 新增行（+ 开头但不是 +++）
        if line.startswith("+") and not line.startswith("+++"):
            content = line[1:]  # 去掉 + 前缀
            matches = regex.findall(content)
            for match in matches:
                match_str = match if isinstance(match, str) else str(match)
                key = (current_file, match_str)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                source = terms_map.get(match_str, "unknown")
                results.append({
                    "commit": current_commit[:12],
                    "file": current_file,
                    "line": new_line_num,
                    "match": match_str,
                    "source": source,
                    "context": content[:200],
                })
            new_line_num += 1
        elif not line.startswith("-"):
            # 上下文行（不以 + 或 - 开头），行号递增
            new_line_num += 1

    proc.wait()
    return results


def main():
    parser = argparse.ArgumentParser(description="扫描 git 历史提交排查隐私泄露")
    parser.add_argument("--dict", type=Path, default=DICT_PATH,
                        help=f"字典库路径（默认: {DICT_PATH}）")
    parser.add_argument("--output", type=Path, default=REPORT_PATH,
                        help=f"输出报告路径（默认: {REPORT_PATH}）")
    parser.add_argument("--min-len", type=int, default=2,
                        help="最小匹配长度（默认2）")
    parser.add_argument("--max-commits", type=int, default=0,
                        help="最多扫描的提交数（0=全部）")
    args = parser.parse_args()

    # 加载搜索词
    terms = load_search_terms(args.dict, min_len=args.min_len)
    if not terms:
        print("字典库为空，无可搜索条目。请先运行 build_dictionary.py")
        return

    terms_map = {v: s for v, s in terms}
    regex = build_regex(terms)
    print(f"已加载 {len(terms)} 个搜索词条目")
    print("开始扫描 git 历史（可能需要几分钟）...")

    # 扫描
    results = scan_git_history(regex, terms_map, max_commits=args.max_commits)

    # 输出 CSV
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["commit", "file", "line", "match", "source", "context"])
        writer.writeheader()
        writer.writerows(results)

    # 统计
    print(f"\n扫描完成: {args.output}")
    print(f"  匹配记录: {len(results)}")
    if results:
        commit_counts = {}
        for r in results:
            commit_counts[r["commit"]] = commit_counts.get(r["commit"], 0) + 1
        print(f"  涉及提交: {len(commit_counts)}")
        print(f"\n  隐私最多的提交:")
        for commit, count in sorted(commit_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"    {count:4d}  {commit}")


if __name__ == "__main__":
    main()
