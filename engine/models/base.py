"""统一基类和 ID 生成器。"""

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


def generate_id(entity_type: str, wxid: str, suffix: str = "") -> str:
    """生成稳定主键。

    格式: <type>_<wxid_suffix>_<date_seq>
    wxid_suffix 取 wxid 的后 6 位（或 hash 前 6 位）
    """
    if not wxid:
        wxid_hash = hashlib.md5(str(time.time()).encode()).hexdigest()[:6]
    elif len(wxid) >= 6:
        wxid_hash = wxid[-6:]
    else:
        wxid_hash = wxid

    parts = [entity_type, wxid_hash]
    if suffix:
        parts.append(suffix)
    return "_".join(parts)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class EntityBase:
    """所有实体必须携带的统一元数据"""
    _id: str = ""
    source: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    version: int = 1
    confidence: float = 1.0
    privacy_level: str = "private"

    def touch(self):
        self.updated_at = now_iso()
        self.version += 1
