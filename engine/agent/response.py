"""统一工具返回格式 — 给 chat_data/brief_data/message_context_data 等结构化工具使用。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolEnvelope:
    """结构化工具的标准返回信封（类型标注用）。"""
    status: str  # "ok" | "error"
    data: Any = None
    meta: dict = field(default_factory=dict)


def ok(data: Any, **meta) -> dict:
    """成功返回。"""
    return {"status": "ok", "data": data, "meta": meta}


def err(code: str, message: str, **meta) -> dict:
    """错误返回。"""
    return {"status": "error", "error": {"code": code, "message": message}, "meta": meta}
