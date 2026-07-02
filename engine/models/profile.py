"""联系人 profile 模型。"""

from dataclasses import dataclass, field
from typing import Optional

from .base import EntityBase


@dataclass
class Profile(EntityBase):
    name: str = ""
    wxid: str = ""
    wechat_id: str = ""
    nickname: str = ""
    remark: str = ""
    tags: list[str] = field(default_factory=list)
    description: str = ""
    added_date: str = ""
    age: Optional[int] = None
    occupation: str = ""

    custom_fields: dict[str, str] = field(default_factory=dict)

    def get_custom(self, key: str, default: str = "") -> str:
        """获取自定义字段值。"""
        return self.custom_fields.get(key, default)

    def set_custom(self, key: str, value: str) -> None:
        """设置自定义字段值。"""
        self.custom_fields[key] = value
        self.touch()

    def remove_custom(self, key: str) -> None:
        """删除自定义字段。"""
        if key in self.custom_fields:
            del self.custom_fields[key]
            self.touch()

    @classmethod
    def from_wechat_row(cls, row: dict) -> "Profile":
        """从 contacts 表行创建"""
        wxid = row.get("id", "")
        name = row.get("remark") or row.get("display_name") or row.get("nickname") or wxid
        return cls(
            _id=f"contact_{wxid[-6:]}" if len(wxid) >= 6 else f"contact_{wxid}",
            source="weflow-sync",
            name=name,
            wxid=wxid,
            nickname=row.get("nickname", ""),
            remark=row.get("remark", ""),
        )

    @classmethod
    def from_yaml(cls, d: dict) -> "Profile":
        return cls(
            _id=d.get("_id", ""),
            source=d.get("source", ""),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            version=d.get("version", 1),
            confidence=d.get("confidence", 1.0),
            privacy_level=d.get("privacy_level", "private"),
            name=d.get("name", ""),
            wxid=d.get("wxid", ""),
            wechat_id=d.get("wechat_id", ""),
            nickname=d.get("nickname", ""),
            remark=d.get("remark", ""),
            tags=d.get("tags", []),
            description=d.get("description", ""),
            added_date=d.get("added_date", ""),
            age=d.get("age"),
            occupation=d.get("occupation", ""),
            custom_fields=d.get("custom_fields", {}),
        )

    def to_yaml(self) -> dict:
        data = {
            "_id": self._id,
            "source": self.source,
            "name": self.name,
            "wxid": self.wxid,
            "wechat_id": self.wechat_id,
            "nickname": self.nickname,
            "remark": self.remark,
            "tags": self.tags,
            "description": self.description,
            "added_date": self.added_date,
            "age": self.age,
            "occupation": self.occupation,
        }
        if self.custom_fields:
            data["custom_fields"] = self.custom_fields
        return data
