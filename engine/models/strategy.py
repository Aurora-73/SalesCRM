"""策略模型。"""

from dataclasses import dataclass, field


@dataclass
class Action:
    priority: int = 0
    action: str = ""
    detail: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {"priority": self.priority, "action": self.action, "detail": self.detail, "reason": self.reason}

    @classmethod
    def from_dict(cls, d: dict) -> "Action":
        return cls(priority=d.get("priority", 0), action=d.get("action", ""),
                   detail=d.get("detail", ""), reason=d.get("reason", ""))


@dataclass
class Risk:
    description: str = ""
    source: str = ""
    severity: str = "low"

    def to_dict(self) -> dict:
        return {"description": self.description, "source": self.source, "severity": self.severity}

    @classmethod
    def from_dict(cls, d: dict) -> "Risk":
        return cls(description=d.get("description", ""), source=d.get("source", ""),
                   severity=d.get("severity", "low"))


@dataclass
class Strategy:
    _id: str = ""
    current_stage: str = ""
    heat_level: float = 0.0
    customer_intent: str = "none"
    advancement_risk: str = "low"
    actions: list[Action] = field(default_factory=list)
    risks: list[Risk] = field(default_factory=list)
    knowledge_refs: list[str] = field(default_factory=list)

    def to_yaml(self) -> dict:
        return {
            "_id": self._id,
            "current_stage": self.current_stage,
            "heat_level": round(self.heat_level, 2),
            "customer_intent": self.customer_intent,
            "advancement_risk": self.advancement_risk,
            "actions": [a.to_dict() for a in self.actions],
            "risks": [r.to_dict() for r in self.risks],
            "knowledge_refs": self.knowledge_refs,
        }

    @classmethod
    def from_yaml(cls, d: dict) -> "Strategy":
        return cls(
            _id=d.get("_id", ""),
            current_stage=d.get("current_stage", ""),
            heat_level=d.get("heat_level", 0.0),
            customer_intent=d.get("customer_intent", "none"),
            advancement_risk=d.get("advancement_risk", "low"),
            actions=[Action.from_dict(a) for a in d.get("actions", [])],
            risks=[Risk.from_dict(r) for r in d.get("risks", [])],
            knowledge_refs=d.get("knowledge_refs", []),
        )
