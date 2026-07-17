"""篡改 git 历史，从所有提交中去除隐私内容。

⚠️ 高风险操作：会重写所有提交哈希，需要 git push --force 同步远程。

读取 data/private/dictionary.yaml，将所有隐私词条替换为 [REDACTED]，
优先使用 git filter-repo（如已安装），回退到 git filter-branch。

安全措施：
  - 默认 dry-run 模式，只展示将替换的内容
  - 执行前自动备份 .git 到 .git.backup-{timestamp}
  - 需显式 --force 才真正执行
  - 执行后提示 push --force 的风险

用法（从项目根目录）：
    python -X utf8 tools/private/rewrite_git_history.py --dry-run    # 预览
    python -X utf8 tools/private/rewrite_git_history.py --force      # 执行
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
PRIVATE_DIR = DATA_DIR / "private"
DICT_PATH = PRIVATE_DIR / "dictionary.yaml"

REPLACEMENT_TEXT = "[REDACTED]"

# 排除列表：这些词虽然是字典库中的 nickname，但替换会破坏代码
# （纯数字批次号、常见短词、代码常量、微信内置账号等）
EXCLUDE_TERMS = {
    "001", "414", "ooo",  # 纯数字/字母短词（批次号、sample_id）
    "Blink", "SEVEN",  # 代码常量（BlinkMacSystemFont, 7-Zip）
    "weixin",  # 路径（D:/Weixin）
    "filehelper", "exmail_tool", "shhtinns",  # 微信内置账号
    "微信支付", "微信运动",  # 微信内置账号
    "[REDACTED]", "[REDACTED]", "[REDACTED]", "[REDACTED]",  # 聊天内容短语
    "[REDACTED]", "[REDACTED]", "[REDACTED]",  # annotations 中的非字典联系人
    "大众点评",  # 公众号名（聊天中出现）
}


def load_search_terms(dict_path: Path, min_len: int = 2) -> list[str]:
    """从字典库加载所有隐私词条（只返回字符串列表）。"""
    if not dict_path.exists():
        print(f"[错误] 字典库不存在: {dict_path}", file=sys.stderr)
        sys.exit(1)

    with open(dict_path, "r", encoding="utf-8") as f:
        d = yaml.safe_load(f) or {}

    terms: list[str] = []

    my = d.get("my_identity", {})
    if isinstance(my, dict):
        for field in ("nickname", "wxid", "remark"):
            v = str(my.get(field, "") or "").strip()
            if len(v) >= min_len:
                terms.append(v)

    contacts = d.get("contacts", [])
    if isinstance(contacts, list):
        for c in contacts:
            if not isinstance(c, dict):
                continue
            for field in ("nickname", "remark", "alias", "wxid"):
                v = str(c.get(field, "") or "").strip()
                if len(v) >= min_len:
                    terms.append(v)

    custom = d.get("custom", [])
    if isinstance(custom, list):
        for item in custom:
            if isinstance(item, str):
                v = item.strip()
                if len(v) >= min_len:
                    terms.append(v)
            elif isinstance(item, dict):
                v = str(item.get("value", "") or "").strip()
                if len(v) >= min_len:
                    terms.append(v)

    # 去重，排除已知误报词，按长度降序（先替换长词避免部分匹配）
    unique = sorted(set(terms) - EXCLUDE_TERMS, key=len, reverse=True)
    return unique


def check_filter_repo() -> bool:
    """检查 git filter-repo 是否可用。"""
    try:
        result = subprocess.run(
            ["git", "filter-repo", "--version"],
            capture_output=True, timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def backup_git() -> Path:
    """备份 .git 目录。"""
    git_dir = ROOT_DIR / ".git"
    if not git_dir.exists():
        print("[错误] .git 目录不存在，不是 git 仓库", file=sys.stderr)
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = ROOT_DIR / f".git.backup-{timestamp}"
    print(f"备份 .git → {backup_path} ...", file=sys.stderr)
    shutil.copytree(git_dir, backup_path)
    print(f"备份完成: {backup_path}", file=sys.stderr)
    return backup_path


def write_replace_rules(terms: list[str], rules_path: Path) -> None:
    """生成 git filter-repo --replace-text 格式的替换规则文件。

    格式：每行一个规则，literal_string==>replacement
    """
    with open(rules_path, "w", encoding="utf-8") as f:
        f.write(f"# 自动生成的替换规则 {datetime.now()}\n")
        f.write(f"# 共 {len(terms)} 条\n\n")
        for term in terms:
            # git filter-repo 的 literal 匹配，不使用 regex:
            f.write(f"{term}==>{REPLACEMENT_TEXT}\n")


def run_filter_repo(rules_path: Path, dry_run: bool) -> int:
    """使用 git filter-repo 替换历史。"""
    cmd = [
        "git", "filter-repo",
        "--replace-text", str(rules_path),
        "--force",
    ]
    if dry_run:
        # git filter-repo 没有 --dry-run，但可以用 --dry-run 分析
        cmd.insert(2, "--dry-run")

    print(f"执行: {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(cmd, cwd=str(ROOT_DIR))
    return result.returncode


def run_filter_branch(terms: list[str], dry_run: bool) -> int:
    """使用 git filter-branch 回退方案。

    通过 --tree-filter 在每个提交的文件树中执行替换。
    较慢，但无需额外安装。
    """
    # 生成替换脚本
    import json
    script_path = PRIVATE_DIR / "_replace_terms.py"
    script_content = f'''#!/usr/bin/env python3
"""自动生成的隐私替换脚本（由 rewrite_git_history.py 生成）。"""
import os
import sys

TERMS = {json.dumps(terms, ensure_ascii=False)}
REPLACEMENT = "{REPLACEMENT_TEXT}"

def replace_in_file(path):
    """替换文件中的隐私内容。"""
    try:
        for enc in ("utf-8", "gbk", "latin-1"):
            try:
                with open(path, "r", encoding=enc) as f:
                    content = f.read()
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        else:
            return
    except Exception:
        return

    original = content
    for term in TERMS:
        content = content.replace(term, REPLACEMENT)
    if content != original:
        with open(path, "w", encoding=enc) as f:
            f.write(content)

for root, dirs, files in os.walk("."):
    # 跳过 .git
    dirs[:] = [d for d in dirs if d != ".git"]
    for fname in files:
        replace_in_file(os.path.join(root, fname))
'''
    script_path.write_text(script_content, encoding="utf-8")

    if dry_run:
        print("[dry-run] 将使用 git filter-branch --tree-filter 执行替换", file=sys.stderr)
        print(f"[dry-run] 替换脚本: {script_path}", file=sys.stderr)
        print(f"[dry-run] 替换词条: {len(terms)} 条", file=sys.stderr)
        for t in terms[:20]:
            print(f"  {t} → {REPLACEMENT_TEXT}", file=sys.stderr)
        if len(terms) > 20:
            print(f"  ... 还有 {len(terms) - 20} 条", file=sys.stderr)
        return 0

    cmd = [
        "git", "filter-branch", "--force",
        "--tree-filter", f'python -X utf8 "{script_path}"',
        "--prune-empty",
        "--", "--all",
    ]
    env = dict(os.environ)
    env["FILTER_BRANCH_SQUELCH_WARNING"] = "1"
    print(f"执行: git filter-branch --tree-filter ...", file=sys.stderr)
    print("（可能需要较长时间，取决于提交数量）", file=sys.stderr)
    result = subprocess.run(cmd, cwd=str(ROOT_DIR), env=env)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description="⚠️ 篡改 git 历史去除隐私（高风险操作）"
    )
    parser.add_argument("--dict", type=Path, default=DICT_PATH,
                        help=f"字典库路径（默认: {DICT_PATH}）")
    parser.add_argument("--min-len", type=int, default=2,
                        help="最小匹配长度（默认2）")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="预览模式（默认）：只展示替换内容，不修改历史")
    mode.add_argument("--force", action="store_true",
                      help="⚠️ 真正执行历史重写（需先备份）")
    args = parser.parse_args()

    # 加载词条
    terms = load_search_terms(args.dict, min_len=args.min_len)
    if not terms:
        print("字典库为空，无可替换条目。")
        return

    print(f"已加载 {len(terms)} 个隐私词条:")
    for t in terms[:20]:
        print(f"  {t} → {REPLACEMENT_TEXT}")
    if len(terms) > 20:
        print(f"  ... 还有 {len(terms) - 20} 条")
    print()

    actually_run = args.force and not args.dry_run

    if actually_run:
        print("⚠️⚠️⚠️ 警告 ⚠️⚠️⚠️", file=sys.stderr)
        print("即将重写所有 git 提交历史，此操作不可逆！", file=sys.stderr)
        print("所有提交哈希将改变，需要 git push --force 同步远程。", file=sys.stderr)
        print(file=sys.stderr)

        # 备份
        backup_path = backup_git()
        print(f"\n备份已创建: {backup_path}", file=sys.stderr)
        print(f"如需回滚: rm -rf .git && mv {backup_path} .git", file=sys.stderr)
        print(file=sys.stderr)

    # 选择方案
    use_filter_repo = check_filter_repo()
    if use_filter_repo:
        print("使用 git filter-repo（推荐方案）", file=sys.stderr)
        rules_path = PRIVATE_DIR / "_replace_rules.txt"
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        write_replace_rules(terms, rules_path)
        ret = run_filter_repo(rules_path, dry_run=not actually_run)
    else:
        print("git filter-repo 不可用，回退到 git filter-branch", file=sys.stderr)
        print("提示: 安装 git filter-repo 可获得更好性能: pip install git-filter-repo", file=sys.stderr)
        ret = run_filter_branch(terms, dry_run=not actually_run)

    if ret == 0:
        if actually_run:
            print("\n✅ 历史重写完成", file=sys.stderr)
            print("后续步骤:", file=sys.stderr)
            print("  1. 检查结果: git log --oneline", file=sys.stderr)
            print("  2. 推送到远程: git push --force --all", file=sys.stderr)
            print("  3. 推送标签: git push --force --tags", file=sys.stderr)
            print("  4. 通知协作者重新 clone 仓库", file=sys.stderr)
            print("  5. 确认无误后删除备份: rm -rf .git.backup-*", file=sys.stderr)
        else:
            print("\n[dry-run] 预览完成，未修改任何内容。", file=sys.stderr)
            print("确认无误后使用 --force 真正执行。", file=sys.stderr)
    else:
        print(f"\n❌ 执行失败（返回码 {ret}）", file=sys.stderr)
        if actually_run:
            print(f"可从备份恢复: rm -rf .git && mv {ROOT_DIR}/.git.backup-* .git", file=sys.stderr)

    sys.exit(ret)


if __name__ == "__main__":
    main()
