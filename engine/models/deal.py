"""商机相关数据模型。"""

from dataclasses import dataclass, field
from typing import Optional, List

from .base import EntityBase, generate_id, now_iso


@dataclass
class DealStage:
    """商机阶段。"""
    stage_id: str
    stage_name: str
    order: int
    probability: float


@dataclass
class DealHistory:
    """商机阶段变更历史。"""
    timestamp: str = field(default_factory=now_iso)
    stage_id: str = ""
    stage_name: str = ""
    reason: str = ""


@dataclass
class Deal(EntityBase):
    """商机/交易模型。"""
    person_id: str = ""
    person_name: str = ""
    title: str = ""
    description: str = ""
    amount: float = 0.0
    currency: str = "CNY"
    current_stage: str = ""
    stage_probability: float = 0.0
    expected_close_date: str = ""
    actual_close_date: str = ""
    status: str = "open"
    competition: str = ""
    contacts: List[str] = field(default_factory=list)
    notes: str = ""
    stage_history: List[DealHistory] = field(default_factory=list)

    @classmethod
    def create(cls, person_id: str, person_name: str, title: str,
               amount: float = 0.0, stage: str = "lead") -> "Deal":
        """创建新商机。"""
        return cls(
            _id=generate_id("deal", person_id),
            person_id=person_id,
            person_name=person_name,
            title=title,
            amount=amount,
            current_stage=stage,
        )

    def advance_stage(self, stage_id: str, stage_name: str, reason: str = ""):
        """推进到下一阶段。"""
        self.stage_history.append(DealHistory(
            stage_id=self.current_stage,
            stage_name=self.current_stage,
            reason="推进到下一阶段" if not reason else reason,
        ))
        self.current_stage = stage_id
        self.stage_name = stage_name
        self.touch()

    def close(self, success: bool, reason: str = ""):
        """关闭商机。"""
        self.status = "won" if success else "lost"
        self.actual_close_date = now_iso()
        if reason:
            self.notes = f"{self.notes}\n\n关闭原因: {reason}".strip()
        self.touch()


@dataclass
class ContactInfo:
    """客户联系信息扩展。"""
    company: str = ""
    position: str = ""
    industry: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    decision_role: str = ""
    department: str = ""
