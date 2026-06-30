"""截图导入管道。

扫描截图目录，执行 OCR，解析消息，导出 JSON 预览，用户编辑后导入数据库。

契约：
1. 文件名排序 = 聊天时间顺序（越小越早）
2. 忽略截图文件名中的时间，OCR 内部时间仅作参考
3. 外部导入消息统一放在微信第一条消息之前 2 小时
4. 先导出 JSON 预览，用户编辑确认后才写入数据库
5. 通过 wxid（微信 ID）唯一标识联系人，不使用昵称
6. 所有消息存入 wxid 对应的 conversation，platform 仅作来源标记
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from engine.importers.ocr_engine import ocr_batch, OCRResult
from engine.importers.screenshot_parser import parse_screenshots, ParsedMessage


@dataclass
class ImportResult:
    """导入结果。"""
    wxid: str
    display_name: str
    person_id: str
    platform: str
    total_screenshots: int
    total_messages: int
    imported_messages: int
    skipped_messages: int
    failed_messages: int
    errors: list[str]


@dataclass
class ImportPreview:
    """导入预览（用户确认前的中间状态）。"""
    wxid: str
    display_name: str
    platform: str
    total_screenshots: int
    messages: list[ParsedMessage]
    errors: list[str]


def _generate_message_id(wxid: str, platform: str, content: str, timestamp: int) -> str:
    """生成消息唯一 ID。"""
    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:8]
    return f"ocr_{wxid}_{platform}_{content_hash}_{timestamp}"


def _message_exists(conn: sqlite3.Connection, message_id: str) -> bool:
    """检查消息是否已存在。"""
    cursor = conn.execute(
        "SELECT 1 FROM messages WHERE id = ?",
        (message_id,)
    )
    return cursor.fetchone() is not None


def _insert_message(
    conn: sqlite3.Connection,
    message_id: str,
    conversation_id: str,
    sender_id: str,
    sender_name: str,
    content: str,
    timestamp: int,
    platform: str,
    source: str,
) -> None:
    """插入消息到数据库。"""
    conn.execute(
        """INSERT INTO messages (id, conversation_id, sender_id, sender_name, timestamp, type,
                                content, platform, source, synced_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (message_id, conversation_id, sender_id, sender_name, timestamp, 1,
         content, platform, source, int(datetime.now().timestamp()))
    )


def _find_screenshots(directory: Path) -> list[Path]:
    """查找目录中的截图文件。"""
    extensions = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    screenshots: set[Path] = set()
    for f in directory.iterdir():
        if f.is_file() and f.suffix.lower() in extensions:
            screenshots.add(f)
    return sorted(screenshots, key=lambda p: p.name)


def _compute_base_timestamp(first_wechat_timestamp: int) -> int:
    """计算外部导入消息的基准时间戳。

    规则：放在微信第一条消息之前 2 小时。
    """
    return first_wechat_timestamp - 2 * 60 * 60


def _lookup_contact(conn: sqlite3.Connection, wxid: str) -> dict | None:
    """通过 wxid 查找联系人信息。"""
    row = conn.execute(
        "SELECT id, display_name, remark, nickname, alias FROM contacts WHERE id = ?",
        (wxid,),
    ).fetchone()
    if not row:
        # 也尝试通过 alias（微信号）查找
        row = conn.execute(
            "SELECT id, display_name, remark, nickname, alias FROM contacts WHERE alias = ?",
            (wxid,),
        ).fetchone()
    if not row:
        return None
    return {
        "wxid": row[0],
        "display_name": row[1] or row[2] or row[3] or row[0],
        "remark": row[2],
        "nickname": row[3],
        "alias": row[4],
    }


def ensure_wechat_data(conn: sqlite3.Connection, wxid: str) -> tuple[dict | None, str | None]:
    """确保微信数据可用：查找联系人 + 同步消息。

    Returns:
        (contact_info, error) — 成功返回 (contact_dict, None)，失败返回 (None, error_msg)
    """
    from engine.config import load_config
    from engine.importers.weflow_client import WeFlowClient
    from engine.importers.wcd_client import WCDClient
    from engine.importers.sync_contacts import sync_contacts
    from engine.importers.sync_conversations import sync_conversations
    from engine.importers.sync_messages import sync_one_session
    from engine.importers.checkpoint import CheckpointManager

    def _make_client(config):
        if config.weflow.backend == "wcd":
            return WCDClient(
                base_url=config.weflow.base_url,
                token=config.weflow.token,
                timeout=config.weflow.timeout,
                decrypted_db_dir=config.weflow.decrypted_db_dir or None,
            )
        return WeFlowClient(
            base_url=config.weflow.base_url,
            token=config.weflow.token,
            timeout=config.weflow.timeout,
        )

    # 1. 在已有数据中查找
    contact = _lookup_contact(conn, wxid)
    if not contact:
        # 没找到 → 拉取最新联系人列表
        print(f"未找到 {wxid}，正在拉取联系人列表...")
        try:
            config = load_config()
            client = _make_client(config)
            if not client.health():
                backend = config.weflow.backend
                return None, f"连接 {backend} 失败，请确保服务已启动"

            sync_contacts(client, conn)
            sync_conversations(client, conn)
        except Exception as e:
            return None, f"拉取联系人失败: {e}"

        contact = _lookup_contact(conn, wxid)
        if not contact:
            return None, f"微信通讯录中未找到 {wxid}，请确认微信号是否正确"

    actual_wxid = contact["wxid"]

    # 2. 检查是否已有微信消息
    row = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE conversation_id = ? AND source = 'sync'",
        (actual_wxid,),
    ).fetchone()
    has_messages = row[0] > 0

    # 3. 没有消息 → 同步
    if not has_messages:
        print(f"正在同步 {contact['display_name']} ({actual_wxid}) 的微信消息...")
        try:
            config = load_config()
            client = _make_client(config)
            checkpoint = CheckpointManager(conn)
            synced = sync_one_session(client, conn, checkpoint, actual_wxid, since=0, verbose=False)
            print(f"同步完成: +{synced} 条消息")
        except Exception as e:
            return None, f"同步消息失败: {e}"

    return contact, None


def format_preview(preview: ImportPreview) -> str:
    """格式化导入预览（纯文本，用于终端展示）。"""
    lines = []
    lines.append(f"{'='*50}")
    lines.append(f"导入预览: {preview.display_name} ({preview.wxid})")
    lines.append(f"来源平台: {preview.platform}")
    lines.append(f"{'='*50}")
    lines.append(f"截图数: {preview.total_screenshots}")
    lines.append(f"消息数: {len(preview.messages)}")
    lines.append("")

    for i, msg in enumerate(preview.messages, 1):
        side = "我" if msg.sender == "me" else "客户"
        content = msg.content.replace("\n", " / ")
        if len(content) > 40:
            content = content[:40] + "..."
        lines.append(f"{i:3d}. [{side}] {content}")

    if preview.errors:
        lines.append("")
        lines.append(f"警告 ({len(preview.errors)}):")
        for err in preview.errors:
            lines.append(f"  - {err}")

    return "\n".join(lines)


def export_preview_json(preview: ImportPreview, output_path: Path) -> Path:
    """导出预览为 JSON 文件，供用户编辑后导入。

    JSON 结构：
    {
      "wxid": "[REDACTED]",
      "display_name": "[REDACTED]",
      "platform": "xiaohongshu",
      "screenshots": 6,
      "base_time": "2026-06-05 17:51",
      "messages": [
        {"sender": "client", "content": "你好呀"},
        ...
      ]
    }

    用户可以：
    - 删除不需要的消息条目
    - 修改 sender（"me" 或 "client"）
    - 修改 content
    - 修改 base_time（调整时间位置）
    """
    base_dt = datetime.fromtimestamp(preview.messages[0].timestamp) if preview.messages else None

    data = {
        "wxid": preview.wxid,
        "display_name": preview.display_name,
        "platform": preview.platform,
        "screenshots": preview.total_screenshots,
        "base_time": base_dt.strftime("%Y-%m-%d %H:%M") if base_dt else "",
        "messages": [
            {
                "sender": msg.sender,
                "content": msg.content,
            }
            for msg in preview.messages
        ],
    }

    output_path = Path(output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return output_path


def prepare_import(
    conn: sqlite3.Connection,
    wxid: str,
    screenshot_dir: Path,
    platform: str = "wechat",
    contact_info: dict | None = None,
) -> ImportPreview:
    """执行 OCR 和解析，返回预览结果（不写入数据库）。

    调用前应先调用 ensure_wechat_data() 确保微信数据可用。

    Args:
        conn: 数据库连接
        wxid: 微信 ID
        screenshot_dir: 截图目录（必须由用户指定）
        platform: 来源平台标识
        contact_info: 联系人信息（由 ensure_wechat_data 返回）

    Returns:
        ImportPreview 预览结果
    """
    errors: list[str] = []
    display_name = contact_info.get("display_name", wxid) if contact_info else wxid

    # 验证截图目录
    if not screenshot_dir.is_dir():
        return ImportPreview(
            wxid=wxid, display_name=display_name, platform=platform,
            total_screenshots=0, messages=[], errors=[f"截图目录不存在: {screenshot_dir}"],
        )

    # 查找截图文件
    screenshots = _find_screenshots(screenshot_dir)
    if not screenshots:
        return ImportPreview(
            wxid=wxid, display_name=display_name, platform=platform,
            total_screenshots=0, messages=[], errors=[f"未找到截图文件: {screenshot_dir}"],
        )

    # 执行 OCR
    print(f"正在识别 {len(screenshots)} 张截图...")
    ocr_results_map = ocr_batch(screenshots)

    # 获取微信首条消息时间
    row = conn.execute(
        "SELECT MIN(timestamp) FROM messages WHERE conversation_id = ? AND source = 'sync'",
        (wxid,),
    ).fetchone()
    first_wechat_ts = int(row[0]) if row and row[0] else None

    if not first_wechat_ts:
        return ImportPreview(
            wxid=wxid, display_name=display_name, platform=platform,
            total_screenshots=0, messages=[], errors=[f"未找到 {display_name} 的微信聊天记录"],
        )

    # 计算基准时间（微信第一条消息前 2 小时）
    base_ts = _compute_base_timestamp(first_wechat_ts)
    base_dt = datetime.fromtimestamp(base_ts)
    print(f"外部消息基准时间: {base_dt.strftime('%Y-%m-%d %H:%M')}")

    # 解析消息
    print("正在解析消息...")
    messages = parse_screenshots(screenshot_dir, ocr_results_map, base_timestamp=base_ts)

    if not messages:
        errors.append("未识别到任何消息")

    return ImportPreview(
        wxid=wxid,
        display_name=display_name,
        platform=platform,
        total_screenshots=len(screenshots),
        messages=messages,
        errors=errors,
    )


def confirm_and_import(
    conn: sqlite3.Connection,
    preview: ImportPreview,
) -> ImportResult:
    """用户确认后执行导入。

    消息存入 wxid 对应的 conversation（与微信消息同会话）。
    """
    # 查找 person_id
    from engine.identity.directory import get_person_by_wxid
    person = get_person_by_wxid(conn, preview.wxid)
    person_id = person.id if person else ""

    if not preview.messages:
        return ImportResult(
            wxid=preview.wxid, display_name=preview.display_name,
            person_id=person_id, platform=preview.platform,
            total_screenshots=preview.total_screenshots, total_messages=0,
            imported_messages=0, skipped_messages=0, failed_messages=0,
            errors=preview.errors,
        )

    imported = 0
    skipped = 0
    failed = 0
    errors: list[str] = []

    for msg in preview.messages:
        try:
            msg_id = _generate_message_id(
                preview.wxid, preview.platform, msg.content, msg.timestamp,
            )

            if _message_exists(conn, msg_id):
                skipped += 1
                continue

            sender_id = "me" if msg.sender == "me" else preview.wxid
            sender_name = "我" if msg.sender == "me" else preview.display_name

            _insert_message(
                conn, msg_id, preview.wxid, sender_id, sender_name,
                msg.content, msg.timestamp, preview.platform, "ocr",
            )
            imported += 1

        except Exception as e:
            failed += 1
            errors.append(f"导入失败: {msg.content[:20]}... - {e}")

    conn.commit()

    return ImportResult(
        wxid=preview.wxid,
        display_name=preview.display_name,
        person_id=person_id,
        platform=preview.platform,
        total_screenshots=preview.total_screenshots,
        total_messages=len(preview.messages),
        imported_messages=imported,
        skipped_messages=skipped,
        failed_messages=failed,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# 从用户修改后的 JSON 预览文件导入
# ---------------------------------------------------------------------------


def load_preview_json(file_path: str | Path) -> tuple[list[ParsedMessage], int, str, str]:
    """从用户修改后的 JSON 预览文件解析消息列表和元数据。

    JSON 中 content 为空字符串的条目视为已删除，跳过。

    Returns:
        (ParsedMessage 列表, base_timestamp, wxid, platform)
    """
    file_path = Path(file_path)
    if not file_path.is_file():
        raise FileNotFoundError(f"预览文件不存在: {file_path}")

    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    wxid = data.get("wxid", "")
    platform = data.get("platform", "wechat")

    # 从 base_time 字符串解析基准时间戳
    base_timestamp = 0
    base_time_str = data.get("base_time", "")
    if base_time_str:
        try:
            base_timestamp = int(datetime.strptime(base_time_str, "%Y-%m-%d %H:%M").timestamp())
        except ValueError:
            pass

    messages_raw = data.get("messages", [])
    messages: list[ParsedMessage] = []

    for item in messages_raw:
        content = item.get("content", "").strip()
        if not content:
            continue

        sender = item.get("sender", "client")
        if sender not in ("me", "client"):
            sender = "client"

        messages.append(ParsedMessage(
            sender=sender,
            content=content,
            timestamp=0,
            confidence=1.0,
        ))

    return messages, base_timestamp, wxid, platform


def import_from_file(
    conn: sqlite3.Connection,
    preview_file: Path,
) -> ImportResult:
    """从用户修改后的 JSON 预览文件导入消息。

    流程：
    1. 读取 ocr_messages.json（含 wxid、base_time）
    2. 分配时间戳
    3. 写入 wxid 对应的 conversation
    """
    if not preview_file.is_file():
        return ImportResult(
            wxid="", display_name="", person_id="", platform="",
            total_screenshots=0, total_messages=0,
            imported_messages=0, skipped_messages=0, failed_messages=0,
            errors=[f"预览文件不存在: {preview_file}"],
        )

    conn.row_factory = sqlite3.Row

    # 解析消息和元数据
    messages, base_ts, wxid, platform = load_preview_json(preview_file)
    if not messages:
        return ImportResult(
            wxid=wxid, display_name="", person_id="", platform=platform,
            total_screenshots=0, total_messages=0,
            imported_messages=0, skipped_messages=0, failed_messages=0,
            errors=["预览文件中无有效消息"],
        )

    if not base_ts:
        return ImportResult(
            wxid=wxid, display_name="", person_id="", platform=platform,
            total_screenshots=0, total_messages=0,
            imported_messages=0, skipped_messages=0, failed_messages=0,
            errors=["JSON 中 base_time 格式无效，请使用 YYYY-MM-DD HH:MM 格式"],
        )

    if not wxid:
        return ImportResult(
            wxid="", display_name="", person_id="", platform=platform,
            total_screenshots=0, total_messages=0,
            imported_messages=0, skipped_messages=0, failed_messages=0,
            errors=["JSON 中缺少 wxid 字段"],
        )

    # 查找联系人
    contact = _lookup_contact(conn, wxid)
    display_name = contact.get("display_name", wxid) if contact else wxid

    # 查找 person_id
    from engine.identity.directory import get_person_by_wxid
    person = get_person_by_wxid(conn, wxid)
    person_id = person.id if person else ""

    # wxid 必须已有 conversation（来自微信同步）
    row = conn.execute(
        "SELECT id FROM conversations WHERE id = ?", (wxid,)
    ).fetchone()
    if not row:
        return ImportResult(
            wxid=wxid, display_name=display_name, person_id=person_id, platform=platform,
            total_screenshots=0, total_messages=0,
            imported_messages=0, skipped_messages=0, failed_messages=0,
            errors=[f"未找到 {wxid} 的会话，请先同步微信数据"],
        )

    # 分配时间戳
    for i, msg in enumerate(messages):
        msg.timestamp = base_ts + i

    # 导入到 wxid 对应的 conversation
    imported = 0
    skipped = 0
    failed = 0
    errors: list[str] = []

    for msg in messages:
        try:
            msg_id = _generate_message_id(wxid, platform, msg.content, msg.timestamp)
            if _message_exists(conn, msg_id):
                skipped += 1
                continue

            sender_id = "me" if msg.sender == "me" else wxid
            sender_name = "我" if msg.sender == "me" else display_name
            _insert_message(
                conn, msg_id, wxid, sender_id, sender_name,
                msg.content, msg.timestamp, platform, "ocr",
            )
            imported += 1
        except Exception as e:
            failed += 1
            errors.append(f"导入失败: {msg.content[:20]}... - {e}")

    conn.commit()

    return ImportResult(
        wxid=wxid,
        display_name=display_name,
        person_id=person_id,
        platform=platform,
        total_screenshots=0,
        total_messages=len(messages),
        imported_messages=imported,
        skipped_messages=skipped,
        failed_messages=failed,
        errors=errors,
    )
