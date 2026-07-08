"""贴纸词典管理。

从消息中提取贴纸 md5，建立全局词典，支持自动检测和人工标注。
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

_MD5_PATTERN = re.compile(r'md5="([a-f0-9]{32})"')
_WIDTH_PATTERN = re.compile(r'width=\s*"(\d+)"')
_HEIGHT_PATTERN = re.compile(r'height=\s*"(\d+)"')
_CDN_PATTERN = re.compile(r'cdnurl\s*=\s*"([^"]+)"')
_PRODUCTID_PATTERN = re.compile(r'productid\s*=\s*"([^"]*)"')


@dataclass
class Sticker:
    md5: str
    label: str = ""
    emotion: str = ""
    content_type: str = ""
    width: int = 0
    height: int = 0
    cdn_url: str = ""
    product_id: str = ""
    frequency: int = 0
    first_seen: int = 0
    auto_detected: str = ""
    user_verified: int = 0

    def to_dict(self) -> dict:
        return {
            "md5": self.md5, "label": self.label, "emotion": self.emotion,
            "content_type": self.content_type, "width": self.width, "height": self.height,
            "cdn_url": self.cdn_url, "product_id": self.product_id,
            "frequency": self.frequency, "first_seen": self.first_seen,
            "auto_detected": self.auto_detected, "user_verified": self.user_verified,
        }


def ensure_stickers_table(conn: sqlite3.Connection) -> None:
    """创建 stickers 表（如果不存在）。"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stickers (
            md5 TEXT PRIMARY KEY,
            label TEXT DEFAULT '',
            emotion TEXT DEFAULT '',
            content_type TEXT DEFAULT '',
            width INTEGER DEFAULT 0,
            height INTEGER DEFAULT 0,
            cdn_url TEXT DEFAULT '',
            product_id TEXT DEFAULT '',
            frequency INTEGER DEFAULT 0,
            first_seen INTEGER DEFAULT 0,
            auto_detected TEXT DEFAULT '',
            user_verified INTEGER DEFAULT 0
        )
    """)
    conn.commit()


def scan_stickers(conn: sqlite3.Connection, private_only: bool = False) -> dict:
    """扫描所有消息，提取贴纸 md5 并更新 stickers 表。

    Args:
        private_only: True 时只统计私聊贴纸（排除群聊）
    """
    ensure_stickers_table(conn)

    if private_only:
        rows = conn.execute(
            "SELECT m.raw_content, m.timestamp FROM messages m "
            "JOIN conversations c ON m.conversation_id = c.id "
            "WHERE m.type = 47 AND m.raw_content IS NOT NULL "
            "AND c.type = 'private'"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT raw_content, timestamp FROM messages "
            "WHERE type = 47 AND raw_content IS NOT NULL"
        ).fetchall()

    freq: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    metadata: dict[str, dict] = {}

    for r in rows:
        raw = r["raw_content"] or ""
        m = _MD5_PATTERN.search(raw)
        if not m:
            continue
        md5 = m.group(1)
        freq[md5] = freq.get(md5, 0) + 1
        ts = r["timestamp"] or 0
        if md5 not in first_seen or ts < first_seen[md5]:
            first_seen[md5] = ts
        if md5 not in metadata:
            w = _WIDTH_PATTERN.search(raw)
            h = _HEIGHT_PATTERN.search(raw)
            cdn = _CDN_PATTERN.search(raw)
            pid = _PRODUCTID_PATTERN.search(raw)
            metadata[md5] = {
                "width": int(w.group(1)) if w else 0,
                "height": int(h.group(1)) if h else 0,
                "cdn_url": cdn.group(1).replace("&amp;", "&") if cdn else "",
                "product_id": pid.group(1) if pid else "",
            }

    new_count = 0
    updated_count = 0
    for md5, count in freq.items():
        existing = conn.execute(
            "SELECT md5 FROM stickers WHERE md5 = ?", (md5,)
        ).fetchone()

        meta = metadata.get(md5, {})
        if existing:
            conn.execute(
                "UPDATE stickers SET frequency = ?, first_seen = MIN(first_seen, ?) WHERE md5 = ?",
                (count, first_seen.get(md5, 0), md5),
            )
            updated_count += 1
        else:
            conn.execute(
                "INSERT INTO stickers (md5, frequency, first_seen, width, height, cdn_url, product_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (md5, count, first_seen.get(md5, 0),
                 meta.get("width", 0), meta.get("height", 0),
                 meta.get("cdn_url", ""), meta.get("product_id", "")),
            )
            new_count += 1

    conn.commit()
    return {
        "total": len(freq),
        "new": new_count,
        "updated": updated_count,
        "total_messages": len(rows),
    }


def get_sticker(conn: sqlite3.Connection, md5: str) -> Sticker | None:
    """获取单个贴纸信息。"""
    row = conn.execute("SELECT * FROM stickers WHERE md5 = ?", (md5,)).fetchone()
    if not row:
        return None
    return Sticker(
        md5=row["md5"], label=row["label"], emotion=row["emotion"],
        content_type=row["content_type"], width=row["width"], height=row["height"],
        cdn_url=row["cdn_url"], product_id=row["product_id"],
        frequency=row["frequency"], first_seen=row["first_seen"],
        auto_detected=row["auto_detected"], user_verified=row["user_verified"],
    )


def list_stickers(
    conn: sqlite3.Connection,
    limit: int = 50,
    unlabeled_only: bool = False,
    min_frequency: int = 1,
) -> list[Sticker]:
    """列出贴纸，按频率降序。"""
    ensure_stickers_table(conn)
    query = "SELECT * FROM stickers WHERE frequency >= ?"
    params: list = [min_frequency]
    if unlabeled_only:
        query += " AND user_verified = 0"
    query += " ORDER BY frequency DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [
        Sticker(
            md5=r["md5"], label=r["label"], emotion=r["emotion"],
            content_type=r["content_type"], width=r["width"], height=r["height"],
            cdn_url=r["cdn_url"], product_id=r["product_id"],
            frequency=r["frequency"], first_seen=r["first_seen"],
            auto_detected=r["auto_detected"], user_verified=r["user_verified"],
        )
        for r in rows
    ]


def label_sticker(
    conn: sqlite3.Connection,
    md5: str,
    label: str = "",
    emotion: str = "",
    content_type: str = "",
) -> bool:
    """人工标注贴纸。"""
    ensure_stickers_table(conn)
    existing = conn.execute("SELECT md5 FROM stickers WHERE md5 = ?", (md5,)).fetchone()
    if not existing:
        return False

    updates = []
    params = []
    if label:
        updates.append("label = ?")
        params.append(label)
    if emotion:
        updates.append("emotion = ?")
        params.append(emotion)
    if content_type:
        updates.append("content_type = ?")
        params.append(content_type)
    if not updates:
        return False

    updates.append("user_verified = 1")
    params.append(md5)
    conn.execute(f"UPDATE stickers SET {', '.join(updates)} WHERE md5 = ?", params)
    conn.commit()
    return True


def get_labeled_emotions(conn: sqlite3.Connection) -> dict[str, str]:
    """获取所有已标注情绪的贴纸。返回 {md5: emotion}。"""
    ensure_stickers_table(conn)
    rows = conn.execute(
        "SELECT md5, emotion FROM stickers WHERE emotion != ''"
    ).fetchall()
    return {r["md5"]: r["emotion"] for r in rows}


def format_sticker_list(stickers: list[Sticker], show_auto: bool = False) -> str:
    """格式化贴纸列表。"""
    lines = []
    lines.append(f"{'#':<4} {'频率':>5} {'MD5':<14} {'标签':<15} {'情绪':<8} {'类型':<10} {'已验证':<5}")
    lines.append("-" * 70)
    for i, s in enumerate(stickers, 1):
        verified = "✓" if s.user_verified else ""
        label = s.label or "(未标注)"
        emotion = s.emotion or "-"
        ctype = s.content_type or "-"
        lines.append(f"{i:<4} {s.frequency:>5} {s.md5[:12]}... {label:<15} {emotion:<8} {ctype:<10} {verified:<5}")
    return "\n".join(lines)
