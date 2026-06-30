"""事件模型。"""

from dataclasses import dataclass, field


@dataclass
class Event:
    _id: str = ""
    timestamp: str = ""
    event_type: str = ""
    content: str = ""
    source: str = "manual"
    confidence: float = 1.0
    tags: list[str] = field(default_factory=list)
    ref: str = ""

    def to_dict(self) -> dict:
        return {
            "_id": self._id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "content": self.content,
            "source": self.source,
            "confidence": self.confidence,
            "tags": self.tags,
            "ref": self.ref,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        return cls(
            _id=d.get("_id", ""),
            timestamp=d.get("timestamp", ""),
            event_type=d.get("event_type", ""),
            content=d.get("content", ""),
            source=d.get("source", "manual"),
            confidence=d.get("confidence", 1.0),
            tags=d.get("tags", []),
            ref=d.get("ref", ""),
        )
