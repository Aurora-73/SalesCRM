"""消息增量同步

从 WeFlow 原始消息 API 拉取消息，增量写入 SQLite。
使用 offset 分页 + watermark checkpoint。

已知限制：WeFlow API 行为不稳定，相同参数有时返回 0 有时返回数据。
使用重试 + 多 limit 值探测来缓解。
"""
import hashlib
import json
import logging
import sqlite3
import time
from datetime import datetime

from engine.importers.weflow_client import WeFlowClient
from engine.importers.checkpoint import CheckpointManager

logger = logging.getLogger(__name__)

# 原始消息 API 默认日期范围（覆盖所有历史数据）
# 注意：start=20200101 会导致 API 返回 0 条（WeFlow 限制），20210101 起正常
DEFAULT_START = "20210101"


def fallback_message_id(
    session_id: str, sender: str, timestamp: int, content: str
) -> str:
    """构造 fallback 去重键（当 serverId 缺失时）。"""
    raw = f"{session_id}:{sender}:{timestamp}:{content}"
    return "fb_" + hashlib.md5(raw.encode("utf-8")).hexdigest()


def upsert_message(db: sqlite3.Connection, session_id: str, msg: dict) -> None:
    """幂等写入单条消息（兼容原始 API 和 ChatLab 两种格式）。"""
    # 原始 API 字段优先，ChatLab 字段兜底
    server_id = msg.get("serverId") or msg.get("platformMessageId")
    if not server_id:
        server_id = fallback_message_id(
            session_id,
            msg.get("senderUsername") or msg.get("sender", ""),
            msg.get("createTime") or msg.get("timestamp", 0),
            msg.get("content", ""),
        )

    sender_id = msg.get("senderUsername") or msg.get("sender", "")
    timestamp = msg.get("createTime") or msg.get("timestamp", 0)
    msg_type = msg.get("localType") or msg.get("type", 0)
    content = msg.get("parsedContent") or msg.get("content")
    raw_content = msg.get("rawContent")
    reply_to = msg.get("replyToMessageId")
    media_path = msg.get("mediaUrl") or msg.get("mediaPath")
    group_nick = msg.get("groupNickname")

    db.execute(
        """
        INSERT INTO messages (
            id, conversation_id, sender_id, sender_name,
            timestamp, type, content, raw_content,
            reply_to_id, media_path, group_nickname,
            raw_json, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))
        ON CONFLICT(id) DO UPDATE SET
            content = excluded.content,
            raw_content = excluded.raw_content,
            sender_name = excluded.sender_name,
            media_path = excluded.media_path,
            raw_json = excluded.raw_json,
            synced_at = excluded.synced_at
        """,
        (
            str(server_id),
            session_id,
            sender_id,
            msg.get("accountName") or msg.get("senderName", ""),
            timestamp,
            msg_type,
            content,
            raw_content,
            reply_to,
            media_path,
            group_nick,
            json.dumps(msg, ensure_ascii=False),
        ),
    )

    # 有媒体信息时写入 attachments 表
    if media_path:
        upsert_attachment(db, str(server_id), session_id, msg)


def upsert_attachment(
    db: sqlite3.Connection, message_id: str, session_id: str, msg: dict
) -> None:
    """幂等写入附件记录。"""
    att_id = f"att_{message_id}"
    media_url = msg.get("mediaUrl") or msg.get("mediaPath", "")
    media_type_raw = msg.get("mediaType", "")
    media_type = media_type_raw if media_type_raw else "unknown"
    if not media_type_raw:
        if "/images/" in media_url:
            media_type = "image"
        elif "/voices/" in media_url:
            media_type = "voice"
        elif "/videos/" in media_url:
            media_type = "video"

    file_name = msg.get("mediaFileName") or (
        media_url.rsplit("/", 1)[-1] if "/" in media_url else media_url
    )

    db.execute(
        """
        INSERT INTO attachments (
            id, message_id, conversation_id, media_type,
            file_name, http_url, local_path, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))
        ON CONFLICT(id) DO UPDATE SET
            http_url = excluded.http_url,
            local_path = excluded.local_path,
            synced_at = excluded.synced_at
        """,
        (
            att_id,
            message_id,
            session_id,
            media_type,
            file_name,
            media_url,
            msg.get("mediaLocalPath"),
        ),
    )


def _ts_to_datestr(ts: int) -> str:
    """Unix 时间戳 → YYYYMMDD 字符串。"""
    return datetime.fromtimestamp(ts).strftime("%Y%m%d")


def _fetch_messages_with_retry(
    client: WeFlowClient,
    session_id: str,
    start_date: str,
    offset: int = 0,
    max_retries: int = 3,
) -> dict:
    """带重试的消息拉取。WeFlow API 不稳定，需要重试。"""
    limits_to_try = [500, 200, 100]

    for attempt in range(max_retries):
        limit = limits_to_try[attempt % len(limits_to_try)]
        resp = client.get_messages(
            talker=session_id,
            limit=limit,
            offset=offset,
            start=start_date,
        )
        messages = resp.get("messages", [])
        if messages:
            return resp

        # 首次无数据且是 offset=0 时重试
        if offset == 0 and attempt < max_retries - 1:
            time.sleep(0.5)
            continue

        # 非首次页返回空，视为已到底
        return resp

    return resp


def sync_one_session(
    client: WeFlowClient,
    db: sqlite3.Connection,
    checkpoint: CheckpointManager,
    session_id: str,
    since: int,
    verbose: bool = False,
) -> int:
    """同步单个会话的增量消息，返回本次新增/更新消息数。

    使用原始消息 API（/api/v1/messages）+ offset 分页。
    since > 0 时作为 start 日期传入，实现增量同步。
    """
    total_synced = 0
    offset = 0
    start_date = _ts_to_datestr(since) if since > 0 else DEFAULT_START

    while True:
        resp = _fetch_messages_with_retry(client, session_id, start_date, offset)

        messages = resp.get("messages", [])
        if not messages:
            break

        for msg in messages:
            upsert_message(db, session_id, msg)

        db.commit()
        total_synced += len(messages)

        # 更新 watermark 到最新消息时间
        latest_ts = max(m.get("createTime", 0) for m in messages)
        if latest_ts > since:
            checkpoint.update_watermark(session_id, latest_ts, len(messages))

        if verbose:
            logger.info(
                f"  {session_id}: +{len(messages)} 条 (累计 {total_synced})"
            )

        has_more = resp.get("hasMore", False)
        if not has_more:
            break

        offset += len(messages)

    checkpoint.clear_error(session_id)
    return total_synced
