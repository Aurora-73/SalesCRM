"""销售阶段模型。"""

from dataclasses import dataclass, field
from typing import Optional


STAGES = [
    "未识别", "线索", "初步接触", "深入沟通",
    "已会面", "持续跟进", "方案推进", "签约确认", "退出/失败",
]


@dataclass
class StageState:
    current_stage: str = "未识别"
    entered_at: str = ""
    days_in_current_stage: int = 0
    is_stagnant: bool = False
    next_stage: str = ""
    advancement_signals: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "current_stage": self.current_stage,
            "entered_at": self.entered_at,
            "days_in_current_stage": self.days_in_current_stage,
            "is_stagnant": self.is_stagnant,
            "next_stage": self.next_stage,
            "advancement_signals": self.advancement_signals,
            "blockers": self.blockers,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StageState":
        return cls(
            current_stage=d.get("current_stage", "未识别"),
            entered_at=d.get("entered_at", ""),
            days_in_current_stage=d.get("days_in_current_stage", 0),
            is_stagnant=d.get("is_stagnant", False),
            next_stage=d.get("next_stage", ""),
            advancement_signals=d.get("advancement_signals", []),
            blockers=d.get("blockers", []),
        )


@dataclass
class StageOverride:
    stage: str = ""
    reason: str = ""
    overridden_at: str = ""

    def to_dict(self) -> dict:
        return {"stage": self.stage, "reason": self.reason, "overridden_at": self.overridden_at}

    @classmethod
    def from_dict(cls, d: dict) -> Optional["StageOverride"]:
        if not d or not d.get("stage"):
            return None
        return cls(stage=d["stage"], reason=d.get("reason", ""), overridden_at=d.get("overridden_at", ""))


@dataclass
class EvidenceEntry:
    date: str = ""
    event: str = ""
    source: str = ""
    metrics_snapshot: dict = field(default_factory=dict)
    stage_change: str = ""

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "event": self.event,
            "source": self.source,
            "metrics_snapshot": self.metrics_snapshot,
            "stage_change": self.stage_change,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EvidenceEntry":
        return cls(
            date=d.get("date", ""),
            event=d.get("event", ""),
            source=d.get("source", ""),
            metrics_snapshot=d.get("metrics_snapshot", {}),
            stage_change=d.get("stage_change", ""),
        )


@dataclass
class Stage:
    stage_state: StageState = field(default_factory=StageState)
    stage_override: Optional[StageOverride] = None
    evidence_chain: list[EvidenceEntry] = field(default_factory=list)

    @property
    def effective_stage(self) -> str:
        if self.stage_override:
            return self.stage_override.stage
        return self.stage_state.current_stage

    def to_yaml(self) -> dict:
        d: dict = {"stage_state": self.stage_state.to_dict()}
        if self.stage_override:
            d["stage_override"] = self.stage_override.to_dict()
        else:
            d["stage_override"] = None
        d["evidence_chain"] = [e.to_dict() for e in self.evidence_chain]
        return d

    @classmethod
    def from_yaml(cls, data: dict) -> "Stage":
        return cls(
            stage_state=StageState.from_dict(data.get("stage_state", {})),
            stage_override=StageOverride.from_dict(data.get("stage_override")),
            evidence_chain=[EvidenceEntry.from_dict(e) for e in data.get("evidence_chain", [])],
        )
