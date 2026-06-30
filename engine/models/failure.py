"""失败案例模型。"""

from dataclasses import dataclass, field


@dataclass
class FailurePattern:
    category: str = ""
    detail: str = ""

    def to_dict(self) -> dict:
        return {"category": self.category, "detail": self.detail}

    @classmethod
    def from_dict(cls, d: dict) -> "FailurePattern":
        return cls(category=d.get("category", ""), detail=d.get("detail", ""))


@dataclass
class FailureCase:
    person_id: str = ""          # 关联的 person_id（可选）
    person: str = ""             # 人物名称（显示用）
    date: str = ""               # 发生日期
    stage: str = ""              # 当时所处阶段
    cause: str = ""              # 失败原因（一句话）
    signals: list[str] = field(default_factory=list)    # 失败信号
    outcome: str = ""            # 结果
    lesson: str = ""             # 教训
    duration_months: int = 0
    stage_reached: str = ""
    failure_reasons: list[FailurePattern] = field(default_factory=list)
    error_patterns: list[str] = field(default_factory=list)
    lessons: list[str] = field(default_factory=list)
    retrospective_detection: bool = False
    detection_signals: list[str] = field(default_factory=list)
    created_at: str = ""

    def to_yaml(self) -> dict:
        return {
            "person_id": self.person_id,
            "person": self.person,
            "date": self.date,
            "stage": self.stage,
            "cause": self.cause,
            "signals": self.signals,
            "outcome": self.outcome,
            "lesson": self.lesson,
            "duration_months": self.duration_months,
            "stage_reached": self.stage_reached,
            "failure_reasons": [r.to_dict() for r in self.failure_reasons],
            "error_patterns": self.error_patterns,
            "lessons": self.lessons,
            "retrospective_detection": self.retrospective_detection,
            "detection_signals": self.detection_signals,
            "created_at": self.created_at,
        }

    @classmethod
    def from_yaml(cls, d: dict) -> "FailureCase":
        return cls(
            person_id=d.get("person_id", ""),
            person=d.get("person", ""),
            date=d.get("date", ""),
            stage=d.get("stage", ""),
            cause=d.get("cause", ""),
            signals=d.get("signals", []),
            outcome=d.get("outcome", ""),
            lesson=d.get("lesson", ""),
            duration_months=d.get("duration_months", 0),
            stage_reached=d.get("stage_reached", ""),
            failure_reasons=[FailurePattern.from_dict(r) for r in d.get("failure_reasons", [])],
            error_patterns=d.get("error_patterns", []),
            lessons=d.get("lessons", []),
            retrospective_detection=d.get("retrospective_detection", False),
            detection_signals=d.get("detection_signals", []),
            created_at=d.get("created_at", ""),
        )
