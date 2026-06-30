"""共享测试 fixture。"""
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def tmp_db(tmp_path):
    """创建临时 SQLite DB，含完整 schema。"""
    db_path = tmp_path / "test_core.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        PRAGMA journal_mode = WAL;
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS contacts (
            id TEXT PRIMARY KEY, nickname TEXT, remark TEXT, alias TEXT,
            display_name TEXT, avatar_url TEXT, type TEXT, labels TEXT,
            raw_json TEXT, first_seen_at INTEGER, updated_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY, type TEXT, display_name TEXT, contact_id TEXT,
            last_message_at INTEGER, unread_count INTEGER, raw_json TEXT,
            first_seen_at INTEGER, updated_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, sender_id TEXT NOT NULL,
            sender_name TEXT, timestamp INTEGER NOT NULL, type INTEGER NOT NULL,
            content TEXT, raw_content TEXT, reply_to_id TEXT, media_path TEXT,
            group_nickname TEXT, raw_json TEXT, revoked INTEGER DEFAULT 0,
            platform TEXT DEFAULT 'wechat', source TEXT DEFAULT 'sync',
            synced_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_msg_sender ON messages(sender_id, timestamp);

        CREATE TABLE IF NOT EXISTS moments (
            id TEXT PRIMARY KEY, author_id TEXT NOT NULL, author_name TEXT,
            content TEXT, timestamp INTEGER NOT NULL, media_count INTEGER,
            like_count INTEGER, comment_count INTEGER, raw_json TEXT,
            synced_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS moment_interactions (
            id TEXT PRIMARY KEY, moment_id TEXT NOT NULL, type TEXT NOT NULL,
            user_id TEXT NOT NULL, user_name TEXT, content TEXT,
            timestamp INTEGER, synced_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS people (
            id TEXT PRIMARY KEY, display_name TEXT NOT NULL, real_name TEXT,
            note TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS contact_accounts (
            id TEXT PRIMARY KEY, person_id TEXT NOT NULL, platform TEXT DEFAULT 'wechat',
            wxid TEXT, conversation_id TEXT, display_name TEXT, remark TEXT,
            nickname TEXT, active INTEGER DEFAULT 1, source TEXT,
            updated_at INTEGER NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_identity_account_wxid ON contact_accounts(wxid);
        CREATE INDEX IF NOT EXISTS idx_identity_account_person ON contact_accounts(person_id);

        CREATE TABLE IF NOT EXISTS contact_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT, person_id TEXT NOT NULL,
            account_id TEXT, alias_type TEXT NOT NULL, value TEXT NOT NULL,
            value_norm TEXT NOT NULL, sensitivity TEXT DEFAULT 'normal',
            source TEXT, created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_identity_alias_norm ON contact_aliases(value_norm);
        CREATE INDEX IF NOT EXISTS idx_identity_alias_person ON contact_aliases(person_id);

        CREATE TABLE IF NOT EXISTS contact_identity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL,
            person_id TEXT, detail TEXT, created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS contact_excludes (
            wxid TEXT PRIMARY KEY, reason TEXT, created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS contact_merges (
            canonical_wxid TEXT PRIMARY KEY, merged_wxids TEXT NOT NULL,
            display_name TEXT, created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL, description TEXT
        );
    """)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def test_config(tmp_path):
    """创建测试用 Config（用 mock 避免依赖真实 config.yaml）。"""
    from engine.config import Config
    data = {
        "my_name": "测试用户",
        "my_wxid": "wxid_testuser",
        "weflow": {"base_url": "http://127.0.0.1:5031", "token": "test_token"},
        "metrics": {
            "msg_count_cap": 500,
            "active_days_window": 30,
            "recency_decay": 90,
            "session_gap_hours": 4,
            "min_messages": 20,
        },
        "wiki": {"enabled": False, "path": "docs/wiki"},
    }
    return Config(data)


@pytest.fixture
def now_ts():
    """当前 Unix 时间戳。"""
    return int(time.time())


@pytest.fixture
def insert_messages(tmp_db):
    """插入测试消息的 helper fixture。返回一个闭包。"""
    _counter = 0

    def _insert(conversation_id: str, sender_id: str, content: str,
                timestamp: int, msg_type: int = 1):
        nonlocal _counter
        _counter += 1
        msg_id = f"test_msg_{_counter}"
        tmp_db.execute(
            """INSERT OR IGNORE INTO messages
               (id, conversation_id, sender_id, timestamp, type, content, synced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (msg_id, conversation_id, sender_id, timestamp, msg_type, content, timestamp),
        )
        tmp_db.commit()
        return msg_id

    return _insert


@pytest.fixture
def setup_people(tmp_db, now_ts):
    """在 DB 中创建测试用 person + account。返回闭包。"""
    def _create(person_id: str, display_name: str, wxid: str):
        tmp_db.execute(
            "INSERT OR IGNORE INTO people (id, display_name, real_name, note, created_at, updated_at) VALUES (?, ?, '', '', ?, ?)",
            (person_id, display_name, now_ts, now_ts),
        )
        tmp_db.execute(
            """INSERT OR IGNORE INTO contact_accounts
               (id, person_id, platform, wxid, conversation_id, display_name, remark, nickname, active, source, updated_at)
               VALUES (?, ?, 'wechat', ?, ?, ?, '', '', 1, 'test', ?)""",
            (f"acct_{wxid}", person_id, wxid, wxid, display_name, now_ts),
        )
        tmp_db.commit()
    return _create


@pytest.fixture
def setup_contacts(tmp_db, now_ts):
    """在 DB 中创建 contacts 和 conversations 记录（供 bootstrap_identity 使用）。返回闭包。"""
    def _create(wxid: str, nickname: str, remark: str = "", display_name: str = ""):
        effective_name = display_name or remark or nickname
        tmp_db.execute(
            """INSERT OR IGNORE INTO contacts (id, nickname, remark, display_name, type, updated_at)
               VALUES (?, ?, ?, ?, 'friend', ?)""",
            (wxid, nickname, remark, effective_name, now_ts),
        )
        tmp_db.execute(
            """INSERT OR IGNORE INTO conversations (id, type, display_name, contact_id, updated_at)
               VALUES (?, 'private', ?, ?, ?)""",
            (wxid, effective_name, wxid, now_ts),
        )
        tmp_db.commit()
    return _create
