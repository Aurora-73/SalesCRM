"""朋友圈增量同步

从 WeFlow SNS Timeline API 拉取朋友圈数据，写入 SQLite。
使用 offset 分页 + watermark checkpoint。
"""
import json
import logging
import sqlite3
import time

from engine.importers.weflow_client import WeFlowClient
from engine.importers.checkpoint import CheckpointManager

logger = logging.getLogger(__name__)

# 朋友圈 checkpoint 的 session_id 标识
MOMENTS_SESSION_ID = "__moments__"


def upsert_moment(db: sqlite3.Connection, moment: dict) -> str:
    """幂等写入单条朋友圈。返回 moment id。"""
    tid = str(moment.get("tid", ""))
    if not tid:
        return ""

    author_id = moment.get("username", "")
    author_name = moment.get("nickname", "")
    content = moment.get("contentDesc", "")
    timestamp = moment.get("createTime", 0)
    media = moment.get("media", [])
    media_count = len(media)
    likes = moment.get("likes", [])
    comments = moment.get("comments", [])

    db.execute(
        """
        INSERT INTO moments (
            id, author_id, author_name, content, timestamp,
            media_count, like_count, comment_count,
            raw_json, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))
        ON CONFLICT(id) DO UPDATE SET
            content = excluded.content,
            author_name = excluded.author_name,
            media_count = excluded.media_count,
            like_count = excluded.like_count,
            comment_count = excluded.comment_count,
            raw_json = excluded.raw_json,
            synced_at = excluded.synced_at
        """,
        (
            tid,
            author_id,
            author_name,
            content,
            timestamp,
            media_count,
            len(likes),
            len(comments),
            json.dumps(moment, ensure_ascii=False),
        ),
    )

    # 写入点赞
    for i, liker_name in enumerate(likes):
        like_id = f"{tid}_like_{i}"
        db.execute(
            """
            INSERT INTO moment_interactions (
                id, moment_id, type, user_id, user_name, content, timestamp, synced_at
            ) VALUES (?, ?, 'like', '', ?, NULL, ?, strftime('%s','now'))
            ON CONFLICT(id) DO UPDATE SET
                user_name = excluded.user_name,
                synced_at = excluded.synced_at
            """,
            (like_id, tid, liker_name, timestamp),
        )

    # 写入评论
    for i, comment in enumerate(comments):
        if isinstance(comment, dict):
            comment_id = f"{tid}_comment_{i}"
            db.execute(
                """
                INSERT INTO moment_interactions (
                    id, moment_id, type, user_id, user_name, content, timestamp, synced_at
                ) VALUES (?, ?, 'comment', ?, ?, ?, ?, strftime('%s','now'))
                ON CONFLICT(id) DO UPDATE SET
                    user_name = excluded.user_name,
                    content = excluded.content,
                    synced_at = excluded.synced_at
                """,
                (
                    comment_id,
                    tid,
                    comment.get("username", ""),
                    comment.get("nickname", ""),
                    comment.get("content", ""),
                    comment.get("createTime", timestamp),
                ),
            )

    return tid


def sync_moments(
    client: WeFlowClient,
    db: sqlite3.Connection,
    checkpoint: CheckpointManager,
    verbose: bool = False,
) -> int:
    """同步朋友圈数据，返回新增/更新条数。"""
    total_synced = 0
    offset = 0
    page_size = 50

    while True:
        resp = client.get_moments_timeline(limit=page_size, offset=offset)

        timeline = resp.get("timeline", [])
        if not timeline:
            break

        for moment in timeline:
            upsert_moment(db, moment)

        db.commit()
        total_synced += len(timeline)

        if verbose:
            logger.info(f"  朋友圈: +{len(timeline)} 条 (累计 {total_synced})")

        # 更新 watermark
        latest_ts = max(m.get("createTime", 0) for m in timeline)
        checkpoint.update_watermark(MOMENTS_SESSION_ID, latest_ts, len(timeline))

        # 检查是否还有更多
        if len(timeline) < page_size:
            break

        offset += len(timeline)

    checkpoint.clear_error(MOMENTS_SESSION_ID)
    return total_synced
