"""贴纸包模块。

提供贴纸词典管理、自动检测和人工标注功能。
"""

from .core import (
    Sticker,
    ensure_stickers_table,
    scan_stickers,
    get_sticker,
    list_stickers,
    label_sticker,
    get_labeled_emotions,
    format_sticker_list,
)

__all__ = [
    "Sticker",
    "ensure_stickers_table",
    "scan_stickers",
    "get_sticker",
    "list_stickers",
    "label_sticker",
    "get_labeled_emotions",
    "format_sticker_list",
]
