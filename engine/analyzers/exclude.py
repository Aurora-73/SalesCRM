"""联系人排除逻辑

基于微信标签的排除机制：
1. 硬排除：用户自己、非个人 wxid（系统号/企业号）
2. 标签排除：微信标签含"非攻略对象"或"放弃"的联系人
3. 类型排除：contacts.type = 'former_friend'（已删除好友）
4. 手动排除：contact_excludes 表
5. 关键词排除：config.yaml 中的自定义关键词

标签"置顶攻略对象"标记为优先分析对象。
"""
import json
import sqlite3
import time
from dataclasses import dataclass

# 硬排除 wxid 精确匹配
HARDCODED_WXIDS = {
    "filehelper",
    "exmail_tool",
    "shhtinns",
    "@opencustomerservicemsg",
}

# 硬排除 wxid 前缀
HARDCODED_PREFIXES = ("ww_", "qq")

# 硬排除 wxid 后缀
HARDCODED_SUFFIXES = ("@openim", "@qy_u")

# 排除标签
EXCLUDE_LABELS = {"非攻略对象", "放弃", "群友"}

# 优先标签
PRIORITY_LABEL = "置顶攻略对象"


@dataclass
class ExcludeInfo:
    wxid: str
    display_name: str
    reason: str


def parse_labels(raw: str | None) -> list[str]:
    """解析 labels JSON 字符串。"""
    if not raw:
        return []
    try:
        result = json.loads(raw)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def is_hard_excluded(wxid: str, my_wxid: str) -> str | None:
    """硬排除检查（系统号/企业号/自己）。返回排除原因，None 表示不排除。"""
    if wxid == my_wxid or wxid.startswith(my_wxid):
        return "用户自己"

    if wxid in HARDCODED_WXIDS:
        return "系统账号"

    for prefix in HARDCODED_PREFIXES:
        if wxid.startswith(prefix):
            return f"非个人账号 ({prefix}*)"

    for suffix in HARDCODED_SUFFIXES:
        if wxid.endswith(suffix):
            return f"非个人账号 (*{suffix})"

    return None


def get_manual_excludes(conn: sqlite3.Connection) -> dict[str, str]:
    """从 contact_excludes 表读取手动排除列表。返回 {wxid: reason}。"""
    try:
        rows = conn.execute(
            "SELECT wxid, reason FROM contact_excludes"
        ).fetchall()
        return {r["wxid"]: (r["reason"] or "手动排除") for r in rows}
    except sqlite3.OperationalError:
        return {}


def add_manual_exclude(conn: sqlite3.Connection, wxid: str, reason: str = "手动排除") -> None:
    """添加手动排除。"""
    now = int(time.time())
    conn.execute(
        """
        INSERT INTO contact_excludes (wxid, reason, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT(wxid) DO UPDATE SET reason = excluded.reason
        """,
        (wxid, reason, now),
    )
    conn.commit()


def remove_manual_exclude(conn: sqlite3.Connection, wxid: str) -> bool:
    """移除手动排除。返回是否成功。"""
    cursor = conn.execute("DELETE FROM contact_excludes WHERE wxid = ?", (wxid,))
    conn.commit()
    return cursor.rowcount > 0


def filter_contacts(
    contacts: list[dict],
    conn: sqlite3.Connection,
    my_wxid: str = "",
    name_keywords: list[str] | None = None,
) -> tuple[list[dict], list[ExcludeInfo]]:
    """过滤联系人，返回 (included, excluded)。

    Args:
        contacts: [{wxid, display_name, message_count, ...}, ...]
        conn: DB 连接
        my_wxid: 用户自己的 wxid
        name_keywords: 配置中的自定义排除关键词

    Returns:
        (included_contacts, excluded_info_list)
        included_contacts 中的每个 dict 可能包含额外的 top_target 字段。
    """
    manual_excludes = get_manual_excludes(conn)
    user_keywords = name_keywords or []

    # 预加载标签、remark、type
    contact_meta: dict[str, dict] = {}
    try:
        rows = conn.execute(
            "SELECT id, nickname, remark, labels, type FROM contacts"
        ).fetchall()
        for r in rows:
            contact_meta[r["id"]] = {
                "nickname": r["nickname"] or "",
                "remark": r["remark"] or "",
                "labels": parse_labels(r["labels"]),
                "type": r["type"] or "",
            }
    except sqlite3.OperationalError:
        pass

    included = []
    excluded = []

    for c in contacts:
        wxid = c["wxid"]
        display_name = c.get("display_name", "")
        meta = contact_meta.get(wxid, {})
        remark = meta.get("remark", "")
        nickname = meta.get("nickname", "")
        labels = meta.get("labels", [])

        # Layer 1: 硬排除（系统号/企业号/自己）
        reason = is_hard_excluded(wxid, my_wxid)
        if reason:
            excluded.append(ExcludeInfo(wxid, display_name, reason))
            continue

        # Layer 2: 标签排除
        matched_exclude_labels = [lb for lb in labels if lb in EXCLUDE_LABELS]
        if matched_exclude_labels:
            excluded.append(ExcludeInfo(
                wxid, display_name, f"标签: {', '.join(matched_exclude_labels)}"
            ))
            continue

        # Layer 3: 类型排除（已删除好友）
        if meta.get("type") == "former_friend":
            excluded.append(ExcludeInfo(wxid, display_name, "已删除好友"))
            continue

        # Layer 4: 手动排除
        if wxid in manual_excludes:
            excluded.append(ExcludeInfo(wxid, display_name, manual_excludes[wxid]))
            continue

        # Layer 5: 关键词排除
        skip = False
        for kw in user_keywords:
            if kw in display_name or kw in remark or kw in nickname:
                excluded.append(ExcludeInfo(wxid, display_name, f"关键词 '{kw}'"))
                skip = True
                break
        if skip:
            continue

        # 标记置顶对象
        if PRIORITY_LABEL in labels:
            c = dict(c)
            c["top_target"] = True
            c["labels"] = labels

        included.append(c)

    return included, excluded


def get_contact_labels(conn: sqlite3.Connection, wxid: str) -> list[str]:
    """获取单个联系人的标签列表。"""
    row = conn.execute(
        "SELECT labels FROM contacts WHERE id = ?", (wxid,)
    ).fetchone()
    if row:
        return parse_labels(row["labels"])
    return []


def search_contacts(conn: sqlite3.Connection, keyword: str) -> list[dict]:
    """按名字模糊搜索联系人（含标签信息）。"""
    like = f"%{keyword}%"
    rows = conn.execute(
        """
        SELECT c.id AS wxid,
               COALESCE(c.display_name, c.id) AS display_name,
               co.remark,
               co.nickname,
               co.labels
        FROM conversations c
        LEFT JOIN contacts co ON co.id = c.id
        WHERE c.type = 'private'
          AND (c.display_name LIKE ?
               OR co.remark LIKE ?
               OR co.nickname LIKE ?
               OR co.alias LIKE ?)
        LIMIT 20
        """,
        (like, like, like, like),
    ).fetchall()
    return [
        {
            "wxid": r["wxid"],
            "display_name": r["display_name"],
            "remark": r["remark"] or "",
            "nickname": r["nickname"] or "",
            "labels": parse_labels(r["labels"]),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# 账号合并
# ---------------------------------------------------------------------------

def get_all_merges(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """读取所有合并关系。返回 {canonical_wxid: [merged_wxid1, merged_wxid2, ...]}。"""
    try:
        rows = conn.execute(
            "SELECT canonical_wxid, merged_wxids FROM contact_merges"
        ).fetchall()
        return {
            r["canonical_wxid"]: json.loads(r["merged_wxids"])
            for r in rows
        }
    except sqlite3.OperationalError:
        return {}


def get_merge_for_wxid(conn: sqlite3.Connection, wxid: str) -> list[str] | None:
    """查找 wxid 所属的合并组。返回合并组中所有 wxid（含自身），None 表示未合并。"""
    merges = get_all_merges(conn)
    for canonical, merged_list in merges.items():
        all_wxids = [canonical] + merged_list
        if wxid in all_wxids:
            return all_wxids
    return None


def add_merge(
    conn: sqlite3.Connection,
    canonical_wxid: str,
    merged_wxids: list[str],
    display_name: str = "",
) -> None:
    """添加或更新合并组。canonical_wxid 是主账号，merged_wxids 是要合并进来的账号。"""
    now = int(time.time())
    conn.execute(
        """
        INSERT INTO contact_merges (canonical_wxid, merged_wxids, display_name, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(canonical_wxid) DO UPDATE SET
            merged_wxids = excluded.merged_wxids,
            display_name = excluded.display_name
        """,
        (canonical_wxid, json.dumps(merged_wxids, ensure_ascii=False), display_name, now),
    )
    conn.commit()


def remove_merge(conn: sqlite3.Connection, canonical_wxid: str) -> bool:
    """删除合并组。"""
    cursor = conn.execute(
        "DELETE FROM contact_merges WHERE canonical_wxid = ?", (canonical_wxid,)
    )
    conn.commit()
    return cursor.rowcount > 0

