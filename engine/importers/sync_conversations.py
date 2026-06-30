"""会话同步

从 WeFlow API 拉取会话列表，幂等写入 SQLite。
"""
import json
import logging
import sqlite3

from engine.importers.weflow_client import WeFlowClient

logger = logging.getLogger(__name__)

# WeFlow API 返回的 type 字段不可靠（全为 0），改用 session_id 模式判断
_SESSION_TYPE_MAP = {1: "private", 2: "group", 3: "channel"}


def map_session_type(weFlow_type: int, session_id: str = "") -> str:
    """根据 session_id 模式判断会话类型（API type 字段不可靠）。"""
    if "@chatroom" in session_id:
        return "group"
    if session_id.startswith("gh_"):
        return "official"
    if session_id.startswith("wxid_") or "@" not in session_id:
        return "private"
    return _SESSION_TYPE_MAP.get(weFlow_type, "other")


def sync_conversations(client: WeFlowClient, db: sqlite3.Connection) -> int:
    """同步会话列表到 SQLite，返回会话总数。"""
    sessions = client.list_sessions(limit=10000)
    logger.info(f"拉取到 {len(sessions)} 个会话")

    for s in sessions:
        session_id = s.get("username", "")
        session_type = map_session_type(s.get("type", 0), session_id)
        contact_id = session_id if session_type == "private" else None

        db.execute(
            """
            INSERT INTO conversations (
                id, type, display_name, contact_id,
                last_message_at, unread_count, raw_json,
                first_seen_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%s','now'), strftime('%s','now'))
            ON CONFLICT(id) DO UPDATE SET
                display_name = excluded.display_name,
                last_message_at = excluded.last_message_at,
                unread_count = excluded.unread_count,
                raw_json = excluded.raw_json,
                updated_at = strftime('%s','now')
            """,
            (
                session_id,
                session_type,
                s.get("displayName"),
                contact_id,
                s.get("lastTimestamp"),
                s.get("unreadCount", 0),
                json.dumps(s, ensure_ascii=False),
            ),
        )

    db.commit()
    logger.info(f"会话同步完成: {len(sessions)} 个")
    return len(sessions)
