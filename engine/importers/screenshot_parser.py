"""截图解析器。

解析聊天截图，识别消息气泡，区分发送方，提取时间戳。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image

from engine.importers.ocr_engine import OCRResult


@dataclass
class ParsedMessage:
    """解析后的消息。"""
    sender: str      # 'me' 或 'client'
    content: str
    timestamp: int   # Unix timestamp
    confidence: float


def get_image_size(image_path: str | Path) -> tuple[int, int]:
    """获取图片尺寸 (width, height)。"""
    with Image.open(image_path) as img:
        return img.size


def _extract_date_from_filename(filename: str) -> datetime | None:
    """从截图文件名提取日期时间。

    支持格式：
    - Screenshot_2026-06-05-19-53-56-57_xxx.jpg
    - 2026-06-05_19-53-56.jpg
    - 20260605_195356.jpg
    """
    # 格式 1: Screenshot_2026-06-05-19-53-56-57_xxx.jpg
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})", filename)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                          int(m.group(4)), int(m.group(5)), int(m.group(6)))
        except ValueError:
            pass

    # 格式 2: 2026-06-05_19-53-56.jpg
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})", filename)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                          int(m.group(4)), int(m.group(5)), int(m.group(6)))
        except ValueError:
            pass

    # 格式 3: 20260605_195356.jpg
    m = re.search(r"(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})", filename)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                          int(m.group(4)), int(m.group(5)), int(m.group(6)))
        except ValueError:
            pass

    return None


def _parse_time_text(time_text: str, base_date: datetime) -> int | None:
    """解析时间文本为 Unix 时间戳。

    支持格式：
    - "下午 3:42" / "上午 10:30"
    - "昨天 18:30"
    - "06-05 19:53"
    - "19:53"
    """
    time_text = time_text.strip()

    # 格式 1: "下午 3:42" / "上午 10:30"
    m = re.match(r"(上午|下午)\s*(\d{1,2}):(\d{2})", time_text)
    if m:
        period = m.group(1)
        hour = int(m.group(2))
        minute = int(m.group(3))
        if period == "下午" and hour < 12:
            hour += 12
        elif period == "上午" and hour == 12:
            hour = 0
        dt = base_date.replace(hour=hour, minute=minute, second=0)
        return int(dt.timestamp())

    # 格式 2: "昨天 18:30"
    m = re.match(r"昨天\s*(\d{1,2}):(\d{2})", time_text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        dt = (base_date - timedelta(days=1)).replace(hour=hour, minute=minute, second=0)
        return int(dt.timestamp())

    # 格式 3: "06-05 19:53"
    m = re.match(r"(\d{2})-(\d{2})\s*(\d{1,2}):(\d{2})", time_text)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        hour = int(m.group(3))
        minute = int(m.group(4))
        try:
            dt = base_date.replace(month=month, day=day, hour=hour, minute=minute, second=0)
            return int(dt.timestamp())
        except ValueError:
            pass

    # 格式 4: "19:53"
    m = re.match(r"(\d{1,2}):(\d{2})$", time_text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        dt = base_date.replace(hour=hour, minute=minute, second=0)
        return int(dt.timestamp())

    # 格式 5: "1月12日晚上20:16" 或 "1月12日下午3:42"
    m = re.match(r"(\d{1,2})月(\d{1,2})日(?:上午|下午|晚上|凌晨|早上)?\s*(\d{1,2}):(\d{2})", time_text)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        hour = int(m.group(3))
        minute = int(m.group(4))
        try:
            dt = base_date.replace(month=month, day=day, hour=hour, minute=minute, second=0)
            return int(dt.timestamp())
        except ValueError:
            pass

    return None


def _is_time_text(text: str) -> bool:
    """判断文本是否是时间戳。"""
    patterns = [
        r"^(上午|下午)\s*\d{1,2}:\d{2}$",
        r"^昨天\s*\d{1,2}:\d{2}$",
        r"^\d{2}-\d{2}\s*\d{1,2}:\d{2}$",
        r"^\d{1,2}:\d{2}$",
        # 中文日期格式: 1月12日晚上20:16、1月12日下午3:42
        r"^\d{1,2}月\d{1,2}日(上午|下午|晚上|凌晨|早上)?\s*\d{1,2}:\d{2}",
        # 纯日期: 1月12日、2026年1月12日、1月12日日（OCR 重复）
        r"^\d{1,4}年?\d{1,2}月\d{1,2}日{1,2}$",
        # 网络状态指示器
        r"^\d+\.?\d*[kKMG]/s",
        r"^\d+B/s$",
        r"^昨日\s*\d{1,2}:\d{2}$",
        # 星期X HH:MM
        r"^(星期一|星期二|星期三|星期四|星期五|星期六|星期日)\s*\d{1,2}:\d{2}",
        r"^(星期一|星期二|星期三|星期四|星期五|星期六|星期日)$",
    ]
    return any(re.match(p, text.strip()) for p in patterns)


def _is_system_message(text: str) -> bool:
    """判断是否是系统消息（非聊天内容）。"""
    system_patterns = [
        r"以下是新消息",
        r"以上是历史消息",
        r"你已添加了",
        r"你撤回了一条消息",
        r"对方撤回了一条消息",
        r"红包",
        r"转账",
        r"拍了拍",
        r"\[图片\]",
        r"\[视频\]",
        r"\[语音\]",
        r"\[文件\]",
        r"\[位置\]",
        # 应用内功能关键词
        r"^imgPlay$",
        r"img\s*Play",
        r"^收付款$",
        r"^确认收款$",
        r"^转账给",
        r"^对方收款",
        r"^服务通知",
        r"^微信运动",
        r"^我的地址",
        # 表情/贴纸占位
        r"^\[动画表情\]",
        r"^\[表情\]",
        r"^\[动画\]",
        # 网络/系统状态
        r"^\d+\.?\d*[kKMG]/s",
        r"^使用(数据流量|无线网络)",
        # OCR 常见噪声
        r"^OMARTIST$",
        # 运营商名称（截图顶栏）
        r"中国(联通|移动|电信)",
        # 电量/信号
        r"^\d{1,3}%$",
        # 应用顶栏文字
        r"^<微信",
        r"^<返回",
        r"^\s*微信\s*$",
        r"^聊天信息$",
        r"^通讯录$",
        r"^发现$",
    ]
    return any(re.search(p, text) for p in system_patterns)


def _group_by_bubble(ocr_results: list[OCRResult], image_width: int) -> list[list[OCRResult]]:
    """将 OCR 结果按消息气泡分组。

    逻辑：
    1. 系统消息和时间戳单独成组
    2. 相邻的文本行（y 坐标接近）合并为一组
    """
    if not ocr_results:
        return []

    groups: list[list[OCRResult]] = []
    current_group: list[OCRResult] = [ocr_results[0]]

    for i in range(1, len(ocr_results)):
        prev = ocr_results[i - 1]
        curr = ocr_results[i]

        # 计算垂直间距
        y_gap = curr.top - prev.bottom

        # 如果间距过大，或者是系统消息/时间戳，开始新组
        if y_gap > 20 or _is_system_message(curr.text) or _is_time_text(curr.text):
            groups.append(current_group)
            current_group = [curr]
        else:
            current_group.append(curr)

    if current_group:
        groups.append(current_group)

    return groups


def _determine_senders(
    groups: list[list[OCRResult]],
    image_width: int,
) -> list[str]:
    """根据所有气泡的 x 位置聚类判断发送方。

    用 k-means (k=2) 自动发现左右两侧的天然聚类中心，
    左侧聚类 → "client"（对方），右侧聚类 → "me"（自己）。

    优势：不依赖硬编码阈值，自适应不同聊天平台的布局差异。
    当只有一个聚类时（单侧消息），直接判断全为同一发送方。
    """
    if not groups:
        return []

    # 归一化 x 中心坐标 (0.0 = 左边缘, 1.0 = 右边缘)
    x_positions = []
    for group in groups:
        avg_x = sum(r.center_x for r in group) / len(group)
        x_positions.append(avg_x / image_width)

    # 只用边缘位置初始化聚类（排除居中的时间/系统消息干扰）
    edge_positions = [x for x in x_positions if x < 0.35 or x > 0.65]

    # ----- 情况 1: 只有一侧有消息 -----
    if len(edge_positions) < 2:
        avg_x = sum(x_positions) / len(x_positions)
        default = "me" if avg_x > 0.5 else "client"
        return [default] * len(groups)

    # ----- 情况 2: 双侧消息，k-means 聚类 -----
    c_left = min(edge_positions)
    c_right = max(edge_positions)

    for _ in range(20):
        left_group = []
        right_group = []
        for x in x_positions:
            if abs(x - c_left) <= abs(x - c_right):
                left_group.append(x)
            else:
                right_group.append(x)
        if left_group:
            new_left = sum(left_group) / len(left_group)
        else:
            new_left = c_left
        if right_group:
            new_right = sum(right_group) / len(right_group)
        else:
            new_right = c_right
        if abs(new_left - c_left) < 0.005 and abs(new_right - c_right) < 0.005:
            break
        c_left, c_right = new_left, new_right

    # 如果聚类中心太接近，说明实际只有一侧有内容
    if abs(c_right - c_left) < 0.15:
        mid = (c_left + c_right) / 2
        return ["me" if mid > 0.5 else "client"] * len(groups)

    # 分配发送方：离左中心近 = client，离右中心近 = me
    senders = []
    for x in x_positions:
        if abs(x - c_left) < abs(x - c_right):
            senders.append("client")
        else:
            senders.append("me")

    return senders


def parse_screenshot(
    image_path: str | Path,
    ocr_results: list[OCRResult],
    base_timestamp: int = 0,
) -> list[ParsedMessage]:
    """解析单张截图，返回消息列表。

    Args:
        image_path: 截图文件路径
        ocr_results: OCR 识别结果
        base_timestamp: 基准时间戳（消息从此时间开始逐秒递增）

    Returns:
        ParsedMessage 列表，按 y 坐标从上到下排列
    """
    if not ocr_results:
        return []

    # 获取图片尺寸
    width, height = get_image_size(image_path)

    # 按气泡分组
    groups = _group_by_bubble(ocr_results, width)

    # 过滤：跳过系统消息和时间戳，留下有效内容组
    content_groups: list[list[OCRResult]] = []
    content_indices: list[int] = []  # 在原 groups 中的索引
    for i, group in enumerate(groups):
        texts = [r.text for r in group]
        combined_text = "".join(texts)
        if _is_system_message(combined_text):
            continue
        if len(group) == 1 and _is_time_text(group[0].text):
            continue
        content_groups.append(group)
        content_indices.append(i)

    if not content_groups:
        return []

    # 批量判断发送方（聚类分析所有气泡的 x 位置）
    senders = _determine_senders(content_groups, width)

    messages: list[ParsedMessage] = []
    current_timestamp = base_timestamp

    for group, sender in zip(content_groups, senders):
        # 合并多行文本
        content = "\n".join(r.text for r in group)

        # 计算平均置信度
        avg_confidence = sum(r.confidence for r in group) / len(group)

        messages.append(ParsedMessage(
            sender=sender,
            content=content,
            timestamp=current_timestamp,
            confidence=avg_confidence,
        ))

        # 时间戳递增 1 秒（保持顺序）
        current_timestamp += 1

    return messages


def parse_screenshots(
    screenshot_dir: str | Path,
    ocr_results_map: dict[str, list[OCRResult]],
    base_timestamp: int = 0,
) -> list[ParsedMessage]:
    """解析多张截图，返回合并后的消息列表。

    Args:
        screenshot_dir: 截图目录
        ocr_results_map: {图片路径: OCRResult 列表} 字典
        base_timestamp: 基准时间戳（从此开始逐秒递增）

    Returns:
        所有截图的消息合并后的列表，按文件名顺序排列
    """
    all_messages: list[ParsedMessage] = []

    # 按文件名排序（契约：文件名越小 = 聊天内容越早）
    sorted_paths = sorted(ocr_results_map.keys(), key=lambda p: Path(p).name)

    offset = 0
    for image_path in sorted_paths:
        ocr_results = ocr_results_map[image_path]
        messages = parse_screenshot(image_path, ocr_results, base_timestamp=base_timestamp + offset)
        all_messages.extend(messages)
        offset += len(messages)

    return all_messages
