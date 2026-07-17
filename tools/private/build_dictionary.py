"""导出隐私字典库。

从 core.db 的 contacts 表和 config.yaml 的 my_name/my_wxid 导出
昵称、微信号、备注、别名到 data/private/dictionary.yaml。

用户可在 dictionary.yaml 的 custom 区手动新增条目（手机号、邮箱等），
重复运行本脚本不会覆盖 custom 区内容。

用法（从项目根目录）：
    python -X utf8 tools/private/build_dictionary.py
    python -X utf8 tools/private/build_dictionary.py --db path/to/core.db
    python -X utf8 tools/private/build_dictionary.py --config path/to/config.yaml
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import yaml

# 项目根目录：tools/private/ 的上上级
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
PRIVATE_DIR = DATA_DIR / "private"
DICT_PATH = PRIVATE_DIR / "dictionary.yaml"

# SalesCRM 的 core.db 在 data/raw/，config.yaml 在 data/system/（与 loveMentor 相同）
DEFAULT_DB_PATH = DATA_DIR / "raw" / "core.db"
DEFAULT_CONFIG_PATH = DATA_DIR / "system" / "config.yaml"
FACTS_SELF_DIR = DATA_DIR / "facts" / "self"


def load_config_identity(config_path: Path) -> dict:
    """从 config.yaml 读取 my_name 和 my_wxid。"""
    if not config_path.exists():
        print(f"[警告] 配置文件不存在: {config_path}", file=sys.stderr)
        return {"nickname": "", "wxid": "", "remark": ""}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return {
            "nickname": str(cfg.get("my_name", "") or ""),
            "wxid": str(cfg.get("my_wxid", "") or ""),
            "remark": "",
        }
    except Exception as e:
        print(f"[警告] 读取配置失败: {e}", file=sys.stderr)
        return {"nickname": "", "wxid": "", "remark": ""}


def load_contacts_from_db(db_path: Path) -> list[dict]:
    """从 core.db 的 contacts 表导出联系人信息。"""
    if not db_path.exists():
        print(f"[警告] 数据库不存在: {db_path}", file=sys.stderr)
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT nickname, remark, alias, display_name, id FROM contacts"
        ).fetchall()
        conn.close()
    except Exception as e:
        print(f"[警告] 读取数据库失败: {e}", file=sys.stderr)
        return []

    contacts = []
    for row in rows:
        # id 字段可能是 wxid 或内部 ID，统一作为 wxid
        contacts.append({
            "nickname": str(row["nickname"] or ""),
            "remark": str(row["remark"] or ""),
            "alias": str(row["alias"] or ""),
            "wxid": str(row["id"] or ""),
        })
    return contacts


def load_self_from_facts() -> list[str]:
    """从 data/facts/self/ 目录的文件名提取自我昵称。"""
    names = []
    if not FACTS_SELF_DIR.is_dir():
        return names
    for p in FACTS_SELF_DIR.glob("*.md"):
        # 文件名格式: 昵称__person_xxxx.md
        stem = p.stem
        if "__person_" in stem:
            name = stem.split("__person_")[0]
            if name:
                names.append(name)
        elif stem and not stem.startswith("_"):
            names.append(stem)
    return names


def preserve_custom_section(dict_path: Path) -> list:
    """读取已有 dictionary.yaml 的 custom 区，保留用户自定义内容。"""
    if not dict_path.exists():
        return []
    try:
        with open(dict_path, "r", encoding="utf-8") as f:
            old = yaml.safe_load(f) or {}
        custom = old.get("custom", [])
        if isinstance(custom, list):
            return custom
    except Exception:
        pass
    return []


def build_dictionary(db_path: Path, config_path: Path) -> dict:
    """构建字典数据结构。"""
    my_identity = load_config_identity(config_path)

    # 补充 facts/self 目录中的昵称
    self_names = load_self_from_facts()
    if self_names and not my_identity["nickname"]:
        my_identity["nickname"] = self_names[0]

    contacts = load_contacts_from_db(db_path)

    # 保留用户 custom 区
    custom = preserve_custom_section(DICT_PATH)

    return {
        "my_identity": my_identity,
        "contacts": contacts,
        "custom": custom,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def main():
    parser = argparse.ArgumentParser(description="导出隐私字典库")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH,
                        help=f"core.db 路径（默认: {DEFAULT_DB_PATH}）")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH,
                        help=f"config.yaml 路径（默认: {DEFAULT_CONFIG_PATH}）")
    parser.add_argument("--output", type=Path, default=DICT_PATH,
                        help=f"输出路径（默认: {DICT_PATH}）")
    args = parser.parse_args()

    # 确保输出目录存在
    args.output.parent.mkdir(parents=True, exist_ok=True)

    dictionary = build_dictionary(args.db, args.config)

    # 写入 YAML（allow_unicode=True 保留中文，sort_keys=False 保持顺序）
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("# 隐私字典库 — 自动生成 + 用户可扩展\n")
        f.write("# my_identity 和 contacts 每次运行自动刷新；custom 区由用户手动维护。\n")
        f.write("# custom 区可添加任意字符串（手机号、邮箱、地址等），扫描时会全部检查。\n\n")
        yaml.dump(dictionary, f, allow_unicode=True, sort_keys=False,
                  default_flow_style=False)

    # 统计
    contact_count = len(dictionary["contacts"])
    custom_count = len(dictionary["custom"])
    my_name = dictionary["my_identity"]["nickname"] or "(空)"
    print(f"字典库已生成: {args.output}")
    print(f"  自我昵称: {my_name}")
    print(f"  联系人数: {contact_count}")
    print(f"  自定义条目: {custom_count}")
    if custom_count == 0:
        print(f"\n  提示: 可在 {args.output} 的 custom 区手动添加手机号、邮箱等敏感信息。")


if __name__ == "__main__":
    main()
