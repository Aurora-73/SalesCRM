"""配置管理模块。

加载 data/system/config.yaml，提供类型安全的访问。
"""

import os
import re
import shutil
from pathlib import Path
from typing import Optional

import yaml


# 项目根目录：engine/ 的上一级
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
SYSTEM_DIR = DATA_DIR / "system"
RAW_DIR = DATA_DIR / "raw"
FACTS_DIR = DATA_DIR / "facts"
CUSTOMERS_DIR = DATA_DIR / "customers"
FACTS_PEOPLE_DIR = CUSTOMERS_DIR  # 已迁移：data/facts/people/ → data/customers/
FACTS_SELF_DIR = FACTS_DIR / "self"
OUTPUTS_DIR = DATA_DIR / "outputs"
OUTPUTS_RANKINGS_DIR = OUTPUTS_DIR / "rankings"
OUTPUTS_REPORTS_DIR = OUTPUTS_DIR / "reports"
OUTPUTS_EXPORTS_DIR = OUTPUTS_DIR / "exports"
OUTPUTS_ANALYSIS_DIR = OUTPUTS_DIR / "analysis"
OUTPUTS_EVALUATIONS_DIR = OUTPUTS_DIR / "evaluations"
CACHE_DIR = DATA_DIR / "cache"
CACHE_CHECKPOINTS_DIR = CACHE_DIR / "checkpoints"
CACHE_EMBEDDINGS_DIR = CACHE_DIR / "embeddings"
WIKI_DIR = ROOT_DIR / "docs" / "wiki"
LEGACY_WIKI_PEOPLE_DIR = ROOT_DIR / "wiki" / "people"
CONFIG_PATH = SYSTEM_DIR / "config.yaml"


def slug_display_name(name: str) -> str:
    """将 display_name 转为安全的文件名片段（去除 Windows 非法字符）。"""
    return re.sub(r'[\\/:*?"<>|]+', "_", name.strip()) or "unknown"
CONFIG_EXAMPLE_PATH = SYSTEM_DIR / "config.example.yaml"
DB_PATH = RAW_DIR / "core.db"
ATTACHMENTS_DIR = RAW_DIR / "attachments"
LEGACY_CONFIG_PATH = DATA_DIR / "config.yaml"
LEGACY_CONFIG_EXAMPLE_PATH = DATA_DIR / "config.example.yaml"
LEGACY_DB_PATH = DATA_DIR / "core.db"
LEGACY_DB_WAL_PATH = DATA_DIR / "core.db-wal"
LEGACY_DB_SHM_PATH = DATA_DIR / "core.db-shm"
LEGACY_ATTACHMENTS_DIR = DATA_DIR / "attachments"
LEGACY_RANKINGS_DIR = DATA_DIR / "rankings"
LEGACY_EXPORTS_DIR = DATA_DIR / "exports"


class ConfigError(Exception):
    """配置相关错误"""


class WeFlowConfig:
    """数据源连接配置（WeFlow 或 WeChatDataAnalysis）"""

    def __init__(self, d: dict):
        self.backend: str = d.get("backend", "weflow")  # "weflow" 或 "wcd"
        self.base_url: str = d.get("base_url", "http://127.0.0.1:5031")
        self.token: str = d.get("token", "")
        self.timeout: int = d.get("timeout", 30)
        self.page_size: int = d.get("page_size", 5000)
        self.media_download: bool = d.get("media_download", False)
        self.sync_moments: bool = d.get("sync_moments", True)
        self.decrypted_db_dir: str = d.get("decrypted_db_dir", "")  # WCD 解密数据库目录（用于标签提取）



class MetricsConfig:
    """指标计算参数"""

    def __init__(self, d: dict):
        self.msg_count_cap: int = d.get("msg_count_cap", 500)
        self.active_days_window: int = d.get("active_days_window", 30)
        self.recency_decay: int = d.get("recency_decay", 90)
        self.session_gap_hours: int = d.get("session_gap_hours", 4)
        self.min_messages: int = d.get("min_messages", 20)


class WeightsConfig:
    """指标权重"""

    def __init__(self, d: dict):
        # base weights（不含 trend）总和 = 0.90，trend = 0.10，总计 1.00
        self.fback: float = d.get("fback", 0.10)
        self.rlatency: float = d.get("rlatency", 0.10)
        self.qscore: float = d.get("qscore", 0.00)
        self.escore: float = d.get("escore", 0.05)
        self.moments: float = d.get("moments", 0.06)
        self.msg_count: float = d.get("msg_count", 0.02)
        self.active_days: float = d.get("active_days", 0.04)
        self.recent: float = d.get("recent", 0.05)
        self.trend: float = d.get("trend", 0.10)
        self.fback_quality: float = d.get("fback_quality", 0.10)
        self.escore_volatility: float = d.get("escore_volatility", 0.08)
        self.qscore_personal: float = d.get("qscore_personal", 0.10)
        self.qscore_functional: float = d.get("qscore_functional", 0.05)
        self.rlatency_context: float = d.get("rlatency_context", 0.05)
        self.msg_volume_trend: float = d.get("msg_volume_trend", 0.05)
        self.latency_trend: float = d.get("latency_trend", 0.05)

    def as_dict(self) -> dict:
        return {
            "fback": self.fback,
            "rlatency": self.rlatency,
            "qscore": self.qscore,
            "escore": self.escore,
            "moments": self.moments,
            "msg_count": self.msg_count,
            "active_days": self.active_days,
            "recent": self.recent,
            "trend": self.trend,
            "fback_quality": self.fback_quality,
            "escore_volatility": self.escore_volatility,
            "qscore_personal": self.qscore_personal,
            "qscore_functional": self.qscore_functional,
            "rlatency_context": self.rlatency_context,
            "msg_volume_trend": self.msg_volume_trend,
            "latency_trend": self.latency_trend,
        }


class RankingExcludeConfig:
    """排名排除配置"""

    def __init__(self, d: dict):
        self.name_keywords: list[str] = d.get("name_keywords", [])


class RankingConfig:
    """排名配置"""

    def __init__(self, d: dict):
        self.exclude = RankingExcludeConfig(d.get("exclude", {}))


class WikiConfig:
    """Wiki 知识库配置"""

    def __init__(self, d: dict):
        self.enabled: bool = d.get("enabled", False)
        self.path: str = d.get("path", "docs/wiki")
        self.index_file: str = d.get("index_file", "search-index.json")
        max_chars = d.get("max_chars", {})
        self.max_chars_reply: int = max_chars.get("reply", 2500)
        self.max_chars_meet: int = max_chars.get("meet", 4000)
        self.max_chars_ask: int = max_chars.get("ask", 6000)
        self.max_chars_analyze: int = max_chars.get("analyze", 8000)
        self.max_chars_weekly: int = max_chars.get("weekly", 5000)

    @property
    def root_path(self) -> Path:
        return ROOT_DIR / self.path


class Config:
    """全局配置"""

    def __init__(self, d: dict):
        self.my_name: str = d.get("my_name", "")
        self.my_wxid: str = d.get("my_wxid", "")
        self.weflow = WeFlowConfig(d.get("weflow", {}))
        self.metrics = MetricsConfig(d.get("metrics", {}))
        self.weights = WeightsConfig(d.get("weights", {}))
        self.ranking = RankingConfig(d.get("ranking", {}))
        self.wiki = WikiConfig(d.get("wiki", {}))

    @property
    def db_path(self) -> Path:
        return DB_PATH


def load_config(path: Optional[Path] = None) -> Config:
    """加载配置文件。

    优先使用指定路径，否则使用 data/system/config.yaml。
    如果配置文件不存在，从 config.example.yaml 复制一份。
    """
    ensure_data_dirs()
    config_path = path or CONFIG_PATH

    if not config_path.exists():
        if CONFIG_EXAMPLE_PATH.exists():
            shutil.copy2(CONFIG_EXAMPLE_PATH, config_path)
            print(f"已从 config.example.yaml 生成 {config_path}")
        else:
            raise ConfigError(
                f"配置文件不存在: {config_path}\n"
                f"请先运行: python -c \"from engine.importers.db_init import init_db; init_db('{config_path.parent / 'core.db'}')\""
            )

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ConfigError(f"配置文件格式错误: {config_path}")

    return Config(raw)


def ensure_data_dirs():
    """确保 data/ 下所有必要目录存在，并迁移旧布局。"""
    dirs = [
        DATA_DIR,
        SYSTEM_DIR,
        RAW_DIR,
        FACTS_DIR,
        FACTS_PEOPLE_DIR,
        FACTS_SELF_DIR,
        OUTPUTS_DIR,
        OUTPUTS_RANKINGS_DIR,
        OUTPUTS_REPORTS_DIR,
        OUTPUTS_EXPORTS_DIR,
        OUTPUTS_ANALYSIS_DIR,
        OUTPUTS_EVALUATIONS_DIR,
        CACHE_DIR,
        CACHE_CHECKPOINTS_DIR,
        CACHE_EMBEDDINGS_DIR,
        ATTACHMENTS_DIR,
        DATA_DIR / "failures",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_layout()


def _migrate_legacy_layout() -> None:
    """将旧 data 根层布局迁移到新的分层目录。"""
    _move_legacy_file(LEGACY_CONFIG_PATH, CONFIG_PATH)
    _move_legacy_file(LEGACY_CONFIG_EXAMPLE_PATH, CONFIG_EXAMPLE_PATH)
    _move_legacy_file(LEGACY_DB_PATH, DB_PATH)
    _move_legacy_file(LEGACY_DB_WAL_PATH, RAW_DIR / "core.db-wal")
    _move_legacy_file(LEGACY_DB_SHM_PATH, RAW_DIR / "core.db-shm")
    _move_legacy_dir(LEGACY_ATTACHMENTS_DIR, ATTACHMENTS_DIR)
    _move_legacy_dir(LEGACY_RANKINGS_DIR, OUTPUTS_RANKINGS_DIR)
    _move_legacy_dir(LEGACY_EXPORTS_DIR, OUTPUTS_EXPORTS_DIR)


def _move_legacy_file(src: Path, dst: Path) -> None:
    if not src.exists() or dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def _move_legacy_dir(src: Path, dst: Path) -> None:
    if not src.exists() or src == dst:
        return
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            _move_legacy_dir(item, target)
        else:
            if not target.exists():
                shutil.move(str(item), str(target))
    try:
        src.rmdir()
    except OSError:
        pass
