"""同步主入口

协调联系人、会话、消息的全量/增量同步。
"""
import logging
import time
from dataclasses import dataclass

from engine.config import Config
from engine.importers.db_init import init_db, get_db
from engine.importers.weflow_client import WeFlowClient, WeFlowError
from engine.importers.wcd_client import WCDClient, WCDError
from engine.importers.checkpoint import CheckpointManager
from engine.importers.sync_contacts import sync_contacts
from engine.importers.sync_conversations import sync_conversations
from engine.importers.sync_messages import sync_one_session
from engine.importers.sync_moments import sync_moments

logger = logging.getLogger(__name__)


class SyncError(Exception):
    """同步错误"""


@dataclass
class SyncResult:
    contact_count: int = 0
    session_count: int = 0
    total_synced: int = 0
    elapsed_seconds: float = 0
    mode: str = "incremental"
    sessions_ok: int = 0
    sessions_skipped: int = 0  # WCDB 500 数据库未加载
    sessions_error: int = 0    # 其他错误
    moments_synced: int = 0


def run_sync(
    config: Config,
    mode: str = "incremental",
    session_id: str | None = None,
    meta_only: bool = False,
    verbose: bool = False,
) -> SyncResult:
    """执行同步（仅私聊，不包含群聊和公众号）。

    Args:
        config: 全局配置
        mode: "incremental"（默认）或 "full"
        session_id: 指定同步某个私聊（None = 全部私聊）
        meta_only: 只同步联系人和会话（不同步消息）
        verbose: 输出详细日志
    """
    start_time = time.time()

    # 确保数据库已初始化
    db = init_db(config.db_path)

    # 根据 backend 配置选择客户端
    if config.weflow.backend == "wcd":
        client = WCDClient(
            base_url=config.weflow.base_url,
            token=config.weflow.token,
            timeout=config.weflow.timeout,
            decrypted_db_dir=config.weflow.decrypted_db_dir or None,
        )
    else:
        client = WeFlowClient(
            base_url=config.weflow.base_url,
            token=config.weflow.token,
            timeout=config.weflow.timeout,
        )
    checkpoint = CheckpointManager(db)

    # 记录同步日志开始
    sync_log_id = checkpoint.start_sync_log()

    # 1. 健康检查
    if not client.health():
        raise SyncError(
            f"连接 API 失败: {config.weflow.base_url}\n"
            f"请确保:\n"
            f"1. WCD 已启动（cd _reference/WeChatDataAnalysis && uv run main.py）\n"
            f"2. API 服务端口正确（默认 10392）\n"
            f"3. Token 已配置（data/system/config.yaml → weflow.token）"
        )

    # 2. 刷新 WCD 数据库快照（使用缓存密钥，不重启微信）
    if config.weflow.backend == "wcd":
        try:
            client.decrypt_databases()
        except WCDError as e:
            logger.warning(f"数据库解密失败（不影响同步，使用旧快照）: {e}")

    # 3. 同步联系人
    contact_count = sync_contacts(client, db)

    # 4. 同步会话列表
    session_count = sync_conversations(client, db)

    result = SyncResult(
        contact_count=contact_count,
        session_count=session_count,
        mode=mode,
    )

    if meta_only:
        result.elapsed_seconds = time.time() - start_time
        return result

    # 5. 按会话增量同步消息（只同步私聊，不同步群聊/公众号）
    if session_id:
        sessions = [(session_id,)]
    else:
        sessions = db.execute(
            "SELECT id FROM conversations WHERE type = 'private'"
        ).fetchall()

    total_synced = 0
    for (sid,) in sessions:
        since = 0 if mode == "full" else checkpoint.get_watermark(sid)
        try:
            synced = sync_one_session(
                client,
                db,
                checkpoint,
                sid,
                since,
                verbose=verbose,
            )
            total_synced += synced
            if synced > 0:
                result.sessions_ok += 1
        except (WeFlowError, WCDError) as e:
            error_msg = str(e)
            if "创建游标失败" in error_msg or "-3" in error_msg:
                # WCDB 消息数据库未加载，不是真正的错误
                result.sessions_skipped += 1
                if verbose:
                    logger.info(f"  {sid}: 消息数据库未加载（跳过）")
            else:
                logger.error(f"会话 {sid} 同步失败: {error_msg}")
                checkpoint.record_error(sid, error_msg)
                result.sessions_error += 1
        except Exception as e:
            logger.error(f"会话 {sid} 同步异常: {e}")
            checkpoint.record_error(sid, str(e))
            result.sessions_error += 1

    result.total_synced = total_synced

    # 6. 同步朋友圈
    if config.weflow.sync_moments and not session_id:
        try:
            moments_count = sync_moments(client, db, checkpoint, verbose=verbose)
            result.moments_synced = moments_count
        except Exception as e:
            logger.error(f"朋友圈同步失败: {e}")

    result.elapsed_seconds = time.time() - start_time

    # 6. 记录日志
    checkpoint.finish_sync_log(
        sync_log_id,
        total_synced,
        "success",
    )

    return result


def show_status(config: Config) -> str:
    """显示同步状态和覆盖率。"""
    from datetime import datetime
    from engine.analyzers.exclude import EXCLUDE_LABELS, PRIORITY_LABEL, parse_labels

    db = get_db(config.db_path)
    checkpoint = CheckpointManager(db)

    # 基础统计
    contact_count = db.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
    session_count = db.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    message_count = db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    moments_count = db.execute("SELECT COUNT(*) FROM moments").fetchone()[0]

    # 消息时间范围
    time_range = db.execute(
        "SELECT MIN(timestamp) AS first_ts, MAX(timestamp) AS last_ts FROM messages"
    ).fetchone()
    first_msg = (
        datetime.fromtimestamp(time_range["first_ts"]).strftime("%Y-%m-%d")
        if time_range["first_ts"] else "N/A"
    )
    last_msg = (
        datetime.fromtimestamp(time_range["last_ts"]).strftime("%Y-%m-%d")
        if time_range["last_ts"] else "N/A"
    )

    # 会话同步状态分类
    synced_ids = set()
    states = checkpoint.get_all_states()
    ok_count = 0
    error_count = 0
    error_details = []
    for st in states:
        synced_ids.add(st["session_id"])
        if st["last_error"]:
            error_count += 1
            error_details.append(st)
        else:
            ok_count += 1

    # 未进入 sync_state 的会话 = 从未成功同步（可能被 WCDB 跳过）
    all_conv_ids = {
        r[0] for r in db.execute("SELECT id FROM conversations").fetchall()
    }
    never_synced = len(all_conv_ids - synced_ids)

    # 最后同步时间
    last_sync = db.execute(
        "SELECT MAX(last_sync_at) FROM sync_state"
    ).fetchone()[0]
    last_sync_str = (
        datetime.fromtimestamp(last_sync).strftime("%Y-%m-%d %H:%M:%S")
        if last_sync else "从未同步"
    )

    # 最后一次同步日志
    last_log = db.execute(
        "SELECT * FROM sync_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    last_log_str = ""
    if last_log:
        log_time = datetime.fromtimestamp(last_log["started_at"]).strftime("%Y-%m-%d %H:%M")
        last_log_str = f"{log_time}  消息: {last_log['messages_synced']:,}  状态: {last_log['status']}"

    # 重点对象覆盖情况（置顶攻略对象）
    priority_coverage = []
    try:
        priority_rows = db.execute("""
            SELECT co.id, COALESCE(c.display_name, co.id) AS display_name,
                   co.labels, c.last_message_at
            FROM contacts co
            LEFT JOIN conversations c ON c.id = co.id
            WHERE co.labels LIKE ?
        """, (f'%{PRIORITY_LABEL}%',)).fetchall()

        for r in priority_rows:
            labels = parse_labels(r["labels"])
            if PRIORITY_LABEL not in labels:
                continue
            wxid = r["id"]
            display_name = r["display_name"]

            # 检查是否被排除
            excluded_labels = [lb for lb in labels if lb in EXCLUDE_LABELS]
            if excluded_labels:
                continue

            # 获取消息统计
            msg_stat = db.execute(
                "SELECT COUNT(*) AS cnt, MIN(timestamp) AS first_ts, MAX(timestamp) AS last_ts "
                "FROM messages WHERE conversation_id = ?",
                (wxid,),
            ).fetchone()
            msg_count = msg_stat["cnt"] if msg_stat else 0

            # 同步状态
            state = db.execute(
                "SELECT last_sync_at, last_error FROM sync_state WHERE session_id = ?",
                (wxid,),
            ).fetchone()

            first_ts = msg_stat["first_ts"] if msg_stat and msg_stat["first_ts"] else None
            last_ts = msg_stat["last_ts"] if msg_stat and msg_stat["last_ts"] else None

            priority_coverage.append({
                "name": display_name,
                "wxid_suffix": wxid[-6:] if len(wxid) > 6 else wxid,
                "msg_count": msg_count,
                "first_msg": datetime.fromtimestamp(first_ts).strftime("%Y-%m-%d") if first_ts else None,
                "last_msg": datetime.fromtimestamp(last_ts).strftime("%Y-%m-%d") if last_ts else None,
                "last_sync": state["last_sync_at"] if state else None,
                "last_error": state["last_error"] if state else None,
                "has_messages": msg_count > 0,
            })
    except Exception:
        pass

    # 组装输出
    coverage_pct = f"{ok_count / session_count * 100:.1f}%" if session_count > 0 else "N/A"

    lines = [
        f"同步状态 (core.db)",
        f"{'─' * 60}",
        f"联系人: {contact_count:,}",
        f"会话: {session_count:,}",
        f"消息: {message_count:,}  ({first_msg} ~ {last_msg})",
        f"朋友圈: {moments_count:,}",
        f"最后同步: {last_sync_str}",
    ]
    if last_log_str:
        lines.append(f"最近一次: {last_log_str}")

    lines.append("")
    lines.append("会话覆盖率:")
    lines.append(f"  成功: {ok_count}  跳过(DB未加载): {never_synced}  失败: {error_count}  覆盖率: {coverage_pct}")

    if error_details:
        lines.append("")
        lines.append("最近错误:")
        for e in error_details[:5]:
            row = db.execute(
                "SELECT display_name FROM conversations WHERE id = ?",
                (e["session_id"],),
            ).fetchone()
            name = row[0] if row else e["session_id"]
            lines.append(f"  {name}: {e['last_error'][:60]}")

    if priority_coverage:
        lines.append("")
        lines.append(f"置顶攻略对象 ({len(priority_coverage)} 个):")
        lines.append(f"  {'姓名':<16} {'消息':<8} {'时间范围':<24} {'状态'}")
        lines.append(f"  {'─' * 60}")
        for p in sorted(priority_coverage, key=lambda x: -x["msg_count"]):
            range_str = f"{p['first_msg'] or '?'} ~ {p['last_msg'] or '?'}"
            if p["last_error"]:
                status = f"ERROR: {p['last_error'][:30]}"
            elif p["msg_count"] == 0:
                status = "无消息"
            else:
                status = "OK"
            lines.append(
                f"  {p['name']:<16} {p['msg_count']:<8,} {range_str:<24} {status}"
            )

    return "\n".join(lines)
