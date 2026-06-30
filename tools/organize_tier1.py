"""按课程前缀将 tier1-core 下每个人目录中的文件分组到子文件夹。

规则：
- 含 "：" 的文件名，取第一个 "：" 前的部分作为课程前缀
- 同一前缀有 ≥2 个文件 → 创建子文件夹并移入
- 独立文件不动
- README.md / SUMMARY.md 不动
"""

import os
import re
import shutil
import sys
from collections import defaultdict


BASE = os.path.join(os.path.dirname(__file__), "..", "docs", "kb", "tier1-core")
SKIP = {"README.md", "SUMMARY.md"}


def extract_prefix(name: str) -> str | None:
    """从文件名提取课程前缀。返回 None 表示不归组。"""
    stem = os.path.splitext(name)[0]

    # 模式1：含中文全角冒号 "："
    if "：" in stem:
        prefix = stem.split("：")[0].strip()
        # 去掉开头的序号前缀如 "57、"
        prefix = re.sub(r'^[0-9]+、\s*', '', prefix)
        if prefix and len(prefix) >= 2:
            return prefix

    return None


def process_person(person_dir: str):
    person_name = os.path.basename(person_dir)
    files = [f for f in os.listdir(person_dir)
             if os.path.isfile(os.path.join(person_dir, f)) and f not in SKIP]

    # 按前缀分组
    groups: dict[str, list[str]] = defaultdict(list)
    for f in files:
        prefix = extract_prefix(f)
        if prefix:
            groups[prefix].append(f)

    moved = 0
    for prefix, group_files in sorted(groups.items()):
        if len(group_files) < 2:
            continue

        sub_dir = os.path.join(person_dir, prefix)
        os.makedirs(sub_dir, exist_ok=True)

        for f in sorted(group_files):
            src = os.path.join(person_dir, f)
            dst = os.path.join(sub_dir, f)
            if not os.path.exists(dst):
                shutil.move(src, dst)
                moved += 1

        print(f"  [{person_name}] {prefix}/  ({len(group_files)} 文件)")

    return moved


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    total_moved = 0
    for person in sorted(os.listdir(BASE)):
        person_dir = os.path.join(BASE, person)
        if not os.path.isdir(person_dir):
            continue
        print(f"\n处理: {person}/")
        total_moved += process_person(person_dir)

    print(f"\n共移动 {total_moved} 个文件")


if __name__ == "__main__":
    main()
