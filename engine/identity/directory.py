"""联系人身份目录。

把 WeFlow 的 wxid / 会话和用户记得住的各种名字统一映射到稳定 Person。
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from dataclasses import dataclass, field


MAX_CANDIDATES = 5


@dataclass(frozen=True)
class IdentityAccount:
    id: str
    person_id: str
    wxid: str
    conversation_id: str
    display_name: str
    remark: str = ""
    nickname: str = ""
    active: bool = True


@dataclass(frozen=True)
class IdentityPerson:
    id: str
    display_name: str
    real_name: str = ""
    note: str = ""
    accounts: list[IdentityAccount] = field(default_factory=list)
    aliases: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class ResolveResult:
    person: IdentityPerson | None
    candidates: list[IdentityPerson] = field(default_factory=list)
    matched_by: str = ""
    too_many: bool = False


def bootstrap_identity(conn: sqlite3.Connection) -> dict[str, int]:
    """从现有 contacts/conversations 初始化身份目录。

    先为每个私聊 wxid 建 1:1 Person，再把现有 contact_merges 合并进去。
    """
    rows = conn.execute(
        """
        SELECT c.id AS wxid,
               c.id AS conversation_id,
               COALESCE(c.display_name, co.display_name, co.remark, co.nickname, c.id) AS display_name,
               co.remark,
               co.nickname,
               co.alias
        FROM conversations c
        LEFT JOIN contacts co ON co.id = c.id
        WHERE c.type = 'private'
        """
    ).fetchall()

    created_people = 0
    created_accounts = 0
    created_aliases = 0
    now = int(time.time())
    for row in rows:
        wxid = row["wxid"]
        account_id = _account_id_for_wxid(wxid)
        existing_account = conn.execute(
            "SELECT person_id FROM contact_accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        person_id = (
            existing_account["person_id"]
            if existing_account else _person_id_for_wxid(wxid)
        )
        display_name = _default_display_name(row)

        exists = conn.execute("SELECT 1 FROM people WHERE id = ?", (person_id,)).fetchone()
        if not exists:
            conn.execute(
                """
                INSERT INTO people (id, display_name, real_name, note, created_at, updated_at)
                VALUES (?, ?, '', '', ?, ?)
                """,
                (person_id, display_name, now, now),
            )
            created_people += 1

        conn.execute(
            """
            INSERT INTO contact_accounts (
                id, person_id, platform, wxid, conversation_id, display_name,
                remark, nickname, active, source, updated_at
            )
            VALUES (?, ?, 'wechat', ?, ?, ?, ?, ?, 1, 'bootstrap', ?)
            ON CONFLICT(id) DO UPDATE SET
                display_name = excluded.display_name,
                remark = excluded.remark,
                nickname = excluded.nickname,
                updated_at = excluded.updated_at
            """,
            (
                account_id,
                person_id,
                wxid,
                row["conversation_id"],
                display_name,
                row["remark"] or "",
                row["nickname"] or "",
                now,
            ),
        )
        if not existing_account:
            created_accounts += 1

        for alias_type, value in _aliases_from_row(row, display_name):
            if _insert_alias(conn, person_id, account_id, alias_type, value, "bootstrap"):
                created_aliases += 1

    conn.commit()

    merge_count = _apply_existing_merges(conn)
    return {
        "people": created_people,
        "accounts": created_accounts,
        "aliases": created_aliases,
        "merges": merge_count,
    }


def resolve_contact(conn: sqlite3.Connection, query: str) -> ResolveResult:
    """统一查人入口。"""
    bootstrap_identity(conn)
    q = query.strip()
    if not q:
        return ResolveResult(None, [])

    row = conn.execute("SELECT id FROM people WHERE id = ?", (q,)).fetchone()
    if row:
        return ResolveResult(get_person(conn, row["id"]), matched_by="person_id")

    row = conn.execute(
        """
        SELECT person_id FROM contact_accounts
        WHERE wxid = ? OR conversation_id = ? OR id = ?
        LIMIT 1
        """,
        (q, q, q),
    ).fetchone()
    if row:
        return ResolveResult(get_person(conn, row["person_id"]), matched_by="account")

    norm = normalize_alias(q)
    exact_rows = conn.execute(
        """
        SELECT DISTINCT person_id, alias_type FROM contact_aliases
        WHERE value_norm = ?
        LIMIT ?
        """,
        (norm, MAX_CANDIDATES + 1),
    ).fetchall()
    exact_person_ids = list(dict.fromkeys(r["person_id"] for r in exact_rows))
    if len(exact_person_ids) == 1:
        return ResolveResult(
            get_person(conn, exact_person_ids[0]),
            matched_by=f"alias:{exact_rows[0]['alias_type']}",
        )
    if len(exact_person_ids) > 1:
        return _candidate_result(conn, exact_person_ids)

    like_rows = conn.execute(
        """
        SELECT DISTINCT person_id FROM contact_aliases
        WHERE value_norm LIKE ?
        LIMIT ?
        """,
        (f"%{norm}%", MAX_CANDIDATES + 1),
    ).fetchall()
    if len(like_rows) == 1:
        return ResolveResult(get_person(conn, like_rows[0]["person_id"]), matched_by="alias:fuzzy")
    return _candidate_result(conn, [r["person_id"] for r in like_rows])


def search_people(conn: sqlite3.Connection, keyword: str) -> ResolveResult:
    """搜索联系人，可能返回多个候选。"""
    return resolve_contact(conn, keyword)


def get_person(conn: sqlite3.Connection, person_id: str) -> IdentityPerson | None:
    row = conn.execute(
        "SELECT id, display_name, real_name, note FROM people WHERE id = ?",
        (person_id,),
    ).fetchone()
    if not row:
        return None
    accounts = [
        IdentityAccount(
            id=r["id"],
            person_id=r["person_id"],
            wxid=r["wxid"] or "",
            conversation_id=r["conversation_id"] or "",
            display_name=r["display_name"] or "",
            remark=r["remark"] or "",
            nickname=r["nickname"] or "",
            active=bool(r["active"]),
        )
        for r in conn.execute(
            """
            SELECT id, person_id, wxid, conversation_id, display_name, remark, nickname, active
            FROM contact_accounts
            WHERE person_id = ?
            ORDER BY active DESC, display_name
            """,
            (person_id,),
        ).fetchall()
    ]
    aliases = [
        {
            "type": r["alias_type"],
            "value": r["value"],
            "sensitivity": r["sensitivity"],
            "source": r["source"] or "",
        }
        for r in conn.execute(
            """
            SELECT alias_type, value, sensitivity, source
            FROM contact_aliases
            WHERE person_id = ?
            ORDER BY alias_type, value
            """,
            (person_id,),
        ).fetchall()
    ]
    return IdentityPerson(
        id=row["id"],
        display_name=row["display_name"],
        real_name=row["real_name"] or "",
        note=row["note"] or "",
        accounts=accounts,
        aliases=aliases,
    )


def add_alias(
    conn: sqlite3.Connection,
    person_id: str,
    alias_type: str,
    value: str,
    *,
    sensitivity: str = "normal",
    source: str = "manual",
) -> bool:
    person = get_person(conn, person_id)
    if not person:
        return False
    inserted = _insert_alias(
        conn, person_id, None, alias_type, value, source, sensitivity=sensitivity
    )
    conn.commit()
    if inserted:
        _log(conn, "alias_add", person_id, {"type": alias_type, "value": value})
    return inserted


def set_display_name(conn: sqlite3.Connection, person_id: str, display_name: str) -> bool:
    if not get_person(conn, person_id):
        return False
    now = int(time.time())
    conn.execute(
        "UPDATE people SET display_name = ?, updated_at = ? WHERE id = ?",
        (display_name, now, person_id),
    )
    _insert_alias(conn, person_id, None, "display_name", display_name, "manual")
    _log(conn, "set_name", person_id, {"display_name": display_name})
    conn.commit()
    return True


def link_account(conn: sqlite3.Connection, person_id: str, wxid: str) -> bool:
    person = get_person(conn, person_id)
    if not person:
        return False
    source = get_person_by_wxid(conn, wxid)
    if source and source.id != person_id:
        merge_people(conn, person_id, source.id)
        return True

    row = conn.execute(
        """
        SELECT c.id AS wxid,
               COALESCE(c.display_name, co.display_name, co.remark, co.nickname, c.id) AS display_name,
               co.remark,
               co.nickname
        FROM conversations c
        LEFT JOIN contacts co ON co.id = c.id
        WHERE c.id = ?
        """,
        (wxid,),
    ).fetchone()
    if not row:
        return False
    now = int(time.time())
    account_id = _account_id_for_wxid(wxid)
    conn.execute(
        """
        INSERT INTO contact_accounts (
            id, person_id, platform, wxid, conversation_id, display_name,
            remark, nickname, active, source, updated_at
        )
        VALUES (?, ?, 'wechat', ?, ?, ?, ?, ?, 1, 'manual', ?)
        ON CONFLICT(id) DO UPDATE SET
            person_id = excluded.person_id,
            updated_at = excluded.updated_at
        """,
        (
            account_id,
            person_id,
            wxid,
            wxid,
            _default_display_name(row),
            row["remark"] or "",
            row["nickname"] or "",
            now,
        ),
    )
    _log(conn, "link_account", person_id, {"wxid": wxid})
    conn.commit()
    return True


def get_person_by_wxid(conn: sqlite3.Connection, wxid: str) -> IdentityPerson | None:
    row = conn.execute(
        "SELECT person_id FROM contact_accounts WHERE wxid = ?",
        (wxid,),
    ).fetchone()
    if not row:
        return None
    return get_person(conn, row["person_id"])


def merge_people(conn: sqlite3.Connection, keep_person_id: str, merge_person_id: str) -> bool:
    if keep_person_id == merge_person_id:
        return False
    keep = get_person(conn, keep_person_id)
    merge = get_person(conn, merge_person_id)
    if not keep or not merge:
        return False
    now = int(time.time())
    conn.execute(
        "UPDATE contact_accounts SET person_id = ?, updated_at = ? WHERE person_id = ?",
        (keep_person_id, now, merge_person_id),
    )
    conn.execute(
        "UPDATE contact_aliases SET person_id = ? WHERE person_id = ?",
        (keep_person_id, merge_person_id),
    )
    _insert_alias(conn, keep_person_id, None, "merged_display_name", merge.display_name, "merge")
    conn.execute("DELETE FROM people WHERE id = ?", (merge_person_id,))
    _log(conn, "merge_people", keep_person_id, {"merged": merge_person_id})
    conn.commit()
    return True


def audit_identity(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    bootstrap_identity(conn)
    duplicate_aliases = [
        {
            "value": r["value"],
            "value_norm": r["value_norm"],
            "people": r["people"].split(","),
            "count": r["cnt"],
        }
        for r in conn.execute(
            """
            SELECT value, value_norm, COUNT(DISTINCT person_id) AS cnt,
                   GROUP_CONCAT(DISTINCT person_id) AS people
            FROM contact_aliases
            WHERE alias_type IN ('display_name', 'remark', 'nickname', 'manual', 'fake_name', 'real_name')
            GROUP BY value_norm
            HAVING cnt > 1
            ORDER BY cnt DESC, value
            LIMIT 50
            """
        ).fetchall()
    ]
    multi_account = [
        {
            "person_id": r["id"],
            "display_name": r["display_name"],
            "accounts": r["cnt"],
        }
        for r in conn.execute(
            """
            SELECT p.id, p.display_name, COUNT(a.id) AS cnt
            FROM people p
            JOIN contact_accounts a ON a.person_id = p.id
            GROUP BY p.id
            HAVING cnt > 1
            ORDER BY cnt DESC, p.display_name
            """
        ).fetchall()
    ]
    return {"duplicate_aliases": duplicate_aliases, "multi_account": multi_account}


def normalize_alias(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().lower())


def _candidate_result(conn: sqlite3.Connection, person_ids: list[str]) -> ResolveResult:
    unique_ids = list(dict.fromkeys(person_ids))
    too_many = len(unique_ids) > MAX_CANDIDATES
    selected = unique_ids[:MAX_CANDIDATES]
    candidates = [p for pid in selected if (p := get_person(conn, pid))]
    return ResolveResult(None, candidates, matched_by="candidate", too_many=too_many)


def _person_id_for_wxid(wxid: str) -> str:
    digest = hashlib.md5(wxid.encode("utf-8")).hexdigest()[:8]
    return f"person_{digest}"


def _account_id_for_wxid(wxid: str) -> str:
    digest = hashlib.md5(wxid.encode("utf-8")).hexdigest()[:8]
    return f"acct_{digest}"


def _default_display_name(row: sqlite3.Row) -> str:
    remark = (row["remark"] or "").strip() if "remark" in row.keys() else ""
    nickname = (row["nickname"] or "").strip() if "nickname" in row.keys() else ""
    display = (row["display_name"] or "").strip() if "display_name" in row.keys() else ""
    wxid = (row["wxid"] or "").strip()
    return remark or nickname or display or _wxid_suffix(wxid)


def _wxid_suffix(wxid: str) -> str:
    if len(wxid) <= 6:
        return wxid
    return wxid[-6:]


def _aliases_from_row(row: sqlite3.Row, display_name: str) -> list[tuple[str, str]]:
    values = [
        ("display_name", display_name),
        ("remark", row["remark"] or ""),
        ("nickname", row["nickname"] or ""),
        ("wechat_alias", row["alias"] or "" if "alias" in row.keys() else ""),
        ("wxid_suffix", _wxid_suffix(row["wxid"])),
    ]
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for alias_type, value in values:
        value = value.strip()
        norm = normalize_alias(value)
        if not value or norm in seen:
            continue
        seen.add(norm)
        out.append((alias_type, value))
    return out


def _insert_alias(
    conn: sqlite3.Connection,
    person_id: str,
    account_id: str | None,
    alias_type: str,
    value: str,
    source: str,
    *,
    sensitivity: str = "normal",
) -> bool:
    value = value.strip()
    if not value:
        return False
    norm = normalize_alias(value)
    exists = conn.execute(
        """
        SELECT 1 FROM contact_aliases
        WHERE person_id = ? AND alias_type = ? AND value_norm = ?
        """,
        (person_id, alias_type, norm),
    ).fetchone()
    if exists:
        return False
    conn.execute(
        """
        INSERT INTO contact_aliases (
            person_id, account_id, alias_type, value, value_norm,
            sensitivity, source, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (person_id, account_id, alias_type, value, norm, sensitivity, source, int(time.time())),
    )
    return True


def _apply_existing_merges(conn: sqlite3.Connection) -> int:
    try:
        rows = conn.execute("SELECT canonical_wxid, merged_wxids FROM contact_merges").fetchall()
    except sqlite3.OperationalError:
        return 0
    count = 0
    for row in rows:
        keep = get_person_by_wxid(conn, row["canonical_wxid"])
        if not keep:
            continue
        try:
            merged_wxids = json.loads(row["merged_wxids"])
        except json.JSONDecodeError:
            continue
        for wxid in merged_wxids:
            merge = get_person_by_wxid(conn, wxid)
            if merge and merge.id != keep.id and merge_people(conn, keep.id, merge.id):
                count += 1
    return count


def _log(conn: sqlite3.Connection, action: str, person_id: str, detail: dict) -> None:
    conn.execute(
        """
        INSERT INTO contact_identity_log (action, person_id, detail, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (action, person_id, json.dumps(detail, ensure_ascii=False), int(time.time())),
    )
