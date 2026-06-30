"""数据同步 — agent_sync, sync_person。"""
from __future__ import annotations

import sqlite3

from engine.agent.core import _get_conn, _resolve_person


def _build_sync_client(config):
    from engine.importers.weflow_client import WeFlowClient
    from engine.importers.wcd_client import WCDClient

    if config.weflow.backend == "wcd":
        return WCDClient(
            config.weflow.base_url,
            config.weflow.token,
            timeout=config.weflow.timeout,
            decrypted_db_dir=config.weflow.decrypted_db_dir or None,
        )
    return WeFlowClient(
        config.weflow.base_url,
        config.weflow.token,
        timeout=config.weflow.timeout,
    )


def _refresh_wcd_snapshot(client, config) -> str:
    if config.weflow.backend != "wcd":
        return ""
    from engine.importers.wcd_client import WCDError

    try:
        result = client.decrypt_databases()
    except WCDError as e:
        return f"WCD 快照刷新失败，使用旧快照: {e}"

    status = result.get("status")
    if status == "skipped":
        return f"WCD 快照未刷新: {result.get('reason', '未知原因')}"
    success = result.get("success_count")
    failed = result.get("failure_count")
    if success is not None or failed is not None:
        return f"WCD 快照已刷新: 成功 {success or 0}, 失败 {failed or 0}"
    return "WCD 快照已刷新"


def agent_sync(mode: str = "incremental", session_id: str | None = None, meta_only: bool = False) -> str:
    from engine.importers import run_sync, SyncError
    conn, config = _get_conn()
    try:
        result = run_sync(config, mode=mode, session_id=session_id, meta_only=meta_only)
        mode_str = "全量" if mode == "full" else "增量"
        scope_str = "（仅联系人/会话）" if meta_only else ""
        lines = [
            f"# 同步完成 ({mode_str}{scope_str})\n",
            f"- 联系人: {result.contact_count}",
            f"- 会话: {result.session_count}",
        ]
        if not meta_only:
            lines.append(f"- 消息同步: {result.total_synced:,} 条")
            lines.append(f"- 会话详情: {result.sessions_ok} 成功 / {result.sessions_skipped} 跳过 / {result.sessions_error} 失败")
        if result.moments_synced > 0:
            lines.append(f"- 朋友圈: {result.moments_synced:,} 条")
        lines.append(f"- 耗时: {result.elapsed_seconds:.1f}s")
        return "\n".join(lines)
    except SyncError as e:
        return f"同步失败: {e}"
    except Exception as e:
        return f"同步异常: {e}"
    finally:
        conn.close()


def sync_person(name: str, mode: str = "incremental") -> str:
    from engine.importers.sync_messages import sync_one_session
    from engine.importers.checkpoint import CheckpointManager
    from engine.importers.sync_contacts import sync_contacts
    from engine.importers.sync_conversations import sync_conversations
    from engine.identity import bootstrap_identity

    conn, config = _get_conn()
    try:
        client = _build_sync_client(config)
        if not client.health():
            backend_name = "WeChatDataAnalysis" if config.weflow.backend == "wcd" else "WeFlow"
            return f"连接 {backend_name} API 失败，请确保服务已启动"

        refresh_msg = _refresh_wcd_snapshot(client, config)

        person = _resolve_person(conn, name)
        if not person:
            # WCD 快照刷新后，同步元数据并重建身份索引，再给新增联系人一次解析机会。
            if config.weflow.backend == "wcd":
                sync_contacts(client, conn)
                sync_conversations(client, conn)
                bootstrap_identity(conn)
                person = _resolve_person(conn, name)
            if not person:
                return f"未找到联系人: {name}"
        if not person.accounts:
            return f"未找到联系人: {name}"

        checkpoint = CheckpointManager(conn)
        total = 0
        details = []
        for account in person.accounts:
            wxid = account.wxid
            if not wxid:
                continue
            since = 0 if mode == "full" else checkpoint.get_watermark(wxid)
            try:
                synced = sync_one_session(client, conn, checkpoint, wxid, since=since, verbose=False)
                total += synced
                if synced > 0:
                    details.append(f"- {account.display_name or wxid}: +{synced} 条")
            except Exception as e:
                details.append(f"- {account.display_name or wxid}: 失败 ({e})")

        lines = [f"# 同步完成: {person.display_name}\n"]
        if refresh_msg:
            lines.append(f"- {refresh_msg}")
        lines.append(f"- 新增消息: {total} 条")
        if details:
            lines.extend(details)
        return "\n".join(lines)
    finally:
        conn.close()
