"""评估/验证模型。"""

from dataclasses import dataclass, field


@dataclass
class TimelineEntry:
    date: str = ""
    event: str = ""
    result: str = ""

    def to_dict(self) -> dict:
        return {"date": self.date, "event": self.event, "result": self.result}

    @classmethod
    def from_dict(cls, d: dict) -> "TimelineEntry":
        return cls(date=d.get("date", ""), event=d.get("event", ""), result=d.get("result", ""))


@dataclass
class Evaluation:
    invited: bool = False
    accepted: bool = False
    dated: bool = False
    date_feedback: str = ""
    continuing: bool = False
    entered_failure: bool = False
    timeline: list[TimelineEntry] = field(default_factory=list)

    def to_yaml(self) -> dict:
        return {
            "outcomes": {
                "invited": self.invited,
                "accepted": self.accepted,
                "dated": self.dated,
                "date_feedback": self.date_feedback,
                "continuing": self.continuing,
                "entered_failure": self.entered_failure,
            },
            "timeline": [t.to_dict() for t in self.timeline],
        }

    @classmethod
    def from_yaml(cls, d: dict) -> "Evaluation":
        outcomes = d.get("outcomes", {})
        return cls(
            invited=outcomes.get("invited", False),
            accepted=outcomes.get("accepted", False),
            dated=outcomes.get("dated", False),
            date_feedback=outcomes.get("date_feedback", ""),
            continuing=outcomes.get("continuing", False),
            entered_failure=outcomes.get("entered_failure", False),
            timeline=[TimelineEntry.from_dict(t) for t in d.get("timeline", [])],
        )
