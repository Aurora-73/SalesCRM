"""排名模型。"""

from dataclasses import dataclass, field


@dataclass
class RankedPerson:
    rank: int = 0
    name: str = ""
    _id: str = ""           # 向后兼容，等于 person_id
    person_id: str = ""     # identity 系统的 person_id
    base_score: float = 0.0
    composite: float = 0.0
    signal_level: str = ""
    stage: str = ""
    delta_rank: int = 0
    delta_composite: float = 0.0
    tags: list[str] = field(default_factory=list)
    
    interaction_pattern: str = ""
    urgency: float = 0.0
    recent_raw: int = 0

    def to_dict(self) -> dict:
        return {
            "rank": self.rank,
            "name": self.name,
            "_id": self._id,
            "person_id": self.person_id,
            "base_score": round(self.base_score, 4),
            "composite": round(self.composite, 4),
            "signal_level": self.signal_level,
            "stage": self.stage,
            "delta_rank": self.delta_rank,
            "delta_composite": round(self.delta_composite, 4),
            "tags": self.tags,
            "interaction_pattern": self.interaction_pattern,
            "urgency": round(self.urgency, 4),
            "recent_raw": self.recent_raw,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RankedPerson":
        pid = d.get("person_id", "") or d.get("_id", "")
        return cls(
            rank=d.get("rank", 0), name=d.get("name", ""),
            _id=d.get("_id", pid), person_id=pid,
            base_score=d.get("base_score", 0.0), composite=d.get("composite", 0.0),
            signal_level=d.get("signal_level", ""), stage=d.get("stage", ""),
            delta_rank=d.get("delta_rank", 0), delta_composite=d.get("delta_composite", 0.0),
            tags=d.get("tags", []),
            interaction_pattern=d.get("interaction_pattern", ""),
            urgency=d.get("urgency", 0.0),
            recent_raw=d.get("recent_raw", 0),
        )


@dataclass
class RankingChange:
    name: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "reason": self.reason}


@dataclass
class InsufficientData:
    name: str = ""
    message_count: int = 0
    status: str = "数据不足，不参与排名"

    def to_dict(self) -> dict:
        return {"name": self.name, "message_count": self.message_count, "status": self.status}


@dataclass
class Ranking:
    week: str = ""
    generated_at: str = ""
    total_candidates: int = 0
    rankings: list[RankedPerson] = field(default_factory=list)
    risers: list[RankingChange] = field(default_factory=list)
    fallers: list[RankingChange] = field(default_factory=list)
    insufficient_data: list[InsufficientData] = field(default_factory=list)
    strategy_summary: list[dict] = field(default_factory=list)
    
    hot_customers: list[RankedPerson] = field(default_factory=list)
    silent_customers: list[RankedPerson] = field(default_factory=list)
    urgent_customers: list[RankedPerson] = field(default_factory=list)

    def to_yaml(self) -> dict:
        return {
            "week": self.week,
            "generated_at": self.generated_at,
            "total_candidates": self.total_candidates,
            "rankings": [r.to_dict() for r in self.rankings],
            "changes": {
                "risers": [r.to_dict() for r in self.risers],
                "fallers": [f.to_dict() for f in self.fallers],
            },
            "insufficient_data": [i.to_dict() for i in self.insufficient_data],
            "strategy_summary": self.strategy_summary,
            "hot_customers": [h.to_dict() for h in self.hot_customers],
            "silent_customers": [s.to_dict() for s in self.silent_customers],
            "urgent_customers": [u.to_dict() for u in self.urgent_customers],
        }

    @classmethod
    def from_yaml(cls, d: dict) -> "Ranking":
        changes = d.get("changes", {})
        return cls(
            week=d.get("week", ""),
            generated_at=d.get("generated_at", ""),
            total_candidates=d.get("total_candidates", 0),
            rankings=[RankedPerson.from_dict(r) for r in d.get("rankings", [])],
            risers=[RankingChange(name=r["name"], reason=r.get("reason", "")) for r in changes.get("risers", [])],
            fallers=[RankingChange(name=f["name"], reason=f.get("reason", "")) for f in changes.get("fallers", [])],
            insufficient_data=[InsufficientData(**i) for i in d.get("insufficient_data", [])],
            strategy_summary=d.get("strategy_summary", []),
            hot_customers=[RankedPerson.from_dict(h) for h in d.get("hot_customers", [])],
            silent_customers=[RankedPerson.from_dict(s) for s in d.get("silent_customers", [])],
            urgent_customers=[RankedPerson.from_dict(u) for u in d.get("urgent_customers", [])],
        )
