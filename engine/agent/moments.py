"""朋友圈 — moments_stats, sync_moments_to_archive 及辅助函数。"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from engine.config import Config, load_config
from engine.identity import IdentityPerson


def _query_moments_data(conn: sqlite3.Connection, wxid: str, my_wxid: str, display_name: str = "") -> dict:
    if not my_wxid:
        my_wxid = load_config().my_wxid
    my_name = ""
    row = conn.execute("SELECT display_name FROM contacts WHERE id = ?", (my_wxid,)).fetchone()
    if row:
        my_name = row[0] or ""
    result = {"customer_posts": [], "my_interactions_on_customer_posts": [], "customer_interactions_on_my_posts": []}
    rows = conn.execute(
        "SELECT content, timestamp, like_count, comment_count FROM moments WHERE author_id = ? ORDER BY timestamp DESC LIMIT 20",
        (wxid,),
    ).fetchall()
    for r in rows:
        result["customer_posts"].append({"content": r[0] or "", "timestamp": r[1], "likes": r[2], "comments": r[3]})
    if my_name:
        rows = conn.execute("""
            SELECT mi.type, mi.content, mi.timestamp, m.content
            FROM moment_interactions mi JOIN moments m ON mi.moment_id = m.id
            WHERE m.author_id = ? AND mi.user_name = ? ORDER BY mi.timestamp DESC LIMIT 20
        """, (wxid, my_name)).fetchall()
    else:
        rows = []
    for r in rows:
        result["my_interactions_on_customer_posts"].append({"type": r[0], "content": r[1] or "", "timestamp": r[2], "post": r[3] or ""})
    if display_name:
        rows = conn.execute("""
            SELECT mi.type, mi.content, mi.timestamp, m.content
            FROM moment_interactions mi JOIN moments m ON mi.moment_id = m.id
            WHERE m.author_id = ? AND mi.user_name = ? ORDER BY mi.timestamp DESC LIMIT 20
        """, (my_wxid, display_name)).fetchall()
    else:
        rows = []
    for r in rows:
        result["customer_interactions_on_my_posts"].append({"type": r[0], "content": r[1] or "", "timestamp": r[2], "my_post": r[3] or ""})
    return result


def _format_moments_section(moments: dict) -> str:
    parts = []
    customer_posts = moments["customer_posts"]
    customer_interactions = moments["customer_interactions_on_my_posts"]
    my_interactions = moments["my_interactions_on_customer_posts"]
    if not customer_posts and not customer_interactions and not my_interactions:
        return ""
    if customer_interactions:
        parts.append("### 客户在你的朋友圈互动")
        for item in customer_interactions[:10]:
            ts = datetime.fromtimestamp(item["timestamp"]).strftime("%m-%d")
            action = "评论" if item["type"] == "comment" else "点赞"
            post_preview = item["my_post"][:30]
            detail = f': "{item["content"][:40]}"' if item["content"] else ""
            parts.append(f"- [{ts}] {action}「{post_preview}」{detail}")
        parts.append("")
    if my_interactions:
        parts.append("### 你在客户的朋友圈互动")
        for item in my_interactions[:10]:
            ts = datetime.fromtimestamp(item["timestamp"]).strftime("%m-%d")
            action = "评论" if item["type"] == "comment" else "点赞"
            post_preview = item["post"][:30]
            detail = f': "{item["content"][:40]}"' if item["content"] else ""
            parts.append(f"- [{ts}] {action}「{post_preview}」{detail}")
        parts.append("")
    if customer_posts:
        parts.append("### 客户的朋友圈动态")
        for item in customer_posts[:10]:
            ts = datetime.fromtimestamp(item["timestamp"]).strftime("%m-%d")
            content = item["content"][:60] if item["content"] else "(图片/视频)"
            stats = []
            if item["likes"]:
                stats.append(f"{item['likes']}赞")
            if item["comments"]:
                stats.append(f"{item['comments']}评")
            stat_str = f" ({', '.join(stats)})" if stats else ""
            parts.append(f"- [{ts}] {content}{stat_str}")
        parts.append("")
    return "\n".join(parts)


def moments_stats(name: str) -> dict | str:
    from engine.agent.core import _get_conn, _resolve_person
    conn, config = _get_conn()
    try:
        person = _resolve_person(conn, name)
        if not person:
            return f"未找到联系人: {name}"
        if not person.accounts:
            return f"未找到联系人: {name}"
        wxid = person.accounts[0].wxid
        display_name = person.display_name
        my_wxid = config.my_wxid
        my_name_row = conn.execute("SELECT display_name FROM contacts WHERE id = ?", (my_wxid,)).fetchone()
        my_name = my_name_row[0] if my_name_row else ""
        customer_posts_count = conn.execute("SELECT COUNT(*) FROM moments WHERE author_id = ?", (wxid,)).fetchone()[0]
        my_likes, my_comments = 0, 0
        my_comments_detail = []
        if my_name:
            rows = conn.execute("""
                SELECT mi.type, mi.content, mi.timestamp, m.content
                FROM moment_interactions mi JOIN moments m ON mi.moment_id = m.id
                WHERE m.author_id = ? AND mi.user_name = ? ORDER BY mi.timestamp DESC
            """, (wxid, my_name)).fetchall()
            for r in rows:
                if r[0] == "like":
                    my_likes += 1
                elif r[0] == "comment":
                    my_comments += 1
                    my_comments_detail.append({"content": r[1] or "", "timestamp": r[2], "post": (r[3] or "")[:40]})
        customer_likes, customer_comments = 0, 0
        customer_comments_detail = []
        if display_name:
            rows = conn.execute("""
                SELECT mi.type, mi.content, mi.timestamp, m.content
                FROM moment_interactions mi JOIN moments m ON mi.moment_id = m.id
                WHERE m.author_id = ? AND mi.user_name = ? ORDER BY mi.timestamp DESC
            """, (my_wxid, display_name)).fetchall()
            for r in rows:
                if r[0] == "like":
                    customer_likes += 1
                elif r[0] == "comment":
                    customer_comments += 1
                    customer_comments_detail.append({"content": r[1] or "", "timestamp": r[2], "post": (r[3] or "")[:40]})
        my_posts_count = conn.execute("SELECT COUNT(*) FROM moments WHERE author_id = ?", (my_wxid,)).fetchone()[0]
        customer_like_ratio = customer_likes / my_posts_count if my_posts_count > 0 else 0.0
        total_customer = customer_likes + customer_comments
        total_my = my_likes + my_comments
        if total_customer == 0 and total_my == 0:
            summary = "无朋友圈互动"
        elif total_customer == 0 and total_my > 0:
            summary = f"单向投入：你有 {total_my} 次互动，客户 0 次"
        elif total_customer > 0 and total_my == 0:
            summary = f"客户主动：客户有 {total_customer} 次互动，你 0 次"
        elif total_my > total_customer * 2:
            summary = f"你投入过多：你 {total_my} 次 vs 客户 {total_customer} 次"
        else:
            summary = f"互动均衡：你 {total_my} 次 vs 客户 {total_customer} 次"
        return {
            "person": display_name, "person_id": person.id, "customer_posts": customer_posts_count,
            "my_likes_on_customer": my_likes, "my_comments_on_customer": my_comments,
            "my_comments_detail": my_comments_detail[:10],
            "customer_likes_on_my": customer_likes, "customer_comments_on_my": customer_comments,
            "customer_comments_detail": customer_comments_detail[:10],
            "my_posts_total": my_posts_count, "customer_like_ratio": round(customer_like_ratio, 3),
            "engagement_summary": summary,
        }
    finally:
        conn.close()


def sync_moments_to_archive(conn: sqlite3.Connection, config: Config, person: IdentityPerson) -> str:
    if not person.accounts:
        return ""
    wxid = person.accounts[0].wxid
    moments = _query_moments_data(conn, wxid, config.my_wxid)
    text = _format_moments_section(moments)
    if not text:
        return ""
    from engine.facts.people_archive import get_person_archive_path
    path = get_person_archive_path(person, my_wxid=config.my_wxid)
    if path.is_file():
        content = path.read_text(encoding="utf-8")
    else:
        content = ""
    section_header = "## 朋友圈互动"
    if section_header in content:
        idx = content.find(section_header)
        next_section = content.find("\n## ", idx + 4)
        if next_section != -1:
            content = content[:idx] + f"{section_header}\n\n{text}\n\n" + content[next_section:]
        else:
            content = content[:idx] + f"{section_header}\n\n{text}\n"
    else:
        if not content.endswith("\n"):
            content += "\n"
        content += f"\n{section_header}\n\n{text}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return text
