"""批量 OCR 聊天截图，每张图输出同名的 .txt + .json。

递归扫描目录中的图片文件，对每张图独立执行 OCR → 气泡分组 → 发送方判断，
在图片同目录生成同名 .txt（带发送方标签的可读文本）和 .json（结构化数据）。

输出不经过 SalesCRM 主流程，专门用于 wiki 素材的批量 OCR。

Usage:
    python tools/batch_ocr_chat.py "百度网盘" --batch
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engine.importers.ocr_engine import ocr_batch, OCRResult


# ---------------------------------------------------------------------------
# 单图解析（从 screenshot_parser 独立精简，避免 parse_screenshots 的多图合并）
# ---------------------------------------------------------------------------

@dataclass
class ParsedMessage:
    sender: str
    content: str
    timestamp: int
    confidence: float


def _is_time_text(text: str) -> bool:
    patterns = [
        r"^(上午|下午)\s*\d{1,2}:\d{2}$",
        r"^昨天\s*\d{1,2}:\d{2}$",
        r"^昨日\s*\d{1,2}:\d{2}$",
        r"^\d{2}-\d{2}\s*\d{1,2}:\d{2}$",
        r"^\d{1,2}:\d{2}$",
        r"^\d{1,2}月\d{1,2}日(?:上午|下午|晚上|凌晨|早上)?\s*\d{1,2}:\d{2}",
        r"^\d{1,4}年?\d{1,2}月\d{1,2}日{1,2}$",
        r"^\d+\.?\d*[kKMG]/s",
        r"^\d+B/s$",
        # 星期X HH:MM
        r"^(星期一|星期二|星期三|星期四|星期五|星期六|星期日)\s*\d{1,2}:\d{2}",
        # 星期X（独立行）
        r"^(星期一|星期二|星期三|星期四|星期五|星期六|星期日)$",
    ]
    return any(re.match(p, text.strip()) for p in patterns)


def _is_system_message(text: str) -> bool:
    patterns = [
        r"以下是新消息", r"以上是历史消息",
        r"你已添加了", r"你撤回了一条消息", r"对方撤回了一条消息",
        r"红包", r"转账", r"拍了拍",
        r"\[图片\]", r"\[视频\]", r"\[语音\]", r"\[文件\]", r"\[位置\]",
        r"^imgPlay$", r"img\s*Play",
        r"^收付款$", r"^确认收款$", r"^转账给", r"^对方收款",
        r"^服务通知", r"^微信运动", r"^我的地址",
        r"^\[动画表情\]", r"^\[表情\]", r"^\[动画\]",
        r"^\d+\.?\d*[kKMG]/s",
        r"^使用(数据流量|无线网络)",
        r"^OMARTIST$",
        # 运营商名称（截图顶栏）
        r"中国(联通|移动|电信)",
        r"^中国铁塔",
        # 电量/信号指示
        r"^\d{1,3}%$",
        r"^\d+\s*[kKMG]?\s*[bB](ps)?$",  # 网速
        # 应用顶栏文字
        r"^<微信",        # 微信返回按钮
        r"^<返回",        # 返回按钮
        r"^\s*微信\s*$",  # 微信标题
        r"^聊天信息$",
        r"^通讯录$",
        r"^发现$",
    ]
    return any(re.search(p, text) for p in patterns)


def _group_by_bubble(items: list[OCRResult], image_width: int) -> list[list[OCRResult]]:
    if not items:
        return []
    groups: list[list[OCRResult]] = []
    cur: list[OCRResult] = [items[0]]
    for i in range(1, len(items)):
        prev = items[i - 1]
        curr = items[i]
        gap = curr.top - prev.bottom
        if gap > 20 or _is_system_message(curr.text) or _is_time_text(curr.text):
            groups.append(cur)
            cur = [curr]
        else:
            cur.append(curr)
    if cur:
        groups.append(cur)
    return groups


def _determine_senders(groups: list[list[OCRResult]], image_width: int) -> list[str]:
    if not groups:
        return []
    x_positions = []
    for g in groups:
        avg_x = sum(r.center_x for r in g) / len(g)
        x_positions.append(avg_x / image_width)
    edge = [x for x in x_positions if x < 0.35 or x > 0.65]
    if len(edge) < 2:
        avg_x = sum(x_positions) / len(x_positions)
        return ["me" if avg_x > 0.5 else "client"] * len(groups)
    c_left, c_right = min(edge), max(edge)
    for _ in range(20):
        left = [x for x in x_positions if abs(x - c_left) <= abs(x - c_right)]
        right = [x for x in x_positions if abs(x - c_left) > abs(x - c_right)]
        if left:
            c_left = sum(left) / len(left)
        if right:
            c_right = sum(right) / len(right)
        if abs(c_right - c_left) < 0.005:
            break
    if abs(c_right - c_left) < 0.15:
        mid = (c_left + c_right) / 2
        return ["me" if mid > 0.5 else "client"] * len(groups)
    return ["client" if abs(x - c_left) < abs(x - c_right) else "me" for x in x_positions]


def parse_one_image(ocr_results: list[OCRResult], image_path: Path, base_ts: int) -> list[ParsedMessage]:
    """解析单张截图的气泡消息，返回消息列表。"""
    if not ocr_results:
        return []

    # 粗略估计图片宽度
    xs = [p[0] for p in ocr_results[0].bbox]
    width = int(max(xs) * 2) if xs else 1080

    groups = _group_by_bubble(ocr_results, width)
    content_groups = []
    for g in groups:
        txt = "".join(r.text for r in g)
        if _is_system_message(txt):
            continue
        if len(g) == 1 and _is_time_text(g[0].text):
            continue
        content_groups.append(g)

    if not content_groups:
        return []

    senders = _determine_senders(content_groups, width)
    messages = []
    ts = base_ts
    for g, sender in zip(content_groups, senders):
        content = "\n".join(r.text for r in g)
        conf = sum(r.confidence for r in g) / len(g)
        messages.append(ParsedMessage(sender=sender, content=content, timestamp=ts, confidence=conf))
        ts += 1
    return messages


# ---------------------------------------------------------------------------
# 图片查找
# ---------------------------------------------------------------------------

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def find_image_files(directory: Path) -> list[Path]:
    images: list[Path] = []
    for f in directory.rglob("*"):
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS:
            images.append(f)
    return sorted(images)


def output_path_for(img_path: Path) -> tuple[Path, Path]:
    """返回 (txt路径, json路径)，与图片同名不同后缀。"""
    base = img_path.parent / img_path.stem
    return base.with_suffix(".txt"), base.with_suffix(".json")


# ---------------------------------------------------------------------------
# 格式化输出
# ---------------------------------------------------------------------------

def format_text(messages: list[ParsedMessage]) -> str:
    lines = []
    for msg in messages:
        side = "我" if msg.sender == "me" else "客户"
        t = datetime.fromtimestamp(msg.timestamp).strftime("%m-%d %H:%M")
        content_lines = msg.content.split("\n")
        for i, cl in enumerate(content_lines):
            lines.append(f"[{t}] {side}: {cl}" if i == 0 else f"       {cl}")
    return "\n".join(lines)


def format_json(messages: list[ParsedMessage]) -> list[dict]:
    return [
        {"sender": m.sender, "content": m.content, "timestamp": m.timestamp, "confidence": round(m.confidence, 3)}
        for m in messages
    ]


# ---------------------------------------------------------------------------
# 核心处理
# ---------------------------------------------------------------------------

def process_image(image_path: Path) -> int:
    """对单张图片 OCR → 解析 → 输出同名的 .txt / .json。返回消息条数。"""
    ocr_results = ocr_batch([image_path]).get(str(image_path), [])
    if not ocr_results:
        return 0

    messages = parse_one_image(ocr_results, image_path, base_ts=int(time.time()))
    if not messages:
        return 0

    txt_path, json_path = output_path_for(image_path)
    txt_path.write_text(format_text(messages), encoding="utf-8")
    json_path.write_text(json.dumps(format_json(messages), ensure_ascii=False, indent=2), encoding="utf-8")

    me = sum(1 for m in messages if m.sender == "me")
    client = sum(1 for m in messages if m.sender == "client")
    print(f"    {image_path.name} → {len(messages)}条 (我{me} 客户{client})")
    return len(messages)


def process_directory(image_paths: list[Path]) -> tuple[int, int]:
    """处理一个目录下的所有图片。返回 (图片数, 消息总数)。"""
    if not image_paths:
        return 0, 0

    leaf_dir = image_paths[0].parent
    print(f"\n{'='*60}")
    print(f"目录: {leaf_dir}")
    print(f"图片: {len(image_paths)} 张")

    t0 = time.time()
    total_msg = 0
    valid = 0

    for img_path in image_paths:
        n = process_image(img_path)
        if n > 0:
            valid += 1
        total_msg += n

    t1 = time.time()
    print(f"耗时: {t1-t0:.1f}s  |  识别: {valid}/{len(image_paths)} 张  |  消息: {total_msg} 条")
    return valid, total_msg


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="批量 OCR 聊天截图，每张图输出同名 .txt/.json")
    parser.add_argument("directory", type=str, help="截图目录路径")
    parser.add_argument("--batch", action="store_true", help="批量模式：递归处理所有子目录")
    args = parser.parse_args()

    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"错误: 目录不存在: {directory}")
        sys.exit(1)

    print(f"扫描: {directory}")
    all_images = find_image_files(directory)
    print(f"图片: {len(all_images)} 张")
    if not all_images:
        print("无图片")
        sys.exit(0)

    t_start = time.time()

    if args.batch:
        # 按叶子目录分组，每组单独处理
        groups: dict[Path, list[Path]] = {}
        for img in all_images:
            leaf = img.parent.resolve()
            groups.setdefault(leaf, []).append(img)
        for leaf, imgs in groups.items():
            imgs.sort(key=lambda p: p.name)
        sorted_leaves = sorted(groups.items(), key=lambda x: x[0])

        print(f"目录: {len(sorted_leaves)} 个\n")
        total_imgs = 0
        total_msg = 0
        for leaf, imgs in sorted_leaves:
            n_img, n_msg = process_directory(imgs)
            total_imgs += n_img
            total_msg += n_msg
    else:
        n_img, n_msg = process_directory(all_images)
        total_imgs = n_img
        total_msg = n_msg

    elapsed = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"完成: {total_imgs}/{len(all_images)} 张识别, {total_msg} 条消息, 耗时 {elapsed:.0f}s")


if __name__ == "__main__":
    main()
