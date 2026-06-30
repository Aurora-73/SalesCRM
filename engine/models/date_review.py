"""会面复盘模型。"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DateReview:
    date: str = ""
    location: str = ""
    duration_hours: float = 0.0
    cost: float = 0.0
    activities: list[str] = field(default_factory=list)
    initiator: str = "me"
    client_mood: str = ""
    key_discussion: bool = False
    client_response: str = ""
    client_engagement_level: str = "medium"
    comfort_level: str = "medium"
    clear_positive_feedback: bool = False
    my_performance_score: int = 3
    topic_distribution: dict = field(default_factory=dict)
    what_went_well: list[str] = field(default_factory=list)
    what_could_improve: list[str] = field(default_factory=list)
    next_step: str = ""
    next_meeting_urgency: str = "medium"
    rating: int = 3

    def to_yaml(self) -> dict:
        return {
            "date": self.date,
            "location": self.location,
            "duration_hours": self.duration_hours,
            "cost": self.cost,
            "activities": self.activities,
            "initiator": self.initiator,
            "client_mood": self.client_mood,
            "key_discussion": self.key_discussion,
            "client_response": self.client_response,
            "client_engagement_level": self.client_engagement_level,
            "comfort_level": self.comfort_level,
            "clear_positive_feedback": self.clear_positive_feedback,
            "my_performance_score": self.my_performance_score,
            "topic_distribution": self.topic_distribution,
            "what_went_well": self.what_went_well,
            "what_could_improve": self.what_could_improve,
            "next_step": self.next_step,
            "next_meeting_urgency": self.next_meeting_urgency,
            "rating": self.rating,
        }
