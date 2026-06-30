"""WeChatDataAnalysis HTTP API 客户端。

接口与 WeFlowClient 完全兼容，内部做路径和字段映射。
上层代码（sync_contacts/sync_conversations/sync_messages/sync_moments）零改动。
"""

import json
import logging
import os
import sqlite3
import struct
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class WCDError(Exception):
    pass


class WCDClient:

    def __init__(self, base_url: str, token: str = "", timeout: int = 30,
                 decrypted_db_dir: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._decrypted_db_dir = Path(decrypted_db_dir) if decrypted_db_dir else None
        self._label_cache: dict[str, list[str]] | None = None

    def _read_labels(self) -> dict[str, list[str]]:
        """读取标签（带缓存）。需要配置 decrypted_db_dir。"""
        if self._label_cache is not None:
            return self._label_cache
        if not self._decrypted_db_dir:
            self._label_cache = {}
            return self._label_cache
        self._label_cache = _read_contact_labels(self._decrypted_db_dir)
        return self._label_cache

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        url = f"{self.base_url}{path}"
        if params:
            filtered = {k: v for k, v in params.items() if v is not None}
            if filtered:
                url += "?" + urllib.parse.urlencode(filtered)

        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise WCDError("WCD API 认证失败 (HTTP 401)") from e
            body_text = ""
            try:
                body_text = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise WCDError(f"HTTP {e.code}: {body_text}") from e
        except urllib.error.URLError as e:
            raise WCDError(f"连接 WCD API 失败: {e.reason}") from e

    def _post(self, path: str, data: dict | None = None) -> dict:
        """POST 请求（用于 /api/decrypt 等）。"""
        url = f"{self.base_url}{path}"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        body = json.dumps(data).encode("utf-8") if data else b""
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            body_text = ""
            try:
                body_text = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise WCDError(f"HTTP {e.code}: {body_text}") from e
        except urllib.error.URLError as e:
            raise WCDError(f"连接 WCD API 失败: {e.reason}") from e

    def decrypt_databases(self) -> dict:
        """用缓存密钥重新解密微信数据库（不重启微信，不重新获取密钥）。

        同步流程中自动调用，确保 WCD 数据库快照与微信最新数据同步。
        密钥从 account_keys.json 读取，无需用户交互。
        """
        if not self._decrypted_db_dir:
            logger.info("未配置 decrypted_db_dir，跳过数据库解密")
            return {"status": "skipped", "reason": "未配置 decrypted_db_dir"}

        keys_file = self._decrypted_db_dir.parent / "account_keys.json"
        if not keys_file.is_file():
            logger.info(f"密钥文件不存在: {keys_file}，跳过数据库解密")
            return {"status": "skipped", "reason": f"文件不存在: {keys_file}"}

        try:
            data = json.loads(keys_file.read_text(encoding="utf-8"))
        except Exception as e:
            raise WCDError(f"读取密钥文件失败: {e}") from e

        if not data or not isinstance(data, dict):
            return {"status": "skipped", "reason": "密钥文件为空"}

        # WCD 有多个账号时用相同密钥，只取第一个即可
        account = list(data.values())[0]
        db_key = account.get("db_key", "")
        db_path = account.get("db_key_source_db_storage_path", "")

        if not db_key or not db_path:
            raise WCDError("account_keys.json 中缺少 db_key 或 db_key_source_db_storage_path")

        logger.info("正在重新解密微信数据库（使用缓存密钥）...")
        try:
            result = self._post("/api/decrypt", {
                "key": db_key,
                "db_storage_path": db_path,
            })
        except WCDError:
            raise
        except Exception:
            raise WCDError("解密数据库失败") from None

        success = result.get("success_count", 0)
        failed = result.get("failure_count", 0)
        logger.info(f"数据库解密完成: 成功 {success}, 失败 {failed}")
        return result

    def health(self) -> bool:
        try:
            self._get("/api/health")
            return True
        except WCDError:
            return False

    def check_cached_keys(self) -> dict:
        """检查 account_keys.json 中是否已缓存密钥。"""
        if not self._decrypted_db_dir:
            return {"cached": False, "reason": "未配置 decrypted_db_dir"}
        keys_file = self._decrypted_db_dir.parent / "account_keys.json"
        if not keys_file.is_file():
            return {"cached": False, "reason": f"文件不存在: {keys_file}"}
        try:
            data = json.loads(keys_file.read_text(encoding="utf-8"))
            accounts = list(data.keys()) if isinstance(data, dict) else []
            return {"cached": bool(accounts), "accounts": accounts, "path": str(keys_file)}
        except Exception as e:
            return {"cached": False, "reason": f"解析失败: {e}"}

    def fetch_keys(self, wechat_install_path: str | None = None) -> dict:
        """获取微信数据库密钥（需要重启微信 + 扫码登录）。

        ⚠️ 不建议使用此方法：
        - 会强制关闭并重启微信进程
        - 需要用户在 60 秒内完成扫码登录
        - 频繁调用可能导致微信账号异常
        - 密钥应通过 account_keys.json 持久化，无需重复获取

        正确做法：确保 output/account_keys.json 存在且包含有效密钥。
        """
        logger.warning(
            "fetch_keys 被调用 — 这会重启微信进程并要求扫码登录，不建议频繁使用。"
            "密钥应通过 account_keys.json 持久化。"
        )
        params: dict[str, Any] = {}
        if wechat_install_path:
            params["wechat_install_path"] = wechat_install_path
        return self._get("/api/get_keys", params=params)

    def list_contacts(self, keyword: str | None = None, limit: int = 100) -> list[dict]:
        """获取联系人列表。返回格式兼容 WeFlowClient。"""
        params: dict[str, Any] = {"limit": limit}
        if keyword:
            params["keyword"] = keyword
        resp = self._get("/api/chat/contacts", params=params)

        raw_contacts = resp.get("contacts", [])

        # 从解密后的 contact.db 读取标签
        labels_map = self._read_labels()

        mapped = []
        for c in raw_contacts:
            contact_type = c.get("contactType") or c.get("type") or ""
            username = c.get("username", "")
            mapped.append({
                "id": username,
                "username": username,
                "nickname": c.get("nickname", ""),
                "remark": c.get("remark", ""),
                "alias": c.get("alias", ""),
                "displayName": c.get("name") or c.get("nickname") or c.get("remark") or username,
                "avatarUrl": c.get("avatar", ""),
                "type": contact_type,
                "labels": labels_map.get(username, []),
            })
        return mapped

    def list_sessions(self, keyword: str | None = None, limit: int = 100) -> list[dict]:
        """获取会话列表。返回格式兼容 WeFlowClient。"""
        params: dict[str, Any] = {"limit": limit}
        if keyword:
            params["keyword"] = keyword
        resp = self._get("/api/chat/sessions", params=params)

        raw_sessions = resp.get("sessions", [])
        mapped = []
        for s in raw_sessions:
            username = s.get("id") or s.get("username", "")
            is_group = s.get("isGroup", False)
            # WeFlow 的 type: 1=private, 2=group, 3=channel
            session_type = 2 if is_group else 1
            if username.startswith("gh_"):
                session_type = 3

            # lastMessageTime 格式：WCD 返回 "HH:MM" 或 "MM-DD" 等格式
            # WeFlow 返回 Unix 时间戳（秒）
            last_ts = s.get("lastTimestamp", 0)
            if not last_ts:
                # WCD 可能没有直接返回时间戳，从 lastMessageTime 推断
                last_ts = 0

            mapped.append({
                "username": username,
                "name": s.get("name", ""),
                "displayName": s.get("name", ""),
                "avatarUrl": s.get("avatar", ""),
                "type": session_type,
                "lastMessage": s.get("lastMessage", ""),
                "lastTimestamp": last_ts,
                "unreadCount": s.get("unreadCount", 0),
            })
        return mapped

    def get_messages(
        self,
        talker: str,
        limit: int = 1000,
        offset: int = 0,
        start: str | None = None,
        end: str | None = None,
    ) -> dict:
        """获取消息。返回格式兼容 WeFlowClient。

        WCD 不支持 start/end 日期参数，改为本地过滤。
        """
        params: dict[str, Any] = {
            "username": talker,
            "limit": min(limit, 500),  # WCD 上限 500
            "offset": offset,
        }

        resp = self._get("/api/chat/messages", params=params)

        raw_messages = resp.get("messages", [])

        # 本地日期过滤（WCD 不支持 start/end）
        if start or end:
            start_ts = _datestr_to_ts(start) if start else 0
            end_ts = _datestr_to_ts(end) if end else 9999999999
            filtered = []
            for m in raw_messages:
                ts = m.get("createTime", 0)
                if start_ts <= ts <= end_ts:
                    filtered.append(m)
            raw_messages = filtered

        # 字段映射：WCD → WeFlow 格式
        mapped_messages = []
        for m in raw_messages:
            # 媒体 URL：WCD 分散在 imageUrl/videoUrl/emojiUrl
            media_url = m.get("imageUrl") or m.get("videoUrl") or m.get("emojiUrl") or ""

            # 媒体类型推断
            media_type = ""
            render_type = m.get("renderType", "")
            if m.get("voiceLength"):
                media_type = "voice"
            elif m.get("imageUrl"):
                media_type = "image"
            elif m.get("videoUrl"):
                media_type = "video"
            elif m.get("emojiUrl"):
                media_type = "emoji"

            # rawContent：优先用原始内容，表情贴纸构造 XML（兼容 scan_stickers）
            raw_content = m.get("rawContent") or m.get("content", "")
            emoji_md5 = m.get("emojiMd5", "")
            if emoji_md5:
                emoji_url = m.get("emojiUrl", "")
                raw_content = f'<msg><emoji md5="{emoji_md5}" cdnurl="{emoji_url}"/></msg>'

            mapped_messages.append({
                "localId": m.get("localId", 0),
                "serverId": m.get("serverId") or m.get("serverIdStr", ""),
                "localType": m.get("type", 0),
                "createTime": m.get("createTime", 0),
                "isSend": m.get("isSent", False),
                "senderUsername": m.get("senderUsername", ""),
                "content": m.get("content", ""),
                "rawContent": raw_content,
                "parsedContent": m.get("content", ""),
                "replyToMessageId": m.get("quoteServerId") or None,
                "mediaType": media_type,
                "mediaFileName": "",
                "mediaUrl": media_url,
                "mediaLocalPath": "",
                "groupNickname": m.get("groupNickname", ""),
                "accountName": m.get("accountName", ""),
            })

        # WCD 没有 hasMore 字段，用消息数量推断
        has_more = len(raw_messages) >= min(limit, 500)

        return {
            "success": resp.get("status") == "success",
            "talker": talker,
            "count": resp.get("total", len(mapped_messages)),
            "hasMore": has_more,
            "messages": mapped_messages,
        }

    def pull_messages(
        self, session_id: str, since: int = 0, limit: int = 5000
    ) -> tuple[list[dict], int, bool]:
        """兼容接口，内部调用 get_messages。"""
        resp = self.get_messages(talker=session_id, limit=limit)
        messages = resp.get("messages", [])
        watermark = since
        for m in messages:
            ts = m.get("createTime", 0)
            if ts > watermark:
                watermark = ts
        return messages, watermark, resp.get("hasMore", False)

    def get_moments_timeline(
        self,
        limit: int = 20,
        offset: int = 0,
        usernames: str | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> dict:
        """获取朋友圈。返回格式兼容 WeFlowClient。"""
        params: dict[str, Any] = {"limit": limit}
        if offset > 0:
            params["offset"] = offset
        if usernames:
            params["usernames"] = usernames

        resp = self._get("/api/sns/timeline", params=params)

        # WCD 返回格式：{"status": "success", "posts": [...]} 或 {"timeline": [...]}
        # WeFlow 返回 {"posts": [...]}
        posts = resp.get("posts") or resp.get("timeline") or []

        # 日期过滤
        if start or end:
            start_ts = _datestr_to_ts(start) if start else 0
            end_ts = _datestr_to_ts(end) if end else 9999999999
            posts = [p for p in posts if start_ts <= p.get("createTime", 0) <= end_ts]

        return {"posts": posts}

    def get_media_url(self, relative_path: str) -> str:
        """获取媒体下载 URL。WCD 使用分类型端点。"""
        # 根据路径推断类型
        if "/images/" in relative_path or relative_path.endswith((".jpg", ".png", ".gif", ".jpeg")):
            return f"{self.base_url}/api/chat/media/image?md5={urllib.parse.quote(relative_path)}"
        elif "/voices/" in relative_path or relative_path.endswith((".slk", ".amr", ".silk")):
            return f"{self.base_url}/api/chat/media/voice?md5={urllib.parse.quote(relative_path)}"
        elif "/videos/" in relative_path or relative_path.endswith((".mp4", ".mov")):
            return f"{self.base_url}/api/chat/media/video?md5={urllib.parse.quote(relative_path)}"
        else:
            return f"{self.base_url}/api/media/resource/{urllib.parse.quote(relative_path)}"

    def download_media(self, relative_path: str, save_path: str) -> bool:
        """下载媒体文件。"""
        url = self.get_media_url(relative_path)
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = urllib.request.Request(url, headers=headers)
        try:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                with open(save_path, "wb") as f:
                    while True:
                        chunk = resp.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
            return True
        except Exception as e:
            logger.warning(f"下载媒体失败 {relative_path}: {e}")
            return False


def _datestr_to_ts(datestr: str) -> int:
    """YYYYMMDD 字符串 → Unix 时间戳。"""
    if not datestr:
        return 0
    try:
        from datetime import datetime
        dt = datetime.strptime(datestr, "%Y%m%d")
        return int(dt.timestamp())
    except (ValueError, OSError):
        return 0


# ---------------------------------------------------------------------------
# 标签提取（从解密后的 contact.db 读取）
# ---------------------------------------------------------------------------

def _find_contact_db(decrypted_db_dir: Path) -> Path | None:
    """在解密数据库目录中找到 contact.db。"""
    if not decrypted_db_dir.is_dir():
        return None
    # WeChatDataAnalysis 的解密输出在 output/databases/{account}/contact.db
    for account_dir in decrypted_db_dir.iterdir():
        if not account_dir.is_dir():
            continue
        contact_db = account_dir / "contact.db"
        if contact_db.is_file():
            return contact_db
    # 也检查直接在目录下的 contact.db
    direct = decrypted_db_dir / "contact.db"
    if direct.is_file():
        return direct
    return None


def _read_label_name_map(contact_db_path: Path) -> dict[int, str]:
    """从 contact_label 表读取 {label_id → label_name} 映射。"""
    label_map: dict[int, str] = {}
    try:
        conn = sqlite3.connect(str(contact_db_path))
        conn.row_factory = sqlite3.Row
        # 检查 contact_label 表是否存在
        table_check = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='contact_label'"
        ).fetchone()
        if not table_check:
            conn.close()
            return label_map

        # 获取列名（WeFlow 做了列名探测，这里简化处理）
        columns = {row[1] for row in conn.execute("PRAGMA table_info(contact_label)").fetchall()}

        id_col = None
        name_col = None
        for candidate in ("label_id_", "label_id", "labelId", "id"):
            if candidate in columns:
                id_col = candidate
                break
        for candidate in ("label_name_", "label_name", "labelName", "name"):
            if candidate in columns:
                name_col = candidate
                break

        if id_col and name_col:
            rows = conn.execute(
                f'SELECT "{id_col}" AS lid, "{name_col}" AS lname FROM contact_label'
            ).fetchall()
            for row in rows:
                try:
                    lid = int(row[0])
                    lname = str(row[1] or "").strip()
                    if lid > 0 and lname:
                        label_map[lid] = lname
                except (ValueError, TypeError):
                    pass

        conn.close()
    except Exception as e:
        logger.debug(f"读取 contact_label 失败: {e}")
    return label_map


def _parse_label_ids_from_extra_buffer(raw: bytes) -> list[int]:
    """从 extra_buffer 的 protobuf 中提取 field 30（标签 ID 列表）。

    WeFlow 的 extra_buffer 是 protobuf 编码。field 30 的 wire_type=2（length-delimited），
    内部是 packed repeated varint。
    """
    if not raw:
        return []

    label_ids: list[int] = []
    idx = 0
    n = len(raw)

    while idx < n:
        # 读 tag（varint）
        tag, idx = _pb_read_varint(raw, idx)
        if tag is None:
            break
        field_no = tag >> 3
        wire_type = tag & 0x7

        if wire_type == 0:  # varint
            _, idx = _pb_read_varint(raw, idx)
            if idx is None:
                break
        elif wire_type == 2:  # length-delimited
            size, idx = _pb_read_varint(raw, idx)
            if idx is None or size is None:
                break
            end = idx + int(size)
            if end > n:
                break
            chunk = raw[idx:end]
            idx = end

            if field_no == 30:
                # packed repeated varint
                sub_idx = 0
                while sub_idx < len(chunk):
                    val, sub_idx = _pb_read_varint(chunk, sub_idx)
                    if val is None:
                        break
                    label_ids.append(int(val))
        elif wire_type == 1:  # 64-bit
            idx += 8
        elif wire_type == 5:  # 32-bit
            idx += 4
        else:
            break

    return label_ids


def _pb_read_varint(data: bytes, offset: int) -> tuple[int | None, int]:
    """读取 protobuf varint。返回 (value, new_offset)，失败返回 (None, offset)。"""
    result = 0
    shift = 0
    while offset < len(data):
        b = data[offset]
        offset += 1
        result |= (b & 0x7F) << shift
        if (b & 0x80) == 0:
            return result, offset
        shift += 7
        if shift > 63:
            return None, offset
    return None, offset


def _read_contact_labels(decrypted_db_dir: Path) -> dict[str, list[str]]:
    """读取所有联系人的标签。返回 {username: [label_name, ...]}。"""
    contact_db = _find_contact_db(decrypted_db_dir)
    if not contact_db:
        return {}

    label_map = _read_label_name_map(contact_db)
    if not label_map:
        return {}

    result: dict[str, list[str]] = {}
    try:
        conn = sqlite3.connect(str(contact_db))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT username, extra_buffer FROM contact").fetchall()
        for row in rows:
            username = str(row[0] or "").strip()
            if not username:
                continue
            raw = row[1]
            if isinstance(raw, memoryview):
                raw = raw.tobytes()
            elif not isinstance(raw, (bytes, bytearray)):
                raw = b""
            ids = _parse_label_ids_from_extra_buffer(raw)
            if ids:
                names = []
                seen = set()
                for lid in ids:
                    name = label_map.get(lid)
                    if name and name not in seen:
                        seen.add(name)
                        names.append(name)
                if names:
                    result[username] = names
        conn.close()
    except Exception as e:
        logger.debug(f"读取联系人标签失败: {e}")

    return result
