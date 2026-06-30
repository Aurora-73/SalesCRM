"""SQLite schema 初始化

创建 core.db 及所有表、索引。
WAL 模式 + 外键约束。
"""
import sqlite3
from pathlib import Path

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  INTEGER NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS contacts (
    id              TEXT PRIMARY KEY,
    nickname        TEXT,
    remark          TEXT,
    alias           TEXT,
    display_name    TEXT,
    avatar_url      TEXT,
    type            TEXT,
    labels          TEXT,
    raw_json        TEXT,
    first_seen_at   INTEGER,
    updated_at      INTEGER
);

CREATE TABLE IF NOT EXISTS conversations (
    id              TEXT PRIMARY KEY,
    type            TEXT,
    display_name    TEXT,
    contact_id      TEXT,
    last_message_at INTEGER,
    unread_count    INTEGER,
    raw_json        TEXT,
    first_seen_at   INTEGER,
    updated_at      INTEGER
);
CREATE INDEX IF NOT EXISTS idx_conv_contact ON conversations(contact_id);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    sender_id       TEXT NOT NULL,
    sender_name     TEXT,
    timestamp       INTEGER NOT NULL,
    type            INTEGER NOT NULL,
    content         TEXT,
    raw_content     TEXT,
    reply_to_id     TEXT,
    media_path      TEXT,
    group_nickname  TEXT,
    raw_json        TEXT,
    revoked         INTEGER DEFAULT 0,
    platform        TEXT DEFAULT 'wechat',
    source          TEXT DEFAULT 'sync',
    synced_at       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_conv      ON messages(conversation_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_msg_sender    ON messages(sender_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_msg_timestamp ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_msg_type      ON messages(type);

CREATE TABLE IF NOT EXISTS attachments (
    id              TEXT PRIMARY KEY,
    message_id      TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    media_type      TEXT NOT NULL,
    file_name       TEXT,
    local_path      TEXT,
    http_url        TEXT,
    file_size       INTEGER,
    downloaded      INTEGER DEFAULT 0,
    synced_at       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_att_msg  ON attachments(message_id);
CREATE INDEX IF NOT EXISTS idx_att_conv ON attachments(conversation_id);

CREATE TABLE IF NOT EXISTS moments (
    id              TEXT PRIMARY KEY,
    author_id       TEXT NOT NULL,
    author_name     TEXT,
    content         TEXT,
    timestamp       INTEGER NOT NULL,
    media_count     INTEGER,
    like_count      INTEGER,
    comment_count   INTEGER,
    raw_json        TEXT,
    synced_at       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_moment_author ON moments(author_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_moment_time   ON moments(timestamp);

CREATE TABLE IF NOT EXISTS moment_interactions (
    id              TEXT PRIMARY KEY,
    moment_id       TEXT NOT NULL,
    type            TEXT NOT NULL,
    user_id         TEXT NOT NULL,
    user_name       TEXT,
    content         TEXT,
    timestamp       INTEGER,
    synced_at       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mia_moment ON moment_interactions(moment_id);
CREATE INDEX IF NOT EXISTS idx_mia_user   ON moment_interactions(user_id);
CREATE INDEX IF NOT EXISTS idx_mia_username ON moment_interactions(user_name);

CREATE TABLE IF NOT EXISTS sync_state (
    session_id      TEXT PRIMARY KEY,
    watermark       INTEGER NOT NULL,
    message_count   INTEGER DEFAULT 0,
    last_sync_at    INTEGER NOT NULL,
    last_error      TEXT
);

CREATE TABLE IF NOT EXISTS sync_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      INTEGER NOT NULL,
    finished_at     INTEGER,
    session_id      TEXT,
    messages_synced INTEGER DEFAULT 0,
    status          TEXT,
    error_detail    TEXT
);

CREATE TABLE IF NOT EXISTS contact_excludes (
    wxid        TEXT PRIMARY KEY,
    reason      TEXT,
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS contact_merges (
    canonical_wxid  TEXT PRIMARY KEY,
    merged_wxids    TEXT NOT NULL,
    display_name    TEXT,
    created_at      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS people (
    id              TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL,
    real_name       TEXT,
    note            TEXT,
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS contact_accounts (
    id              TEXT PRIMARY KEY,
    person_id       TEXT NOT NULL,
    platform        TEXT DEFAULT 'wechat',
    wxid            TEXT,
    conversation_id TEXT,
    display_name    TEXT,
    remark          TEXT,
    nickname        TEXT,
    active          INTEGER DEFAULT 1,
    source          TEXT,
    updated_at      INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_identity_account_wxid
    ON contact_accounts(wxid);
CREATE INDEX IF NOT EXISTS idx_identity_account_person
    ON contact_accounts(person_id);

CREATE TABLE IF NOT EXISTS contact_aliases (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id       TEXT NOT NULL,
    account_id      TEXT,
    alias_type      TEXT NOT NULL,
    value           TEXT NOT NULL,
    value_norm      TEXT NOT NULL,
    sensitivity     TEXT DEFAULT 'normal',
    source          TEXT,
    created_at      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_identity_alias_norm
    ON contact_aliases(value_norm);
CREATE INDEX IF NOT EXISTS idx_identity_alias_person
    ON contact_aliases(person_id);

CREATE TABLE IF NOT EXISTS contact_identity_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    action          TEXT NOT NULL,
    person_id       TEXT,
    detail          TEXT,
    created_at      INTEGER NOT NULL
);
"""


def init_db(db_path: str | Path) -> sqlite3.Connection:
    """初始化 SQLite 数据库，创建所有表和索引。

    Args:
        db_path: 数据库文件路径

    Returns:
        sqlite3.Connection（WAL 模式，外键开启，row_factory=Row）
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL)
    conn.row_factory = sqlite3.Row
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """版本化迁移：按序执行未应用的迁移。"""
    # 确保 schema_version 表存在（兼容旧库）
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL, description TEXT)"
    )
    conn.commit()

    current = _get_schema_version(conn)
    for version, desc, func in MIGRATIONS:
        if version > current:
            func(conn)
            _set_schema_version(conn, version, desc)


def _get_schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return row[0] if row and row[0] else 0


def _set_schema_version(conn: sqlite3.Connection, version: int, description: str) -> None:
    import time
    conn.execute(
        "INSERT OR REPLACE INTO schema_version (version, applied_at, description) VALUES (?, ?, ?)",
        (version, int(time.time()), description),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# 迁移注册表
# ---------------------------------------------------------------------------

def _migration_1_add_labels(conn: sqlite3.Connection) -> None:
    """添加 contacts.labels 列。"""
    cursor = conn.execute("PRAGMA table_info(contacts)")
    columns = {row[1] for row in cursor.fetchall()}
    if "labels" not in columns:
        conn.execute("ALTER TABLE contacts ADD COLUMN labels TEXT")
        conn.commit()


def _migration_2_add_platform_source(conn: sqlite3.Connection) -> None:
    """添加 messages.platform/source 列。"""
    cursor = conn.execute("PRAGMA table_info(messages)")
    columns = {row[1] for row in cursor.fetchall()}
    if "platform" not in columns:
        conn.execute("ALTER TABLE messages ADD COLUMN platform TEXT DEFAULT 'wechat'")
    if "source" not in columns:
        conn.execute("ALTER TABLE messages ADD COLUMN source TEXT DEFAULT 'sync'")
    conn.commit()


def _migration_3_moment_username_idx(conn: sqlite3.Connection) -> None:
    """添加 moment_interactions.user_name 索引。"""
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mia_username ON moment_interactions(user_name)")
    conn.commit()


def _migration_4_identity_tables(conn: sqlite3.Connection) -> None:
    """创建身份目录表。"""
    _ensure_identity_tables(conn)


MIGRATIONS = [
    (1, "添加 contacts.labels 列", _migration_1_add_labels),
    (2, "添加 messages.platform/source 列", _migration_2_add_platform_source),
    (3, "添加 moment_interactions.user_name 索引", _migration_3_moment_username_idx),
    (4, "创建身份目录表", _migration_4_identity_tables),
]


def _ensure_identity_tables(conn: sqlite3.Connection) -> None:
    """为已有数据库补齐联系人身份目录所需表。"""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS people (
            id              TEXT PRIMARY KEY,
            display_name    TEXT NOT NULL,
            real_name       TEXT,
            note            TEXT,
            created_at      INTEGER NOT NULL,
            updated_at      INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS contact_accounts (
            id              TEXT PRIMARY KEY,
            person_id       TEXT NOT NULL,
            platform        TEXT DEFAULT 'wechat',
            wxid            TEXT,
            conversation_id TEXT,
            display_name    TEXT,
            remark          TEXT,
            nickname        TEXT,
            active          INTEGER DEFAULT 1,
            source          TEXT,
            updated_at      INTEGER NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_identity_account_wxid
            ON contact_accounts(wxid);
        CREATE INDEX IF NOT EXISTS idx_identity_account_person
            ON contact_accounts(person_id);

        CREATE TABLE IF NOT EXISTS contact_aliases (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id       TEXT NOT NULL,
            account_id      TEXT,
            alias_type      TEXT NOT NULL,
            value           TEXT NOT NULL,
            value_norm      TEXT NOT NULL,
            sensitivity     TEXT DEFAULT 'normal',
            source          TEXT,
            created_at      INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_identity_alias_norm
            ON contact_aliases(value_norm);
        CREATE INDEX IF NOT EXISTS idx_identity_alias_person
            ON contact_aliases(person_id);

        CREATE TABLE IF NOT EXISTS contact_identity_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            action          TEXT NOT NULL,
            person_id       TEXT,
            detail          TEXT,
            created_at      INTEGER NOT NULL
        );
        """
    )
    conn.commit()


def get_db(db_path: str | Path) -> sqlite3.Connection:
    """连接已有数据库（不创建表，仅设置 WAL + 外键 + Row factory）。

    Args:
        db_path: 数据库文件路径

    Returns:
        sqlite3.Connection（WAL 模式，row_factory=Row）
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    _migrate(conn)
    return conn
