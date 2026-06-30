"""同步 checkpoint 管理

基于 SQLite sync_state / sync_log 表管理每个会话的增量同步进度。
"""
import sqlite3
import time
from typing import Optional


class CheckpointManager:
    """管理同步 checkpoint（基于 SQLite sync_state / sync_log 表）"""

    def __init__(self, conn: sqlite3.Connection):
        """接受一个已打开的 DB 连接（应已设置 row_factory = sqlite3.Row）。"""
        self.conn = conn

    # ---- sync_state 操作 ----

    def get_watermark(self, session_id: str) -> int:
        """获取会话的上次 watermark，首次同步返回 0。"""
        row = self.conn.execute(
            "SELECT watermark FROM sync_state WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row["watermark"] if row else 0

    def update_watermark(
        self,
        session_id: str,
        watermark: int,
        message_count_delta: int = 0,
    ):
        """UPSERT watermark：更新水位、累加消息数、刷新同步时间、清除错误。"""
        now = int(time.time())
        self.conn.execute(
            """
            INSERT INTO sync_state (session_id, watermark, message_count, last_sync_at, last_error)
            VALUES (?, ?, ?, ?, NULL)
            ON CONFLICT(session_id) DO UPDATE SET
                watermark = excluded.watermark,
                message_count = sync_state.message_count + excluded.message_count,
                last_sync_at = excluded.last_sync_at,
                last_error = NULL
            """,
            (session_id, watermark, message_count_delta, now),
        )
        self.conn.commit()

    def record_error(self, session_id: str, error: str):
        """记录同步错误，同时刷新 last_sync_at。"""
        now = int(time.time())
        self.conn.execute(
            """
            INSERT INTO sync_state (session_id, watermark, message_count, last_sync_at, last_error)
            VALUES (?, 0, 0, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                last_error = excluded.last_error,
                last_sync_at = excluded.last_sync_at
            """,
            (session_id, now, error),
        )
        self.conn.commit()

    def clear_error(self, session_id: str):
        """清除同步错误（将 last_error 置为 NULL）。"""
        self.conn.execute(
            "UPDATE sync_state SET last_error = NULL WHERE session_id = ?",
            (session_id,),
        )
        self.conn.commit()

    def get_all_states(self) -> list[dict]:
        """获取所有会话的同步状态，返回字典列表。"""
        rows = self.conn.execute(
            """
            SELECT session_id, watermark, message_count, last_sync_at, last_error
            FROM sync_state
            ORDER BY last_sync_at DESC
            """
        ).fetchall()
        return [
            {
                "session_id": r["session_id"],
                "watermark": r["watermark"],
                "message_count": r["message_count"],
                "last_sync_at": r["last_sync_at"],
                "last_error": r["last_error"],
            }
            for r in rows
        ]

    # ---- sync_log 操作 ----

    def start_sync_log(self, session_id: Optional[str] = None) -> int:
        """写入一条 sync_log 记录（started_at=now），返回自增 id。"""
        now = int(time.time())
        cursor = self.conn.execute(
            """
            INSERT INTO sync_log (started_at, session_id)
            VALUES (?, ?)
            """,
            (now, session_id),
        )
        self.conn.commit()
        return cursor.lastrowid

    def finish_sync_log(
        self,
        log_id: int,
        messages_synced: int,
        status: str,
        error_detail: Optional[str] = None,
    ):
        """更新 sync_log 记录：填入 finished_at、同步消息数、状态和错误详情。"""
        now = int(time.time())
        self.conn.execute(
            """
            UPDATE sync_log
            SET finished_at = ?, messages_synced = ?, status = ?, error_detail = ?
            WHERE id = ?
            """,
            (now, messages_synced, status, error_detail, log_id),
        )
        self.conn.commit()

    # ---- 汇总查询 ----

    def get_sync_summary(self) -> dict:
        """返回同步汇总信息。

        Returns:
            {
                "total_contacts": int,
                "total_conversations": int,
                "total_messages": int,
                "last_sync_at": int | None,
                "session_states": list[dict],
            }
        """
        # 会话总数与总消息数
        agg = self.conn.execute(
            "SELECT COUNT(*) AS cnt, COALESCE(SUM(message_count), 0) AS total_msg FROM sync_state"
        ).fetchone()
        total_conversations = agg["cnt"]
        total_messages = agg["total_msg"]

        # 最后同步时间
        last_row = self.conn.execute(
            "SELECT MAX(last_sync_at) AS last_ts FROM sync_state"
        ).fetchone()
        last_sync_at = last_row["last_ts"]

        # 会话状态列表
        session_states = self.get_all_states()

        # 联系人总数（如果 contacts 表存在）
        total_contacts = 0
        try:
            cr = self.conn.execute("SELECT COUNT(*) AS cnt FROM contacts").fetchone()
            total_contacts = cr["cnt"]
        except sqlite3.OperationalError:
            # contacts 表不存在时降级为会话数
            total_contacts = total_conversations

        return {
            "total_contacts": total_contacts,
            "total_conversations": total_conversations,
            "total_messages": total_messages,
            "last_sync_at": last_sync_at,
            "session_states": session_states,
        }
