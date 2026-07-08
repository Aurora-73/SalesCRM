"""指标模型。"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MetricValue:
    raw: float = 0.0
    normalized: float = 0.0
    confidence: float = 0.0
    sample_size: int = 0
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = {
            "raw": self.raw,
            "normalized": self.normalized,
            "confidence": self.confidence,
            "sample_size": self.sample_size,
        }
        if self.extra:
            data["extra"] = self.extra
        return data

    @classmethod
    def from_dict(cls, d: dict) -> "MetricValue":
        return cls(
            raw=d.get("raw", 0.0),
            normalized=d.get("normalized", 0.0),
            confidence=d.get("confidence", 0.0),
            sample_size=d.get("sample_size", 0),
            extra=d.get("extra", {}),
        )


@dataclass
class DeltaInfo:
    composite: float = 0.0
    rank: int = 0

    def to_dict(self) -> dict:
        return {"composite": self.composite, "rank": self.rank}

    @classmethod
    def from_dict(cls, d: dict) -> "DeltaInfo":
        return cls(composite=d.get("composite", 0.0), rank=d.get("rank", 0))


@dataclass
class Metrics:
    _id: str = ""
    base_score: float = 0.0
    composite: float = 0.0
    signal_level: str = ""
    top_target_bonus: bool = False

    # 原始指标
    fback: MetricValue = field(default_factory=MetricValue)
    rlatency: MetricValue = field(default_factory=MetricValue)
    qscore: MetricValue = field(default_factory=MetricValue)
    escore: MetricValue = field(default_factory=MetricValue)
    moments: MetricValue = field(default_factory=MetricValue)
    msg_count: MetricValue = field(default_factory=MetricValue)
    active_days: MetricValue = field(default_factory=MetricValue)
    recent: MetricValue = field(default_factory=MetricValue)
    trend: MetricValue = field(default_factory=MetricValue)

    # 新增指标
    fback_quality: MetricValue = field(default_factory=MetricValue)
    escore_volatility: MetricValue = field(default_factory=MetricValue)
    qscore_personal: MetricValue = field(default_factory=MetricValue)
    qscore_functional: MetricValue = field(default_factory=MetricValue)
    rlatency_context: MetricValue = field(default_factory=MetricValue)
    msg_volume_trend: MetricValue = field(default_factory=MetricValue)
    latency_trend: MetricValue = field(default_factory=MetricValue)

    # 跟进投入惩罚（乘法系数，不参与加权）
    neediness_penalty: float = 1.0
    volume_ratio: float = 1.0
    initiation_ratio: float = 0.5
    # 互动模式标签
    interaction_pattern: str = ""

    # 动态时间信号（signal_flags，不参与 composite 加权）
    session_recency: dict = field(default_factory=dict)
    momentum: dict = field(default_factory=dict)
    initiation_source: dict = field(default_factory=dict)
    # 媒体参与度
    media_engagement: dict = field(default_factory=dict)

    # 销售特有指标（不参与 composite 加权，仅用于销售决策公式）
    meeting_count: int = 0
    deal_stage: int = 0
    budget_known: int = 0
    decision_chain: float = 0.0
    competition: float = 0.0
    urgency: float = 0.0

    delta: DeltaInfo = field(default_factory=DeltaInfo)

    def all_metrics(self) -> dict[str, MetricValue]:
        """返回所有参与加权的 MetricValue 字段。"""
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

    def to_yaml(self) -> dict:
        data = {
            "_id": self._id,
            "base_score": round(self.base_score, 4),
            "composite": round(self.composite, 4),
            "signal_level": self.signal_level,
            "top_target_bonus": self.top_target_bonus,
            "neediness_penalty": round(self.neediness_penalty, 4),
            "volume_ratio": round(self.volume_ratio, 4),
            "initiation_ratio": round(self.initiation_ratio, 4),
            "interaction_pattern": self.interaction_pattern,
            "metrics": {k: v.to_dict() for k, v in self.all_metrics().items()},
            "delta": self.delta.to_dict(),
        }
        if self.session_recency:
            data["session_recency"] = self.session_recency
        if self.momentum:
            data["momentum"] = self.momentum
        if self.initiation_source:
            data["initiation_source"] = self.initiation_source
        if self.media_engagement:
            data["media_engagement"] = self.media_engagement
        return data

    @classmethod
    def from_yaml(cls, d: dict) -> "Metrics":
        metrics_d = d.get("metrics", {})
        return cls(
            _id=d.get("_id", ""),
            base_score=d.get("base_score", 0.0),
            composite=d.get("composite", 0.0),
            signal_level=d.get("signal_level", ""),
            top_target_bonus=d.get("top_target_bonus", False),
            neediness_penalty=d.get("neediness_penalty", 1.0),
            volume_ratio=d.get("volume_ratio", 1.0),
            initiation_ratio=d.get("initiation_ratio", 0.5),
            interaction_pattern=d.get("interaction_pattern", ""),
            fback=MetricValue.from_dict(metrics_d.get("fback", {})),
            rlatency=MetricValue.from_dict(metrics_d.get("rlatency", {})),
            qscore=MetricValue.from_dict(metrics_d.get("qscore", {})),
            escore=MetricValue.from_dict(metrics_d.get("escore", {})),
            moments=MetricValue.from_dict(metrics_d.get("moments", {})),
            msg_count=MetricValue.from_dict(metrics_d.get("msg_count", {})),
            active_days=MetricValue.from_dict(metrics_d.get("active_days", {})),
            recent=MetricValue.from_dict(metrics_d.get("recent", {})),
            trend=MetricValue.from_dict(metrics_d.get("trend", {})),
            fback_quality=MetricValue.from_dict(metrics_d.get("fback_quality", {})),
            escore_volatility=MetricValue.from_dict(metrics_d.get("escore_volatility", {})),
            qscore_personal=MetricValue.from_dict(metrics_d.get("qscore_personal", {})),
            qscore_functional=MetricValue.from_dict(metrics_d.get("qscore_functional", {})),
            rlatency_context=MetricValue.from_dict(metrics_d.get("rlatency_context", {})),
            msg_volume_trend=MetricValue.from_dict(metrics_d.get("msg_volume_trend", {})),
            latency_trend=MetricValue.from_dict(metrics_d.get("latency_trend", {})),
            session_recency=d.get("session_recency", {}),
            momentum=d.get("momentum", {}),
            initiation_source=d.get("initiation_source", {}),
            media_engagement=d.get("media_engagement", {}),
            delta=DeltaInfo.from_dict(d.get("delta", {})),
        )
