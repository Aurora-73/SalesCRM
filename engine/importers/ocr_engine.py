"""OCR 引擎封装。

使用 RapidOCR (ONNX Runtime) 进行文字识别，返回带位置信息的结果。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path

from engine.config import CACHE_DIR

# OCR 缓存目录
OCR_CACHE_DIR = CACHE_DIR / "ocr"


@dataclass
class OCRResult:
    """单条 OCR 识别结果。"""
    text: str
    bbox: list[tuple[int, int]]  # 四个顶点坐标 [(x1,y1), (x2,y2), (x3,y3), (x4,y4)]
    confidence: float

    @property
    def center_x(self) -> int:
        """获取文字区域中心 x 坐标。"""
        xs = [p[0] for p in self.bbox]
        return sum(xs) // len(xs)

    @property
    def center_y(self) -> int:
        """获取文字区域中心 y 坐标。"""
        ys = [p[1] for p in self.bbox]
        return sum(ys) // len(ys)

    @property
    def left(self) -> int:
        """获取文字区域左边界 x 坐标。"""
        return min(p[0] for p in self.bbox)

    @property
    def right(self) -> int:
        """获取文字区域右边界 x 坐标。"""
        return max(p[0] for p in self.bbox)

    @property
    def top(self) -> int:
        """获取文字区域上边界 y 坐标。"""
        return min(p[1] for p in self.bbox)

    @property
    def bottom(self) -> int:
        """获取文字区域下边界 y 坐标。"""
        return max(p[1] for p in self.bbox)


def _get_image_hash(image_path: str | Path) -> str:
    """计算图片文件的 MD5 哈希（用于缓存）。"""
    path = Path(image_path)
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def _load_cache(image_hash: str) -> list[OCRResult] | None:
    """从缓存加载 OCR 结果。"""
    cache_file = OCR_CACHE_DIR / f"{image_hash}.json"
    if not cache_file.is_file():
        return None
    try:
        with open(cache_file, encoding="utf-8") as f:
            data = json.load(f)
        return [OCRResult(**item) for item in data]
    except (json.JSONDecodeError, KeyError):
        return None


def _save_cache(image_hash: str, results: list[OCRResult]) -> None:
    """保存 OCR 结果到缓存。超过 500MB 时清理最旧的文件。"""
    OCR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cleanup_cache_if_needed(OCR_CACHE_DIR, max_bytes=500 * 1024 * 1024)
    cache_file = OCR_CACHE_DIR / f"{image_hash}.json"
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in results], f, ensure_ascii=False, indent=2)


def _cleanup_cache_if_needed(cache_dir: Path, max_bytes: int) -> None:
    """缓存总大小超过 max_bytes 时，删除最旧的文件直到低于阈值。"""
    files = sorted(cache_dir.glob("*.json"), key=lambda f: f.stat().st_mtime)
    total = sum(f.stat().st_size for f in files)
    if total <= max_bytes:
        return
    for f in files:
        if total <= max_bytes:
            break
        size = f.stat().st_size
        f.unlink()
        total -= size


def _ocr_chunk(engine, image_path: str, y_offset: int = 0) -> list[OCRResult]:
    """对单个图片（或切片）执行 OCR，返回结果列表。"""
    raw_result, _ = engine(image_path)
    ocr_results: list[OCRResult] = []
    if raw_result:
        for line in raw_result:
            bbox_raw = line[0]
            bbox = [(int(p[0]), int(p[1]) + y_offset) for p in bbox_raw]
            text = line[1]
            confidence = float(line[2])
            ocr_results.append(OCRResult(
                text=text,
                bbox=bbox,
                confidence=confidence,
            ))
    return ocr_results


_MAX_DIM = 30000  # OpenCV SHRT_MAX=32767，留余量


def ocr_image(image_path: str | Path, use_cache: bool = True) -> list[OCRResult]:
    """对单张图片进行 OCR 识别。超长图片自动分片处理。

    Args:
        image_path: 图片文件路径
        use_cache: 是否使用缓存（默认 True）

    Returns:
        OCRResult 列表，按 y 坐标排序（从上到下）
    """
    image_path = Path(image_path)
    if not image_path.is_file():
        raise FileNotFoundError(f"图片不存在: {image_path}")

    # 检查缓存
    image_hash = _get_image_hash(image_path)
    if use_cache:
        cached = _load_cache(image_hash)
        if cached is not None:
            return cached

    # 初始化 OCR 引擎
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        raise ImportError(
            "rapidocr-onnxruntime 未安装。请运行: pip install rapidocr-onnxruntime"
        )

    engine = RapidOCR()

    # 检查图片尺寸，超长则分片
    from PIL import Image
    with Image.open(image_path) as img:
        w, h = img.size

    ocr_results: list[OCRResult] = []

    if h <= _MAX_DIM:
        ocr_results = _ocr_chunk(engine, str(image_path))
    else:
        # 分片处理
        import numpy as np
        img_array = np.array(Image.open(image_path).convert("RGB"))
        chunk_h = _MAX_DIM
        for y_start in range(0, h, chunk_h):
            y_end = min(y_start + chunk_h, h)
            chunk = img_array[y_start:y_end]
            # RapidOCR 接受 numpy 数组
            raw_result, _ = engine(chunk)
            if raw_result:
                for line in raw_result:
                    bbox_raw = line[0]
                    bbox = [(int(p[0]), int(p[1]) + y_start) for p in bbox_raw]
                    text = line[1]
                    confidence = float(line[2])
                    ocr_results.append(OCRResult(
                        text=text,
                        bbox=bbox,
                        confidence=confidence,
                    ))
            print(f"  分片 OCR: y={y_start}-{y_end} ({len(raw_result or [])} 条)")

    # 按 y 坐标排序
    ocr_results.sort(key=lambda r: r.center_y)

    # 保存缓存
    if use_cache:
        _save_cache(image_hash, ocr_results)

    return ocr_results


def ocr_batch(image_paths: list[str | Path], use_cache: bool = True) -> dict[str, list[OCRResult]]:
    """批量 OCR 识别。

    Args:
        image_paths: 图片文件路径列表
        use_cache: 是否使用缓存

    Returns:
        {图片路径: OCRResult 列表} 字典
    """
    results: dict[str, list[OCRResult]] = {}
    for path in image_paths:
        path_str = str(path)
        try:
            results[path_str] = ocr_image(path, use_cache=use_cache)
        except Exception as e:
            print(f"OCR 失败: {path} - {e}")
            results[path_str] = []
    return results
