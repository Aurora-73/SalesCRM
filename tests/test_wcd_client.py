"""WCDClient 单元测试。"""
import pytest
import sqlite3
import struct
from pathlib import Path
from unittest.mock import patch, MagicMock
from engine.importers.wcd_client import (
    WCDClient, _datestr_to_ts,
    _pb_read_varint, _parse_label_ids_from_extra_buffer,
    _read_label_name_map, _read_contact_labels,
)


class TestDatestrToTs:
    def test_valid_date(self):
        ts = _datestr_to_ts("20260101")
        assert ts > 0
        # 2026-01-01 应在合理范围内
        assert ts > 1700000000

    def test_empty_string(self):
        assert _datestr_to_ts("") == 0

    def test_none(self):
        assert _datestr_to_ts(None) == 0

    def test_invalid_format(self):
        assert _datestr_to_ts("invalid") == 0


class TestWCDClientHealth:
    @patch.object(WCDClient, "_get")
    def test_health_ok(self, mock_get):
        mock_get.return_value = {"status": "ok"}
        client = WCDClient("http://localhost:10392")
        assert client.health() is True

    @patch.object(WCDClient, "_get")
    def test_health_fail(self, mock_get):
        from engine.importers.wcd_client import WCDError
        mock_get.side_effect = WCDError("Connection refused")
        client = WCDClient("http://localhost:10392")
        assert client.health() is False


class TestListContacts:
    @patch.object(WCDClient, "_get")
    def test_contact_mapping(self, mock_get):
        mock_get.return_value = {
            "status": "success",
            "contacts": [
                {
                    "username": "wxid_abc123",
                    "nickname": "[REDACTED]儿",
                    "remark": "鱼",
                    "alias": "fish",
                    "name": "[REDACTED]儿",
                    "avatar": "http://example.com/avatar.jpg",
                    "contactType": "friend",
                },
            ],
        }
        client = WCDClient("http://localhost:10392")
        contacts = client.list_contacts(limit=10)

        assert len(contacts) == 1
        c = contacts[0]
        assert c["id"] == "wxid_abc123"
        assert c["nickname"] == "[REDACTED]儿"
        assert c["remark"] == "鱼"
        assert c["alias"] == "fish"
        assert c["displayName"] == "[REDACTED]儿"
        assert c["avatarUrl"] == "http://example.com/avatar.jpg"
        assert c["type"] == "friend"
        assert c["labels"] == []  # WCD 不返回标签


class TestListSessions:
    @patch.object(WCDClient, "_get")
    def test_session_mapping_private(self, mock_get):
        mock_get.return_value = {
            "status": "success",
            "sessions": [
                {
                    "id": "wxid_abc123",
                    "username": "wxid_abc123",
                    "name": "[REDACTED]儿",
                    "avatar": "http://example.com/a.jpg",
                    "lastMessage": "在干嘛",
                    "lastTimestamp": 1735689600,
                    "unreadCount": 2,
                    "isGroup": False,
                    "isTop": False,
                },
            ],
        }
        client = WCDClient("http://localhost:10392")
        sessions = client.list_sessions(limit=10)

        assert len(sessions) == 1
        s = sessions[0]
        assert s["username"] == "wxid_abc123"
        assert s["displayName"] == "[REDACTED]儿"
        assert s["type"] == 1  # private

    @patch.object(WCDClient, "_get")
    def test_session_mapping_group(self, mock_get):
        mock_get.return_value = {
            "status": "success",
            "sessions": [
                {
                    "id": "12345@chatroom",
                    "username": "12345@chatroom",
                    "name": "项目群",
                    "avatar": "",
                    "lastMessage": "收到",
                    "lastTimestamp": 1735689600,
                    "unreadCount": 0,
                    "isGroup": True,
                    "isTop": False,
                },
            ],
        }
        client = WCDClient("http://localhost:10392")
        sessions = client.list_sessions(limit=10)

        assert sessions[0]["type"] == 2  # group


class TestGetMessages:
    @patch.object(WCDClient, "_get")
    def test_message_mapping(self, mock_get):
        mock_get.return_value = {
            "status": "success",
            "username": "wxid_abc123",
            "total": 2,
            "messages": [
                {
                    "localId": 1,
                    "serverId": 12345,
                    "type": 1,
                    "createTime": 1735689600,
                    "isSent": False,
                    "senderUsername": "wxid_abc123",
                    "content": "你好",
                },
                {
                    "localId": 2,
                    "serverId": 12346,
                    "type": 1,
                    "createTime": 1735689660,
                    "isSent": True,
                    "senderUsername": "wxid_me",
                    "content": "你好呀",
                },
            ],
        }
        client = WCDClient("http://localhost:10392")
        resp = client.get_messages(talker="wxid_abc123", limit=50)

        assert resp["success"] is True
        assert resp["talker"] == "wxid_abc123"
        assert resp["count"] == 2
        assert len(resp["messages"]) == 2

        m = resp["messages"][0]
        assert m["serverId"] == 12345
        assert m["localType"] == 1
        assert m["createTime"] == 1735689600
        assert m["senderUsername"] == "wxid_abc123"
        assert m["content"] == "你好"
        assert m["rawContent"] == "你好"  # WCD 无 rawContent，用 content 兜底
        assert m["parsedContent"] == "你好"
        assert m["isSend"] is False

    @patch.object(WCDClient, "_get")
    def test_has_more_true(self, mock_get):
        # 返回 500 条（上限），应推断 hasMore=True
        messages = [{"localId": i, "serverId": i, "type": 1, "createTime": 1735689600 + i,
                      "isSent": False, "senderUsername": "wxid_abc123", "content": f"msg{i}"}
                     for i in range(500)]
        mock_get.return_value = {"status": "success", "username": "wxid_abc123",
                                  "total": 500, "messages": messages}
        client = WCDClient("http://localhost:10392")
        resp = client.get_messages(talker="wxid_abc123", limit=500)
        assert resp["hasMore"] is True

    @patch.object(WCDClient, "_get")
    def test_has_more_false(self, mock_get):
        mock_get.return_value = {"status": "success", "username": "wxid_abc123",
                                  "total": 10, "messages": [{"localId": i} for i in range(10)]}
        client = WCDClient("http://localhost:10392")
        resp = client.get_messages(talker="wxid_abc123", limit=500)
        assert resp["hasMore"] is False

    @patch.object(WCDClient, "_get")
    def test_date_filter_start(self, mock_get):
        # 用实际的时间戳值（2026-01-01 和 2026-02-01 和 2026-03-01）
        ts_jan = _datestr_to_ts("20260101")
        ts_feb = _datestr_to_ts("20260201")
        ts_mar = _datestr_to_ts("20260301")

        mock_get.return_value = {
            "status": "success",
            "username": "wxid_abc123",
            "total": 3,
            "messages": [
                {"localId": 1, "serverId": 1, "type": 1, "createTime": ts_jan, "content": "old"},
                {"localId": 2, "serverId": 2, "type": 1, "createTime": ts_feb, "content": "mid"},
                {"localId": 3, "serverId": 3, "type": 1, "createTime": ts_mar, "content": "new"},
            ],
        }
        client = WCDClient("http://localhost:10392")
        # start=20260201 应过滤掉 1 月的消息
        resp = client.get_messages(talker="wxid_abc123", limit=500, start="20260201")
        assert len(resp["messages"]) == 2
        assert resp["messages"][0]["content"] == "mid"

    @patch.object(WCDClient, "_get")
    def test_media_fields(self, mock_get):
        mock_get.return_value = {
            "status": "success",
            "username": "wxid_abc123",
            "total": 1,
            "messages": [
                {
                    "localId": 1,
                    "serverId": 1,
                    "type": 3,
                    "createTime": 1735689600,
                    "isSent": False,
                    "senderUsername": "wxid_abc123",
                    "content": "[图片]",
                    "imageUrl": "http://example.com/img.jpg",
                    "quoteServerId": "999",
                },
            ],
        }
        client = WCDClient("http://localhost:10392")
        resp = client.get_messages(talker="wxid_abc123", limit=50)

        m = resp["messages"][0]
        assert m["mediaUrl"] == "http://example.com/img.jpg"
        assert m["mediaType"] == "image"
        assert m["replyToMessageId"] == "999"

    @patch.object(WCDClient, "_get")
    def test_voice_message(self, mock_get):
        mock_get.return_value = {
            "status": "success",
            "username": "wxid_abc123",
            "total": 1,
            "messages": [
                {
                    "localId": 1,
                    "serverId": 1,
                    "type": 34,
                    "createTime": 1735689600,
                    "isSent": False,
                    "senderUsername": "wxid_abc123",
                    "content": "[语音]",
                    "voiceLength": 5,
                },
            ],
        }
        client = WCDClient("http://localhost:10392")
        resp = client.get_messages(talker="wxid_abc123", limit=50)

        m = resp["messages"][0]
        assert m["mediaType"] == "voice"
        assert m["localType"] == 34


class TestGetMomentsTimeline:
    @patch.object(WCDClient, "_get")
    def test_moments_mapping(self, mock_get):
        mock_get.return_value = {
            "status": "success",
            "posts": [
                {
                    "username": "wxid_abc123",
                    "content": "今天天气真好",
                    "createTime": 1735689600,
                    "likes": ["wxid_me"],
                    "comments": [{"username": "wxid_me", "content": "[REDACTED]"}],
                },
            ],
        }
        client = WCDClient("http://localhost:10392")
        resp = client.get_moments_timeline(limit=10)

        assert "posts" in resp
        assert len(resp["posts"]) == 1
        p = resp["posts"][0]
        assert p["username"] == "wxid_abc123"
        assert p["content"] == "今天天气真好"
        assert p["createTime"] == 1735689600


class TestClientInstantiation:
    def test_default_values(self):
        client = WCDClient("http://localhost:10392")
        assert client.base_url == "http://localhost:10392"
        assert client.token == ""
        assert client.timeout == 30

    def test_strips_trailing_slash(self):
        client = WCDClient("http://localhost:10392/")
        assert client.base_url == "http://localhost:10392"

    def test_decrypted_db_dir(self):
        client = WCDClient("http://localhost:10392", decrypted_db_dir="/tmp/dbs")
        assert client._decrypted_db_dir == Path("/tmp/dbs")

    def test_no_decrypted_db_dir(self):
        client = WCDClient("http://localhost:10392")
        assert client._decrypted_db_dir is None


# ---------------------------------------------------------------------------
# 标签提取测试
# ---------------------------------------------------------------------------

def _build_protobuf_field_30(label_ids: list[int]) -> bytes:
    """构造包含 field 30（标签 ID）的 protobuf extra_buffer。"""
    # field 30, wire_type 2 (length-delimited)
    tag = (30 << 3) | 2
    # 内部是 packed repeated varint
    inner = b""
    for lid in label_ids:
        inner += _encode_varint(lid)
    return _encode_varint(tag) + _encode_varint(len(inner)) + inner


def _encode_varint(value: int) -> bytes:
    """编码 protobuf varint。"""
    parts = []
    while value > 0x7F:
        parts.append((value & 0x7F) | 0x80)
        value >>= 7
    parts.append(value & 0x7F)
    return bytes(parts)


class TestPbReadVarint:
    def test_single_byte(self):
        val, offset = _pb_read_varint(bytes([0x08]), 0)
        assert val == 8
        assert offset == 1

    def test_multi_byte(self):
        # 300 = 0xAC 0x02
        val, offset = _pb_read_varint(bytes([0xAC, 0x02]), 0)
        assert val == 300
        assert offset == 2

    def test_empty(self):
        val, offset = _pb_read_varint(b"", 0)
        assert val is None


class TestParseLabelIds:
    def test_extract_field_30(self):
        buf = _build_protobuf_field_30([1, 2, 5])
        ids = _parse_label_ids_from_extra_buffer(buf)
        assert ids == [1, 2, 5]

    def test_empty_buffer(self):
        assert _parse_label_ids_from_extra_buffer(b"") == []

    def test_no_field_30(self):
        # field 1, wire_type 0, value 42
        buf = _encode_varint((1 << 3) | 0) + _encode_varint(42)
        assert _parse_label_ids_from_extra_buffer(buf) == []

    def test_mixed_fields(self):
        # field 1 (varint) + field 30 (labels)
        buf = (
            _encode_varint((1 << 3) | 0) + _encode_varint(42) +
            _build_protobuf_field_30([10, 20])
        )
        ids = _parse_label_ids_from_extra_buffer(buf)
        assert ids == [10, 20]


class TestReadLabelNameMap:
    def test_read_from_db(self, tmp_path):
        db_path = tmp_path / "contact.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE contact_label (
                label_id_ INTEGER PRIMARY KEY,
                label_name_ TEXT
            )
        """)
        conn.execute("INSERT INTO contact_label VALUES (1, '非攻略对象')")
        conn.execute("INSERT INTO contact_label VALUES (2, '放弃')")
        conn.execute("INSERT INTO contact_label VALUES (3, '群友')")
        conn.commit()
        conn.close()

        label_map = _read_label_name_map(db_path)
        assert label_map == {1: "非攻略对象", 2: "放弃", 3: "群友"}

    def test_no_table(self, tmp_path):
        db_path = tmp_path / "contact.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE dummy (id INTEGER)")
        conn.commit()
        conn.close()

        assert _read_label_name_map(db_path) == {}


class TestReadContactLabels:
    def test_full_flow(self, tmp_path):
        """端到端测试：建表 → 插入数据 → 读取标签。"""
        db_path = tmp_path / "contact.db"
        conn = sqlite3.connect(str(db_path))

        # 建表
        conn.execute("""
            CREATE TABLE contact_label (
                label_id_ INTEGER PRIMARY KEY,
                label_name_ TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE contact (
                username TEXT PRIMARY KEY,
                extra_buffer BLOB
            )
        """)

        # 插入标签定义
        conn.execute("INSERT INTO contact_label VALUES (1, '非攻略对象')")
        conn.execute("INSERT INTO contact_label VALUES (2, '放弃')")
        conn.execute("INSERT INTO contact_label VALUES (3, '群友')")

        # 插入联系人（extra_buffer 含 field 30 标签 ID）
        buf_12 = _build_protobuf_field_30([1, 2])
        buf_3 = _build_protobuf_field_30([3])
        buf_empty = b""

        conn.execute("INSERT INTO contact VALUES (?, ?)", ("wxid_alice", buf_12))
        conn.execute("INSERT INTO contact VALUES (?, ?)", ("wxid_bob", buf_3))
        conn.execute("INSERT INTO contact VALUES (?, ?)", ("wxid_charlie", buf_empty))
        conn.commit()
        conn.close()

        result = _read_contact_labels(tmp_path)
        assert result["wxid_alice"] == ["非攻略对象", "放弃"]
        assert result["wxid_bob"] == ["群友"]
        assert "wxid_charlie" not in result  # 无标签

    def test_empty_dir(self, tmp_path):
        assert _read_contact_labels(tmp_path) == {}


class TestListContactsWithLabels:
    @patch.object(WCDClient, "_get")
    def test_labels_injected(self, mock_get, tmp_path):
        """验证 list_contacts 正确注入标签。"""
        # 准备解密数据库
        db_dir = tmp_path / "databases" / "test_account"
        db_dir.mkdir(parents=True)
        db_path = db_dir / "contact.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE contact_label (label_id_ INTEGER, label_name_ TEXT)")
        conn.execute("CREATE TABLE contact (username TEXT, extra_buffer BLOB)")
        conn.execute("INSERT INTO contact_label VALUES (1, '非攻略对象')")
        buf = _build_protobuf_field_30([1])
        conn.execute("INSERT INTO contact VALUES (?, ?)", ("wxid_abc123", buf))
        conn.commit()
        conn.close()

        mock_get.return_value = {
            "status": "success",
            "contacts": [
                {"username": "wxid_abc123", "nickname": "[REDACTED]儿", "remark": "", "alias": "",
                 "name": "[REDACTED]儿", "avatar": "", "contactType": "friend"},
            ],
        }

        client = WCDClient("http://localhost:10392", decrypted_db_dir=str(tmp_path / "databases"))
        contacts = client.list_contacts(limit=10)

        assert contacts[0]["labels"] == ["非攻略对象"]

    @patch.object(WCDClient, "_get")
    def test_no_decrypted_dir_labels_empty(self, mock_get):
        """没有配置 decrypted_db_dir 时标签为空。"""
        mock_get.return_value = {
            "status": "success",
            "contacts": [
                {"username": "wxid_abc123", "nickname": "[REDACTED]儿", "remark": "", "alias": "",
                 "name": "[REDACTED]儿", "avatar": "", "contactType": "friend"},
            ],
        }
        client = WCDClient("http://localhost:10392")
        contacts = client.list_contacts(limit=10)
        assert contacts[0]["labels"] == []
